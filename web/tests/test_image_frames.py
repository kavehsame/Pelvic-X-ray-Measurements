"""Check stored image geometry against independent imaging libraries."""

import numpy as np
import pytest

from core.imaging import decode


@pytest.mark.parametrize("suffix", [".mha", ".nrrd", ".nii.gz"])
def test_rotated_anisotropic_image_matches_itk(tmp_path, suffix):
    import SimpleITK as sitk

    pixels = np.arange(240, dtype=np.uint16).reshape(1, 12, 20)
    source = sitk.GetImageFromArray(pixels)
    source.SetSpacing((0.5, 0.7, 1.5))
    source.SetOrigin((11, 13, 17))
    angle = 0.4
    source.SetDirection(
        (np.cos(angle), -np.sin(angle), 0, np.sin(angle), np.cos(angle), 0, 0, 0, 1)
    )
    path = tmp_path / ("rotated" + suffix)
    sitk.WriteImage(source, str(path))
    expected = sitk.ReadImage(str(path))
    loaded = decode(path.name, path.read_bytes())
    np.testing.assert_array_equal(loaded.pixels, sitk.GetArrayFromImage(expected)[0])
    np.testing.assert_allclose(loaded.spacing, expected.GetSpacing()[:2], rtol=1e-6)
    for index in ((0, 0, 0), (9, 5, 0), (19, 11, 0)):
        ras = np.asarray(expected.TransformIndexToPhysicalPoint(index)) * [-1, -1, 1]
        np.testing.assert_allclose(
            (loaded.source_affine @ [*index, 1])[:3], ras, atol=1e-5
        )


def test_nifti_sform_controls_pixel_spacing(tmp_path):
    import nibabel as nib

    pixels = np.arange(240, dtype=np.float32).reshape(20, 12, 1)
    affine = np.diag([0.5, 0.7, 1, 1])
    source = nib.Nifti1Image(pixels, affine)
    source.header.set_xyzt_units("mm")
    source.set_sform(affine, code=1)
    source.header.set_zooms((1, 1, 1))
    path = tmp_path / "sform.nii"
    source.to_filename(path)
    expected = nib.load(path)
    loaded = decode(path.name, path.read_bytes())
    np.testing.assert_allclose(
        loaded.spacing, nib.affines.voxel_sizes(expected.affine)[:2]
    )
