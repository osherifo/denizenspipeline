"""Render a FreeSurfer flat patch as a clean flatmap image.

Autoflatten writes ``{hemi}.autoflatten.flat.patch.3d`` — a binary FreeSurfer
patch holding the flattened (x, y) position of every vertex that survived the
cuts — alongside a matplotlib QA figure. That QA figure bundles the patch
outline, a metric-distortion map and a histogram into one picture, so it is
useful for judging the flattening but is *not* a view of the cortex.

This module pairs the patch with the topology of the full surface to recover a
real triangle mesh, then renders just the cortex, shaded by any per-vertex
scalar FreeSurfer produced (curvature, thickness, sulcal depth, area). The
result is a transparent PNG per hemisphere that the UI can rotate, flip and
compose.

**Source of truth is the run's own patch**, never the pycortex store's
``flat_*.gii``. The store's copy can be a stale flattening with a different
vertex count, and it lives inside the container image rather than on the
mounted working directory, so it does not survive a rebuild. The patch sits in
the derivatives tree next to everything else the run produced.

Depends only on numpy + nibabel + matplotlib — not pycortex — so viewing a
flatmap does not require a populated pycortex store.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

HEMIS = ("lh", "rh")

# Surfaces to take face topology from, in preference order. Any surface of the
# same hemisphere shares vertex numbering, so any of these gives valid faces.
_TOPOLOGY_SURFACES = ("inflated", "white", "smoothwm", "orig")

# Per-vertex scalars FreeSurfer writes that are meaningful on a flatmap.
SCALARS = ("curv", "thickness", "sulc", "area")

PATCH_SUFFIX = ".autoflatten.flat.patch.3d"


class FlatMeshError(RuntimeError):
    """Raised when a flat patch cannot be turned into a mesh."""


@dataclass(frozen=True)
class FlatMesh:
    """A flattened cortical surface, compacted to the patch's own vertices."""

    hemi: str
    points: np.ndarray        # (n, 3) float32 — flattened, z = 0
    faces: np.ndarray         # (m, 3) int32 — indices into `points`
    vertex_ids: np.ndarray    # (n,) int64 — index of each point in the FULL surface

    @property
    def n_points(self) -> int:
        return int(self.points.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self.faces.shape[0])


# ── patch reading ────────────────────────────────────────────────────

def read_patch(path: Path | str) -> np.ndarray:
    """Read a binary FreeSurfer ``.patch.3d`` file.

    Returns a structured array with fields ``vert``, ``x``, ``y``, ``z``.
    Values are returned **raw**: ``vert`` is 1-based and its **sign encodes
    edge status** (negative = on the patch boundary). Decoding to a 0-based
    index is ``abs(vert) - 1``, done by :func:`build_flat_mesh` — getting it
    wrong silently produces an off-by-one mesh that still renders, so it is
    kept in one place rather than repeated at call sites.
    """
    path = Path(path)
    with open(path, "rb") as fp:
        header = fp.read(8)
        # Both fields are needed; a 4..7 byte file would otherwise reach
        # struct.unpack and raise struct.error, escaping this module's
        # error contract.
        if len(header) < 8:
            raise FlatMeshError(f"{path} is too short to be a patch file")
        _version, nverts = struct.unpack(">ii", header)
        data = np.frombuffer(
            fp.read(),
            dtype=[("vert", ">i4"), ("x", ">f4"), ("y", ">f4"), ("z", ">f4")],
        )
    if len(data) != nverts:
        raise FlatMeshError(
            f"{path}: header declares {nverts} vertices but the file holds {len(data)}"
        )
    return data


def _topology_path(surf_dir: Path, hemi: str) -> Path:
    for name in _TOPOLOGY_SURFACES:
        candidate = surf_dir / f"{hemi}.{name}"
        if candidate.is_file():
            return candidate
    raise FlatMeshError(
        f"no topology surface for {hemi} in {surf_dir} "
        f"(looked for: {', '.join(_TOPOLOGY_SURFACES)})"
    )


def patch_path(surf_dir: Path | str, hemi: str) -> Path:
    return Path(surf_dir) / f"{hemi}{PATCH_SUFFIX}"


# ── mesh construction ────────────────────────────────────────────────

def build_flat_mesh(surf_dir: Path | str, hemi: str) -> FlatMesh:
    """Build a compacted flat mesh for *hemi* from the run's patch.

    The mesh is compacted to the patch's own vertices — faces are renumbered —
    so a per-vertex scalar array lines up with it 1:1. Keeping the full
    surface's vertex count instead would leave thousands of unreferenced points
    sitting at the origin, dragging stray triangles into the middle of the
    render.
    """
    if hemi not in HEMIS:
        raise FlatMeshError(f"hemi must be one of {HEMIS}, got {hemi!r}")

    import nibabel.freesurfer.io as fsio

    surf_dir = Path(surf_dir)
    patch = read_patch(patch_path(surf_dir, hemi))
    surf_pts, polys = fsio.read_geometry(_topology_path(surf_dir, hemi))

    # 1-based, sign-encoded (see read_patch).
    vertex_ids = (np.abs(patch["vert"]).astype(np.int64) - 1)
    # Count from the surface's own vertex array. Deriving it from the faces
    # (polys.max() + 1) undercounts when a surface carries vertices no face
    # references, which would reject a perfectly valid patch.
    n_full = int(len(surf_pts))
    if vertex_ids.max() >= n_full:
        raise FlatMeshError(
            f"{hemi}: patch references vertex {vertex_ids.max()} but the surface "
            f"has {n_full} — patch and surface are from different runs"
        )

    # Keep faces whose three vertices all survived the cuts.
    in_patch = np.zeros(n_full, dtype=bool)
    in_patch[vertex_ids] = True
    faces_full = polys[in_patch[polys].all(axis=1)]

    # Compact: full-surface index -> position in `points`.
    remap = np.full(n_full, -1, dtype=np.int64)
    remap[vertex_ids] = np.arange(len(vertex_ids))
    faces = remap[faces_full].astype(np.int32)

    points = np.zeros((len(vertex_ids), 3), dtype=np.float32)
    points[:, 0] = patch["x"].astype(np.float32)
    points[:, 1] = patch["y"].astype(np.float32)
    # z stays 0 — this is a flat surface, and a non-zero z from the patch
    # would tilt it out of the viewing plane.

    logger.info(
        "flat mesh %s: %d vertices, %d faces (from %d surface faces)",
        hemi, len(points), len(faces), len(polys),
    )
    return FlatMesh(hemi=hemi, points=points, faces=faces, vertex_ids=vertex_ids)


