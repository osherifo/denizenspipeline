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
            "enum": ["reading", "listening", "visual"],
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
    "preparation": {
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
            if source not in ("compute", "filesystem", "cloud", "database", "grouped_hdf", "npz_concat"):
                errors.append(
                    f"features[{i}] invalid source '{source}', "
                    f"must be one of: compute, filesystem, cloud, database, grouped_hdf, npz_concat"
                )
            if source == "filesystem" and "path" not in feat:
                errors.append(f"features[{i}] filesystem source requires 'path'")
            if source == "cloud" and "bucket" not in feat:
                errors.append(f"features[{i}] cloud source requires 'bucket'")
            if source == "grouped_hdf" and "paths" not in feat:
                errors.append(f"features[{i}] grouped_hdf source requires 'paths'")

    # Split validation — either whole-run holdout (test_runs) or a trial-level
    # holdout named by test_trials (a per-run mask the response loader supplies).
    split = config.get("split", {})
    if "test_runs" not in split and "test_trials" not in split:
        errors.append("'split' requires either 'test_runs' or 'test_trials'")
    elif "test_runs" in split and "test_trials" in split:
        errors.append("'split' accepts either 'test_runs' or 'test_trials', not both "
                      "(the preparer would silently ignore 'test_runs')")

    # Preparation validation
    prep = config.get("preparation", {})
    prep_type = prep.get("type", "default")

    if prep_type == "pipeline":
        # Pipeline preparer: validate steps list
        steps = prep.get("steps")
        if steps is None:
            errors.append("pipeline preparer requires 'preparation.steps'")
        elif not isinstance(steps, list):
            errors.append("'preparation.steps' must be a list")
        else:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"preparation.steps[{i}] must be a dict")
                elif "name" not in step:
                    errors.append(f"preparation.steps[{i}] missing 'name'")
    else:
        # Default / other preparer types: validate trim params
        trim_start = prep.get("trim_start", 5)
        trim_end = prep.get("trim_end", 5)
        if not isinstance(trim_start, int) or trim_start < 0:
            errors.append(f"preparation.trim_start must be non-negative int, got {trim_start}")
        if not isinstance(trim_end, int) or trim_end < 0:
            errors.append(f"preparation.trim_end must be non-negative int, got {trim_end}")

    # Analysis validation (optional)
    analysis = config.get("analysis")
    if analysis is not None:
        if not isinstance(analysis, list):
            errors.append("'analysis' must be a list")
        else:
            for i, acfg in enumerate(analysis):
                if not isinstance(acfg, dict):
                    errors.append(f"analysis[{i}] must be a dict")
                    continue

                name = acfg.get("name")
                if name is None:
                    errors.append(f"analysis[{i}] missing 'name'")
                elif not isinstance(name, str):
                    errors.append(
                        f"analysis[{i}].name must be a string, got {type(name).__name__}"
                    )

                params = acfg.get("params")
                if params is not None and not isinstance(params, dict):
                    errors.append(
                        f"analysis[{i}].params must be a dict, got {type(params).__name__}"
                    )
    # Model validation
    model = config.get("model", {})
    if "type" in model:
        valid_models = ("bootstrap_ridge",)
        if model["type"] not in valid_models:
            pass  # Allow unknown models (could be external plugins)

    # Intermediates validation (optional, opt-in QA feature)
    inter = config.get("intermediates")
    if inter is not None:
        if not isinstance(inter, dict):
            errors.append("'intermediates' must be a dict")
        else:
            from fmriflow.intermediates import SAVEABLE_STAGES
            save = inter.get("save")
            if save not in (None, False, True) and not isinstance(save, (list, str)):
                errors.append(
                    "'intermediates.save' must be bool, list of stage names, "
                    "or a stage name string"
                )
            if isinstance(save, list):
                for s in save:
                    if s not in SAVEABLE_STAGES:
                        errors.append(
                            f"intermediates.save: '{s}' is not a recognised stage "
                            f"(known: {', '.join(SAVEABLE_STAGES)})"
                        )
            fmt = inter.get("format", "joblib")
            if fmt not in ("joblib",):
                errors.append(
                    f"intermediates.format '{fmt}' not supported "
                    "(only 'joblib' in v1)"
                )
            compress = inter.get("compress", "lz4")
            if (
                compress not in ("lz4", "gzip", "none", None, False, True)
                and not isinstance(compress, int)
            ):
                errors.append(
                    f"intermediates.compress '{compress}' invalid "
                    "(use 'lz4', 'gzip', 'none', or an int level)"
                )

    # QA validation (optional, opt-in QA-viz layer)
    qa = config.get("qa")
    if qa is not None:
        if not isinstance(qa, dict):
            errors.append("'qa' must be a dict")
        else:
            from fmriflow.intermediates import SAVEABLE_STAGES as _QA_STAGES
            enabled = qa.get("enabled", False)
            if not isinstance(enabled, bool):
                errors.append("'qa.enabled' must be a bool")
            stages = qa.get("stages")
            if stages is not None and not (
                isinstance(stages, bool)
                or isinstance(stages, str)
                or isinstance(stages, list)
            ):
                errors.append(
                    "'qa.stages' must be a bool, string, or list of stage names"
                )
            if isinstance(stages, list):
                for s in stages:
                    if s not in _QA_STAGES:
                        errors.append(
                            f"qa.stages: '{s}' is not a recognised stage "
                            f"(known: {', '.join(_QA_STAGES)})"
                        )
            # Per-stage blocks: validate ``plugins`` is a list of strings.
            for key, val in qa.items():
                if key in ("enabled", "stages", "output_subdir"):
                    continue
                if not isinstance(val, dict):
                    continue
                if key not in _QA_STAGES:
                    errors.append(
                        f"qa.{key}: not a recognised stage "
                        f"(known: {', '.join(_QA_STAGES)})"
                    )
                    continue
                plugins = val.get("plugins")
                if plugins is not None and not isinstance(plugins, list):
                    errors.append(f"qa.{key}.plugins must be a list of names")

    # Stimulus validation
    stim = config.get("stimulus", {})
    lang = stim.get("language", "en")
    if lang not in ("en", "zh", "es"):
        errors.append(f"stimulus.language must be one of: en, zh, es — got '{lang}'")

    loader = stim.get("loader", "textgrid")
    if loader in ("audio", "video") and "path" not in stim:
        errors.append(f"stimulus loader '{loader}' requires 'stimulus.path'")

    return errors


