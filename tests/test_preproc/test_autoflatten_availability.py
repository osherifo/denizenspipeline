"""The autoflatten availability check must reflect what the runner needs.

``_build_autoflatten_command`` always shells out to the ``autoflatten``
console script. The check used to accept a merely importable package, so
the doctor reported healthy on a machine where the CLI was not on PATH —
and the failure only surfaced as a bare ``FileNotFoundError`` after
preprocessing had already run for hours.
"""

import sys

from fmriflow.preproc.autoflatten import (
    AutoflattenConfig,
    _build_autoflatten_command,
    check_autoflatten_available,
)


def test_available_when_the_cli_is_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/autoflatten")

    ok, detail = check_autoflatten_available()

    assert ok is True
    assert "CLI" in detail


def test_unavailable_when_only_importable(monkeypatch):
    """An importable package the runner cannot invoke is not 'available'."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setitem(sys.modules, "autoflatten", object())

    ok, detail = check_autoflatten_available()

    assert ok is False
    assert "PATH" in detail


def test_unavailable_when_not_installed_at_all(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setitem(sys.modules, "autoflatten", None)  # forces ImportError

    ok, detail = check_autoflatten_available()

    assert ok is False
    assert "pip install autoflatten" in detail


def test_runner_invokes_the_cli_by_name():
    """Pins the assumption the check above depends on."""
    cmd = _build_autoflatten_command(
        AutoflattenConfig(subjects_dir="/fs", subject="sub-01"),
    )

    assert cmd[0] == "autoflatten"
    assert cmd[1] == "run"


def test_subprocess_gets_subjects_dir_in_its_environment(monkeypatch, tmp_path):
    """FreeSurfer tools resolve subjects via $SUBJECTS_DIR, not the argv path.

    Without this the label-mapping step looks under
    $FREESURFER_HOME/subjects and fails on every label.
    """
    import subprocess

    from fmriflow.server.services import autoflatten_manager as am

    captured = {}

    class _FakeProc:
        pid = 4242
        returncode = 0

        def wait(self):
            return 0

    def fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(am._subprocess, "Popen", fake_popen)

    subjects_dir = tmp_path / "derivatives" / "freesurfer"
    subjects_dir.mkdir(parents=True)
    config = AutoflattenConfig(subjects_dir=str(subjects_dir), subject="sub-01")

    handle = am.AutoflattenRunHandle(run_id="r", subject="sub-01")
    handle.log_path = str(tmp_path / "out.log")

    try:
        am.AutoflattenManager.__new__(am.AutoflattenManager)._execute_detached(
            handle, {}, config, ["lh"],
        )
    except Exception:
        pass  # only the spawned environment matters here

    assert captured.get("env") is not None, "Popen was called without env="
    assert captured["env"]["SUBJECTS_DIR"] == str(subjects_dir)


def test_pycortex_import_uses_positional_args(monkeypatch, tmp_path):
    """pycortex's import_subj parameter names differ across releases.

    1.3.x takes (freesurfer_subject, pycortex_subject,
    freesurfer_subject_dir); passing fs_subject=/cx_subject= raised
    TypeError on every first-time import, and the error was swallowed —
    the run reported success with no pycortex surface.
    """
    import sys
    import types

    from fmriflow.preproc import autoflatten as af

    captured = {}

    def fake_import_subj(freesurfer_subject, pycortex_subject=None,
                         freesurfer_subject_dir=None, whitematter_surf="smoothwm"):
        captured.update(
            fs=freesurfer_subject, cx=pycortex_subject, dir=freesurfer_subject_dir,
        )

    fake_cortex = types.ModuleType("cortex")
    fake_fs = types.ModuleType("cortex.freesurfer")
    fake_fs.import_subj = fake_import_subj
    fake_cortex.freesurfer = fake_fs
    monkeypatch.setitem(sys.modules, "cortex", fake_cortex)
    monkeypatch.setitem(sys.modules, "cortex.freesurfer", fake_fs)
    monkeypatch.setattr(af, "_pycortex_subject_list", lambda c: [])

    config = AutoflattenConfig(
        subjects_dir=str(tmp_path), subject="sub-01",
        pycortex_surface_name="sub01fs",
    )
    af._do_pycortex_import(config, {})

    assert captured == {"fs": "sub-01", "cx": "sub01fs", "dir": str(tmp_path)}
