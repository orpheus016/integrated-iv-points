from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data_storage import DataStorage
from pages.wafer_map_widget import ColorScaleBar, WaferMapWidget
from measurement import DEFAULT_TEMP_C, calculate_doping
from style import (
    ACCENT_COLOR,
    ACCENT_COLOR_DARK,
    BACKGROUND_COLOR,
    CARD_COLOR,
    TEXT_COLOR,
    apply_neumorphic_shadow,
)


class InfoCard(QFrame):
    def __init__(self, title, unit):
        super().__init__()
        self.setObjectName("infoCard")

        self.setMinimumHeight(110)
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

        # Use a single rich-text label so number and unit share the same baseline
        self.unit_text = unit
        self.val = QLabel()
        self.val.setProperty("role", "value")
        self.val.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.val.setTextFormat(Qt.RichText)
        # initial empty value with unit
        # Use same font-size for number and unit and force baseline alignment
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
        # render value + unit together with HTML to ensure baseline alignment
        try:
            unit_html = self.unit_text
        except Exception:
            unit_html = ""
        self.val.setText(
            f"<div style='text-align:center; line-height:1;'><span style='display:inline-block; font-size:36pt; line-height:1; color:{TEXT_COLOR}; font-weight:bold; vertical-align:baseline;'>{v}</span>"
                f"<span style='display:inline-block; font-size:25pt; line-height:1; color:{ACCENT_COLOR}; font-weight:bold; vertical-align:baseline; margin-left:6px; transform:translateY(-6px);'>&nbsp;{unit_html}</span></div>"
        )


