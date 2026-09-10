"""Checkpoints — small uniform QA records evaluated as nodes produce files.

A node declares ``CHECKS``: which artefacts to look at and which metric
function to run on each. Evaluation turns metrics + norms into one
:class:`Checkpoint` with a verdict (``ok`` / ``suspicious`` / ``bad`` /
``unknown``). Records are appended to ``<run_dir>/checkpoints.jsonl`` and
echoed as ``{"event": "checkpoint", ...}`` into the run's event stream, so
the monitor shows them live.

Two evaluation paths:

- **Live, inside a container app** (fmriprep): :class:`CheckpointWatcher`
  polls the declared artefacts while the app runs and evaluates each one
  as soon as it appears or changes — ``nu.mgz`` is judged ~20 minutes
  into a 10-hour recon-all, not after.
- **On node completion** (any node): the runner evaluates the generic
  output checks for every nifti output port.

``abort_on_bad`` (per run, off by default) turns a ``bad`` verdict into a
termination of the offending app / an abort of the run.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from fmriflow.preproc.norms import Bound, StepNorms, norms_for

logger = logging.getLogger(__name__)

Verdict = Literal["ok", "suspicious", "bad", "unknown"]
VERDICT_ORDER = {"ok": 0, "unknown": 1, "suspicious": 2, "bad": 3}
CHECKPOINTS_FILENAME = "checkpoints.jsonl"


@dataclass(frozen=True)
class Checkpoint:
    stage: str
    run_id: str
    node: str
    step: str
    subject: str
    metrics: dict[str, Any]
    expectations: dict[str, list]           # {metric: [op, value]} (hard bounds)
    verdict: str
    thumbnail: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    t: float = 0.0
    artifact: str | None = None
    reasons: list[str] = field(default_factory=list)
    soft_expectations: dict[str, list] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage, "run_id": self.run_id, "node": self.node, "step": self.step,
            "subject": self.subject, "metrics": self.metrics, "expectations": self.expectations,
            "soft_expectations": self.soft_expectations, "verdict": self.verdict,
            "thumbnail": self.thumbnail, "detail": self.detail, "t": self.t,
            "artifact": self.artifact, "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Checkpoint:
        return cls(
            stage=d.get("stage", "preproc"), run_id=d.get("run_id", ""), node=d.get("node", ""),
            step=d.get("step", ""), subject=d.get("subject", ""), metrics=dict(d.get("metrics") or {}),
            expectations=dict(d.get("expectations") or {}), verdict=d.get("verdict", "unknown"),
            thumbnail=d.get("thumbnail"), detail=dict(d.get("detail") or {}), t=float(d.get("t") or 0.0),
            artifact=d.get("artifact"), reasons=list(d.get("reasons") or []),
            soft_expectations=dict(d.get("soft_expectations") or {}),
        )


MetricFn = Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]   # -> (metrics, detail)


@dataclass(frozen=True)
class Check:
    """One declared check on a node.

    ``artifact`` is a path template with placeholders the node's
    ``checkpoint_context()`` supplies (``{node_dir}``, ``{fs_subject_dir}``,
    ``{derivatives_dir}``, ``{subject}``, ...). ``metrics`` computes the
    metric dict from the file; ``norms_key`` selects the norms row
    (defaults to ``step``). ``live`` checks are evaluated while the node
    is still running.

    A check is also plain data (:meth:`to_dict` / :meth:`from_dict`): a
    pipeline node may carry ``checks:`` entries naming a registered metric
    and, optionally, its own ``norms`` bounds that overlay the table.
    """

    step: str
    artifact: str
    metrics: MetricFn
    norms_key: str | None = None
    live: bool = True
    thumbnail: str | None = None       # "volume" | None
    metric: str | None = None          # registry name (None for a bare function)
    norms: dict[str, dict[str, Any]] | None = None   # inline {"hard": {...}, "soft": {...}}
    source: str = "builtin"            # "builtin" | "pipeline"

    @property
    def key(self) -> str:
        return self.norms_key or self.step

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step, "artifact": self.artifact, "metric": self.metric or _metric_name(self.metrics),
            "norms_key": self.norms_key, "live": self.live, "thumbnail": self.thumbnail,
            "norms": self.norms, "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], *, source: str = "pipeline") -> Check:
        name = str(d.get("metric") or "nifti_stats")
        fn = get_metric(name)
        norms = d.get("norms") or None
        if norms:
            norms = {k: {m: _bound_from_json(b) for m, b in (v or {}).items()} for k, v in norms.items() if k in ("hard", "soft")}
        return cls(
            step=str(d.get("step") or name), artifact=str(d.get("artifact") or ""), metrics=fn,
            norms_key=d.get("norms_key") or None, live=bool(d.get("live", True)),
            thumbnail=d.get("thumbnail") or None, metric=name, norms=norms, source=source,
        )


def _bound_from_json(b: Any) -> Bound:
    """``["<", 0.5]`` / ``["between", [lo, hi]]`` (JSON / YAML) → ``(op, value)``."""
    if isinstance(b, (list, tuple)) and len(b) == 2:
        op, val = b
        if op == "between" and isinstance(val, (list, tuple)):
            val = (float(val[0]), float(val[1]))
        return (str(op), val)
    raise ValueError(f"bad bound {b!r}: expected [op, value]")


# ── metric registry ───────────────────────────────────────────────

_METRICS: dict[str, MetricFn] = {}
_METRIC_FILES: dict[str, Path] = {}       # user metric name -> the addon file that registered it
_ADDON_ERRORS: dict[str, str] = {}        # addon file name -> why it failed to load
_ADDONS_LOADED = False
_METRIC_SLUG = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def checkpoint_metric(name: str):
    """Register a metric function ``fn(path) -> (metrics, detail)`` under ``name``,
    so pipeline-level checks (and the UI) can refer to it. Files under
    ``$FMRIFLOW_HOME/addons/checks/`` are imported on first use."""
    def wrap(fn: MetricFn) -> MetricFn:
        _METRICS[name] = fn
        return fn
    return wrap


def _metric_name(fn: MetricFn) -> str | None:
    return next((n for n, f in _METRICS.items() if f is fn), None)


def is_builtin_metric(name: str) -> bool:
    fn = _METRICS.get(name)
    return fn is not None and name not in _METRIC_FILES and (fn.__module__ or "").startswith("fmriflow.")


def addon_checks_dir() -> Path:
    from fmriflow.core.paths import addons_dir
    return addons_dir("checks")


def _load_file(f: Path) -> list[str]:
    """Exec one addon file; return the metric names it registered."""
    import importlib.util
    before = set(_METRICS)
    replaced = {n: _METRICS[n] for n in before}
    spec = importlib.util.spec_from_file_location(f"fmriflow_addon_checks_{f.stem}", f)
    if not (spec and spec.loader):
        raise ImportError(f"cannot load {f}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = [n for n, fn in _METRICS.items() if n not in before or replaced.get(n) is not fn]
    for n in names:
        _METRIC_FILES[n] = f
    return names


def load_addon_metrics(dirs: list[Path] | None = None, *, reload: bool = False) -> None:
    """Import every ``.py`` under the addon checks dir(s) so their
    ``@checkpoint_metric`` decorators run. Idempotent unless ``reload``,
    which drops every user metric first and re-imports the files."""
    global _ADDONS_LOADED
    if dirs is None:
        if _ADDONS_LOADED and not reload:
            return
        _ADDONS_LOADED = True
        try:
            dirs = [addon_checks_dir()]
        except Exception:
            return
    if reload:
        for n in list(_METRIC_FILES):
            _METRICS.pop(n, None)
        _METRIC_FILES.clear()
        _ADDON_ERRORS.clear()
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                _load_file(f)
            except Exception as e:
                logger.exception("could not load addon checks file %s", f)
                _ADDON_ERRORS[f.name] = f"{type(e).__name__}: {e}"


def get_metric(name: str) -> MetricFn:
    load_addon_metrics()
    try:
        return _METRICS[name]
    except KeyError:
        raise KeyError(f"unknown checkpoint metric {name!r}; known: {sorted(_METRICS)}") from None


def metric_catalog() -> list[dict[str, Any]]:
    """``[{name, description, builtin, tier, path}]`` for the UI's metric picker and editor."""
    load_addon_metrics()
    out = []
    for name, fn in sorted(_METRICS.items()):
        doc = (fn.__doc__ or "").strip().splitlines()
        builtin = is_builtin_metric(name)
        out.append({
            "name": name, "description": doc[0] if doc else "", "builtin": builtin,
            "tier": "builtin" if builtin else "user",
            "path": str(_METRIC_FILES[name]) if name in _METRIC_FILES else None,
        })
    for fname, err in sorted(_ADDON_ERRORS.items()):
        out.append({"name": fname[:-3], "description": "", "builtin": False, "tier": "user",
                    "path": str(addon_checks_dir() / fname), "error": err})
    return out


