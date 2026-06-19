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
