"""Build synthetic inputs and compare the web calculations with the saved replay."""

import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage

from core.csv_export import write_case_csv
from core.engine import Session, index_transform
from core.imaging import decode
from core.scene_files import append_csv_metadata, read_csv, read_mrb, write_mrb

ROOT = Path(__file__).resolve().parents[2]
QA = Path(os.environ.get("PELVIC_QA_OUTPUT", ROOT / "build" / "qa")).resolve()
if not QA.is_relative_to(ROOT):
    raise ValueError("Test output must stay inside this repository.")
REPLAY = Path(__file__).resolve().parents[1] / "tests/fixtures"


def measurements(text):
    return {
        row["name"]: row
        for row in csv.DictReader(io.StringIO(text))
        if row["section"] == "measurement"
    }


def compare(reference, observed):
    if reference.keys() != observed.keys():
        raise AssertionError(
            {
                "missing": sorted(reference.keys() - observed.keys()),
                "extra": sorted(observed.keys() - reference.keys()),
            }
        )
    max_delta = 0.0
    values = 0
    for name, previous in reference.items():
        current = observed[name]
        assert previous["units"] == current["units"], name
        for key in ("raw_value", "corrected_value_mm"):
            a, b = previous[key], current[key]
            assert bool(a) == bool(b), (name, key)
            if a:
                delta = abs(float(a) - float(b))
                assert delta <= 1e-6, (name, key, delta)
                max_delta = max(max_delta, delta)
                values += 1
    return {
        "measurements": len(reference),
        "numeric_values": values,
        "max_absolute_difference": max_delta,
    }


def synthetic_dicom(path, pixels, *, rle=False):
    uid = "1.2.826.0.1.3680043.10.543.20261117.1"
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = uid
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = SecondaryCaptureImageStorage, uid
    ds.PatientName, ds.PatientID = "Synthetic^Test", "QA"
    ds.StudyInstanceUID, ds.SeriesInstanceUID = uid + ".1", uid + ".2"
    ds.Modality = "DX"
    ds.Rows, ds.Columns = pixels.shape
    ds.PhotometricInterpretation = "MONOCHROME1"
    ds.SamplesPerPixel = 1
    ds.PixelRepresentation = 0
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 12, 11
    ds.PixelSpacing = ["0.7", "0.5"]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 0, -1]
    ds.ImagePositionPatient = [10, 20, 30]
    ds.WindowCenter, ds.WindowWidth = "1500", "3000"
    ds.PixelData = pixels.astype("<u2").tobytes()
    if rle:
        ds.compress("1.2.840.10008.1.2.5", generate_instance_uid=False)
    ds.save_as(path, enforce_file_format=True)


def make_lossless(source, dest, *, jpeg_ls=False):
    # GDCM is used only here as an independent encoder for test data.
    import gdcm

    reader = gdcm.ImageReader()
    reader.SetFileName(str(source))
    assert reader.Read()
    change = gdcm.ImageChangeTransferSyntax()
    syntax = (
        gdcm.TransferSyntax.JPEGLSLossless
        if jpeg_ls
        else gdcm.TransferSyntax.JPEGLosslessProcess14_1
    )
    change.SetTransferSyntax(gdcm.TransferSyntax(syntax))
    change.SetInput(reader.GetImage())
    assert change.Change()
    writer = gdcm.ImageWriter()
    writer.SetFile(reader.GetFile())
    writer.SetImage(change.GetOutput())
    writer.SetFileName(str(dest))
    assert writer.Write()


def make_other_formats(fixtures, gray):
    import nibabel as nib
    from pydicom import dcmread
    from pydicom.encaps import encapsulate
    from pydicom.uid import JPEG2000Lossless
    import zlib

    fixture = fixtures / "input/02-synthetic.dcm"
    buf = io.BytesIO()
    Image.fromarray(gray).save(buf, format="JPEG2000", no_jp2=True, irreversible=False)
    ds = dcmread(fixture)
    ds.file_meta.TransferSyntaxUID = JPEG2000Lossless
    ds.PixelData = encapsulate([buf.getvalue()])
    ds["PixelData"].is_undefined_length = True
    ds.save_as(fixtures / "test-j2k.dcm", enforce_file_format=True)
    raw = gray.astype("<u2").tobytes()
    h, w = gray.shape
    (fixtures / "pixels.raw").write_bytes(raw)
    header = (
        f"NRRD0004\ntype: unsigned short\ndimension: 3\nsizes: {w} {h} 1\n"
        "space: right-anterior-superior\nspace directions: (-0.5,0,0) (0,-0.7,0) (0,0,1)\n"
        "space origin: (10,20,30)\nendian: little\n"
    )
    (fixtures / "test.nrrd").write_bytes(
        (header + "encoding: gzip\n\n").encode() + gzip.compress(raw)
    )
    (fixtures / "test.nhdr").write_text(
        header + "encoding: raw\ndata file: pixels.raw\n"
    )
    meta = f"ObjectType = Image\nNDims = 3\nDimSize = {w} {h} 1\nElementSpacing = 0.5 0.7 1\nElementType = MET_USHORT\n"
    (fixtures / "test.mha").write_bytes(
        (meta + "CompressedData = True\nElementDataFile = LOCAL\n").encode()
        + zlib.compress(raw)
    )
    (fixtures / "test.mhd").write_text(meta + "ElementDataFile = pixels.raw")
    ni = nib.Nifti1Image(gray.T[..., np.newaxis], np.diag([0.5, 0.7, 1.0, 1.0]))
    ni.header.set_xyzt_units("mm")
    ni.set_qform(ni.affine, code=1)
    ni.set_sform(ni.affine, code=0)
    ni.to_filename(fixtures / "test.nii.gz")
    for filename, companion in (
        ("test.nrrd", None),
        ("test.nhdr", raw),
        ("test.mha", None),
        ("test.mhd", raw),
        ("test.nii.gz", None),
    ):
        image = decode(filename, (fixtures / filename).read_bytes(), companion)
        np.testing.assert_array_equal(image.pixels, gray)
        np.testing.assert_allclose(image.spacing, [0.5, 0.7], rtol=1e-6)


