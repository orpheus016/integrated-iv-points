# pages/loading_page.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QFrame, QHBoxLayout, QGridLayout, QPushButton, QMessageBox
)

from style import (
    BACKGROUND_COLOR, CARD_COLOR, TEXT_COLOR,
    ACCENT_COLOR, apply_neumorphic_shadow
)
from pages.wafer_map_widget import WaferMapWidget
from measurement import DEFAULT_TEMP_C, calculate_doping

import random

try:
    from software.scripts.integrate import FrontendBridge
    from software.config.config import SimulationConfig, SerialConfig
    _BACKEND_AVAILABLE = True
except ImportError:
    _BACKEND_AVAILABLE = False

class InfoCard(QFrame):
    def __init__(self, title, unit):
        super().__init__()
        self.setObjectName("infoCard")
        self.setMinimumHeight(220)
        self.setStyleSheet(
            f"""
            QFrame#infoCard {{
                background-color: {CARD_COLOR};
                border-radius: 18px;
                border: 2px solid {ACCENT_COLOR};
            }}
            QFrame#infoCard QLabel {{
                border: none;
                background: transparent;
            }}
            QLabel[role="title"] {{
                color: #8d857a;
                font-size: 20pt;
                font-weight: bold;
            }}
            QLabel[role="value"] {{
                color: {TEXT_COLOR};
                font-size: 36pt;
                font-weight: bold;
            }}
            QLabel[role="unit"] {{
                color: {ACCENT_COLOR};
                font-size: 18pt;
                font-weight: bold;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.title = QLabel(title)
        self.title.setProperty("role", "title")
        self.title.setAlignment(Qt.AlignCenter)

        row = QHBoxLayout()
        row.setContentsMargins(0, -7, 0, 0)
        row.setSpacing(2)
        row.setAlignment(Qt.AlignCenter)

        self.unit_text = unit
        self.val = QLabel()
        self.val.setProperty("role", "value")
        self.val.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.val.setTextFormat(Qt.RichText)
        self.val.setText(
            f"<div style='text-align:center; line-height:1;'><span style='display:inline-block; font-size:36pt; line-height:1; color:{TEXT_COLOR}; font-weight:bold; vertical-align:baseline;'>--</span>"
            f"<span style='display:inline-block; font-size:25pt; line-height:1; color:{ACCENT_COLOR}; font-weight:bold; vertical-align:baseline; margin-left:8px; transform:translateY(-6px);'>&nbsp;{self.unit_text}</span></div>"
        )

        row.addStretch()
        row.addWidget(self.val, 0, Qt.AlignBottom)
        row.addStretch()

        layout.addWidget(self.title, alignment=Qt.AlignHCenter)
        layout.addLayout(row)
    
    def set_value(self, v):
        try:
            unit_html = self.unit_text
        except Exception:
            unit_html = ""
        self.val.setText(
            f"<div style='text-align:center; line-height:1;'><span style='display:inline-block; font-size:36pt; line-height:1; color:{TEXT_COLOR}; font-weight:bold; vertical-align:baseline;'>{v}</span>"
            f"<span style='display:inline-block; font-size:25pt; line-height:1; color:{ACCENT_COLOR}; font-weight:bold; vertical-align:baseline; margin-left:6px; transform:translateY(-6px);'>&nbsp;{unit_html}</span></div>"
        )


class LoadingPage(QWidget):
    loading_complete = Signal()

    def __init__(self):
        super().__init__()
        self.measurement_points = []  # Store (voltage, current, x, y, doping) tuples
        self.current_point_index = 0
        self._num_points = 1
        self._thickness_mm = 1.0  # Default thickness
        self._carrier_type = "N (100)"  # Default carrier type
        self._diameter_inch = None
        self._wafer_area_cm2 = None
        self._temperature_c = DEFAULT_TEMP_C
        self._home_room_temp_c = DEFAULT_TEMP_C
        # Wafer measurement temperature (from MLX). Lock first MLX reading per run.
        self._wafer_temp_locked = False
        self._wafer_temp_value = None
        self._stream_active = False
        self._stream_voltage_v = None
        self._stream_current_a = None
        self._last_x_cm = 0.0
        self._last_y_cm = 0.0
        self._measurement_completed = False
        self._manual_mode = False
        self._serial_reader = None
        self._waiting_for_probe_contact = True

        # Backend VI-stability bridge -- does NOT open any serial port.
        # Receives data pushed from Qt signal handlers and runs the backbone
        # (BOCD by default) to find a stable Snapshot during each stream window.
        if _BACKEND_AVAILABLE:
            def send_cmd(cmd: str):
                if self._serial_reader is not None:
                    try:
                        self._serial_reader.send_command(cmd)
                    except Exception:
                        pass

            self._bridge = FrontendBridge(
                backbone_name="bocd",
                sim_config=SimulationConfig(),
                output_dir="software/output/ads1256",
                serial_config=SerialConfig(),
                write_callback=send_cmd
            )
            self._gain = SimulationConfig.gain
        else:
            self._bridge = None
            self._gain = 1.0
            print("backend not connected")

        self._build_ui()

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

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(24)

        # LEFT SIDE: MEASUREMENTS RESULTS
        left_card = QFrame()
        left_card.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_COLOR};
                border-radius: 36px;
            }}
        """)
        apply_neumorphic_shadow(left_card, radius=24, blur_radius=32)

        layout = QVBoxLayout(left_card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Vertically center the measurement content in the card.
        layout.addStretch(1)

        # Header: Measuring title on the left, temperature badges on the right
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Measuring...")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet(f"color: {TEXT_COLOR}; letter-spacing: 1px;")
        header.addWidget(title)
        header.addStretch()

        # Room temperature badge (SHT)
        self.room_temp_info = QLabel("Room Temp : -- C")
        self.room_temp_info.setFixedWidth(178)
        self.room_temp_info.setFixedHeight(34)
        self.room_temp_info.setAlignment(Qt.AlignCenter)
        self.room_temp_info.setStyleSheet(
            f"background-color: white; border: 1px solid #e6eef6; border-radius: 10px; color: #0f172a;"
            f" font-size: 11pt; font-weight: 600; padding: 4px 10px;"
        )
        header.addWidget(self.room_temp_info)

        # Wafer temperature badge (MLX)
        self.wafer_temp_info = QLabel("Wafer Temp : -- C")
        self.wafer_temp_info.setFixedWidth(178)
        self.wafer_temp_info.setFixedHeight(34)
        self.wafer_temp_info.setAlignment(Qt.AlignCenter)
        self.wafer_temp_info.setStyleSheet(
            f"background-color: white; border: 1px solid #e6eef6; border-radius: 10px; color: #0f172a;"
            f" font-size: 11pt; font-weight: 600; padding: 4px 10px;"
        )
        header.addWidget(self.wafer_temp_info)

        layout.addLayout(header)

        # Wafer summary below the header
        self.wafer_info = QLabel("Thickness: -- μm | Type: - | Diameter: -- inch | Area: -- cm²")
        self.wafer_info.setAlignment(Qt.AlignCenter)
        self.wafer_info.setMinimumHeight(80)
        self.wafer_info.setStyleSheet(
            f"background-color: white; border: 2px solid {ACCENT_COLOR}; border-radius: 12px;"
            f" color: {TEXT_COLOR}; font-size: 15pt; font-weight: bold; padding: 12px 18px;"
        )
        layout.addWidget(self.wafer_info)

        # Measurement cards grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.volt = InfoCard("Voltage", "V")
        self.curr = InfoCard("Current", "mA")
        self.rs = InfoCard("Sheet Resistance", "Ω/sq")
        self.rho = InfoCard("Resistivity", "Ω·cm")
        self.sig = InfoCard("Conductivity", "S/cm")
        self.dop = InfoCard("Doping", "cm⁻³")

        grid.addWidget(self.volt, 0, 0)
        grid.addWidget(self.curr, 0, 1)
        grid.addWidget(self.rs, 1, 0)
        grid.addWidget(self.rho, 1, 1)
        grid.addWidget(self.sig, 2, 0)
        grid.addWidget(self.dop, 2, 1)

        layout.addLayout(grid)

        # End measurement button, shown during active measurement runs
        self._end_button = QPushButton("End Measurement")
        self._end_button.setCursor(Qt.PointingHandCursor)
        self._end_button.setMinimumHeight(42)
        self._end_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {ACCENT_COLOR};
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 11pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {ACCENT_COLOR}; }}
        """
        )
        self._end_button.clicked.connect(self._on_end_clicked)
        self._end_button.setVisible(False)
        layout.addWidget(self._end_button)
        layout.addStretch(1)
        card_layout.addWidget(left_card, 1)

        # RIGHT SIDE: WAFER MAPPING
        right_card = QFrame()
        right_card.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_COLOR};
                border-radius: 36px;
            }}
        """)
        apply_neumorphic_shadow(right_card, radius=24, blur_radius=32)

        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(22, 22, 22, 18)
        right_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(18, 0, 18, 0)
        header.setSpacing(12)
        right_title = QLabel("Real-time Wafer Mapping")
        right_title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        right_title.setStyleSheet(f"color: {TEXT_COLOR};")
        header.addWidget(right_title)
        header.addStretch()

        # Right-side info block: restore the point counter to the original position
        right_block = QVBoxLayout()
        right_block.setSpacing(4)
        right_block.setContentsMargins(0, 6, 0, 0)

        self.points_info = QLabel("Waiting for contact...")
        self.points_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.points_info.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12pt; font-weight: bold; padding-right: 2px;")
        right_block.addWidget(self.points_info, alignment=Qt.AlignRight)

        header.addLayout(right_block)
        right_layout.addLayout(header)

        self.wafer_map = WaferMapWidget()
        right_layout.addWidget(self.wafer_map, 1)

        # XY Position display at bottom of wafer map
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
        self.xy_label.setStyleSheet(f"font-size: 11pt; font-weight: bold; color: {TEXT_COLOR};")
        xy_layout.addWidget(self.xy_label)

        right_layout.addWidget(xy_box)

        card_layout.addWidget(right_card, 1)

        main.addWidget(card)

    def set_num_points(self, num_points: int):
        """Set the expected number of measurement points."""
        self._num_points = max(1, num_points)
        self.measurement_points = []
        self.current_point_index = 0
        self._measurement_completed = False
        self._stream_active = False
        self._stream_voltage_v = None
        self._stream_current_a = None
        self._last_x_cm = 0.0
        self._last_y_cm = 0.0
        self._update_points_info()
        self.volt.set_value("--")
        self.curr.set_value("--")
        self.rs.set_value("--")
        self.rho.set_value("--")
        self.sig.set_value("--")
        self.dop.set_value("--")
        if hasattr(self, 'wafer_map'):
            self.wafer_map.clear_contours()
            self.wafer_map.set_probe_point(0.0, 0.0)
        if hasattr(self, 'xy_label'):
            self.xy_label.setText("X: 0.00 cm | Y: 0.00 cm")

    def set_wafer_params(
        self,
        diameter_inch: float,
        wafer_area_cm2: float,
        doping_type: str,
        thickness_mm: float = 1.0,
        carrier_type: str = "N (100)",
        temperature_c: float = DEFAULT_TEMP_C,
    ):
        """Configure the wafer map widget parameters and measurement parameters."""
        self._thickness_mm = thickness_mm
        self._carrier_type = carrier_type
        self._diameter_inch = float(diameter_inch)
        self._wafer_area_cm2 = float(wafer_area_cm2)
        self._temperature_c = float(temperature_c)
        self._home_room_temp_c = float(temperature_c)
        if hasattr(self, 'wafer_map'):
            self.wafer_map.set_wafer_diameter_inch(diameter_inch)
            self.wafer_map.set_wafer_area_cm2(wafer_area_cm2)
            self.wafer_map.set_doping_type(doping_type)
        if hasattr(self, 'wafer_info'):
            thickness_um = self._thickness_mm * 1000
            self.wafer_info.setText(
                f"Thickness: {thickness_um:.0f} μm | Type: {self._carrier_type} | Diameter: {self._diameter_inch:.0f} inch | Area: {self._wafer_area_cm2:.2f} cm²"
            )
        if hasattr(self, 'room_temp_info'):
            self.room_temp_info.setText(f"Room Temp : {self._home_room_temp_c:.1f} C")

    def on_temperature_received(self, temp_c: float):
        # SHT temperature (main page); store for reference but keep the displayed room temp from the homepage.
        try:
            self._sht_temperature = float(temp_c)
        except Exception:
            pass

    def get_temperature_c(self) -> float:
        # Return the measurement temperature: prefer locked MLX value, fallback to stored temperature
        if self._wafer_temp_locked and (self._wafer_temp_value is not None):
            return float(self._wafer_temp_value)
        return float(self._temperature_c)

    def on_mlx_temperature_received(self, temp_c: float):
        # Capture and lock the first MLX reading for the current measurement run
        try:
            if not self._wafer_temp_locked:
                self._wafer_temp_value = float(temp_c)
                self._wafer_temp_locked = True
                # Use MLX value for calculations
                self._temperature_c = float(self._wafer_temp_value)
                if hasattr(self, 'wafer_temp_info'):
                    self.wafer_temp_info.setText(f"Wafer Temp : {self._wafer_temp_value:.1f} C")
        except Exception:
            pass

    def on_position_received(self, x_cm: float, y_cm: float, contact_made: bool):
        """Update probe position continuously and collect data on contact events."""
        self._last_x_cm = float(x_cm)
        self._last_y_cm = float(y_cm)
        if hasattr(self, 'wafer_map'):
            self.wafer_map.set_probe_point(x_cm, y_cm)
        
        # Update XY display
        if hasattr(self, 'xy_label'):
            self.xy_label.setText(f"X: {x_cm:.2f} cm | Y: {y_cm:.2f} cm")
        
        self._waiting_for_probe_contact = not bool(contact_made)

    def on_measurement_started(self):
        """Reset the live V/I display at the start of a streamed measurement."""
        self._stream_active = True
        self._stream_voltage_v = None
        self._stream_current_a = None
        self._measurement_completed = False
        self.volt.set_value("--")
        self.curr.set_value("--")
        self.rs.set_value("--")
        self.rho.set_value("--")
        self.sig.set_value("--")
        self.dop.set_value("--")
        self._update_points_info()
        # Notify the backend bridge that a new measurement stream has started.
        # This resets the backbone and filters so each probe contact is independent.
        if self._bridge is not None:
            try:
                self._bridge.on_stream_start()
            except Exception:
                pass

    def on_voltage_received(self, voltage_v: float):
        try:
            self._stream_voltage_v = float(voltage_v)
            if self._bridge is None:
                display_v = self._stream_voltage_v / self._gain
                self.volt.set_value(f"{display_v:.3f}")
        except Exception:
            pass
        self._try_push_to_bridge()

    def on_current_received(self, current_a: float):
        """Update the live current reading during a measurement stream."""
        try:
            self._stream_current_a = float(current_a)
            if self._bridge is None:
                self.curr.set_value(f"{self._stream_current_a * 1000:.3f}")
        except Exception:
            pass
        self._try_push_to_bridge()

    def _try_push_to_bridge(self):
        """Forward the latest paired V/I reading to the backend bridge.

        The Arduino sends alternating V then I lines; both must be present
        before we push a sample so the bridge always sees a valid pair.
        The bridge accumulates these through its filters and backbone without
        opening any serial connection of its own.
        """
        if self._bridge is None:
            return
        if self._stream_voltage_v is None or self._stream_current_a is None:
            return
        try:
            res = self._bridge.on_sample(self._stream_voltage_v, self._stream_current_a)
            if res:
                filtered_v, snap = res
                if snap is not None:
                    display_v = snap.voltage / self._gain
                    display_i = snap.current_mA
                else:
                    display_v = filtered_v / self._gain
                    display_i = self._stream_current_a * 1000.0

                self.volt.set_value(f"{display_v:.3f}")
                self.curr.set_value(f"{display_i:.3f}")
        except Exception:
            pass

    def on_measurement_stopped(self):
        """Finalize the measurement once STOPSTREAM is received."""
        if self._measurement_completed:
            return

        # Ask the backend bridge for the backbone's stable Snapshot.
        # If the backbone found a stable window during the 5-second stream,
        # its filtered V/I values are more reliable than the raw last sample.
        # If no snapshot was produced (noisy signal, very short stream), fall
        # back to the raw last values so behaviour is identical to before.
        voltage_v = self._stream_voltage_v
        current_a = self._stream_current_a

        if self._bridge is not None:
            try:
                snapshot = self._bridge.on_stream_stop()
                if snapshot is not None:
                    voltage_v = snapshot.voltage
                    current_a = snapshot.current_mA / 1000.0
            except Exception:
                pass  # Keep raw fallback values on any bridge error

        if voltage_v is None or current_a is None:
            self._stream_active = False
            self.points_info.setText("Waiting for measurement data...")
            return

        voltage_v = voltage_v / self._gain

        result = calculate_doping(
            self._thickness_mm,
            self._carrier_type,
            voltage_v,
            current_a,
            self._temperature_c,
        )
        doping_cm3 = result['doping_cm3']

        self.add_measurement_point(self._last_x_cm, self._last_y_cm, voltage_v, current_a, doping_cm3)
        self._stream_active = False
        self._measurement_completed = True

        # Send command to reset current source to 4mA (stage 0)
        if self._serial_reader is not None:
            try:
                self._serial_reader.send_command("i 0")
            except Exception:
                try:
                    self._serial_reader.write(("i 0\n").encode("utf-8"))
                    self._serial_reader.flush()
                except Exception:
                    pass

        if not self._manual_mode and len(self.measurement_points) >= self._num_points:
            self.loading_complete.emit()

    def on_confirm_received(self):
        """Handle MCU confirmation request during manual probe movement."""
        if not self._manual_mode:
            return

        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Question)
        dlg.setWindowTitle("Confirm")
        dlg.setText("Confirm measurement?")
        dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dlg.setDefaultButton(QMessageBox.Yes)
        dlg.setStyleSheet(
            f"QMessageBox {{ background-color: {BACKGROUND_COLOR}; }}\n"
            "QLabel { color: black; background-color: transparent; }\n"
            "QPushButton { color: black; }"
        )

        response = dlg.exec()
        command = "Y" if response == QMessageBox.StandardButton.Yes else "N"

        if self._serial_reader is None:
            return

        try:
            self._serial_reader.send_command(command)
        except Exception:
            try:
                self._serial_reader.write((command + "\n").encode("utf-8"))
                self._serial_reader.flush()
            except Exception:
                pass


    def add_measurement_point(self, x_cm: float, y_cm: float, voltage_v: float, current_a: float, doping_cm3: float):
        """Add a measurement point and update display immediately."""
        self.measurement_points.append((voltage_v, current_a, x_cm, y_cm, doping_cm3))
        self.current_point_index = len(self.measurement_points)
        
        # Update wafer map visualization
        if hasattr(self, 'wafer_map'):
            self.wafer_map.set_probe_point(x_cm, y_cm)
            self.wafer_map.add_measurement_contour(x_cm, y_cm, doping_cm3)
        
        # Calculate and display measurement results
        result = calculate_doping(
            self._thickness_mm,
            self._carrier_type,
            voltage_v,
            current_a,
            self._temperature_c,
        )
        
        # Update display cards
        self.volt.set_value(f"{voltage_v:.2f}")
        self.curr.set_value(f"{current_a * 1000:.2f}")  # Convert A to mA
        self.rs.set_value(f"{result['sheet_res_ohm_per_sq']:.2f}")
        self.rho.set_value(f"{result['resistivity_ohm_cm']:.2e}")
        self.sig.set_value(f"{result['conductivity_s_per_cm']:.2e}")
        self.dop.set_value(f"{doping_cm3:.2e}")
        
        # Update points info
        self._update_points_info()

    def start_loading(self, num_points: int = 1):
        """Start measurement mode."""
        self.set_num_points(num_points)
        self._waiting_for_probe_contact = True
        if hasattr(self, '_end_button'):
            self._end_button.setVisible(True)
        # Lock wafer temperature to a fixed test value for now
        self._wafer_temp_locked = True
        self._wafer_temp_value = 26.85
        # Ensure calculation temperature matches the locked value
        self._temperature_c = float(self._wafer_temp_value)
        if hasattr(self, 'wafer_temp_info'):
            self.wafer_temp_info.setText(f"Wafer Temp : {self._wafer_temp_value:.2f} C")
        if hasattr(self, 'room_temp_info'):
            self.room_temp_info.setText(f"Room Temp : {self._home_room_temp_c:.1f} C")
        # No timer - updates happen in real-time via on_position_received()
        self._update_points_info()

    def set_manual_mode(self, enabled: bool):
        """Enable or disable manual measurement mode.

        When manual mode is enabled the page will not auto-complete when the
        configured number of points is reached; instead the user must press
        the End Measurement button to finish.
        """
        self._manual_mode = bool(enabled)
        self._update_points_info()

    def _update_points_info(self):
        if self._manual_mode:
            self.points_info.setText("Manual Mode")
            return

        label = "Point" if self._num_points == 1 else "Points"
        self.points_info.setText(f"{label} : {self.current_point_index}/{self._num_points}")

    def set_serial_reader(self, serial_reader):
        """Provide a SerialReader-like object used to send commands back to MCU."""
        self._serial_reader = serial_reader

    def _on_end_clicked(self):
        # Send END to serial (if available) and finish measurement
        try:
            if self._serial_reader is not None:
                # Use the reader's send_command API if available
                try:
                    self._serial_reader.send_command("END")
                except Exception:
                    # Fallback: try writing directly if raw serial provided
                    try:
                        self._serial_reader.write(("END\n").encode("utf-8"))
                        self._serial_reader.flush()
                    except Exception:
                        pass
        finally:
            self.loading_complete.emit()
