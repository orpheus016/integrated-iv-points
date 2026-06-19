import os
import csv
import pytest
from datetime import datetime

from software.config.config import build_arg_parser, build_simulation_config, build_serial_config
from software.scripts.integrate import FrontendBridge
from software.command.serial_commander import SerialCommander
from measurement import calculate_doping_from_snapshot

def test_frontend_data_flow_and_switching(tmp_path):
    # 1. Setup paths and configs
    csv_path = os.path.join(
        "software", "output", "ads1256", "volt_log_20260529_153043", "volt_log_20260529_153043.csv"
    )
    assert os.path.exists(csv_path), f"Test data not found at {csv_path}"

    args = build_arg_parser().parse_args([])
    sim_config = build_simulation_config(args)
    serial_config = build_serial_config(args)
    
    # 2. Instantiate Bridge and Commander
    bridge = FrontendBridge("bocd", sim_config, str(tmp_path))
    commander = SerialCommander(serial_config)
    
    # Mock commander as open since we aren't connecting to serial
    class MockSerial:
        is_open = True
        def write(self, data):
            pass
    commander._serial = MockSerial()
    
    bridge.on_stream_start()
    
    highest_stage_commanded = 0
    final_snapshot = None
    
    # Track the current applied by the test logic
    test_current_mA = serial_config.current_switch.current_mA_by_stage[0]
    
    # Analytics tracking
    switch_events = []
    
    blanking_until_s = 0.0
    previous_snapshot = None
    
    # 3. Process CSV lines
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            try:
                v = float(row['measured_v'])
                csv_current_mA = float(row['current_mA'])
                csv_stage = int(row['stage_effective'])
                elapsed_s = float(row['elapsed_s'])
            except ValueError:
                continue
                
            # Scale the voltage according to Ohm's Law.
            # If our test logic has increased the current, the measured voltage should increase proportionally.
            simulated_v = v * (test_current_mA / csv_current_mA)
            
            # Feed to FrontendBridge using our internally managed current and simulated voltage
            bridge.on_sample(simulated_v, test_current_mA / 1000.0)
            
            # Use the latest snapshot (if any) to emulate backend SerialCommander logic
            snap = bridge.last_snapshot
            is_new_snapshot = (snap is not previous_snapshot) and (snap is not None)
            previous_snapshot = snap
                
            if is_new_snapshot:
                decision = commander.decide_stage(snap.voltage, snap.current_mA)
                if decision.switched:
                    # Record analytics for the switch
                    switch_events.append({
                        "sample_idx": idx,
                        "from_stage": highest_stage_commanded,
                        "to_stage": decision.stage,
                        "test_current_mA": test_current_mA,
                        "new_current_mA": serial_config.current_switch.current_mA_by_stage[decision.stage],
                        "snapshot_v": snap.voltage,
                        "csv_stage_at_switch": csv_stage,
                        "csv_v_at_switch": v,
                        "elapsed_s": elapsed_s
                    })
                    
                    highest_stage_commanded = decision.stage
                    # Apply the new current to our local state
                    test_current_mA = serial_config.current_switch.current_mA_by_stage[decision.stage]
                    
                    # Emulate hardware reset during stage switch
                    bridge.backbone.reset()
                    bridge.moving_average.reset()
                    if bridge.low_pass:
                        bridge.low_pass.reset()                    
    # 4. Stop stream and get final snapshot
    final_snapshot = bridge.on_stream_stop()
    
    # Print out our analytics
    print("\n--- Current Switching Analytics ---")
    for event in switch_events:
        print(f"Switched {event['from_stage']} -> {event['to_stage']} at sample {event['sample_idx']}.")
        print(f"  Voltage at switch: {event['snapshot_v']:.5f}V (Raw CSV: {event['csv_v_at_switch']:.5f}V)")
        print(f"  Current changed: {event['test_current_mA']}mA -> {event['new_current_mA']}mA")
        print(f"  CSV Hardware Stage at this moment: {event['csv_stage_at_switch']}")
        
    print(f"\nFinal Snapshot Voltage: {final_snapshot.voltage:.5f}V")
    print(f"Final Snapshot Current: {final_snapshot.current_mA}mA")
    print("-----------------------------------")
    
    # 5. Assertions
    # Ensure pipeline outputted a valid snapshot
    assert final_snapshot is not None, "Pipeline never produced a stable snapshot."
    assert final_snapshot.voltage > 0, "Snapshot voltage should be positive."
    assert final_snapshot.current_mA > 0, "Snapshot current should be positive."
    # Ensure current switching reached at least stage 1
    assert highest_stage_commanded >= 1, f"Expected commander to reach at least stage 1, but got {highest_stage_commanded}"
    
    # Validate measurement.py calculation
    result = calculate_doping_from_snapshot(
        thickness_mm=0.6,
        carrier_type="N (100)",
        snapshot=final_snapshot,
        temp_c=25.0
    )
    
    assert result is not None
    assert "doping_cm3" in result
    assert result["doping_cm3"] > 0, "Calculated doping should be a positive float."
    assert result["resistivity_ohm_cm"] > 0, "Calculated resistivity should be positive."


