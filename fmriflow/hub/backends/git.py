"""Git transport backend — shells out to ``git`` / ``git lfs``.

No new Python dependency: we drive the system ``git`` CLI (and ``git lfs``
when a source uses LFS blobs), the same way the pipeline shells out to
fmriprep / heudiconv. Tokens are injected into HTTPS URLs at call time and
never written to disk config.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from fmriflow.hub.backends.base import BackendError

logger = logging.getLogger(__name__)


class GitBackend:
    def preflight(self) -> list[str]:
        missing: list[str] = []
        if shutil.which("git") is None:
            missing.append("`git` is not installed or not on PATH.")
        return missing

    # ── helpers ──

    def _run(self, args: list[str], cwd: Path | None = None,
             check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            args, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True,
        )
        if check and proc.returncode != 0:
            raise BackendError(
                f"git {' '.join(args[1:])} failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc

    def _auth_url(self, url: str, token: str | None) -> str:
        """Inject a token into an HTTPS URL (leave file://, ssh, etc.)."""
        if not token:
            return url
        parts = urlsplit(url)
        if parts.scheme != "https":
            return url
        netloc = parts.netloc.rsplit("@", 1)[-1]  # drop any existing creds
        # URL-encode the token so reserved chars (@ : / #) can't corrupt the URL.
        safe_token = quote(token, safe="")
        return urlunsplit((parts.scheme, f"oauth2:{safe_token}@{netloc}",
                           parts.path, parts.query, parts.fragment))

    def _has_lfs(self) -> bool:
        return shutil.which("git-lfs") is not None or (
            self._run(["git", "lfs", "version"], check=False).returncode == 0)

    # ── Protocol ──

    def sync(self, url: str, branch: str, dest: Path, token: str | None) -> None:
        auth = self._auth_url(url, token)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if (dest / ".git").is_dir():
            self._run(["git", "remote", "set-url", "origin", auth], cwd=dest)
            self._run(["git", "fetch", "--depth", "1", "origin", branch], cwd=dest)
            # `checkout -B` atomically points local <branch> at origin/<branch>
            # and checks it out — fatal on failure, so a failed checkout can
            # never fall through to a hard-reset of some *other* current branch.
            self._run(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=dest)
        else:
            if dest.exists():
                shutil.rmtree(dest)
            self._run(["git", "clone", "--depth", "1", "--branch", branch,
                       auth, str(dest)])
        # Best-effort LFS pull; a missing git-lfs is non-fatal (blobs stay
        # as pointer files and install will surface a clear error).
        if self._has_lfs():
            self._run(["git", "lfs", "pull"], cwd=dest, check=False)
        # Never leave a token in the on-disk remote config.
        self._run(["git", "remote", "set-url", "origin", url], cwd=dest, check=False)

    def publish(self, url: str, base_branch: str, dest: Path, token: str | None,
                push_branch: str, message: str) -> dict:
        auth = self._auth_url(url, token)
        # Configure a committer identity if the repo/user has none.
        self._run(["git", "config", "user.email", "hub@fmriflow.local"], cwd=dest, check=False)
        self._run(["git", "config", "user.name", "fMRIflow Hub"], cwd=dest, check=False)
        self._run(["git", "checkout", "-B", push_branch], cwd=dest)
        self._run(["git", "add", "-A"], cwd=dest)
        status = self._run(["git", "status", "--porcelain"], cwd=dest)
        if not status.stdout.strip():
            return {"branch": push_branch, "pushed": False, "pr_url": None,
                    "detail": "nothing to publish (no changes)"}
        self._run(["git", "commit", "-m", message], cwd=dest)
        self._run(["git", "remote", "set-url", "origin", auth], cwd=dest)
        try:
            self._run(["git", "push", "-u", "origin", push_branch], cwd=dest)
            pushed = True
        finally:
            self._run(["git", "remote", "set-url", "origin", url], cwd=dest, check=False)
        return {"branch": push_branch, "pushed": pushed,
                "pr_url": _pr_url(url, base_branch, push_branch)}


def _pr_url(url: str, base: str, head: str) -> str | None:
    """Best-effort compare/PR link for GitHub/GitLab remotes."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}/compare/{base}...{head}?expand=1"
    m = re.match(r"https://gitlab\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        return (f"https://gitlab.com/{m.group(1)}/{m.group(2)}/-/merge_requests/new"
                f"?merge_request[source_branch]={head}")
    return None