class ResultPage(QWidget):
    back_to_home = Signal()

    def __init__(self):
        super().__init__()
        self.data_storage = DataStorage()

        self._current_result = None
        self._current_thickness = None
        self._current_wafer_area = None
        self._current_diameter = None
        self._current_wafer_area_cm2 = None
        self._current_temperature_c = DEFAULT_TEMP_C
        self._display_min_doping = WaferMapWidget.DOPING_MIN
        self._display_max_doping = WaferMapWidget.DOPING_MAX
        
        # Multi-point measurement support
        self._measurement_points = []  # List of (voltage_v, current_a, x_cm, y_cm, doping_cm3) tuples
        self._current_point_index = 0
        self._num_points = 1
        self._current_temperature_c = DEFAULT_TEMP_C

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
                border: none;
            }}
        """
        )
        apply_neumorphic_shadow(card, radius=24, blur_radius=32)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Measurement Results")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT_COLOR};")

        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        split = QHBoxLayout()
        split.setSpacing(24)

        right = self._build_right_panel()
        left = self._build_left_panel()

        split.addWidget(left, 1)
        split.addWidget(right, 1)
        layout.addLayout(split)

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
        """
        )
        apply_neumorphic_shadow(panel, radius=16, blur_radius=22)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        info_box = QFrame()
        info_box.setObjectName("infoBox")
        info_box.setFixedHeight(84)
        info_box.setStyleSheet(
            f"""
            QFrame#infoBox {{
                background-color: white;
                border: 2px solid {ACCENT_COLOR};
                border-radius: 12px;
            }}
            QFrame#infoBox QLabel {{
                border: none;
                background: transparent;
            }}
        """
        )
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(14, 4, 14, 4)

        self.info = QLabel("Thickness: -- μm | Type: - | Diameter: -- inch | Area: -- cm²")
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setStyleSheet(f"font-weight: bold; font-size: 15pt; color: {TEXT_COLOR};")
        info_layout.addWidget(self.info)
        layout.addWidget(info_box)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.volt = InfoCard("Voltage", "V")
        self.curr = InfoCard("Current", "mA")
        self.rs = InfoCard("Sheet Resistance", "Ω/sq")
        self.rho = InfoCard("Resistivity", "Ω·cm")
        self.sig = InfoCard("Conductivity", "S/cm")
        self.dop = InfoCard("Doping Concentration", "cm⁻³")

        grid.addWidget(self.volt, 0, 0)
        grid.addWidget(self.curr, 0, 1)
        grid.addWidget(self.rs, 1, 0)
        grid.addWidget(self.rho, 1, 1)
        grid.addWidget(self.sig, 2, 0)
        grid.addWidget(self.dop, 2, 1)

        layout.addLayout(grid)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        
        # Navigation arrows for multi-point measurements
        left_arrow_btn = QPushButton("◀")
        left_arrow_btn.setCursor(Qt.PointingHandCursor)
        left_arrow_btn.setFixedWidth(44)
        left_arrow_btn.setFixedHeight(44)
        left_arrow_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {ACCENT_COLOR};
                color: white;
                border-radius: 10px;
                border: none;
                font-weight: bold;
                padding: 4px 12px;
                font-size: 14pt;
            }}
            QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}
        """
        )
        left_arrow_btn.clicked.connect(self._go_to_previous_point)
        controls.addWidget(left_arrow_btn)
        
        self.point_info = QLabel("Point 1 / 1")
        self.point_info.setAlignment(Qt.AlignCenter)
        self.point_info.setStyleSheet(f"font-size: 11pt; font-weight: bold; color: {TEXT_COLOR};")
        self.point_info.setFixedWidth(94)
        controls.addWidget(self.point_info)
        
        right_arrow_btn = QPushButton("▶")
        right_arrow_btn.setCursor(Qt.PointingHandCursor)
        right_arrow_btn.setFixedWidth(44)
        right_arrow_btn.setFixedHeight(44)
        right_arrow_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {ACCENT_COLOR};
                color: white;
                border-radius: 10px;
                border: none;
                font-weight: bold;
                padding: 4px 12px;
                font-size: 14pt;
            }}
            QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}
        """
        )
        right_arrow_btn.clicked.connect(self._go_to_next_point)
        controls.addWidget(right_arrow_btn)

        controls.addStretch()

        clear_btn = QPushButton("Return")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setMinimumHeight(44)
        clear_btn.setMinimumWidth(132)
        clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {ACCENT_COLOR};
                color: white;
                border-radius: 14px;
                border: none;
                font-weight: bold;
                font-size: 12pt;
                padding: 6px 20px;
            }}
            QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}
        """
        )
        clear_btn.clicked.connect(self.back_to_home.emit)

        controls.addWidget(clear_btn)
        layout.addLayout(controls)

        return panel

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
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(8)
        title = QLabel("Wafer Mapping Contours")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.wafer_map = WaferMapWidget()
        layout.addWidget(self.wafer_map, 1)

        self.color_scale = ColorScaleBar()
        layout.addWidget(self.color_scale)

        self.scale_range_label = QLabel("No data yet")
        self.scale_range_label.setAlignment(Qt.AlignCenter)
        self.scale_range_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.scale_range_label.setFixedWidth(260)
        self.scale_range_label.setStyleSheet("font-size: 10pt; color: #756d61; font-weight: 600;")

        range_row = QHBoxLayout()
        range_row.setSpacing(10)

        range_label = QLabel("Display Range:")
        range_label.setStyleSheet("font-size: 11pt; color: #756d61; font-weight: bold;")
        range_row.addWidget(range_label)

        self.min_range_edit = QLineEdit(f"{self._display_min_doping:.1e}")
        self.min_range_edit.setFixedWidth(108)
        self.min_range_edit.setFixedHeight(34)
        self.min_range_edit.setAlignment(Qt.AlignCenter)
        self.min_range_edit.setStyleSheet(
            f"border: 1px solid {ACCENT_COLOR}; border-radius: 10px; background: white; color: {TEXT_COLOR}; padding: 5px; font-size: 10pt;"
        )
        range_row.addWidget(self.min_range_edit)

        dash = QLabel("to")
        dash.setStyleSheet("font-size: 11pt; color: #756d61; font-weight: 600;")
        range_row.addWidget(dash)

        self.max_range_edit = QLineEdit(f"{self._display_max_doping:.1e}")
        self.max_range_edit.setFixedWidth(108)
        self.max_range_edit.setFixedHeight(34)
        self.max_range_edit.setAlignment(Qt.AlignCenter)
        self.max_range_edit.setStyleSheet(
            f"border: 1px solid {ACCENT_COLOR}; border-radius: 10px; background: white; color: {TEXT_COLOR}; padding: 5px; font-size: 10pt;"
        )
        range_row.addWidget(self.max_range_edit)

        apply_btn = QPushButton("Apply")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setFixedHeight(34)
        apply_btn.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_COLOR}; color: white; border: none; border-radius: 12px; padding: 4px 14px; font-size: 10pt; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}"
        )
        apply_btn.clicked.connect(self._apply_display_range)
        range_row.addWidget(apply_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setFixedHeight(34)
        reset_btn.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_COLOR}; color: white; border: none; border-radius: 12px; padding: 4px 14px; font-size: 10pt; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {ACCENT_COLOR_DARK}; }}"
        )
        reset_btn.clicked.connect(self._reset_display_range)
        range_row.addWidget(reset_btn)

        range_row.addStretch()
        range_row.addWidget(self.scale_range_label)
        layout.addLayout(range_row)

        self.last_point = QLabel("Latest point: X 0.00 cm | Y 0.00 cm")
        self.last_point.setAlignment(Qt.AlignCenter)
        self.last_point.setMinimumHeight(42)
        self.last_point.setStyleSheet(
            f"border: 2px solid {ACCENT_COLOR}; border-radius: 14px; background: white; font-weight: bold; font-size: 11pt; padding: 8px 10px;"
        )
        layout.addWidget(self.last_point)

        return panel

    def _apply_display_range(self):
        try:
            lo = float(self.min_range_edit.text())
            hi = float(self.max_range_edit.text())
        except ValueError:
            self.scale_range_label.setText("Invalid range input")
            return

        if lo <= 0 or hi <= 0 or lo >= hi:
            self.scale_range_label.setText("Range must satisfy 0 < min < max")
            return

        self._display_min_doping = lo
        self._display_max_doping = hi
        self.wafer_map.set_display_range(lo, hi)
        self.color_scale.set_display_range(lo, hi)
        self._set_scale_range_label(f"Display: {lo:.2e} - {hi:.2e} cm⁻³")

    def _reset_display_range(self):
        self._display_min_doping = WaferMapWidget.DOPING_MIN
        self._display_max_doping = WaferMapWidget.DOPING_MAX
        self.min_range_edit.setText(f"{self._display_min_doping:.1e}")
        self.max_range_edit.setText(f"{self._display_max_doping:.1e}")
        self.wafer_map.reset_display_range()
        self.color_scale.reset_display_range()
        self._set_scale_range_label("No data yet")

    def reset_results(self):
        """Reset result widgets so each new run starts from a clean state."""
        self._current_result = None
        self._measurement_points = []
        self._current_point_index = 0
        self._num_points = 1

        self.info.setText("Thickness: -- μm | Type: - | Diameter: -- inch | Area: -- cm²")
        self.point_info.setText("Point 1 / 1")
        self.last_point.setText("Latest point: X 0.00 cm | Y 0.00 cm")

        self.volt.set_value("--")
        self.curr.set_value("--")
        self.rs.set_value("--")
        self.rho.set_value("--")
        self.sig.set_value("--")
        self.dop.set_value("--")

        self.wafer_map.clear_contours()
        self.wafer_map.set_probe_point(0.0, 0.0)
        self.color_scale.clear_range()
        self._set_scale_range_label("No data yet")

    def update_results(
        self,
        r,
        thickness_mm=None,
        wafer_area_in=None,
        diameter_inch=None,
        wafer_area_cm2=None,
        x_cm=0.0,
        y_cm=0.0,
        measurement_points=None,
        num_points=1,
        temperature_c=DEFAULT_TEMP_C,
    ):
        self._current_result = r
        self._current_thickness = thickness_mm
        self._current_wafer_area = wafer_area_in
        self._current_diameter = diameter_inch
        self._current_wafer_area_cm2 = wafer_area_cm2
        self._current_temperature_c = float(temperature_c)
        self._measurement_points = measurement_points if measurement_points else []
        self._num_points = num_points
        self._current_point_index = len(self._measurement_points) - 1 if self._measurement_points else 0
        
        # Update point info display
        if hasattr(self, 'point_info'):
            self.point_info.setText(f"Point 1 / {self._num_points}")

        if r.get("use_bulk_formula", False):
            self.rs.title.setText("Bulk Resistance")
        else:
            self.rs.title.setText("Sheet Resistance")

        thickness_um = r["thickness_mm"] * 1000
        self.info.setText(
            f"Thickness: {thickness_um:.0f} \u03bcm | Type: {r['type']}-type | Diameter: {diameter_inch}\" | Area: {wafer_area_cm2:.2f} cm\u00b2"
        )

        self.volt.set_value(f"{r['voltage_v']:.2f}")
        current_ma = r["current_a"] * 1000
        self.curr.set_value(f"{current_ma:.2f}")
        self.rs.set_value(f"{r['sheet_res_ohm_per_sq']:.2f}")
        self.rho.set_value(f"{r['resistivity_ohm_cm']:.2f}")
        self.sig.set_value(f"{r['conductivity_s_per_cm']:.2f}")
        self.dop.set_value(f"{r['doping_cm3']:.2e}")

        if wafer_area_cm2 is not None:
            self.wafer_map.set_wafer_area_cm2(wafer_area_cm2)
        elif diameter_inch is not None:
            self.wafer_map.set_wafer_diameter_inch(diameter_inch)

        # Keep wafer silhouette in sync with selected doping orientation type.
        result_type = r.get("type")
        if isinstance(result_type, str):
            self.wafer_map.set_doping_type(result_type)

        if self._measurement_points:
            self._update_display_for_current_point()
        else:
            self.wafer_map.set_probe_point(x_cm, y_cm)
            self.wafer_map.add_measurement_contour(x_cm, y_cm, r["doping_cm3"])
            self.last_point.setText(f"Latest point: X {x_cm:.2f} cm | Y {y_cm:.2f} cm")

        # Update color scale bar range.
        mn = self.wafer_map._min_doping
        mx = self.wafer_map._max_doping
        
        if mn is not None and mx is not None:
            self.color_scale.update()
            self._set_scale_range_label(
                f"Data: {mn:.2e} - {mx:.2e} | Display: {self._display_min_doping:.2e} - {self._display_max_doping:.2e} cm⁻³"
            )
        
        if thickness_mm is not None and wafer_area_in is not None:
            wafer_area_cm2_for_storage = wafer_area_in * 6.4516

            # Persist every measured point so historical data matches 1/5/9 point runs.
            if self._measurement_points:
                carrier_type = r.get("type", "N (100)")
                for voltage_v, current_a, _, _, _ in self._measurement_points:
                    point_result = calculate_doping(
                        thickness_mm,
                        carrier_type,
                        voltage_v,
                        current_a,
                        self._current_temperature_c,
                    )
                    self.data_storage.save_measurement(
                        thickness_mm,
                        wafer_area_cm2_for_storage,
                        point_result,
                    )
            else:
                self.data_storage.save_measurement(thickness_mm, wafer_area_cm2_for_storage, r)

    def _go_to_previous_point(self):
        """Navigate to the previous measurement point."""
        if self._measurement_points and self._current_point_index > 0:
            self._current_point_index -= 1
            self._update_display_for_current_point()

    def _go_to_next_point(self):
        """Navigate to the next measurement point."""
        if self._measurement_points and self._current_point_index < len(self._measurement_points) - 1:
            self._current_point_index += 1
            self._update_display_for_current_point()

    def _update_display_for_current_point(self):
        """Update the display to show the current measurement point."""
        if not self._measurement_points or self._current_point_index >= len(self._measurement_points):
            return
        
        voltage_v, current_a, x_cm, y_cm, doping_cm3 = self._measurement_points[self._current_point_index]
        
        # Update point info
        self.point_info.setText(f"Point {self._current_point_index + 1} / {len(self._measurement_points)}")
        
        # Update the display with current point data
        self.volt.set_value(f"{voltage_v:.2f}")
        current_ma = current_a * 1000
        self.curr.set_value(f"{current_ma:.2f}")
        
        # Calculate electrical properties for this point
        if self._current_thickness is not None:
            result = calculate_doping(
                self._current_thickness,
                self._current_result.get("type", "N (100)"),
                voltage_v,
                current_a,
                self._current_temperature_c,
            )
            self.rs.set_value(f"{result['sheet_res_ohm_per_sq']:.2f}")
            self.rho.set_value(f"{result['resistivity_ohm_cm']:.2f}")
            self.sig.set_value(f"{result['conductivity_s_per_cm']:.2f}")
            self.dop.set_value(f"{result['doping_cm3']:.2e}")
        
        # Rebuild contours cumulatively: point N shows first N points.
        self.wafer_map.clear_contours()
        for i in range(self._current_point_index + 1):
            _, _, cx, cy, cdoping = self._measurement_points[i]
            self.wafer_map.add_measurement_contour(cx, cy, cdoping)

        # Update wafer map position
        self.wafer_map.set_probe_point(x_cm, y_cm)
        self.last_point.setText(f"Point {self._current_point_index + 1}: X {x_cm:.2f} cm | Y {y_cm:.2f} cm")

        mn = self.wafer_map._min_doping
        mx = self.wafer_map._max_doping
        
        if mn is not None and mx is not None:
            self.color_scale.update()
            self._set_scale_range_label(
                f"Data: {mn:.2e} - {mx:.2e} | Display: {self._display_min_doping:.2e} - {self._display_max_doping:.2e} cm⁻³"
            )

    def _set_scale_range_label(self, text):
        fm = QFontMetrics(self.scale_range_label.font())
        self.scale_range_label.setText(fm.elidedText(text, Qt.ElideRight, self.scale_range_label.width()))
