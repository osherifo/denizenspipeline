"""PreprocOutputs — manifests on disk: scan, read, validate, collect.

The read side of preprocessing that is not a run: every
``preproc_manifest.json`` under the derivatives root plus the manifests
recorded by finished pipeline runs, and "collect" — build a manifest from
derivatives that were produced elsewhere, through the same collectors the
container-app nodes use.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from fmriflow.preproc.manifest import PreprocConfig, PreprocManifest
from fmriflow.server.services.run_registry import RunRegistry

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "preproc_manifest.json"

# ``collect`` backend name -> node type whose to_manifest() knows the layout.
COLLECT_NODES = {
    "fmriprep": "fmriprep",
    "bids_app": "bids_app",
    "custom": "custom_shell",
    "custom_shell": "custom_shell",
}


def collect_manifest(params: dict[str, Any]) -> PreprocManifest:
    """Build a manifest from existing outputs via the matching node's collector.

    ``params``: ``backend`` (fmriprep | bids_app | custom), ``subject``,
    ``output_dir``, optional ``bids_dir``, ``task``, ``sessions``, ``run_map``,
    ``backend_params``. Writes ``<output_dir>/sub-<subject>/preproc_manifest.json``.
    """
    backend = str(params.get("backend") or "fmriprep")
    node_type = COLLECT_NODES.get(backend)
    if node_type is None:
        raise ValueError(f"cannot collect for backend {backend!r}; one of {sorted(COLLECT_NODES)}")
    from fmriflow.preproc.node_registry import NodeRegistry

    reg = NodeRegistry(user_dirs=[]).discover()
    node = reg.get(node_type)
    out_dir = Path(str(params["output_dir"]))
    inputs: dict[str, Any] = {
        "subject": str(params["subject"]), "output_dir": str(out_dir),
        "bids_dir": params.get("bids_dir") or "", "input_dir": params.get("bids_dir") or "",
    }
    bp = dict(params.get("backend_params") or {})
    if params.get("run_map"):
        bp["run_map"] = params["run_map"]
    if node_type == "fmriprep":
        # FmriprepBackend.collect() reads task / sessions / run_map from the config.
        from fmriflow.preproc.backends.fmriprep import FmriprepBackend
        from fmriflow.preproc.nodes.fmriprep import fmriprep_params

        p = fmriprep_params({k: v for k, v in bp.items() if v not in ("", None)})
        config = PreprocConfig(
            subject=str(params["subject"]), backend="fmriprep", output_dir=str(out_dir),
            bids_dir=params.get("bids_dir"), task=params.get("task"), sessions=params.get("sessions"),
            run_map=params.get("run_map"), backend_params=p.to_dict(),
        )
        manifest = FmriprepBackend().collect(config)
    else:
        manifest = node.to_manifest(inputs, bp, out_dir)
    target = out_dir / f"sub-{params['subject']}" / MANIFEST_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.save(target)
    logger.info("Manifest written to %s", target)
    return manifest


class PreprocOutputs:
    def __init__(self, derivatives_dir: Path | str, registry: RunRegistry | None = None, cache_ttl: float = 30.0) -> None:
        self.derivatives_dir = Path(derivatives_dir)
        self.registry = registry or RunRegistry()
        self._cache: list[dict] | None = None
        self._cache_time = 0.0
        self._cache_ttl = cache_ttl

    def invalidate_cache(self) -> None:
        self._cache = None

    def scan_manifests(self) -> list[dict]:
        """Every ``preproc_manifest.json`` under the derivatives root and every one a
        finished pipeline run wrote, deduplicated by absolute path."""
        now = time.time()
        if self._cache is not None and now - self._cache_time < self._cache_ttl:
            return self._cache
        seen: set[str] = set()
        out: list[dict] = []

        def _add(mf: Path) -> None:
            ap = str(mf.resolve())
            if ap in seen:
                return
            seen.add(ap)
            try:
                m = PreprocManifest.from_json(mf)
            except Exception:
                logger.warning("Could not read manifest: %s", mf, exc_info=True)
                return
            out.append({
                "subject": m.subject, "path": ap, "backend": m.backend, "backend_version": m.backend_version,
                "space": m.space, "n_runs": len(m.runs), "created": m.created, "dataset": m.dataset,
                "n_steps": len(m.additional_steps),
            })

        if self.derivatives_dir.is_dir():
            for mf in sorted(self.derivatives_dir.rglob(MANIFEST_FILENAME)):
                _add(mf)
        try:
            for state in self.registry.list_all():
                if state.kind != "preproc" or state.status != "done":
                    continue
                if state.manifest_path and Path(state.manifest_path).is_file():
                    _add(Path(state.manifest_path))
                    continue
                out_dir = (state.params or {}).get("output_dir")
                if out_dir:
                    for cand in (Path(out_dir) / MANIFEST_FILENAME, Path(out_dir) / f"sub-{state.subject}" / MANIFEST_FILENAME):
                        if cand.is_file():
                            _add(cand)
                            break
        except Exception:
            logger.warning("Could not scan the run registry for manifests", exc_info=True)
        self._cache = out
        self._cache_time = now
        return out

    def get_manifest(self, subject: str) -> dict | None:
        for m in self.scan_manifests():
            if m["subject"] == subject:
                try:
                    return PreprocManifest.from_json(m["path"]).to_dict()
                except Exception:
                    return None
        return None

    def validate_manifest(self, subject: str, config_filename: str | None = None) -> dict:
        path = next((m["path"] for m in self.scan_manifests() if m["subject"] == subject), None)
        if path is None:
            return {"errors": [f"No manifest found for subject '{subject}'"]}
        from fmriflow.preproc.validation import validate_manifest

        manifest = PreprocManifest.from_json(path)
        config = None
        if config_filename:
            try:
                from fmriflow.config.loader import load_config
                config = load_config(config_filename)
            except Exception as e:
                return {"errors": [f"Cannot load config: {e}"]}
        return {"errors": validate_manifest(manifest, config)}

    def collect(self, params: dict) -> dict:
        manifest = collect_manifest(params)
        self.invalidate_cache()
        return {
            "subject": manifest.subject, "backend": manifest.backend, "n_runs": len(manifest.runs),
            "output_dir": manifest.output_dir,
            "manifest_path": str(Path(manifest.output_dir) / f"sub-{manifest.subject}" / MANIFEST_FILENAME),
            "runs": [{"run_name": r.run_name, "n_trs": r.n_trs, "shape": r.shape} for r in manifest.runs],
        }
