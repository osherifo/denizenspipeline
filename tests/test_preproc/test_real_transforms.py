"""Stage 7a — real-transform tests using synthetic NIfTI fixtures.

Validates the four built-in transforms (identity, smooth, mask_apply,
regress_confounds) against actual NIfTI files. Synthetic data: a
10×10×10×20 random volume + a binary mask + a confounds TSV. Tests
verify the math (smoothing reduces variance, masking zeros voxels
outside, regression removes correlated motion-like signal).

Plus an end-to-end integration test: passthrough bootstrap on a
temp derivatives_dir + smooth transform → final manifest's
output_dir contains a real smoothed file.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

# Skip the whole module gracefully if nibabel isn't installed
# (project-level dep, so this should never trigger in CI).
nib = pytest.importorskip("nibabel")

from fmriflow.modules.nipype_nodes.mask_apply import MaskApplyNode
from fmriflow.modules.nipype_nodes.smooth import SmoothNode
from fmriflow.preproc.builtin_transforms.regress_confounds import (
    DEFAULT_COLUMNS,
    RegressConfoundsTransform,
)
from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    TransformStage,
)
from fmriflow.preproc.stack_runner import StackRunConfig, StackRunner
from fmriflow.preproc.transform import Transform
from fmriflow.preproc.transform_registry import TransformRegistry
from fmriflow.preproc.workflow_registry import WorkflowRegistry


# ── Fixtures ───────────────────────────────────────────────────────


def _write_nifti(path: Path, shape: tuple[int, ...], seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    data = rng.standard_normal(shape).astype(np.float32)
    img = nib.Nifti1Image(data, affine=np.eye(4))
    nib.save(img, str(path))
    return path


def _write_mask(path: Path, shape: tuple[int, int, int], radius: int = 3) -> Path:
    """Write a binary mask that's True inside a centred sphere."""
    xx, yy, zz = np.indices(shape)
    cx, cy, cz = [s // 2 for s in shape]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2 + (zz - cz) ** 2)
    mask = (dist <= radius).astype(np.uint8)
    img = nib.Nifti1Image(mask, affine=np.eye(4))
    nib.save(img, str(path))
    return path


def _write_confounds(path: Path, n_trs: int, n_extra_cols: int = 0) -> Path:
    """Write a BIDS-derivatives style confounds TSV with the 6 motion
    columns + optional extras."""
    rng = np.random.default_rng(42)
    rows = rng.standard_normal((n_trs, 6 + n_extra_cols))
    headers = list(DEFAULT_COLUMNS)
    headers += [f"extra_{i}" for i in range(n_extra_cols)]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(headers)
        for r in rows:
            writer.writerow([f"{v:.6f}" for v in r])
    return path


# ── Smooth ─────────────────────────────────────────────────────────


class TestSmoothTransform:
    def test_satisfies_protocol(self):
        assert isinstance(SmoothNode(), Transform)

    def test_smoothing_reduces_high_frequency_variance(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (10, 10, 10, 20))
        node = SmoothNode()
        out = node.run(
            inputs={"in_file": in_file},
            out_dir=tmp_path / "out",
            params={"fwhm": 6.0},
        )

        out_path = Path(out["out_file"])
        assert out_path.is_file()
        smoothed = nib.load(str(out_path)).get_fdata()

        orig = nib.load(str(in_file)).get_fdata()
        assert smoothed.shape == orig.shape

        # Smoothed data has lower voxel-wise variance than the original
        # noisy input — that's the whole point of Gaussian smoothing.
        assert smoothed.std() < orig.std()

    def test_zero_fwhm_is_a_noop_passthrough(self, tmp_path):
        # FWHM=0 should leave the data essentially untouched.
        in_file = _write_nifti(tmp_path / "in.nii.gz", (8, 8, 8, 5))
        node = SmoothNode()
        out = node.run(
            inputs={"in_file": in_file},
            out_dir=tmp_path / "out",
            params={"fwhm": 0.0},
        )
        smoothed = nib.load(str(out["out_file"])).get_fdata()
        orig = nib.load(str(in_file)).get_fdata()
        np.testing.assert_allclose(smoothed, orig, atol=1e-5)


# ── Mask apply ─────────────────────────────────────────────────────


class TestMaskApplyTransform:
    def test_satisfies_protocol(self):
        assert isinstance(MaskApplyNode(), Transform)

    def test_zeros_voxels_outside_mask(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (10, 10, 10, 5))
        mask_file = _write_mask(tmp_path / "mask.nii.gz", (10, 10, 10), radius=3)

        node = MaskApplyNode()
        out = node.run(
            inputs={"in_file": in_file, "mask_file": str(mask_file)},
            out_dir=tmp_path / "out",
            params={},
        )

        masked = nib.load(str(out["out_file"])).get_fdata()
        mask = nib.load(str(mask_file)).get_fdata().astype(bool)

        # Voxels inside the mask are unchanged; voxels outside are zero.
        outside = ~mask
        assert np.all(masked[outside] == 0)
        assert masked.shape == (10, 10, 10, 5)

    def test_requires_mask(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (4, 4, 4, 3))
        node = MaskApplyNode()
        with pytest.raises(ValueError, match="mask"):
            node.run(
                inputs={"in_file": in_file},
                out_dir=tmp_path / "out",
                params={},
            )


# ── Regress confounds ──────────────────────────────────────────────


class TestRegressConfoundsTransform:
    def test_satisfies_protocol(self):
        assert isinstance(RegressConfoundsTransform(), Transform)

    def test_removes_correlated_signal(self, tmp_path):
        """Construct BOLD = motion-correlated signal + noise, regress
        out the motion, verify the residual no longer correlates with
        motion."""
        n_trs = 30
        shape = (5, 5, 5, n_trs)
        rng = np.random.default_rng(0)

        # Build the confounds TSV first so we can build BOLD as a
        # function of it.
        confounds_path = tmp_path / "confounds.tsv"
        motion = rng.standard_normal((n_trs, 6)).astype(np.float64)
        with open(confounds_path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(DEFAULT_COLUMNS)
            for r in motion:
                writer.writerow([f"{v:.6f}" for v in r])

        # BOLD = a per-voxel weighted sum of motion params + small noise.
        # The smaller the noise, the closer the residual should be to zero.
        voxel_betas = rng.standard_normal((np.prod(shape[:3]), 6)) * 0.5
        noise = rng.standard_normal((n_trs, np.prod(shape[:3]))) * 0.1
        signal = motion @ voxel_betas.T  # (n_trs, n_voxels)
        timeseries = signal + noise
        bold = timeseries.T.reshape(*shape[:3], n_trs).astype(np.float32)
        in_file = tmp_path / "in.nii.gz"
        nib.save(nib.Nifti1Image(bold, np.eye(4)), str(in_file))

        node = RegressConfoundsTransform()
        out = node.run(
            inputs={"in_file": in_file},
            out_dir=tmp_path / "out",
            params={
                "confounds_path": str(confounds_path),
                "columns": DEFAULT_COLUMNS,
                "demean": True,
            },
        )

        residuals = nib.load(str(out["out_file"])).get_fdata()
        resid_ts = residuals.reshape(-1, n_trs).T  # (n_trs, n_voxels)

        # The residual should be dominated by noise — its correlation
        # with each motion column should be near zero.
        for i in range(6):
            corrs = np.array([
                np.corrcoef(motion[:, i], resid_ts[:, v])[0, 1]
                for v in range(resid_ts.shape[1])
            ])
            assert np.abs(corrs).mean() < 0.15, (
                f"motion col {i} still correlates with residuals "
                f"(mean |r|={np.abs(corrs).mean():.3f})"
            )

    def test_missing_confounds_path_raises(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (4, 4, 4, 10))
        node = RegressConfoundsTransform()
        with pytest.raises(ValueError, match="confounds_path"):
            node.run(
                inputs={"in_file": in_file},
                out_dir=tmp_path / "out",
                params={},
            )

    def test_missing_confounds_file_raises(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (4, 4, 4, 10))
        node = RegressConfoundsTransform()
        with pytest.raises(FileNotFoundError):
            node.run(
                inputs={"in_file": in_file},
                out_dir=tmp_path / "out",
                params={"confounds_path": str(tmp_path / "ghost.tsv")},
            )

    def test_mismatched_tr_count_raises(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (4, 4, 4, 20))
        confounds = _write_confounds(tmp_path / "c.tsv", n_trs=15)
        node = RegressConfoundsTransform()
        with pytest.raises(ValueError, match="must match"):
            node.run(
                inputs={"in_file": in_file},
                out_dir=tmp_path / "out",
                params={"confounds_path": str(confounds)},
            )

    def test_missing_columns_raises(self, tmp_path):
        in_file = _write_nifti(tmp_path / "in.nii.gz", (4, 4, 4, 10))
        confounds = _write_confounds(tmp_path / "c.tsv", n_trs=10)
        node = RegressConfoundsTransform()
        with pytest.raises(KeyError, match="missing columns"):
            node.run(
                inputs={"in_file": in_file},
                out_dir=tmp_path / "out",
                params={
                    "confounds_path": str(confounds),
                    "columns": ["trans_x", "ghost_regressor"],
                },
            )


# ── End-to-end stack: passthrough + smooth ─────────────────────────


class TestPassthroughSmoothEndToEnd:
    """The headline integration: a real BIDS-derivatives layout +
    a real smoothing transform. No mocks; the runner actually
    invokes scipy.ndimage and writes a NIfTI."""

    def test_passthrough_then_smooth_produces_real_output(self, tmp_path):
        # 1. Build a fake BIDS-derivatives layout with one bold file.
        deriv = tmp_path / "derivatives"
        sub_dir = deriv / "sub-sub01"
        sub_dir.mkdir(parents=True)
        bold_path = (
            sub_dir
            / "sub-sub01_task-story_run-01_space-MNI_desc-preproc_bold.nii.gz"
        )
        _write_nifti(bold_path, (8, 8, 8, 10))

        # 2. Build registries with our four real built-in transforms.
        wf_reg = WorkflowRegistry(user_dir=tmp_path / "_wf_user")
        wf_reg.discover()
        tx_reg = TransformRegistry(user_dir=tmp_path / "_tx_user")
        tx_reg.discover()

        # 3. Configure the stack: passthrough discovers the bold file,
        #    smooth transform Gaussians it.
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="passthrough"),
            transforms=[TransformStage(name="smooth", params={"fwhm": 4.0})],
        )

        config = StackRunConfig(
            subject="sub01",
            output_dir=tmp_path / "out",
            derivatives_dir=deriv,
            dataset="study1",
            sessions=["ses01"],
            task="story",
        )

        runner = StackRunner(wf_reg, tx_reg, use_cache=False)
        result = runner.run(stack, config)

        # 4. Assert: the run completed, the smooth stage ran, the
        #    output NIfTI exists.
        assert result.status == "completed", result.errors
        assert len(result.manifest.additional_steps) == 1
        smooth_step = result.manifest.additional_steps[0]
        assert smooth_step.name == "smooth"

        # The transform writes a real file into its stage out_dir.
        stage_dir = Path(smooth_step.output_dir)
        assert stage_dir.is_dir()
        smoothed_files = list(stage_dir.glob("*_smooth-*.nii.gz"))
        assert len(smoothed_files) == 1

        # And the file is a real, loadable NIfTI of the expected shape.
        smoothed = nib.load(str(smoothed_files[0])).get_fdata()
        assert smoothed.shape == (8, 8, 8, 10)
