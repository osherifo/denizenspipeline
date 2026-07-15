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
            detail = proc.stderr.strip() or proc.stdout.strip()
            # Redact any credential embedded in a URL (git echoes the
            # authed remote URL — and the failing command — verbatim), so
            # the token never leaks into the API error / logs.
            msg = _redact(f"git {' '.join(args[1:])} failed: {detail}")
            raise BackendError(msg)
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

    def _is_empty(self, dest: Path) -> bool:
        """True if the checkout has no commits yet (brand-new/empty remote)."""
        return self._run(["git", "rev-parse", "--verify", "HEAD"],
                         cwd=dest, check=False).returncode != 0

    def _ref_exists(self, dest: Path, ref: str) -> bool:
        return self._run(["git", "rev-parse", "--verify", "--quiet", ref],
                         cwd=dest, check=False).returncode == 0

    def _remote_branches(self, dest: Path) -> list[str]:
        out = self._run(["git", "branch", "-r", "--format=%(refname:short)"],
                        cwd=dest, check=False).stdout
        names = []
        for line in out.splitlines():
            b = line.strip()
            if b.startswith("origin/") and "->" not in b:
                names.append(b[len("origin/"):])
        return names

    def list_branches(self, url: str, token: str | None) -> list[str]:
        """Remote branch names via ``git ls-remote`` (no clone needed)."""
        auth = self._auth_url(url, token)
        out = self._run(["git", "ls-remote", "--heads", auth]).stdout
        branches = []
        for line in out.splitlines():
            parts = line.split("refs/heads/", 1)
            if len(parts) == 2:
                branches.append(parts[1].strip())
        return branches

    # ── Protocol ──

    def sync(self, url: str, branch: str, dest: Path, token: str | None) -> None:
        auth = self._auth_url(url, token)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if (dest / ".git").is_dir():
            self._run(["git", "remote", "set-url", "origin", auth], cwd=dest)
            # Fetch all heads shallowly so any branch is selectable. An empty
            # remote still exits 0 (nothing to fetch), so keep check=True to
            # fail fast on real auth/network errors rather than proceed on
            # stale refs.
            self._run(["git", "fetch", "--depth", "1", "--no-tags",
                       "origin", "+refs/heads/*:refs/remotes/origin/*"],
                      cwd=dest)
        else:
            if dest.exists():
                shutil.rmtree(dest)
            # No --branch pin: an *empty* repo or a different default branch
            # would otherwise hard-fail ("Remote branch main not found").
            # --no-single-branch fetches every branch tip so branch selection
            # works after clone.
            self._run(["git", "clone", "--depth", "1", "--no-single-branch",
                       auth, str(dest)])

        if not self._is_empty(dest):
            if self._ref_exists(dest, f"origin/{branch}"):
                # Atomically point local <branch> at origin/<branch>.
                self._run(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=dest)
            else:
                avail = self._remote_branches(dest)
                raise BackendError(
                    f"branch '{branch}' not found in the repository. "
                    f"Available: {', '.join(avail) if avail else '(none)'}"
                )
        # else: empty remote — nothing checked out; the catalog is empty until
        # the first artifact is published (which initialises the branch).

        if self._has_lfs():
            self._run(["git", "lfs", "pull"], cwd=dest, check=False)
        self._run(["git", "remote", "set-url", "origin", url], cwd=dest, check=False)

    def publish(self, url: str, base_branch: str, dest: Path, token: str | None,
                push_branch: str, message: str) -> dict:
        auth = self._auth_url(url, token)
        self._run(["git", "config", "user.email", "hub@fmriflow.local"], cwd=dest, check=False)
        self._run(["git", "config", "user.name", "fMRIflow Hub"], cwd=dest, check=False)

        # First publish to an empty repo initialises it directly on the base
        # branch (no PR needed / possible). Otherwise push to a feature branch
        # so the change can be reviewed via PR.
        initialised = self._is_empty(dest)
        target = base_branch if initialised else push_branch

        self._run(["git", "checkout", "-B", target], cwd=dest)
        self._run(["git", "add", "-A"], cwd=dest)
        status = self._run(["git", "status", "--porcelain"], cwd=dest)
        if not status.stdout.strip():
            return {"branch": target, "pushed": False, "pr_url": None,
                    "detail": "nothing to publish (no changes)"}
        self._run(["git", "commit", "-m", message], cwd=dest)
        self._run(["git", "remote", "set-url", "origin", auth], cwd=dest)
        try:
            self._run(["git", "push", "-u", "origin", target], cwd=dest)
            pushed = True
        finally:
            self._run(["git", "remote", "set-url", "origin", url], cwd=dest, check=False)
        return {
            "branch": target, "pushed": pushed, "initialized": initialised,
            "pr_url": None if initialised else _pr_url(url, base_branch, push_branch),
        }


def _redact(text: str) -> str:
    """Hide credentials embedded in URLs: ``https://user:tok@host`` → ``https://***@host``."""
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)


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
