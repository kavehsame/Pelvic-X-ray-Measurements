"""Decode single-plane radiographs from bytes already selected in Chrome."""

from dataclasses import dataclass, replace
import gzip
import io
import math
from pathlib import PurePosixPath
import re
import struct
import zlib

import numpy as np
from PIL import Image

MAX_PIXELS = 40_000_000
MAX_FILE = 200_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
NRRD_TYPES = {
    "unsigned char": "u1",
    "uint8": "u1",
    "uint8_t": "u1",
    "uchar": "u1",
    "signed char": "i1",
    "int8": "i1",
    "int8_t": "i1",
    "char": "i1",
    "short": "i2",
    "short int": "i2",
    "signed short": "i2",
    "int16": "i2",
    "int16_t": "i2",
    "ushort": "u2",
    "unsigned short": "u2",
    "unsigned short int": "u2",
    "uint16": "u2",
    "uint16_t": "u2",
    "int": "i4",
    "int32": "i4",
    "int32_t": "i4",
    "unsigned int": "u4",
    "uint": "u4",
    "uint32": "u4",
    "int64": "i8",
    "long long": "i8",
    "uint64": "u8",
    "unsigned long long": "u8",
    "float": "f4",
    "double": "f8",
}
META_TYPES = {
    "MET_CHAR": "i1",
    "MET_UCHAR": "u1",
    "MET_SHORT": "i2",
    "MET_USHORT": "u2",
    "MET_INT": "i4",
    "MET_UINT": "u4",
    "MET_FLOAT": "f4",
    "MET_DOUBLE": "f8",
}
NIFTI_TYPES = {2: "u1", 4: "i2", 8: "i4", 16: "f4", 64: "f8", 256: "i1", 512: "u2", 768: "u4", 1024: "i8", 1280: "u8"}
RASTER = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
LOSSLESS_JPEG = {"1.2.840.10008.1.2.4.57", "1.2.840.10008.1.2.4.70"}
JPEG_LS = {"1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81"}
JPEG_2000 = {"1.2.840.10008.1.2.4.90", "1.2.840.10008.1.2.4.91"}


@dataclass
class Radiograph:
    pixels: np.ndarray
    spacing: tuple
    source_affine: np.ndarray | None
    format: str
    inverted: bool = False
    window: tuple | None = None
    padding: float | None = None
    physical_spacing: bool = False

    @property
    def shape(self):
        return self.pixels.shape

    def native_affine(self):
        """Flatten to the same radiographic XY convention as desktop raster import."""
        h, w = self.shape
        sx, sy = self.spacing
        return np.array([[-sx, 0, 0, (w - 1) * sx], [0, -sy, 0, (h - 1) * sy], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)


def check_plane(sizes):
    if len(sizes) < 2 or min(sizes[:2]) < 2 or any(s != 1 for s in sizes[2:]):
        raise ValueError("Choose a single 2D radiograph. This image contains multiple slices or frames.")
    if math.prod(sizes) > MAX_PIXELS or max(sizes[:2]) > 16384:
        raise ValueError("This radiograph is larger than the browser edition can open.")


def spacing_pair(values):
    out = tuple(abs(float(x)) for x in values[:2])
    return out if len(out) == 2 and all(math.isfinite(x) and x > 1e-6 for x in out) else (1.0, 1.0)


def check_matrix(value):
    matrix = np.asarray(value, dtype=float)
    if (
        matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix[3], [0, 0, 0, 1])
        or abs(np.linalg.det(matrix[:3, :3])) < 1e-12
    ):
        raise ValueError("The image coordinate frame is invalid.")
    return matrix


def space_affine(columns, origin, space):
    axes = np.asarray(columns, dtype=float).T
    if axes.shape == (3, 2):
        normal = np.cross(axes[:, 0], axes[:, 1])
        axes = np.column_stack((axes, normal / np.linalg.norm(normal)))
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = axes, origin
    if space in {"left-posterior-superior", "lps"}:
        matrix[:2] *= -1
    elif space in {"left-anterior-superior", "las"}:
        matrix[0] *= -1
    elif space not in {"right-anterior-superior", "ras"}:
        return None
    return check_matrix(matrix)


