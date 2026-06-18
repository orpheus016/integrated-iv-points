import math
import re

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QIntValidator, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)

from style import (
    ACCENT_COLOR,
    ACCENT_COLOR_DARK,
    BACKGROUND_COLOR,
    CARD_COLOR,
    TEXT_COLOR,
    apply_neumorphic_shadow,
)
from pages.wafer_map_widget import WaferMapWidget


class SerialReader(QThread):
    """Background thread that reads X/Y/contact/temperature values from an MCU via serial."""
    position_received = Signal(float, float, bool)  # emits parsed (x_cm, y_cm, contact_made)
    temperature_received = Signal(float)  # emits parsed temperature (C) for SHT sensor (main page display)
    mlx_temperature_received = Signal(float)  # emits parsed temperature (C) for MLX sensor (wafer/measurement)
    confirm_received = Signal()  # emits when MCU asks for measurement confirmation
    measurement_started = Signal()  # emits when STARTSTREAM is received
    voltage_received = Signal(float)  # emits parsed voltage value from V-prefixed lines
    current_received = Signal(float)  # emits parsed current value from I-prefixed lines
    measurement_stopped = Signal()  # emits when STOPSTREAM is received
    status_changed = Signal(str) # emits status messages for the UI

    SERIAL_PORT = "COM5"
    BAUD_RATE   = 115200
    SERIAL_CM_SCALE = 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._ser = None

    def run(self):
        if not SERIAL_AVAILABLE:
            self.status_changed.emit("pyserial not installed")
            return
        try:
            ser = serial.Serial(self.SERIAL_PORT, self.BAUD_RATE, timeout=1)
            self._ser = ser
            self.status_changed.emit(f"Connected to {self.SERIAL_PORT}")
            self._running = True

            expecting_x = True
            pending_x = 0.0
            pending_y = 0.0
            has_last_position = False
            last_x = 0.0
            last_y = 0.0
            streaming_measurement = False

            while self._running:
                raw = ser.readline()
                if not raw:
                    continue
                try:
                    text = raw.decode("utf-8", errors="ignore").strip()
                    if not text:
                        continue
                    # Normalize lines that may include timestamp arrows like
                    # "15:07:13.734 -> MLX23.35" by taking payload after '->'
                    if '->' in text:
                        text = text.split('->', 1)[1].strip()
                    if not text:
                        continue

                    if "CONFIRM" in text.upper():
                        self.confirm_received.emit()
                        continue

                    # Accept TRUE/FALSE even if surrounded by other minor text
                    if "TRUE" in text.upper():
                        # Emit contact using last-known coordinates even if a recent
                        # numeric X/Y pair hasn't been fully parsed. This ensures
                        # the UI receives a contact event and measurement values
                        # (V/I) are generated.
                        self.position_received.emit(last_x, last_y, True)
                        continue

                    if "FALSE" in text.upper():
                        continue

                    # SHT lines are used for main-page display
                    if text[:3].upper() == "SHT":
                        raw_temp = text[3:].lstrip(" :=\t")
                        if raw_temp:
                            try:
                                self.temperature_received.emit(float(raw_temp))
                            except Exception:
                                pass
                        continue

                    # MLX lines provide the wafer/measurement temperature used in calculations
                    if text[:3].upper() == "MLX":
                        raw_temp = text[3:].lstrip(" :=\t")
                        if raw_temp:
                            try:
                                self.mlx_temperature_received.emit(float(raw_temp))
                            except Exception:
                                pass
                        continue

                    if text.upper() == "STARTSTREAM":
                        streaming_measurement = True
                        self.measurement_started.emit()
                        continue

                    if text.upper() == "STOPSTREAM":
                        streaming_measurement = False
                        self.measurement_stopped.emit()
                        continue

                    if streaming_measurement and text[:1].upper() == "V":
                        raw_value = text[1:].strip()
                        if raw_value:
                            try:
                                self.voltage_received.emit(float(raw_value))
                            except Exception:
                                pass
                        continue

                    if streaming_measurement and text[:1].upper() == "I":
                        raw_value = text[1:].strip()
                        if raw_value:
                            try:
                                self.current_received.emit(float(raw_value))
                            except Exception:
                                pass
                        continue

                    # Extract numeric coordinates even when lines contain labels like
                    # "X: 123", "Y=45", or combined payloads such as "X:123 Y:45".
                    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
                    if not nums:
                        continue

                    if len(nums) >= 2:
                        last_x = float(nums[0]) * self.SERIAL_CM_SCALE
                        last_y = float(nums[1]) * self.SERIAL_CM_SCALE
                        has_last_position = True
                        self.position_received.emit(last_x, last_y, False)
                        expecting_x = True
                        continue

                    val = float(nums[0]) * self.SERIAL_CM_SCALE
                    if expecting_x:
                        pending_x = val
                        expecting_x = False
                    else:
                        pending_y = val
                        last_x = pending_x
                        last_y = pending_y
                        has_last_position = True
                        self.position_received.emit(last_x, last_y, False)
                        expecting_x = True
                except ValueError:
                    pass   # ignore non-numeric lines
            ser.close()
            self._ser = None
        except Exception as e:
            self._ser = None
            self.status_changed.emit(f"Serial error: {e}")

    def stop(self):
        self._running = False
        self.wait()

    def send_command(self, command: str):
        if not command:
            return
        if self._ser is None:
            self.status_changed.emit("Serial not connected; command not sent")
            return

        try:
            self._ser.write((command + "\n").encode("utf-8"))
            self._ser.flush()
            self.status_changed.emit(f"Sent '{command}' to {self.SERIAL_PORT}")
        except Exception as e:
            self.status_changed.emit(f"Serial error while sending command: {e}")


