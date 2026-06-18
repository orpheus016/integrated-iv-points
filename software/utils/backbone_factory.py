"""Shared factory helpers for constructing backbone implementations.

Keeping the selection logic in one place avoids duplicated branching across
`main.py`, `scripts/evaluate.py`, and `scripts/integrate.py`.
"""

from __future__ import annotations

from typing import Any

from ..backbones.baseline import BaselineBackbone
from ..backbones.bocd import BochdBackbone
from ..backbones.derivative_integration import DerivativeIntegrationBackbone
from ..backbones.hysteresis import HysteresisBackbone
from ..backbones.running_stat import RunningStatBackbone
from ..backbones.stddev_window import StdDevWindowBackbone


def create_backbone(name: str, sim_config: Any, args: Any = None) -> object:
    window_samples = max(1, int(sim_config.snapshot_window_s * sim_config.sample_rate_hz))
    min_stable_samples = max(1, int(sim_config.snapshot_min_duration_s * sim_config.sample_rate_hz))
    min_recording_samples = max(1, int(sim_config.snapshot_min_recording_s * sim_config.sample_rate_hz))

    if name == "stddev_window":
        return StdDevWindowBackbone(max(2, window_samples), sim_config.snapshot_std_threshold_v, min_stable_samples, min_recording_samples, gain=sim_config.gain)

    if name == "baseline":
        return BaselineBackbone(max(2, window_samples), sim_config.snapshot_std_threshold_v, min_stable_samples, min_recording_samples, gain=sim_config.gain)

    if name == "running_stat":
        return RunningStatBackbone(max(2, window_samples), sim_config.snapshot_std_threshold_v, min_stable_samples, min_recording_samples, gain=sim_config.gain)

    if name == "hysteresis":
        enter = getattr(args, "hysteresis_enter", 1.0) if args is not None else 1.0
        exit_t = getattr(args, "hysteresis_exit", 0.8) if args is not None else 0.8
        return HysteresisBackbone(max(1, window_samples), enter, exit_t, min_stable_samples, min_recording_samples, gain=sim_config.gain)

    if name == "bocd":
        hazard_rate = getattr(args, "bocd_hazard_rate", 1.0 / 200.0) if args is not None else 1.0 / 200.0
        mean0 = getattr(args, "bocd_mean0", 0.0) if args is not None else 0.0
        var0 = getattr(args, "bocd_var0", 1.0) if args is not None else 1.0
        varx = getattr(args, "bocd_varx", 1e-6) if args is not None else 1e-6
        cp_reset_threshold = getattr(args, "bocd_cp_reset_threshold", 5) if args is not None else 5
        return BochdBackbone(
            min_stable_samples=10,
            min_recording_samples=min_recording_samples,
            hazard_rate=hazard_rate,
            mean0=mean0,
            var0=var0,
            varx=varx,
            cp_reset_threshold=cp_reset_threshold,
            gain=sim_config.gain,
        )

    if name == "derivative_integration":
        dt = getattr(args, "di_dt_threshold", 0.005) if args is not None else 0.005
        it = getattr(args, "di_it_threshold", 0.05) if args is not None else 0.05
        leakage = getattr(args, "di_leakage_factor", 0.9) if args is not None else 0.9
        iir_window = getattr(args, "di_iir_window", 16) if args is not None else 16
        return DerivativeIntegrationBackbone(
            window_samples=max(2, window_samples),
            derivative_threshold=dt,
            integration_threshold=it,
            min_stable_samples=min_stable_samples,
            min_recording_samples=min_recording_samples,
            leakage_factor=leakage,
            iir_window=iir_window,
            gain=sim_config.gain,
        )

    raise ValueError(f"unknown backbone: {name}")