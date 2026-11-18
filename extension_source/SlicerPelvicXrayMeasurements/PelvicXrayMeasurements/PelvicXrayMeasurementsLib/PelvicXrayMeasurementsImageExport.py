"""High-resolution annotated image export support for Pelvic X-ray Measurements.

This mixin isolates raster export and drawing concerns from UI construction and measurement logic.
The widget supplies the current scene state; this file focuses only on turning that state into an
annotated image.
"""
from __future__ import annotations

import logging
import math
import os
import tempfile
from typing import Any

import numpy as np
import qt
import slicer
import vtk

from PelvicXrayMeasurementsConstants import ACTIVE_SIDE_BADGE_ROLE, EPSILON, SIDE_KEYS
from PelvicXrayMeasurementsGeometry import clamp, image_axes_from_volume


class AnnotationImageExportMixin:
    """Provide high-resolution source-image capture and annotation drawing for the widget."""

    def _red_slice_widget(self) -> Any:
        """Return the Red slice widget used as the primary x-ray view. The export and display code
        targets one canonical slice view so behavior stays predictable.
        """

        layout_manager = slicer.app.layoutManager()
        if layout_manager is None:
            return None
        return layout_manager.sliceWidget("Red")

    def _red_slice_displayed_image_node(self, fallback: Any=None) -> Any:
        """Return the image actually shown in the Red slice view, with a fallback if needed. Export
        should match what the user is working on, not merely the last selected node.
        """

        slice_widget = self._red_slice_widget()
        slice_logic = (
            slice_widget.sliceLogic()
            if slice_widget is not None and hasattr(slice_widget, "sliceLogic")
            else None
        )
        composite_node = slice_logic.GetSliceCompositeNode() if slice_logic is not None else None
        if composite_node is None:
            return fallback

        for node_id in (
            composite_node.GetBackgroundVolumeID(),
            composite_node.GetForegroundVolumeID(),
            composite_node.GetLabelVolumeID(),
        ):
            if not node_id:
                continue
            volume_node = slicer.mrmlScene.GetNodeByID(node_id)
            if volume_node is not None and volume_node.IsA("vtkMRMLScalarVolumeNode"):
                return volume_node
        return fallback

    def _image_physical_dimensions(self, image_node: Any) -> Any:
        """Estimate the physical size of the image in scene coordinates. Export sizing and helper-span
        calculations use this instead of screen pixels so geometry remains stable across zoom
        levels.
        """

        if image_node is None:
            return None
        image_data = image_node.GetImageData()
        if image_data is None:
            return None

        dimensions = image_data.GetDimensions()
        spacing = image_node.GetSpacing() if hasattr(image_node, "GetSpacing") else (1.0, 1.0, 1.0)
        width = float(dimensions[0]) * abs(float(spacing[0]))
        height = float(dimensions[1]) * abs(float(spacing[1]))
        if width <= EPSILON or height <= EPSILON:
            return None
        return width, height

    def _full_image_crop_rect(self, image_size: Any, image_node: Any) -> Any:
        """Return the rectangle that corresponds to the full source image within a rendered view.
        Cropping to the image bounds avoids exporting empty letterbox space.
        """

        width = int(image_size.width())
        height = int(image_size.height())
        if width < 2 or height < 2:
            return qt.QRect(0, 0, max(1, width), max(1, height))

        image_dimensions = self._image_physical_dimensions(image_node)
        if image_dimensions is None:
            return qt.QRect(0, 0, width, height)

        image_width, image_height = image_dimensions
        image_aspect = image_width / max(image_height, EPSILON)
        view_aspect = float(width) / float(height)

        if view_aspect > image_aspect:
            crop_height = height
            crop_width = int(round(crop_height * image_aspect))
        else:
            crop_width = width
            crop_height = int(round(crop_width / max(image_aspect, EPSILON)))

        crop_width = max(1, min(width, crop_width))
        crop_height = max(1, min(height, crop_height))
        crop_x = max(0, int(round((width - crop_width) / 2.0)))
        crop_y = max(0, int(round((height - crop_height) / 2.0)))
        return qt.QRect(crop_x, crop_y, crop_width, crop_height)

    def _pixel_has_visible_content(self, qimage: Any, x: Any, y: Any, threshold: Any=10) -> Any:
        """Check whether one pixel contains non-background information. Content-aware cropping uses
        lightweight pixel checks instead of more complex image analysis.
        """

        value = int(qimage.pixel(x, y))
        red = (value >> 16) & 0xFF
        green = (value >> 8) & 0xFF
        blue = value & 0xFF
        return max(red, green, blue) > threshold

    def _row_has_visible_content(self, qimage: Any, y: Any, threshold: Any=10) -> Any:
        """Check whether any visible content exists along one image row. This helps trim empty margins
        from exported captures.
        """

        for x in range(qimage.width()):
            if self._pixel_has_visible_content(qimage, x, y, threshold):
                return True
        return False

    def _column_has_visible_content(self, qimage: Any, x: Any, top: Any, bottom: Any, threshold: Any=10) -> Any:
        """Check whether any visible content exists along one image column. Row and column scans are
        kept separate so cropping stays fast and easy to reason about.
        """

        for y in range(top, bottom + 1):
            if self._pixel_has_visible_content(qimage, x, y, threshold):
                return True
        return False

    def _content_bounds(self, qimage: Any, threshold: Any=10) -> Any:
        """Return the tight visible-content bounds in a rendered image, or `None` if empty."""

        width = qimage.width()
        height = qimage.height()

        top = 0
        while top < height and not self._row_has_visible_content(qimage, top, threshold):
            top += 1
        if top >= height:
            return None

        bottom = height - 1
        while bottom >= top and not self._row_has_visible_content(qimage, bottom, threshold):
            bottom -= 1

        left = 0
        while left < width and not self._column_has_visible_content(qimage, left, top, bottom, threshold):
            left += 1

        right = width - 1
        while right >= left and not self._column_has_visible_content(qimage, right, top, bottom, threshold):
            right -= 1
        return left, top, right, bottom

    def _content_crop_rect(self, qimage: Any, fallback_rect: Any=None, threshold: Any=10, margin: Any=4) -> Any:
        """Compute a tight content crop rectangle from the rendered image. The extra margin preserves
        annotations near the edge while still removing obvious blank space.
        """

        if qimage is None or qimage.isNull():
            return fallback_rect if fallback_rect is not None else qt.QRect()

        width = qimage.width()
        height = qimage.height()
        bounds = self._content_bounds(qimage, threshold)
        if bounds is None:
            return fallback_rect if fallback_rect is not None else qt.QRect(0, 0, width, height)
        left, top, right, bottom = bounds

        left = max(0, left - margin)
        top = max(0, top - margin)
        right = min(width - 1, right + margin)
        bottom = min(height - 1, bottom + margin)

        if right <= left or bottom <= top:
            return fallback_rect if fallback_rect is not None else qt.QRect(0, 0, width, height)
        return qt.QRect(left, top, right - left + 1, bottom - top + 1)

    def _qimage_from_vtk_image(self, vtk_image: Any) -> Any:
        """Convert a VTK image into a QImage. Export rendering crosses between Slicer and Qt, so this
        bridge is kept explicit and reusable.
        """

        if vtk_image is None:
            raise RuntimeError("No captured image data available for export.")

        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".png",
            prefix="hip-xray-export-",
            dir=slicer.app.temporaryPath,
            delete=False,
        )
        temporary_path = temporary_file.name
        temporary_file.close()

        try:
            writer = vtk.vtkPNGWriter()
            writer.SetFileName(temporary_path)
            if hasattr(writer, "SetInputData"):
                writer.SetInputData(vtk_image)
            else:
                writer.SetInput(vtk_image)
            writer.Write()

            qimage = qt.QImage(temporary_path)
            if qimage.isNull():
                raise RuntimeError("Could not load captured image for annotated export.")
            return qimage
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def _draw_measurement_overlay_on_image(self, qimage: Any, overlay_text: Any) -> Any:
        """Draw the measurement summary box onto an exported image. The overlay is added after
        rendering so text quality and layout can be controlled independently of the slice capture.
        """

        if qimage is None or qimage.isNull() or not overlay_text:
            return qimage

        painter = qt.QPainter(qimage)
        try:
            painter.setRenderHint(qt.QPainter.Antialiasing, True)
            painter.setRenderHint(qt.QPainter.TextAntialiasing, True)

            font = qt.QFont()
            font.setBold(True)
            text_lines = overlay_text.splitlines()
            horizontal_padding = max(14, int(round(qimage.width() / 75.0)))
            vertical_padding = max(12, int(round(qimage.height() / 95.0)))
            max_text_width = max(1, qimage.width() - 24 - 2 * horizontal_padding)
            font_point_size = max(14, min(28, int(round(min(qimage.width(), qimage.height()) / 70.0))))
            metrics = None
            text_width = 0
            line_height = 0

            while font_point_size >= 1:
                font.setPointSize(font_point_size)
                painter.setFont(font)
                metrics = qt.QFontMetrics(font)
                text_width = 0
                for line in text_lines:
                    if hasattr(metrics, "horizontalAdvance"):
                        text_width = max(text_width, metrics.horizontalAdvance(line))
                    else:
                        text_width = max(text_width, metrics.width(line))
                line_height = max(1, metrics.height())
                if text_width <= max_text_width or font_point_size == 1:
                    break
                font_point_size -= 1

            line_spacing = max(4, int(round(qimage.height() / 220.0)))
            text_height = (
                line_height * len(text_lines)
                + line_spacing * max(0, len(text_lines) - 1)
            )
            box_width = min(qimage.width() - 24, text_width + 2 * horizontal_padding)
            box_height = min(
                qimage.height() - 24,
                text_height + 2 * vertical_padding + max(6, int(round(qimage.height() / 240.0))),
            )
            box_x = max(12, int(round((qimage.width() - box_width) / 2.0)))
            box_y = max(12, qimage.height() - box_height - 14)
            background_rect = qt.QRectF(box_x, box_y, box_width, box_height)
            text_rect = qt.QRectF(
                box_x + horizontal_padding,
                box_y + vertical_padding,
                box_width - 2 * horizontal_padding,
                box_height - 2 * vertical_padding,
            )

            painter.setPen(qt.QPen(qt.QColor(255, 255, 255, 55), 1.0))
            painter.setBrush(qt.QColor(22, 34, 49, 160))
            painter.drawRoundedRect(background_rect, 9.0, 9.0)
            painter.setPen(qt.QColor(255, 255, 255))
            text_top = text_rect.y() + max(0.0, (text_rect.height() - text_height) / 2.0)
            current_y = text_top
            for line in text_lines:
                line_rect = qt.QRectF(
                    text_rect.x(),
                    current_y,
                    text_rect.width(),
                    line_height,
                )
                painter.drawText(
                    line_rect,
                    int(qt.Qt.AlignHCenter | qt.Qt.AlignVCenter),
                    line,
                )
                current_y += line_height + line_spacing
        finally:
            painter.end()
        return qimage

    def _window_level_for_image(self, image_node: Any) -> Any:
        """Choose a window and level for converting the selected image into an exportable grayscale
        view. Using the active image appearance keeps exported PNGs close to what the user sees
        clinically.
        """

        image_data = image_node.GetImageData() if image_node is not None else None
        scalar_range = image_data.GetScalarRange() if image_data is not None else (0.0, 255.0)
        display_node = image_node.GetDisplayNode() if image_node is not None else None

        if display_node is not None and hasattr(display_node, "GetWindow") and hasattr(display_node, "GetLevel"):
            window = float(display_node.GetWindow())
            level = float(display_node.GetLevel())
            if window > EPSILON:
                return window, level

        window = max(EPSILON, float(scalar_range[1]) - float(scalar_range[0]))
        level = 0.5 * (float(scalar_range[0]) + float(scalar_range[1]))
        return window, level

    def _source_image_qimage(self, image_node: Any) -> Any:
        """Build a QImage from the selected source image at native resolution. This path is used when
        export needs image fidelity rather than a simple on-screen screenshot.
        """

        if image_node is None:
            raise RuntimeError("No image selected for annotated image export.")

        image_array = slicer.util.arrayFromVolume(image_node)
        if image_array is None:
            raise RuntimeError("Could not access the selected image data for export.")

        image_array = np.asarray(image_array)
        while image_array.ndim > 2:
            image_array = image_array[0]
        if image_array.ndim != 2:
            raise RuntimeError("Only 2D scalar images are supported for annotated image export.")

        window, level = self._window_level_for_image(image_node)
        low = level - 0.5 * window
        high = level + 0.5 * window
        if high <= low + EPSILON:
            high = low + 1.0

        normalized = np.clip((image_array.astype(np.float32) - low) / (high - low), 0.0, 1.0)
        grayscale = np.ascontiguousarray(np.flipud((normalized * 255.0).astype(np.uint8)))
        bgra = np.empty((grayscale.shape[0], grayscale.shape[1], 4), dtype=np.uint8)
        bgra[:, :, 0] = grayscale
        bgra[:, :, 1] = grayscale
        bgra[:, :, 2] = grayscale
        bgra[:, :, 3] = 255
        qimage = qt.QImage(
            bgra.data,
            int(bgra.shape[1]),
            int(bgra.shape[0]),
            qt.QImage.Format_ARGB32,
        ).copy()
        if qimage.isNull():
            raise RuntimeError("Could not convert the selected image into an exportable PNG.")
        return qimage

    def _export_image_dimensions(self, image_node: Any) -> Any:
        """Render overlays at a minimum 2,048-pixel long edge, independent of source resolution.

        Increase the render target before Slicer draws the markups, rather than enlarging a
        rasterised annotation layer. Bound large exports to 40 megapixels and 15,500 per edge.
        """

        image_data = image_node.GetImageData() if image_node is not None else None
        if image_data is None:
            raise RuntimeError("Selected image has no image data for export.")

        dimensions = image_data.GetDimensions()
        width = max(1, int(dimensions[0]))
        height = max(1, int(dimensions[1]))
        factor = min(
            max(1.0, 2048.0 / max(width, height)),
            15500.0 / max(width, height),
            math.sqrt(40_000_000.0 / (width * height)),
        )
        return max(2, int(width * factor)), max(2, int(height * factor))

    def _temporarily_disable_slice_annotations(self) -> Any:
        """Disable Slicer slice-corner annotations during image export. The module wants its own clean
        annotation layer, not the transient UI metadata from the viewer.
        """

        data_probe = getattr(slicer.modules, "DataProbeInstance", None)
        info_widget = getattr(data_probe, "infoWidget", None)
        slice_annotations = getattr(info_widget, "sliceAnnotations", None)
        if slice_annotations is None:
            return None, None

        original_enabled = getattr(slice_annotations, "sliceViewAnnotationsEnabled", None)
        if original_enabled is not None:
            slice_annotations.sliceViewAnnotationsEnabled = False
            slice_annotations.updateSliceViewFromGUI()
        return slice_annotations, original_enabled

    def _restore_slice_annotations(self, slice_annotations: Any, original_enabled: Any) -> None:
        """Restore the slice-annotation state after export. Temporary export changes are always unwound
        so the interactive viewer behaves exactly as before.
        """

        if slice_annotations is None or original_enabled is None:
            return
        slice_annotations.sliceViewAnnotationsEnabled = original_enabled
        slice_annotations.updateSliceViewFromGUI()

    def _capture_high_resolution_annotated_slice(self, image_node: Any) -> Any:
        """Capture a high-resolution slice render with Slicer annotations intact. The module uses a
        dedicated export path so saved figures can be sharper than a normal screen grab without
        changing the scene.
        """

        import ScreenCapture

        if image_node is None:
            raise RuntimeError("No image selected for annotated image export.")

        width, height = self._export_image_dimensions(image_node)
        source_widget = self._red_slice_widget()
        source_logic = (
            source_widget.sliceLogic()
            if source_widget is not None and hasattr(source_widget, "sliceLogic")
            else None
        )

        owner_node = None
        view_node = None
        view_widget = None
        view_logic = None
        slice_logics = None
        temp_capture_path = None
        slice_annotations = None
        original_slice_annotations_enabled = None

        try:
            slice_annotations, original_slice_annotations_enabled = self._temporarily_disable_slice_annotations()

            owner_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScriptedModuleNode", "HipExportViewOwner")
            view_logic = slicer.vtkMRMLSliceLogic()
            view_logic.SetMRMLScene(slicer.mrmlScene)
            layout_name = f"HipExportSlice{owner_node.GetID().split('vtkMRMLScriptedModuleNode')[-1]}"
            view_node = view_logic.AddSliceNode(layout_name)
            view_node.SetLayoutLabel("HX")
            view_node.SetLayoutColor([0.95, 0.75, 0.15])
            view_node.SetAndObserveParentLayoutNodeID(owner_node.GetID())

            view_widget = slicer.qMRMLSliceWidget()
            if hasattr(view_widget, "setWindowFlag"):
                view_widget.setWindowFlag(qt.Qt.Tool, True)
            view_widget.setMRMLScene(slicer.mrmlScene)
            view_widget.setMRMLSliceNode(view_node)
            slice_logics = slicer.app.applicationLogic().GetSliceLogics()
            view_widget.setSliceLogics(slice_logics)
            slice_logics.AddItem(view_widget.sliceLogic())
            if hasattr(view_widget, "setAttribute"):
                if hasattr(qt.Qt, "WA_ShowWithoutActivating"):
                    view_widget.setAttribute(qt.Qt.WA_ShowWithoutActivating, True)
            if hasattr(view_widget, "setWindowOpacity"):
                view_widget.setWindowOpacity(0.0)
            if hasattr(view_widget, "sliceController"):
                view_widget.sliceController().setVisible(False)
            view_widget.resize(width, height)
            if hasattr(view_widget, "move"):
                view_widget.move(-max(width + 200, 2000), -max(height + 200, 2000))

            target_logic = view_widget.sliceLogic()
            target_node = target_logic.GetSliceNode()
            target_composite = target_logic.GetSliceCompositeNode()
            target_composite.SetBackgroundVolumeID(image_node.GetID())
            if hasattr(target_composite, "SetForegroundVolumeID"):
                target_composite.SetForegroundVolumeID("")
            if hasattr(target_composite, "SetLabelVolumeID"):
                target_composite.SetLabelVolumeID("")
            if hasattr(target_composite, "SetForegroundOpacity"):
                target_composite.SetForegroundOpacity(0.0)

            if source_logic is not None:
                source_node = source_logic.GetSliceNode()
                target_node.GetSliceToRAS().DeepCopy(source_node.GetSliceToRAS())
                if hasattr(target_logic, "SetSliceOffset") and hasattr(source_logic, "GetSliceOffset"):
                    target_logic.SetSliceOffset(source_logic.GetSliceOffset())

            target_node.UpdateMatrices()
            view_widget.show()
            slicer.app.processEvents()

            if hasattr(target_logic, "FitSliceToAll"):
                target_logic.FitSliceToAll()
            elif hasattr(target_logic, "FitSliceToBackground"):
                target_logic.FitSliceToBackground()

            target_node.UpdateMatrices()
            slice_view = view_widget.sliceView()
            if hasattr(slice_view, "cornerAnnotation"):
                corner_annotation = slice_view.cornerAnnotation()
                for corner_index in range(4):
                    corner_annotation.SetText(corner_index, "")
            slice_view.forceRender()
            slicer.app.processEvents()

            temp_capture = tempfile.NamedTemporaryFile(
                suffix=".png",
                prefix="hip-xray-rendered-export-",
                dir=slicer.app.temporaryPath,
                delete=False,
            )
            temp_capture_path = temp_capture.name
            temp_capture.close()

            capture_logic = ScreenCapture.ScreenCaptureLogic()
            capture_logic.captureImageFromView(slice_view, temp_capture_path)
            captured_image = qt.QImage(temp_capture_path)
            if captured_image.isNull():
                raise RuntimeError("Slicer did not produce a valid rendered PNG during image export.")
            return captured_image
        finally:
            self._restore_slice_annotations(slice_annotations, original_slice_annotations_enabled)
            if temp_capture_path and os.path.exists(temp_capture_path):
                os.remove(temp_capture_path)
            if view_widget is not None:
                view_widget.hide()
                view_widget.setParent(None)
                view_widget.deleteLater()
            if slice_logics is not None and view_widget is not None:
                try:
                    slice_logics.RemoveItem(view_widget.sliceLogic())
                except Exception:
                    logging.debug("Failed to remove temporary slice logic during image export cleanup.", exc_info=True)
            if view_node is not None:
                slicer.mrmlScene.RemoveNode(view_node)
            if owner_node is not None:
                slicer.mrmlScene.RemoveNode(owner_node)

    def _ras_to_export_point(self, ras_point: Any, ras_to_ijk_matrix: Any, image_height: Any) -> Any:
        """Project a RAS point into exported image coordinates. Export annotations are drawn in image
        space, so every live measurement must be mapped out of MRML world coordinates first.
        """

        if ras_point is None or ras_to_ijk_matrix is None:
            return None
        ras_h = [float(ras_point[0]), float(ras_point[1]), float(ras_point[2]), 1.0]
        ijk_h = [0.0, 0.0, 0.0, 0.0]
        ras_to_ijk_matrix.MultiplyPoint(ras_h, ijk_h)
        return qt.QPointF(float(ijk_h[0]), float(image_height - 1.0 - ijk_h[1]))

    def _color_from_display_node(self, display_node: Any, fallback_rgb: Any=(255, 255, 255)) -> Any:
        """Read an RGB color from a display node and convert it to a Qt color. This keeps exported
        annotations visually aligned with the colors users see in Slicer.
        """

        if display_node is not None and hasattr(display_node, "GetColor"):
            color = display_node.GetColor()
            if color is not None and len(color) >= 3:
                return qt.QColor(
                    int(round(clamp(float(color[0])) * 255.0)),
                    int(round(clamp(float(color[1])) * 255.0)),
                    int(round(clamp(float(color[2])) * 255.0)),
                )
        return qt.QColor(*fallback_rgb)

    def _draw_export_point(self, painter: Any, point: Any, color: Any, radius_pixels: Any) -> None:
        """Draw one point marker on an exported image. A shared point primitive keeps annotation style
        consistent across all measurement types.
        """

        if point is None:
            return
        painter.save()
        painter.setPen(qt.QPen(color, max(1.0, radius_pixels * 0.45)))
        painter.setBrush(color)
        painter.drawEllipse(point, radius_pixels, radius_pixels)
        painter.restore()

    def _draw_export_polyline(self, painter: Any, points: Any, color: Any, width_pixels: Any) -> None:
        """Draw one polyline on an exported image. Centralizing polyline drawing avoids repeated pen
        setup and keeps export styling uniform.
        """

        if len(points) < 2:
            return
        painter.save()
        painter.setPen(qt.QPen(color, width_pixels, qt.Qt.SolidLine, qt.Qt.RoundCap, qt.Qt.RoundJoin))
        for index in range(len(points) - 1):
            painter.drawLine(points[index], points[index + 1])
        painter.restore()

    def _projected_markup_points(
        self,
        node: Any,
        ras_to_ijk_matrix: Any,
        image_height: Any,
    ) -> Any:
        """Return all defined control points of a markup node projected into export image space."""

        defined_status = (
            slicer.vtkMRMLMarkupsNode.PositionDefined
            if hasattr(slicer, "vtkMRMLMarkupsNode")
            else None
        )
        projected_points = []
        for point_index in range(node.GetNumberOfControlPoints()):
            if (
                defined_status is not None
                and node.GetNthControlPointPositionStatus(point_index) != defined_status
            ):
                continue
            point = [0.0, 0.0, 0.0]
            if hasattr(node, "GetNthControlPointPositionWorld"):
                node.GetNthControlPointPositionWorld(point_index, point)
            else:
                node.GetNthControlPointPosition(point_index, point)
            projected_point = self._ras_to_export_point(point, ras_to_ijk_matrix, image_height)
            if projected_point is not None:
                projected_points.append(projected_point)
        return projected_points

    def _draw_markup_node_on_image(
        self,
        painter: Any,
        node: Any,
        ras_to_ijk_matrix: Any,
        image_height: Any,
        width_pixels: Any,
        point_radius: Any,
    ) -> None:
        """Render a markup node into the exported image. Export drawing mirrors the MRML scene so
        figures can be reproduced without separate annotation bookkeeping.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode") or not node.GetDisplayVisibility():
            return

        display_node = node.GetDisplayNode()
        color = self._color_from_display_node(display_node)
        projected_points = self._projected_markup_points(
            node,
            ras_to_ijk_matrix,
            image_height,
        )

        if node.IsA("vtkMRMLMarkupsLineNode") and len(projected_points) >= 2:
            self._draw_export_polyline(painter, projected_points[:2], color, width_pixels)
        elif node.IsA("vtkMRMLMarkupsClosedCurveNode") and len(projected_points) >= 3:
            self._draw_export_polyline(
                painter,
                projected_points + [projected_points[0]],
                color,
                width_pixels,
            )
            return
        elif node.IsA("vtkMRMLMarkupsCurveNode") and len(projected_points) >= 2:
            self._draw_export_polyline(painter, projected_points, color, width_pixels)

        for point in projected_points:
            self._draw_export_point(painter, point, color, point_radius)

    def _draw_model_lines_on_image(
        self,
        painter: Any,
        node: Any,
        ras_to_ijk_matrix: Any,
        image_height: Any,
        width_pixels: Any,
    ) -> None:
        """Render line-based model polydata into the exported image. Some helper geometries are stored
        as models rather than markups, so export needs a companion path for them.
        """

        if node is None or not node.IsA("vtkMRMLModelNode") or not node.GetDisplayVisibility():
            return

        poly_data = node.GetPolyData()
        if poly_data is None or poly_data.GetNumberOfLines() < 1:
            return

        color = self._color_from_display_node(node.GetDisplayNode())
        line_cells = poly_data.GetLines()
        id_list = vtk.vtkIdList()
        line_cells.InitTraversal()
        while line_cells.GetNextCell(id_list):
            projected_points = []
            for point_index in range(id_list.GetNumberOfIds()):
                ras_point = poly_data.GetPoint(id_list.GetId(point_index))
                projected_point = self._ras_to_export_point(ras_point, ras_to_ijk_matrix, image_height)
                if projected_point is not None:
                    projected_points.append(projected_point)
            self._draw_export_polyline(painter, projected_points, color, width_pixels)

    def _draw_circle_measurement_on_image(
        self,
        painter: Any,
        center_ras: Any,
        radius_ras: Any,
        display_node: Any,
        image_node: Any,
        ras_to_ijk_matrix: Any,
        image_height: Any,
        width_pixels: Any,
    ) -> None:
        """Draw a circle or projected sphere outline onto the exported image. Circles are redrawn
        analytically so the export matches the fitted geometry even if live display uses a surface
        model.
        """

        if center_ras is None or radius_ras is None or radius_ras <= EPSILON:
            return

        axis_i, axis_j = image_axes_from_volume(image_node)
        if axis_i is None or axis_j is None:
            return

        center_point = self._ras_to_export_point(center_ras, ras_to_ijk_matrix, image_height)
        point_i = self._ras_to_export_point(center_ras + axis_i * radius_ras, ras_to_ijk_matrix, image_height)
        point_j = self._ras_to_export_point(center_ras + axis_j * radius_ras, ras_to_ijk_matrix, image_height)
        if center_point is None or point_i is None or point_j is None:
            return

        radius_x = abs(point_i.x() - center_point.x())
        radius_y = abs(point_j.y() - center_point.y())
        if radius_x <= EPSILON or radius_y <= EPSILON:
            return

        color = self._color_from_display_node(display_node)
        painter.save()
        painter.setPen(qt.QPen(color, width_pixels, qt.Qt.SolidLine, qt.Qt.RoundCap, qt.Qt.RoundJoin))
        painter.setBrush(qt.QBrush(qt.Qt.NoBrush))
        painter.drawEllipse(
            qt.QRectF(
                center_point.x() - radius_x,
                center_point.y() - radius_y,
                2.0 * radius_x,
                2.0 * radius_y,
            )
        )
        painter.restore()

    def _draw_ellipse_measurement_on_image(
        self,
        painter: Any,
        center_ras: Any,
        major_direction: Any,
        minor_direction: Any,
        major_radius: Any,
        minor_radius: Any,
        display_node: Any,
        ras_to_ijk_matrix: Any,
        image_height: Any,
        width_pixels: Any,
    ) -> None:
        """Draw the fitted cup ellipse analytically onto the exported image. Export uses a sampled
        outline because the live slice view represents the ellipse as a thin surface for reliable
        display.
        """

        if (
            center_ras is None
            or major_direction is None
            or minor_direction is None
            or major_radius is None
            or minor_radius is None
            or major_radius <= EPSILON
            or minor_radius <= EPSILON
        ):
            return

        projected_points = []
        sample_count = 180
        for angle in np.linspace(0.0, 2.0 * math.pi, sample_count, endpoint=False):
            ras_point = (
                center_ras
                + major_direction * (float(major_radius) * math.cos(angle))
                + minor_direction * (float(minor_radius) * math.sin(angle))
            )
            projected_point = self._ras_to_export_point(ras_point, ras_to_ijk_matrix, image_height)
            if projected_point is not None:
                projected_points.append(projected_point)

        if len(projected_points) < 3:
            return

        projected_points.append(projected_points[0])
        color = self._color_from_display_node(display_node)
        self._draw_export_polyline(painter, projected_points, color, width_pixels)

    def _draw_visible_scene_nodes_on_image(
        self,
        painter: Any,
        qimage: Any,
        ras_to_ijk_matrix: Any,
        width_pixels: float,
        point_radius: float,
    ) -> None:
        """Draw all currently visible MRML markup and model nodes onto the export image."""

        for role in self.logic._all_node_roles():
            if role == ACTIVE_SIDE_BADGE_ROLE:
                continue
            node = self.logic.get_node(role, create_if_missing=False)
            if node is None or not node.GetDisplayVisibility():
                continue
            if node.IsA("vtkMRMLMarkupsNode"):
                self._draw_markup_node_on_image(
                    painter, node, ras_to_ijk_matrix, qimage.height(), width_pixels, point_radius
                )
            elif node.IsA("vtkMRMLModelNode"):
                self._draw_model_lines_on_image(
                    painter, node, ras_to_ijk_matrix, qimage.height(), width_pixels
                )

    def _draw_optional_circle_measurement(
        self,
        painter: Any,
        image_node: Any,
        ras_to_ijk_matrix: Any,
        image_height: int,
        width_pixels: float,
        center_ras: Any,
        raw_diameter: Any,
        display_node: Any,
        defined: Any,
    ) -> None:
        """Draw one circle measurement when its model is visible and its result is defined."""

        if display_node is None or not defined:
            return
        self._draw_circle_measurement_on_image(
            painter,
            center_ras,
            0.5 * float(raw_diameter),
            display_node,
            image_node,
            ras_to_ijk_matrix,
            image_height,
            width_pixels,
        )

    def _draw_side_measurement_fits_on_image(
        self,
        painter: Any,
        image_node: Any,
        results: Any,
        ras_to_ijk_matrix: Any,
        image_height: int,
        width_pixels: float,
    ) -> None:
        """Draw fitted circles and ellipses that are represented analytically in the export."""

        calibration_circle_node = self.logic.get_node("calibrationCircle", create_if_missing=False)
        if calibration_circle_node is not None and calibration_circle_node.GetDisplayVisibility():
            self._draw_optional_circle_measurement(
                painter,
                image_node,
                ras_to_ijk_matrix,
                image_height,
                width_pixels,
                results["calibration"]["center"],
                results["calibration"]["rawDiameter"],
                calibration_circle_node.GetDisplayNode(),
                results["calibration"]["defined"],
            )

        for side_key in SIDE_KEYS:
            side_results = results["sides"][side_key]

            femur_circle_node = self.logic.get_node(
                self.logic.side_role("femurHeadCircle", side_key), create_if_missing=False
            )
            if femur_circle_node is not None and femur_circle_node.GetDisplayVisibility():
                self._draw_optional_circle_measurement(
                    painter,
                    image_node,
                    ras_to_ijk_matrix,
                    image_height,
                    width_pixels,
                    side_results["femurHead"]["center"],
                    side_results["femurHead"]["rawValue"],
                    femur_circle_node.GetDisplayNode(),
                    side_results["femurHead"]["defined"],
                )

            implant_circle_node = self.logic.get_node(
                self.logic.side_role("implantHeadCircle", side_key), create_if_missing=False
            )
            if implant_circle_node is not None and implant_circle_node.GetDisplayVisibility():
                self._draw_optional_circle_measurement(
                    painter,
                    image_node,
                    ras_to_ijk_matrix,
                    image_height,
                    width_pixels,
                    side_results["implantHead"]["center"],
                    side_results["implantHead"]["rawValue"],
                    implant_circle_node.GetDisplayNode(),
                    side_results["implantHead"]["defined"],
                )

            cup_ellipse_node = self.logic.get_node(
                self.logic.side_role("cupOpeningEllipse", side_key), create_if_missing=False
            )
            if (
                cup_ellipse_node is not None
                and cup_ellipse_node.GetDisplayVisibility()
                and side_results["cupOpeningEllipseFit"]["defined"]
            ):
                self._draw_ellipse_measurement_on_image(
                    painter,
                    side_results["cupOpeningEllipseFit"]["center"],
                    side_results["cupOpeningEllipseFit"]["majorDirection"],
                    side_results["cupOpeningEllipseFit"]["minorDirection"],
                    side_results["cupOpeningEllipseFit"]["majorRadius"],
                    side_results["cupOpeningEllipseFit"]["minorRadius"],
                    cup_ellipse_node.GetDisplayNode(),
                    ras_to_ijk_matrix,
                    image_height,
                    width_pixels,
                )

    def _draw_annotations_on_image(self, qimage: Any, image_node: Any, results: Any) -> Any:
        """Compose all visible measurement annotations onto an image export. Keeping this pass separate
        from the numeric calculations helps preserve export fidelity without affecting results.
        """

        if qimage is None or qimage.isNull() or image_node is None:
            return qimage

        ras_to_ijk_matrix = vtk.vtkMatrix4x4()
        image_node.GetRASToIJKMatrix(ras_to_ijk_matrix)

        painter = qt.QPainter(qimage)
        try:
            painter.setRenderHint(qt.QPainter.Antialiasing, True)
            painter.setRenderHint(qt.QPainter.TextAntialiasing, True)

            width_pixels = max(2.0, min(qimage.width(), qimage.height()) / 420.0)
            point_radius = max(3.0, min(qimage.width(), qimage.height()) / 180.0)
            self._draw_visible_scene_nodes_on_image(
                painter,
                qimage,
                ras_to_ijk_matrix,
                width_pixels,
                point_radius,
            )
            self._draw_side_measurement_fits_on_image(
                painter,
                image_node,
                results,
                ras_to_ijk_matrix,
                qimage.height(),
                width_pixels,
            )
        finally:
            painter.end()

        return qimage

    def _capture_annotation_image(self, image_node: Any=None) -> Any:
        """Create the final annotated export image, including optional measurement text. The method
        keeps export assembly in one place so button handlers stay small.
        """

        image_node = image_node if image_node is not None else self.current_image_node()
        results = self.logic.latest_results
        badge_visibility = None
        if hasattr(self, "_set_active_side_badge_display_visibility"):
            badge_visibility = self._set_active_side_badge_display_visibility(False)
        try:
            qimage = self._capture_high_resolution_annotated_slice(image_node)
            overlay_text = self._measurement_overlay_text(
                results,
                entries_per_line=4,
                include_measurements=self.display_measurements_on_image,
            )
            return self._draw_measurement_overlay_on_image(qimage, overlay_text)
        finally:
            if badge_visibility is not None and hasattr(self, "_set_active_side_badge_display_visibility"):
                self._set_active_side_badge_display_visibility(badge_visibility)