def split_header(raw):
    match = re.search(rb"\r?\n\r?\n", raw[:65536])
    if not match:
        raise ValueError("The image header is missing or larger than expected.")
    return raw[: match.start()].decode("ascii"), raw[match.end() :]


def scalar_payload(payload, sizes, dtype, encoding):
    count = math.prod(sizes)
    expected = count * dtype.itemsize
    if encoding in {"gz", "gzip"}:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
            payload = stream.read(expected + 1)
    elif encoding in {"zlib", "deflate"}:
        decoder = zlib.decompressobj()
        payload = decoder.decompress(payload, expected + 1)
        if not decoder.eof:
            raise ValueError("Compressed image data are incomplete or larger than expected.")
    elif encoding in {"ascii", "text", "txt"}:
        pixels = np.fromstring(payload.decode("ascii"), sep=" ", dtype=dtype)
        if pixels.size != count:
            raise ValueError("The image header and pixel data sizes differ.")
        return pixels.reshape(sizes[1], sizes[0])
    elif encoding != "raw":
        raise ValueError(f"Unsupported image encoding: {encoding}.")
    if len(payload) != expected:
        raise ValueError("The image header and pixel data sizes differ.")
    return np.frombuffer(payload, dtype=dtype).reshape(sizes[1], sizes[0])


def nrrd(raw, companion=None):
    if companion is not None and not re.search(rb"\r?\n\r?\n", raw[:65536]):
        header, payload = raw[:65536].decode("ascii"), b""
    else:
        header, payload = split_header(raw)
    if not header.startswith("NRRD000"):
        raise ValueError("This is not a NRRD radiograph.")
    fields = dict(
        tuple(s.strip().lower() if i == 0 else s.strip() for i, s in enumerate(line.split(":", 1)))
        for line in header.splitlines()[1:]
        if ":" in line and not line.lstrip().startswith("#")
    )
    sizes = list(map(int, fields["sizes"].split()))
    check_plane(sizes)
    if fields.get("data file") or fields.get("datafile"):
        if companion is None:
            raise ValueError("Select the detached NRRD header and its pixel file together.")
        payload = companion
    if fields.get("byte skip", "0") != "0" or fields.get("line skip", "0") != "0":
        raise ValueError("This NRRD uses unsupported byte or line offsets.")
    dtype = np.dtype(NRRD_TYPES[fields["type"].lower()]).newbyteorder(">" if fields.get("endian") == "big" else "<")
    columns = [
        list(map(float, entry.split(","))) for entry in re.findall(r"\(([^)]+)\)", fields.get("space directions", ""))
    ]
    spacing = (
        spacing_pair([np.linalg.norm(v) for v in columns])
        if columns
        else spacing_pair(fields.get("spacings", "1 1").split())
    )
    affine = None
    if len(columns) in {2, 3} and len(columns[0]) == 3 and "space origin" in fields:
        origin = list(map(float, fields["space origin"].strip("()").split(",")))
        affine = space_affine(columns, origin, fields.get("space", "").lower())
    pixels = scalar_payload(payload, sizes, dtype, fields.get("encoding", "raw").lower())
    return Radiograph(pixels, spacing, affine, "NRRD", physical_spacing=bool(columns or "spacings" in fields))