def validate_group_config(config: dict) -> list[str]:
    """Validate a group-scope config (top-level ``group:`` block).

    A group config does not have ``experiment`` / ``subject`` at the root —
    those live in ``subject_template`` and are filled in per-subject. The
    subject configs built by :class:`fmriflow.group_orchestrator.GroupOrchestrator`
    are validated against the subject schema (:func:`validate_config`) at
    fan-out time.
    """
    errors: list[str] = []

    if not config.get("group"):
        errors.append("'group' (group name) is required")

    if "subjects" not in config and "subjects_from" not in config:
        errors.append("'subjects' (list) or 'subjects_from' (rule) is required")
    elif "subjects" in config:
        subs = config["subjects"]
        if not isinstance(subs, list) or not subs:
            errors.append("'subjects' must be a non-empty list")

    template = config.get("subject_template")
    if not isinstance(template, dict) or not template:
        errors.append(
            "'subject_template' is required and must be a dict of "
            "shared subject-scope settings")

    overrides = config.get("subject_overrides")
    if overrides is not None and not isinstance(overrides, dict):
        errors.append("'subject_overrides' must be a dict keyed by subject id")

    if "analysis" in config:
        # Never read: subject configs are built from subject_template +
        # subject_overrides only, and the second pass re-runs each subject's
        # own config snapshot. Fail loudly instead of silently skipping it.
        errors.append(
            "'analysis' at the top level of a group config is ignored; move it "
            "under 'subject_template' (subject analyzers also run in the "
            "second pass when a group analyzer provides bindings)")

    for key in ("group_analyze", "group_report"):
        section = config.get(key)
        if section is None:
            continue
        if not isinstance(section, list):
            errors.append(f"'{key}' must be a list")
            continue
        for i, entry in enumerate(section):
            if not isinstance(entry, dict):
                errors.append(f"{key}[{i}] must be a dict")
            elif "name" not in entry:
                errors.append(f"{key}[{i}] missing 'name'")

    parallel = config.get("parallel")
    if parallel is not None:
        if not isinstance(parallel, dict):
            errors.append("'parallel' must be a dict")
        else:
            mw = parallel.get("max_workers")
            if mw is not None and (not isinstance(mw, int) or mw < 1):
                errors.append("parallel.max_workers must be a positive int")

    return errors


def validate_study_config(config: dict) -> list[str]:
    """Validate a study-scope config (top-level ``study:`` block).

    A study config does not have ``experiment`` / ``subject`` / ``group``
    at the root — those live one level down in the referenced group
    YAMLs. The deep checks (does the referenced group YAML load? does it
    have a top-level ``group:``?) happen inside StudyOrchestrator's
    ``study_collect`` stage; this validator covers the top-level shape
    only so a malformed YAML is rejected before any work happens.
    """
    errors: list[str] = []

    if not config.get("study"):
        errors.append("'study' (study name) is required")

    groups = config.get("groups")
    if not isinstance(groups, list) or not groups:
        errors.append("'groups' must be a non-empty list")
    else:
        seen: set[str] = set()
        for i, entry in enumerate(groups):
            if not isinstance(entry, dict):
                errors.append(f"groups[{i}] must be a dict")
                continue
            label = entry.get("name")
            if not isinstance(label, str) or not label:
                errors.append(f"groups[{i}] missing or empty 'name'")
                continue
            if label in seen:
                errors.append(
                    f"groups[{i}] duplicate label '{label}' "
                    "(each study-scope group name must be unique)"
                )
                continue
            seen.add(label)
            if not isinstance(entry.get("config"), str):
                errors.append(
                    f"groups[{i}] ({label}) missing 'config:' path "
                    "(inline group bodies are not supported in v1)"
                )

    for key in ("study_analyze", "study_report"):
        section = config.get(key)
        if section is None:
            continue
        if not isinstance(section, list):
            errors.append(f"'{key}' must be a list")
            continue
        for i, entry in enumerate(section):
            if not isinstance(entry, dict):
                errors.append(f"{key}[{i}] must be a dict")
            elif "name" not in entry:
                errors.append(f"{key}[{i}] missing 'name'")

    parallel = config.get("parallel")
    if parallel is not None:
        if not isinstance(parallel, dict):
            errors.append("'parallel' must be a dict")
        else:
            mw = parallel.get("max_workers")
            if mw is not None and (not isinstance(mw, int) or mw < 1):
                errors.append("parallel.max_workers must be a positive int")

    return errors