def metric_source(name: str) -> str:
    """The Python source behind a metric: its addon file, or the built-in function."""
    import inspect
    load_addon_metrics()
    if name in _METRIC_FILES:
        return _METRIC_FILES[name].read_text()
    err_file = addon_checks_dir() / f"{name}.py"
    if name in {f[:-3] for f in _ADDON_ERRORS} and err_file.is_file():
        return err_file.read_text()
    fn = get_metric(name)
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return f"# source of {name!r} is not available\n"


METRIC_SCAFFOLD = '''"""A checkpoint metric: a function from an artifact path to numbers.

Register it with @checkpoint_metric("<name>"); it then appears in the metric
picker of a node's Checks and can carry norms (bounds) in Library → Checkpoint
norms. Return (metrics, detail): `metrics` is a flat dict of numbers / bools /
short strings the norms compare against; `detail` is anything extra the
checkpoint card shows.
"""
from pathlib import Path

from fmriflow.preproc.checkpoints import checkpoint_metric


@checkpoint_metric("my_metric")
def my_metric(path: Path) -> tuple[dict, dict]:
    """One line on what this measures — shown in the picker."""
    import nibabel as nib
    import numpy as np

    data = np.asarray(nib.load(str(path)).dataobj, dtype="float32")
    nonzero = data[data != 0]
    metrics = {
        "n_voxels": int(data.size),
        "nonzero_fraction": float(nonzero.size / max(data.size, 1)),
        "mean": float(nonzero.mean()) if nonzero.size else 0.0,
    }
    return metrics, {}
'''


def probe_metric_code(code: str, filename: str) -> list[str]:
    """Compile + exec ``code`` against a scratch registry; return the metric
    names it registers. Raises SyntaxError / the exec error. Nothing is
    registered for real."""
    global _METRICS
    compile(code, filename, "exec")
    import types
    real = _METRICS
    scratch: dict[str, MetricFn] = dict(real)
    _METRICS = scratch
    try:
        mod = types.ModuleType(f"fmriflow_addon_probe_{Path(filename).stem}")
        mod.__file__ = filename
        exec(compile(code, filename, "exec"), mod.__dict__)
        return [n for n, fn in scratch.items() if real.get(n) is not fn]
    finally:
        _METRICS = real


