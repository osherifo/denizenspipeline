"""Deterministic fingerprints for stage-cache invalidation.

The stack cache keys on these hashes. Two flavours:

- **Bootstrap fingerprint** — hash of ``kind`` + workflow name +
  workflow version + sorted-JSON of ``bootstrap.params`` + a
  BIDS-subject-tree mtime/size hash. For ``passthrough`` kind we
  hash the derivatives tree instead. Omar's choice (per the
  decisions in the proposal): mtime-based input hash is enough,
  not a content hash — fast and catches the cases we care about.

- **Transform fingerprint** — hash of ``transform.name`` +
  transform version + sorted-JSON of ``transform.params`` + the
  **prior stage's fingerprint** + the inputs' paths/mtimes/sizes.
  The prior fingerprint cascades: any upstream change invalidates
  every downstream stage, automatically.

Hashes are SHA-256 prefixes (16 hex chars) — plenty for cache
keys, short enough to embed in directory names.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fmriflow.preproc.stack import BootstrapStage, TransformStage


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


def bootstrap_fingerprint(
    stage: BootstrapStage,
    workflow: Any,
    *,
    bids_dir: Path | None,
    derivatives_dir: Path | None,
    subject: str,
) -> str:
    """Compute the bootstrap stage's fingerprint.

    The input-tree hash is taken from ``derivatives_dir`` for
    ``passthrough`` kind (where derivatives ARE the input) and from
    ``bids_dir`` for every other kind.
    """
    workflow_name = getattr(workflow, "name", stage.kind)
    workflow_version = getattr(workflow, "version", "")

    if stage.kind == "passthrough":
        input_hash = _subject_mtime_hash(derivatives_dir, subject)
    else:
        input_hash = _subject_mtime_hash(bids_dir, subject)

    payload = "\n".join(
        [
            f"kind={stage.kind}",
            f"workflow={workflow_name}",
            f"version={workflow_version}",
            f"params={_sorted_json(stage.params)}",
            f"input={input_hash}",
        ]
    )
    return _sha256_short(payload)


def transform_fingerprint(
    stage: TransformStage,
    transform: Any,
    *,
    prior_fingerprint: str,
    inputs: dict[str, Any],
) -> str:
    """Compute a transform stage's fingerprint.

    Includes the prior stage's fingerprint so any upstream change
    invalidates the entire downstream chain.
    """
    transform_version = getattr(transform, "version", "")

    input_parts: list[str] = []
    for key in sorted(inputs):
        value = inputs[key]
        if value is None:
            input_parts.append(f"{key}=None")
            continue
        path = Path(str(value))
        try:
            stat = path.stat()
            input_parts.append(f"{key}={path}|{stat.st_mtime_ns}|{stat.st_size}")
        except (OSError, ValueError):
            input_parts.append(f"{key}={path}|missing")

    payload = "\n".join(
        [
            f"name={stage.name}",
            f"version={transform_version}",
            f"params={_sorted_json(stage.params)}",
            f"prior={prior_fingerprint}",
            f"inputs={';'.join(input_parts)}",
        ]
    )
    return _sha256_short(payload)
