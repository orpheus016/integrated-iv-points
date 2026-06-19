"""Integration helpers exposing a small programmatic API for downstream use.

This module keeps the serial capture path separate from software.main while
still reusing the same backbone, logger, and serial commander infrastructure.
"""

from __future__ import annotations

import argparse
import contextlib
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Tuple

from ..command.serial_commander import SerialCommander
from ..config.config import OutputConfig, SerialConfig, build_arg_parser, build_serial_config, build_simulation_config
from ..data_source.ads1256 import ads1256_passive_reader
from ..utils.backbone_factory import create_backbone
from ..utils.filters import LowPassFilter, MovingAverageFilter
from ..utils.logger import CsvLogger
from ..utils.math import compute_resistance_ohm
from ..utils.types import Snapshot

__all__ = [
    "LAST_CSV_PATH",
    "LAST_SNAPSHOT",
    "LAST_STATUS",
    "Pipeline",
    "FrontendBridge",
    "capture_serial_snapshot",
    "create_backbone",
    "create_commander",
    "run_pipeline",
]

LAST_SNAPSHOT: Optional[Snapshot] = None
LAST_CSV_PATH: Optional[str] = None
LAST_STATUS: Optional[str] = None


def create_commander(serial_config: SerialConfig) -> SerialCommander:
    return SerialCommander(serial_config)


@contextlib.contextmanager
def Pipeline(
    source_iter: Iterator,
    backbone,
    out_dir: str,
    visualizer=None,
    commander: Optional[SerialCommander] = None,
):
    logger = CsvLogger(out_dir)
    try:
        yield (source_iter, backbone, logger, visualizer, commander)
    finally:
        try:
            logger.close()
        except Exception:
            pass
        if commander is not None:
            try:
                commander.stop_stream()
            except Exception:
                pass
            try:
                commander.close()
            except Exception:
                pass


def run_pipeline(
    source_iter: Iterator,
    backbone,
    logger: CsvLogger,
    visualizer=None,
    commander: Optional[SerialCommander] = None,
    stop_on_snapshot: bool = True,
    switch_policy=None,
    gain: float = 1.0,
):
    last_snapshot = None
    stage_start_t = None
    blanking_until_t = None
    force_snapshot_at_t = None
    stage_snapshot_seen = False

    for sample in source_iter:
        t, v, i = sample
        if switch_policy is not None and stage_start_t is None:
            stage_start_t = t
            blanking_until_t = stage_start_t + switch_policy.blanking_s
            force_snapshot_at_t = stage_start_t + switch_policy.max_settle_s

        in_blanking = False
        force_snapshot_due = False
        if switch_policy is not None and stage_start_t is not None:
            assert blanking_until_t is not None
            assert force_snapshot_at_t is not None
            in_blanking = t < blanking_until_t
            force_snapshot_due = (not stage_snapshot_seen) and (t >= force_snapshot_at_t)

        snap: Snapshot | None = None
        if not in_blanking:
            snap = backbone.update((t, v, i))
        if snap is None and force_snapshot_due and not in_blanking:
            resistance = compute_resistance_ohm(v, i, gain)
            snap = Snapshot(timestamp=t, voltage=v, current_mA=i, resistance=resistance, std_dev=None)

        try:
            logger.log_sample(datetime.now(), t, v, i, snap)
        except Exception:
            pass

        if snap is not None:
            stage_snapshot_seen = True
            last_snapshot = snap
            if commander is not None:
                try:
                    decision = commander.decide_stage(snap.voltage, snap.current_mA)
                    if decision.switched and switch_policy is not None:
                        stage_start_t = t
                        blanking_until_t = stage_start_t + switch_policy.blanking_s
                        force_snapshot_at_t = stage_start_t + switch_policy.max_settle_s
                        stage_snapshot_seen = False
                        backbone.reset()
                except Exception:
                    pass
            if stop_on_snapshot:
                break

    return last_snapshot


def _build_default_output_root(args: argparse.Namespace) -> str:
    return os.path.join(args.output_dir, OutputConfig.ads1256_dir_name)