def save_user_metric(name: str, code: str) -> Path:
    """Write ``code`` as ``addons/checks/<name>.py`` and (re)load the addons.

    The code must register ``@checkpoint_metric("<name>")``; built-in names
    are refused. ``ValueError`` explains any refusal.
    """
    if not _METRIC_SLUG.match(name or ""):
        raise ValueError("metric name must start with a letter and use letters / digits / underscores")
    load_addon_metrics()
    if is_builtin_metric(name):
        raise ValueError(f"{name!r} is a built-in metric; duplicate it under another name")
    if not code.strip():
        raise ValueError("code is empty")
    try:
        registered = probe_metric_code(code, f"<checks/{name}.py>")
    except SyntaxError as e:
        raise ValueError(f"Python syntax error: {e}")
    except Exception as e:
        raise ValueError(f"the code fails to run: {type(e).__name__}: {e}")
    if name not in registered:
        raise ValueError(
            f"the code must register @checkpoint_metric({name!r}) (it registers: {registered or 'nothing'})"
        )
    clashes = [n for n in registered if n != name and is_builtin_metric(n)]
    if clashes:
        raise ValueError(f"the code would override built-in metric(s) {clashes}; rename them")
    target = addon_checks_dir() / f"{name}.py"
    target.write_text(code)
    load_addon_metrics(reload=True)
    return target


def delete_user_metric(name: str) -> Path:
    """Remove the addon file behind a user metric; ``KeyError`` when unknown, ``ValueError`` for built-ins."""
    load_addon_metrics()
    if is_builtin_metric(name):
        raise ValueError(f"{name!r} is a built-in metric and cannot be deleted")
    path = _METRIC_FILES.get(name) or (addon_checks_dir() / f"{name}.py")
    if not path.is_file():
        raise KeyError(f"no user metric {name!r}")
    path.unlink()
    load_addon_metrics(reload=True)
    return path


def run_metric(name: str, path: Path) -> dict[str, Any]:
    """Apply a metric to one file — the editor's try-it. Errors are returned, not raised."""
    fn = get_metric(name)
    if not Path(path).exists():
        return {"ok": False, "error": f"no such file: {path}"}
    try:
        metrics, detail = fn(Path(path))
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "metrics": _jsonable(metrics), "detail": _jsonable(detail)}


def _jsonable(v: Any) -> Any:
    import numpy as np
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, Path):
        return str(v)
    return v


def resolve_checks(cls: type, node_checks: list[dict[str, Any]] | None, params: dict[str, Any] | None = None) -> list[Check]:
    """The checks to run for a node: its class ``CHECKS`` (narrowed by an
    optional ``checks_for_params(params, checks)`` method when ``params`` are
    given — fmriprep drops its FreeSurfer checks in functional-only modes),
    minus the ones a pipeline entry disables (``{"step": ..., "enabled": false}``),
    plus the pipeline's own entries (a pipeline entry with a built-in's ``step``
    and ``norms`` only re-bounds that built-in)."""
    from fmriflow.preproc.norms import is_active_step
    base_checks = [c for c in (getattr(cls, "CHECKS", []) or []) if is_active_step(c.key)]
    hook = getattr(cls, "checks_for_params", None)
    if params is not None and callable(hook):
        try:
            base_checks = list(hook(cls(), dict(params), base_checks))
        except Exception:
            logger.exception("checks_for_params failed for %s; using all checks", cls)
    builtin = {c.step: c for c in base_checks}
    out: dict[str, Check] = dict(builtin)
    for entry in node_checks or []:
        step = str(entry.get("step") or "")
        if not step:
            continue
        if entry.get("enabled") is False:
            out.pop(step, None)
            continue
        base = builtin.get(step)
        if base is not None and not entry.get("artifact") and not entry.get("metric"):
            # re-bound a built-in
            norms = entry.get("norms") or None
            if norms:
                norms = {k: {m: _bound_from_json(b) for m, b in (v or {}).items()} for k, v in norms.items() if k in ("hard", "soft")}
            out[step] = Check(**{**base.__dict__, "norms": norms, "source": "pipeline"})
            continue
        out[step] = Check.from_dict({**entry, "step": step})
    return list(out.values())


# ── verdicts ──────────────────────────────────────────────────────

def _holds(value: Any, bound: Bound) -> bool:
    op, ref = bound
    try:
        if op == "<":
            return value < ref
        if op == "<=":
            return value <= ref
        if op == ">":
            return value > ref
        if op == ">=":
            return value >= ref
        if op == "==":
            return value == ref
        if op == "!=":
            return value != ref
        if op == "between":
            lo, hi = ref
            return lo <= value <= hi
    except TypeError:
        return False
    raise ValueError(f"unknown bound op {op!r}")


def _fmt(bound: Bound) -> str:
    op, ref = bound
    return f"between {ref[0]} and {ref[1]}" if op == "between" else f"{op} {ref}"


def verdict_for(metrics: dict[str, Any], norms: StepNorms) -> tuple[str, list[str]]:
    """``bad`` if any hard bound fails, else ``suspicious`` if any soft bound fails,
    ``unknown`` if a bound's metric is missing, else ``ok``."""
    reasons: list[str] = []
    verdict = "ok"
    hard, soft = norms.get("hard", {}), norms.get("soft", {})
    for metric, bound in hard.items():
        if metric not in metrics:
            verdict = max(verdict, "unknown", key=VERDICT_ORDER.get)
            reasons.append(f"{metric}: not measured")
            continue
        if not _holds(metrics[metric], bound):
            verdict = "bad"
            reasons.append(f"{metric}={_short(metrics[metric])} violates {_fmt(bound)}")
    if verdict != "bad":
        for metric, bound in soft.items():
            if metric in metrics and not _holds(metrics[metric], bound):
                verdict = max(verdict, "suspicious", key=VERDICT_ORDER.get)
                reasons.append(f"{metric}={_short(metrics[metric])} outside {_fmt(bound)}")
    return verdict, reasons


def _short(v: Any) -> str:
    return f"{v:.3g}" if isinstance(v, float) else str(v)


def worst_verdict(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda v: VERDICT_ORDER.get(v, 1)) if verdicts else "unknown"


# ── metric functions ──────────────────────────────────────────────

def _load_volume(path: Path):
    import nibabel as nib
    import numpy as np
    img = nib.load(str(path))
    data = np.asanyarray(img.dataobj)
    zooms = img.header.get_zooms()[:3]
    return data, tuple(float(z) for z in zooms)


