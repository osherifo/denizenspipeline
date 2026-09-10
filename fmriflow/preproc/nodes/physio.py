"""Physiological-noise correction nodes (BIOPAC ``.acq`` → PhLEM regressors → cleaned BOLD).

Three nodes so every stage is a checkpoint and can be inspected on its own:

* ``physio_regressors`` — split the acquisition into scan blocks, pick one,
  build the PhLEM regressor TSV for it.
* ``physio_estimate`` — per-voxel OLS weights of those regressors.
* ``physio_clean`` — remove the fitted contribution (estimating the weights
  itself when none are connected).

After fmriprep: feed its ``bold_preproc`` list to ``physio_regressors``
(no iteration — it pairs run *i* with block *i* of the recording, per
session when there is one recording per session) and iterate
``physio_clean`` over ``in_file`` + ``regressors_file``. The bundled
``fmriprep_physio`` template is exactly that.

One run at a time still works: a single ``in_file`` with ``block`` (param
or port), or ``in_file`` + ``block`` iterated in lockstep.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fmriflow.preproc.checkpoints import Check, checkpoint_metric, nifti_stats_metrics
from fmriflow.preproc.node_registry import preproc_node
from fmriflow.preproc.physio import acq as acq_mod
from fmriflow.preproc.physio.phlem import MODEL_TERMS

REGRESSORS_NAME = "physio_regressors.tsv"
BLOCKS_NAME = "physio_blocks.json"
WEIGHTS_NAME = "physio_weights.nii.gz"
CLEAN_SUMMARY_NAME = "physio_clean.json"

_TRIM_PARAMS: dict[str, Any] = {
    "zscore_image": {"type": "bool", "default": True, "group": "Model",
                     "description": "Z-score each voxel's series before fitting / cleaning."},
    "zscore_physio": {"type": "bool", "default": True, "group": "Model",
                      "description": "Z-score each regressor column."},
    "auto_trim": {"type": "bool", "default": False, "group": "Alignment",
                  "description": "Drop surplus physio TRs at the end so the count matches the BOLD."},
    "trim_begin": {"type": "int", "default": 0, "min": 0, "group": "Alignment",
                   "description": "Physio TRs to drop at the start (ignored with auto_trim)."},
    "trim_end": {"type": "int", "default": 0, "min": 0, "group": "Alignment",
                 "description": "Physio TRs to drop at the end (ignored with auto_trim)."},
}


def _trim_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "zscore_image": bool(params.get("zscore_image", True)),
        "zscore_physio": bool(params.get("zscore_physio", True)),
        "auto_trim": bool(params.get("auto_trim", False)),
        "trim_begin": int(params.get("trim_begin") or 0),
        "trim_end": int(params.get("trim_end") or 0),
    }


def _stem(path: Path) -> str:
    return path.name.replace(".nii.gz", "").replace(".nii", "")


def _tr_from_header(path: Path) -> tuple[float, int]:
    import nibabel as nib
    img = nib.load(str(path))
    tr = float(img.header.get_zooms()[3]) if len(img.shape) == 4 else 0.0
    n = int(img.shape[3]) if len(img.shape) == 4 else 0
    return tr, n


_DERIV_ENTITIES = re.compile(r"_(space|res|den|desc)-[A-Za-z0-9]+")


def _acquisition_time(bold: Path, bids_dir: Path | None) -> float | None:
    """Seconds since midnight from the run's raw sidecar (``AcquisitionTime``), else None.

    A derivative (``…_space-T1w_desc-preproc_bold.nii.gz``) maps back to its raw
    file by dropping the derivative entities; the sidecar is looked for next to
    the file first, then under ``bids_dir`` for the same subject / session.
    """
    stem = _DERIV_ENTITIES.sub("", _stem(bold))
    candidates = [bold.parent / f"{stem}.json", bold.with_name(f"{_stem(bold)}.json")]
    if bids_dir is not None:
        parts = dict(kv.split("-", 1) for kv in stem.split("_") if "-" in kv)
        sub, ses = parts.get("sub"), parts.get("ses")
        if sub:
            base = bids_dir / f"sub-{sub}"
            if ses:
                base = base / f"ses-{ses}"
            candidates.append(base / "func" / f"{stem}.json")
    for c in candidates:
        if c.is_file():
            try:
                t = json.loads(c.read_text()).get("AcquisitionTime")
            except Exception:
                continue
            if t:
                try:
                    h, m, sec = str(t).split(":")
                    return int(h) * 3600 + int(m) * 60 + float(sec)
                except ValueError:
                    continue
    return None


# ── metrics ─────────────────────────────────────────────────────────


@checkpoint_metric("physio_blocks")
def physio_blocks_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """What the acquisition split into and whether the chosen block fits the BOLD."""
    d = json.loads(Path(path).read_text())
    blocks = d.get("blocks") or []
    sel = d.get("selected") or {}
    metrics: dict[str, Any] = {
        "n_blocks": len(blocks),
        "sampling_rate": d.get("sampling_rate"),
        "block_durations_s": [b.get("duration_s") for b in blocks],
        "selected_block": sel.get("index"),
        "selected_n_trs": sel.get("n_trs"),
        "bold_n_trs": d.get("bold_n_trs"),
        "tr_s": d.get("tr_s"),
    }
    if sel.get("n_trs") is not None and d.get("bold_n_trs"):
        metrics["tr_surplus"] = int(sel["n_trs"]) - int(d["bold_n_trs"])
    return metrics, {"blocks": blocks}


@checkpoint_metric("physio_regressors")
def physio_regressors_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shape and health of a regressor TSV: NaNs, constant columns, collinearity."""
    import numpy as np
    from fmriflow.preproc.physio.regress import read_regressors
    X, names = read_regressors(path)
    finite = np.isfinite(X)
    metrics: dict[str, Any] = {
        "n_trs": int(X.shape[0]), "n_regressors": int(X.shape[1]),
        "n_nan_inf": int((~finite).sum()),
        "n_constant_columns": int(np.sum(np.nan_to_num(X).std(axis=0) == 0)) if X.size else 0,
    }
    if X.shape[1] > 1 and X.shape[0] > 2:
        Z = np.nan_to_num(X)
        keep = Z.std(axis=0) > 0
        if keep.sum() > 1:
            c = np.corrcoef(Z[:, keep].T)
            np.fill_diagonal(c, 0)
            metrics["max_abs_correlation"] = float(np.max(np.abs(c)))
    return metrics, {"regressor_names": names}


