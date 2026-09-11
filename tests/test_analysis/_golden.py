"""Golden records of analysis runs.

The stage orchestrators were retired after the graph engine matched them on every
case in ``test_golden_subject.py`` and ``test_group_study_runs.py``. Their outputs on
those cases are kept as JSON records in ``golden/``, and each test run compares the
graph engine against them.

Re-record only for an intended behaviour change, then review the diff::

    FMRIFLOW_RECORD_GOLDEN=1 pytest tests/test_analysis/test_golden_subject.py tests/test_analysis/test_group_study_runs.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.types import StimulusData

GOLDEN_DIR = Path(__file__).parent / "golden"
RECORD = os.environ.get("FMRIFLOW_RECORD_GOLDEN") or ""


def digest(value: Any, root: str = "") -> Any:
    """A JSON-able fingerprint of a context value: arrays by shape, dtype and hash."""
    if isinstance(value, np.ndarray):
        arr = np.ascontiguousarray(value)
        if arr.dtype == object:
            return {"ndarray": list(arr.shape), "items": [digest(v, root) for v in arr.ravel().tolist()]}
        return {"ndarray": list(arr.shape), "dtype": str(arr.dtype), "sha256": hashlib.sha256(arr.tobytes()).hexdigest()}
    if isinstance(value, StimulusData):
        return {"StimulusData": list(value.runs)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {type(value).__name__: {f.name: digest(getattr(value, f.name), root) for f in dataclasses.fields(value)}}
    if isinstance(value, dict):
        return {"dict": [[str(k), digest(v, root)] for k, v in value.items()]}
    if isinstance(value, (list, tuple)):
        return [digest(v, root) for v in value]
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    if isinstance(value, str):
        return value.replace(root, "<root>") if root else value
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return {"object": type(value).__name__}


def check_golden(name: str, record: dict) -> None:
    """Compare ``record`` with ``golden/<name>.json`` section by section (or write it when recording)."""
    data = json.loads(json.dumps(record, default=str))
    path = GOLDEN_DIR / f"{name}.json"
    if RECORD:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
        return
    assert path.is_file(), f"no golden record {path.name}; record it with FMRIFLOW_RECORD_GOLDEN=1"
    expected = json.loads(path.read_text())
    assert sorted(data) == sorted(expected)
    for key in expected:
        assert data[key] == expected[key], f"{name}: {key} differs from the golden record"
