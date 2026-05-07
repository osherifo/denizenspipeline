"""StructuralQCStore — persists structural-QC reviews to disk.

Reviews live at::

    {root}/<dataset>/<subject>.yaml

Default root is ``~/.fmriflow/structural_qc/``. One YAML per (dataset, subject).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

import yaml

from fmriflow.qc.structural_review import StructuralQCReview, now_iso

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe(name: str) -> str:
    """Reject names with path separators or other unsafe chars."""
    if not name or not _SAFE_NAME.match(name):
        raise ValueError(f"Unsafe name: {name!r}")
    return name


class StructuralQCStore:
    """Disk-backed registry of structural-QC reviews."""

    def __init__(self, root: Path):
        self.root = Path(root)

    # ── path helpers ────────────────────────────────────────────────

    def _path(self, dataset: str, subject: str) -> Path:
        return self.root / _safe(dataset) / f"{_safe(subject)}.yaml"

    # ── reads ───────────────────────────────────────────────────────

    def get(self, dataset: str, subject: str) -> StructuralQCReview | None:
        p = self._path(dataset, subject)
        if not p.is_file():
            return None
        try:
            data = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError as e:
            logger.warning("Bad QC review YAML at %s: %s", p, e)
            return None
        if not isinstance(data, dict):
            return None
        return StructuralQCReview.from_dict(data)

    def list_for_dataset(self, dataset: str) -> list[StructuralQCReview]:
        d = self.root / _safe(dataset)
        if not d.is_dir():
            return []
        out: list[StructuralQCReview] = []
        for p in sorted(d.glob("*.yaml")):
            try:
                data = yaml.safe_load(p.read_text()) or {}
                if isinstance(data, dict):
                    out.append(StructuralQCReview.from_dict(data))
            except (yaml.YAMLError, ValueError) as e:
                logger.warning("Skipping QC review %s: %s", p, e)
        return out

    def list_all(self) -> list[StructuralQCReview]:
        """Return every review across every dataset under ``root``."""
        out: list[StructuralQCReview] = []
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir()):
            if not d.is_dir():
                continue
            try:
                _safe(d.name)
            except ValueError:
                continue  # skip stray dirs that aren't valid dataset names
            out.extend(self.list_for_dataset(d.name))
        return out

    # ── writes ──────────────────────────────────────────────────────

    def save(self, review: StructuralQCReview) -> Path:
        review.timestamp = now_iso()
        p = self._path(review.dataset, review.subject)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(review.to_dict(), sort_keys=False))
        return p
