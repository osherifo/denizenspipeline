"""
Heuristic file for anatomical-only MP2RAGE sessions.

Converts Siemens MP2RAGE acquisitions to BIDS. An MP2RAGE protocol
exports three series per repetition — the two inversion volumes (INV1,
INV2) and the derived uniform image (UNI). Only the UNI image is a
usable T1-weighted volume, so that is what becomes ``_T1w``; mapping
all three would hand fmriprep three "T1w" images per run and it would
average them into nonsense.

Repeated runs of the same protocol are numbered ``run-01``… in
acquisition order.

Subjects: any
Scanner: Siemens (MP2RAGE product/WIP sequence)
Sessions: single-session (no {session} in the output paths)

20260729 : initial version — UNI to T1w, inversions skipped
"""

# Set True to also emit the inversion volumes as
# ``_inv-<n>_MP2RAGE``. Off by default: support for the MP2RAGE suffix
# varies between bids-validator releases, and fmriprep ignores them.
EMIT_INVERSIONS = False


# ── Classification ──────────────────────────────────────────────────

def _is_mp2rage(seq) -> bool:
    """True for any series belonging to an MP2RAGE protocol."""
    return "mp2rage" in (seq.protocol_name or "").lower()


def _is_uni(seq) -> bool:
    """True for the derived uniform (UNI) image — the T1w candidate.

    Identified from ImageType rather than the series description so
    that renamed protocols still classify correctly.
    """
    image_type = [str(t).upper() for t in (seq.image_type or [])]
    return _is_mp2rage(seq) and "UNI" in image_type


def _inversion_index(seq) -> int | None:
    """Return 1 or 2 for an INV1/INV2 series, else None."""
    desc = (seq.series_description or "").upper()
    if not _is_mp2rage(seq) or _is_uni(seq):
        return None
    for idx in (1, 2):
        if f"INV{idx}" in desc:
            return idx
    return None


def _is_scout(seq) -> bool:
    """True for localizer / slice-positioning series, which BIDS drops."""
    desc = (seq.series_description or "").lower()
    return any(k in desc for k in ("localizer", "scout", "slicepos", "survey"))


# ── BIDS path builders ──────────────────────────────────────────────

def create_key(template, outtype=("nii.gz",), annotation_classes=None):
    if template is None or not template:
        raise ValueError("Template must be a valid format string")
    return template, outtype, annotation_classes


def infotodict(seqinfo):
    """Map DICOM series to BIDS keys.

    ``{item}`` is incremented per key by heudiconv, so appending the
    UNI series in acquisition order yields run-01, run-02, … .
    """
    t1w = create_key(
        "sub-{subject}/anat/sub-{subject}_acq-mp2rage_run-{item:02d}_T1w"
    )
    inv1 = create_key(
        "sub-{subject}/anat/sub-{subject}_acq-mp2rage_run-{item:02d}_inv-1_MP2RAGE"
    )
    inv2 = create_key(
        "sub-{subject}/anat/sub-{subject}_acq-mp2rage_run-{item:02d}_inv-2_MP2RAGE"
    )

    info: dict = {t1w: []}
    if EMIT_INVERSIONS:
        info[inv1] = []
        info[inv2] = []

    for seq in seqinfo:
        if _is_scout(seq):
            continue

        if _is_uni(seq):
            info[t1w].append(seq.series_id)
            continue

        if EMIT_INVERSIONS:
            idx = _inversion_index(seq)
            if idx == 1:
                info[inv1].append(seq.series_id)
            elif idx == 2:
                info[inv2].append(seq.series_id)

    return info
