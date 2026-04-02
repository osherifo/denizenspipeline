"""DICOM utilities — scanner info extraction and series listing.

Uses pydicom if available.  These are optional helpers for heuristic
auto-selection and the ``fmriflow convert scan`` command.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from fmriflow.convert.manifest import ScannerInfo

logger = logging.getLogger(__name__)


@dataclass
class SeriesInfo:
    """Summary of a single DICOM series."""

    number: int
    description: str
    n_images: int
    modality_guess: str  # "bold", "T1w", "T2w", "fmap", "localizer", "unknown"


def extract_scanner_info(dicom_dir: str | Path) -> ScannerInfo | None:
    """Read DICOM headers from the first file in a directory to extract
    scanner metadata.

    Returns ``None`` if pydicom is not installed or no DICOMs are found.
    """
    try:
        import pydicom
    except ImportError:
        logger.debug("pydicom not available — skipping scanner info extraction")
        return None

    dcm_path = _find_first_dicom(Path(dicom_dir))
    if dcm_path is None:
        return None

    try:
        ds = pydicom.dcmread(dcm_path, stop_before_pixels=True)
        return ScannerInfo(
            manufacturer=getattr(ds, "Manufacturer", None),
            model=getattr(ds, "ManufacturerModelName", None),
            field_strength=_safe_float(getattr(ds, "MagneticFieldStrength", None)),
            software_version=_as_str(getattr(ds, "SoftwareVersions", None)),
            station_name=getattr(ds, "StationName", None),
            institution=getattr(ds, "InstitutionName", None),
        )
    except Exception:
        logger.warning("Could not read DICOM headers from %s", dcm_path, exc_info=True)
        return None


def list_series(dicom_dir: str | Path) -> list[SeriesInfo]:
    """List DICOM series in a directory with descriptions, image counts,
    and modality guesses.

    Returns an empty list if pydicom is not available or no DICOMs found.
    """
    try:
        import pydicom
    except ImportError:
        logger.warning("pydicom not installed — cannot list DICOM series")
        return []

    root = Path(dicom_dir)
    series: dict[int, dict] = {}  # series_number → {description, count}

    # Tags we need: SeriesNumber (0020,0011), SeriesDescription (0008,103E)
    SERIES_NUMBER_TAG = pydicom.tag.Tag(0x0020, 0x0011)
    SERIES_DESC_TAG = pydicom.tag.Tag(0x0008, 0x103E)

    for dcm_path in _iter_dicoms(root):
        try:
            ds = pydicom.dcmread(
                dcm_path, stop_before_pixels=True,
                specific_tags=[SERIES_NUMBER_TAG, SERIES_DESC_TAG],
            )
            num = int(getattr(ds, "SeriesNumber", 0))
            desc = getattr(ds, "SeriesDescription", "unknown")
            if num not in series:
                series[num] = {"description": str(desc), "count": 0}
            series[num]["count"] += 1
        except Exception:
            continue

    results = []
    for num in sorted(series):
        info = series[num]
        results.append(SeriesInfo(
            number=num,
            description=info["description"],
            n_images=info["count"],
            modality_guess=_guess_modality(info["description"]),
        ))

    return results


# ── Internal helpers ─────────────────────────────────────────────────────

def _find_first_dicom(root: Path) -> Path | None:
    """Find the first DICOM file in a directory tree."""
    for p in sorted(root.rglob("*")):
        if p.is_file() and _is_dicom(p):
            return p
    return None


def _iter_dicoms(root: Path):
    """Yield DICOM file paths from a directory tree."""
    for p in sorted(root.rglob("*")):
        if p.is_file() and _is_dicom(p):
            yield p


def _is_dicom(path: Path) -> bool:
    """Quick check if a file is likely a DICOM."""
    if path.suffix.lower() == ".dcm":
        return True
    # Check for DICOM magic bytes at offset 128
    if path.suffix == "" or path.suffix.lower() in (".ima", ".img"):
        try:
            with open(path, "rb") as f:
                f.seek(128)
                return f.read(4) == b"DICM"
        except Exception:
            pass
    return False


def _guess_modality(description: str) -> str:
    """Guess modality from a DICOM series description."""
    desc = description.lower()
    if any(k in desc for k in ("bold", "epi", "fmri", "func", "ep2d")):
        return "bold"
    if any(k in desc for k in ("t1", "mprage", "mp2rage", "spgr", "bravo")):
        return "T1w"
    if any(k in desc for k in ("t2", "tse", "space")):
        return "T2w"
    if any(k in desc for k in ("dwi", "dti", "diffusion")):
        return "dwi"
    if any(k in desc for k in ("fmap", "fieldmap", "gre_field", "b0")):
        return "fmap"
    if any(k in desc for k in ("localizer", "scout", "survey")):
        return "localizer"
    return "unknown"


def _safe_float(val: object) -> float | None:
    """Convert a DICOM value to float, or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _as_str(val: object) -> str | None:
    """Convert a DICOM value (possibly a MultiValue) to a string."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    try:
        return str(val)
    except Exception:
        return None
