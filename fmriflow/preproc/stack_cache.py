"""On-disk cache for stage outputs, keyed by fingerprint.

Each cache entry is a JSON-serialised ``PreprocManifest`` at
``<root_dir>/<fingerprint>.json``. The cache is per-run-output-dir
(scoped under ``{output_dir}/.preproc_stack_cache/``) so distinct
runs don't share state — caching is opt-in via the runner's
``use_cache`` flag.

Validity check: a cache hit additionally requires the cached
manifest's ``output_dir`` to still exist on disk. If the user
deleted the stage's outputs, the cache silently misses.

Phase 4c (this file): no pruning, no size limits, no schema
versioning. Add when needed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from fmriflow.preproc.manifest import PreprocManifest

logger = logging.getLogger(__name__)


@dataclass
class StackCache:
    """Filesystem-backed cache of per-stage ``PreprocManifest`` snapshots.

    Construct one per run, rooted under the run's output dir.
    Multiple ``StackCache`` instances pointing at the same root see
    the same entries.
    """

    root_dir: Path

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir)

    def _entry_path(self, fingerprint: str) -> Path:
        return self.root_dir / f"{fingerprint}.json"

    def lookup(self, fingerprint: str) -> PreprocManifest | None:
        """Return the cached manifest if it exists AND its
        ``output_dir`` is still present on disk. Otherwise ``None``.

        A missing output dir invalidates the entry (logged at INFO)
        but does NOT delete the file — keeping it lets a later
        recreate-the-outputs run revive the cache without re-running
        the stage. Tests that need a hard reset can call ``clear()``.
        """
        path = self._entry_path(fingerprint)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
            manifest = PreprocManifest.from_dict(data)
        except Exception as e:
            logger.warning(
                "Could not load cache entry %s: %s — treating as miss",
                fingerprint, e,
            )
            return None

        out = manifest.output_dir
        if not out or not Path(out).exists():
            logger.info(
                "Cache entry %s invalidated: output_dir %r is gone",
                fingerprint, out,
            )
            return None

        return manifest

    def store(self, fingerprint: str, manifest: PreprocManifest) -> Path:
        """Write the manifest to the cache. Creates ``root_dir`` if
        absent. Returns the path of the written file."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        path = self._entry_path(fingerprint)
        path.write_text(manifest.to_json())
        return path

    def invalidate(self, fingerprint: str) -> bool:
        """Remove an entry. Returns True if the entry existed."""
        path = self._entry_path(fingerprint)
        if path.is_file():
            path.unlink()
            return True
        return False

    def clear(self) -> int:
        """Remove all entries under ``root_dir``. Returns the count
        of entries removed.
        """
        if not self.root_dir.is_dir():
            return 0
        count = 0
        for entry in self.root_dir.glob("*.json"):
            entry.unlink()
            count += 1
        return count
