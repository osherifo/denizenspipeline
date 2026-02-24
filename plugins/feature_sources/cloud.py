"""CloudSource — loads features from S3 via cottoncandy."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.types import FeatureSet


class CloudSource:
    """Load features from S3 via cottoncandy.

    Covers v1 patterns:
    - Xs_load_method='from_cc' with cc.download_raw_array()

    Config keys:
        bucket: S3 bucket name
        prefix: path prefix within bucket
        name: feature name
    """

    name = "cloud"

    def load(self, run_names: list[str], config: dict) -> FeatureSet:
        import cottoncandy as cc
        bucket = config['bucket']
        prefix = config.get('prefix', '')
        feature_name = config['name']
        cci = cc.get_interface(bucket)

        data = {}
        for run_name in run_names:
            key = f"{prefix}{run_name}"
            arr = np.nan_to_num(cci.download_raw_array(key))
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1)
            data[run_name] = arr

        n_dims = next(iter(data.values())).shape[1]
        return FeatureSet(name=feature_name, data=data, n_dims=n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'bucket' not in config:
            errors.append("cloud source requires 'bucket'")
        return errors
