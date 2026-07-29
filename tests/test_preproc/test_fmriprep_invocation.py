"""Tests for how the fmriprep backend builds its container invocation.

Covers ``_build_command``, ``_build_container_prefix`` and ``_find_fmriprep``.
These paths decide whether preprocessing launches at all, and a mistake in
them surfaces only at run time on somebody else's machine.
"""

import pytest

from fmriflow.preproc.backends.fmriprep import FmriprepBackend
from fmriflow.preproc.backends.fmriprep_params import FmriprepParams
from fmriflow.preproc.manifest import PreprocConfig


def _config(**overrides) -> PreprocConfig:
    base = dict(
        subject="01",
        backend="fmriprep",
        bids_dir="/bids",
        output_dir="/out",
        work_dir="/work",
    )
    base.update(overrides)
    return PreprocConfig(**base)


# ── container prefixes ──────────────────────────────────────────────


class TestContainerPrefix:
    def test_docker_binds_and_runs_image(self):
        backend = FmriprepBackend()
        params = FmriprepParams(container="nipreps/fmriprep:24.1.1", container_type="docker")
        cmd = backend._build_container_prefix(_config(), params)

        assert cmd[:3] == ["docker", "run", "--rm"]
        assert "-v" in cmd and "/bids:/data:ro" in cmd
        assert "/out:/out" in cmd
        assert "/work:/work" in cmd
        # The image must precede the bids-app positional arguments.
        image_at = cmd.index("nipreps/fmriprep:24.1.1")
        assert cmd[image_at + 1:image_at + 4] == ["/data", "/out", "participant"]
        assert cmd[-2:] == ["-w", "/work"]

    def test_singularity_uses_cleanenv_and_bind_flags(self):
        backend = FmriprepBackend()
        params = FmriprepParams(container="/img/fmriprep.sif", container_type="singularity")
        cmd = backend._build_container_prefix(_config(), params)

        assert cmd[1:3] == ["run", "--cleanenv"]
        assert "-B" in cmd and "/bids:/data:ro" in cmd
        assert "/img/fmriprep.sif" in cmd

    def test_apptainer_takes_the_singularity_path(self):
        """`container_type: apptainer` is documented and must not be rejected."""
        backend = FmriprepBackend()
        docker_style = FmriprepBackend()._build_container_prefix(
            _config(), FmriprepParams(container="/img/f.sif", container_type="singularity"),
        )
        apptainer_style = backend._build_container_prefix(
            _config(), FmriprepParams(container="/img/f.sif", container_type="apptainer"),
        )
        # Same argv shape; only the resolved binary may differ.
        assert apptainer_style[1:] == docker_style[1:]

    def test_no_work_dir_omits_the_work_bind(self):
        backend = FmriprepBackend()
        params = FmriprepParams(container="img", container_type="docker")
        cmd = backend._build_container_prefix(_config(work_dir=None), params)

        assert not any("/work" in part for part in cmd)
        assert "-w" not in cmd

    def test_bare_is_not_a_container_prefix(self):
        """`bare` means "no container", so asking for a prefix is a bug."""
        backend = FmriprepBackend()
        params = FmriprepParams(container="fmriprep", container_type="bare")
        with pytest.raises(ValueError, match="Unknown container_type"):
            backend._build_container_prefix(_config(), params)


# ── full command ────────────────────────────────────────────────────


class TestBuildCommand:
    def test_bare_invokes_fmriprep_directly(self):
        backend = FmriprepBackend()
        params = FmriprepParams()  # no container set
        cmd = backend._build_command(_config(), params)

        assert cmd[0] == "fmriprep"
        assert cmd[1:4] == ["/bids", "/out", "participant"]
        assert "--participant-label" in cmd
        assert cmd[cmd.index("--participant-label") + 1] == "01"
        assert "-w" in cmd

    def test_container_command_carries_param_flags(self):
        backend = FmriprepBackend()
        params = FmriprepParams(
            container="nipreps/fmriprep:24.1.1",
            container_type="docker",
            output_spaces=["T1w", "MNI152NLin2009cAsym"],
        )
        cmd = backend._build_command(_config(), params)

        assert cmd[0] == "docker"
        assert "--output-spaces" in cmd


# ── availability detection ──────────────────────────────────────────


class TestFindFmriprep:
    def test_docker_requires_the_docker_cli(self, monkeypatch):
        """Regression: the slim image shipped no `docker` binary at all."""
        backend = FmriprepBackend()
        params = FmriprepParams(container="img", container_type="docker")

        monkeypatch.setattr("shutil.which", lambda name: None)
        assert backend._find_fmriprep(params) is False

        monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/docker")
        assert backend._find_fmriprep(params) is True

    def test_bare_with_no_container_looks_for_fmriprep_on_path(self, monkeypatch):
        backend = FmriprepBackend()
        params = FmriprepParams()

        monkeypatch.setattr("shutil.which", lambda name: None)
        assert backend._find_fmriprep(params) is False

        monkeypatch.setattr("shutil.which", lambda name: "/opt/conda/bin/fmriprep")
        assert backend._find_fmriprep(params) is True

    def test_singularity_image_must_exist(self, monkeypatch, tmp_path):
        backend = FmriprepBackend()
        monkeypatch.setattr(
            "fmriflow.preproc.backends.fmriprep.FmriprepBackend._singularity_binary",
            lambda self: "/usr/bin/apptainer",
        )

        missing = FmriprepParams(container=str(tmp_path / "nope.sif"), container_type="singularity")
        assert backend._find_fmriprep(missing) is False

        sif = tmp_path / "fmriprep.sif"
        sif.write_bytes(b"")
        present = FmriprepParams(container=str(sif), container_type="apptainer")
        assert backend._find_fmriprep(present) is True

    def test_docker_uri_needs_no_local_file(self, monkeypatch):
        backend = FmriprepBackend()
        monkeypatch.setattr(
            "fmriflow.preproc.backends.fmriprep.FmriprepBackend._singularity_binary",
            lambda self: "/usr/bin/apptainer",
        )
        params = FmriprepParams(
            container="docker://nipreps/fmriprep:24.1.1", container_type="singularity",
        )
        assert backend._find_fmriprep(params) is True
