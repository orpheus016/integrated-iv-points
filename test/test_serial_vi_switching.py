"""test_serial_vi_switching.py — Integration test for frontend serial VI path.

This test verifies that injecting a constant-voltage stream via the real
``vi_prefixed`` ASCII line format (``V<val>\\n`` / ``I<val>\\n``) through the
``SerialReader`` signal chain correctly drives the ``FrontendBridge`` backbone
to converge and triggers ``SerialCommander`` current-stage switching.

No hardware is opened.  A ``MockSerial`` replaces pyserial and the
``SerialReader`` QThread is bypassed entirely — we call the ``LoadingPage``
slot methods directly to simulate the signal chain:

    STARTSTREAM  → loading_page.on_measurement_started()  → bridge.on_stream_start()
    V<val>       → loading_page.on_voltage_received()
    I<val>       → loading_page.on_current_received()     → bridge.on_sample()
    STOPSTREAM   → loading_page.on_measurement_stopped()  → bridge.on_stream_stop()

Four parametrized scenarios are tested — one per hardware current stage:

    Stage 0 →  4 mA  (constant  1.000 V — well above raise_low=0.30 V, no raise)
    Stage 1 →  8 mA  (constant  0.280 V — ≥ raise_low[0]=0.30 V? No: triggers raise,
                                          but ≥ raise_low[1]=0.25 V so stays at 8 mA)
    Stage 2 → 12 mA  (constant  0.200 V — triggers raise to 12 mA, stays because ≥
                                          raise_low[2]=0.15 V)
    Stage 3 → 20 mA  (constant  0.010 V — below all thresholds, raises to stage 3)

The current-switch policy from ``config.py`` (lines 64-74) governs transitions:
    current_mA_by_stage = (4.0, 8.0, 12.0, 20.0)
    raise_low_v_by_stage = (0.30, 0.25, 0.15, 0.0)
"""

from __future__ import annotations

import time
import pytest
from typing import List, Optional, Tuple

from software.config.config import (
    build_arg_parser,
    build_simulation_config,
    build_serial_config,
    CurrentSwitchConfig,
)
from software.scripts.integrate import FrontendBridge
from software.command.serial_commander import SerialCommander


# ---------------------------------------------------------------------------
# Constants derived from config — change config.py; these follow automatically
# ---------------------------------------------------------------------------

_DEFAULTS = CurrentSwitchConfig()
_STAGES = _DEFAULTS.current_mA_by_stage  # (4.0, 8.0, 12.0, 20.0)
_RAISE_LOW = _DEFAULTS.raise_low_v_by_stage  # (0.30, 0.25, 0.15, 0.0)

# Choose a constant voltage for each test scenario.
# The voltage must be *above* the raise_low threshold of its own stage so the
# commander never raises further, but *below* the raise_low threshold of the
# previous stage so a raise from stage N-1 does fire.
#
#   Stage 0  (4 mA): V=1.000  — far above raise_low[0]=0.30  → no raise ever fired
#   Stage 1  (8 mA): V=0.280  — < raise_low[0]=0.30 → triggers 0→1;
#                               ≥ raise_low[1]=0.25 → no further raise
#   Stage 2 (12 mA): V=0.200  — < raise_low[0]=0.30 → 0→1; < raise_low[1]=0.25 → 1→2;
#                               ≥ raise_low[2]=0.15 → no further raise
#   Stage 3 (20 mA): V=0.010  — below all thresholds → raises all the way to stage 3
_TEST_CASES: List[Tuple[float, int, float]] = [
    # (constant_voltage_v, expected_final_stage, expected_current_mA)
    (1.000, 0, _STAGES[0]),
    (0.280, 1, _STAGES[1]),
    (0.200, 2, _STAGES[2]),
    (0.010, 3, _STAGES[3]),
]

# Maximum samples to inject before declaring convergence failure.
# At 50 Hz, 2000 samples == 40 s — generous but bounded.
_MAX_SAMPLES = 2000

# Snapshot convergence tolerance
_SNAPSHOT_V_TOL = 0.01   # V
_SNAPSHOT_I_TOL = 0.5    # mA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockSerial:
    """Minimal serial stub that records every write() call.

    Used in place of ``pyserial.Serial`` so ``SerialCommander`` can call
    ``set_stage()`` / ``reset()`` / ``stop_stream()`` without opening a port.
    """
    is_open: bool = True
    written: List[bytes]

    def __init__(self) -> None:
        self.written = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def clear(self) -> None:
        self.written.clear()