def metaimage(raw, companion=None):
    match = re.search(rb"(?m)^ElementDataFile[ \t]*=[ \t]*([^\r\n]+)(?:\r?\n|$)", raw[:65536])
    if not match:
        raise ValueError("The MetaImage header does not identify its pixel data.")
    local = match[1].strip().upper() == b"LOCAL"
    header = raw[: match.start()].decode("ascii")
    fields = dict(tuple(s.strip() for s in line.split("=", 1)) for line in header.splitlines() if "=" in line)
    sizes = list(map(int, fields["DimSize"].split()))
    check_plane(sizes)
    if fields.get("ElementNumberOfChannels", "1") != "1" or fields.get("HeaderSize", "0") != "0":
        raise ValueError("This MetaImage uses unsupported channels or byte offsets.")
    payload = raw[match.end() :] if local else companion
    if payload is None:
        raise ValueError("Select the MetaImage header and its pixel file together.")
    dtype = np.dtype(META_TYPES[fields["ElementType"]]).newbyteorder(
        ">" if fields.get("BinaryDataByteOrderMSB", fields.get("ElementByteOrderMSB", "")).lower() == "true" else "<"
    )
    encoding = (
        "zlib"
        if fields.get("CompressedData", "").lower() == "true"
        else ("ascii" if fields.get("BinaryData", "true").lower() == "false" else "raw")
    )
    spacings = list(map(float, fields.get("ElementSpacing", "1 1").split()))
    affine = None
    if len(sizes) == 3 and len(spacings) == 3:
        directions = np.array(list(map(float, fields.get("TransformMatrix", "1 0 0 0 1 0 0 0 1").split()))).reshape(
            (3, 3)
        )
        origin = list(map(float, fields.get("Offset", fields.get("Position", fields.get("Origin", "0 0 0"))).split()))
        affine = space_affine(directions * np.array(spacings)[:, None], origin, "lps")
    return Radiograph(
        scalar_payload(payload, sizes, dtype, encoding),
        spacing_pair(spacings),
        affine,
        "MetaImage",
        physical_spacing="ElementSpacing" in fields,
    )


def nifti(raw, compressed):
    stream = gzip.GzipFile(fileobj=io.BytesIO(raw)) if compressed else io.BytesIO(raw)
    with stream:
        header = stream.read(352)
        if len(header) < 352 or header[344:348] != b"n+1\x00":
            raise ValueError("Open a single-file NIfTI-1 radiograph (.nii or .nii.gz).")
        order = "<" if struct.unpack_from("<i", header)[0] == 348 else ">"
        get = lambda fmt, offset: struct.unpack_from(order + fmt, header, offset)
        if get("i", 0)[0] != 348:
            raise ValueError("Invalid NIfTI-1 header.")
        dims = get("8h", 40)
        if not 2 <= dims[0] <= 7:
            raise ValueError("Invalid NIfTI dimensions.")
        sizes = dims[1 : 1 + dims[0]]
        check_plane(sizes)
        pixdim = get("8f", 76)
        spacing = spacing_pair(pixdim[1:])
        units = {1: 1000.0, 2: 1.0, 3: 0.001}.get(header[123] & 7)
        offset = int(get("f", 108)[0])
        if not 352 <= offset <= 4_000_000:
            raise ValueError("Invalid NIfTI pixel offset.")
        dtype = np.dtype(NIFTI_TYPES[get("h", 70)[0]]).newbyteorder(order)
        stream.seek(offset)
        pixels = scalar_payload(stream.read(math.prod(sizes) * dtype.itemsize), sizes, dtype, "raw")
        slope, intercept = get("2f", 112)
        if slope and math.isfinite(slope) and math.isfinite(intercept) and (slope, intercept) != (1, 0):
            pixels = pixels.astype(np.float32) * slope + intercept
        affine = None
        candidate = None
        if get("h", 254)[0] > 0:
            candidate = np.eye(4)
            candidate[:3] = [get("4f", n) for n in (280, 296, 312)]
        elif get("h", 252)[0] > 0:
            b, c, d = get("3f", 256)
            norm_sq = b * b + c * c + d * d
            if norm_sq > 1:
                b, c, d = np.asarray([b, c, d]) / math.sqrt(norm_sq)
            a = math.sqrt(max(0, 1 - norm_sq))
            rotation = np.array(
                [
                    [a * a + b * b - c * c - d * d, 2 * (b * c - a * d), 2 * (b * d + a * c)],
                    [2 * (b * c + a * d), a * a + c * c - b * b - d * d, 2 * (c * d - a * b)],
                    [2 * (b * d - a * c), 2 * (c * d + a * b), a * a + d * d - c * c - b * b],
                ]
            )
            candidate = np.eye(4)
            candidate[:3, :3] = rotation * [*spacing, abs(pixdim[3] or 1) * (-1 if pixdim[0] < 0 else 1)]
            candidate[:3, 3] = get("3f", 268)
        if candidate is not None:
            if units:
                candidate[:3] *= units
            affine = check_matrix(candidate)
            # A valid sform supplies the coordinate frame even when pixdim is
            # stale. Use the same frame for measurements and display aspect.
            spacing = spacing_pair(np.linalg.norm(affine[:3, :2], axis=0))
        elif units:
            spacing = tuple(x * units for x in spacing)
        return Radiograph(pixels, spacing, affine, "NIfTI", physical_spacing=bool(units))


