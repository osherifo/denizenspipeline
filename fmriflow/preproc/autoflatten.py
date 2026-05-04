"""Autoflatten integration — cortical surface flattening post-step.

Wraps the ``autoflatten`` package to create flatmaps from FreeSurfer
surfaces and optionally import them into pycortex.

This runs *after* fmriprep (which produces FreeSurfer reconall outputs)
and *before* analysis (which needs pycortex for visualization).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Common flat patch naming patterns
_FLAT_PATTERNS = [
    "{hemi}.autoflatten.flat.patch.3d",
    "{hemi}.full.flat.patch.3d",
    "{hemi}.flat.patch.3d",
]

VALID_HEMISPHERES = ("lh", "rh", "both")
VALID_BACKENDS = ("pyflatten", "freesurfer")


# ── Config ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AutoflattenConfig:
    """Configuration for autoflatten."""

    subjects_dir: str
    subject: str
    hemispheres: str = "both"
    parallel: bool = True
    backend: str = "pyflatten"
    overwrite: bool = False
    template_file: str | None = None
    output_dir: str | None = None

    # Pre-computed flat patches — skip flattening, just import
    flat_patch_lh: str | None = None
    flat_patch_rh: str | None = None

    # pycortex import
    import_to_pycortex: bool = True
    pycortex_surface_name: str | None = None

    def validate(self) -> list[str]:
        """Return a list of validation errors."""
        errors: list[str] = []

        subjects_path = Path(self.subjects_dir)
        if not subjects_path.is_dir():
            errors.append(f"Subjects directory not found: {self.subjects_dir}")

        subject_path = subjects_path / self.subject
        if subjects_path.is_dir() and not subject_path.is_dir():
            errors.append(
                f"Subject directory not found: {subject_path}"
            )

        if self.hemispheres not in VALID_HEMISPHERES:
            errors.append(
                f"Invalid hemispheres '{self.hemispheres}'. "
                f"Must be one of: {', '.join(VALID_HEMISPHERES)}"
            )

        if self.backend not in VALID_BACKENDS:
            errors.append(
                f"Invalid backend '{self.backend}'. "
                f"Must be one of: {', '.join(VALID_BACKENDS)}"
            )

        if self.flat_patch_lh and not Path(self.flat_patch_lh).is_file():
            errors.append(f"Pre-computed LH patch not found: {self.flat_patch_lh}")
        if self.flat_patch_rh and not Path(self.flat_patch_rh).is_file():
            errors.append(f"Pre-computed RH patch not found: {self.flat_patch_rh}")

        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoflattenConfig:
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# ── Result / Record ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class AutoflattenResult:
    """Result of an autoflatten run."""

    subject: str
    hemispheres: list[str]
    flat_patches: dict[str, str]
    visualizations: dict[str, str]
    pycortex_surface: str | None
    source: str  # "autoflatten", "precomputed", "import_only"
    elapsed_s: float


@dataclass(frozen=True)
class AutoflattenRecord:
    """Record stored in the preprocessing manifest."""

    source: str
    backend: str | None
    hemispheres: list[str]
    flat_patches: dict[str, str]
    visualizations: dict[str, str]
    pycortex_surface: str | None
    template: str | None
    created: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoflattenRecord:
        return cls(**data)

    @classmethod
    def from_result(
        cls, result: AutoflattenResult, config: AutoflattenConfig,
    ) -> AutoflattenRecord:
        from fmriflow.preproc.manifest import now_iso
        return cls(
            source=result.source,
            backend=config.backend if result.source == "autoflatten" else None,
            hemispheres=result.hemispheres,
            flat_patches=result.flat_patches,
            visualizations=result.visualizations,
            pycortex_surface=result.pycortex_surface,
            template=config.template_file or "default",
            created=now_iso(),
        )


# ── Detection ───────────────────────────────────────────────────────────


def detect_existing_flats(subjects_dir: str, subject: str) -> dict[str, Path]:
    """Check whether flat patches already exist for a subject.

    Scans ``surf/`` for common flat patch naming patterns.

    Returns a dict of found hemispheres, e.g. ``{"lh": Path(...), "rh": Path(...)}``.
    Missing hemispheres are omitted (not None-valued).
    """
    surf_dir = Path(subjects_dir) / subject / "surf"
    found: dict[str, Path] = {}

    if not surf_dir.is_dir():
        return found

    for hemi in ("lh", "rh"):
        for pattern in _FLAT_PATTERNS:
            candidate = surf_dir / pattern.format(hemi=hemi)
            if candidate.is_file():
                found[hemi] = candidate
                break

    return found


def check_surfaces(subjects_dir: str, subject: str) -> dict[str, bool]:
    """Check which FreeSurfer surfaces exist for a subject.

    Returns a dict of checks, e.g.::

        {"lh.inflated": True, "rh.inflated": True, ...}
    """
    surf_dir = Path(subjects_dir) / subject / "surf"
    checks: dict[str, bool] = {}

    for hemi in ("lh", "rh"):
        for surface in ("inflated", "smoothwm", "white", "pial"):
            name = f"{hemi}.{surface}"
            checks[name] = (surf_dir / name).is_file()

    return checks


def check_autoflatten_available() -> tuple[bool, str]:
    """Check if the autoflatten package is installed."""
    if shutil.which("autoflatten") is not None:
        return True, "autoflatten CLI found"
    try:
        import autoflatten  # noqa: F401
        return True, "autoflatten package importable"
    except ImportError:
        return False, (
            "autoflatten not found. Install with: "
            "pip install autoflatten"
        )


def check_pycortex_available() -> tuple[bool, str]:
    """Check if pycortex is installed."""
    try:
        import cortex  # noqa: F401
        return True, "pycortex available"
    except ImportError:
        return False, "pycortex not found. Install with: pip install pycortex"


# ── Core execution ──────────────────────────────────────────────────────


def run_autoflatten(config: AutoflattenConfig) -> AutoflattenResult:
    """Run autoflatten on a subject's FreeSurfer outputs.

    Execution flow:
    1. If ``flat_patch_lh`` / ``flat_patch_rh`` are provided → import only
    2. If flat patches already exist and ``overwrite`` is False → use existing
    3. Otherwise → run autoflatten to generate flat patches
    4. Optionally import into pycortex
    """
    start = time.time()
    hemis = _resolve_hemispheres(config.hemispheres)

    # Determine source and flat patch paths
    flat_patches, source = _resolve_flat_patches(config, hemis)

    # Run autoflatten if needed
    if source == "autoflatten":
        flat_patches, visualizations = _execute_autoflatten(config, hemis)
    else:
        # Pre-computed or import_only — no visualizations from autoflatten
        visualizations = {}

    # Import to pycortex
    pycortex_surface = None
    if config.import_to_pycortex and flat_patches:
        pycortex_surface = _do_pycortex_import(config, flat_patches)

    elapsed = time.time() - start

    return AutoflattenResult(
        subject=config.subject,
        hemispheres=list(flat_patches.keys()),
        flat_patches={h: str(p) for h, p in flat_patches.items()},
        visualizations={h: str(p) for h, p in visualizations.items()},
        pycortex_surface=pycortex_surface,
        source=source,
        elapsed_s=elapsed,
    )


def import_flat_patches(
    subjects_dir: str,
    subject: str,
    flat_patch_lh: str | Path,
    flat_patch_rh: str | Path,
    pycortex_surface_name: str | None = None,
) -> str | None:
    """Import pre-computed flat patches into pycortex.

    Convenience function for the ``fmriflow autoflatten import`` CLI.
    """
    config = AutoflattenConfig(
        subjects_dir=subjects_dir,
        subject=subject,
        flat_patch_lh=str(flat_patch_lh),
        flat_patch_rh=str(flat_patch_rh),
        import_to_pycortex=True,
        pycortex_surface_name=pycortex_surface_name,
    )
    flat_patches = {
        "lh": Path(flat_patch_lh),
        "rh": Path(flat_patch_rh),
    }
    return _do_pycortex_import(config, flat_patches)


# ── Private helpers ─────────────────────────────────────────────────────


def _pycortex_subject_list(cortex) -> list[str]:
    """Return the names of subjects registered in pycortex.

    pycortex removed ``cortex.db.get_list()`` in the 1.2.x series in
    favour of the underlying ``cortex.db.subjects`` dict. We try the
    old API first (some installs may still have it) then fall back.
    """
    get_list = getattr(cortex.db, "get_list", None)
    if callable(get_list):
        try:
            return list(get_list())
        except Exception:
            pass
    subjects = getattr(cortex.db, "subjects", None)
    if subjects is not None:
        try:
            return list(subjects)
        except Exception:
            pass
    return []


def _resolve_hemispheres(hemispheres: str) -> list[str]:
    if hemispheres == "both":
        return ["lh", "rh"]
    return [hemispheres]


def _resolve_flat_patches(
    config: AutoflattenConfig, hemis: list[str],
) -> tuple[dict[str, Path], str]:
    """Determine whether to run autoflatten, use pre-computed, or import only.

    Returns (flat_patches_dict, source_label).
    """
    # Case 1: explicit pre-computed paths provided
    explicit: dict[str, Path] = {}
    if config.flat_patch_lh:
        explicit["lh"] = Path(config.flat_patch_lh)
    if config.flat_patch_rh:
        explicit["rh"] = Path(config.flat_patch_rh)

    if explicit:
        logger.info(
            "Using pre-computed flat patches: %s",
            {h: str(p) for h, p in explicit.items()},
        )
        return explicit, "import_only"

    # Case 2: detect existing flat patches
    if not config.overwrite:
        existing = detect_existing_flats(config.subjects_dir, config.subject)
        if all(h in existing for h in hemis):
            logger.info(
                "Flat patches already exist for %s (use overwrite=True to re-flatten): %s",
                config.subject,
                {h: str(p) for h, p in existing.items()},
            )
            return {h: existing[h] for h in hemis}, "precomputed"

    # Case 3: need to run autoflatten
    return {}, "autoflatten"


def _execute_autoflatten(
    config: AutoflattenConfig, hemis: list[str],
) -> tuple[dict[str, Path], dict[str, Path]]:
    """Run the autoflatten CLI and return flat patches + visualizations."""
    cmd = _build_autoflatten_command(config)
    logger.info("Running autoflatten: %s", " ".join(cmd))

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    tail: list[str] = []
    for line in proc.stdout:
        stripped = line.rstrip()
        logger.info("[autoflatten] %s", stripped)
        tail.append(stripped)
        if len(tail) > 50:
            tail.pop(0)
    proc.wait()

    if proc.returncode != 0:
        last_output = "\n".join(tail[-20:])
        raise RuntimeError(
            f"autoflatten exited with code {proc.returncode}\n"
            f"Last output:\n{last_output}"
        )

    # Collect output files
    output_dir = Path(config.output_dir) if config.output_dir else (
        Path(config.subjects_dir) / config.subject / "surf"
    )

    flat_patches: dict[str, Path] = {}
    visualizations: dict[str, Path] = {}

    for hemi in hemis:
        patch = output_dir / f"{hemi}.autoflatten.flat.patch.3d"
        if patch.is_file():
            flat_patches[hemi] = patch

        viz = output_dir / f"{hemi}.autoflatten.flat.patch.png"
        if viz.is_file():
            visualizations[hemi] = viz

    if not flat_patches:
        raise RuntimeError(
            f"autoflatten completed but no flat patches found in {output_dir}"
        )

    return flat_patches, visualizations


def _build_autoflatten_command(config: AutoflattenConfig) -> list[str]:
    """Build the autoflatten CLI command."""
    subject_path = str(Path(config.subjects_dir) / config.subject)
    cmd = ["autoflatten", subject_path]

    if config.hemispheres != "both":
        cmd += ["--hemispheres", config.hemispheres]

    if config.parallel:
        cmd.append("--parallel")

    if config.backend != "pyflatten":
        cmd += ["--backend", config.backend]

    if config.overwrite:
        cmd.append("--overwrite")

    if config.template_file:
        cmd += ["--template-file", config.template_file]

    if config.output_dir:
        cmd += ["--output-dir", config.output_dir]

    return cmd


def _do_pycortex_import(
    config: AutoflattenConfig,
    flat_patches: dict[str, Path],
) -> str | None:
    """Import FreeSurfer surfaces + flat patches into pycortex."""
    try:
        import cortex
        import cortex.freesurfer
    except ImportError:
        logger.warning(
            "pycortex not installed — skipping pycortex import. "
            "Install with: pip install pycortex"
        )
        return None

    cx_name = config.pycortex_surface_name or f"{config.subject}fs"

    # Check if subject already exists in pycortex
    existing_subjects = _pycortex_subject_list(cortex)
    if cx_name not in existing_subjects:
        logger.info(
            "Importing FreeSurfer subject '%s' into pycortex as '%s'",
            config.subject, cx_name,
        )
        try:
            cortex.freesurfer.import_subj(
                fs_subject=config.subject,
                cx_subject=cx_name,
                freesurfer_subject_dir=config.subjects_dir,
            )
        except Exception as e:
            logger.error("Failed to import FreeSurfer subject: %s", e)
            return None
    else:
        logger.info(
            "pycortex subject '%s' already exists, skipping surface import",
            cx_name,
        )

    # Import flat patches
    lh_patch = flat_patches.get("lh")
    rh_patch = flat_patches.get("rh")

    if lh_patch and rh_patch:
        logger.info("Importing flat patches into pycortex subject '%s'", cx_name)
        try:
            cortex.freesurfer.import_flat(
                subject=cx_name,
                patch=str(lh_patch),
                hemis=("lh", "rh"),
                cx_subject=cx_name,
                flat_type="autoflatten",
            )
        except TypeError:
            # Older pycortex API — try positional args
            try:
                cortex.freesurfer.import_flat(
                    cx_name, str(lh_patch), str(rh_patch),
                )
            except Exception as e:
                logger.error("Failed to import flat patches: %s", e)
                return None
        except Exception as e:
            logger.error("Failed to import flat patches: %s", e)
            return None
    else:
        logger.warning(
            "Cannot import flat patches — need both lh and rh, got: %s",
            list(flat_patches.keys()),
        )
        return None

    logger.info("pycortex import complete: subject='%s'", cx_name)
    return cx_name