class _LoadingPageShim:
    """Minimal simulation of ``LoadingPage``'s serial-signal slot chain.

    Reproduces only the methods that are wired up in ``main_window.py``::

        measurement_started → on_measurement_started() → bridge.on_stream_start()
        voltage_received    → on_voltage_received()
        current_received    → on_current_received()    → bridge.on_sample()
        measurement_stopped → on_measurement_stopped() → bridge.on_stream_stop()

    This lets us test the ``LoadingPage`` → ``FrontendBridge`` path without
    importing ``PySide6`` or standing up a QApplication.
    """

    def __init__(self, bridge: FrontendBridge) -> None:
        self._bridge = bridge
        self._stream_voltage_v: Optional[float] = None
        self._stream_current_a: Optional[float] = None

    # --- slot implementations (mirror loading_page.py) ---

    def on_measurement_started(self) -> None:
        """Called when STARTSTREAM received: delegate to bridge."""
        self._stream_voltage_v = None
        self._stream_current_a = None
        if self._bridge:
            self._bridge.on_stream_start()

    def on_voltage_received(self, voltage_v: float) -> None:
        """Called for each V<value> line."""
        self._stream_voltage_v = float(voltage_v)

    def on_current_received(self, current_a: float) -> None:
        """Called for each I<value> line; feeds bridge when voltage is ready."""
        self._stream_current_a = float(current_a)
        if self._bridge and self._stream_voltage_v is not None:
            self._bridge.on_sample(self._stream_voltage_v, self._stream_current_a)

    def on_measurement_stopped(self):
        """Called when STOPSTREAM received: finalise bridge."""
        if self._bridge:
            return self._bridge.on_stream_stop()
        return None


def _emit_vi_prefixed_line(
    page: _LoadingPageShim,
    voltage_v: float,
    current_a: float,
) -> None:
    """Simulate the ``SerialReader`` parsing a ``V<v>\\nI<i>\\n`` pair.

    Mirrors the parsing logic in ``home_page.py`` lines 140-156:
    - A line starting with ``V`` while streaming → ``voltage_received.emit()``
    - A line starting with ``I`` while streaming → ``current_received.emit()``
    """
    # Parse V-prefixed line and forward
    v_line = f"V{voltage_v}"
    page.on_voltage_received(float(v_line[1:].strip()))

    # Parse I-prefixed line and forward (value is in Amperes from the firmware)
    i_line = f"I{current_a}"
    page.on_current_received(float(i_line[1:].strip()))


def _run_constant_voltage_stream(
    constant_v: float,
    initial_current_a: float,
    bridge: FrontendBridge,
    page: _LoadingPageShim,
    mock_serial: _MockSerial,
    serial_config,
) -> Tuple[int, float, int, list]:
    """Inject constant-voltage VI lines until a snapshot is obtained or budget expires.

    Implements the full integration loop:
      1. Emit STARTSTREAM → ``on_measurement_started``
      2. For each sample:
         a. Emit V<v> + I<i> → ``on_voltage_received`` + ``on_current_received``
         b. The bridge processes it internally and fires `mock_serial_write` if needed.
         c. On a stage switch: update applied current.
      3. Once snapshot obtained, break.
      4. Emit STOPSTREAM → ``on_measurement_stopped``
    """
    page.on_measurement_started()

    current_a = initial_current_a
    samples = 0
    final_snapshot = None
    current_stage = 0
    all_written = []

    for _ in range(_MAX_SAMPLES):
        samples += 1
        _emit_vi_prefixed_line(page, constant_v, current_a)

        # Check for stage switch commands from the encapsulated commander
        while mock_serial.written:
            cmd = mock_serial.written.pop(0)
            all_written.append(cmd)
            if cmd.startswith("i"):
                try:
                    stage = int(cmd.strip()[1:])
                    current_stage = stage
                    current_a = serial_config.current_switch.current_mA_by_stage[stage] / 1000.0
                except ValueError:
                    pass
            elif cmd.strip() == "c":
                current_stage = 0
                current_a = serial_config.current_switch.current_mA_by_stage[0] / 1000.0

        if bridge.last_snapshot is not None:
            # Reached convergence!
            final_snapshot = bridge.last_snapshot
            break

    stopped_snapshot = page.on_measurement_stopped()
    if final_snapshot is None:
        final_snapshot = stopped_snapshot or bridge.last_snapshot

    final_current_mA = serial_config.current_switch.current_mA_by_stage[current_stage]
    return current_stage, final_current_mA, samples, all_written


# ---------------------------------------------------------------------------
# Parametrized test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "constant_v, expected_stage, expected_mA",
    _TEST_CASES,
    ids=[
        f"stage{stage}_v{v:.3f}_i{mA:.0f}mA"
        for v, stage, mA in _TEST_CASES
    ],
)
def test_vi_serial_switching_converges(
    tmp_path,
    monkeypatch,
    constant_v: float,
    expected_stage: int,
    expected_mA: float,
) -> None:
    """Verify that a constant-voltage VI serial stream converges at the correct stage.

    The test exercises the full integration path from the frontend serial
    parsing layer (``SerialReader`` signals → ``LoadingPage`` slots) through
    the ``FrontendBridge`` backbone to the ``SerialCommander`` stage-switching
    logic — without opening a serial port or touching real hardware.

    Assertions
    ----------
    1. A stable snapshot is produced (backbone converged).
    2. The commander settled on the correct current stage for the given voltage.
    3. The snapshot voltage is close to the injected constant voltage.
    4. The snapshot current_mA matches the expected stage current.
    5. The ``MockSerial.written`` log contains an ``i<stage>`` command whenever
       a stage switch was needed (verifying the backend→hardware signal path).
    """
    # --- Setup ---
    import time
    mock_time = [0.0]
    def mock_perf_counter():
        mock_time[0] += 0.01  # Advance 10ms per call (~100 SPS)
        return mock_time[0]
    monkeypatch.setattr(time, "perf_counter", mock_perf_counter)

    args = build_arg_parser().parse_args([
        "--noise", "0",           # zero noise for deterministic convergence
        "--backbone", "bocd",
    ])
    sim_config = build_simulation_config(args)
    serial_config = build_serial_config(args)

    mock_serial = _MockSerial()
    def mock_serial_write(cmd: str):
        mock_serial.written.append(cmd)

    bridge = FrontendBridge(
        "bocd", 
        sim_config, 
        str(tmp_path), 
        serial_config=serial_config, 
        write_callback=mock_serial_write
    )

    page = _LoadingPageShim(bridge)

    # Initial current: always start at stage 0 (4 mA)
    initial_current_a = serial_config.current_switch.current_mA_by_stage[0] / 1000.0

    # --- Run ---
    final_stage, final_current_mA, samples_consumed, all_written = _run_constant_voltage_stream(
        constant_v=constant_v,
        initial_current_a=initial_current_a,
        bridge=bridge,
        page=page,
        mock_serial=mock_serial,
        serial_config=serial_config,
    )

    # --- Retrieve final snapshot ---
    final_snapshot = bridge.last_snapshot

    print(
        f"\n[stage{expected_stage}] V={constant_v:.3f}V  "
        f"expected={expected_mA:.0f}mA  "
        f"got_stage={final_stage}  got_mA={final_current_mA:.0f}mA  "
        f"samples={samples_consumed}"
    )
    if final_snapshot is not None:
        print(
            f"  snapshot: V={final_snapshot.voltage:.5f}  "
            f"I={final_snapshot.current_mA:.3f}mA"
        )
    print(f"  serial writes: {all_written}")

    # 1. Backbone must have converged
    assert final_snapshot is not None, (
        f"No stable snapshot produced for V={constant_v:.3f}V after {samples_consumed} samples. "
        f"Backbone never converged."
    )

    # 2. Commander settled on the correct stage
    assert final_stage == expected_stage, (
        f"Expected stage {expected_stage} ({expected_mA:.0f} mA) "
        f"but commander is at stage {final_stage} ({final_current_mA:.0f} mA)."
    )

    # 3. Snapshot voltage is close to the injected constant
    assert abs(final_snapshot.voltage - constant_v) <= _SNAPSHOT_V_TOL, (
        f"Snapshot voltage {final_snapshot.voltage:.5f}V deviates too far from "
        f"injected constant {constant_v:.3f}V."
    )

    # 4. Snapshot current_mA matches the expected stage current
    assert abs(final_snapshot.current_mA - expected_mA) <= _SNAPSHOT_I_TOL, (
        f"Snapshot current {final_snapshot.current_mA:.3f} mA does not match "
        f"expected {expected_mA:.0f} mA."
    )

    # 5. Serial write log contains i<stage> command if stage != 0
    #    (stage 0 is the default; no switch command is sent for it)
    if expected_stage > 0:
        expected_cmd = f"i{expected_stage}"
        assert any(expected_cmd in w for w in all_written), (
            f"Expected serial command '{expected_cmd}' not found in writes: {all_written}"
        )
