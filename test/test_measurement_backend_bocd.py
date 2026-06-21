import pytest
from unittest.mock import patch, MagicMock

import measurement
from software.config.config import SimulationConfig

if not measurement.SERIAL_AVAILABLE:
    pytest.skip("pyserial not installed", allow_module_level=True)

@patch("measurement.serial.Serial")
@patch("software.scripts.integrate.time.perf_counter")
def test_measurement_uses_bocd_voltage(mock_perf, mock_serial_cls):
    """
    Test that measurement.py's _read_voltage_current_from_serial uses the 
    FrontendBridge (BOCD) to filter noise rather than just returning the 
    last read value from the serial line.
    """
    # Mock time.perf_counter to advance by 0.1s on each call
    time_vals = [0.0]
    def advance_time():
        time_vals[0] += 0.1
        return time_vals[0]
    mock_perf.side_effect = advance_time
    
    mock_serial = MagicMock()
    mock_serial_cls.return_value.__enter__.return_value = mock_serial
    
    GAIN = SimulationConfig.gain
    
    # Create a sequence of serial lines simulating a noisy measurement
    # that ends with a massive outlier. 
    lines = [b"STARTSTREAM\n"]
    
    # 100 samples stabilizing around 2.0V (raw voltage sent by Arduino)
    # The _read_voltage_current_from_serial expects V to be unscaled.
    for _ in range(100):
        lines.append(f"V {2.0 * GAIN}\n".encode("utf-8"))
        lines.append(b"I 0.01\n")
        
    # Last sample is wildly off (5.0V). If the code just takes the last
    # value like it used to, it will return 5.0. If it uses BOCD, it 
    # will return the stable ~2.0V.
    lines.append(f"V {5.0 * GAIN}\n".encode("utf-8"))
    lines.append(b"I 0.01\n")
    
    lines.append(b"STOPSTREAM\n")
    lines.append(b"") # EOF to end readline loop if it doesn't break
    
    mock_serial.readline.side_effect = lines
    
    voltage_v, current_a, status = measurement._read_voltage_current_from_serial(port="COM1")
    
    assert status == "STOPSTREAM"
    
    # Ensure it didn't just take the 5.0V outlier
    assert voltage_v != 5.0, "Failed: measurement used the last raw serial value (5.0V) instead of BOCD snapshot!"
    
    # Ensure it's close to the stabilized 2.0V
    assert abs(voltage_v - 2.0) < 0.1, f"Expected BOCD voltage around 2.0V, but got {voltage_v:.3f}V"

    # Also test the public run_measurement API to ensure the fallback calculation uses this correct value
    mock_serial.readline.side_effect = lines
    result = measurement.run_measurement(thickness_mm=1.0, carrier_type="N (100)", temp_c=25.0)
    
    assert result["serial_status"] == "STOPSTREAM"
    assert abs(result["voltage_v"] - 2.0) < 0.1, f"Expected run_measurement to use BOCD voltage, got {result['voltage_v']:.3f}V"