class MeasurementCommandSender(QThread):
    """Background thread that sends a measurement command to the MCU."""

    status_changed = Signal(str)

    def __init__(self, command: str, port: str, baud_rate: int, parent=None):
        super().__init__(parent)
        self.command = command
        self.port = port
        self.baud_rate = baud_rate

    def run(self):
        if not SERIAL_AVAILABLE:
            self.status_changed.emit("pyserial not installed")
            return

        try:
            ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            self.status_changed.emit(f"Connected to {self.port}")

            ser.write((self.command + "\n").encode("utf-8"))
            ser.flush()
            self.status_changed.emit(f"Sent '{self.command}' to {self.port}")
            ser.close()
        except Exception as e:
            self.status_changed.emit(f"Serial error: {e}")


class ThicknessDiscIndicator(QWidget):
    """Simple 3D-like disc indicator used for thickness visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 0.5
        self.setFixedSize(126, 78)

    def set_ratio(self, ratio: float):
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        disc_w = w - 12.0
        top_h = 22.0
        x = (w - disc_w) / 2.0
        bottom_rim_y = 24.0

        # Higher thickness -> thicker side wall, with a fixed bottom base.
        side_h = 6.0 + (self._ratio * 12.0)
        top_y = bottom_rim_y - side_h
        body_top = top_y + (top_h / 2.0)

        # Soft cast shadow.
        shadow = QRadialGradient(x + disc_w * 0.65, body_top + side_h + 8.0, disc_w * 0.55)
        shadow.setColorAt(0.0, QColor(125, 168, 200, 95))
        shadow.setColorAt(1.0, QColor(125, 168, 200, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow)
        painter.drawEllipse(QRectF(x + 8.0, body_top + side_h - 1.0, disc_w * 0.95, top_h * 0.95))

        # Side wall.
        side_grad = QLinearGradient(x, body_top, x + disc_w, body_top)
        side_grad.setColorAt(0.0, QColor("#b8d8ef"))
        side_grad.setColorAt(0.5, QColor("#a4c8e2"))
        side_grad.setColorAt(1.0, QColor("#7ea7c7"))
        painter.setBrush(side_grad)
        painter.drawRoundedRect(QRectF(x, body_top, disc_w, side_h), top_h / 2.0, top_h / 2.0)

        # Bottom rim for depth.
        painter.setBrush(QColor("#7fa8c7"))
        painter.drawEllipse(QRectF(x, body_top + side_h - (top_h / 2.0), disc_w, top_h))

        # Top surface.
        top_grad = QLinearGradient(x, top_y, x, top_y + top_h)
        top_grad.setColorAt(0.0, QColor("#f0f5f2"))
        top_grad.setColorAt(1.0, QColor("#dfe7e2"))
        painter.setBrush(top_grad)
        painter.setPen(QPen(QColor("#d8e1dc"), 1.0))
        painter.drawEllipse(QRectF(x, top_y, disc_w, top_h))


class MiniThermometer(QWidget):
    """Compact thermometer indicator for temperature visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.5
        self.setFixedSize(20, 48)

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, float(level)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        tube_x = 6.0
        tube_y = 4.0
        tube_w = 8.0
        tube_h = 30.0
        bulb_r = 6.5

        # Glass tube background.
        painter.setPen(QPen(QColor("#8ba9c2"), 1.0))
        painter.setBrush(QColor("#e8f3fb"))
        painter.drawRoundedRect(QRectF(tube_x, tube_y, tube_w, tube_h), 4.0, 4.0)

        # Fill level inside the tube.
        fill_h = max(1.0, self._level * (tube_h - 2.0))
        fill_y = tube_y + tube_h - 1.0 - fill_h
        fill_grad = QLinearGradient(tube_x, fill_y, tube_x, fill_y + fill_h)
        fill_grad.setColorAt(0.0, QColor("#f97316"))
        fill_grad.setColorAt(1.0, QColor("#ef4444"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill_grad)
        painter.drawRoundedRect(QRectF(tube_x + 1.0, fill_y, tube_w - 2.0, fill_h), 3.0, 3.0)

        # Bulb.
        painter.setBrush(QColor("#ef4444"))
        painter.drawEllipse(QRectF((self.width() - (bulb_r * 2.0)) / 2.0, tube_y + tube_h - 1.0, bulb_r * 2.0, bulb_r * 2.0))


class MeasurementModeTile(QPushButton):
    """Painted menu tile used to present a measurement mode option."""
    activated = Signal()

    def __init__(self, title: str, point_count: int, show_joystick: bool = False, random_points: int = 0, parent=None):
        super().__init__(parent)
        self._title = title
        self._point_count = point_count
        self._show_joystick = show_joystick
        self._random_points = int(random_points or 0)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        # make tiles checkable so selection can be visualized
        self.setCheckable(True)
        # Slightly shorter vertically for better proportion
        self.setFixedSize(360, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.NoFocus)
        if self._random_points > 0:
            # Fixed square points: 45, 135, 225, 315 degrees (forms a square when connected)
            self._random_angles = [math.radians(45), math.radians(135), math.radians(225), math.radians(315)]

    def mouseDoubleClickEvent(self, event):
        # emit activated so parent can start measurement on double-click
        try:
            self.activated.emit()
        except Exception:
            pass
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        hovered = self.underMouse()
        pressed = self.isDown()

        selected = bool(self.isChecked())

        if selected:
            base_top = QColor("#27459a")
            base_bottom = QColor("#1c3490")
            if hovered:
                base_top = QColor("#2d4fb0")
                base_bottom = QColor("#243f9c")
            if pressed:
                base_top = QColor("#18347e")
                base_bottom = QColor("#102c72")

            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, base_top)
            gradient.setColorAt(1.0, base_bottom)
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, 16.0, 16.0)
        else:
            # Unselected: outline with accent color, inner filled with card background
            pen = QPen(QColor(ACCENT_COLOR), 2.8)
            painter.setPen(pen)
            painter.setBrush(QColor(CARD_COLOR))
            painter.drawRoundedRect(rect, 16.0, 16.0)

        # subtle inner highlight/border
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1.0))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 15.0, 15.0)

        title_rect = rect.adjusted(8, 7, -8, -rect.height() // 2)
        title_font = QFont("Segoe UI", 15, QFont.Bold)
        painter.setFont(title_font)
        if selected:
            painter.setPen(QColor("#ffffff"))
        else:
            painter.setPen(QColor(ACCENT_COLOR))
        painter.drawText(title_rect, Qt.AlignHCenter | Qt.AlignTop, self._title)

        self._paint_measurement_visual(painter, rect)

        # If not selected, draw small accent markers in corners? (optional)

    def _paint_measurement_visual(self, painter: QPainter, rect: QRectF):
        visual_top = rect.top() + 68.0
        visual_rect = QRectF(rect.left() + 22.0, visual_top, rect.width() - 44.0, rect.height() - visual_top - 16.0)

        # If randomized points requested (manual), draw target then randomized dots
        if getattr(self, '_random_angles', None):
            # Center the target visual and draw four points that form a square.
            target_rect = QRectF(visual_rect)
            inner_r = self._paint_target_visual(painter, target_rect, point_count=0)
            cx = target_rect.center().x()
            cy = target_rect.center().y() + 2.0
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ef233c"))
            dot_r = 5.0
            for ang in self._random_angles[:4]:
                px = cx + math.cos(ang) * inner_r
                py = cy - math.sin(ang) * inner_r
                painter.drawEllipse(QRectF(px - dot_r, py - dot_r, dot_r * 2.0, dot_r * 2.0))
        elif self._show_joystick:
            target_rect = QRectF(visual_rect.left() + 1.0, visual_rect.top() + 2.0, visual_rect.width() * 0.58, visual_rect.height())
            joystick_rect = QRectF(visual_rect.right() - 64.0, visual_rect.center().y() - 42.0, 58.0, 78.0)
            self._paint_target_visual(painter, target_rect, point_count=5)
            self._paint_joystick_visual(painter, joystick_rect)
        else:
            self._paint_target_visual(painter, visual_rect, point_count=self._point_count)

    def _paint_target_visual(self, painter: QPainter, rect: QRectF, point_count: int):
        center_x = rect.center().x()
        center_y = rect.center().y() + 2.0
        outer_radius = min(rect.width(), rect.height()) * 0.34
        inner_radius = outer_radius * (2.0 / 3.0)

        # Use white when selected, otherwise use accent navy so circles remain visible
        if self.isChecked():
            circle_pen = QPen(QColor(255, 255, 255, 245), 3.0)
            tick_pen = QPen(QColor(255, 255, 255, 220), 2.2)
        else:
            circle_pen = QPen(QColor(ACCENT_COLOR), 3.0)
            tick_pen = QPen(QColor(ACCENT_COLOR), 2.2)

        painter.setPen(circle_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(center_x - outer_radius, center_y - outer_radius, outer_radius * 2.0, outer_radius * 2.0))
        painter.drawEllipse(QRectF(center_x - inner_radius, center_y - inner_radius, inner_radius * 2.0, inner_radius * 2.0))

        painter.setPen(tick_pen)
        tick_length = outer_radius * 0.18
        painter.drawLine(center_x, center_y - outer_radius - 7.0, center_x, center_y - outer_radius - 7.0 + tick_length)
        painter.drawLine(center_x, center_y + outer_radius + 7.0, center_x, center_y + outer_radius + 7.0 - tick_length)
        painter.drawLine(center_x - outer_radius - 7.0, center_y, center_x - outer_radius - 7.0 + tick_length, center_y)
        painter.drawLine(center_x + outer_radius + 7.0, center_y, center_x + outer_radius + 7.0 - tick_length, center_y)

        # Determine point positions. If point_count == 0, do not draw any points
        if point_count == 0:
            point_positions = []
        elif point_count == 1:
            point_positions = [(center_x, center_y)]
        elif point_count == 5:
            point_positions = [
                (center_x, center_y),
                (center_x, center_y - inner_radius),
                (center_x + inner_radius, center_y),
                (center_x, center_y + inner_radius),
                (center_x - inner_radius, center_y),
            ]
        else:
            point_positions = [(center_x, center_y)]
            ring_radius = inner_radius
            angles = [0, 45, 90, 135, 180, 225, 270, 315]
            for angle in angles:
                radians_value = math.radians(angle)
                point_positions.append((center_x + math.cos(radians_value) * ring_radius, center_y - math.sin(radians_value) * ring_radius))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ef233c"))
        for point_x, point_y in point_positions:
            painter.drawEllipse(QRectF(point_x - 4.0, point_y - 4.0, 8.0, 8.0))

        return inner_radius

    def _paint_joystick_visual(self, painter: QPainter, rect: QRectF):
        painter.save()
        painter.translate(rect.center())

        black_pen = QPen(QColor("#111111"), 3.2)
        black_pen.setJoinStyle(Qt.RoundJoin)
        black_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(black_pen)

        painter.setBrush(QColor("#ffffff"))

        base = QPainterPath()
        base.moveTo(-19.0, 18.0)
        base.lineTo(-19.0, 30.0)
        base.lineTo(19.0, 30.0)
        base.lineTo(19.0, 18.0)
        base.lineTo(14.0, 11.0)
        base.lineTo(-14.0, 11.0)
        base.closeSubpath()
        painter.drawPath(base)

        top = QPainterPath()
        top.moveTo(-13.0, 11.0)
        top.lineTo(-8.5, 2.0)
        top.lineTo(8.5, 2.0)
        top.lineTo(13.0, 11.0)
        top.closeSubpath()
        painter.drawPath(top)

        # Stick.
        painter.drawLine(0.0, 11.0, 0.0, -12.0)

        # Knob with the small highlight dots from the reference.
        painter.drawEllipse(QRectF(-10.0, -31.0, 20.0, 20.0))
        painter.setBrush(QColor("#111111"))
        painter.drawEllipse(QRectF(-4.0, -25.0, 8.0, 8.0))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(-6.0, -28.0, 2.4, 2.4))
        painter.drawEllipse(QRectF(-3.4, -26.5, 2.0, 2.0))

        # Front lip and side face to echo the blocky base in the image.
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(-24.0, 23.0, 48.0, 10.0), 5.0, 5.0)

        side = QPainterPath()
        side.moveTo(19.0, 18.0)
        side.lineTo(27.0, 23.0)
        side.lineTo(27.0, 33.0)
        side.lineTo(19.0, 30.0)
        side.closeSubpath()
        painter.drawPath(side)

        painter.restore()


