"""Build a freeview command from a stub FS subject directory."""

from __future__ import annotations

from fmriflow.server.routes.structural_qc import _build_freeview_command


def test_command_includes_only_existing_files(tmp_path):
    fs_subject = tmp_path / "sub-01"
    (fs_subject / "mri").mkdir(parents=True)
    (fs_subject / "surf").mkdir(parents=True)

    # Only create T1.mgz and lh.pial
    (fs_subject / "mri" / "T1.mgz").write_bytes(b"")
    (fs_subject / "surf" / "lh.pial").write_bytes(b"")

    cmd = _build_freeview_command(fs_subject)

    assert cmd.startswith("freeview")
    assert "T1.mgz" in cmd
    assert "lh.pial" in cmd
    # Files we didn't create must be absent
    assert "aseg.mgz" not in cmd
    assert "rh.pial" not in cmd
    assert "lh.white" not in cmd
    assert "brainmask.mgz" not in cmd


def test_empty_fs_dir_yields_bare_command(tmp_path):
    fs_subject = tmp_path / "sub-01"
    fs_subject.mkdir()
    cmd = _build_freeview_command(fs_subject)
    assert cmd == "freeview"