def first_number(value):
    if hasattr(value, "__len__") and not isinstance(value, str):
        value = value[0] if len(value) else None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def dicom(raw):
    from pydicom import dcmread
    from pydicom.errors import InvalidDicomError
    from pydicom.uid import ImplicitVRLittleEndian

    try:
        ds = dcmread(io.BytesIO(raw))
    except InvalidDicomError:
        ds = dcmread(io.BytesIO(raw), force=True)
    if "Rows" not in ds or "Columns" not in ds or "PixelData" not in ds:
        raise ValueError("The DICOM file does not contain a radiograph.")
    w, h, frames = int(ds.Columns), int(ds.Rows), int(ds.get("NumberOfFrames") or 1)
    check_plane((w, h, frames))
    if int(ds.get("SamplesPerPixel", 1)) != 1 or ds.get("PhotometricInterpretation") not in {
        "MONOCHROME1",
        "MONOCHROME2",
    }:
        raise ValueError("Use a single-frame monochrome DICOM radiograph.")
    if "TransferSyntaxUID" not in ds.file_meta:
        if not ds.original_encoding[0] or not ds.original_encoding[1]:
            raise ValueError("The DICOM file does not specify its transfer syntax.")
        ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    syntax = str(ds.file_meta.TransferSyntaxUID)
    if syntax in LOSSLESS_JPEG | JPEG_LS | JPEG_2000:
        from pydicom.encaps import get_frame
        from worker_codecs import decode_compressed

        if int(ds.BitsAllocated) not in {8, 16} or not 1 <= int(ds.BitsStored) <= int(ds.BitsAllocated):
            raise ValueError("The compressed DICOM uses an unsupported bit depth.")
        frame = get_frame(ds.PixelData, 0, number_of_frames=1)
        dtype = np.dtype("<u2" if int(ds.BitsAllocated) == 16 else "u1")
        codec = "lossless" if syntax in LOSSLESS_JPEG else "jls" if syntax in JPEG_LS else "j2k"
        try:
            decoded = decode_compressed(memoryview(frame), w, h, dtype.itemsize, codec)
        except Exception as exc:
            raise ValueError("The compressed DICOM frame is invalid or uses an unsupported encoding.") from exc
        if hasattr(decoded, "to_py"):
            decoded = decoded.to_py()
        pixels = np.frombuffer(decoded, dtype=dtype).reshape(h, w)
        if int(ds.PixelRepresentation) == 1:
            shift = dtype.itemsize * 8 - int(ds.BitsStored)
            pixels = (pixels << shift).view(np.dtype(f"<i{dtype.itemsize}")) >> shift
        else:
            pixels = pixels & ((1 << int(ds.BitsStored)) - 1)
    else:
        try:
            pixels = ds.pixel_array
        except (NotImplementedError, RuntimeError) as exc:
            raise ValueError(
                f"Chrome could not decode this DICOM transfer syntax ({syntax}). "
                "Export this radiograph as uncompressed DICOM or a lossless image."
            ) from exc
    if pixels.shape != (h, w):
        raise ValueError("The DICOM pixel dimensions do not match the header.")
    slope = first_number(ds.get("RescaleSlope", 1))
    intercept = first_number(ds.get("RescaleIntercept", 0))
    slope, intercept = (1 if slope is None else slope), (0 if intercept is None else intercept)
    if (slope, intercept) != (1, 0):
        pixels = pixels.astype(np.float32) * slope + intercept
    padding = first_number(ds.get("PixelPaddingValue"))
    center, width = first_number(ds.get("WindowCenter")), first_number(ds.get("WindowWidth"))
    window = (
        (center - width / 2, center + width / 2) if center is not None and width is not None and width > 0 else None
    )
    measured = ds.get("PixelSpacing", ds.get("ImagerPixelSpacing"))
    spacing = spacing_pair(measured[::-1]) if measured is not None else (1.0, 1.0)
    source = None
    if ds.get("ImageOrientationPatient") and ds.get("ImagePositionPatient"):
        row, column = np.asarray(ds.ImageOrientationPatient, dtype=float).reshape(2, 3)
        source = space_affine((row * spacing[0], column * spacing[1]), ds.ImagePositionPatient, "lps")
    return Radiograph(
        pixels,
        spacing,
        source,
        "DICOM",
        ds.PhotometricInterpretation == "MONOCHROME1",
        window,
        None if padding is None else padding * slope + intercept,
        measured is not None,
    )


