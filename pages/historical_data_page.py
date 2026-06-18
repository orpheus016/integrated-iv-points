# pages/historical_data_page.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog
)

from style import (
    BACKGROUND_COLOR, CARD_COLOR, TEXT_COLOR,
    ACCENT_COLOR, ACCENT_COLOR_DARK, apply_neumorphic_shadow
)
from data_storage import DataStorage


class HistoricalDataPage(QWidget):
    back_to_home = Signal()

    def __init__(self):
        super().__init__()
        self.data_storage = DataStorage()
        from pathlib import Path
        self.backup_dir = Path.home() / "Documents" / "Data" / "Backup"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.backup_file = self.backup_dir / "FourPointMeasurement_Backup.csv"
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BACKGROUND_COLOR};")

        main = QVBoxLayout(self)
        main.setContentsMargins(40, 30, 40, 30)
        main.setSpacing(0)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_COLOR};
                border-radius: 34px;
                border: none;
            }}
        """)
        apply_neumorphic_shadow(card, radius=24, blur_radius=32)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(18)

        # Title row with Home button
        header = QHBoxLayout()
        title = QLabel("Historical Data")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT_COLOR}; letter-spacing: 1px;")

        home = QPushButton("← Home")
        home.setFixedHeight(42)
        home.setFixedWidth(100)
        home.setCursor(Qt.PointingHandCursor)
        home.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_COLOR};
                border: none;
                color: {TEXT_COLOR};
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 12pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #fffaf3;
            }}
            QPushButton:pressed {{
                background-color: #fff5e6;
            }}
        """)
        home.clicked.connect(self.back_to_home.emit)

        export_btn = QPushButton("Export CSV")
        export_btn.setFixedHeight(42)
        export_btn.setFixedWidth(120)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #5cb85c;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 12pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #4cae4c;
            }}
            QPushButton:pressed {{
                background-color: #398439;
            }}
        """)
        export_btn.clicked.connect(self._export_to_csv)

        clear_btn = QPushButton("Clear Data")
        clear_btn.setFixedHeight(42)
        clear_btn.setFixedWidth(120)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #d9534f;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 12pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #c9302c;
            }}
            QPushButton:pressed {{
                background-color: #ac2925;
            }}
        """)
        clear_btn.clicked.connect(self._clear_data)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(export_btn)
        header.addWidget(clear_btn)
        header.addWidget(home)
        layout.addLayout(header)

        # =====================================================
        # Table view only
        # =====================================================
        table_page = QFrame()
        table_page.setMinimumHeight(440)
        table_page.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 20px;
                border: 2px solid {ACCENT_COLOR};
            }}
        """)
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(12, 12, 12, 12)
        
        # Create data table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Thickness\n(mm)", "Wafer Area\n(cm²)", "Type",
            "Voltage\n(V)", "Current\n(A)", "Sheet Res\n(Ω/sq)", 
            "Resistivity\n(Ω·cm)", "Conductivity\n(S/cm)", "Doping\n(cm⁻³)"
        ])
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                alternate-background-color: #f9f7f4;
                gridline-color: #e0dbd4;
                border: none;
                color: black;
            }}
            QHeaderView::section {{
                background-color: {ACCENT_COLOR};
                color: white;
                padding: 6px;
                border: none;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 6px;
                color: black;
            }}
        """)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)
        layout.addWidget(table_page, 1)

        note = QLabel("*Please close any CSV measurement files before making any changes")
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet("color: #6b665f; font-style: italic; font-size: 10pt;")
        layout.addWidget(note)

        main.addWidget(card)

    def showEvent(self, event):
        """Load/reload data when the page becomes visible."""
        super().showEvent(event)
        # Always reload data when showing to ensure it's up to date
        self._load_data()
    
    def _load_data(self):
        """Load measurement data from Excel and populate the table."""
        measurements = self.data_storage.load_all_measurements()
        
        self.table.setRowCount(len(measurements))
        
        for row_idx, measurement in enumerate(measurements):
            self._add_row_to_table(row_idx, measurement)
    
    def _add_row_to_table(self, row_idx, measurement):
        """Add a single measurement row to the table."""
        columns = [
            "Timestamp",
            "Thickness (mm)",
            "Wafer Area (cm²)",
            "Type",
            "Voltage (V)",
            "Current (A)",
            "Sheet Resistance (Ω/sq)",
            "Resistivity (Ω·cm)",
            "Conductivity (S/cm)",
            "Doping Concentration (cm⁻³)"
        ]
        
        for col_idx, col_name in enumerate(columns):
            value = measurement.get(col_name)
            
            if value is None:
                text = "--"
            elif col_name == "Doping Concentration (cm⁻³)":
                try:
                    text = f"{float(value):.3e}"
                except (TypeError, ValueError):
                    text = str(value)
            elif isinstance(value, (int, float)):
                # Format floats appropriately
                if col_name in ["Voltage (V)", "Current (A)"]:
                    text = f"{value:.4g}"
                else:
                    text = f"{value:.4g}"
            else:
                text = str(value)
            
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, col_idx, item)
    
    def _clear_data(self):
        """Clear all historical data after confirmation."""
        reply = QMessageBox.question(
            self,
            "Clear Data",
            "Are you sure you want to delete all historical data? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                measurements = self.data_storage.load_all_measurements()

                # Write backup before clearing (overwrite single backup file)
                if measurements:
                    self._write_csv(measurements, self.backup_file)

                import os
                data_file = self.data_storage.get_file_path()
                if os.path.exists(data_file):
                    os.remove(data_file)
                    self.data_storage._ensure_workbook()
                    self._load_data()
                    QMessageBox.information(self, "Success", "All historical data has been cleared. A backup CSV was saved to the Backup folder.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear data: {e}")

    def _write_csv(self, measurements, csv_file):
        """Write measurements list to a CSV file."""
        import csv

        columns = [
            "Timestamp",
            "Thickness (mm)",
            "Wafer Area (inch)",
            "Type",
            "Voltage (V)",
            "Current (A)",
            "Sheet Resistance (Ohm/sq)",
            "Resistivity (Ohm-cm)",
            "Conductivity (S/cm)",
            "Doping Concentration (cm-3)"
        ]

        column_mapping = {
            "Timestamp": "Timestamp",
            "Thickness (mm)": "Thickness (mm)",
            "Wafer Area (inch)": "Wafer Area (inch)",
            "Type": "Type",
            "Voltage (V)": "Voltage (V)",
            "Current (A)": "Current (A)",
            "Sheet Resistance (Ω/sq)": "Sheet Resistance (Ohm/sq)",
            "Resistivity (Ω·cm)": "Resistivity (Ohm-cm)",
            "Conductivity (S/cm)": "Conductivity (S/cm)",
            "Doping Concentration (cm⁻³)": "Doping Concentration (cm-3)"
        }

        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for measurement in measurements:
                row = []
                for orig_col in column_mapping:
                    row.append(measurement.get(orig_col, ""))
                writer.writerow(row)
    
    def _export_to_csv(self):
        """Export table data to CSV file."""
        try:
            from pathlib import Path
            
            # Generate filename with timestamp and ask user where to save (defaulting to desired folder)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_dir = Path.home() / "Documents" / "Data"
            default_dir.mkdir(parents=True, exist_ok=True)
            default_name = f"FourPointMeasurement_{timestamp}.csv"
            suggested_path = str(default_dir / default_name)

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save CSV",
                suggested_path,
                "CSV Files (*.csv);;All Files (*.*)"
            )

            # User cancelled
            if not file_path:
                return

            csv_file = Path(file_path)
            if csv_file.suffix.lower() != ".csv":
                csv_file = csv_file.with_suffix(".csv")

            measurements = self.data_storage.load_all_measurements()

            if not measurements:
                QMessageBox.warning(self, "No Data", "There is no data to export.")
                return
            # Write chosen CSV
            self._write_csv(measurements, csv_file)

            # Also write/overwrite backup CSV in backup folder
            self._write_csv(measurements, self.backup_file)
            
            QMessageBox.information(
                self,
                "Export Successful",
                f"Data exported to:\n{csv_file}"
            )
            # Reload data to refresh the table and graphs
            self._load_data()
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {e}")