def scalar_for_mesh(surf_dir: Path | str, mesh: FlatMesh, scalar: str) -> np.ndarray:
    """Load a FreeSurfer per-vertex scalar, subset to the mesh's vertices."""
    import nibabel.freesurfer.io as fsio

    if scalar not in SCALARS:
        raise FlatMeshError(f"scalar must be one of {SCALARS}, got {scalar!r}")
    path = Path(surf_dir) / f"{mesh.hemi}.{scalar}"
    if not path.is_file():
        raise FlatMeshError(f"no {scalar} file for {mesh.hemi}: {path}")

    values = fsio.read_morph_data(path)
    if mesh.vertex_ids.max() >= len(values):
        raise FlatMeshError(
            f"{scalar} has {len(values)} values but the patch references vertex "
            f"{mesh.vertex_ids.max()} — mismatched surfaces"
        )
    return values[mesh.vertex_ids].astype(np.float32)


def available_scalars(surf_dir: Path | str, hemi: str) -> list[str]:
    """Which per-vertex scalars this subject actually has on disk."""
    surf_dir = Path(surf_dir)
    return [s for s in SCALARS if (surf_dir / f"{hemi}.{s}").is_file()]


# ── rendering ────────────────────────────────────────────────────────

# Display defaults per scalar. Curvature and sulcal depth are shown the
# classic way — binarised into dark sulci / light gyri — because the
# continuous values are dominated by a few extreme vertices and render as a
# flat wash. Thickness and area are genuinely continuous, so they keep it.
_BINARISED = ("curv", "sulc")

# Two mid-greys for binarised curvature, matching the conventional flatmap.
_SULCUS_GREY = 0.38
_GYRUS_GREY = 0.72
_CONTINUOUS_RANGE: dict[str, tuple[float, float]] = {
    "thickness": (0.0, 5.0),
    "area": (0.0, 2.0),
}


def render_path(surf_dir: Path | str, hemi: str, scalar: str) -> Path:
    return Path(surf_dir) / f"{hemi}.autoflatten.flat.{scalar}.render.png"


def _is_stale(cache: Path, source: Path) -> bool:
    """True when *cache* is missing or older than *source*.

    Re-flattening rewrites the patch, so an mtime check keeps a cached render
    from silently outliving the geometry it came from. Compared in
    nanoseconds: at seconds resolution a patch rewritten inside the same tick
    as its render would read as up to date.
    """
    return (
        not cache.is_file()
        or cache.stat().st_mtime_ns < source.stat().st_mtime_ns
    )


def render_flat_png(
    surf_dir: Path | str,
    hemi: str,
    scalar: str = "curv",
    *,
    dpi: int = 200,
) -> Path:
    """Render the flattened cortex to a transparent PNG. Returns its path.

    Transparent so the two hemispheres can be overlapped and composed in the
    UI without opaque rectangles cutting into each other.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    surf_dir = Path(surf_dir)
    source = patch_path(surf_dir, hemi)
    if not source.is_file():
        raise FlatMeshError(f"no flat patch for {hemi}: {source}")

    out = render_path(surf_dir, hemi, scalar)
    if not _is_stale(out, source):
        return out

    mesh = build_flat_mesh(surf_dir, hemi)
    values = scalar_for_mesh(surf_dir, mesh, scalar)

    if scalar in _BINARISED:
        # Sign, not magnitude: positive curvature = sulcus. Rendered as two
        # mid-greys rather than black/white — the conventional flatmap look,
        # and it leaves headroom for a coloured overlay to sit on top.
        values = np.where(values > 0, _SULCUS_GREY, _GYRUS_GREY)
        cmap, vmin, vmax = "gray", 0.0, 1.0
    else:
        cmap = "viridis"
        vmin, vmax = _CONTINUOUS_RANGE.get(scalar, (float(values.min()), float(values.max())))

    tri = mtri.Triangulation(
        mesh.points[:, 0], mesh.points[:, 1], triangles=mesh.faces,
    )

    # Size the canvas to the patch's own aspect ratio so the cortex fills it
    # and the UI can rotate it without a lopsided bounding box.
    # np.ptp(arr), not arr.ptp() — the method was removed in NumPy 2.0.
    width = float(np.ptp(mesh.points[:, 0])) or 1.0
    height = float(np.ptp(mesh.points[:, 1])) or 1.0
    fig_w = 6.0
    fig = plt.figure(figsize=(fig_w, fig_w * height / width), dpi=dpi)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.tripcolor(tri, values, cmap=cmap, vmin=vmin, vmax=vmax, shading="gouraud")
    ax.set_aspect("equal")
    ax.axis("off")

    fig.savefig(out, transparent=True, dpi=dpi,
                bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    logger.info("rendered %s", out)
    return out
