"""list_series reports DICOM attributes verbatim — nothing inferred."""

from __future__ import annotations

import pytest

pydicom = pytest.importorskip("pydicom")

from fmriflow.convert.dicom_utils import list_series  # noqa: E402


def _write(path, *, series_number, description, modality="MR",
           image_type=("ORIGINAL", "PRIMARY", "M", "ND"), model="Prisma",
           series_uid=None, study_date="20200101"):
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SeriesNumber = series_number
    ds.SeriesInstanceUID = series_uid or generate_uid()
    ds.SeriesDescription = description
    ds.Modality = modality
    ds.ImageType = list(image_type)
    ds.Manufacturer = "SIEMENS"
    ds.ManufacturerModelName = model
    ds.MagneticFieldStrength = 3
    ds.StationName = "MR1"
    ds.StudyDate = study_date
    ds.ProtocolName = "proto"
    ds.save_as(str(path), write_like_original=False)


def test_series_carry_modality_and_image_type_verbatim(tmp_path):
    from pydicom.uid import generate_uid
    series3_uid = generate_uid()
    _write(tmp_path / "a.dcm", series_number=3, description="localizer_haste", series_uid=series3_uid)
    _write(tmp_path / "b.dcm", series_number=3, description="localizer_haste", series_uid=series3_uid)
    _write(tmp_path / "c.dcm", series_number=7, description="anything", modality="OT",
           image_type=("DERIVED", "SECONDARY"), model="TrioTim")

    series = {s.number: s for s in list_series(tmp_path)}
    assert set(series) == {3, 7}
    assert series[3].n_images == 2
    assert series[3].modality == "MR"
    assert series[3].image_type == "ORIGINAL\\PRIMARY\\M\\ND"
    assert series[3].description == "localizer_haste"
    assert series[3].series_instance_uid == series3_uid
    assert series[7].modality == "OT"
    assert series[7].image_type == "DERIVED\\SECONDARY"
    assert series[7].model == "TrioTim"
    assert series[7].field_strength == 3.0
    assert series[7].protocol_name == "proto"
    # No inferred field survives on the record.
    assert not hasattr(series[3], "modality_guess")


def test_duplicate_series_numbers_across_sessions_stay_distinct(tmp_path):
    """SeriesNumber only has to be unique *within one study* — a directory that
    holds DICOMs from two sessions (each restarting their own numbering) must
    not merge same-numbered series from different sessions into one record."""
    from pydicom.uid import generate_uid

    session1 = tmp_path / "20200101" / "series3"
    session1.mkdir(parents=True)
    session2 = tmp_path / "20200215" / "series3"
    session2.mkdir(parents=True)

    uid1, uid2 = generate_uid(), generate_uid()
    _write(session1 / "a.dcm", series_number=3, description="bold_run1",
           series_uid=uid1, study_date="20200101")
    _write(session1 / "b.dcm", series_number=3, description="bold_run1",
           series_uid=uid1, study_date="20200101")
    _write(session2 / "a.dcm", series_number=3, description="bold_run1_rescan",
           series_uid=uid2, study_date="20200215")

    series = list_series(tmp_path)
    by_uid = {s.series_instance_uid: s for s in series}

    # Two distinct records, not one merged-and-overwritten record.
    assert len(series) == 2
    assert {s.number for s in series} == {3}          # both really are "series 3"
    assert set(by_uid) == {uid1, uid2}

    first = by_uid[uid1]
    second = by_uid[uid2]
    assert first.n_images == 2 and first.description == "bold_run1" and first.study_date == "20200101"
    assert second.n_images == 1 and second.description == "bold_run1_rescan" and second.study_date == "20200215"
