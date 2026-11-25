"""In-memory radiograph and markups used by the shared geometry in Chrome.

The accessors mirror the subset of MRML consumed by the desktop calculations.
No display toolkit, virtual server, Slicer module or native VTK is loaded.
"""

from itertools import product
import math
import numpy as np


class Matrix:
    def __init__(self):
        self.values = np.eye(4)

    def SetElement(self, row, column, value):
        self.values[row, column] = value

    def GetElement(self, row, column):
        return float(self.values[row, column])

    def MultiplyPoint(self, point, output=None):
        result = (self.values @ point).tolist()
        if output is not None:
            output[:] = result
        return result


vtkMatrix4x4 = Matrix


def vtkVector3d(*coords):
    return coords


def vtk_to_numpy(scalars):
    return scalars.pixels.ravel()


class vtkStringArray:
    def __init__(self):
        self.values = []

    def GetValue(self, index):
        return self.values[index]

    def GetNumberOfValues(self):
        return len(self.values)


class CurvePath:
    def __init__(self, points=()):
        self.points = points

    def GetNumberOfPoints(self):
        return len(self.points)


def ellipse_path(center, major_direction, minor_direction, major_radius, minor_radius):
    return CurvePath(
        [
            center + major_radius * math.cos(theta) * major_direction + minor_radius * math.sin(theta) * minor_direction
            for theta in np.linspace(0, 2 * math.pi, 121)
        ]
    )


class Display:
    def __init__(self):
        self.color = (0.2, 0.7, 0.95)
        self.glyph_scale = 1.0
        self.labels = False

    def SetColor(self, *color):
        self.color = color

    def SetSelectedColor(self, *color):
        self.color = color

    def SetGlyphScale(self, value):
        self.glyph_scale = value

    def SetPointLabelsVisibility(self, value):
        self.labels = value

    def SetVisibility(self, value):
        self.owner.visible = bool(value)


class Markup:
    PositionDefined = 2

    def __init__(self, classname, name, node_id):
        self.classname = classname
        self.name = name
        self.node_id = node_id
        self.points = []
        self.labels = []
        self.attributes = {}
        self.display = Display()
        self.display.owner = self
        self.visible = True
        self.locked = False
        self.curve_type = 1
        self.segment_size = 30
        self.path = CurvePath()

    def IsA(self, classname):
        return (
            classname in {self.classname, "vtkMRMLNode"}
            or classname == "vtkMRMLMarkupsNode"
            and self.classname.startswith("vtkMRMLMarkups")
        )

    def GetID(self):
        return self.node_id

    def GetName(self):
        return self.name

    def GetAttribute(self, key):
        return self.attributes.get(key)

    def SetAttribute(self, key, value):
        if value is None:
            self.attributes.pop(key, None)
        else:
            self.attributes[key] = str(value)

    def GetAttributeNames(self, array):
        array.values[:] = sorted(self.attributes)

    def GetNumberOfControlPoints(self):
        return len(self.points)

    GetNumberOfDefinedControlPoints = GetNumberOfControlPoints

    def GetNthControlPointPositionStatus(self, index):
        return self.PositionDefined

    def GetNthControlPointPositionWorld(self, index, output):
        output[:] = self.points[index]

    def SetNthControlPointPositionWorld(self, index, *point):
        self.points[index] = np.asarray(point[0] if len(point) == 1 else point, dtype=float)

    def AddControlPointWorld(self, point):
        self.points.append(np.asarray(point, dtype=float))
        self.labels.append(f"{self.name}-{len(self.points)}")
        return len(self.points) - 1

    def RemoveNthControlPoint(self, index):
        del self.points[index]
        del self.labels[index]

    def GetNthControlPointLabel(self, index):
        return self.labels[index]

    def SetNthControlPointLabel(self, index, label):
        self.labels[index] = label

    def SetLocked(self, locked):
        self.locked = locked

    def GetLocked(self):
        return self.locked

    def SetDisplayVisibility(self, visible):
        self.visible = bool(visible)

    def CreateDefaultDisplayNodes(self):
        return self.display

    def GetDisplayNode(self):
        return self.display

    def StartModify(self):
        return None

    def EndModify(self, previous):
        pass  # Browser updates are dispatched explicitly.

    def SetNumberOfPointsPerInterpolatingSegment(self, size):
        self.segment_size = size

    def GetNumberOfPointsPerInterpolatingSegment(self):
        return self.segment_size

    def SetCurveType(self, curve_type):
        self.curve_type = curve_type

    def GetCurveType(self):
        return self.curve_type

    def SetAndObservePolyData(self, path):
        self.path = path

    def GetPolyData(self):
        return self.path


class Volume:
    def __init__(self, pixels, matrix):
        self.pixels = pixels
        self.planning_metric = False
        self.planning_axes = ((-1., 0., 0.), (0., 1., 0.))
        self.affine = matrix
        self.inverse = np.linalg.inv(matrix)

    def GetImageData(self):
        return self

    def GetPointData(self):
        return self

    def GetScalars(self):
        return self

    def GetNumberOfComponents(self):
        return 1

    def GetDimensions(self):
        return self.pixels.shape[1], self.pixels.shape[0], 1

    def GetExtent(self):
        w, h, _ = self.GetDimensions()
        return 0, w - 1, 0, h - 1, 0, 0

    def GetIJKToRASMatrix(self, matrix):
        matrix.values = self.affine.copy()

    def SetIJKToRASMatrix(self, matrix):
        self.affine = matrix.values.copy()
        self.inverse = np.linalg.inv(self.affine)

    def GetRASToIJKMatrix(self, matrix):
        matrix.values = self.inverse.copy()

    def GetRASBounds(self, bounds):
        w, h, _ = self.GetDimensions()
        corners = np.array(
            [self.affine @ [x, y, z, 1] for x, y, z in product((-0.5, w - 0.5), (-0.5, h - 0.5), (-0.5, 0.5))]
        )
        bounds[:] = [value for i in range(3) for value in (float(corners[:, i].min()), float(corners[:, i].max()))]

    def from_image(self, xy):
        return (self.affine @ [*xy, 0, 1])[:3]

    def to_image(self, point):
        return (self.inverse @ [*point, 1])[:2].tolist()


class Collection(list):
    def InitTraversal(self):
        self.cursor = iter(self)

    def GetNextItemAsObject(self):
        return next(self.cursor, None)


class Scene:
    def __init__(self):
        self.markups = {}
        self.volume = None
        self._next_id = 1

    def GetNodesByClass(self, classname):
        return Collection(node for node in self.markups.values() if node.IsA(classname))

    def GetFirstNodeByClass(self, classname):
        if classname in ("vtkMRMLVolumeNode", "vtkMRMLScalarVolumeNode"):
            return self.volume
        return next(iter(self.GetNodesByClass(classname)), None)

    def AddNewNodeByClass(self, classname, name):
        node_id = str(self._next_id)
        self._next_id += 1
        node = Markup(classname, name, node_id)
        self.markups[node_id] = node
        return node

    def RemoveNode(self, node):
        self.markups.pop(node.GetID(), None)

    def Clear(self):
        self.markups.clear()
        self.volume = None
