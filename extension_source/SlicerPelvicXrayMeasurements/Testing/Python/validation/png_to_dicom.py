#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    PYDICOM_IMPLEMENTATION_UID,
    SecondaryCaptureImageStorage,
    generate_uid,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the PNG-to-DICOM converter."""

    parser = argparse.ArgumentParser(
        description="Convert a PNG image to a DICOM Secondary Capture file."
    )

    parser.add_argument(
        "--png-path",
        required=True,
        help="Path to the input PNG image.",
    )
    parser.add_argument(
        "--dcm-path",
        required=True,
        help="Path to the output DICOM file.",
    )
    parser.add_argument(
        "--row-spacing-mm",
        type=float,
        default=0.2,
        help="Pixel spacing in mm for rows (vertical spacing). Default: 0.2",
    )
    parser.add_argument(
        "--col-spacing-mm",
        type=float,
        default=0.2,
        help="Pixel spacing in mm for columns (horizontal spacing). Default: 0.2",
    )
    parser.add_argument(
        "--mode",
        choices=["L", "RGB"],
        default="L",
        help="Image mode to use when loading the PNG. 'L' = grayscale, 'RGB' = color. Default: L",
    )
    parser.add_argument(
        "--patient-name",
        default="Anonymous",
        help="PatientName value for the DICOM. Default: Anonymous",
    )
    parser.add_argument(
        "--patient-id",
        default="000000",
        help="PatientID value for the DICOM. Default: 000000",
    )
    parser.add_argument(
        "--modality",
        default="SC",
        help="DICOM Modality. Default: SC",
    )
    parser.add_argument(
        "--conversion-type",
        default="WSD",
        help="DICOM ConversionType. Default: WSD",
    )

    return parser.parse_args()


def main() -> None:
    """Convert the requested PNG file into a DICOM Secondary Capture file."""

    args = parse_args()

    png_path = Path(args.png_path).expanduser().resolve()
    dcm_path = Path(args.dcm_path).expanduser().resolve()

    if not png_path.exists():
        raise FileNotFoundError(f"Input PNG not found: {png_path}")

    img = Image.open(png_path).convert(args.mode)
    arr = np.array(img, dtype=np.uint8)

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

    ds = FileDataset(str(dcm_path), {}, file_meta=file_meta, preamble=b"\0" * 128)

    now = datetime.now()
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()

    ds.Modality = args.modality
    ds.ConversionType = args.conversion_type
    ds.PatientName = args.patient_name
    ds.PatientID = args.patient_id

    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime

    if args.mode == "L":
        if arr.ndim != 2:
            raise ValueError("Expected a 2D grayscale image array for mode 'L'.")

        ds.Rows, ds.Columns = arr.shape
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"

    elif args.mode == "RGB":
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError("Expected an RGB image array with shape (rows, cols, 3).")

        ds.Rows, ds.Columns, _ = arr.shape
        ds.SamplesPerPixel = 3
        ds.PhotometricInterpretation = "RGB"
        ds.PlanarConfiguration = 0

    else:
        raise ValueError(f"Unsupported mode: {args.mode}")

    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelSpacing = [str(args.row_spacing_mm), str(args.col_spacing_mm)]
    ds.PixelData = arr.tobytes()

    ds.save_as(str(dcm_path), write_like_original=False)
    print(f"Saved DICOM to: {dcm_path}")


if __name__ == "__main__":
    main()
