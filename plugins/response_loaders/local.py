"""LocalResponseLoader — loads fMRI responses from local files."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from denizenspipeline.core.types import ResponseData


class LocalResponseLoader:
    """Loads fMRI responses from local HDF5 or numpy files."""

    name = "local"

    def load(self, config: dict) -> ResponseData:
        resp_cfg = config.get('response', {})
        sub_cfg = config.get('subject_config', {})
        data_dir = Path(config.get('paths', {}).get('data_dir', '.'))

        subject = config['subject']
        experiment = config['experiment']
        surface = sub_cfg['surface']
        transform = sub_cfg['transform']
        mask_type = resp_cfg.get('mask_type', 'thick')

        # Load cortical mask
        try:
            import cortex
            mask = cortex.db.get_mask(surface, transform, mask_type)
        except ImportError:
            mask = np.array([True])  # Placeholder if pycortex unavailable

        # Load response data from local files
        resp_dir = data_dir / 'responses' / experiment / subject
        responses = {}

        if resp_dir.exists():
            # Try HDF5 files first
            for f in sorted(resp_dir.glob('*.hdf5')):
                import h5py
                run_name = f.stem
                with h5py.File(f, 'r') as h:
                    raw = h['data'][:]
                responses[run_name] = raw[:, mask] if mask.ndim > 0 else raw

            # Fall back to .npz files
            if not responses:
                for f in sorted(resp_dir.glob('*.npz')):
                    run_name = f.stem
                    raw = np.load(f)['data']
                    responses[run_name] = raw[:, mask] if mask.ndim > 0 else raw

        return ResponseData(
            responses=responses,
            mask=mask,
            surface=surface,
            transform=transform,
        )

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        sub_cfg = config.get('subject_config', {})
        if 'surface' not in sub_cfg:
            errors.append("subject_config.surface is required for local loader")
        if 'transform' not in sub_cfg:
            errors.append("subject_config.transform is required for local loader")
        data_dir = config.get('paths', {}).get('data_dir')
        if not data_dir:
            errors.append("paths.data_dir required for local loader")
        return errors
