"""CloudResponseLoader — loads fMRI responses from S3."""

from __future__ import annotations

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.plugins._decorators import response_loader


@response_loader("cloud")
class CloudResponseLoader:
    """Loads fMRI responses from S3 cloud storage via cottoncandy."""

    name = "cloud"

    PARAM_SCHEMA = {
        "mask_type": {"type": "string", "default": "thick", "description": "Pycortex cortical mask type"},
    }

    def load(self, config: dict) -> ResponseData:
        import cottoncandy as cc
        import cortex

        resp_cfg = config.get('response', {})
        sub_cfg = config.get('subject_config', {})
        bucket = config.get('paths', {}).get(
            's3_bucket', 'glab-fmriflow-shared')

        subject = config['subject']
        experiment = config['experiment']
        sessions = sub_cfg.get('sessions', [])
        surface = sub_cfg['surface']
        transform = sub_cfg['transform']
        mask_type = resp_cfg.get('mask_type', 'thick')

        cci = cc.get_interface(bucket)
        mask = cortex.db.get_mask(surface, transform, mask_type)

        responses = {}
        for session in sessions:
            run_names = self._list_runs(cci, experiment, session)
            for run_name in run_names:
                raw = np.nan_to_num(cci.download_raw_array(
                    f"{experiment}/{session}/{run_name}"))
                responses[run_name] = raw[:, mask]

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
            errors.append("subject_config.surface is required")
        if 'transform' not in sub_cfg:
            errors.append("subject_config.transform is required")
        return errors

    def _list_runs(self, cci, experiment, session):
        """List available runs in an S3 session directory."""
        prefix = f"{experiment}/{session}/"
        try:
            keys = cci.ls(prefix)
            return [k.split('/')[-1] for k in keys if not k.endswith('/')]
        except Exception:
            return []
