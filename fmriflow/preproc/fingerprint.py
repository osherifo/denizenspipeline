"""Content fingerprint of a subject's input directory.

``_subject_mtime_hash`` hashes ``(relative path, mtime, size)`` over every
file under ``<root>/sub-<subject>`` so a container-app node (fmriprep) is
invalidated when its BIDS input changes — nipype only hashes the path
string of a directory input.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any



_FINGERPRINT_HEX_LEN = 16


def _sha256_short(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:_FINGERPRINT_HEX_LEN]


def _sorted_json(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, default=str)


def _subject_mtime_hash(root: Path | None, subject: str) -> str:
    """Hash of all files under ``root/sub-<subject>/`` (or just ``root``
    if no per-subject subdir exists).

    Each file contributes ``(relative_path, mtime_ns, size_bytes)``;
    files are sorted by path so the result is order-independent. A
    missing directory still produces a stable hash (encoding "no-input"
    instead of ``""``) so a stack with no BIDS input still gets a
    meaningful fingerprint.
    """
    if root is None:
        return _sha256_short(f"no-root")

    root = Path(root)
    if not root.is_dir():
        return _sha256_short(f"no-root:{root}")

    scan = root / f"sub-{subject}"
    if not scan.is_dir():
        scan = root

    parts: list[str] = []
    for f in sorted(scan.rglob("*")):
        if not f.is_file():
            continue
        try:
            stat = f.stat()
            rel = f.relative_to(scan)
            parts.append(f"{rel}|{stat.st_mtime_ns}|{stat.st_size}")
        except (OSError, ValueError):
            continue
    return _sha256_short("\n".join(parts) if parts else "empty")