def test_bridge_resets_on_start_loading(tmp_path):
    """Verify that on_stream_start() (called by start_loading()) cleanly resets
    the backbone, filters, and logger so each measurement run starts fresh.

    This mirrors the fix applied to LoadingPage.start_loading(): the bridge is
    reset at measurement entry, not when STARTSTREAM arrives from serial.
    """
    args = build_arg_parser().parse_args([])
    sim_config = build_simulation_config(args)

    bridge = FrontendBridge("bocd", sim_config, str(tmp_path))

    # --- First run ---
    bridge.on_stream_start()
    first_logger_path = bridge.last_csv_path
    assert bridge.logger is not None, "Logger should be open after on_stream_start()"
    assert bridge.last_snapshot is None, "Snapshot must be None at stream start"

    # Feed a handful of stable samples so the backbone may emit a snapshot
    for i in range(20):
        bridge.on_sample(voltage_v=1.5, current_a=0.004)

    # Capture first-run snapshot state
    first_snapshot = bridge.last_snapshot
    bridge.on_stream_stop()
    assert bridge.logger is None, "Logger should be closed after on_stream_stop()"

    # --- Second run (simulates user pressing Start Measurement again) ---
    bridge.on_stream_start()
    second_logger_path = bridge.last_csv_path

    assert second_logger_path != first_logger_path, (
        "Each run must write to a unique timestamped directory"
    )
    assert bridge.last_snapshot is None, (
        "Snapshot must be reset to None at the start of a new run"
    )
    assert bridge.logger is not None, "Logger must be open for the second run"

    # Feed samples for second run with a different voltage level
    for i in range(20):
        bridge.on_sample(voltage_v=2.0, current_a=0.008)

    second_snapshot = bridge.on_stream_stop()

    # The two snapshots should be independent
    if first_snapshot is not None and second_snapshot is not None:
        assert first_snapshot is not second_snapshot, (
            "Second run snapshot must be a new object, not the first run's"
        )


def test_sequential_measurement_runs_no_stale_state(tmp_path):
    """Simulate two complete measurement cycles through FrontendBridge and
    confirm that the second run is not contaminated by the first run's data.

    This is the unit-level equivalent of pressing 'Start Measurement' twice in
    the GUI, exercising the same reset path that LoadingPage.start_loading() calls.
    """
    args = build_arg_parser().parse_args([])
    sim_config = build_simulation_config(args)

    bridge = FrontendBridge("bocd", sim_config, str(tmp_path))

    def _run_stream(voltage_v: float, current_a: float, n_samples: int = 30):
        """Helper: start stream, push samples, stop stream, return snapshot."""
        bridge.on_stream_start()
        for _ in range(n_samples):
            bridge.on_sample(voltage_v=voltage_v, current_a=current_a)
        return bridge.on_stream_stop()

    # Run 1: low-impedance scenario
    snap1 = _run_stream(voltage_v=0.5, current_a=0.020, n_samples=40)

    # Run 2: high-impedance scenario with a different voltage
    snap2 = _run_stream(voltage_v=3.0, current_a=0.004, n_samples=40)

    # Both runs must produce independent (or None) snapshots
    # If backbone produced snapshots, they must differ
    if snap1 is not None and snap2 is not None:
        # Voltage regimes differ by 6x — snapshots cannot be identical
        assert snap1 is not snap2, "Snapshots from separate runs must be distinct objects"
        # The second-run snapshot should reflect the higher voltage regime
        assert abs(snap2.voltage - snap1.voltage) > 0.01, (
            f"Second-run snapshot voltage ({snap2.voltage:.4f}V) should differ "
            f"from first-run ({snap1.voltage:.4f}V) given different input regimes"
        )

    # Verify unique log files were written for each run
    csv_files = list(tmp_path.rglob("*.csv"))
    assert len(csv_files) >= 2, (
        f"Expected at least 2 separate CSV log files (one per run), found {len(csv_files)}"
    )
