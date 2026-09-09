"""Serving a preprocessing app's files to the browser, safely.

Shared by the subject-keyed structural-QC routes and the run-scoped node
routes: one safe-join, one suffix whitelist per kind of root, one FreeSurfer
subject-dir finder, one freeview command builder.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

# Files served from a FreeSurfer subject dir for in-browser viewing.
FS_ALLOWED_SUFFIXES = {
    ".nii", ".gz", ".mgz",
    ".pial", ".white", ".inflated", ".smoothwm",
    # Per-vertex scalar overlays for niivue mesh layers.
    ".curv", ".thickness", ".area",
    ".png", ".svg",
}

# Files served from an app's output dir to satisfy its HTML report's
# relative URLs (figures, embedded svg, etc.).
OUT_ALLOWED_SUFFIXES = {
    ".svg", ".png", ".jpg", ".jpeg", ".gif",
    ".html", ".htm", ".css", ".js", ".json",
    ".tsv", ".txt", ".nii", ".gz",
}

MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
}


def safe_join(root: Path, rel: str) -> Path:
    """Resolve ``root / rel`` and refuse to leave ``root``."""
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if not str(target).startswith(str(root_resolved) + "/") and target != root_resolved:
        raise HTTPException(403, "Path escapes root")
    return target


def serve_file(root: Path, rel: str, allowed: set[str], *, media_types: dict[str, str] | None = None) -> FileResponse:
    """A file under ``root`` by relative path, suffix-whitelisted on the
    *requested* name (so a symlink such as ``lh.pial -> lh.pial.T1`` passes)."""
    suffix = Path(rel).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(403, f"Suffix not allowed: {suffix}")
    target = safe_join(root, rel)
    if not target.is_file():
        raise HTTPException(404, f"File not found: {rel}")
    media = (media_types or MEDIA_TYPES).get(suffix, "application/octet-stream")
    return FileResponse(target, media_type=media)


def find_fs_subject_dir(fs_dir: str | Path | None, subject: str, output_dir: str | Path | None) -> Path | None:
    """The FreeSurfer subject directory: under ``fs_dir`` when given, else the
    common fmriprep layouts under ``output_dir``."""
    label = subject if subject.startswith("sub-") else f"sub-{subject}"
    bare = subject[4:] if subject.startswith("sub-") else subject
    if fs_dir:
        for name in (label, bare):
            cand = Path(fs_dir) / name
            if cand.is_dir():
                return cand
    if output_dir:
        out = Path(output_dir)
        for base in (out / "sourcedata" / "freesurfer", out / "freesurfer", out.parent / "freesurfer"):
            for name in (label, bare):
                cand = base / name
                if cand.is_dir():
                    return cand
    return None


def build_freeview_command(
    fs_subject_dir: Path,
    *,
    drawing_path: Path | None = None,
    ras: tuple[float, float, float] | None = None,
) -> str:
    """Build a freeview command using the files that actually exist."""
    parts: list[str] = ["freeview"]
    mri = fs_subject_dir / "mri"
    surf = fs_subject_dir / "surf"

    volumes = [
        ("T1.mgz", ""),
        ("brainmask.mgz", ":colormap=heat:opacity=0.3"),
        ("aseg.mgz", ":colormap=lut:opacity=0.3"),
    ]
    for name, opts in volumes:
        p = mri / name
        if p.is_file():
            parts.append(f"-v {p}{opts}")

    if drawing_path and drawing_path.is_file():
        parts.append(f"-v {drawing_path}:colormap=lut:opacity=0.5")

    surfaces = [
        ("lh.pial", ":edgecolor=red"),
        ("rh.pial", ":edgecolor=red"),
        ("lh.white", ":edgecolor=yellow"),
        ("rh.white", ":edgecolor=yellow"),
    ]
    for name, opts in surfaces:
        p = surf / name
        if p.is_file():
            parts.append(f"-f {p}{opts}")

    if ras:
        parts.append(f"-c {ras[0]:.1f} {ras[1]:.1f} {ras[2]:.1f}")

    return " \\\n  ".join(parts)


def save_drawing(fs_subject_dir: Path, data: bytes, ras: tuple[float, float, float]) -> dict:
    """Store a QC drawing NIfTI in the subject's ``mri/`` and return a
    freeview command centred on it."""
    dest = fs_subject_dir / "mri" / "qc_drawing.nii"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info("Saved QC drawing (%d bytes) -> %s", len(data), dest)
    centre = ras if any(v != 0 for v in ras) else None
    return {"saved": True, "path": str(dest), "command": build_freeview_command(fs_subject_dir, drawing_path=dest, ras=centre)}
