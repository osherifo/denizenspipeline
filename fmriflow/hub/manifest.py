"""The ``hub.json`` manifest — the catalog contract for a source repo.

A source repo is laid out as ``kinds/<kind>/<name>.<ext>`` (+ sidecars /
blobs) plus a root ``hub.json`` listing every artifact with an integrity
hash. This module both reads the manifest and (re)builds entries by scanning
+ hashing files, so contributing an artifact is: drop the file(s) → rebuild
the entry → commit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

SCHEMA = 1
MANIFEST_NAME = "hub.json"
KINDS_DIR = "kinds"

# Artifact kinds the hub understands. `feature_array` is the large-binary
# (git-LFS) class; the rest are small text/code files.
KINDS = (
    "error", "module", "analysis_config", "workflow_config",
    "stack_preset", "heuristic", "transform", "workflow", "feature_array",
)


@dataclass
class ArtifactEntry:
    kind: str
    name: str
    files: list[str]                    # repo-relative paths
    sha256: str
    size: int = 0
    version: str = "1"
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    lfs: bool = False
    metadata: dict = field(default_factory=dict)  # e.g. {"category": "models"}

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def combined_sha256(repo_dir: Path, rel_files: list[str]) -> tuple[str, int]:
    """Hash a (sorted) set of files together + total size."""
    h = hashlib.sha256()
    total = 0
    for rel in sorted(rel_files):
        p = repo_dir / rel
        h.update(rel.encode())
        h.update(sha256_of(p).encode())
        total += p.stat().st_size
    return h.hexdigest(), total


def manifest_path(repo_dir: Path) -> Path:
    return repo_dir / MANIFEST_NAME


def read_manifest(repo_dir: Path) -> list[ArtifactEntry]:
    """Parse ``hub.json`` → entries (empty list if missing/malformed)."""
    mp = manifest_path(repo_dir)
    if not mp.is_file():
        return []
    try:
        data = json.loads(mp.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    entries: list[ArtifactEntry] = []
    for a in data.get("artifacts", []):
        if not isinstance(a, dict) or "kind" not in a or "name" not in a:
            continue
        entries.append(ArtifactEntry(
            kind=a["kind"], name=a["name"],
            files=list(a.get("files", [])),
            sha256=a.get("sha256", ""),
            size=int(a.get("size", 0)),
            version=str(a.get("version", "1")),
            description=a.get("description", ""),
            author=a.get("author", ""),
            tags=list(a.get("tags", [])),
            lfs=bool(a.get("lfs", False)),
            metadata=dict(a.get("metadata", {})),
        ))
    return entries


def write_manifest(repo_dir: Path, entries: list[ArtifactEntry]) -> None:
    payload = {"schema": SCHEMA,
               "artifacts": [e.to_dict() for e in entries]}
    manifest_path(repo_dir).write_text(json.dumps(payload, indent=2) + "\n")


def build_entry(repo_dir: Path, kind: str, name: str, rel_files: list[str],
                *, lfs: bool = False, **meta) -> ArtifactEntry:
    """Hash the files and assemble an entry (for publish/regenerate)."""
    digest, size = combined_sha256(repo_dir, rel_files)
    return ArtifactEntry(
        kind=kind, name=name, files=rel_files, sha256=digest, size=size,
        version=str(meta.pop("version", "1")),
        description=meta.pop("description", ""),
        author=meta.pop("author", ""),
        tags=list(meta.pop("tags", []) or []),
        lfs=lfs,
        metadata=dict(meta.pop("metadata", {}) or meta),
    )


def validate_manifest(repo_dir: Path) -> list[str]:
    """Check a store repo against the schema. Returns a list of problems
    ([] = valid). Used by the ``/validate`` endpoint and surfaced on sync so a
    malformed store is flagged rather than silently half-working.
    """
    problems: list[str] = []
    mp = manifest_path(repo_dir)
    if not mp.is_file():
        return [f"no {MANIFEST_NAME} at the repo root — this is not a hub store "
                "(an empty repo is fine; publish to initialise it)."]
    try:
        data = json.loads(mp.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return [f"{MANIFEST_NAME} is not valid JSON: {e}"]
    if not isinstance(data, dict):
        return [f"{MANIFEST_NAME} must be a JSON object"]
    schema = data.get("schema")
    if schema != SCHEMA:
        problems.append(f"unsupported manifest schema {schema!r} (this build expects {SCHEMA})")
    arts = data.get("artifacts")
    if not isinstance(arts, list):
        return problems + [f"{MANIFEST_NAME} must have an 'artifacts' array"]
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(arts):
        where = f"artifacts[{i}]"
        if not isinstance(a, dict):
            problems.append(f"{where}: not an object"); continue
        kind, name = a.get("kind"), a.get("name")
        if kind not in KINDS:
            problems.append(f"{where}: unknown kind {kind!r} (allowed: {', '.join(KINDS)})")
        if not name:
            problems.append(f"{where}: missing 'name'")
        if kind and name:
            key = (kind, name)
            if key in seen:
                problems.append(f"{where}: duplicate {kind}/{name}")
            seen.add(key)
        files = a.get("files")
        if not isinstance(files, list) or not files:
            problems.append(f"{where} ({kind}/{name}): 'files' must be a non-empty array")
        else:
            for rel in files:
                if not (repo_dir / rel).is_file():
                    problems.append(f"{where} ({kind}/{name}): missing file '{rel}'")
        if not a.get("sha256"):
            problems.append(f"{where} ({kind}/{name}): missing 'sha256' (install verifies it)")
        if kind == "module" and not (a.get("metadata") or {}).get("category"):
            problems.append(f"{where} ({name}): module entries need metadata.category")
    return problems


def verify(repo_dir: Path, entry: ArtifactEntry) -> bool:
    """Recompute the hash and compare to the manifest (integrity check).

    An entry with an empty ``sha256`` is treated as unverifiable → False,
    so installs of unhashed artifacts are rejected (fail closed)."""
    if not entry.sha256:
        return False
    for rel in entry.files:
        if not (repo_dir / rel).is_file():
            return False
    digest, _ = combined_sha256(repo_dir, entry.files)
    return digest == entry.sha256
