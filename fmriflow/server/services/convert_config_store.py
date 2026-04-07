"""ConvertConfigStore — saves and indexes conversion config YAML files.

Stores both single-run and batch conversion configs in ~/.fmriflow/convert_configs/
for reproducibility and re-running.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path.home() / ".fmriflow" / "convert_configs"


class ConvertConfigStore:
    """Indexes saved conversion configs from a directory."""

    def __init__(self, configs_dir: Path | None = None):
        self.configs_dir = configs_dir or DEFAULT_DIR
        self.configs_dir.mkdir(parents=True, exist_ok=True)
        self._configs_dir_resolved = self.configs_dir.resolve()
        self._cache: list[dict] | None = None
        self._cache_time: float = 0
        self._cache_ttl = 5.0

    def _invalidate(self) -> None:
        self._cache = None

    def _maybe_rescan(self) -> list[dict]:
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        configs = []
        for path in sorted(self.configs_dir.glob("*.yaml")):
            try:
                raw = path.read_text()
                data = yaml.safe_load(raw) or {}
                if not isinstance(data, dict):
                    continue
                configs.append(self._extract_summary(path, data))
            except Exception:
                logger.debug("Skipping %s", path, exc_info=True)

        self._cache = configs
        self._cache_time = now
        return configs

    def _extract_summary(self, path: Path, data: dict) -> dict:
        """Extract lightweight summary from a saved config."""
        meta = data.get("_meta", {})
        config_type = "batch" if "convert_batch" in data else "single"

        summary: dict[str, Any] = {
            "filename": path.name,
            "name": meta.get("name", path.stem),
            "type": config_type,
            "created": meta.get("created", ""),
            "description": meta.get("description", ""),
        }

        if config_type == "batch":
            batch = data["convert_batch"]
            summary["heuristic"] = batch.get("heuristic", "")
            summary["bids_dir"] = batch.get("bids_dir", "")
            summary["n_jobs"] = len(batch.get("jobs", []))
        else:
            summary["heuristic"] = data.get("heuristic", "")
            summary["bids_dir"] = data.get("bids_dir", "")
            summary["subject"] = data.get("subject", "")

        return summary

    def list_configs(self) -> list[dict]:
        """Return summaries of all saved configs."""
        return self._maybe_rescan()

    def _validate_filename(self, filename: str) -> Path:
        """Validate *filename* and return a safe :class:`~pathlib.Path`.

        Raises :class:`ValueError` when *filename* contains path separators,
        lacks a ``.yaml`` extension, or would escape *configs_dir* after
        resolution (path-traversal guard).
        """
        if "/" in filename or "\\" in filename or not filename:
            raise ValueError(f"Invalid config filename: {filename!r}")
        if not filename.endswith(".yaml"):
            raise ValueError(f"Config filename must end with .yaml: {filename!r}")
        resolved = (self.configs_dir / filename).resolve()
        if not resolved.is_relative_to(self._configs_dir_resolved):
            raise ValueError(f"Config filename escapes config directory: {filename!r}")
        return resolved

    def get_config(self, filename: str) -> dict | None:
        """Return full config + raw YAML for a saved config."""
        try:
            path = self._validate_filename(filename)
        except ValueError:
            return None
        if not path.is_file():
            return None
        raw = path.read_text()
        try:
            data = yaml.safe_load(raw) or {}
        except Exception:
            data = {}
        return {
            "filename": filename,
            "config": data,
            "yaml_string": raw,
        }

    def save_config(self, name: str, config: dict, description: str = "") -> dict:
        """Save a conversion config to disk.

        Adds _meta block with name, timestamp, description.
        Returns the saved summary.
        Raises :class:`FileExistsError` if a config with that name already exists.
        """
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        if not safe_name:
            safe_name = "convert_config"
        filename = f"{safe_name}.yaml"

        path = self.configs_dir / filename
        if path.exists():
            raise FileExistsError(
                f"A config named '{name}' already exists. "
                "Delete it first or choose a different name."
            )

        # Add metadata
        config["_meta"] = {
            "name": name,
            "created": datetime.now(timezone.utc).isoformat(),
            "description": description,
        }

        raw = yaml.safe_dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
        path.write_text(raw)
        self._invalidate()

        logger.info("Saved convert config: %s", path)
        return self._extract_summary(path, config)

    def delete_config(self, filename: str) -> bool:
        """Delete a saved config."""
        try:
            path = self._validate_filename(filename)
        except ValueError:
            return False
        if not path.is_file():
            return False
        path.unlink()
        self._invalidate()
        return True

    def save_from_run_params(self, params: dict, name: str = "", description: str = "") -> dict:
        """Save a single conversion run's params as a reusable config."""
        config = {
            "source_dir": params.get("source_dir", ""),
            "bids_dir": params.get("bids_dir", ""),
            "subject": params.get("subject", ""),
            "heuristic": params.get("heuristic", ""),
        }
        if params.get("sessions"):
            config["sessions"] = params["sessions"]
        if params.get("dataset_name"):
            config["dataset_name"] = params["dataset_name"]
        if params.get("grouping"):
            config["grouping"] = params["grouping"]
        if params.get("minmeta"):
            config["minmeta"] = True
        if params.get("overwrite") is False:
            config["overwrite"] = False
        if params.get("validate_bids") is False:
            config["validate_bids"] = False

        if not name:
            name = f"convert_{config['subject']}_{config['heuristic']}"

        return self.save_config(name, config, description)

    def save_from_batch_params(self, params: dict, name: str = "", description: str = "") -> dict:
        """Save batch conversion params as a reusable config."""
        from fmriflow.convert.batch import BatchConfig, BatchJobConfig, batch_config_to_dict

        batch_config = BatchConfig(
            heuristic=params["heuristic"],
            bids_dir=params["bids_dir"],
            jobs=[
                BatchJobConfig(
                    subject=j["subject"],
                    source_dir=j["source_dir"],
                    session=j.get("session", ""),
                )
                for j in params["jobs"]
            ],
            source_root=params.get("source_root", ""),
            max_workers=params.get("max_workers", 2),
            dataset_name=params.get("dataset_name", ""),
            grouping=params.get("grouping", ""),
            minmeta=params.get("minmeta", False),
            overwrite=params.get("overwrite", True),
            validate_bids=params.get("validate_bids", True),
        )
        config = batch_config_to_dict(batch_config)

        if not name:
            name = f"batch_{batch_config.heuristic}_{len(batch_config.jobs)}jobs"

        return self.save_config(name, config, description)
