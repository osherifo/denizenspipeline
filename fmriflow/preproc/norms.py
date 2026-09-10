"""Hard norms for preprocessing checkpoints — one reviewable table.

Each entry names a checkpoint *step* and, per metric, a bound that marks
the result ``bad`` (``hard``) and optionally an earlier bound that marks
it ``suspicious`` (``soft``). Bounds are ``(op, value)`` with ``op`` one
of ``<``, ``<=``, ``>``, ``>=``, ``between`` (value = ``(lo, hi)``).

Sequence-specific overrides use ``"<step>@<sequence>"`` keys and are
merged over the base entry by :func:`norms_for` — an MP2RAGE UNI and an
MPRAGE do not share an intensity profile, but they do share the
"a normalised volume must not collapse to one value" rule.
"""

from __future__ import annotations

from typing import Any

Bound = tuple[str, Any]
StepNorms = dict[str, dict[str, Bound]]   # {"hard": {...}, "soft": {...}}

# The MP2RAGE incident: nu.mgz / T1.mgz had 70–92 unique values with 67–84 %
# of non-zero voxels sitting on one value. A healthy FreeSurfer volume has
# ~200+ unique values and a modal fraction well under 0.3.
_NORMALISED_VOLUME: StepNorms = {
    "hard": {"modal_fraction": ("<", 0.50), "n_unique": (">", 100)},
    "soft": {"modal_fraction": ("<", 0.30), "n_unique": (">", 200)},
}

HARD_NORMS: dict[str, StepNorms] = {
    "orig.mgz": {
        "hard": {"n_unique": (">", 50)},
        "soft": {"modal_fraction": ("<", 0.50)},
    },
    "nu.mgz": _NORMALISED_VOLUME,
    "T1.mgz": _NORMALISED_VOLUME,
    "brainmask.mgz": {
        "hard": {"brain_volume_cm3": ("between", (700.0, 2200.0))},
        "soft": {"brain_volume_cm3": ("between", (900.0, 1900.0))},
    },
    "wm.mgz": {
        # Healthy WM ≈ 400–600 cm³; the MP2RAGE failure produced 1285.
        "hard": {"wm_volume_cm3": ("between", (250.0, 900.0))},
        "soft": {"wm_volume_cm3": ("between", (350.0, 700.0))},
    },
    "lh.white": {"hard": {"n_defects": ("<", 150)}, "soft": {"n_defects": ("<", 60)}},
    "rh.white": {"hard": {"n_defects": ("<", 150)}, "soft": {"n_defects": ("<", 60)}},
    "lh.thickness": {
        "hard": {"mean_mm": ("between", (1.8, 3.5)), "zero_fraction": ("<", 0.05)},
        "soft": {"mean_mm": ("between", (2.2, 3.0)), "zero_fraction": ("<", 0.02)},
    },
    "rh.thickness": {
        "hard": {"mean_mm": ("between", (1.8, 3.5)), "zero_fraction": ("<", 0.05)},
        "soft": {"mean_mm": ("between", (2.2, 3.0)), "zero_fraction": ("<", 0.02)},
    },
    "aseg.stats": {
        "hard": {"etiv_cm3": ("between", (900.0, 2200.0))},
        "soft": {"etiv_cm3": ("between", (1100.0, 1900.0))},
    },
    # Generic per-output checks attached to every nifti output port.
    "output": {
        "hard": {"exists": ("==", True), "size_bytes": (">", 0)},
        "soft": {"nonzero_fraction": (">", 0.01)},
    },
    "bold_output": {
        "hard": {"exists": ("==", True), "is_4d": ("==", True), "n_trs": (">", 1)},
        "soft": {"nonzero_fraction": (">", 0.01)},
    },
}


# ── user overlay ($FMRIFLOW_HOME/configs/norms.yaml) ────────────────
#
# Same shape as HARD_NORMS, bounds written as [op, value] (or
# ["between", [lo, hi]]). Merged over the built-ins metric by metric, so a
# file that sets only `lh.thickness: {soft: {mean_mm: [between, [2.0, 3.2]]}}`
# changes just that bound. Re-read when the file changes.

USER_NORMS_FILENAME = "norms.yaml"
_user_cache: tuple[float, dict[str, StepNorms]] | None = None


