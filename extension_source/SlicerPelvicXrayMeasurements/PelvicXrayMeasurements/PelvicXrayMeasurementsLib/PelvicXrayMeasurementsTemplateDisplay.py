"""Read AP film geometry and display the manufacturer's PNG in Slicer slice views."""
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
import qt
import slicer
import vtk

import PelvicXrayMeasurementsPlanning as planning
from PelvicXrayMeasurementsGeometry import image_right_direction, image_up_direction


def configure_volume(volume, path=None, *, loading=False):
    if volume is None or (not loading and volume.GetAttribute(planning.METRIC_ATTRIBUTE) is not None):
        return
    patient, detector, orientation, labels = None, None, None, None
    storage = volume.GetStorageNode()
    source = str(path or (storage.GetFileName() if storage else "") or "")
    uid = (volume.GetAttribute("DICOM.instanceUIDs") or "").split()
    metric = False
    if source and Path(source).is_file():
        from pydicom import dcmread
        from pydicom.misc import is_dicom
        if Path(source).suffix.lower() in (".dcm", ".dicom", ".ima") or is_dicom(source):
            from pydicom.errors import InvalidDicomError
            try:
                ds = dcmread(source, stop_before_pixels=True, force=True,
                             specific_tags=["PixelSpacing","ImagerPixelSpacing","ImageOrientationPatient","PatientOrientation"])
                patient, detector = ds.get("PixelSpacing"), ds.get("ImagerPixelSpacing")
                orientation, labels = ds.get("ImageOrientationPatient"), ds.get("PatientOrientation")
            except (OSError, InvalidDicomError, ValueError):
                pass
        elif source.lower().endswith((".nrrd", ".nhdr", ".mha", ".mhd", ".nii", ".nii.gz")):
            metric = True
    if uid and patient is None and getattr(slicer, "dicomDatabase", None):
        fields = [slicer.dicomDatabase.instanceValue(uid[0], tag) for tag in
                  ("0028,0030", "0018,1164", "0020,0037", "0020,0020")]
        patient, detector, orientation, labels = [v.split("\\") if v else None for v in fields]
    if patient is not None or detector is not None:
        pitch, metric = planning.dicom_spacing(patient, detector)
        # A projection reader can default to 1 mm or to the detector pitch.
        # Set the original column/row pitch before adding any landmarks.
        if loading:
            volume.SetSpacing(*pitch, volume.GetSpacing()[2])
        elif not np.allclose(volume.GetSpacing()[:2], pitch, rtol=1e-4):
            metric = False
    axes = planning.dicom_ap_axes(orientation, labels)
    volume.SetAttribute(planning.METRIC_ATTRIBUTE, "1" if metric else "0")
    volume.SetAttribute(planning.AP_AXES_ATTRIBUTE, json.dumps(axes))


def scale(volume, ball):
    if volume is None:
        return None
    configure_volume(volume)
    return planning.template_scale(ball, volume.GetAttribute(planning.METRIC_ATTRIBUTE) == "1")


def axes(volume):
    configure_volume(volume)
    basis = np.array([image_right_direction(volume), -image_up_direction(volume)])
    return np.asarray(json.loads(volume.GetAttribute(planning.AP_AXES_ATTRIBUTE) or json.dumps(planning.STANDARD_AP))) @ basis


@lru_cache(maxsize=4)
def texture(digest):
    raw = planning.artwork_bytes(digest)
    image = qt.QImage.fromData(qt.QByteArray(raw), "PNG")
    if image.isNull():
        raise ValueError("The selected implant PNG cannot be opened.")
    data = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(image, data)
    tex = vtk.vtkTexture()
    tex.SetInputData(data)
    tex.InterpolateOn()
    tex.RepeatOff()
    tex.EdgeClampOn()
    return tex


@lru_cache(maxsize=4)
def hit_grid(digest):
    from vtk.util.numpy_support import vtk_to_numpy
    data = texture(digest).GetInput()
    w, h, _ = data.GetDimensions()
    rgba = vtk_to_numpy(data.GetPointData().GetScalars()).reshape(h, w, 4)
    return planning.artwork_hit_grid(rgba[::-1, :, 3])


def hits_artwork(digest, point, corners):
    a, b, _, d = corners
    basis = np.column_stack((b - a, d - a))
    if abs(np.linalg.det(basis)) < 1e-8:
        return False
    u, v = np.linalg.solve(basis, point - a)
    if not (0 <= u < 1 and 0 <= v < 1):
        return False
    grid = hit_grid(digest)
    return bool(grid[int(v * grid.shape[0]), int(u * grid.shape[1])])


def textured_quad(digest):
    raw = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetNumberOfPoints(4)
    raw.SetPoints(points)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(4)
    uv = vtk.vtkFloatArray()
    uv.SetNumberOfComponents(2)
    for i, (u, v) in enumerate(((0, 1), (1, 1), (1, 0), (0, 0))):
        cells.InsertCellPoint(i)
        uv.InsertNextTuple2(u, v)
    raw.SetPolys(cells)
    raw.GetPointData().SetTCoords(uv)
    mapper = vtk.vtkPolyDataMapper2D()
    mapper.SetInputData(raw)
    actor = vtk.vtkTexturedActor2D()
    actor.SetMapper(mapper)
    actor.SetTexture(texture(digest))
    actor.PickableOff()
    return actor


def sync_artwork(logic, renderer, slice_node, actors):
    matrix = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Invert(slice_node.GetXYToRAS(), matrix)
    visible = set()
    for side in ("left", "right"):
        for kind in planning.COMPONENTS:
            role = logic.side_role(planning.ROTATION_ROLES[kind] + "Outline", side)
            node = logic.get_node(role)
            digest = node.GetAttribute("PXM.TemplateArtwork")
            frame = node.GetPolyData()
            if not digest or not node.GetDisplayVisibility() or not frame or frame.GetNumberOfPoints() != 4:
                continue
            visible.add(role)
            if role not in actors or actors[role][0] != digest:
                if role in actors:
                    renderer.RemoveActor2D(actors[role][1])
                actor = textured_quad(digest)
                actors[role] = (digest, actor)
                renderer.AddActor2D(actor)
            actor = actors[role][1]
            quad = actor.GetMapper().GetInput().GetPoints()
            for j in range(4):
                x, y, _, _ = matrix.MultiplyPoint([*frame.GetPoint(j), 1])
                quad.SetPoint(j, x, y, 0.)
            quad.Modified()
    for role in actors.keys() - visible:
        renderer.RemoveActor2D(actors.pop(role)[1])

