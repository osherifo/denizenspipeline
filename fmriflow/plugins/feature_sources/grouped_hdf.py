"""GroupedHDFSource — loads features from HDF files with story/feature structure.

Handles the common layout where one HDF file per phase contains groups
per story, each with datasets per feature:

    features_trn.hdf
      ├── story_01/
      │   ├── numwords    (n_trs, 1)
      │   ├── english1000 (n_trs, 985)
      │   └── ...
      ├── story_02/
      │   └── ...

Config example (single feature)::

    features:
      - name: numwords
        source: grouped_hdf
        paths:
          trn: /data/features/features_trn_NEW.hdf
          val: /data/features/features_val_NEW.hdf
        run_map:
          story_01: run_name_01
          story_02: run_name_02

To load many features from the same files without repeating yourself,
use YAML anchors::

    _hdf: &hdf_common
      source: grouped_hdf
      paths:
        trn: /data/features/features_trn_NEW.hdf
        val: /data/features/features_val_NEW.hdf
      run_map:
        story_01: run_name_01
        story_02: run_name_02

    features:
      - name: numwords
        <<: *hdf_common
      - name: english1000
        <<: *hdf_common
      - name: letters
        <<: *hdf_common

Config keys:
    name:     Feature name. Also used as the HDF dataset key unless
              ``dataset`` is set.
    paths:    Dict mapping phase labels to HDF file paths.
              e.g. ``{trn: path1.hdf, val: path2.hdf}``
              OR a single path string if all stories are in one file.
    dataset:  HDF dataset name within each story group (default: same
              as ``name``).
    run_map:  Optional dict mapping HDF story names to pipeline run names.
              Same format as response.run_map — keys are HDF names, values
              are pipeline names.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from fmriflow.core.types import FeatureSet
from fmriflow.plugins._decorators import feature_source


@feature_source("grouped_hdf")
class GroupedHDFSource:
    """Load a single feature from phase-split HDF files."""

    name = "grouped_hdf"
    PARAM_SCHEMA = {
        "name": {"type": "string", "required": True, "description": "Feature name (also used as HDF dataset key)"},
        "paths": {"type": "dict", "required": True, "description": "Phase labels mapped to HDF file paths"},
        "dataset": {"type": "string", "description": "HDF dataset name (defaults to feature name)"},
        "run_map": {"type": "dict", "description": "Map HDF story names to pipeline run names"},
    }

    def load(self, run_names: list[str], config: dict) -> FeatureSet:
        import h5py

        feature_name = config['name']
        dataset = config.get('dataset', feature_name)
        run_map = config.get('run_map', {})

        # Build reverse map: pipeline_name -> hdf_story_name
        reverse_map = {v: k for k, v in run_map.items()} if run_map else {}
        run_names_set = set(run_names)

        # Resolve paths: either a dict of phases or a single path
        paths_cfg = config['paths']
        if isinstance(paths_cfg, str):
            hdf_paths = [Path(paths_cfg)]
        else:
            hdf_paths = [Path(p) for p in paths_cfg.values()]

        data: dict[str, np.ndarray] = {}

        for hdf_path in hdf_paths:
            with h5py.File(hdf_path, 'r') as h:
                for story_key in h.keys():
                    # Map HDF story name to pipeline run name
                    pipeline_name = run_map.get(story_key, story_key)

                    if pipeline_name not in run_names_set:
                        continue

                    if dataset not in h[story_key]:
                        continue

                    data[pipeline_name] = h[story_key][dataset][:]

        n_dims = next(iter(data.values())).shape[1] if data else 0
        return FeatureSet(name=feature_name, data=data, n_dims=n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'paths' not in config:
            errors.append("grouped_hdf source requires 'paths'")
        else:
            paths_cfg = config['paths']
            if isinstance(paths_cfg, str):
                if not Path(paths_cfg).exists():
                    errors.append(f"Path not found: {paths_cfg}")
            else:
                for phase, p in paths_cfg.items():
                    if not Path(p).exists():
                        errors.append(f"Path not found for phase '{phase}': {p}")
        return errors