def user_norms_path():
    from fmriflow.core.paths import configs_root
    return configs_root() / USER_NORMS_FILENAME


def _bound(b: Any) -> Bound:
    if isinstance(b, (list, tuple)) and len(b) == 2:
        op, val = b
        if op == "between" and isinstance(val, (list, tuple)):
            val = (float(val[0]), float(val[1]))
        return (str(op), val)
    raise ValueError(f"bad bound {b!r}: expected [op, value]")


def parse_norms(data: Any) -> dict[str, StepNorms]:
    """Validate a YAML/JSON norms mapping into the internal shape."""
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError("norms must be a mapping of step -> {hard, soft}")
    out: dict[str, StepNorms] = {}
    for step, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{step}: expected {{hard, soft}}")
        row: StepNorms = {"hard": {}, "soft": {}}
        for kind in ("hard", "soft"):
            for metric, b in (entry.get(kind) or {}).items():
                row[kind][str(metric)] = _bound(b)
        out[str(step)] = row
    return out


def load_user_norms() -> dict[str, StepNorms]:
    global _user_cache
    try:
        path = user_norms_path()
    except Exception:
        return {}
    if not path.is_file():
        _user_cache = None
        return {}
    mtime = path.stat().st_mtime
    if _user_cache and _user_cache[0] == mtime:
        return _user_cache[1]
    import yaml
    try:
        parsed = parse_norms(yaml.safe_load(path.read_text()) or {})
    except Exception as e:  # a broken file must not take preprocessing down
        import logging
        logging.getLogger(__name__).warning("ignoring %s: %s", path, e)
        parsed = {}
    _user_cache = (mtime, parsed)
    return parsed


def save_user_norms(data: dict[str, Any]) -> None:
    """Validate and write the overlay; an empty mapping removes the file."""
    parsed = parse_norms(data)
    path = user_norms_path()
    if not parsed:
        if path.is_file():
            path.unlink()
        return
    import yaml
    dump = {step: {k: {m: [op, list(v) if isinstance(v, tuple) else v] for m, (op, v) in bounds.items()}
                   for k, bounds in row.items() if bounds}
            for step, row in parsed.items()}
    path.write_text(yaml.safe_dump(dump, sort_keys=True))


def effective_norms() -> dict[str, StepNorms]:
    """Built-ins with the user overlay merged in, metric by metric."""
    merged: dict[str, StepNorms] = {k: {"hard": dict(v.get("hard", {})), "soft": dict(v.get("soft", {}))} for k, v in HARD_NORMS.items()}
    for step, row in load_user_norms().items():
        dst = merged.setdefault(step, {"hard": {}, "soft": {}})
        dst["hard"].update(row.get("hard", {}))
        dst["soft"].update(row.get("soft", {}))
    return merged


def norms_table() -> list[dict[str, Any]]:
    """Flat rows for the UI: one per (step, kind, metric), marking user overrides."""
    user = load_user_norms()
    rows = []
    for step, row in sorted(effective_norms().items()):
        for kind in ("hard", "soft"):
            for metric, (op, val) in sorted(row.get(kind, {}).items()):
                overridden = metric in (user.get(step, {}).get(kind) or {})
                builtin = HARD_NORMS.get(step, {}).get(kind, {}).get(metric)
                rows.append({
                    "step": step, "kind": kind, "metric": metric, "op": op,
                    "value": list(val) if isinstance(val, tuple) else val,
                    "source": "user" if overridden else "builtin",
                    "builtin": [builtin[0], list(builtin[1]) if isinstance(builtin[1], tuple) else builtin[1]] if builtin else None,
                })
    return rows


def norms_for(step: str, sequence: str | None = None) -> StepNorms:
    """Norms for ``step`` (built-ins + user overlay), with ``step@sequence``
    overrides merged on top."""
    table = effective_norms()
    base = table.get(step, {"hard": {}, "soft": {}})
    out: StepNorms = {"hard": dict(base.get("hard", {})), "soft": dict(base.get("soft", {}))}
    if sequence:
        override = table.get(f"{step}@{sequence}")
        if override:
            out["hard"].update(override.get("hard", {}))
            out["soft"].update(override.get("soft", {}))
    return out