class HomePage(QWidget):
    # thickness_mm, carrier_type, wafer_area_in2, diameter_inch, wafer_area_cm2, x_cm, y_cm, num_points, temp_c, mode
    start_measurement = Signal(float, str, float, int, float, float, float, int, float, str)
    view_historical_data = Signal()

    MAX_WAFER_DIAMETER_INCH = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_type = "N (100)"
        self._updating_wafer = False
        self._current_diameter = self.MAX_WAFER_DIAMETER_INCH
        self._joystick_x = 0.0
        self._joystick_y = 0.0
        self._temperature_c = 25.0
        self._thickness_min = 280
        self._thickness_max = 725

        self._build_ui()
        self._setup_serial_joystick()

    def _show_warning(self, title: str, message: str):
        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Warning)
        dlg.setWindowTitle(title)
        dlg.setText(message)
        dlg.setStyleSheet(
            f"QMessageBox {{ background-color: {BACKGROUND_COLOR}; }}\n"
            "QLabel { color: black; background-color: transparent; }\n"
            "QPushButton { color: black; }"
        )
        dlg.exec()

    def _diameter_to_area(self, diameter: float) -> float:
        area_in2 = math.pi * (diameter / 2) ** 2
        return area_in2 * 6.4516

    def _area_to_diameter(self, area_cm2: float) -> float:
        area_in2 = area_cm2 / 6.4516
        return 2 * math.sqrt(area_in2 / math.pi)

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BACKGROUND_COLOR};")

        main = QVBoxLayout(self)
        main.setContentsMargins(40, 30, 40, 30)
        main.setSpacing(0)

        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_COLOR};
                border-radius: 34px;
            }}
        """
        )
        apply_neumorphic_shadow(card, radius=24, blur_radius=32)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(22)

        title = QLabel("Four Point Measurement")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {TEXT_COLOR};")
        card_layout.addWidget(title)

        split = QHBoxLayout()
        split.setSpacing(24)

        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        split.addWidget(left_panel, 1)
        split.addWidget(right_panel, 1)
        card_layout.addLayout(split)

        main.addWidget(card)

    def _build_left_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_COLOR};
                border-radius: 24px;
            }}
            QLabel {{ color: {TEXT_COLOR}; }}
            QLineEdit {{
                background: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 10px;
                padding: 6px 8px;
                color: {TEXT_COLOR};
                font-size: 12pt;
                font-weight: bold;
            }}
        """
        )
        apply_neumorphic_shadow(panel, radius=16, blur_radius=22)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(11)
        layout.setAlignment(Qt.AlignTop)

        self._left_stack = QStackedWidget()
        layout.addWidget(self._left_stack)

        input_page = QWidget()
        form_layout = QVBoxLayout(input_page)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(11)
        form_layout.setAlignment(Qt.AlignTop)

        # Center the homepage form content vertically within the left panel.
        form_layout.addStretch(1)

        thickness_card = QFrame()
        thickness_card.setMaximumHeight(132)
        thickness_layout = QVBoxLayout(thickness_card)
        thickness_layout.setContentsMargins(0, 0, 0, 0)
        thickness_layout.setSpacing(2)

        thickness_split = QHBoxLayout()
        thickness_split.setSpacing(8)

        thickness_left = QFrame()
        thickness_left_layout = QVBoxLayout(thickness_left)
        thickness_left_layout.setContentsMargins(0, 0, 0, 0)
        thickness_left_layout.setSpacing(4)

        thickness_label = QLabel("Thickness (um)")
        thickness_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        thickness_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        thickness_left_layout.addWidget(thickness_label)

        input_visual_row = QHBoxLayout()
        input_visual_row.setContentsMargins(0, 0, 0, 0)
        input_visual_row.setSpacing(8)
        input_visual_row.addStretch(1)

        self.tedit = QLineEdit("500")
        # Keep numeric input, but allow out-of-range values so warning logic can run.
        self.tedit.setValidator(QIntValidator(0, 9999))
        self.tedit.setAlignment(Qt.AlignCenter)
        # Keep the numeric field compact but give it a bit more room and internal padding
        self.tedit.setFixedWidth(64)
        self.tedit.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_COLOR};
                font-size: 14pt;
                font-weight: bold;
                padding-left: 6px;
                padding-right: 6px;
            }}
            """
        )
        self.tedit.editingFinished.connect(self._manual_changed)

        thickness_input_box = QFrame()
        thickness_input_box.setFixedWidth(136)
        thickness_input_box.setFixedHeight(50)
        thickness_input_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 12px;
            }}
            """
        )
        thickness_input_layout = QHBoxLayout(thickness_input_box)
        thickness_input_layout.setContentsMargins(8, 0, 8, 0)
        thickness_input_layout.setSpacing(6)
        thickness_input_layout.addWidget(self.tedit)
        thickness_input_layout.addStretch(1)

        thickness_unit = QLabel("um")
        thickness_unit.setStyleSheet(
            f"color: {ACCENT_COLOR}; font-size: 14pt; font-weight: bold; border: none; background: transparent; padding-left: 2px;"
        )
        thickness_input_layout.addWidget(thickness_unit, alignment=Qt.AlignVCenter | Qt.AlignRight)

        input_visual_row.addWidget(thickness_input_box)

        visual_col = QVBoxLayout()
        visual_col.setContentsMargins(0, 0, 0, 0)
        visual_col.setSpacing(1)
        visual_col.addSpacing(12)

        self.thickness_disc = ThicknessDiscIndicator()
        visual_col.addWidget(self.thickness_disc, alignment=Qt.AlignHCenter)

        input_visual_row.addLayout(visual_col)
        input_visual_row.addStretch(1)

        thickness_left_layout.addLayout(input_visual_row)

        thickness_right = QFrame()
        thickness_right_layout = QVBoxLayout(thickness_right)
        thickness_right_layout.setContentsMargins(8, 0, 8, 0)
        thickness_right_layout.setSpacing(4)

        temperature_label = QLabel("Room Temperature")
        temperature_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        temperature_label.setAlignment(Qt.AlignCenter)
        thickness_right_layout.addWidget(temperature_label)
        thickness_right_layout.addSpacing(10)

        temperature_value_box = QFrame()
        temperature_value_box.setObjectName("temperatureValueBox")
        temperature_value_box.setFixedWidth(208)
        temperature_value_box.setFixedHeight(74)
        temperature_value_box.setStyleSheet(
            f"""
            QFrame#temperatureValueBox {{
                background-color: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 12px;
            }}
            """
        )
        temperature_value_layout = QHBoxLayout(temperature_value_box)
        temperature_value_layout.setContentsMargins(10, 7, 10, 7)
        temperature_value_layout.setSpacing(6)

        temp_values_col = QVBoxLayout()
        temp_values_col.setContentsMargins(0, 0, 0, 0)
        temp_values_col.setSpacing(0)

        self.temperature_k_value = QLabel("303.2 K")
        self.temperature_k_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.temperature_k_value.setStyleSheet(
            f"color: {TEXT_COLOR}; font-size: 13pt; font-weight: bold;"
        )
        temp_values_col.addWidget(self.temperature_k_value)

        self.temperature_c_value = QLabel("30.0 C")
        self.temperature_c_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.temperature_c_value.setStyleSheet(
            f"color: #4b5563; font-size: 11pt; font-weight: 600;"
        )
        temp_values_col.addWidget(self.temperature_c_value)

        temperature_value_layout.addLayout(temp_values_col, 1)

        self.temperature_thermometer = MiniThermometer()
        temperature_value_layout.addWidget(self.temperature_thermometer, alignment=Qt.AlignRight | Qt.AlignVCenter)

        thickness_right_layout.addWidget(temperature_value_box, alignment=Qt.AlignHCenter)

        thickness_split.addWidget(thickness_left, 1, Qt.AlignTop)
        thickness_split.addWidget(thickness_right, 1, Qt.AlignTop)

        thickness_layout.addLayout(thickness_split)
        self._update_thickness_visual(500)
        self._update_temperature_display(self._temperature_c)
        form_layout.addWidget(thickness_card)

        diameter_card = QFrame()
        diameter_layout = QVBoxLayout(diameter_card)
        diameter_layout.setSpacing(8)

        diameter_label = QLabel("Wafer Diameter (inch)")
        diameter_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        diameter_label.setAlignment(Qt.AlignCenter)
        diameter_layout.addWidget(diameter_label)

        diam_buttons_row = QHBoxLayout()
        diam_buttons_row.setSpacing(8)
        self.diameter_buttons = {}

        button_style = f"""
            QPushButton {{
                background-color: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 12px;
                min-height: 42px;
                min-width: 42px;
                font-weight: bold;
                font-size: 13pt;
            }}
            QPushButton[selected=\"true\"] {{
                background-color: {ACCENT_COLOR};
                color: white;
            }}
        """

        for inch in range(1, self.MAX_WAFER_DIAMETER_INCH + 1):
            btn = QPushButton(str(inch))
            btn.setCheckable(True)
            btn.setStyleSheet(button_style)
            btn.clicked.connect(lambda _checked, d=inch: self._diameter_button_clicked(d))
            self.diameter_buttons[inch] = btn
            diam_buttons_row.addWidget(btn)

        self.diameter_buttons[self.MAX_WAFER_DIAMETER_INCH].setChecked(True)
        self.diameter_buttons[self.MAX_WAFER_DIAMETER_INCH].setProperty("selected", True)
        diameter_layout.addLayout(diam_buttons_row)

        type_card = QFrame()
        type_layout = QVBoxLayout(type_card)
        type_layout.setSpacing(8)

        type_label = QLabel("Doping Type")
        type_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        type_label.setAlignment(Qt.AlignCenter)
        type_layout.addWidget(type_label)

        toggle_grid = QGridLayout()
        toggle_grid.setHorizontalSpacing(8)
        toggle_grid.setVerticalSpacing(8)
        self.type_buttons = {}
        # 2x2 layout with N on the left column and P on the right column.
        type_options = ["N (100)", "P (100)", "N (111)", "P (111)"]

        for idx, option in enumerate(type_options):
            btn = QPushButton(option)
            btn.setCheckable(True)
            btn.clicked.connect(self._segment_clicked)
            btn.setMinimumHeight(42)
            btn.setProperty("type_option", option)
            self.type_buttons[option] = btn
            row = idx // 2
            col = idx % 2
            toggle_grid.addWidget(btn, row, col)

        self._apply_segment_style()
        self._set_type("N (100)", initial=True)
        type_layout.addLayout(toggle_grid)
        form_layout.addWidget(type_card)
        form_layout.addWidget(diameter_card)

        area_card = QFrame()
        area_layout = QVBoxLayout(area_card)
        area_layout.setSpacing(8)

        area_label = QLabel("Wafer Area (cm²)")
        area_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        area_label.setAlignment(Qt.AlignCenter)
        area_layout.addWidget(area_label)

        self.wafer_area_slider = QSlider(Qt.Horizontal)
        area_min = int(self._diameter_to_area(1) * 100)
        area_max = int(self._diameter_to_area(self.MAX_WAFER_DIAMETER_INCH) * 100)
        area_default = self._diameter_to_area(self._current_diameter)

        self.wafer_area_slider.setRange(area_min, area_max)
        self.wafer_area_slider.setValue(int(area_default * 100))
        self.wafer_area_slider.valueChanged.connect(self._wafer_area_slider_changed)
        self.wafer_area_slider.setStyleSheet(
            """
            QSlider::groove:horizontal {
                background-color: #9a9a9a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background-color: #5e5e5e;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background-color: #3d3d3d;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            """
        )
        area_layout.addWidget(self.wafer_area_slider)

        self.wafer_area_edit = QLineEdit(f"{area_default:.2f}")
        self.wafer_area_edit.setValidator(QDoubleValidator(0.01, 9999.99, 2))
        self.wafer_area_edit.setAlignment(Qt.AlignCenter)
        self.wafer_area_edit.setFixedWidth(80)
        self.wafer_area_edit.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_COLOR};
                font-size: 14pt;
                font-weight: bold;
            }}
        """
        )
        self.wafer_area_edit.editingFinished.connect(self._wafer_area_manual_changed)

        area_input_box = QFrame()
        area_input_box.setFixedWidth(190)
        area_input_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 14px;
            }}
            """
        )
        area_input_layout = QHBoxLayout(area_input_box)
        area_input_layout.setContentsMargins(10, 2, 10, 2)
        area_input_layout.setSpacing(2)
        area_input_layout.addWidget(self.wafer_area_edit)

        area_unit = QLabel("cm²")
        area_unit.setStyleSheet(
            f"color: {ACCENT_COLOR}; font-size: 14pt; font-weight: bold; border: none; background: transparent;"
        )
        area_input_layout.addWidget(area_unit)

        area_layout.addWidget(area_input_box, alignment=Qt.AlignHCenter)
        form_layout.addWidget(area_card)

        button_stack = QVBoxLayout()
        button_stack.setContentsMargins(0, 30, 0, 0)
        button_stack.setSpacing(8)

        start = QPushButton("Start Measurement")
        start.setCursor(Qt.PointingHandCursor)
        start.clicked.connect(self._start)
        start.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        history = QPushButton("View Historical Data")
        history.setCursor(Qt.PointingHandCursor)
        history.clicked.connect(self.view_historical_data.emit)
        history.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        start.setMinimumHeight(50)
        start.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {ACCENT_COLOR};
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 13pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}
        """
        )

        history.setMinimumHeight(50)
        history.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {ACCENT_COLOR};
                border: 2px solid {ACCENT_COLOR};
                border-radius: 20px;
                font-size: 13pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #f8fafc; }}
        """
        )

        button_stack.addWidget(start)
        button_stack.addWidget(history)
        form_layout.addLayout(button_stack)

        exit_btn = QPushButton("Exit")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setMinimumHeight(38)
        exit_btn.setFixedWidth(170)
        exit_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #dc2626;
                color: white;
                border: 2px solid black;
                border-radius: 14px;
                font-size: 12pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #b91c1c; }}
        """
        )
        exit_btn.clicked.connect(lambda: QApplication.instance().quit())

        # Anchor the Exit button to the bottom-left of the left panel.
        # Add a stretch so everything above takes remaining space, then a
        # horizontal row containing the exit button left-aligned.
        form_layout.addStretch(1)
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.addWidget(exit_btn)
        bottom_row.addStretch(1)
        form_layout.addLayout(bottom_row)

        self._left_stack.addWidget(input_page)
        self._left_stack.addWidget(self._build_measurement_menu_page())
        self._left_stack.setCurrentIndex(0)

        return panel

    def _build_measurement_menu_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 60, 16, 10)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("Measurement Menu")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT_COLOR};")

        # Centered container for title + tiles
        center_box = QWidget()
        center_layout = QVBoxLayout(center_box)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(12)
        center_layout.setAlignment(Qt.AlignCenter)

        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(8)
        grid_layout.setVerticalSpacing(8)

        tile_specs = [
            ("1-Point\nMeasurement", 1, False, 0),
            ("5-Points\nMeasurement", 5, False, 0),
            ("9-Points\nMeasurement", 9, False, 0),
            ("Manual\nMeasurement", 0, False, 4),
        ]

        # Button group to make selection exclusive and styleable like the segment controls
        btn_group = QButtonGroup(page)
        btn_group.setExclusive(True)

        for index, (label, point_count, show_joystick, random_points) in enumerate(tile_specs):
            tile = MeasurementModeTile(label, point_count, show_joystick, random_points)
            # require double-click to activate measurement
            tile.activated.connect(lambda m=label.replace("\n", " "): self._run_selected_measurement(m))
            btn_group.addButton(tile)
            grid_layout.addWidget(tile, index // 2, index % 2)

        # Allow grid to size naturally to avoid being overlapped by the Return button
        grid_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        # Assemble centered content
        center_layout.addWidget(title)
        center_layout.addWidget(grid_container, 0, Qt.AlignCenter)

        # Add the center content and allow it to expand so Return sits below tiles
        center_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(center_box)

        return_btn = QPushButton("Return")
        return_btn.setCursor(Qt.PointingHandCursor)
        return_btn.setMinimumHeight(40)
        return_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {ACCENT_COLOR};
                color: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 20px;
                font-size: 13pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}
        """
        )
        return_btn.clicked.connect(self._show_input_form)
        # Use a stretch so the Return button stays below the tiles
        layout.addStretch(1)
        layout.addWidget(return_btn)

        # small spacing between the Return button and instructions
        layout.addSpacing(12)

        # Place instruction text below the Return button
        info_label = QLabel()
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        info_label.setStyleSheet("font-size:11pt; color: #756d61; padding-left:0px; padding-top:8px;")
        info_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info_label.setText(
            "• Double-click to begin a measurement.\n"
            "• Pre-determined point(s) distance is based on 2/3R from the center point.\n"
            "• Manual measurement requires joystick to move the chuck manually."
        )
        layout.addWidget(info_label)

        return page

    def _build_right_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_COLOR};
                border-radius: 24px;
            }}
            QLabel {{ color: {TEXT_COLOR}; }}
        """
        )
        apply_neumorphic_shadow(panel, radius=16, blur_radius=22)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("Wafer Mapping")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        #subtitle = QLabel("Joystick from Arduino (COM7) | Line 1 = X, Line 2 = Y")
        #subtitle.setAlignment(Qt.AlignCenter)
        #subtitle.setStyleSheet("font-size: 10pt; color: #756d61;")
        #layout.addWidget(subtitle)

        self.wafer_map = WaferMapWidget()
        self.wafer_map.set_wafer_area_cm2(self._diameter_to_area(self._current_diameter))
        self.wafer_map.set_doping_type(self._current_type)
        layout.addWidget(self.wafer_map, 1)

        xy_box = QFrame()
        xy_box.setStyleSheet(
            f"""
            QFrame {{
                border: 2px solid {ACCENT_COLOR};
                border-radius: 12px;
                background: white;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
            """
        )
        xy_layout = QHBoxLayout(xy_box)
        xy_layout.setContentsMargins(12, 8, 12, 8)

        self.xy_label = QLabel("X: 0.00 cm | Y: 0.00 cm")
        self.xy_label.setAlignment(Qt.AlignCenter)
        self.xy_label.setStyleSheet(f"font-size: 12pt; font-weight: bold; color: {TEXT_COLOR};")
        xy_layout.addWidget(self.xy_label)

        self._serial_status = QLabel("Connecting to COM3...")
        self._serial_status.setAlignment(Qt.AlignCenter)
        self._serial_status.setStyleSheet("font-size: 9pt; color: #8d857a;")
        layout.addWidget(self._serial_status)

        layout.addWidget(xy_box)
        return panel

    def _setup_serial_joystick(self):
        self._serial_reader = SerialReader(self)
        self._serial_reader.position_received.connect(self._on_position_received)
        self._serial_reader.temperature_received.connect(self._on_temperature_received)
        self._serial_reader.status_changed.connect(self._on_serial_status)
        self._serial_reader.start()

    def _on_position_received(self, x_cm: float, y_cm: float, contact_made: bool):
        self._joystick_x = x_cm
        self._joystick_y = y_cm
        self.wafer_map.set_probe_point(x_cm, y_cm)
        status_text = "Contact: TRUE" if contact_made else "Contact: FALSE"
        self.xy_label.setText(f"X: {x_cm:.2f} cm | Y: {y_cm:.2f} cm | {status_text}")

    def _on_serial_status(self, msg: str):
        self._serial_status.setText(msg)

    def _on_temperature_received(self, temp_c: float):
        self._update_temperature_display(temp_c)

    def _start_measurement_command_sender(self, command: str, port: str, baudrate: int):
        if hasattr(self, "_serial_reader") and self._serial_reader is not None and self._serial_reader.isRunning():
            self._serial_reader.send_command(command)
            return

        self._on_serial_status("Serial reader not running; cannot send command")

    def _apply_segment_style(self):
        style = f"""
            QPushButton {{
                border: 2px solid {ACCENT_COLOR};
                border-radius: 10px;
                background: white;
                color: {ACCENT_COLOR_DARK};
                font-weight: bold;
                font-size: 14pt;
                min-height: 46px;
            }}
            QPushButton[active=\"true\"] {{
                background: {ACCENT_COLOR};
                color: white;
            }}
        """
        for btn in self.type_buttons.values():
            btn.setStyleSheet(style)

    def _set_type(self, t: str, initial: bool = False):
        self._current_type = t

        if hasattr(self, "wafer_map"):
            self.wafer_map.set_doping_type(t)

        for option, btn in self.type_buttons.items():
            is_active = option == t
            btn.setProperty("active", is_active)
            btn.setChecked(is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if not initial:
            pass

    def _segment_clicked(self):
        sender = self.sender()
        selected = sender.property("type_option")
        if selected in self.type_buttons:
            self._set_type(selected)

    def _manual_changed(self):
        try:
            v = int(float(self.tedit.text()))
            if v < self._thickness_min or v > self._thickness_max:
                self._show_warning(
                    "Invalid Thickness",
                    f"Thickness value {v} um is out of valid range.\n\nValid range: {self._thickness_min} - {self._thickness_max} um",
                )
                v = max(self._thickness_min, min(self._thickness_max, v))
                self.tedit.setText(f"{v}")
            self._update_thickness_visual(v)
        except ValueError:
            pass

    def _update_thickness_visual(self, thickness_um: int):
        ratio = (thickness_um - self._thickness_min) / (self._thickness_max - self._thickness_min)
        ratio = max(0.0, min(1.0, ratio))
        if hasattr(self, "thickness_disc"):
            self.thickness_disc.set_ratio(ratio)

    def _update_temperature_display(self, temp_c: float):
        self._temperature_c = float(temp_c)
        temp_k = self._temperature_c + 273.15
        # Visual scaling for thermometer: 15C..45C maps to 0..1.
        ratio = (self._temperature_c - 15.0) / 30.0
        ratio = max(0.0, min(1.0, ratio))
        self.temperature_c_value.setText(f"{self._temperature_c:.1f} C")
        self.temperature_k_value.setText(f"{temp_k:.1f} K")
        if hasattr(self, "temperature_thermometer"):
            self.temperature_thermometer.set_level(ratio)

    def _diameter_button_clicked(self, diameter):
        self._set_diameter_button_visual(diameter)

        self._current_diameter = diameter
        area_cm2 = self._diameter_to_area(diameter)
        self.wafer_map.set_wafer_area_cm2(area_cm2)

        if not self._updating_wafer:
            self._updating_wafer = True
            self.wafer_area_slider.setValue(int(area_cm2 * 100))
            self.wafer_area_edit.setText(f"{area_cm2:.2f}")
            self._updating_wafer = False

    def _set_diameter_button_visual(self, diameter: int):
        for btn in self.diameter_buttons.values():
            btn.setChecked(False)
            btn.setProperty("selected", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        active = self.diameter_buttons[diameter]
        active.setChecked(True)
        active.setProperty("selected", True)
        active.style().unpolish(active)
        active.style().polish(active)

    def _wafer_area_slider_changed(self, v):
        area_cm2 = v / 100
        self.wafer_area_edit.setText(f"{area_cm2:.2f}")
        self.wafer_map.set_wafer_area_cm2(area_cm2)

        if not self._updating_wafer:
            self._updating_wafer = True
            diameter = self._area_to_diameter(area_cm2)
            diameter_int = max(1, min(self.MAX_WAFER_DIAMETER_INCH, round(diameter)))
            self._current_diameter = diameter_int
            self._set_diameter_button_visual(diameter_int)
            self._updating_wafer = False

    def _wafer_area_manual_changed(self):
        try:
            v = float(self.wafer_area_edit.text())
            area_min = self.wafer_area_slider.minimum() / 100.0
            area_max = self.wafer_area_slider.maximum() / 100.0

            if v < area_min or v > area_max:
                self._show_warning(
                    "Invalid Wafer Area",
                    f"Wafer area value {v:.2f} cm\u00b2 is out of valid range.\n\nValid range: {area_min:.2f} - {area_max:.2f} cm\u00b2",
                )
                v = max(area_min, min(area_max, v))
                self.wafer_area_edit.setText(f"{v:.2f}")

            self.wafer_area_slider.setValue(int(v * 100))
        except ValueError:
            pass

    def _collect_valid_inputs(self):
        try:
            thickness_um = int(float(self.tedit.text()))
        except ValueError:
            self._show_warning(
                "Invalid Thickness",
                f"Please enter a valid numeric thickness value.\n\nValid range: {self._thickness_min} - {self._thickness_max} um",
            )
            return None

        try:
            wafer_area_cm2 = float(self.wafer_area_edit.text())
        except ValueError:
            self._show_warning("Invalid Wafer Area", "Please enter a valid wafer area.")
            return None

        if thickness_um < self._thickness_min or thickness_um > self._thickness_max:
            self._show_warning(
                "Invalid Thickness",
                f"Thickness value {thickness_um} um is out of valid range.\n\nValid range: {self._thickness_min} - {self._thickness_max} um",
            )
            thickness_um = max(self._thickness_min, min(self._thickness_max, thickness_um))
            self.tedit.setText(f"{thickness_um}")
            self._update_thickness_visual(thickness_um)
            return None

        area_min = self.wafer_area_slider.minimum() / 100.0
        area_max = self.wafer_area_slider.maximum() / 100.0
        if not (area_min <= wafer_area_cm2 <= area_max):
            self._show_warning(
                "Invalid Wafer Area",
                f"Wafer area must be between {area_min:.2f} and {area_max:.2f} cm\u00b2.",
            )
            return None

        return thickness_um, wafer_area_cm2

    def _start(self):
        valid = self._collect_valid_inputs()
        if valid is None:
            return
        self._show_measurement_menu()

    def _show_measurement_menu(self):
        if hasattr(self, "_left_stack"):
            self._left_stack.setCurrentIndex(1)

    def _show_input_form(self):
        if hasattr(self, "_left_stack"):
            self._left_stack.setCurrentIndex(0)

    def _run_selected_measurement(self, mode: str):
        valid = self._collect_valid_inputs()
        if valid is None:
            return

        thickness_um, wafer_area_cm2 = valid

        thickness_mm = thickness_um / 1000.0
        wafer_area_in2 = wafer_area_cm2 / 6.4516
        command_map = {
            "1-Point Measurement": "1",
            "5-Points Measurement": "5",
            "9-Points Measurement": "9",
            "Manual Measurement": "m",
        }
        num_points_map = {
            "1-Point Measurement": 1,
            "5-Points Measurement": 5,
            "9-Points Measurement": 9,
            "Manual Measurement": 1,
        }
        diameter_cm = self._current_diameter * 2.54
        # Always include wafer diameter (cm) with the command so MCU knows size
        command = f"{command_map.get(mode, '0')} {diameter_cm:.2f}"
        num_points = num_points_map.get(mode, 1)

        self._start_measurement_command_sender(command, "COM5", 115200)

        self.start_measurement.emit(
            thickness_mm,
            self._current_type,
            wafer_area_in2,
            self._current_diameter,
            wafer_area_cm2,
            self._joystick_x,
            self._joystick_y,
            num_points,
            self._temperature_c,
            mode,
        )
