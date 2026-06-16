"""Persisted preprocessing-stack presets stored as YAML files.

Each preset is a ``PreprocStack`` recipe — bootstrap + transforms,
purely subject-agnostic — saved to one file at
``$FMRIFLOW_HOME/addons/pipelines/<slug>.yaml``.

Lifecycle:

- ``list_presets()`` scans the directory, returns one summary per
  file.
- ``load(name)`` returns the parsed ``PreprocStack``.
- ``save(name, stack, description)`` writes a new file (or
  overwrites if the slug exists).
- ``delete(name)`` removes it.

Per resolved-decision-5: presets are directory-based YAML files,
not first-class entries in the workflow / transform registries. A
later promotion to a registered object is possible but not
required for v1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from fmriflow.core import paths
from fmriflow.preproc.stack import PreprocStack

logger = logging.getLogger(__name__)


_SLUG_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_slug(name: str) -> str:
    """Ensure ``name`` is safe to use as a filename — no path
    separators, no traversal tricks."""
    if not name or not _SLUG_RE.match(name):
        raise ValueError(
            f"Preset name {name!r} is invalid; allowed characters: "
            f"letters, digits, underscore, hyphen."
        )
    return name


@dataclass
class PresetSummary:
    name: str
    description: str
    n_transforms: int
    bootstrap_kind: str
    path: str


class StackPresetStore:
    """Reads + writes preset YAMLs under ``$FMRIFLOW_HOME/addons/pipelines/``."""

    def __init__(self, root: Path | None = None) -> None:
        if root is not None:
            self._explicit_root = Path(root)
        else:
            self._explicit_root = None

    @property
    def root(self) -> Path:
        if self._explicit_root is not None:
            self._explicit_root.mkdir(parents=True, exist_ok=True)
            return self._explicit_root
        return paths.addons_dir("pipelines")

    def list_presets(self) -> list[PresetSummary]:
        out: list[PresetSummary] = []
        if not self.root.is_dir():
            return out
        for path in sorted(self.root.glob("*.yaml")):
            name = path.stem
            try:
                data = yaml.safe_load(path.read_text()) or {}
            except Exception as e:
                logger.warning("Could not parse preset %s: %s", path, e)
                continue
            stack = data.get("stack", {})
            bootstrap = stack.get("bootstrap", {})
            transforms = stack.get("transforms", []) or []
            out.append(
                PresetSummary(
                    name=name,
                    description=data.get("description", ""),
                    n_transforms=len(transforms),
                    bootstrap_kind=bootstrap.get("kind", "unknown"),
                    path=str(path),
                )
            )
        return out

    def load(self, name: str) -> tuple[PreprocStack, str]:
        """Return (stack, description) for a named preset."""
        _validate_slug(name)
        path = self.root / f"{name}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Preset not found: {name}")
        data = yaml.safe_load(path.read_text()) or {}
        stack = PreprocStack.from_dict(data["stack"])
        return stack, data.get("description", "")

    def save(self, name: str, stack: PreprocStack, description: str = "") -> Path:
        _validate_slug(name)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{name}.yaml"
        payload = {
            "name": name,
            "description": description,
            "stack": stack.to_dict(),
        }
        path.write_text(yaml.safe_dump(payload, sort_keys=False))
        return path

    def delete(self, name: str) -> bool:
        _validate_slug(name)
        path = self.root / f"{name}.yaml"
        if not path.is_file():
            return False
        path.unlink()
        return True
