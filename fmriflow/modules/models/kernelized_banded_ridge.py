"""KernelizedBandedRidgeModel — descriptive alias for multiple_kernel_ridge.

``MultipleKernelRidgeCV`` in himalaya is, mathematically, the **kernelized
form** of banded ridge regression: per-group regularization solved in the
dual (kernel) space via random-search over the simplex of group weights.
We expose it under the more descriptive ``kernelized_banded_ridge`` name
in addition to ``multiple_kernel_ridge``, since the latter is opaque to
readers who don't already know the himalaya vocabulary.

The implementation is a one-line subclass — same fit/validate, same
PARAM_SCHEMA, same kernel pipeline.
"""

from __future__ import annotations

from fmriflow.modules._decorators import model
from fmriflow.modules.models.himalaya import MultipleKernelRidgeModel


@model("kernelized_banded_ridge")
class KernelizedBandedRidgeModel(MultipleKernelRidgeModel):
    name = "kernelized_banded_ridge"
