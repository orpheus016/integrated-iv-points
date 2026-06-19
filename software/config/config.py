"""Configuration defaults for voltage simulation and streaming."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SimulationConfig:
    sample_rate_hz: float = 50.0
    window_seconds: float = 10.0
    snapshot_min_recording_s: float = 1.0
    max_measurement_s: float = 5.0
    gain: float = 1.82
    current_source_a: float = 0.010
    sample_resistance_ohm: float = 1.0
    transient_model: str = "first_order"
    tau_s: float = 0.5
    damping_ratio: float = 0.4
    noise_sigma_v: float = 0.0005
    drift_amplitude_v: float = 0.0002
    drift_frequency_hz: float = 0.05
    line_interference_hz: float = 50.0
    line_interference_v: float = 0.0003
    adc_full_scale_v: float = 2.5
    adc_bits: int = 24
    moving_average_window: int = 5
    low_pass_alpha: float = 0.2
    enable_low_pass: bool = False
    snapshot_window_s: float = 1.0
    snapshot_std_threshold_v: float = 0.0002
    snapshot_min_duration_s: float = 1.0


@dataclass(frozen=True)
class StreamMarkersConfig:
    stream_start: str = "*STREAM_START"
    stream_stop: str = "*STREAM_STOP"
    reset_done: str = "*Reset DONE!"


@dataclass(frozen=True)
class FrontendMarkersConfig:
    stream_start: str = "STARTSTREAM"
    stream_stop: str = "STOPSTREAM"


@dataclass(frozen=True)
class SerialProtocolConfig:
    reset_command: str = "R"
    stream_command: str = "C"
    stop_command: str = "s"
    stage_command_prefix: str = "i"
    stage_command_min: int = 0
    stage_command_max: int = 3
    stream_startup_delay_s: float = 2.0
    stream_start_timeout_s: float = 5.0
    stream_restart_delay_s: float = 0.07
    line_timeout_s: float = 1.0


@dataclass(frozen=True)
class CurrentSwitchConfig:
    current_mA_by_stage: Tuple[float, float, float, float] = (4.0, 8.0, 12.0, 20.0)
    power_limit_mw: float = 5.0
    min_voltage_v: float = 0.001
    headroom_v: float = 2.0
    raise_low_v_by_stage: Tuple[float, float, float, float] = (0.3, 0.25, 0.15, 0.0)
    raise_high_v_by_stage: Tuple[float, float, float, float] = (0.35, 0.3, 0.2, 0.0)
    blanking_s: float = 0.5
    max_settle_s: float = 1.2
    stage_match_tolerance_mA: float = 0.1


@dataclass(frozen=True)
class OutputConfig:
    ads_dir: str = "software/output/ads"
    ads1256_dir_name: str = "ads1256"
    testbench_dir: str = "software/output/testbench"


@dataclass(frozen=True)
class CLIConfig:
    source: str = "dummy"
    backbone: str = "bocd"
    bocd_hazard_rate: float = 0.02
    bocd_mean0: float = 0.0
    bocd_var0: float = 0.5
    bocd_varx: float = 0.0001
    bocd_cp_reset_threshold: int = 3
    di_dt_threshold: float = 0.005
    di_it_threshold: float = 0.05
    di_leakage_factor: float = 0.9
    di_iir_window: int = 16
    csv_path: str = "software/output/testbench/input.csv"
    sample_rate_hz: float = SimulationConfig.sample_rate_hz
    window_seconds: float = SimulationConfig.window_seconds
    snapshot_min_recording_s: float = SimulationConfig.snapshot_min_recording_s
    max_measurement_s: float = SimulationConfig.max_measurement_s
    gain: float = SimulationConfig.gain
    current_source_a: float = SimulationConfig.current_source_a
    sample_resistance_ohm: float = SimulationConfig.sample_resistance_ohm
    transient_model: str = SimulationConfig.transient_model
    tau_s: float = SimulationConfig.tau_s
    damping_ratio: float = SimulationConfig.damping_ratio
    noise_sigma_v: float = SimulationConfig.noise_sigma_v
    drift_amplitude_v: float = SimulationConfig.drift_amplitude_v
    drift_frequency_hz: float = SimulationConfig.drift_frequency_hz
    line_interference_hz: float = SimulationConfig.line_interference_hz
    line_interference_v: float = SimulationConfig.line_interference_v
    adc_full_scale_v: float = SimulationConfig.adc_full_scale_v
    adc_bits: int = SimulationConfig.adc_bits
    moving_average_window: int = SimulationConfig.moving_average_window
    low_pass: bool = SimulationConfig.enable_low_pass
    low_pass_alpha: float = SimulationConfig.low_pass_alpha
    snapshot_window_s: float = SimulationConfig.snapshot_window_s
    snapshot_std_threshold_v: float = SimulationConfig.snapshot_std_threshold_v
    snapshot_min_duration_s: float = SimulationConfig.snapshot_min_duration_s
    snapshot_mode: str = "first"
    plot_mode: str = "comparison"
    live_plot: bool = False
    plot_update_hz: float = 15.0
    plot_backend: str = ""
    save_plot_on_interrupt: bool = False
    live_backbones: str = ""
    live_duration_s: float = 0.0
    evaluation_plot_mode: str = "comparison"
    evaluation_animate: bool = False
    evaluation_animation_output: str = "screen"
    evaluation_animation_fps: int = 12
    stop_on_snapshot: bool = True
    stop_holdoff_s: float = CurrentSwitchConfig.blanking_s
    stop_require_post_switch: bool = True
    stop_final_holdoff_s: float = CurrentSwitchConfig.max_settle_s
    output_dir: str = "software/output"
    port: str = "COM5"
    baud: int = 115200
    switch_currents: str = "4.0,8.0,12.0,20.0"
    switch_raise_low: str = "0.3,0.25,0.15,0.0"
    switch_raise_high: str = "0.35,0.3,0.2,0.0"
    switch_power_limit_mw: float = CurrentSwitchConfig.power_limit_mw
    switch_min_voltage_v: float = CurrentSwitchConfig.min_voltage_v
    switch_headroom_v: float = CurrentSwitchConfig.headroom_v
    switch_blanking_s: float = CurrentSwitchConfig.blanking_s
    switch_max_settle_s: float = CurrentSwitchConfig.max_settle_s
    switch_stage_match_tol_mA: float = CurrentSwitchConfig.stage_match_tolerance_mA
    # Evaluate script specific defaults
    input: str = "software/output/testbench"
    out: str = "software/output/evaluate"
    backbones: str = "stddev_window,baseline,hysteresis,derivative_integration"
    show: bool = False
    filename: str = ""
    frontend_start_marker: str = FrontendMarkersConfig.stream_start
    frontend_stop_marker: str = FrontendMarkersConfig.stream_stop
    data_format: str = "vi_prefixed"  # "vi_prefixed" for PySide GUI, "csv" for backend standalone



@dataclass(frozen=True)
class SerialConfig:
    port: str = "COM5"
    baud_rate: int = 115200
    timeout_s: float = 1.0
    markers: StreamMarkersConfig = StreamMarkersConfig()
    frontend_markers: FrontendMarkersConfig = FrontendMarkersConfig()
    protocol: SerialProtocolConfig = SerialProtocolConfig()
    current_switch: CurrentSwitchConfig = CurrentSwitchConfig()
    data_format: str = "csv"


def _parse_float_tuple(value: str, expected_len: int, label: str) -> Tuple[float, ...]:
    parts = [item.strip() for item in value.split(",") if item.strip()]
    if len(parts) != expected_len:
        raise ValueError(f"{label} expects {expected_len} comma-separated values, got {len(parts)}")
    return tuple(float(item) for item in parts)


def build_arg_parser() -> argparse.ArgumentParser:
    defaults = CLIConfig()
    parser = argparse.ArgumentParser(description="Simulated ADS1256 voltage acquisition")
    parser.add_argument("--source", choices=["dummy", "serial", "csv", "settling", "worst_case"], default=defaults.source)
    parser.add_argument("--backbone", choices=["running_stat", "stddev_window", "baseline", "hysteresis", "bocd", "derivative_integration"], default=defaults.backbone)
    parser.add_argument("--csv-path", type=str, default=defaults.csv_path)
    parser.add_argument("--sample-rate", type=float, default=defaults.sample_rate_hz)
    parser.add_argument("--window-seconds", type=float, default=defaults.window_seconds)
    parser.add_argument("--snapshot-min-recording", type=float, default=defaults.snapshot_min_recording_s)
    parser.add_argument("--max-measurement", type=float, default=defaults.max_measurement_s)
    parser.add_argument("--gain", type=float, default=defaults.gain)
    parser.add_argument("--current", type=float, default=defaults.current_source_a)
    parser.add_argument("--resistance", type=float, default=defaults.sample_resistance_ohm)
    parser.add_argument("--transient-model", choices=["first_order", "underdamped"], default=defaults.transient_model)
    parser.add_argument("--tau", type=float, default=defaults.tau_s)
    parser.add_argument("--damping", type=float, default=defaults.damping_ratio)
    parser.add_argument("--noise", type=float, default=defaults.noise_sigma_v)
    parser.add_argument("--drift-amp", type=float, default=defaults.drift_amplitude_v)
    parser.add_argument("--drift-freq", type=float, default=defaults.drift_frequency_hz)
    parser.add_argument("--line-freq", type=float, default=defaults.line_interference_hz)
    parser.add_argument("--line-amp", type=float, default=defaults.line_interference_v)
    parser.add_argument("--adc-full-scale", type=float, default=defaults.adc_full_scale_v)
    parser.add_argument("--adc-bits", type=int, default=defaults.adc_bits)
    parser.add_argument("--moving-average", type=int, default=defaults.moving_average_window)
    parser.add_argument("--low-pass", action=argparse.BooleanOptionalAction, default=defaults.low_pass)
    parser.add_argument("--low-pass-alpha", type=float, default=defaults.low_pass_alpha)
    parser.add_argument("--snapshot-window", type=float, default=defaults.snapshot_window_s)
    parser.add_argument("--snapshot-threshold", type=float, default=defaults.snapshot_std_threshold_v)
    parser.add_argument("--snapshot-min-duration", type=float, default=defaults.snapshot_min_duration_s)
    # Hysteresis backbone tuning
    parser.add_argument("--hysteresis-enter", type=float, default=1.0, help="enter threshold (V) for hysteresis backbone")
    parser.add_argument("--hysteresis-exit", type=float, default=0.8, help="exit threshold (V) for hysteresis backbone")
    # BOCD backbone tuning
    parser.add_argument("--bocd-hazard-rate", type=float, default=defaults.bocd_hazard_rate, dest="bocd_hazard_rate", help="prior changepoint probability per sample for BOCD backbone")
    parser.add_argument("--bocd-mean0", type=float, default=defaults.bocd_mean0, dest="bocd_mean0", help="prior mean on the signal level for BOCD backbone")
    parser.add_argument("--bocd-var0", type=float, default=defaults.bocd_var0, dest="bocd_var0", help="prior variance on the signal mean for BOCD backbone")
    parser.add_argument("--bocd-varx", type=float, default=defaults.bocd_varx, dest="bocd_varx", help="assumed observation noise variance for BOCD backbone")
    parser.add_argument("--bocd-cp-reset-threshold", type=int, default=defaults.bocd_cp_reset_threshold, dest="bocd_cp_reset_threshold", help="MAP run-length must fall below this to confirm a changepoint (BOCD backbone)")
    # Derivative Integration backbone tuning
    parser.add_argument("--di-derivative-threshold", type=float, default=defaults.di_dt_threshold, dest="di_dt_threshold", help="minimum delta to trigger integration (DI backbone)")
    parser.add_argument("--di-integration-threshold", type=float, default=defaults.di_it_threshold, dest="di_it_threshold", help="accumulated value required to flag detection (DI backbone)")
    parser.add_argument("--di-leakage-factor", type=float, default=defaults.di_leakage_factor, dest="di_leakage_factor", help="dissipation rate (DI backbone)")
    parser.add_argument("--di-iir-window", type=int, default=defaults.di_iir_window, dest="di_iir_window", help="window size for smoothing (DI backbone)")
    parser.add_argument("--snapshot-mode", choices=["first", "continuous"], default=defaults.snapshot_mode)
    parser.add_argument("--plot-mode", choices=["comparison", "full"], default=defaults.plot_mode)
    parser.add_argument("--live-plot", action=argparse.BooleanOptionalAction, default=defaults.live_plot)
    parser.add_argument("--plot-update-hz", type=float, default=defaults.plot_update_hz)
    parser.add_argument("--plot-backend", type=str, default=defaults.plot_backend)
    parser.add_argument("--save-plot-on-interrupt", action=argparse.BooleanOptionalAction, default=defaults.save_plot_on_interrupt)
    parser.add_argument("--live-backbones", type=str, default=defaults.live_backbones, help="comma-separated backbone names for live comparison")
    parser.add_argument("--live-duration", type=float, default=defaults.live_duration_s, help="duration (s) for live multi-backbone capture; 0 uses --max-measurement")
    parser.add_argument("--evaluation-plot-mode", choices=["comparison", "transient"], default=defaults.evaluation_plot_mode)
    parser.add_argument("--evaluation-animate", action=argparse.BooleanOptionalAction, default=defaults.evaluation_animate)
    parser.add_argument("--evaluation-animation-output", choices=["screen", "gif", "video"], default=defaults.evaluation_animation_output)
    parser.add_argument("--evaluation-animation-fps", type=int, default=defaults.evaluation_animation_fps)
    parser.add_argument("--stop-on-snapshot", action=argparse.BooleanOptionalAction, default=defaults.stop_on_snapshot)
    parser.add_argument(
        "--stop-holdoff",
        dest="stop_holdoff_s",
        type=float,
        default=defaults.stop_holdoff_s,
        help="minimum seconds after stage switch before stop-on-snapshot",
    )
    parser.add_argument("--stop-require-post-switch", action=argparse.BooleanOptionalAction, default=defaults.stop_require_post_switch, help="require a post-switch snapshot before stop-on-snapshot")
    parser.add_argument(
        "--stop-final-holdoff",
        dest="stop_final_holdoff_s",
        type=float,
        default=defaults.stop_final_holdoff_s,
        help="extra holdoff (s) before stopping on the final stage",
    )
    parser.add_argument("--output-dir", type=str, default=defaults.output_dir)
    parser.add_argument("--port", type=str, default=defaults.port)
    parser.add_argument("--baud", type=int, default=defaults.baud)
    parser.add_argument("--switch-currents", type=str, default=defaults.switch_currents, help="comma-separated current stages in mA")
    parser.add_argument("--switch-raise-low", type=str, default=defaults.switch_raise_low, help="comma-separated raise low thresholds in V")
    parser.add_argument("--switch-raise-high", type=str, default=defaults.switch_raise_high, help="comma-separated raise high thresholds in V")
    parser.add_argument("--switch-power-limit-mw", type=float, default=defaults.switch_power_limit_mw)
    parser.add_argument("--switch-min-voltage", type=float, default=defaults.switch_min_voltage_v)
    parser.add_argument("--switch-headroom", type=float, default=defaults.switch_headroom_v)
    parser.add_argument("--switch-blanking", type=float, default=defaults.switch_blanking_s)
    parser.add_argument("--switch-max-settle", type=float, default=defaults.switch_max_settle_s)
    parser.add_argument("--switch-stage-match-tol", type=float, default=defaults.switch_stage_match_tol_mA, help="tolerance (mA) for mapping current to stage")
    # Evaluate script specific args
    parser.add_argument("--input", type=str, default=defaults.input, help="file or directory to read CSVs from")
    parser.add_argument("--out", type=str, default=defaults.out, help="output directory for plots and summaries")
    parser.add_argument("--backbones", type=str, default=defaults.backbones, help="comma-separated backbone names to evaluate")
    parser.add_argument("--show", action="store_true", help="show interactive plots", default=defaults.show)
    parser.add_argument("--filename", type=str, default=defaults.filename, help="Custom name for saved CSV (manual_capture)")
    # Frontend config args
    parser.add_argument("--frontend-start-marker", type=str, default=defaults.frontend_start_marker, help="marker that Arduino sends to start the stream")
    parser.add_argument("--frontend-stop-marker", type=str, default=defaults.frontend_stop_marker, help="marker that Arduino sends to stop the stream")
    parser.add_argument("--data-format", choices=["csv", "vi_prefixed"], default=defaults.data_format, help="format of data lines over serial")
    return parser


def build_simulation_config(args: argparse.Namespace) -> SimulationConfig:
    return SimulationConfig(
        sample_rate_hz=args.sample_rate,
        window_seconds=args.window_seconds,
        snapshot_min_recording_s=args.snapshot_min_recording,
        max_measurement_s=args.max_measurement,
        gain=args.gain,
        current_source_a=args.current,
        sample_resistance_ohm=args.resistance,
        transient_model=args.transient_model,
        tau_s=args.tau,
        damping_ratio=args.damping,
        noise_sigma_v=args.noise,
        drift_amplitude_v=args.drift_amp,
        drift_frequency_hz=args.drift_freq,
        line_interference_hz=args.line_freq,
        line_interference_v=args.line_amp,
        adc_full_scale_v=args.adc_full_scale,
        adc_bits=args.adc_bits,
        moving_average_window=args.moving_average,
        low_pass_alpha=args.low_pass_alpha,
        enable_low_pass=args.low_pass,
        snapshot_window_s=args.snapshot_window,
        snapshot_std_threshold_v=args.snapshot_threshold,
        snapshot_min_duration_s=args.snapshot_min_duration,
    )


def build_serial_config(args: argparse.Namespace) -> SerialConfig:
    defaults = CurrentSwitchConfig()
    currents = _parse_float_tuple(args.switch_currents, len(defaults.current_mA_by_stage), "switch-currents")
    raise_low = _parse_float_tuple(args.switch_raise_low, len(defaults.raise_low_v_by_stage), "switch-raise-low")
    raise_high = _parse_float_tuple(args.switch_raise_high, len(defaults.raise_high_v_by_stage), "switch-raise-high")
    current_switch = CurrentSwitchConfig(
        current_mA_by_stage=currents,
        power_limit_mw=args.switch_power_limit_mw,
        min_voltage_v=args.switch_min_voltage,
        headroom_v=args.switch_headroom,
        raise_low_v_by_stage=raise_low,
        raise_high_v_by_stage=raise_high,
        blanking_s=args.switch_blanking,
        max_settle_s=args.switch_max_settle,
        stage_match_tolerance_mA=args.switch_stage_match_tol,
    )
    frontend_markers = FrontendMarkersConfig(
        stream_start=args.frontend_start_marker,
        stream_stop=args.frontend_stop_marker,
    )
    return SerialConfig(
        port=args.port, 
        baud_rate=args.baud, 
        current_switch=current_switch,
        frontend_markers=frontend_markers,
        data_format=args.data_format,
    )
