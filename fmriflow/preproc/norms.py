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


def norms_for(step: str, sequence: str | None = None) -> StepNorms:
    """Base norms for ``step``, with ``step@sequence`` overrides merged on top."""
    base = HARD_NORMS.get(step, {"hard": {}, "soft": {}})
    out: StepNorms = {"hard": dict(base.get("hard", {})), "soft": dict(base.get("soft", {}))}
    if sequence:
        override = HARD_NORMS.get(f"{step}@{sequence}")
        if override:
            out["hard"].update(override.get("hard", {}))
            out["soft"].update(override.get("soft", {}))
    return out