@checkpoint_metric("volume_intensity")
def volume_intensity_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """n_unique, modal value + fraction and quartiles over the non-zero voxels."""
    import numpy as np
    data, zooms = _load_volume(path)
    nz = data[data != 0]
    if nz.size == 0:
        return {"n_nonzero": 0, "n_unique": 0, "modal_fraction": 1.0}, {}
    flat = nz.ravel()
    if flat.dtype.kind == "f":
        rounded = np.round(flat, 3)
    else:
        rounded = flat
    values, counts = np.unique(rounded, return_counts=True)
    modal_idx = int(np.argmax(counts))
    p25, p50, p75 = (float(x) for x in np.percentile(flat, [25, 50, 75]))
    hist, edges = np.histogram(flat, bins=64)
    metrics = {
        "n_nonzero": int(flat.size),
        "n_unique": int(values.size),
        "modal_value": float(values[modal_idx]),
        "modal_fraction": float(counts[modal_idx] / flat.size),
        "p25": p25, "p50": p50, "p75": p75,
        "min": float(flat.min()), "max": float(flat.max()),
        "shape": [int(s) for s in data.shape],
    }
    detail = {"histogram": [int(h) for h in hist], "edges": [float(e) for e in edges], "zooms": list(zooms)}
    return metrics, detail


