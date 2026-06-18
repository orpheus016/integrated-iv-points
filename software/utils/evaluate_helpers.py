"""Reusable helper functions for offline evaluation scripts.

This module centralizes the evaluation pipeline pieces so scripts can import
the same behavior without duplicating logic.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from ..data_source.dummy import dummy_voltage_generator
from ..data_source.settling import settling_signal_generator
from ..data_source.worst_case import worst_case_signal_generator
from .backbone_factory import create_backbone
from .csv_replay import csv_replay_reader
from .math import compute_resistance_ohm
from .visualization import render_evaluation_results
from .types import Sample, Snapshot


@dataclass
class Metrics:
    rmse: float
    mae: float
    maxabs: float


def compute_metrics(errors: List[float]) -> Metrics:
    if not errors:
        return Metrics(math.nan, math.nan, math.nan)
    mse = sum(e * e for e in errors) / len(errors)
    rmse = math.sqrt(mse)
    mae = sum(abs(e) for e in errors) / len(errors)
    maxabs = max(abs(e) for e in errors)
    return Metrics(rmse=rmse, mae=mae, maxabs=maxabs)


def build_source_iterator_eval(source: str, sim_config, args) -> Iterator[Sample]:
    if source == "csv":
        csv_path = getattr(args, "input", getattr(args, "csv_path", ""))
        return csv_replay_reader(csv_path, sample_rate_hz=sim_config.sample_rate_hz)

    if source == "dummy":
        return islice(dummy_voltage_generator(sim_config), max(1, int(sim_config.max_measurement_s * sim_config.sample_rate_hz)))

    if source == "settling":
        return islice(settling_signal_generator(sim_config), max(1, int(sim_config.max_measurement_s * sim_config.sample_rate_hz)))

    if source == "worst_case":
        return islice(worst_case_signal_generator(sim_config), max(1, int(sim_config.max_measurement_s * sim_config.sample_rate_hz)))

    raise ValueError(f"unsupported evaluation source: {source}")


def _build_fallback_snapshot(times: List[float], voltages: List[float], currents: List[float], gain: float) -> Optional[Snapshot]:
    if not times:
        return None
    timestamp = times[-1]
    voltage = voltages[-1]
    current_mA = currents[-1]
    resistance = compute_resistance_ohm(voltage, current_mA, gain)
    return Snapshot(
        timestamp=timestamp,
        voltage=voltage,
        current_mA=current_mA,
        resistance=resistance,
        std_dev=None,
        stage=None,
    )


def _select_decided_snapshot(snapshots: List[Snapshot], times: List[float], voltages: List[float], currents: List[float], gain: float) -> Optional[Snapshot]:
    if snapshots:
        return snapshots[-1]
    return _build_fallback_snapshot(times, voltages, currents, gain)


def evaluate_samples(samples: Iterable[Sample], backbones: Iterable[str], sim_config, args) -> dict:
    times: List[float] = []
    voltages: List[float] = []
    currents: List[float] = []
    for t, v, i in samples:
        times.append(t)
        voltages.append(v)
        currents.append(i)

    results = {}
    for bname in backbones:
        bb = create_backbone(bname, sim_config, args)
        snapshots: List[Snapshot] = []
        window_samples = max(1, int(sim_config.snapshot_window_s * sim_config.sample_rate_hz))
        for t, v, i in zip(times, voltages, currents):
            snap = bb.update((t, v, i))
            if snap is not None:
                snapshots.append(snap)

        if hasattr(bb, "best_snapshot") and bb.best_snapshot is not None:
            decided_snapshot = bb.best_snapshot
        else:
            decided_snapshot = _select_decided_snapshot(snapshots, times, voltages, currents, sim_config.gain)

        errors: List[float] = []
        refs: List[float] = []
        if decided_snapshot is not None:
            candidate_snapshots = [decided_snapshot]
        else:
            candidate_snapshots = []

        for snap in candidate_snapshots:
            idx = min(range(len(times)), key=lambda k: abs(times[k] - snap.timestamp))
            start = max(0, idx - window_samples + 1)
            ref_mean = sum(voltages[start: idx + 1]) / max(1, idx - start + 1)
            refs.append(ref_mean)
            errors.append(snap.voltage - ref_mean)

        metrics = compute_metrics(errors)
        results[bname] = {
            "snapshots": snapshots,
            "decided_snapshot": decided_snapshot,
            "metrics": metrics,
            "refs": refs,
        }
    return {"times": times, "voltages": voltages, "currents": currents, "results": results}


def evaluate_file(csv_path: str, backbones: Iterable[str], sim_config, args) -> dict:
    return evaluate_samples(csv_replay_reader(csv_path, sample_rate_hz=sim_config.sample_rate_hz), backbones, sim_config, args)


def plot_results(base_out: Path, name: str, data: dict, show: bool = False, plot_mode: str = "comparison", animate: bool = False, animation_output: str = "screen", animation_fps: int = 12) -> None:
    render_evaluation_results(
        base_out,
        name,
        data,
        show=show,
        plot_mode=plot_mode,
        animate=animate,
        animation_output=animation_output,
        animation_fps=animation_fps,
    )


def write_summary(base_out: Path, name: str, data: dict) -> None:
    out_csv = base_out / f"{Path(name).stem}-metrics.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "backbone",
            "decided_snapshot",
            "decided_timestamp",
            "decided_voltage",
            "decided_current_mA",
            "decided_resistance",
            "decided_std_dev",
            "decided_stage",
            "rmse",
            "mae",
            "maxabs",
            "num_snapshots",
        ])
        for bname, info in data["results"].items():
            m = info["metrics"]
            decided_snapshot: Optional[Snapshot] = info.get("decided_snapshot")
            if decided_snapshot is None:
                decided_values = ["", "", "", "", "", "", ""]
                selected_marker = ""
            else:
                selected_marker = "*"
                decided_values = [
                    f"{decided_snapshot.timestamp:.6f}",
                    f"{decided_snapshot.voltage:.8f}",
                    f"{decided_snapshot.current_mA:.8f}",
                    "" if decided_snapshot.resistance is None else f"{decided_snapshot.resistance:.8f}",
                    "" if decided_snapshot.std_dev is None else f"{decided_snapshot.std_dev:.8f}",
                    "" if decided_snapshot.stage is None else decided_snapshot.stage,
                ]
            writer.writerow([
                bname,
                selected_marker,
                *decided_values,
                m.rmse,
                m.mae,
                m.maxabs,
                len(info["snapshots"]),
            ])
