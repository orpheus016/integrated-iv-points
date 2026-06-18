from typing import List, Tuple
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QFont
from PySide6.QtWidgets import QWidget


class WaferMapWidget(QWidget):
    """Draw a circular wafer map with a live probe point and contour overlays."""

    DOPING_MIN = 5e13
    DOPING_MAX = 5e18
    REFERENCE_WAFER_DIAMETER_INCH = 5.0
    REFERENCE_WAFER_RADIUS_CM = REFERENCE_WAFER_DIAMETER_INCH * 2.54 / 2.0
    GRID_STEPS = 20
    AXIS_LABEL_FRACTIONS = tuple([-9.0 / 8.0] + [i / 8.0 for i in range(-8, 11)])
    VISUAL_WAFER_DIAMETER_RATIO = 0.80
    N100_DIAG = 1.35
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 360)

        self._wafer_radius_cm = self.REFERENCE_WAFER_RADIUS_CM
        self._point_x_cm = 0.0
        self._point_y_cm = 0.0

        self._contours: List[Tuple[float, float, float]] = []
        self._min_doping = None
        self._max_doping = None
        self._display_min = self.DOPING_MIN
        self._display_max = self.DOPING_MAX
        self._doping_type = "N (100)"

    def set_wafer_diameter_inch(self, diameter_inch: float):
        radius_cm = (diameter_inch * 2.54) / 2.0
        self._wafer_radius_cm = max(0.2, min(10.0, radius_cm))
        self.update()

    def set_wafer_area_cm2(self, area_cm2: float):
        # Convert wafer area directly to radius so map scaling follows cm^2 continuously.
        area_cm2 = max(0.01, float(area_cm2))
        radius_cm = math.sqrt(area_cm2 / math.pi)
        self._wafer_radius_cm = max(0.2, min(10.0, radius_cm))
        self.update()

    def set_probe_point(self, x_cm: float, y_cm: float):
        radius = max(self._wafer_radius_cm, 1e-9)
        self._point_x_cm = max(-radius, min(radius, x_cm))
        self._point_y_cm = max(-radius, min(radius, y_cm))
        self.update()

    def set_display_range(self, min_doping_cm3: float, max_doping_cm3: float):
        lo = max(1.0, float(min_doping_cm3))
        hi = max(1.0, float(max_doping_cm3))
        if lo >= hi:
            return
        self._display_min = lo
        self._display_max = hi
        self.update()

    def reset_display_range(self):
        self._display_min = self.DOPING_MIN
        self._display_max = self.DOPING_MAX
        self.update()

    def set_doping_type(self, doping_type: str):
        valid_types = {"P (100)", "P (111)", "N (100)", "N (111)"}
        if doping_type not in valid_types:
            return
        self._doping_type = doping_type
        self.update()

    def clear_contours(self):
        self._contours.clear()
        self._min_doping = None
        self._max_doping = None
        self.update()

    def add_measurement_contour(self, x_cm: float, y_cm: float, doping_cm3: float):
        radius = max(self._wafer_radius_cm, 1e-9)
        x = max(-radius, min(radius, x_cm))
        y = max(-radius, min(radius, y_cm))
        d = max(0.0, float(doping_cm3))
        self._contours.append((x, y, d))

        if self._min_doping is None or d < self._min_doping:
            self._min_doping = d
        if self._max_doping is None or d > self._max_doping:
            self._max_doping = d

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Keep extra bottom space so X-axis labels are not clipped.
        left_margin = 42
        right_margin = 20
        top_margin = 8
        bottom_margin = 56

        avail_w = max(40.0, self.width() - left_margin - right_margin)
        avail_h = max(40.0, self.height() - top_margin - bottom_margin)
        side = min(avail_w, avail_h)

        panel_left = left_margin + (avail_w - side) / 2
        panel_top = top_margin + (avail_h - side) / 2
        center_x = panel_left + side / 2
        center_y = panel_top + side / 2
        half_side = side / 2
        cell_px = side / self.GRID_STEPS
        display_radius_px = (self.VISUAL_WAFER_DIAMETER_RATIO * side) / 2.0

        wafer_path = self._wafer_outline_path(center_x, center_y, display_radius_px)

        # Background vignette for visual depth.
        vignette = QRadialGradient(center_x, center_y, side * 0.55)
        vignette.setColorAt(0.0, QColor("#ffffff"))
        vignette.setColorAt(1.0, QColor("#f7f9fc"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(vignette)
        painter.drawRect(int(panel_left), int(panel_top), int(side), int(side))

        inside_base = QColor("#f6f8fb")
        outside_base = QColor("#eef2f7")

        # Paint the square panel as outside area first.
        painter.setPen(Qt.NoPen)
        painter.setBrush(outside_base)
        painter.drawRect(int(panel_left), int(panel_top), int(side), int(side))

        # Fill contours clipped by the wafer silhouette so no white gaps remain
        # inside the wafer, while color never bleeds outside the boundary.
        painter.save()
        painter.setClipPath(wafer_path)

        for row in range(self.GRID_STEPS):
            for col in range(self.GRID_STEPS):
                x_cm, y_cm = self._cell_center_cm(col, row)

                cell_left = panel_left + col * cell_px
                cell_top = panel_top + row * cell_px
                cell_w = int(math.ceil(cell_px)) + 1

                doping = self._interpolated_doping(x_cm, y_cm)
                fill = self._doping_color(doping) if doping is not None else inside_base

                painter.setPen(Qt.NoPen)
                painter.setBrush(fill)
                painter.drawRect(int(cell_left), int(cell_top), cell_w, cell_w)

        painter.restore()

        # Draw square cell boundaries to match contour-map style.
        grid_pen = QPen(QColor("#94a3b8"), 0.9)
        painter.setPen(grid_pen)
        painter.setBrush(Qt.NoBrush)
        for i in range(self.GRID_STEPS + 1):
            gx = panel_left + i * cell_px
            gy = panel_top + i * cell_px
            painter.drawLine(int(gx), int(panel_top), int(gx), int(panel_top + side))
            painter.drawLine(int(panel_left), int(gy), int(panel_left + side), int(gy))

        # Wafer outline with doping-type-dependent silhouette.
        outline_pen = QPen(QColor("#0f172a"), 2)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(wafer_path)

        axis_pen = QPen(QColor("#64748b"), 1.1)
        axis_pen.setCosmetic(True)
        painter.setPen(axis_pen)
        painter.drawLine(int(panel_left), int(center_y), int(panel_left + side), int(center_y))
        painter.drawLine(int(center_x), int(panel_top), int(center_x), int(panel_top + side))

        # Current measurement point marker.
        point_x, point_y = self._cm_to_px(self._point_x_cm, self._point_y_cm, center_x, center_y, display_radius_px)
        marker_pen = QPen(QColor("#0f172a"), 2)
        painter.setPen(marker_pen)
        painter.setBrush(QColor("#d84545"))
        painter.drawEllipse(int(point_x - 6), int(point_y - 6), 12, 12)

        # Tick labels stay in cm but their positions are rendered on the fixed visual wafer size.
        painter.setPen(QColor("#0f172a"))
        for frac in self.AXIS_LABEL_FRACTIONS:
            x_cm = self._wafer_radius_cm * frac
            x_px = center_x + display_radius_px * frac
            label = self._format_cm_label(x_cm)
            painter.drawText(int(x_px - 12), int(panel_top + side + 12), 24, 14, Qt.AlignHCenter, label)

            y_cm = self._wafer_radius_cm * frac
            y_px = center_y - display_radius_px * frac
            painter.drawText(int(panel_left - 42), int(y_px - 7), 30, 14, Qt.AlignRight, label)

        # Unit label in bottom-left of the grid (e.g. "(cm)"). Place it
        # at the same vertical level as the X-axis tick labels and use a
        # larger pixel-size font so the change is visible across platforms.
        painter.save()
        font = painter.font()
        new_font = QFont(font)
        new_font.setPixelSize(16)
        painter.setFont(new_font)
        painter.setPen(QColor("#0f172a"))
        painter.drawText(int(panel_left - 28), int(panel_top + side + 5), 64, 20, Qt.AlignLeft, "(cm)")
        painter.restore()

    def _is_inside_wafer_shape(self, x_cm: float, y_cm: float) -> bool:
        radius = max(self._wafer_radius_cm, 1e-9)
        xn = x_cm / radius
        yn = y_cm / radius
        return self._is_inside_unit_shape(xn, yn)

    def _is_inside_unit_shape(self, xn: float, yn: float) -> bool:
        if (xn * xn + yn * yn) > 1.0:
            return False

        # All types have a slight bottom flat.
        bottom_cut = -0.95
        if yn < bottom_cut:
            return False

        # P (111): only the slight bottom flat.
        if self._doping_type == "P (111)":
            return True

        # N (111): add a 45-degree diagonal cut at the bottom-left.
        if self._doping_type == "N (111)":
            # Mirror the N(100) diagonal: use the negative of the N100 diagonal constant
            diag_const = -self.N100_DIAG
            if xn < -0.30:
                return (xn + yn) >= diag_const
            return True

        # P (100): add a left vertical flat plus a diagonal chamfer
        # connecting the left and bottom flats at the bottom-left corner.
        if self._doping_type == "P (100)":
            left_cut = -0.95
            if xn < left_cut:
                return False
            return (xn + yn) >= -1.55

        # N (100): add an upper-left diagonal cut (135 deg from bottom baseline).
        return (yn - xn) <= self.N100_DIAG

    def _wafer_outline_path(self, center_x: float, center_y: float, radius_px: float) -> QPainterPath:
        # Use the general sampler for all types. The unit-shape test encodes
        # the flats/diagonals; sampling produces a smooth polygon that follows
        # the same rules. This avoids special-case math that can misplace
        # the diagonal when mirroring across axes.
        path = QPainterPath()
        samples = 720
        points = []

        for i in range(samples + 1):
            theta = (2.0 * math.pi * i) / samples
            xn = math.cos(theta)
            yn = math.sin(theta)

            if not self._is_inside_unit_shape(xn, yn):
                continue

            px = center_x + (radius_px * xn)
            py = center_y - (radius_px * yn)
            points.append((px, py))

        if not points:
            path.addEllipse(center_x - radius_px, center_y - radius_px, radius_px * 2.0, radius_px * 2.0)
            return path

        path.moveTo(points[0][0], points[0][1])
        for px, py in points[1:]:
            path.lineTo(px, py)
        path.closeSubpath()
        return path

    def _cm_to_px(self, x_cm: float, y_cm: float, center_x: float, center_y: float, display_radius_px: float):
        radius = max(self._wafer_radius_cm, 1e-9)
        scale = display_radius_px / radius
        px = center_x + x_cm * scale
        py = center_y - y_cm * scale
        return px, py

    def _format_cm_label(self, value_cm: float) -> str:
        rounded = round(value_cm)
        if abs(value_cm - rounded) < 0.05:
            return f"{rounded:d}"
        return f"{value_cm:.1f}"

    def _cell_center_cm(self, col: int, row: int):
        radius = max(self._wafer_radius_cm, 1e-9)
        span = radius * 2.0
        x_cm = ((col + 0.5) / self.GRID_STEPS) * span - radius
        y_cm = radius - ((row + 0.5) / self.GRID_STEPS) * span
        return x_cm, y_cm

    def _interpolated_doping(self, x_cm: float, y_cm: float):
        # Recompute from all measured points so colors readjust globally (not stacking overlays).
        if not self._contours:
            return None

        # ubah ini u/ atur doping concentration spread
        sigma_cm = max(0.8, self._wafer_radius_cm * 0.30)
        sigma2 = sigma_cm * sigma_cm
        weighted_log_sum = 0.0
        weight_sum = 0.0

        for px, py, d in self._contours:
            d_clamped = max(self.DOPING_MIN, min(self.DOPING_MAX, d))
            dist2 = (x_cm - px) ** 2 + (y_cm - py) ** 2
            if dist2 < 1e-10:
                return d_clamped

            w = math.exp(-dist2 / (2.0 * sigma2))
            weighted_log_sum += w * math.log10(d_clamped)
            weight_sum += w

        if weight_sum <= 1e-12:
            return None

        interp_log = weighted_log_sum / weight_sum
        return max(self.DOPING_MIN, min(self.DOPING_MAX, 10 ** interp_log))

    def _doping_color(self, value: float) -> QColor:
        lo = max(self._display_min, 1e-30)
        hi = max(self._display_max, lo * 1.000001)
        v = max(lo, min(hi, value))

        # Use log scaling because concentration spans multiple orders of magnitude.
        span = max(math.log10(hi) - math.log10(lo), 1e-12)
        t = (math.log10(v) - math.log10(lo)) / span
        t = max(0.0, min(1.0, t))

        # Blue -> Green -> Orange -> Red palette.
        if t < 0.33:
            local_t = t / 0.33
            return self._lerp_color(QColor("#3e7bff"), QColor("#37c799"), local_t)
        if t < 0.66:
            local_t = (t - 0.33) / 0.33
            return self._lerp_color(QColor("#37c799"), QColor("#f1b84e"), local_t)

        local_t = (t - 0.66) / 0.34
        return self._lerp_color(QColor("#f1b84e"), QColor("#d94a45"), local_t)

    def _lerp_color(self, c1: QColor, c2: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        r = int(c1.red() + (c2.red() - c1.red()) * t)
        g = int(c1.green() + (c2.green() - c1.green()) * t)
        b = int(c1.blue() + (c2.blue() - c1.blue()) * t)
        return QColor(r, g, b)


class ColorScaleBar(QWidget):
    """Horizontal gradient bar showing the doping concentration color scale."""

    # Same 4-stop palette as WaferMapWidget.
    _STOPS = [
        (0.00, QColor("#3e7bff")),
        (0.33, QColor("#37c799")),
        (0.66, QColor("#f1b84e")),
        (1.00, QColor("#d94a45")),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self._display_min = WaferMapWidget.DOPING_MIN
        self._display_max = WaferMapWidget.DOPING_MAX

    def set_display_range(self, min_doping_cm3: float, max_doping_cm3: float):
        lo = max(1.0, float(min_doping_cm3))
        hi = max(1.0, float(max_doping_cm3))
        if lo >= hi:
            return
        self._display_min = lo
        self._display_max = hi
        self.update()

    def reset_display_range(self):
        self._display_min = WaferMapWidget.DOPING_MIN
        self._display_max = WaferMapWidget.DOPING_MAX
        self.update()

    def clear_range(self):
        # Compatibility hook used by the result page reset action.
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bar_h = 18
        bar_top = 4
        bar_left = 8
        bar_right = self.width() - 8
        bar_w = bar_right - bar_left
        radius = bar_h / 2

        # Gradient bar.
        grad = QLinearGradient(bar_left, 0, bar_right, 0)
        for stop, color in self._STOPS:
            grad.setColorAt(stop, color)

        path = QPainterPath()
        path.addRoundedRect(bar_left, bar_top, bar_w, bar_h, radius, radius)
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawPath(path)

        # Border.
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Tick marks at 0 %, 50 %, 100 %.
        tick_pen = QPen(QColor("#0f172a"), 1)
        painter.setPen(tick_pen)
        for frac in (0.0, 0.5, 1.0):
            tx = int(bar_left + frac * bar_w)
            painter.drawLine(tx, bar_top + bar_h, tx, bar_top + bar_h + 4)

        # Labels.
        painter.setPen(QColor("#4b4b4b"))
        label_y = bar_top + bar_h + 16

        lo_txt = f"{self._display_min:.1e}"
        mid_val = math.sqrt(self._display_min * self._display_max)
        mid_txt = f"{mid_val:.1e}"
        hi_txt = f"{self._display_max:.1e}"

        fm = painter.fontMetrics()
        painter.drawText(bar_left, label_y, lo_txt)
        mid_x = int(bar_left + bar_w / 2 - fm.horizontalAdvance(mid_txt) / 2)
        painter.drawText(mid_x, label_y, mid_txt)
        painter.drawText(int(bar_right - fm.horizontalAdvance(hi_txt)), label_y, hi_txt)
