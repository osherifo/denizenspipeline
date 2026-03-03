"""DefaultPreprocessor — trim, z-score, concatenate, delay."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.array_utils import make_delayed, zscore
from denizenspipeline.core.types import (
    FeatureData, PreparedData, ResponseData,
)


class DefaultPreprocessor:
    """Standard preprocessing: trim -> z-score -> concatenate -> delay.

    Wraps the Setup class from v1 interpretation/analysis.py.
    """

    name = "default"

    def prepare(self, responses: ResponseData, features: FeatureData,
                config: dict) -> PreparedData:
        prep_cfg = config.get('preprocessing', {})
        split_cfg = config['split']

        trim_start = prep_cfg.get('trim_start', 5)
        trim_end = prep_cfg.get('trim_end', 5)
        delays = prep_cfg.get('delays', [1, 2, 3, 4])
        do_zscore = prep_cfg.get('zscore', True)
        trim_features = prep_cfg.get('trim_features', True)
        apply_delays = prep_cfg.get('apply_delays', True)

        test_runs = split_cfg['test_runs']
        all_runs = sorted(
            set(responses.responses.keys())
            & set(self._get_feature_runs(features))
        )
        train_runs = sorted(set(all_runs) - set(test_runs))

        # Trim and z-score responses
        trimmed_resp = {}
        for run in all_runs:
            r = responses.responses[run]
            r = self._trim(r, trim_start, trim_end)
            if do_zscore:
                r = zscore(r)
            trimmed_resp[run] = r

        # Trim and z-score features, concatenate feature dims
        feature_names = features.feature_names
        feature_dims = [features.features[fn].n_dims for fn in feature_names]

        trimmed_feat = {}
        for run in all_runs:
            run_feats = []
            for fn in feature_names:
                f = features.features[fn].data[run]
                if trim_features:
                    f = self._trim(f, trim_start, trim_end)
                if do_zscore:
                    f = zscore(f)
                run_feats.append(f)
            trimmed_feat[run] = np.hstack(run_feats)

        # Concatenate runs, split train/test
        Y_train = np.vstack([trimmed_resp[r] for r in train_runs])
        Y_test = np.vstack([trimmed_resp[r] for r in test_runs])
        X_train = np.vstack([trimmed_feat[r] for r in train_runs])
        X_test = np.vstack([trimmed_feat[r] for r in test_runs])

        # Apply temporal delays
        if apply_delays:
            X_train = make_delayed(X_train, delays)
            X_test = make_delayed(X_test, delays)

        return PreparedData(
            X_train=X_train, Y_train=Y_train,
            X_test=X_test, Y_test=Y_test,
            feature_names=feature_names,
            feature_dims=feature_dims,
            delays=delays,
            train_runs=train_runs,
            test_runs=test_runs,
            metadata={'delays_applied': apply_delays},
        )

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'split' not in config or 'test_runs' not in config.get('split', {}):
            errors.append("split.test_runs is required")
        return errors

    def _trim(self, arr, start, end):
        if end == 0:
            return arr[start:]
        return arr[start:-end]

    def _get_feature_runs(self, features):
        first_feat = list(features.features.values())[0]
        return list(first_feat.data.keys())
