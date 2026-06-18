# main_window.py
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from pages.home_page import HomePage
from pages.loading_page import LoadingPage
from pages.result_page import ResultPage
from pages.historical_data_page import HistoricalDataPage
from measurement import DEFAULT_TEMP_C, run_measurement, calculate_doping


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Four Point Probe Interface")
        self.setMinimumSize(1000, 700)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home = HomePage()
        self.loading = LoadingPage()
        self.result = ResultPage()
        self.historical = HistoricalDataPage()

        self.stack.addWidget(self.home)
        self.stack.addWidget(self.loading)
        self.stack.addWidget(self.result)
        self.stack.addWidget(self.historical)

        self.home.start_measurement.connect(self._show_loading)
        self.loading.loading_complete.connect(self._loading_finished)
        self.result.back_to_home.connect(self._go_home)
        self.home.view_historical_data.connect(self._show_historical)
        self.historical.back_to_home.connect(self._go_home)

        # Store measurement parameters
        self._thickness = None
        self._carrier = None
        self._wafer_area = None
        self._diameter = None
        self._wafer_area_cm2 = None
        self._x_cm = 0.0
        self._y_cm = 0.0
        self._num_points = 1
        self._measurement_points = []
        self._temperature_c = DEFAULT_TEMP_C

    def _show_loading(self, thickness, carrier, wafer_area, diameter, wafer_area_cm2, x_cm, y_cm, num_points=1, temperature_c=DEFAULT_TEMP_C, mode=""):
        """Store measurement parameters and show loading screen."""
        self._thickness = thickness
        self._carrier = carrier
        self._wafer_area = wafer_area
        self._diameter = diameter
        self._wafer_area_cm2 = wafer_area_cm2
        self._x_cm = x_cm
        self._y_cm = y_cm
        self._num_points = num_points
        self._temperature_c = float(temperature_c)
        self._measurement_points = []

        self.result.reset_results()
        
        # Configure loading page
        self.loading.set_num_points(num_points)
        self.loading.set_wafer_params(diameter, wafer_area_cm2, carrier, thickness, carrier, self._temperature_c)
        
        # Connect home page serial reader to loading page for real-time measurement collection
        if hasattr(self.home, '_serial_reader') and self.home._serial_reader is not None:
            try:
                self.home._serial_reader.position_received.disconnect(self.loading.on_position_received)
            except:
                pass
            self.home._serial_reader.position_received.connect(self.loading.on_position_received)
            try:
                self.home._serial_reader.temperature_received.disconnect(self.loading.on_temperature_received)
            except:
                pass
            self.home._serial_reader.temperature_received.connect(self.loading.on_temperature_received)
            try:
                self.home._serial_reader.confirm_received.disconnect(self.loading.on_confirm_received)
            except:
                pass
            self.home._serial_reader.confirm_received.connect(self.loading.on_confirm_received)
            try:
                self.home._serial_reader.measurement_started.disconnect(self.loading.on_measurement_started)
            except:
                pass
            self.home._serial_reader.measurement_started.connect(self.loading.on_measurement_started)
            try:
                self.home._serial_reader.voltage_received.disconnect(self.loading.on_voltage_received)
            except:
                pass
            self.home._serial_reader.voltage_received.connect(self.loading.on_voltage_received)
            try:
                self.home._serial_reader.current_received.disconnect(self.loading.on_current_received)
            except:
                pass
            self.home._serial_reader.current_received.connect(self.loading.on_current_received)
            try:
                self.home._serial_reader.measurement_stopped.disconnect(self.loading.on_measurement_stopped)
            except:
                pass
            self.home._serial_reader.measurement_stopped.connect(self.loading.on_measurement_stopped)
            # Also connect MLX sensor readings (wafer measurement temperature) if available
            try:
                try:
                    self.home._serial_reader.mlx_temperature_received.disconnect(self.loading.on_temperature_received)
                except:
                    pass
                # MLX readings should be handled by loading.on_mlx_temperature_received
                try:
                    self.home._serial_reader.mlx_temperature_received.connect(self.loading.on_mlx_temperature_received)
                except Exception:
                    # Fallback: connect to generic handler if specific handler missing
                    self.home._serial_reader.mlx_temperature_received.connect(self.loading.on_temperature_received)
            except Exception:
                # Older SerialReader instances may not have MLX signal; ignore
                pass
            # Pass serial reader and manual-mode flag to loading page
            try:
                self.loading.set_serial_reader(self.home._serial_reader)
            except Exception:
                pass
            try:
                self.loading.set_manual_mode(mode == "Manual Measurement")
            except Exception:
                pass
        
        self.stack.setCurrentWidget(self.loading)
        self.loading.start_loading(num_points)

    def _loading_finished(self):
        """Transition to results page after measurement is complete."""
        # Disconnect the serial reader from loading page
        if hasattr(self.home, '_serial_reader') and self.home._serial_reader is not None:
            try:
                self.home._serial_reader.position_received.disconnect(self.loading.on_position_received)
            except:
                pass
            try:
                self.home._serial_reader.temperature_received.disconnect(self.loading.on_temperature_received)
            except:
                pass
            try:
                self.home._serial_reader.confirm_received.disconnect(self.loading.on_confirm_received)
            except:
                pass
            try:
                self.home._serial_reader.measurement_started.disconnect(self.loading.on_measurement_started)
            except:
                pass
            try:
                self.home._serial_reader.voltage_received.disconnect(self.loading.on_voltage_received)
            except:
                pass
            try:
                self.home._serial_reader.current_received.disconnect(self.loading.on_current_received)
            except:
                pass
            try:
                self.home._serial_reader.measurement_stopped.disconnect(self.loading.on_measurement_stopped)
            except:
                pass

        measured_temp_c = self.loading.get_temperature_c()
        
        # Get the first measurement as the main result
        if self.loading.measurement_points:
            voltage_v, current_a, x_cm, y_cm, doping_cm3 = self.loading.measurement_points[0]
            # Create a result dict similar to run_measurement output
            result = calculate_doping(self._thickness, self._carrier, voltage_v, current_a, measured_temp_c)
        else:
            # Fallback result if no measurements collected
            result = run_measurement(self._thickness, self._carrier, measured_temp_c)
        
        # Get measurement points from loading page
        measurement_points = self.loading.measurement_points
        
        self.result.update_results(
            result,
            self._thickness,
            self._wafer_area,
            self._diameter,
            self._wafer_area_cm2,
            self._x_cm,
            self._y_cm,
            measurement_points,
            self._num_points,
            measured_temp_c,
        )
        self.stack.setCurrentWidget(self.result)

    def _go_home(self):
        self.stack.setCurrentWidget(self.home)

    def _show_historical(self):
        """Navigate to historical data page."""
        self.stack.setCurrentWidget(self.historical)