def _mask_volume_metrics(path: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np
    data, zooms = _load_volume(path)
    voxel_cm3 = float(np.prod(zooms)) / 1000.0
    nz = data != 0
    metrics = {f"{name}_volume_cm3": float(nz.sum() * voxel_cm3), "n_voxels": int(nz.sum())}
    flat = data[nz]
    if flat.size:
        values, counts = np.unique(flat, return_counts=True)
        metrics["modal_fraction"] = float(counts.max() / flat.size)
        metrics["n_unique"] = int(values.size)
    return metrics, {"zooms": list(zooms)}


@checkpoint_metric("wm_volume")
def wm_volume_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _mask_volume_metrics(path, "wm")


@checkpoint_metric("brain_volume")
def brain_volume_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _mask_volume_metrics(path, "brain")


@checkpoint_metric("surface")
def surface_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Vertex / face counts and the Euler number of a FreeSurfer surface.

    For a closed triangle mesh E = 3F/2 and a sphere-topology surface has
    Euler number 2; each handle costs 2, so ``n_defects = (2 - euler) / 2``.
    """
    from nibabel.freesurfer import read_geometry
    verts, faces = read_geometry(str(path))
    n_v, n_f = int(verts.shape[0]), int(faces.shape[0])
    n_e = (3 * n_f) // 2
    euler = n_v - n_e + n_f
    return {"n_vertices": n_v, "n_faces": n_f, "euler": int(euler), "n_defects": int(max(0, (2 - euler) // 2))}, {}


@checkpoint_metric("thickness")
def thickness_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np
    from nibabel.freesurfer import read_morph_data
    th = np.asarray(read_morph_data(str(path)), dtype="float64")
    if th.size == 0:
        return {"n_vertices": 0}, {}
    nz = th[th > 0]
    hist, edges = np.histogram(th, bins=40, range=(0.0, 6.0))
    return {
        "n_vertices": int(th.size),
        "mean_mm": float(nz.mean()) if nz.size else 0.0,
        "p95_mm": float(np.percentile(nz, 95)) if nz.size else 0.0,
        "zero_fraction": float((th <= 0).mean()),
    }, {"histogram": [int(h) for h in hist], "edges": [float(e) for e in edges]}


@checkpoint_metric("aseg_stats")
def aseg_stats_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Global measures from recon-all's ``aseg.stats`` header."""
    metrics: dict[str, Any] = {}
    wanted = {
        "EstimatedTotalIntraCranialVol": "etiv_cm3",
        "BrainSegVol": "brainseg_cm3",
        "CerebralWhiteMatterVol": "cerebral_wm_cm3",
        "TotalGrayVol": "total_gray_cm3",
    }
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("# Measure"):
            continue
        parts = [p.strip() for p in line[len("# Measure"):].split(",")]
        if len(parts) < 4:
            continue
        key = parts[0]
        if key in wanted:
            try:
                metrics[wanted[key]] = float(parts[3]) / 1000.0
            except ValueError:
                pass
    return metrics, {}


@checkpoint_metric("output_file")
def output_file_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generic: existence, size and, for NIfTI, shape / 4D-ness / non-zero fraction."""
    metrics: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return metrics, {}
    metrics["size_bytes"] = int(path.stat().st_size)
    suffix = "".join(path.suffixes[-2:]).lower()
    if any(suffix.endswith(s) for s in (".nii", ".nii.gz", ".mgz", ".mgh")):
        try:
            import numpy as np
            data, _ = _load_volume(path)
            metrics["shape"] = [int(s) for s in data.shape]
            metrics["is_4d"] = data.ndim == 4 and data.shape[3] > 1
            metrics["n_trs"] = int(data.shape[3]) if data.ndim == 4 else 1
            sample = data[..., 0] if data.ndim == 4 else data
            metrics["nonzero_fraction"] = float(np.count_nonzero(sample) / max(sample.size, 1))
        except Exception as e:
            metrics["read_error"] = str(e)
    return metrics, {}


@checkpoint_metric("nifti_stats")
def nifti_stats_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shape, voxel size, non-zero fraction, mean/std and percentiles of any NIfTI/MGZ — the
    all-purpose metric for a check written in the UI."""
    import numpy as np
    data, zooms = _load_volume(path)
    arr = np.asarray(data, dtype="float64")
    if arr.ndim == 4 and arr.shape[3] == 1:
        arr = arr[..., 0]          # a singleton time axis is a single volume
    nz = arr[arr != 0]
    metrics: dict[str, Any] = {
        "shape": [int(x) for x in data.shape], "ndim": int(arr.ndim), "is_4d": arr.ndim == 4,
        "n_trs": int(arr.shape[3]) if arr.ndim == 4 else 1,
        "voxel_mm": [round(float(z), 3) for z in zooms],
        "nonzero_fraction": float(nz.size / max(arr.size, 1)),
        "n_unique": int(np.unique(np.round(nz, 3)).size) if nz.size else 0,
    }
    if nz.size:
        p1, p50, p99 = (float(x) for x in np.percentile(nz, [1, 50, 99]))
        metrics.update({"mean": float(nz.mean()), "std": float(nz.std()), "p01": p1, "p50": p50, "p99": p99,
                        "min": float(nz.min()), "max": float(nz.max())})
    if arr.ndim == 4 and arr.shape[3] > 1:
        ts = arr.reshape(-1, arr.shape[3])
        m = ts.mean(axis=1); sd = ts.std(axis=1)
        keep = (m != 0) & (sd > 0)
        if keep.any():
            metrics["tsnr_median"] = float(np.median(m[keep] / sd[keep]))
    return metrics, {}


@checkpoint_metric("bold_integrity")
def bold_integrity_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """A BOLD series' basic integrity: NaN/Inf voxels, all-zero volumes, negative values,
    flat time series, and RF-spike volumes (global mean beyond median ± 5·MAD)."""
    import numpy as np
    data, _ = _load_volume(path)
    arr = np.asarray(data, dtype="float64")
    if arr.ndim == 4 and arr.shape[3] == 1:
        arr = arr[..., 0]          # fmriprep writes reference volumes as (x, y, z, 1)
    metrics: dict[str, Any] = {"shape": [int(x) for x in data.shape], "is_4d": arr.ndim == 4}
    bad = ~np.isfinite(arr)
    metrics["n_nan_inf"] = int(bad.sum())
    finite = np.where(bad, 0.0, arr)
    metrics["n_negative"] = int((finite < 0).sum())
    if arr.ndim == 4:
        n_t = arr.shape[3]
        vol_means = finite.reshape(-1, n_t).mean(axis=0)
        metrics["n_trs"] = int(n_t)
        metrics["n_zero_volumes"] = int((np.abs(finite).reshape(-1, n_t).sum(axis=0) == 0).sum())
        med = float(np.median(vol_means))
        mad = float(np.median(np.abs(vol_means - med))) * 1.4826 or 1e-9
        spikes = np.abs(vol_means - med) > 5.0 * mad
        metrics["n_spike_volumes"] = int(spikes.sum())
        metrics["spike_volumes"] = [int(i) for i in np.flatnonzero(spikes)[:20]]
        ts = finite.reshape(-1, n_t)
        nonzero = np.abs(ts).sum(axis=1) > 0
        metrics["flat_voxel_fraction"] = float((ts[nonzero].std(axis=1) == 0).mean()) if nonzero.any() else 1.0
        metrics["global_mean_range"] = [float(vol_means.min()), float(vol_means.max())]
    else:
        metrics["n_trs"] = 1
        metrics["n_zero_volumes"] = int(np.abs(finite).sum() == 0)
        metrics["n_spike_volumes"] = 0
        nz = finite[finite != 0]
        metrics["spatial_std"] = float(nz.std()) if nz.size else 0.0
    return metrics, {}


def _read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = [ln for ln in path.read_text(errors="replace").splitlines() if ln.strip()]
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = [ln.split("\t") for ln in lines[1:]]
    return header, rows


def _column(header: list[str], rows: list[list[str]], name: str) -> list[float]:
    import math
    if name not in header:
        return []
    i = header.index(name)
    out = []
    for r in rows:
        try:
            v = float(r[i])
        except (ValueError, IndexError):
            v = math.nan
        out.append(v)
    return out


@checkpoint_metric("confounds_motion")
def confounds_motion_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Head motion from fmriprep's confounds TSV: framewise displacement (mean, max, fraction
    over 0.5 mm), DVARS, and the rigid-body extremes (max |translation| mm, max |rotation| deg)."""
    import math
    import numpy as np
    header, rows = _read_tsv(path)
    metrics: dict[str, Any] = {"n_trs": len(rows)}
    fd = [v for v in _column(header, rows, "framewise_displacement") if not math.isnan(v)]
    if fd:
        a = np.asarray(fd)
        metrics.update({"mean_fd": float(a.mean()), "max_fd": float(a.max()),
                        "frac_fd_over_0p2": float((a > 0.2).mean()), "frac_fd_over_0p5": float((a > 0.5).mean()),
                        "n_fd_over_0p5": int((a > 0.5).sum())})
    dv = [v for v in _column(header, rows, "dvars") if not math.isnan(v)]
    if dv:
        metrics["mean_dvars"] = float(np.mean(dv)); metrics["max_dvars"] = float(np.max(dv))
    trans = [np.asarray([v for v in _column(header, rows, c) if not math.isnan(v)]) for c in ("trans_x", "trans_y", "trans_z")]
    rots = [np.asarray([v for v in _column(header, rows, c) if not math.isnan(v)]) for c in ("rot_x", "rot_y", "rot_z")]
    if all(t.size for t in trans):
        metrics["max_abs_trans_mm"] = float(max(np.abs(t - t[0]).max() for t in trans))
        metrics["trans_range_mm"] = float(max(t.max() - t.min() for t in trans))
    if all(r.size for r in rots):
        metrics["max_abs_rot_deg"] = float(math.degrees(max(np.abs(r - r[0]).max() for r in rots)))
    return metrics, {}


@checkpoint_metric("fieldmap_stats")
def fieldmap_stats_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """A preprocessed fieldmap (Hz): finite fraction, spread and the 99th-percentile |offset| —
    a flat map means estimation failed, an enormous one means a wrong delta-TE or wrap."""
    import numpy as np
    data, _ = _load_volume(path)
    arr = np.asarray(data, dtype="float64")
    finite = np.isfinite(arr)
    vals = arr[finite & (arr != 0)]
    metrics: dict[str, Any] = {"finite_fraction": float(finite.mean()), "n_voxels": int(vals.size)}
    if vals.size:
        metrics.update({"std_hz": float(vals.std()), "p99_abs_hz": float(np.percentile(np.abs(vals), 99)),
                        "max_abs_hz": float(np.abs(vals).max()), "median_hz": float(np.median(vals))})
    else:
        metrics.update({"std_hz": 0.0, "p99_abs_hz": 0.0, "max_abs_hz": 0.0})
    return metrics, {}


@checkpoint_metric("phasediff_delta_te")
def phasediff_delta_te_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """From a GRE fieldmap's phasediff JSON: the two echo times and their difference in ms,
    plus how far ΔTE sits from a multiple of the 3 T fat-water period (~2.27 ms)."""
    import json as _json
    meta = _json.loads(path.read_text())
    te1, te2 = meta.get("EchoTime1"), meta.get("EchoTime2")
    metrics: dict[str, Any] = {"has_both_echoes": te1 is not None and te2 is not None}
    if te1 is not None and te2 is not None:
        te1, te2 = float(te1), float(te2)
        d_ms = (te2 - te1) * 1000.0
        metrics.update({"te1_ms": te1 * 1000.0, "te2_ms": te2 * 1000.0, "delta_te_ms": d_ms,
                        "echoes_ordered": te2 > te1 > 0,
                        "fat_period_offset_ms": abs(d_ms / 2.27 - round(d_ms / 2.27)) * 2.27 if d_ms > 0 else 0.0})
    for k in ("PhaseEncodingDirection", "IntendedFor"):
        if k in meta:
            metrics[f"has_{k}"] = True
    return metrics, {}


@checkpoint_metric("compcor_components")
def compcor_components_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """fmriprep's CompCor regressors from the confounds TSV (+ its JSON sidecar): how many
    a/tCompCor columns, any NaN/Inf or constant ones, and the variance the retained
    anatomical components explain."""
    import json as _json
    import math
    import numpy as np
    header, rows = _read_tsv(path)
    acomp = [c for c in header if c.startswith("a_comp_cor_")]
    tcomp = [c for c in header if c.startswith("t_comp_cor_")]
    metrics: dict[str, Any] = {"n_acompcor": len(acomp), "n_tcompcor": len(tcomp), "n_rows": len(rows)}
    n_nan = 0; n_const = 0
    for c in acomp + tcomp:
        col = np.asarray(_column(header, rows, c))
        n_nan += int((~np.isfinite(col)).sum())
        good = col[np.isfinite(col)]
        if good.size and good.std() == 0:
            n_const += 1
    metrics["n_nan_inf_components"] = n_nan
    metrics["n_constant_components"] = n_const
    side = path.with_suffix("").with_suffix(".json") if path.name.endswith(".tsv") else None
    if side is not None and side.is_file():
        try:
            meta = _json.loads(side.read_text())
            cum = [float(v.get("CumulativeVarianceExplained")) for k, v in meta.items()
                   if k.startswith("a_comp_cor_") and isinstance(v, dict) and v.get("CumulativeVarianceExplained") is not None and (v.get("Retained") in (True, None))]
            if cum:
                metrics["acompcor_cumulative_variance"] = float(max(cum))
            masks = {str(v.get("Mask")) for k, v in meta.items() if k.startswith("a_comp_cor_") and isinstance(v, dict)}
            metrics["acompcor_masks"] = sorted(m for m in masks if m and m != "None")
        except (ValueError, TypeError) as e:
            metrics["sidecar_error"] = str(e)
    if acomp:
        cols = np.column_stack([np.asarray(_column(header, rows, c)) for c in acomp[:10]])
        cols = cols[np.isfinite(cols).all(axis=1)]
        if cols.shape[0] > 3 and cols.shape[1] > 1:
            corr = np.corrcoef(cols, rowvar=False)
            off = np.abs(corr[~np.eye(corr.shape[0], dtype=bool)])
            metrics["max_abs_component_correlation"] = float(np.nan_to_num(off).max())
    return metrics, {}


# ── evaluation ────────────────────────────────────────────────────

def evaluate(
    check: Check,
    artifact: Path,
    *,
    run_id: str,
    node: str,
    subject: str,
    sequence: str | None = None,
    stage: str = "preproc",
) -> Checkpoint:
    from fmriflow.preproc.norms import active_metrics
    norms = norms_for(check.key, sequence)
    if check.norms:
        # a pipeline entry's own bounds overlay the table, metric by metric
        for kind in ("hard", "soft"):
            norms[kind].update(check.norms.get(kind) or {})
    try:
        metrics, detail = check.metrics(artifact)
    except Exception as e:
        logger.warning("checkpoint %s on %s failed: %s", check.step, artifact, e)
        metrics, detail = {"error": str(e)}, {}
        verdict, reasons = "unknown", [f"could not compute metrics: {e}"]
    else:
        verdict, reasons = verdict_for(metrics, norms)
        keep = active_metrics(check.key)
        if keep is not None and check.source == "builtin":
            metrics = {k: v for k, v in metrics.items() if k in keep}   # parked metrics stay off the record
    return Checkpoint(
        stage=stage, run_id=run_id, node=node, step=check.step, subject=subject,
        metrics=metrics, expectations={k: list(v) for k, v in norms["hard"].items()},
        soft_expectations={k: list(v) for k, v in norms["soft"].items()},
        verdict=verdict, thumbnail=None, detail=detail, t=time.time(),
        artifact=str(artifact), reasons=reasons,
    )


def generic_output_checks(cls: type) -> list[tuple[str, Check]]:
    """(port, Check) for every nifti-kind output port of a node class (active steps only)."""
    from fmriflow.preproc.node_registry import node_ports
    from fmriflow.preproc.norms import is_active_step
    _, outputs = node_ports(cls)
    checks: list[tuple[str, Check]] = []
    for port, spec in outputs.items():
        kind = str(spec.get("kind", "file"))
        if kind not in ("file", "nifti", "mgz"):
            continue
        key = "bold_output" if kind == "nifti" and port in ("bold", "bold_preproc", "out_file") else "output"
        if not is_active_step(key):
            continue
        checks.append((port, Check(step=port, artifact=port, metrics=output_file_metrics, norms_key=key, live=False)))
    return checks


_GLOB_CHARS = ("*", "?", "[")
_BIDS_ENTITY = re.compile(r"(ses|task|acq|run|dir|echo|fmapid)-[A-Za-z0-9]+")


def resolve_artifacts(template: str, context: dict[str, Any]) -> list[Path]:
    """Every file a template names. A template may use glob wildcards (``*``,
    ``?``, ``**``) for outputs whose names carry run-level entities — fmriprep's
    ``sub-01_ses-01_task-x_run-1_desc-preproc_bold.nii.gz`` — so one check
    covers every run; matches come back sorted, missing files as an empty list."""
    try:
        text = template.format(**context)
    except (KeyError, IndexError):
        return []
    if not any(ch in text for ch in _GLOB_CHARS):
        return [Path(text)]
    # split at the first wildcard segment so Path.glob gets a fixed root
    parts = Path(text).parts
    fixed = []
    for i, part in enumerate(parts):
        if any(ch in part for ch in _GLOB_CHARS):
            root = Path(*fixed) if fixed else Path(".")
            pattern = str(Path(*parts[i:]))
            try:
                return sorted(p for p in root.glob(pattern) if p.is_file())
            except (OSError, ValueError):
                return []
        fixed.append(part)
    return [Path(text)]


def resolve_artifact(template: str, context: dict[str, Any]) -> Path | None:
    """The first file a template names (see :func:`resolve_artifacts`)."""
    found = resolve_artifacts(template, context)
    if found:
        return found[0]
    if any(ch in template for ch in _GLOB_CHARS):
        return None
    try:
        return Path(template.format(**context))
    except (KeyError, IndexError):
        return None


def substep_label(path: Path) -> str:
    """``task-x_run-1`` from a BIDS file name (else its stem): what a check over
    several runs appends to its step name, ``bold_spikes[task-x_run-1]``."""
    name = path.name
    ents = _BIDS_ENTITY.findall(name)
    if ents:
        return "_".join(m.group(0) for m in _BIDS_ENTITY.finditer(name))
    return name.split(".", 1)[0]


class CheckpointSink:
    """Appends checkpoints to ``checkpoints.jsonl`` and mirrors them into the event stream."""

    def __init__(self, checkpoints_path: Path | str | None, events_path: Path | str | None = None) -> None:
        self.checkpoints_path = Path(checkpoints_path) if checkpoints_path else None
        self.events_path = Path(events_path) if events_path else None
        self._lock = threading.Lock()

    def write(self, cp: Checkpoint) -> None:
        record = cp.to_dict()
        with self._lock:
            if self.checkpoints_path is not None:
                self.checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.checkpoints_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, default=str) + "\n")
            if self.events_path is not None:
                from fmriflow.preproc.nipype_log import append_jsonl
                append_jsonl(self.events_path, {
                    "event": "checkpoint", "node": cp.node, "leaf": cp.node.rsplit(".", 1)[-1],
                    "step": cp.step, "verdict": cp.verdict, "reasons": list(cp.reasons),
                    "metrics": cp.metrics, "expectations": cp.expectations, "t": cp.t, "timestamp": cp.t,
                })


def _norms_key_of(d: dict[str, Any]) -> str | None:
    """The norms key a recorded checkpoint (or its mirrored event) was judged by.

    Built-in steps are their own key. Generic output checks record the *port name*
    as their step: a BOLD port maps to ``bold_output``; any other port is
    recognised as ``output`` by its bounds, or (an event carries no bounds) by
    the generic metric's key set. ``None`` for a step a pipeline named itself.
    """
    from fmriflow.preproc.norms import HARD_NORMS
    base = str(d.get("step") or "").split("[", 1)[0]
    if base in HARD_NORMS:
        return base
    if base in _BOLD_PORTS:
        return "bold_output"
    exp = set((d.get("expectations") or {}).keys())
    if exp:
        return "output" if exp == set(HARD_NORMS.get("output", {}).get("hard", {})) else None
    keys = set((d.get("metrics") or {}).keys())
    if keys and "exists" in keys and keys <= _OUTPUT_METRIC_KEYS:
        return "output"
    return None


_BOLD_PORTS = ("bold", "bold_preproc", "out_file")
_OUTPUT_METRIC_KEYS = {"exists", "size_bytes", "shape", "is_4d", "n_trs", "nonzero_fraction", "read_error"}


def is_parked_record(d: dict[str, Any]) -> bool:
    """True for a recorded checkpoint of a check that is parked today (a built-in
    or generic check whose norms key is outside :data:`ACTIVE_CHECKS`). Checks a
    pipeline declared under its own step name are kept."""
    from fmriflow.preproc.norms import ACTIVE_CHECKS, is_active_step
    if ACTIVE_CHECKS is None:
        return False
    key = _norms_key_of(d)
    return key is not None and not is_active_step(key)


def trim_record(d: dict[str, Any]) -> dict[str, Any]:
    """A live record as it would be written today: parked metrics and soft bounds gone."""
    from fmriflow.preproc.norms import active_metrics
    key = _norms_key_of(d)
    keep = active_metrics(key) if key else None
    out = dict(d)
    if keep is not None:
        out["metrics"] = {k: v for k, v in (d.get("metrics") or {}).items() if k in keep}
        out["expectations"] = {k: v for k, v in (d.get("expectations") or {}).items() if k in keep}
    out["soft_expectations"] = {}
    if out.get("verdict") == "suspicious":
        out["verdict"] = "ok"
        out["reasons"] = [r for r in (d.get("reasons") or []) if " outside " not in r]
    return out


def read_checkpoints(path: Path | str, *, active_only: bool = True) -> list[Checkpoint]:
    """Records from ``checkpoints.jsonl``; by default only those of checks that are
    live today, trimmed to the live metrics, so old runs show what new runs would."""
    p = Path(path)
    if not p.is_file():
        return []
    out: list[Checkpoint] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if active_only:
                if is_parked_record(d):
                    continue
                d = trim_record(d)
            out.append(Checkpoint.from_dict(d))
        except (ValueError, KeyError):
            continue
    return out


class CheckpointWatcher(threading.Thread):
    """Poll a node's declared artefacts while it runs; evaluate each on appearance / change.

    ``on_bad`` is called (once per artefact) when a verdict is ``bad`` — the
    container interface uses it to terminate the app when the run opted in.
    """

    def __init__(
        self,
        checks: list[Check],
        context: dict[str, Any],
        sink: CheckpointSink,
        *,
        run_id: str,
        node: str,
        subject: str,
        sequence: str | None = None,
        poll_interval: float = 15.0,
        on_bad: Callable[[Checkpoint], None] | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"checkpoints-{node}")
        self.checks = [c for c in checks if c.live]
        self.context = context
        self.sink = sink
        self.run_id, self.node, self.subject, self.sequence = run_id, node, subject, sequence
        self.poll_interval = poll_interval
        self.on_bad = on_bad
        self._stop_event = threading.Event()
        self._seen: dict[str, float] = {}
        self.results: list[Checkpoint] = []

    def stop(self) -> None:
        self._stop_event.set()

    def sweep(self, *, final: bool = False) -> list[Checkpoint]:
        """Evaluate every artefact that is new or changed since the last sweep."""
        produced: list[Checkpoint] = []
        import dataclasses
        for check in self.checks:
            artifacts = resolve_artifacts(check.artifact, self.context)
            many = any(ch in check.artifact for ch in _GLOB_CHARS)
            for artifact in artifacts:
                if not artifact.exists():
                    continue
                try:
                    mtime = artifact.stat().st_mtime
                except OSError:
                    continue
                # Skip files still being written (mtime within the last poll).
                if not final and time.time() - mtime < min(self.poll_interval, 5.0):
                    continue
                key = f"{check.step}|{artifact}"
                if self._seen.get(key) == mtime:
                    continue
                self._seen[key] = mtime
                # One check over several runs: each file gets its own record, same norms.
                effective = dataclasses.replace(check, step=f"{check.step}[{substep_label(artifact)}]", norms_key=check.key) if many else check
                cp = evaluate(effective, artifact, run_id=self.run_id, node=self.node,
                              subject=self.subject, sequence=self.sequence)
                self.sink.write(cp)
                self.results.append(cp)
                produced.append(cp)
                if cp.verdict == "bad" and self.on_bad is not None:
                    try:
                        self.on_bad(cp)
                    except Exception:
                        logger.exception("on_bad handler failed")
        return produced

    def run(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            try:
                self.sweep()
            except Exception:
                logger.exception("checkpoint sweep failed")


# ── thumbnails ────────────────────────────────────────────────────

def render_thumbnail(artifact: Path, *, size: int = 160) -> Path | None:
    """Mid-axial slice PNG next to the artefact, regenerated when the artefact is newer."""
    artifact = Path(artifact)
    if not artifact.exists():
        return None
    out = artifact.with_name(artifact.name + ".checkpoint.png")
    try:
        if out.exists() and out.stat().st_mtime >= artifact.stat().st_mtime:
            return out
    except OSError:
        pass
    try:
        import numpy as np
        from PIL import Image
        data, _ = _load_volume(artifact)
        if data.ndim == 4:
            data = data[..., 0]
        if data.ndim != 3:
            return None
        sl = np.asarray(data[:, :, data.shape[2] // 2], dtype="float64")
        nz = sl[sl != 0]
        hi = float(np.percentile(nz, 99.5)) if nz.size else 1.0
        lo = float(np.percentile(nz, 0.5)) if nz.size else 0.0
        norm = np.clip((sl - lo) / max(hi - lo, 1e-6), 0, 1)
        img = Image.fromarray((np.rot90(norm) * 255).astype("uint8"))
        img.thumbnail((size, size))
        img.save(out)
        return out
    except Exception as e:
        logger.debug("thumbnail for %s failed: %s", artifact, e)
        return None


def prune_parked(run_dir: Path | str) -> dict[str, int]:
    """Rewrite a run's ``checkpoints.jsonl`` and ``events.jsonl`` without the records
    of parked checks (and with live records trimmed). The originals are kept next to
    them as ``*.jsonl.parked`` the first time, so widening the allow-list later can
    restore them. Returns counts of removed records per file."""
    run_dir = Path(run_dir)
    removed = {"checkpoints": 0, "events": 0}
    cp = run_dir / CHECKPOINTS_FILENAME
    if cp.is_file():
        backup = cp.with_suffix(".jsonl.parked")
        if not backup.exists():
            backup.write_bytes(cp.read_bytes())
        kept = []
        for line in cp.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if is_parked_record(d):
                removed["checkpoints"] += 1
                continue
            kept.append(json.dumps(trim_record(d), default=str))
        cp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    ev = run_dir / "events.jsonl"
    if ev.is_file():
        backup = ev.with_suffix(".jsonl.parked")
        if not backup.exists():
            backup.write_bytes(ev.read_bytes())
        kept = []
        for line in ev.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                kept.append(line)
                continue
            if d.get("event") == "checkpoint":
                if is_parked_record(d):
                    removed["events"] += 1
                    continue
                d = trim_record(d)
                line = json.dumps(d, default=str)
            kept.append(line)
        ev.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed

