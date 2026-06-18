# measurement.py
import time
import math

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

Q_E = 1.602e-19

DEFAULT_TEMP_C = 0.0


def _read_voltage_current_from_serial(port: str = "COM5", baud_rate: int = 9600) -> tuple[float, float, str]:
    if not SERIAL_AVAILABLE:
        return 0.0, 0.0, "F"

    try:
        with serial.Serial(port, baud_rate, timeout=2) as ser:
            deadline = time.monotonic() + 30.0
            stream_started = False
            voltage_v = 0.0
            current_a = 0.0
            status = "F"

            while time.monotonic() < deadline:
                raw = ser.readline()
                if not raw:
                    continue

                text = raw.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue
                if "->" in text:
                    text = text.split("->", 1)[1].strip()
                if not text:
                    continue

                upper = text.upper()

                if upper == "STARTSTREAM":
                    stream_started = True
                    status = "STARTSTREAM"
                    deadline = time.monotonic() + 30.0
                    continue

                if upper == "STOPSTREAM":
                    status = "STOPSTREAM"
                    break

                if not stream_started:
                    continue

                if upper.startswith("V"):
                    try:
                        voltage_v = float(text[1:].strip())
                    except ValueError:
                        pass
                    deadline = time.monotonic() + 30.0
                    continue

                if upper.startswith("I"):
                    try:
                        current_a = float(text[1:].strip())
                    except ValueError:
                        pass
                    deadline = time.monotonic() + 30.0
                    continue

        return voltage_v, current_a, status
    except Exception:
        return 0.0, 0.0, "F"


def calculate_silicon_doping(
    voltage_v: float,
    current_a: float,
    thickness_cm: float,
    temp_c: float,
    carrier_type: str = "n",
) -> tuple[float, float]:
    """Return (doping_cm3, resistivity_ohm_cm) using an iterative mobility model."""
    if voltage_v <= 0 or current_a <= 0 or thickness_cm <= 0:
        return 0.0, 0.0
    
    t_kelvin = temp_c + 273.15
    s = 0.127

    # Measured resistivity from 4-point probe setup.
    if thickness_cm < (0.127/2):    
    # 1. Calculate measured resistivity from 4-point probe
        rho = (voltage_v / current_a) * thickness_cm * 4.532
        sigma = 1 / rho
    
    else:
        rho = (voltage_v / current_a) * math.pi * thickness_cm / math.log(math.sinh(thickness_cm / s) / math.sinh(thickness_cm / (2 * s)))
        sigma = 1 / rho

    if carrier_type.lower() == "n":
        mu_max, mu_min = 1417.0, 52.2
        n_ref, alpha = 9.68e16, 0.68
    else:
        mu_max, mu_min = 470.5, 44.9
        n_ref, alpha = 2.23e17, 0.719

    # Arora temperature correction.
    t_norm = t_kelvin / 300.0
    mu_max_t = mu_max * (t_norm ** -2.5)
    mu_min_t = mu_min * (t_norm ** -0.5)

    n_guess = 1e15
    for _ in range(30):
        mu = mu_min_t + (mu_max_t - mu_min_t) / (1.0 + (n_guess / n_ref) ** alpha)
        n_guess = sigma / (Q_E * mu)

    return n_guess, rho


def calculate_doping(
    thickness_mm: float,
    carrier_type: str,
    voltage_v: float,
    current_a: float,
    temp_c: float = DEFAULT_TEMP_C,
) -> dict:
    """Calculate electrical properties from voltage and current."""
    thickness_cm = thickness_mm / 10.0
    normalized_type = carrier_type.strip().upper()
    model_type = "p" if normalized_type.startswith("P") else "n"

    doping, resistivity = calculate_silicon_doping(
        voltage_v,
        current_a,
        thickness_cm,
        temp_c,
        model_type,
    )

    conductivity = 1.0 / resistivity if resistivity > 0 else 0.0
    rs = resistivity / thickness_cm if thickness_cm > 0 else 0.0

    return {
        "thickness_mm": thickness_mm,
        "type": normalized_type,
        "voltage_v": voltage_v,
        "current_a": current_a,
        "sheet_res_ohm_per_sq": rs,
        "resistivity_ohm_cm": resistivity,
        "conductivity_s_per_cm": conductivity,
        "doping_cm3": doping,
        "temperature_c": temp_c,
        "use_bulk_formula": False,
    }

def run_measurement(
    thickness_mm: float,
    carrier_type: str,
    temp_c: float = DEFAULT_TEMP_C,
    wafer_area_in2: float = None,
    diameter_inch: float = None,
    wafer_area_cm2: float = None,
    x_cm: float = None,
    y_cm: float = None,
    num_points: int = 1,
    mode: str = "",
) -> dict:
    """Calculate electrical properties from serial voltage/current readings.

    Accepts all parameters from HomePage signal for context, but primarily uses
    thickness_mm, carrier_type, and temp_c for calculations.
    """
    voltage_v, current_a, status = _read_voltage_current_from_serial()

    result = calculate_doping(thickness_mm, carrier_type, voltage_v, current_a, temp_c)
    result["serial_status"] = status

    return result
