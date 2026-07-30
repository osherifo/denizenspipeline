"""MP2RAGE background cleaning — prepare a UNI image for FreeSurfer.

MP2RAGE's uniform (UNI) image is a ratio of the two inversion volumes, so
outside the head — where there is no signal — the ratio is ill-conditioned
and produces noise centred near the MIDDLE of the intensity range rather
than near zero. FreeSurfer's intensity normalisation assumes an MPRAGE-like
near-zero background, reads that mid-grey noise as a huge bias field, and
over-corrects: tissue gets clamped to the white-matter target and the
GM/WM contrast that surface placement depends on disappears.

Observed on a real subject: 83.8% of non-zero voxels in ``T1.mgz`` were
exactly 110, cortical thickness came out ~2.0 mm against a healthy ~2.5 mm,
and ~10% of vertices had zero thickness. recon-all exited 0 throughout.

This workflow attenuates the background using the SECOND INVERSION (INV2),
which has good SNR and a genuinely dark background, and writes a BIDS-shaped
tree containing only the cleaned ``_T1w`` images — which is what fmriprep
should consume, so it never sees the raw UNI.

Two things go wrong with a raw UNI, and they need different fixes:

**Background.** The mid-grey noise outside the head breaks skull-stripping and
biases the normalisation. Fixed by attenuating with INV2 (`method` below).

**Dynamic range.** Every brain voxel sits in the top ~20% of the stored range
(measured on a real subject: in-head p1..p99 = 3218..4090 of 0..4095).
FreeSurfer's `conform` rescales linearly over the full range into 8 bits, so
all tissue lands in roughly 32 of the 256 levels and grey/white differ by a
handful of quantisation steps — the contrast is gone *before* bias correction
or normalisation run. Fixed by `rescale`, which windows to the tissue range
and recovers ~4.6x more levels.

Masking alone is not enough: it zeroes the background but leaves the brain
where it was in the range. On a real subject, masking alone moved the
saturation of `T1.mgz` from 83.8% to 68.7% of non-zero voxels at exactly 110
— better, still unusable.

Two masking methods, both standard practice:

- ``soft`` (default) — ``UNI * INV2 / (INV2 + beta)``. Smoothly attenuates
  background toward zero. No hard edge, which matters because a sharp
  intensity cliff is itself a large gradient that bias correction and
  surface placement can latch onto. Note this also scales *tissue* by
  ``INV2/(INV2+beta)`` — roughly 0.85 for typical INV2 brain values at
  beta=100. That is harmless: FreeSurfer normalises intensity anyway, and
  what it needs is the near-zero background, not a particular tissue value.
- ``mask`` — threshold INV2 (Otsu), keep the largest connected component,
  close holes, dilate, and zero the UNI outside. Sharper, and easier to
  eyeball, but leaves that edge.

Run it as the bootstrap of a ``preproc`` stage:

    bootstrap:
      kind: nipype
      workflow: mp2rage_background_clean
      params: {method: soft, beta: 100}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.manifest import PreprocManifest, now_iso
from fmriflow.preproc.workflow_registry import register_preproc_workflow


# ── The per-run operation, as a self-contained nipype Function ───────
# Nipype executes Function nodes in a fresh interpreter, so every import
# this needs must happen inside the body.

def _clean_one(uni_path, inv2_path, out_path, method, beta, dilate,
               rescale, rescale_floor_pct=1.0):
    """Attenuate the UNI background using INV2. Returns the written path."""
    import os

    import numpy as np
    import nibabel as nb
    from scipy import ndimage

    uni_img = nb.load(uni_path)
    uni = uni_img.get_fdata()
    inv2 = nb.load(inv2_path).get_fdata()

    if inv2.shape != uni.shape:
        raise ValueError(
            f"INV2 shape {inv2.shape} != UNI shape {uni.shape} for {uni_path}"
        )

    if method == "soft":
        # Denominator is never 0 for beta > 0, so no divide guard needed.
        cleaned = uni * (inv2 / (inv2 + float(beta)))
    elif method == "mask":
        hist, edges = np.histogram(inv2.ravel(), bins=256)
        centres = (edges[:-1] + edges[1:]) / 2
        w0 = np.cumsum(hist)
        w1 = w0[-1] - w0
        with np.errstate(invalid="ignore", divide="ignore"):
            m0 = np.cumsum(hist * centres) / w0
            m1 = (np.cumsum((hist * centres)[::-1])[::-1] - hist * centres) / w1
            between = w0 * w1 * (m0 - m1) ** 2
        thr = float(centres[np.nanargmax(between)])

        mask = inv2 > thr
        labels, n = ndimage.label(mask)
        if n > 1:
            sizes = ndimage.sum(mask, labels, range(1, n + 1))
            mask = labels == (int(np.argmax(sizes)) + 1)
        mask = ndimage.binary_closing(mask, np.ones((5, 5, 5)))
        mask = ndimage.binary_fill_holes(mask)
        if dilate:
            mask = ndimage.binary_dilation(mask, iterations=int(dilate))
        cleaned = np.where(mask, uni, 0)
    else:
        raise ValueError(f"unknown method {method!r} (expected 'soft' or 'mask')")

    if rescale:
        # Stretch tissue across the output range.
        #
        # MP2RAGE UNI parks every brain voxel in the top ~20% of its stored
        # range (measured here: in-head p1..p99 = 3218..4090 of 0..4095).
        # FreeSurfer's conform rescales linearly over the FULL range into
        # 8 bits, so all tissue lands in ~32 of the 256 levels and grey/white
        # differ by a handful of quantisation steps. Windowing to the tissue
        # range first recovers ~4.6x more levels.
        #
        # Background is already at (or near) zero from the masking above, and
        # sits below `lo`, so it clips back to zero rather than being lifted.
        # The window is anchored on voxels inside the mask, which is a HEAD
        # mask — it carries skull, scalp and neck as well as brain, so a very
        # low floor lets those drag the window wide and wastes the stretch.
        # Raising the floor sharpens the stretch but starts clipping dark
        # anatomy (CSF, ventricles) to zero, so it is left conservative and
        # exposed as a parameter.
        inside = cleaned[cleaned > 0]
        if inside.size:
            lo = float(np.percentile(inside, rescale_floor_pct))
            hi = float(np.percentile(inside, 99.5))
            if hi > lo:
                cleaned = np.clip((cleaned - lo) / (hi - lo), 0.0, 1.0) * 4095.0

    out = nb.Nifti1Image(cleaned.astype(np.float32), uni_img.affine, uni_img.header)
    out.set_data_dtype(np.float32)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    nb.save(out, out_path)
    return str(out_path)


def _pair_up(bids_dir: str, subject: str, out_dir: str) -> list[tuple[str, str, str]]:
    """Match each UNI (_T1w) with its same-run INV2, and its output path.

    Returned as (uni, inv2, out) triples. A UNI with no matching INV2 is
    skipped by the caller with a loud error rather than silently passed
    through — an unmasked volume reaching recon-all is the whole failure
    this workflow exists to prevent.
    """
    src = Path(bids_dir) / f"sub-{subject}" / "anat"
    dest = Path(out_dir) / f"sub-{subject}" / "anat"
    triples: list[tuple[str, str, str]] = []
    for uni in sorted(src.glob("*_T1w.nii.gz")):
        stem = uni.name[: -len("_T1w.nii.gz")]
        inv2 = sorted(src.glob(f"{stem}_inv-2_MP2RAGE.nii.gz")) or \
               sorted(src.glob(f"{stem}*inv-2*.nii.gz"))
        if not inv2:
            continue
        triples.append((str(uni), str(inv2[0]), str(dest / uni.name)))
    return triples


def _declare_in_bidsignore(root: Path, entries: tuple[str, ...]) -> None:
    """Add *entries* to ``root/.bidsignore``, creating it if needed.

    Tolerates the missing trailing newline heudiconv leaves behind — a
    naive append there merges two entries into one corrupt line that
    declares neither.
    """
    path = root / ".bidsignore"
    existing = (
        [line.strip() for line in path.read_text().splitlines() if line.strip()]
        if path.is_file() else []
    )
    missing = [e for e in entries if e not in existing]
    if not missing:
        return
    root.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([*existing, *missing]) + "\n")


@register_preproc_workflow("mp2rage_background_clean")
class MP2RAGEBackgroundClean:
    """Attenuate MP2RAGE UNI background with INV2 so FreeSurfer can normalise it."""

    name = "mp2rage_background_clean"
    version = "0.1.0"
    description = (
        "Attenuate MP2RAGE UNI background using the INV2 volume, so FreeSurfer's "
        "intensity normalisation does not clamp the brain to a flat value. Writes a "
        "BIDS-shaped tree of cleaned _T1w images for fmriprep to consume."
    )

    PARAM_SCHEMA: dict = {
        "method": {
            "type": "string",
            "default": "soft",
            "enum": ["soft", "mask"],
            "description": (
                "soft = UNI * INV2/(INV2+beta), no hard edge (recommended). "
                "mask = binary INV2 head mask, sharper but leaves an edge."
            ),
        },
        "beta": {
            "type": "float",
            "default": 100.0,
            "min": 1.0,
            "description": "Regularisation constant for method=soft. Larger suppresses more background.",
        },
        "dilate": {
            "type": "int",
            "default": 2,
            "min": 0,
            "description": "Mask dilation iterations for method=mask. Ignored when method=soft.",
        },
        "rescale": {
            "type": "bool",
            "default": True,
            "description": (
                "Stretch tissue across the output range before FreeSurfer "
                "conforms it to 8 bits. MP2RAGE UNI stores tissue in the top "
                "~20% of its range, so without this the whole brain quantises "
                "into ~32 grey levels and GM/WM contrast is lost before "
                "recon-all starts."
            ),
        },
        "rescale_floor_pct": {
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 50.0,
            "description": (
                "Lower percentile of in-mask intensity anchoring the rescale "
                "window. Higher sharpens the stretch but clips dark anatomy "
                "to zero — measured on one subject, p1 clipped 0.8% of the "
                "brain core and p5 clipped 2.8%."
            ),
        },
        "copy_dataset_files": {
            "type": "bool",
            "default": True,
            "description": "Copy dataset_description.json / README / .bidsignore into the output root.",
        },
    }
    REQUIRED_PYTHON: list[str] = ["nibabel>=5.0", "scipy>=1.10", "nipype>=1.8"]
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    # ── contract ────────────────────────────────────────────────────

    def _params(self, config: Any) -> dict:
        p = dict(getattr(config, "backend_params", {}) or {})
        return {
            "method": p.get("method", "soft"),
            "beta": float(p.get("beta", 100.0)),
            "dilate": int(p.get("dilate", 2)),
            "rescale": bool(p.get("rescale", True)),
            "rescale_floor_pct": float(p.get("rescale_floor_pct", 1.0)),
            "copy_dataset_files": bool(p.get("copy_dataset_files", True)),
        }

    def validate(self, config: Any) -> list[str]:
        errors: list[str] = []
        params = self._params(config)

        if params["method"] not in ("soft", "mask"):
            errors.append(
                f"method must be 'soft' or 'mask', got {params['method']!r}"
            )
        if params["beta"] <= 0:
            errors.append(f"beta must be > 0, got {params['beta']}")

        bids_dir = getattr(config, "bids_dir", None)
        if not bids_dir:
            errors.append("bids_dir is required — it holds the UNI + inversions")
            return errors
        if not Path(bids_dir).is_dir():
            errors.append(f"bids_dir not found: {bids_dir}")
            return errors

        subject = getattr(config, "subject", "")
        anat = Path(bids_dir) / f"sub-{subject}" / "anat"
        if not anat.is_dir():
            errors.append(f"no anat directory for sub-{subject} under {bids_dir}")
            return errors

        unis = sorted(anat.glob("*_T1w.nii.gz"))
        if not unis:
            errors.append(f"no *_T1w.nii.gz under {anat}")
            return errors

        triples = _pair_up(bids_dir, subject, str(getattr(config, "output_dir", "")))
        if len(triples) != len(unis):
            missing = len(unis) - len(triples)
            errors.append(
                f"{missing} of {len(unis)} T1w images have no matching inv-2 volume. "
                "Convert with a heuristic that keeps the inversions "
                "(mp2rage_anat_inv, i.e. EMIT_INVERSIONS = True) — cleaning cannot "
                "run without INV2, and letting an unmasked UNI through is exactly "
                "the failure this workflow prevents."
            )
        return errors

    def build(self, config: Any) -> Any:
        """Return a nipype Workflow with one cleaning node per run."""
        from nipype import Function, Workflow
        from nipype.pipeline.engine import MapNode

        params = self._params(config)
        triples = _pair_up(
            str(config.bids_dir), config.subject, str(config.output_dir),
        )

        # Nipype's working tree must live OUTSIDE output_dir: output_dir is a
        # BIDS root here, and anything unexpected inside it fails strict
        # validation — which fmriprep runs itself and aborts on.
        base_dir = Path(config.output_dir).parent / ".nipype_work"
        base_dir.mkdir(parents=True, exist_ok=True)

        wf = Workflow(name="mp2rage_background_clean", base_dir=str(base_dir))
        clean = MapNode(
            Function(
                input_names=["uni_path", "inv2_path", "out_path",
                             "method", "beta", "dilate", "rescale",
                             "rescale_floor_pct"],
                output_names=["out_file"],
                function=_clean_one,
            ),
            iterfield=["uni_path", "inv2_path", "out_path"],
            name="clean",
        )
        clean.inputs.uni_path = [t[0] for t in triples]
        clean.inputs.inv2_path = [t[1] for t in triples]
        clean.inputs.out_path = [t[2] for t in triples]
        clean.inputs.method = params["method"]
        clean.inputs.beta = params["beta"]
        clean.inputs.dilate = params["dilate"]
        clean.inputs.rescale = params["rescale"]
        clean.inputs.rescale_floor_pct = params["rescale_floor_pct"]
        wf.add_nodes([clean])
        return wf

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        params = self._params(config)
        out_dir = Path(config.output_dir)

        if params["copy_dataset_files"] and getattr(config, "bids_dir", None):
            import shutil
            src_root = Path(config.bids_dir)
            for fname in ("dataset_description.json", "README", "CHANGES", ".bidsignore"):
                s = src_root / fname
                if s.is_file():
                    out_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(s, out_dir / fname)

        # output_dir is a BIDS root, so declare the non-BIDS files fmriflow
        # itself drops into it — otherwise strict validation fails and
        # fmriprep, which runs that validator, refuses to start. The preproc
        # manager writes preproc_manifest.json *after* this method returns,
        # so it must be declared ahead of time rather than detected.
        _declare_in_bidsignore(out_dir, ("preproc_manifest.json", ".nipype_work/"))

        written = sorted((out_dir / f"sub-{config.subject}" / "anat").glob("*_T1w.nii.gz"))

        return PreprocManifest(
            subject=config.subject,
            dataset=getattr(config, "dataset", None) or "unknown",
            sessions=list(getattr(config, "sessions", None) or []),
            # Anatomical-only stage: `runs` describes BOLD runs, so it is
            # empty here by design (as it is for fmriprep anat_only). The
            # cleaned images are located by path, not through the manifest.
            runs=[],
            backend="nipype",
            backend_version=self.version,
            parameters={
                "workflow": self.name,
                "method": params["method"],
                "beta": params["beta"],
                "dilate": params["dilate"],
                "rescale": params["rescale"],
                "rescale_floor_pct": params["rescale_floor_pct"],
                "n_cleaned": len(written),
                "cleaned_files": [str(p.relative_to(out_dir)) for p in written],
            },
            space="native",
            additional_steps=[
                f"mp2rage_background_clean:{params['method']}"
                + (":rescaled" if params["rescale"] else ""),
            ],
            output_dir=str(out_dir),
            created=now_iso(),
        )
