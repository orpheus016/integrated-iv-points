import pytest
from unittest.mock import MagicMock
from pages.loading_page import LoadingPage
from software.config.config import SimulationConfig

@pytest.fixture
def loading_page():
    # We patch widgets if needed, but PySide6 can sometimes run headless
    # Instead, let's mock QApplication if not created, but standard trick is pytest-qt
    # Or just mock the components we care about
    pass

def test_loading_page_gain_live_display(monkeypatch):
    """Verify that live voltage is divided by gain before displaying, using the bridge filtered output."""
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    monkeypatch.setattr("pages.loading_page.SimulationConfig.gain", 1.82)
    
    page = LoadingPage()
    
    # Mock the volt display to check what it is set to
    page.volt = MagicMock()
    page.curr = MagicMock()
    
    # Ensure bridge is mock
    if page._bridge is not None:
        page._bridge.on_sample = MagicMock(return_value=(1.82, None))

    # Test on_voltage_received (this will just set _stream_voltage_v)
    page.on_voltage_received(1.82)
    
    # Test on_current_received which triggers the bridge
    page.on_current_received(0.010)
    
    # It should divide filtered value (1.82) by 1.82 to get 1.000
    page.volt.set_value.assert_called_with("1.000")
    page.curr.set_value.assert_called_with("10.000")

def test_loading_page_gain_live_display_with_snapshot(monkeypatch):
    """Verify that live display prioritizes snapshot values if available."""
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    monkeypatch.setattr("pages.loading_page.SimulationConfig.gain", 1.82)
    
    page = LoadingPage()
    
    page.volt = MagicMock()
    page.curr = MagicMock()
    
    from software.utils.types import Snapshot
    snap = Snapshot(timestamp=1.0, voltage=3.64, current_mA=20.0, resistance=10.0, std_dev=0.1)
    
    # Mock bridge returning a snapshot
    if page._bridge is not None:
        page._bridge.on_sample = MagicMock(return_value=(1.82, snap))

    page.on_voltage_received(1.82)
    page.on_current_received(0.010)
    
    # It should use snapshot.voltage (3.64) divided by gain (1.82) -> 2.000
    page.volt.set_value.assert_called_with("2.000")
    # It should use snapshot.current_mA directly
    page.curr.set_value.assert_called_with("20.000")

def test_loading_page_gain_final_result(monkeypatch):
    """Verify that the final snapshot voltage is divided by gain."""
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    monkeypatch.setattr("pages.loading_page.SimulationConfig.gain", 1.82)
    
    page = LoadingPage()
    
    # Mock add_measurement_point to see what gets passed
    page.add_measurement_point = MagicMock()
    
    # Simulate stopping the measurement
    page._measurement_completed = False
    page._stream_voltage_v = 1.82
    page._stream_current_a = 0.010 # 10mA
    
    # Make sure bridge returns None so it uses fallback values
    if page._bridge is not None:
        page._bridge.on_stream_stop = MagicMock(return_value=None)

    page.on_measurement_stopped()
    
    # add_measurement_point should receive voltage_v = 1.0 (1.82 / 1.82)
    # The signature is: add_measurement_point(x_cm, y_cm, voltage_v, current_a, doping_cm3)
    page.add_measurement_point.assert_called_once()
    args, kwargs = page.add_measurement_point.call_args
    assert args[2] == 1.0  # voltage_v is the 3rd argument (index 2)