@checkpoint_metric("physio_clean_summary")
def physio_clean_metrics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The cleaning node's summary: variance removed, NaNs in the output."""
    d = json.loads(Path(path).read_text())
    return {k: d.get(k) for k in ("n_trs", "n_regressors", "variance_removed_fraction", "n_nan_inf")}, {}


# ── nodes ───────────────────────────────────────────────────────────


@preproc_node("physio_regressors")
class PhysioRegressorsNode:
    """Split a BIOPAC recording into scan blocks and build PhLEM regressors for one."""

    name = "physio_regressors"
    version = "0.1.0"
    description = (
        "Split a BIOPAC .acq recording into scan blocks at gaps in the scanner's TTL train, "
        "then build the PhLEM physiological regressors (RETROICOR phases, per-TR rates, "
        "respiration-volume and heart-rate variation) for one block as a TSV."
    )

    INPUTS = {
        "physio_file": {"kind": "file", "required": True,
                        "description": "BIOPAC .acq recording — or one per session (matched by ses- in the file name)"},
        "block": {"kind": "any", "required": False,
                  "description": "block index for a single in_file (overrides the param; may iterate in lockstep with it)"},
        "in_file": {"kind": "nifti", "required": False,
                    "description": "the run's BOLD, or fmriprep's whole list (run i in scan order ↔ block i); supplies the TR when tr=0"},
        "bids_dir": {"kind": "dir", "required": False,
                     "description": "raw BIDS root: the runs' sidecars give the scan order (AcquisitionTime) the blocks follow"},
    }
    OUTPUTS = {
        "regressors_file": {"kind": "tsv", "description": "one column per regressor, one row per TR (a list when in_file is a list)"},
        "bold_files": {"kind": "nifti", "description": "the BOLD runs that got regressors, in the same order (feed physio_clean)"},
        "blocks_file": {"kind": "json", "description": "how the recording split into blocks and which block this run got"},
    }

    PARAM_SCHEMA: dict[str, Any] = {
        "block": {"type": "int", "default": 0, "min": 0, "group": "Block",
                  "description": "Which scan block of the recording a single in_file is (0-based)."},
        "blocks": {"type": "list[int]", "default": [], "group": "Block",
                   "description": "With a list of BOLDs: explicit block index per paired run, in list order, when the "
                                  "recording has extra blocks. Empty = run i (scan order) is block i."},
        "sessions": {"type": "list[string]", "default": [], "group": "Block",
                     "description": "Which session each recording in physio_file covers, in the same order (e.g. 01, 02). "
                                    "Runs from other sessions are left out. Empty = match by ses- in the file names."},
        "max_tr_mismatch": {"type": "int", "default": 5, "min": 0, "group": "Block",
                            "description": "A run whose block has more or fewer triggers than the BOLD has TRs, by more than "
                                           "this, stops the node (a wrong pairing)."},
        "tr": {"type": "float", "default": 0.0, "min": 0.0, "group": "Block",
               "description": "TR in seconds; 0 reads it from in_file's header (values > 10 are taken as ms)."},
        "model": {"type": "list[string]", "default": list(MODEL_TERMS), "enum": list(MODEL_TERMS), "group": "Model",
                  "description": "Regressor families to build."},
        "ppg_peak_rise": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "group": "Model",
                          "description": "Beat detection threshold as a fraction of the 20th-highest PPG peak."},
        "resp_peak_rise": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "group": "Model",
                           "description": "Breath detection threshold as a fraction of the 20th-highest RESP peak."},
        "ppg_channel": {"type": "int", "default": acq_mod.DEFAULT_PPG_CHANNEL, "min": 0, "group": "Acquisition"},
        "resp_channel": {"type": "int", "default": acq_mod.DEFAULT_RESP_CHANNEL, "min": 0, "group": "Acquisition"},
        "ttl_channel": {"type": "int", "default": acq_mod.DEFAULT_TTL_CHANNEL, "min": 0, "group": "Acquisition"},
        "run_gap_s": {"type": "float", "default": acq_mod.DEFAULT_RUN_GAP_S, "min": 0.0, "group": "Acquisition",
                      "description": "A TTL gap longer than this (seconds) starts a new block."},
        "ttl_threshold": {"type": "float", "default": acq_mod.DEFAULT_TTL_THRESHOLD, "group": "Acquisition",
                          "description": "A drop steeper than this between samples counts as a pulse."},
    }

    REQUIRED_PYTHON: list[str] = ["bioread"]
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    CHECKS = [
        Check(step="physio_blocks", artifact="{node_dir}/**/physio_blocks*.json", metrics=physio_blocks_metrics, live=False),
        Check(step="physio_regressors", artifact="{node_dir}/**/physio_regressors*.tsv", metrics=physio_regressors_metrics, live=False),
    ]

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        from fmriflow.preproc.physio.pairing import pair_runs

        physio_in = inputs["physio_file"]
        physio_files = [str(p) for p in (physio_in if isinstance(physio_in, (list, tuple)) else [physio_in])]
        bold_in = inputs.get("in_file")
        many = isinstance(bold_in, (list, tuple))
        out_dir.mkdir(parents=True, exist_ok=True)
        splits: dict[str, acq_mod.AcqSplit] = {}

        def split(path: str) -> acq_mod.AcqSplit:
            if path not in splits:
                splits[path] = acq_mod.split_acq(
                    path,
                    ppg_channel=int(params.get("ppg_channel", acq_mod.DEFAULT_PPG_CHANNEL)),
                    resp_channel=int(params.get("resp_channel", acq_mod.DEFAULT_RESP_CHANNEL)),
                    ttl_channel=int(params.get("ttl_channel", acq_mod.DEFAULT_TTL_CHANNEL)),
                    run_gap_s=float(params.get("run_gap_s", acq_mod.DEFAULT_RUN_GAP_S)),
                    ttl_threshold=float(params.get("ttl_threshold", acq_mod.DEFAULT_TTL_THRESHOLD)),
                )
            return splits[path]

        if not many:
            block_in = inputs.get("block")
            block = int(block_in) if block_in not in (None, "") else int(params.get("block") or 0)
            if len(physio_files) != 1:
                raise ValueError("physio_regressors: several recordings need a list of BOLDs to pair them with")
            reg, blk = self._one(split(physio_files[0]), block, bold_in, out_dir, params, suffix="")
            out = {"regressors_file": reg, "blocks_file": blk}
            if bold_in:
                out["bold_files"] = Path(str(bold_in))
            return out

        bolds = [str(b) for b in bold_in]
        explicit = [int(x) for x in (params.get("blocks") or [])] or None
        sessions = [str(x) for x in (params.get("sessions") or [])] or None
        bids_dir = inputs.get("bids_dir")
        times = {b: _acquisition_time(Path(b), Path(bids_dir) if bids_dir else None) for b in bolds}
        pairs, skipped = pair_runs(bolds, physio_files, explicit, sessions=sessions, order_key=lambda b: times[b])
        if not pairs:
            raise ValueError("physio_regressors: no BOLD run is covered by a recording (check 'sessions')")
        # Every recording must split into exactly the runs it is paired with,
        # unless the caller mapped blocks explicitly.
        per_file: dict[str, list] = {}
        for pr in pairs:
            per_file.setdefault(pr.physio_file, []).append(pr)
        if explicit is None:
            for path, prs in per_file.items():
                sp = split(path)
                if len(sp.blocks) != len(prs):
                    have = ", ".join(f"#{b.index} {b.duration_s:.0f}s/{b.n_pulses} triggers" for b in sp.blocks)
                    want = ", ".join(f"{Path(pr.bold).name} ({_tr_from_header(Path(pr.bold))[1]} TRs)" for pr in prs)
                    raise ValueError(
                        f"physio_regressors: {Path(path).name} splits into {len(sp.blocks)} block(s) [{have}] but "
                        f"{len(prs)} BOLD run(s) pair with it [{want}]; set 'blocks' to map runs to blocks explicitly, "
                        f"or adjust run_gap_s / ttl_threshold"
                    )
        # The block's trigger count must match the run's TR count: the check that
        # catches a wrong scan order before any regressor is fitted.
        tol = int(params.get("max_tr_mismatch", 5) or 0)
        table = []
        bad = []
        for pr in pairs:
            blk = split(pr.physio_file).blocks[pr.block]
            n_trs = _tr_from_header(Path(pr.bold))[1]
            table.append((Path(pr.bold).name, pr.session, times[pr.bold], pr.block, blk.n_pulses, n_trs))
            if abs(blk.n_pulses - n_trs) > tol:
                bad.append(f"{Path(pr.bold).name}: block #{pr.block} has {blk.n_pulses} triggers, BOLD has {n_trs} TRs")
        if bad:
            rows = "\n".join(f"  {name}  ses={ses} t={t}  block #{k}: {np} triggers vs {nt} TRs" for name, ses, t, k, np, nt in table)
            raise ValueError(
                "physio_regressors: runs and blocks do not line up (wrong scan order or a missing/extra block):\n"
                + "\n".join("  " + b for b in bad) + "\nfull pairing:\n" + rows
                + "\nConnect bids_dir so runs are ordered by AcquisitionTime, or set 'blocks' explicitly."
            )
        regs: list[Path] = []
        blks: list[Path] = []
        used: list[Path] = []
        for pr in pairs:
            reg, blk = self._one(split(pr.physio_file), pr.block, pr.bold, out_dir, params, suffix="_" + _stem(Path(pr.bold)),
                                 extra={"session": pr.session, "order": pr.order, "acquisition_time_s": times[pr.bold],
                                        "skipped_runs": [Path(b).name for b in skipped]})
            regs.append(reg); blks.append(blk); used.append(Path(pr.bold))
        return {"regressors_file": regs, "bold_files": used, "blocks_file": blks}

    def _one(self, split: acq_mod.AcqSplit, block: int, in_file: Any, out_dir: Path, params: dict[str, Any], *,
             suffix: str, extra: dict[str, Any] | None = None) -> tuple[Path, Path]:
        """Regressors for one BOLD from ``block`` of ``split``; files named with ``suffix``."""
        from fmriflow.preproc.physio.phlem import build_regressors
        from fmriflow.preproc.physio.regress import write_regressors

        tr = float(params.get("tr") or 0.0)
        bold_n_trs = None
        if in_file:
            header_tr, bold_n_trs = _tr_from_header(Path(in_file))
            if tr <= 0:
                tr = header_tr
        if tr <= 0:
            raise ValueError("physio_regressors: set 'tr' (seconds) or connect in_file so it can be read from the header")
        if tr > 10:      # the lab's convention: values above 10 are milliseconds
            tr = tr / 1000.0

        physio_file = Path(split.source)
        if not 0 <= block < len(split.blocks):
            raise ValueError(
                f"physio_regressors: block {block} requested but {physio_file.name} has "
                f"{len(split.blocks)} block(s): "
                + ", ".join(f"#{b.index} {b.duration_s:.0f}s/{b.summary()['n_trs']} TRs" for b in split.blocks)
            )
        blk = split.blocks[block]
        t, _trigger, cardiac, respiratory = blk.data

        terms = [str(x) for x in (params.get("model") or MODEL_TERMS)]
        X, names = build_regressors(
            cardiac, respiratory, t, tr, blk.sampling_rate, terms=terms,
            ppg_peak_rise=float(params["ppg_peak_rise"]) if params.get("ppg_peak_rise") is not None else None,
            resp_peak_rise=float(params["resp_peak_rise"]) if params.get("resp_peak_rise") is not None else None,
        )

        regressors_file = write_regressors(out_dir / f"physio_regressors{suffix}.tsv", X, names)
        summary = split.summary()
        summary.update({
            "selected": {**blk.summary(), "n_trs": int(X.shape[0])},
            "tr_s": tr, "bold_file": str(in_file or ""), "bold_n_trs": bold_n_trs,
            "regressors": names, "n_regressors": int(X.shape[1]),
            **(extra or {}),
        })
        blocks_file = out_dir / f"physio_blocks{suffix}.json"
        blocks_file.write_text(json.dumps(summary, indent=2))
        return regressors_file, blocks_file