def capture_serial_snapshot(args: Optional[argparse.Namespace] = None) -> Optional[Snapshot]:
    """Capture one serial run and export the last stable snapshot.

    The Arduino owns stream framing. This function waits for *STREAM_START,
    reads until *STREAM_STOP, logs the per-run CSV, and stores the last
    emitted snapshot in LAST_SNAPSHOT for importers such as measurement.py.
    """
    global LAST_SNAPSHOT
    global LAST_CSV_PATH
    global LAST_STATUS

    if args is None:
        args = build_arg_parser().parse_args([])

    sim_config = build_simulation_config(args)
    serial_config = build_serial_config(args)
    backbone = create_backbone(args.backbone, sim_config, args)

    out_root = _build_default_output_root(args)
    run_name = f"volt_log_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir, run_filename = CsvLogger.build_run_paths(out_root, run_name)
    logger = CsvLogger(run_dir, filename=run_filename)
    LAST_CSV_PATH = logger.path

    moving_average = MovingAverageFilter(sim_config.moving_average_window)
    low_pass = LowPassFilter(sim_config.low_pass_alpha) if sim_config.enable_low_pass else None
    commander = SerialCommander(serial_config)
    source_iter = ads1256_passive_reader(serial_config, commander=commander, manage_current_switching=False)

    snapshot: Optional[Snapshot] = None
    status = "F"

    try:
        for elapsed_sample_s, raw_voltage, current_mA in source_iter:
            filtered = moving_average.update(raw_voltage)
            if low_pass is not None:
                filtered = low_pass.update(filtered)

            snapshot = backbone.update((elapsed_sample_s, filtered, current_mA))
            logger.log_sample(datetime.now(), elapsed_sample_s, filtered, current_mA, snapshot)

            if snapshot is not None:
                status = "snapshot"
                if args.stop_on_snapshot:
                    try:
                        commander.stop_stream()
                    except Exception:
                        pass
                    break
    except Exception:
        status = "error"
        raise
    finally:
        LAST_SNAPSHOT = snapshot
        LAST_STATUS = status

        try:
            logger.close()
        except Exception:
            pass

        try:
            commander.reset()
        except Exception:
            pass
        try:
            commander.close()
        except Exception:
            pass

        try:
            backbone.reset()
        except Exception:
            pass
        try:
            moving_average.reset()
        except Exception:
            pass
        if low_pass is not None:
            try:
                low_pass.reset()
            except Exception:
                pass

    return snapshot

import time

class FrontendBridge:
    """A push-based adapter for the PySide6 frontend to feed data into the backend.
    
    This class owns the backend pipeline (filtering, backbone, logging) without 
    needing to open its own serial port, allowing the frontend's SerialReader 
    to remain the sole owner of the serial port.
    """
    def __init__(self, backbone_name: str, sim_config, output_dir: str):
        self.sim_config = sim_config
        self.backbone = create_backbone(backbone_name, sim_config)
        self.output_dir = output_dir
        self.moving_average = MovingAverageFilter(sim_config.moving_average_window)
        self.low_pass = LowPassFilter(sim_config.low_pass_alpha) if sim_config.enable_low_pass else None
        
        self.logger: Optional[CsvLogger] = None
        self.last_snapshot: Optional[Snapshot] = None
        self.last_csv_path: Optional[str] = None
        self.start_time: float = 0.0
        
    def on_stream_start(self):
        """Called when STARTSTREAM is received from Arduino."""
        self.backbone.reset()
        self.moving_average.reset()
        if self.low_pass is not None:
            self.low_pass.reset()
            
        run_name = f"volt_log_{datetime.now():%Y%m%d_%H%M%S_%f}"
        run_dir, run_filename = CsvLogger.build_run_paths(self.output_dir, run_name)
        self.logger = CsvLogger(run_dir, filename=run_filename)
        self.last_csv_path = self.logger.path
        self.last_snapshot = None
        self.start_time = time.perf_counter()

    def on_sample(self, voltage_v: float, current_a: float) -> Optional[Tuple[float, Optional[Snapshot]]]:
        """Called when a paired V and I reading is received."""
        if self.logger is None:
            return None  # Stream not started
            
        # Convert Amperes to milliamps for the backend
        current_mA = current_a * 1000.0
        elapsed_s = time.perf_counter() - self.start_time
        
        filtered = self.moving_average.update(voltage_v)
        if self.low_pass is not None:
            filtered = self.low_pass.update(filtered)
            
        snap = self.backbone.update((elapsed_s, filtered, current_mA))
        self.logger.log_sample(datetime.now(), elapsed_s, filtered, current_mA, snap)
        
        if snap is not None:
            self.last_snapshot = snap
            
        return filtered, snap
            
    def on_stream_stop(self) -> Optional[Snapshot]:
        """Called when STOPSTREAM is received from Arduino."""
        if self.logger is not None:
            self.logger.close()
            self.logger = None
            
        return self.last_snapshot
