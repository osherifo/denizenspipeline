"""DICOM utilities — scanner info extraction and series listing.

Uses pydicom if available.  These are optional helpers for heuristic
auto-selection and the ``fmriflow convert scan`` command.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable

from fmriflow.convert.manifest import ScannerInfo

logger = logging.getLogger(__name__)


@dataclass
class SeriesInfo:
    """Summary of a single DICOM series.

    Every field except ``n_images`` is a DICOM attribute read verbatim
    from the series' own first file (so a directory holding sessions from
    different scanners reports each correctly); nothing is inferred.

    ``series_instance_uid`` is what actually identifies a series — DICOM
    only guarantees ``SeriesNumber`` is unique *within one study*, and a
    directory scanned here may hold several studies/sessions that each
    restart their own numbering (the exact case this scan is meant to
    surface, e.g. two sessions both containing a "series 3").
    """

    number: int          # SeriesNumber
    series_instance_uid: str  # SeriesInstanceUID (0020,000E) — the real identity
    description: str     # SeriesDescription
    n_images: int        # files counted in the series
    modality: str | None = None      # Modality (0008,0060)
    image_type: str | None = None    # ImageType (0008,0008), backslash-joined
    manufacturer: str | None = None
    model: str | None = None
    field_strength: float | None = None
    software_version: str | None = None
    station_name: str | None = None
    institution: str | None = None
    study_date: str | None = None
    protocol_name: str | None = None


StopCheck = Callable[[], bool]
ProgressCallback = Callable[[dict], None]


class ScanCancelled(Exception):
    """Raised inside a scan when its stop check turns true."""


def extract_scanner_info(dicom_dir: str | Path, *, should_stop: StopCheck | None = None) -> ScannerInfo | None:
    """Read DICOM headers from the first file in a directory to extract
    scanner metadata.

    Returns ``None`` if pydicom is not installed or no DICOMs are found.
    """
    try:
        import pydicom
    except ImportError:
        logger.debug("pydicom not available — skipping scanner info extraction")
        return None

    dcm_path = _find_first_dicom(Path(dicom_dir), should_stop=should_stop)
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


def list_series(
    dicom_dir: str | Path,
    *,
    should_stop: StopCheck | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[SeriesInfo]:
    """List DICOM series in a directory with descriptions, image counts,
    and modality guesses.

    Streams the directory tree, so ``should_stop`` (checked every file)
    ends a long scan promptly with :class:`ScanCancelled`; ``on_progress``
    gets ``{"files_seen", "dicoms_seen", "series_found", "current_dir"}``
    every 50 files. Returns an empty list if pydicom is not available or
    no DICOMs found.
    """
    try:
        import pydicom
    except ImportError:
        logger.warning("pydicom not installed — cannot list DICOM series")
        return []

    root = Path(dicom_dir)
    series: dict[str, dict] = {}  # series_instance_uid → {number, description, count, ...}

    # Tags we need: SeriesInstanceUID (0020,000E) is the real per-series key —
    # SeriesNumber is only unique *within one study*, and this directory may
    # hold several. SeriesNumber, SeriesDescription (0008,103E), plus the
    # scanner identity, are read from the first file of each series.
    T = pydicom.tag.Tag
    SERIES_UID_TAG = T(0x0020, 0x000E)
    SERIES_NUMBER_TAG = T(0x0020, 0x0011)
    SERIES_DESC_TAG = T(0x0008, 0x103E)
    SCANNER_TAGS = [
        T(0x0008, 0x0060),  # Modality
        T(0x0008, 0x0008),  # ImageType
        T(0x0008, 0x0070),  # Manufacturer
        T(0x0008, 0x1090),  # ManufacturerModelName
        T(0x0018, 0x0087),  # MagneticFieldStrength
        T(0x0018, 0x1020),  # SoftwareVersions
        T(0x0008, 0x1010),  # StationName
        T(0x0008, 0x0080),  # InstitutionName
        T(0x0008, 0x0020),  # StudyDate
        T(0x0018, 0x1030),  # ProtocolName
    ]

    files_seen = 0
    dicoms_seen = 0
    for dcm_path in _iter_dicoms(root, should_stop=should_stop):
        files_seen += 1
        if on_progress is not None and files_seen % 50 == 0:
            on_progress({"files_seen": files_seen, "dicoms_seen": dicoms_seen, "series_found": len(series),
                         "current_dir": str(dcm_path.parent)})
        try:
            ds = pydicom.dcmread(
                dcm_path, stop_before_pixels=True,
                specific_tags=[SERIES_UID_TAG, SERIES_NUMBER_TAG, SERIES_DESC_TAG, *SCANNER_TAGS],
            )
            uid = getattr(ds, "SeriesInstanceUID", None)
            num = int(getattr(ds, "SeriesNumber", 0))
            # Fall back to (SeriesNumber, first file's directory) when a file is
            # somehow missing the UID — keeps series from different studies apart
            # even without one, instead of silently merging on SeriesNumber alone.
            key = str(uid) if uid else f"num-{num}:{dcm_path.parent}"
            desc = getattr(ds, "SeriesDescription", "unknown")
            if key not in series:
                series[key] = {
                    "number": num, "series_instance_uid": str(uid) if uid else "",
                    "description": str(desc), "count": 0,
                    "modality": _as_str(getattr(ds, "Modality", None)),
                    "image_type": _as_str(getattr(ds, "ImageType", None)),
                    "manufacturer": _as_str(getattr(ds, "Manufacturer", None)),
                    "model": _as_str(getattr(ds, "ManufacturerModelName", None)),
                    "field_strength": _safe_float(getattr(ds, "MagneticFieldStrength", None)),
                    "software_version": _as_str(getattr(ds, "SoftwareVersions", None)),
                    "station_name": _as_str(getattr(ds, "StationName", None)),
                    "institution": _as_str(getattr(ds, "InstitutionName", None)),
                    "study_date": _as_str(getattr(ds, "StudyDate", None)),
                    "protocol_name": _as_str(getattr(ds, "ProtocolName", None)),
                }
            series[key]["count"] += 1
            dicoms_seen += 1
        except Exception:
            continue
    if on_progress is not None:
        on_progress({"files_seen": files_seen, "dicoms_seen": dicoms_seen, "series_found": len(series), "current_dir": str(root)})

    results = []
    # Numeric SeriesNumber first (the familiar order within a session), study
    # date and UID break ties between series from different studies/sessions
    # that share a number.
    for key in sorted(series, key=lambda k: (series[k]["number"], series[k].get("study_date") or "", k)):
        info = series[key]
        results.append(SeriesInfo(
            number=info["number"],
            series_instance_uid=info["series_instance_uid"],
            description=info["description"],
            n_images=info["count"],
            modality=info.get("modality"), image_type=info.get("image_type"),
            manufacturer=info.get("manufacturer"), model=info.get("model"),
            field_strength=info.get("field_strength"), software_version=info.get("software_version"),
            station_name=info.get("station_name"), institution=info.get("institution"),
            study_date=info.get("study_date"), protocol_name=info.get("protocol_name"),
        ))

    return results


# ── Internal helpers ─────────────────────────────────────────────────────

def _find_first_dicom(root: Path, *, should_stop: StopCheck | None = None) -> Path | None:
    """Find the first DICOM file in a directory tree."""
    for p in _iter_dicoms(root, should_stop=should_stop):
        return p
    return None


def _iter_dicoms(root: Path, *, should_stop: StopCheck | None = None):
    """Yield DICOM file paths from a directory tree, streaming.

    ``os.walk`` with per-directory sorting keeps the old deterministic
    order without listing the whole tree up front, so a stop check can
    end the scan within one file's worth of work.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        if should_stop is not None and should_stop():
            raise ScanCancelled()
        dirnames.sort()
        for name in sorted(filenames):
            if should_stop is not None and should_stop():
                raise ScanCancelled()
            p = Path(dirpath) / name
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
    if isinstance(val, (list, tuple)) or type(val).__name__ == "MultiValue":
        return "\\".join(str(v) for v in val)
    try:
        return str(val)
    except Exception:
        return None
