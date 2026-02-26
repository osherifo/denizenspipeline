"""PreparedDataLoader — loads pre-saved X/Y train/test matrices."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from denizenspipeline.core.array_utils import zscore
from denizenspipeline.core.types import (
    FeatureData, PreparedData, ResponseData,
)


class PreparedDataLoader:
    """Load pre-saved train/test matrices directly, skipping stages 1-4.

    Covers the v1 load_data_matrices() pattern where entire
    X_train/Y_train/X_test/Y_test are saved as .npz files.
    """

    name = "pre_prepared"

    def prepare(self, responses: ResponseData, features: FeatureData,
                config: dict) -> PreparedData:
        prep = config['preprocessing']
        source = prep.get('source', 'local')
        delays = prep.get('delays', [1, 2, 3, 4])
        do_zscore = prep.get('do_zscore', True)

        if source == 'local':
            Y_data = np.load(prep['Y_path'])
            Y_train, Y_test = Y_data['Y_train'], Y_data['Y_test']
            X_data = np.load(prep['X_path'], allow_pickle=True)
            X_train = X_data['X_train']
            X_test = X_data['X_test']
            # Handle dict-in-npz (v1 pattern with allow_pickle=True)
            if hasattr(X_train, 'item'):
                X_train = X_train.item()
            if hasattr(X_test, 'item'):
                X_test = X_test.item()
            # If dict, concatenate in order of feature_names
            if isinstance(X_train, dict):
                fnames = prep['feature_names']
                X_train = np.hstack([X_train[fn] for fn in fnames])
                X_test = np.hstack([X_test[fn] for fn in fnames])

        elif source == 'cloud':
            import cottoncandy as cc
            cci = cc.get_interface(prep['s3_bucket'])
            Y_train = np.nan_to_num(cci.download_raw_array(prep['Y_train_path']))
            Y_test = np.nan_to_num(cci.download_raw_array(prep['Y_test_path']))
            X_train = np.nan_to_num(cci.download_raw_array(prep['X_train_path']))
            X_test = np.nan_to_num(cci.download_raw_array(prep['X_test_path']))

        else:
            raise ValueError(f"Unknown source: {source}")

        if do_zscore:
            Y_train = zscore(Y_train)
            Y_test = zscore(Y_test)

        return PreparedData(
            X_train=X_train, Y_train=Y_train,
            X_test=X_test, Y_test=Y_test,
            feature_names=prep.get('feature_names', []),
            feature_dims=prep.get('feature_dims', []),
            delays=delays,
            train_runs=prep.get('train_runs', []),
            test_runs=prep.get('test_runs', []),
        )

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        prep = config.get('preprocessing', {})
        source = prep.get('source', 'local')
        if source == 'local':
            for key in ('Y_path', 'X_path'):
                if key not in prep:
                    errors.append(f"pre_prepared requires preprocessing.{key}")
                elif not Path(prep[key]).exists():
                    errors.append(f"File not found: {prep[key]}")
        elif source == 'cloud':
            for key in ('s3_bucket', 'Y_train_path', 'Y_test_path',
                        'X_train_path', 'X_test_path'):
                if key not in prep:
                    errors.append(
                        f"pre_prepared cloud requires preprocessing.{key}")
        return errors
