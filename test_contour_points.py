import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pages.result_page import ResultPage


def _fake_result(doping_cm3: float) -> dict:
    return {
        "thickness_mm": 0.5,
        "type": "P (110)",
        "voltage_v": 0.8,
        "current_a": 0.02,
        "sheet_res_ohm_per_sq": 120.0,
        "resistivity_ohm_cm": 6.0,
        "conductivity_s_per_cm": 1.0 / 6.0,
        "doping_cm3": doping_cm3,
        "use_bulk_formula": False,
    }


def main():
    app = QApplication(sys.argv)

    page = ResultPage()
    page.setWindowTitle("Contour Map Test - Auto Points")
    page.resize(1200, 800)
    page.show()

    points = [
        #(0.0, 0.0, 1e18),
        #(0.0, 3.0, 5e18),
        #(3.0, 0.0, 1e18),
        #(0.0, -3.0, 4e19),
        #(-3.0, 0.0, 2.8e19),
        #(-5.0, 0.0, 1e18),
    ]

    def inject_points():
        thickness_mm = 0.3
        wafer_area_cm2 = 20.27
        diameter_inch = 2
        wafer_area_in2 = wafer_area_cm2 / 6.4516

        for x_cm, y_cm, doping in points:
            page.update_results(
                _fake_result(doping),
                thickness_mm=thickness_mm,
                wafer_area_in=wafer_area_in2,
                diameter_inch=diameter_inch,
                wafer_area_cm2=wafer_area_cm2,
                x_cm=x_cm,
                y_cm=y_cm,
            )

    QTimer.singleShot(200, inject_points)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
