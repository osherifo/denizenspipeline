"""Tests for turning a FreeSurfer flat patch into a renderable mesh.

The subtle part is the patch index encoding: entries are 1-based and their
SIGN marks boundary vertices. Getting that wrong yields an off-by-one mesh
that still renders plausibly, so it is asserted directly.
"""

import struct

import numpy as np
import pytest

from fmriflow.preproc import flat_mesh
from fmriflow.preproc.flat_mesh import (
    FlatMeshError,
    build_flat_mesh,
    read_patch,
    scalar_for_mesh,
)

nb = pytest.importorskip("nibabel")
import nibabel.freesurfer.io as fsio  # noqa: E402


def _write_patch(path, vert_ids, xs, ys, *, negate_first=True):
    """Write a binary patch. vert_ids are 0-based; stored 1-based, sign-encoded."""
    stored = []
    for i, v in enumerate(vert_ids):
        one_based = v + 1
        # Sign marks boundary vertices — exercise both branches.
        stored.append(-one_based if (negate_first and i == 0) else one_based)
    with open(path, "wb") as fp:
        fp.write(struct.pack(">i", -1))
        fp.write(struct.pack(">i", len(stored)))
        for v, x, y in zip(stored, xs, ys):
            fp.write(struct.pack(">i", int(v)))
            fp.write(struct.pack(">f", float(x)))
            fp.write(struct.pack(">f", float(y)))
            fp.write(struct.pack(">f", 0.0))


@pytest.fixture
def surf(tmp_path):
    """A 6-vertex surface; the patch keeps 5 of them (vertex 5 is cut away)."""
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [1, 1, 0], [2, 0, 0], [9, 9, 9],
    ], dtype=np.float32)
    polys = np.array([
        [0, 1, 2],
        [1, 3, 2],
        [1, 4, 3],
        [3, 4, 5],   # touches the cut-away vertex 5 -> must be dropped
    ], dtype=np.int32)
    d = tmp_path / "surf"
    d.mkdir()
    fsio.write_geometry(str(d / "lh.inflated"), pts, polys)

    kept = [0, 1, 2, 3, 4]
    _write_patch(d / f"lh{flat_mesh.PATCH_SUFFIX}", kept,
                 xs=[0, 10, 0, 10, 20], ys=[0, 0, 10, 10, 0])

    fsio.write_morph_data(str(d / "lh.curv"), np.arange(6, dtype=np.float32))
    fsio.write_morph_data(str(d / "lh.thickness"), np.full(6, 2.5, dtype=np.float32))
    return d


# ── patch parsing ───────────────────────────────────────────────────


def test_read_patch_preserves_sign_encoding(surf):
    data = read_patch(surf / f"lh{flat_mesh.PATCH_SUFFIX}")

    assert len(data) == 5
    # First entry was written negative (boundary marker) and must stay negative
    # — decoding happens in build_flat_mesh, not here.
    assert data["vert"][0] < 0
    assert data["vert"][1] > 0


def test_read_patch_rejects_a_truncated_file(tmp_path):
    p = tmp_path / "bad.patch.3d"
    p.write_bytes(b"\x00\x00")
    with pytest.raises(FlatMeshError, match="too short"):
        read_patch(p)


def test_read_patch_rejects_a_count_mismatch(tmp_path):
    p = tmp_path / "bad.patch.3d"
    with open(p, "wb") as fp:
        fp.write(struct.pack(">i", -1))
        fp.write(struct.pack(">i", 99))       # claims 99...
        fp.write(struct.pack(">ifff", 1, 0.0, 0.0, 0.0))  # ...supplies 1
    with pytest.raises(FlatMeshError, match="declares 99"):
        read_patch(p)


# ── mesh construction ───────────────────────────────────────────────


def test_builds_a_compacted_mesh(surf):
    mesh = build_flat_mesh(surf, "lh")

    assert mesh.n_points == 5           # vertex 5 was cut away
    assert mesh.faces.shape[1] == 3
    # The face touching the cut-away vertex must be dropped.
    assert mesh.n_faces == 3
    # Compacted: every face index addresses `points`, not the full surface.
    assert mesh.faces.max() < mesh.n_points