def decode(name, raw, companion=None):
    if len(raw) > MAX_FILE:
        raise ValueError("Choose a radiograph smaller than 200 MB.")
    lname = name.lower()
    suffix = PurePosixPath(lname).suffix
    if suffix in RASTER:
        with Image.open(io.BytesIO(raw)) as image:
            check_plane(image.size)
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Choose a single-page radiograph.")
            pixels = np.asarray(image if image.mode in {"I;16", "I;16L", "I;16B", "I", "F"} else image.convert("L"))
        result = Radiograph(pixels, (1.0, 1.0), None, suffix[1:].upper())
    elif suffix in {".nrrd", ".nhdr"} or raw.startswith(b"NRRD000"):
        result = nrrd(raw, companion)
    elif suffix in {".mha", ".mhd"}:
        result = metaimage(raw, companion)
    elif lname.endswith((".nii", ".nii.gz")):
        result = nifti(raw, lname.endswith(".gz"))
    elif suffix in {".dcm", ".dicom", ".ima", ""} or raw[128:132] == b"DICM":
        result = dicom(raw)
    else:
        raise ValueError("Choose a DICOM, raster image or supported single-slice volume.")
    if not np.isfinite(result.pixels).all():
        raise ValueError("The radiograph contains non-finite pixel values.")
    return result


def reorient(image, turns, mirrored):
    """Rotate clockwise in quarter turns, then mirror in the displayed horizontal direction."""
    turns = int(turns) % 4
    data = np.rot90(image.pixels, -turns)
    if mirrored:
        data = np.fliplr(data)
    spacing = image.spacing[::-1] if turns % 2 else image.spacing
    return replace(image, pixels=np.ascontiguousarray(data), spacing=spacing)


def default_window(image):
    # The sampled percentiles bound windowing time and avoid outlier pixels.
    stride = max(1, int(math.sqrt(image.pixels.size / 160_000)))
    sample = image.pixels[::stride, ::stride]
    if image.padding is not None:
        sample = sample[sample != image.padding]
    if sample.size == 0:
        sample = image.pixels[::stride, ::stride]
    lo, hi = map(float, np.percentile(sample, (0.5, 99.5)))
    if hi <= lo:
        lo, hi = float(sample.min()), float(sample.max())
    if hi <= lo:
        hi = lo + 1.0
    window = image.window or (lo, hi)
    return min(lo, window[0]), max(hi, window[1]), window


def display_png(image, low, high, invert):
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        raise ValueError("Window minimum must be less than its maximum.")
    gray = image.pixels.astype(np.float32, copy=True)
    gray -= low
    gray *= 255.0 / (high - low)
    np.clip(gray, 0, 255, out=gray)
    gray = gray.astype(np.uint8)
    if bool(invert):
        np.bitwise_not(gray, out=gray)
    buffer = io.BytesIO()
    Image.fromarray(gray).save(buffer, format="PNG", compress_level=2)
    return buffer.getvalue()
