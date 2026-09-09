"""list_series reports DICOM attributes verbatim — nothing inferred."""

from __future__ import annotations

import pytest

pydicom = pytest.importorskip("pydicom")

from fmriflow.convert.dicom_utils import list_series  # noqa: E402


def _write(path, *, series_number, description, modality="MR",
           image_type=("ORIGINAL", "PRIMARY", "M", "ND"), model="Prisma"):
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SeriesNumber = series_number
    ds.SeriesDescription = description
    ds.Modality = modality
    ds.ImageType = list(image_type)
    ds.Manufacturer = "SIEMENS"
    ds.ManufacturerModelName = model
    ds.MagneticFieldStrength = 3
    ds.StationName = "MR1"
    ds.StudyDate = "20200101"
    ds.ProtocolName = "proto"
    ds.save_as(str(path), write_like_original=False)


def test_series_carry_modality_and_image_type_verbatim(tmp_path):
    _write(tmp_path / "a.dcm", series_number=3, description="localizer_haste")
    _write(tmp_path / "b.dcm", series_number=3, description="localizer_haste")
    _write(tmp_path / "c.dcm", series_number=7, description="anything", modality="OT",
           image_type=("DERIVED", "SECONDARY"), model="TrioTim")

    series = {s.number: s for s in list_series(tmp_path)}
    assert set(series) == {3, 7}
    assert series[3].n_images == 2
    assert series[3].modality == "MR"
    assert series[3].image_type == "ORIGINAL\\PRIMARY\\M\\ND"
    assert series[3].description == "localizer_haste"
    assert series[7].modality == "OT"
    assert series[7].image_type == "DERIVED\\SECONDARY"
    assert series[7].model == "TrioTim"
    assert series[7].field_strength == 3.0
    assert series[7].protocol_name == "proto"
    # No inferred field survives on the record.
    assert not hasattr(series[3], "modality_guess")