def test_index_decoding_is_off_by_one_safe(surf):
    """abs(vert) - 1: the sign is a flag, and the values are 1-based."""
    mesh = build_flat_mesh(surf, "lh")

    assert mesh.vertex_ids.tolist() == [0, 1, 2, 3, 4]
    # Point 0 came from the negatively-stored (boundary) entry and must still
    # carry that vertex's flat coordinates.
    assert mesh.points[0].tolist() == [0.0, 0.0, 0.0]
    assert mesh.points[4].tolist() == [20.0, 0.0, 0.0]


def test_flat_mesh_is_planar(surf):
    assert np.all(build_flat_mesh(surf, "lh").points[:, 2] == 0)


def test_rejects_a_patch_from_a_different_surface(surf):
    """A patch referencing vertices the surface lacks is a hard error."""
    _write_patch(surf / f"lh{flat_mesh.PATCH_SUFFIX}", [0, 1, 500],
                 xs=[0, 1, 2], ys=[0, 1, 2])
    with pytest.raises(FlatMeshError, match="different runs"):
        build_flat_mesh(surf, "lh")


def test_rejects_a_bad_hemi(surf):
    with pytest.raises(FlatMeshError, match="hemi must be"):
        build_flat_mesh(surf, "both")


def test_missing_topology_surface_is_reported(tmp_path):
    d = tmp_path / "surf"
    d.mkdir()
    _write_patch(d / f"lh{flat_mesh.PATCH_SUFFIX}", [0], xs=[0], ys=[0])
    with pytest.raises(FlatMeshError, match="no topology surface"):
        build_flat_mesh(d, "lh")


# ── scalars ─────────────────────────────────────────────────────────


def test_scalar_is_subset_to_the_mesh(surf):
    mesh = build_flat_mesh(surf, "lh")

    curv = scalar_for_mesh(surf, mesh, "curv")

    # One value per MESH vertex, not per surface vertex — the renderer
    # colours triangles by these, so a length mismatch would be fatal.
    assert len(curv) == mesh.n_points == 5
    assert curv.tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]  # vertex 5 excluded


def test_unknown_scalar_rejected(surf):
    mesh = build_flat_mesh(surf, "lh")
    with pytest.raises(FlatMeshError, match="scalar must be"):
        scalar_for_mesh(surf, mesh, "bogus")


def test_available_scalars_reflects_disk(surf):
    found = flat_mesh.available_scalars(surf, "lh")
    assert "curv" in found and "thickness" in found
    assert "sulc" not in found       # not written by the fixture


# ── rendering + caching ─────────────────────────────────────────────


def test_renders_a_png(surf):
    out = flat_mesh.render_flat_png(surf, "lh", "curv")

    assert out.is_file()
    assert out.suffix == ".png"
    # A real image, not an empty file.
    assert out.stat().st_size > 0
    from PIL import Image
    with Image.open(out) as im:
        assert im.width > 10 and im.height > 10
        # Transparent, so hemispheres can be composed without opaque boxes.
        assert im.mode in ("RGBA", "LA")


def test_render_cache_is_reused_then_invalidated(surf):
    out = flat_mesh.render_flat_png(surf, "lh", "curv")
    first = out.stat().st_mtime_ns

    flat_mesh.render_flat_png(surf, "lh", "curv")
    assert out.stat().st_mtime_ns == first, "should reuse the cached render"

    # Re-flattening rewrites the patch; a cached render must not outlive it.
    import os
    patch = surf / f"lh{flat_mesh.PATCH_SUFFIX}"
    future = out.stat().st_mtime + 100
    os.utime(patch, (future, future))

    flat_mesh.render_flat_png(surf, "lh", "curv")
    assert out.stat().st_mtime_ns != first, "a newer patch must invalidate the render"


def test_each_scalar_gets_its_own_render(surf):
    curv = flat_mesh.render_flat_png(surf, "lh", "curv")
    thick = flat_mesh.render_flat_png(surf, "lh", "thickness")

    assert curv != thick
    assert curv.is_file() and thick.is_file()


def test_missing_patch_is_reported(tmp_path):
    d = tmp_path / "surf"
    d.mkdir()
    with pytest.raises(FlatMeshError, match="no flat patch"):
        flat_mesh.render_flat_png(d, "lh", "curv")
