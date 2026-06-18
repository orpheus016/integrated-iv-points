"""
Capture IV data from Arduino to CSV using the SerialCommander abstraction interface.
Complies with csv_replay.py rules and handles system exceptions gracefully.
"""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime
from pathlib import Path

from ..config.config import build_arg_parser, build_serial_config, OutputConfig
from ..command.serial_commander import SerialCommander

def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    serial_cfg = build_serial_config(args)
    markers = serial_cfg.markers
    protocol = serial_cfg.protocol

    out_dir = Path(OutputConfig.testbench_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if args.filename:
        out_path = out_dir / f"{args.filename}.csv"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"capture_{timestamp}.csv"

    commander = SerialCommander(serial_cfg)

    try:
        print(f"Opening port {serial_cfg.port}...")
        commander.open()
        
        # Wait out the initial bootloader reset window
        print(f"Waiting {protocol.stream_startup_delay_s}s for hardware initialization...")
        time.sleep(protocol.stream_startup_delay_s)
        
        # Flush the buffer of data sent during boot
        commander.flush_input()

        print(f"Initiating stream with token: '{protocol.stream_command}'")
        commander.start_stream()

        print("Synchronizing with stream header...")
        
        # Robust synchronization loop: loop until we find exactly stream_start
        start_timeout = time.monotonic() + protocol.stream_start_timeout_s
        while True:
            if time.monotonic() > start_timeout:
                raise TimeoutError(f"Timed out waiting for synchronization marker: {markers.stream_start}")
                
            line = commander.read_line()
            if not line:
                continue
                
            if line == markers.stream_start:
                print(f"Stream synchronized. Writing to -> {out_path}")
                break
            
            # Print any boot/debug messages out to console while waiting
            if line.startswith("*"):
                print(f"[Hardware Log] {line}")

        # Now begin recording data safely
        with out_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["voltage", "current_mA"]) # Header for csv_replay.py

            while True:
                line = commander.read_line()
                
                if line == markers.stream_stop:
                    print("Stream terminated normally by hardware.")
                    break
                
                if line.startswith("*"):
                    # Ignore auxiliary log lines or unexpected markers safely mid-stream
                    continue

                if "," in line:
                    try:
                        sample = commander.parse_sample_line(line, timestamp_s=0.0)
                        writer.writerow([sample.voltage_v, sample.current_mA])
                    except ValueError:
                        continue

    except KeyboardInterrupt:
        print(f"\nExecution interrupted. Issuing halt command '{protocol.stop_command}'...")
        try:
            commander.stop_stream()
            # Drain trailing data lines up to the final stop marker using raw read to avoid class panic
            stop_timeout = time.monotonic() + 2.0
            while time.monotonic() < stop_timeout:
                line = commander.read_line()
                if line == markers.stream_stop:
                    print("Halt handshake confirmed.")
                    break
        except Exception as e:
            print(f"Failed to close connection down cleanly: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Runtime Exception: {e}", file=sys.stderr)
    finally:
        commander.close()
        print("Serial port interface released.")

if __name__ == "__main__":
    main()