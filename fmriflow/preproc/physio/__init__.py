"""Physiological-noise correction from a BIOPAC recording.

Three stages, each also a preprocessing node (``fmriflow.preproc.nodes.physio``):

1. :mod:`.acq` — split one ``.acq`` acquisition into scan blocks using the
   scanner's TTL pulses (one block per functional run).
2. :mod:`.phlem` — the PhLEM physiological model: filter the pulse-ox and
   respiration traces, find beats and breaths, expand them into RETROICOR
   phase terms, per-TR rates, and Chang-style respiration-volume and
   heart-rate regressors.
3. :mod:`.regress` — fit those regressors per voxel (weights image), then
   remove their contribution from the BOLD series.

The model is a line-for-line port of the lab's MATLAB-derived code; every
numerical choice (filter orders, normalised pass-bands, peak thresholds,
response functions) is kept as-is so results match the existing pipeline.
"""
