"""Configuration validation schema and validator."""

from __future__ import annotations

CONFIG_SCHEMA = {
    "experiment": {"type": "string", "required": True},
    "subject": {"type": "string", "required": True},
    "stimulus": {
        "loader": {"type": "string", "default": "textgrid"},
        "language": {
            "type": "string", "default": "en",
            "enum": ["en", "zh", "es"],
        },
        "modality": {
            "type": "string", "default": "reading",
            "enum": ["reading", "listening"],
        },
    },
    "features": {
        "type": "list",
        "items": {
            "name": {"type": "string", "required": True},
            "source": {
                "type": "string", "default": "compute",
                "enum": ["compute", "filesystem", "cloud", "database"],
            },
            "extractor": {"type": "string"},
            "params": {"type": "dict", "default": {}},
            "path": {"type": "string"},
            "save_to": {"type": "dict"},
        },
    },
    "preprocessing": {
        "trim_start": {"type": "int", "default": 5, "min": 0},
        "trim_end": {"type": "int", "default": 5, "min": 0},
        "delays": {"type": "list[int]", "default": [1, 2, 3, 4]},
        "zscore": {"type": "bool", "default": True},
        "apply_delays": {"type": "bool", "default": True},
    },
    "model": {
        "type": {"type": "string", "default": "bootstrap_ridge"},
        "params": {"type": "dict", "default": {}},
    },
    "split": {
        "test_runs": {"type": "list[str]", "required": True},
        "train_runs": {"type": "list[str]", "default": "auto"},
    },
}


def validate_config(config: dict) -> list[str]:
    """Validate a resolved config dict against the schema.

    Parameters
    ----------
    config : dict
        The fully resolved configuration.

    Returns
    -------
    list of str
        Error messages. Empty list means valid.
    """
    errors = []

    # Required top-level fields
    if "experiment" not in config:
        errors.append("'experiment' is required")
    if "subject" not in config:
        errors.append("'subject' is required")

    # Features validation
    features = config.get("features", [])
    if not isinstance(features, list):
        errors.append("'features' must be a list")
    else:
        for i, feat in enumerate(features):
            if not isinstance(feat, dict):
                errors.append(f"features[{i}] must be a dict")
                continue
            if "name" not in feat:
                errors.append(f"features[{i}] missing 'name'")
            source = feat.get("source", "compute")
            if source not in ("compute", "filesystem", "cloud", "database", "grouped_hdf"):
                errors.append(
                    f"features[{i}] invalid source '{source}', "
                    f"must be one of: compute, filesystem, cloud, database, grouped_hdf"
                )
            if source == "filesystem" and "path" not in feat:
                errors.append(f"features[{i}] filesystem source requires 'path'")
            if source == "cloud" and "bucket" not in feat:
                errors.append(f"features[{i}] cloud source requires 'bucket'")
            if source == "grouped_hdf" and "paths" not in feat:
                errors.append(f"features[{i}] grouped_hdf source requires 'paths'")

    # Split validation
    split = config.get("split", {})
    if "test_runs" not in split:
        errors.append("'split.test_runs' is required")

    # Preprocessing validation
    prep = config.get("preprocessing", {})
    trim_start = prep.get("trim_start", 5)
    trim_end = prep.get("trim_end", 5)
    if not isinstance(trim_start, int) or trim_start < 0:
        errors.append(f"preprocessing.trim_start must be non-negative int, got {trim_start}")
    if not isinstance(trim_end, int) or trim_end < 0:
        errors.append(f"preprocessing.trim_end must be non-negative int, got {trim_end}")

    # Model validation
    model = config.get("model", {})
    if "type" in model:
        valid_models = ("bootstrap_ridge",)
        if model["type"] not in valid_models:
            pass  # Allow unknown models (could be external plugins)

    # Stimulus validation
    stim = config.get("stimulus", {})
    lang = stim.get("language", "en")
    if lang not in ("en", "zh", "es"):
        errors.append(f"stimulus.language must be one of: en, zh, es — got '{lang}'")

    return errors
