"""LocalResponseLoader — loads fMRI responses from local files."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from denizenspipeline.core.types import ResponseData
from denizenspipeline.plugins._decorators import response_loader
from denizenspipeline.plugins.response_loaders.readers import get_reader

logger = logging.getLogger(__name__)

# Placeholder stored when no cortical mask was applied to the data.
_NO_MASK = np.array([True])


@response_loader("local")
class LocalResponseLoader:
    """Loads fMRI responses from local HDF5 or numpy files.

    Handles two data layouts transparently:

    - **Volumetric** (3-D+): the loader fetches a pycortex mask and extracts
      cortical voxels.  The mask is stored on ``ResponseData`` so reporters
      can reconstruct the full volume later.
    - **Pre-masked** (2-D, e.g. PHACT HDF): the data is already in voxel
      space.  No mask is applied; reporters receive the scores directly and
      pass them to ``cortex.Volume`` which handles the geometry via the
      surface/transform.
    """

    name = "local"

    PARAM_SCHEMA = {
        "path": {"type": "path", "description": "Response data directory path"},
        "reader": {"type": "string", "default": "auto", "enum": ["auto", "npz_per_run", "hdf5_per_run", "single_pickle", "single_hdf5", "phact_hdf", "bling_hdf"], "description": "Response file reader"},
        "run_map": {"type": "dict", "description": "Map run names to file names"},
        "mask_type": {"type": "string", "default": "thick", "description": "Pycortex cortical mask type"},
    }

    def load(self, config: dict) -> ResponseData:
        resp_cfg = config.get('response', {})
        sub_cfg = config.get('subject_config', {})

        surface = sub_cfg.get('surface', 'unknown')
        transform = sub_cfg.get('transform', 'unknown')

        # ── 1. Read raw arrays via the selected reader ──────────────────
        resp_dir = self._resolve_resp_dir(config, resp_cfg)

        reader_name = resp_cfg.get('reader', 'auto')
        reader = get_reader(reader_name)
        raw_responses = reader.read(resp_dir, None, resp_cfg) if resp_dir.exists() else {}

        # Rename runs if run_map is provided
        run_map = resp_cfg.get('run_map', {})
        if run_map:
            raw_responses = {
                run_map.get(k, k): v for k, v in raw_responses.items()
            }

        # ── 2. Apply cortical mask (volumetric only) ────────────────────
        is_volumetric = any(arr.ndim > 2 for arr in raw_responses.values())

        if is_volumetric:
            responses, mask = self._apply_mask(
                raw_responses, surface, transform,
                resp_cfg.get('mask_type', 'thick'),
            )
        else:
            if raw_responses:
                logger.info("Response data is 2-D (pre-masked), skipping "
                            "cortical mask extraction")
            responses = raw_responses
            mask = _NO_MASK

        return ResponseData(
            responses=responses,
            mask=mask,
            surface=surface,
            transform=transform,
        )

    # ── private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_resp_dir(config: dict, resp_cfg: dict) -> Path:
        if 'path' in resp_cfg:
            return Path(resp_cfg['path'])
        data_dir = Path(config.get('paths', {}).get('data_dir', '.'))
        return data_dir / 'responses' / config['experiment'] / config['subject']

    @staticmethod
    def _apply_mask(
        raw_responses: dict[str, np.ndarray],
        surface: str,
        transform: str,
        mask_type: str,
    ) -> tuple[dict[str, np.ndarray], np.ndarray]:
        """Load a pycortex mask and extract cortical voxels from volumetric data."""
        try:
            import cortex
            mask = cortex.db.get_mask(surface, transform, mask_type)
        except ImportError:
            logger.warning("pycortex not installed — cannot mask volumetric "
                           "data; flatmap/webgl reporters will not work")
            return raw_responses, _NO_MASK
        except Exception as e:
            logger.warning("Could not load pycortex mask (surface=%s, "
                           "transform=%s, mask_type=%s): %s",
                           surface, transform, mask_type, e)
            return raw_responses, _NO_MASK

        flat_mask = mask.ravel()
        responses = {}
        for run_name, raw in raw_responses.items():
            flat = raw.reshape(raw.shape[0], -1)
            responses[run_name] = flat[:, flat_mask]

        logger.info("Applied pycortex mask (%d voxels from %s volume)",
                    int(flat_mask.sum()), "x".join(str(d) for d in mask.shape))
        return responses, mask

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        resp_cfg = config.get('response', {})
        has_path = 'path' in resp_cfg
        has_data_dir = config.get('paths', {}).get('data_dir')
        if not has_path and not has_data_dir:
            errors.append(
                "local loader requires either response.path or paths.data_dir")
        if has_path and not Path(resp_cfg['path']).exists():
            errors.append(f"response.path not found: {resp_cfg['path']}")
        return errors