@preproc_node("physio_estimate")
class PhysioEstimateNode:
    """Per-voxel OLS weights of the physio regressors."""

    name = "physio_estimate"
    version = "0.1.0"
    description = "Fit the physio regressors to every voxel (OLS via pseudo-inverse); writes the weights image."

    INPUTS = {
        "in_file": {"kind": "nifti", "required": True, "description": "4-D BOLD"},
        "regressors_file": {"kind": "tsv", "required": True, "description": "physio regressor TSV"},
    }
    OUTPUTS = {"weights_file": {"kind": "nifti", "description": "(x, y, z, n_regressors) weights"}}
    PARAM_SCHEMA: dict[str, Any] = dict(_TRIM_PARAMS)

    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    CHECKS = [
        Check(step="physio_weights", artifact="{node_dir}/**/" + WEIGHTS_NAME, metrics=nifti_stats_metrics, live=False),
    ]

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        from fmriflow.preproc.physio.regress import estimate_weights
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / WEIGHTS_NAME
        estimate_weights(inputs["in_file"], inputs["regressors_file"], out, **_trim_kwargs(params))
        return {"weights_file": out}


@preproc_node("physio_clean")
class PhysioCleanNode:
    """Remove the fitted physio contribution from a BOLD series."""

    name = "physio_clean"
    version = "0.1.0"
    description = (
        "Subtract regressors × weights from every voxel, z-score the residual and restore the voxel mean. "
        "Estimates the weights itself when none are connected."
    )

    INPUTS = {
        "in_file": {"kind": "nifti", "required": True, "description": "4-D BOLD"},
        "regressors_file": {"kind": "tsv", "required": True, "description": "physio regressor TSV"},
        "weights_file": {"kind": "nifti", "required": False,
                         "description": "weights from physio_estimate (estimated here when absent)"},
    }
    OUTPUTS = {
        "out_file": {"kind": "nifti", "description": "cleaned BOLD"},
        "weights_file": {"kind": "nifti", "description": "the weights used"},
        "summary_file": {"kind": "json", "description": "variance removed, TR counts"},
    }
    PARAM_SCHEMA: dict[str, Any] = dict(_TRIM_PARAMS)

    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    CHECKS = [
        Check(step="physio_clean", artifact="{node_dir}/**/" + CLEAN_SUMMARY_NAME, metrics=physio_clean_metrics, live=False),
    ]

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        from fmriflow.preproc.physio.regress import clean, estimate_weights
        out_dir.mkdir(parents=True, exist_ok=True)
        kw = _trim_kwargs(params)
        in_file = Path(inputs["in_file"])
        weights = inputs.get("weights_file")
        if not weights:
            weights = out_dir / WEIGHTS_NAME
            estimate_weights(in_file, inputs["regressors_file"], weights, **kw)
        out = out_dir / f"{_stem(in_file)}_desc-physioclean_bold.nii.gz"
        summary = clean(in_file, inputs["regressors_file"], weights, out, **kw)
        summary_file = out_dir / CLEAN_SUMMARY_NAME
        summary_file.write_text(json.dumps(summary, indent=2))
        return {"out_file": out, "weights_file": Path(weights), "summary_file": summary_file}
