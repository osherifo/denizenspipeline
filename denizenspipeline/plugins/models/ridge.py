"""BootstrapRidgeModel — bootstrap ridge regression with per-voxel alpha."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.ridge import bootstrap_ridge
from denizenspipeline.core.types import ModelResult, PreparedData
from denizenspipeline.plugins._decorators import model


@model("bootstrap_ridge")
class BootstrapRidgeModel:
    """Bootstrap ridge regression with per-voxel alpha selection.

    Wraps the existing bootstrap_ridge function.
    """

    name = "bootstrap_ridge"

    def fit(self, data: PreparedData, config: dict) -> ModelResult:
        model_cfg = config.get('model', {}).get('params', {})

        alphas = self._resolve_alphas(model_cfg.get('alphas', 'logspace(1,3,20)'))
        n_boots = model_cfg.get('n_boots', 50)
        single_alpha = model_cfg.get('single_alpha', False)
        chunk_len = model_cfg.get('chunk_len', 40)
        n_chunks = model_cfg.get('n_chunks', 20)

        weights, scores, alphas_out, _, _ = bootstrap_ridge(
            data.X_train, data.Y_train,
            data.X_test, data.Y_test,
            alphas=alphas,
            nboots=n_boots,
            chunklen=chunk_len,
            nchunks=n_chunks,
            single_alpha=single_alpha,
            use_corr=True,
        )

        return ModelResult(
            weights=weights,
            scores=scores,
            alphas=alphas_out,
            feature_names=data.feature_names,
            feature_dims=data.feature_dims,
            delays=data.delays,
        )

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        model_cfg = config.get('model', {}).get('params', {})
        n_boots = model_cfg.get('n_boots', 50)
        if not isinstance(n_boots, int) or n_boots < 1:
            errors.append(f"n_boots must be positive int, got {n_boots}")
        return errors

    def _resolve_alphas(self, spec):
        """Resolve alpha specification.

        'logspace(1,3,20)' -> np.logspace(1, 3, 20)
        [100, 200, 300]    -> np.array([100, 200, 300])
        """
        if isinstance(spec, str) and spec.startswith('logspace'):
            args = spec[len('logspace('):-1].split(',')
            parsed = [float(a.strip()) for a in args]
            # num (3rd arg) must be int for np.logspace
            if len(parsed) >= 3:
                parsed[2] = int(parsed[2])
            return np.logspace(*parsed)
        return np.array(spec, dtype=float)
