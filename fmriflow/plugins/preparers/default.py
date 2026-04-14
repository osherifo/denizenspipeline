"""DefaultPreparer — trim, z-score, concatenate, delay."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

from fmriflow.core.array_utils import make_delayed, zscore
from fmriflow.core.types import (
    FeatureData, PreparedData, ResponseData,
)
from fmriflow.plugins._decorators import preparer


@preparer("default")
class DefaultPreparer:
    """Default data preparation: trim -> z-score -> concatenate -> delay.

    Wraps the Setup class from v1 interpretation/analysis.py.
    """

    name = "default"
    PARAM_SCHEMA = {
        "trim_start": {"type": "int", "default": 5, "min": 0, "description": "TRs to remove from start of each run"},
        "trim_end": {"type": "int", "default": 5, "min": 0, "description": "TRs to remove from end of each run"},
        "zscore": {"type": "bool", "default": True, "description": "Apply z-score normalization"},
        "trim_features": {"type": "bool", "default": True, "description": "Trim features along with responses"},
        "trim_responses": {"type": "bool", "default": True, "description": "Trim responses"},
        "apply_delays": {"type": "bool", "default": True, "description": "Apply temporal delays to features"},
        "delays": {"type": "list[int]", "default": [1, 2, 3, 4], "description": "Delay values in TRs"},
    }

    def prepare(self, responses: ResponseData, features: FeatureData,
                config: dict) -> PreparedData:
        prep_cfg = config.get('preparation', config.get('preprocessing', {}))
        split_cfg = config['split']

        trim_start = prep_cfg.get('trim_start', 5)
        trim_end = prep_cfg.get('trim_end', 5)
        delays = prep_cfg.get('delays', [1, 2, 3, 4])
        do_zscore = prep_cfg.get('zscore', True)
        trim_features = prep_cfg.get('trim_features', True)
        trim_responses = prep_cfg.get('trim_responses', True)
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
            if trim_responses:
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

        # Validate per-run TR counts and log shapes
        for run in all_runs:
            nr = trimmed_resp[run].shape[0]
            nf = trimmed_feat[run].shape[0]
            if nr != nf:
                raise ValueError(
                    f"Row mismatch in run '{run}': responses have "
                    f"{nr} TRs but features have {nf} TRs. "
                    f"Ensure trim_start and trim_end are applied consistently "
                    f"to both responses and features.")
            logger.info("Run '%s': %d TRs", run, nr)

        # Concatenate runs, split train/test
        Y_train = np.vstack([trimmed_resp[r] for r in train_runs])
        Y_test = np.vstack([trimmed_resp[r] for r in test_runs])
        X_train = np.vstack([trimmed_feat[r] for r in train_runs])
        X_test = np.vstack([trimmed_feat[r] for r in test_runs])

        logger.info("X_train=%s Y_train=%s X_test=%s Y_test=%s",
                     X_train.shape, Y_train.shape, X_test.shape, Y_test.shape)

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