def main():
    for name in ("fixtures", "native_output"):
        target = QA / name
        assert target.resolve().is_relative_to(ROOT)
        target.mkdir(parents=True, exist_ok=True)
    fixtures = QA / "fixtures"
    if not (fixtures / "input").exists():
        (fixtures / "input").mkdir()
    input_dir = fixtures / "input"
    y, x = np.mgrid[:900, :1000]
    gray = (
        (1400 + 650 * np.cos(x / 125) + 700 * np.sin(y / 116) + 800 * (x > 601))
        .clip(0, 4095)
        .astype(np.uint16)
    )
    Image.fromarray(gray).save(input_dir / "01-synthetic.png")
    synthetic_dicom(input_dir / "02-synthetic.dcm", gray)
    synthetic_dicom(fixtures / "test-rle.dcm", gray, rle=True)
    make_lossless(input_dir / "02-synthetic.dcm", fixtures / "test-lossless.dcm")
    make_lossless(
        input_dir / "02-synthetic.dcm", fixtures / "test-jls.dcm", jpeg_ls=True
    )
    make_other_formats(fixtures, gray)
    np.testing.assert_array_equal(
        decode("rle.dcm", (fixtures / "test-rle.dcm").read_bytes()).pixels, gray
    )
    path = next(REPLAY.glob("*.mrb"))
    copyfile(path, fixtures / "SyntheticFullCase.mrb")
    copyfile(
        REPLAY / "SyntheticFullCase_reference.csv",
        fixtures / "SyntheticFullCase_reference.csv",
    )
    reference = measurements(
        (REPLAY / "SyntheticFullCase_reference.csv").read_text("utf-8-sig")
    )
    s = Session()
    s.open(path.name, path.read_bytes())
    target = QA / "browser_scene_roundtrip.mrb"
    target.write_bytes(write_mrb(s.image, s.controller, s.case_name, s.get_settings()))
    assert ZipFile(target).testzip() is None
    reopened = Session()
    reopened.open(target.name, target.read_bytes())
    result_csv = QA / "browser_recomputed.csv"
    result_csv.unlink(missing_ok=True)
    write_case_csv(result_csv, reopened.controller, path.name, "Browser software check")
    append_csv_metadata(result_csv, reopened.get_settings(), reopened.base_image)
    computed = measurements(result_csv.read_text("utf-8-sig"))
    parity = compare(reference, computed)
    recovered = read_csv(result_csv.read_bytes())
    assert len(recovered["points"]) == 83
    original = read_mrb(path.read_bytes())[1]
    assert original["settings"]["comments"] == reopened.settings.pelvic_comments
    for role, points in s.serialize()["points"].items():
        np.testing.assert_allclose(
            reopened.serialize()["points"][role], points, atol=1e-7
        )
    for turn in range(4):
        for mirror in (False, True):
            plane = np.arange(24).reshape(4, 6)
            rotated = np.rot90(plane, -turn)
            if mirror:
                rotated = np.fliplr(rotated)
            inv = index_transform(plane.shape, turn, mirror)
            for j, i in np.ndindex(rotated.shape):
                old_i, old_j = map(int, (inv @ [i, j, 0, 1])[:2])
                assert rotated[j, i] == plane[old_j, old_i]
    evidence = {
        "status": "passed",
        "patient_data": False,
        "prior_replay_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "csv_measurement_comparison": parity,
        "editable_roles_roundtrip": len(recovered["points"]),
        "reorientation_index_mappings": 8,
    }
    (QA / "core_checks.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
