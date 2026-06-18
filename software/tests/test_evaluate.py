from __future__ import annotations

import csv
from itertools import islice
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)


def test_evaluate_chooses_last_emitted_snapshot(monkeypatch):
    from software.config.config import SimulationConfig
    from software.utils import evaluate_helpers as evaluate_helpers_module
    from software.utils.types import Snapshot

    class FakeBackbone:
        def __init__(self):
            self._count = 0

        def update(self, sample):
            self._count += 1
            if self._count == 2:
                return Snapshot(timestamp=sample[0], voltage=1.0, current_mA=10.0)
            if self._count == 4:
                return Snapshot(timestamp=sample[0], voltage=2.0, current_mA=10.0)
            return None

    monkeypatch.setattr(evaluate_helpers_module, "create_backbone", lambda *args, **kwargs: FakeBackbone())

    sim_config = SimulationConfig(sample_rate_hz=10.0, snapshot_window_s=1.0, snapshot_min_duration_s=0.1)
    samples = [
        (0.0, 0.1, 10.0),
        (0.1, 0.2, 10.0),
        (0.2, 0.3, 10.0),
        (0.3, 0.4, 10.0),
    ]

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    data = evaluate_helpers_module.evaluate_samples(samples, ["baseline"], sim_config, Args())
    decided = data["results"]["baseline"]["decided_snapshot"]

    assert decided is not None
    assert decided.voltage == 2.0


def test_evaluate_falls_back_to_final_sample_when_no_snapshot(monkeypatch):
    from software.config.config import SimulationConfig
    from software.utils import evaluate_helpers as evaluate_helpers_module

    class FakeBackbone:
        def update(self, sample):
            return None

    monkeypatch.setattr(evaluate_helpers_module, "create_backbone", lambda *args, **kwargs: FakeBackbone())

    sim_config = SimulationConfig(sample_rate_hz=10.0, snapshot_window_s=1.0, snapshot_min_duration_s=0.1, gain=2.0)
    samples = [
        (0.0, 0.1, 10.0),
        (0.1, 0.2, 10.0),
        (0.2, 0.3, 10.0),
    ]

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    data = evaluate_helpers_module.evaluate_samples(samples, ["baseline"], sim_config, Args())
    decided = data["results"]["baseline"]["decided_snapshot"]

    assert decided is not None
    assert decided.timestamp == 0.2
    assert decided.voltage == 0.3
    assert decided.current_mA == 10.0
    assert decided.resistance == 15.0


def test_evaluate_uses_gain_for_emitted_snapshot(monkeypatch):
    from software.config.config import SimulationConfig
    from software.utils import evaluate_helpers as evaluate_helpers_module
    from software.utils.types import Snapshot

    class FakeBackbone:
        def update(self, sample):
            return Snapshot(timestamp=sample[0], voltage=0.2, current_mA=10.0, resistance=10.0)

    monkeypatch.setattr(evaluate_helpers_module, "create_backbone", lambda *args, **kwargs: FakeBackbone())

    sim_config = SimulationConfig(sample_rate_hz=10.0, snapshot_window_s=1.0, snapshot_min_duration_s=0.1, gain=2.0)
    samples = [
        (0.0, 0.1, 10.0),
    ]

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    data = evaluate_helpers_module.evaluate_samples(samples, ["baseline"], sim_config, Args())
    decided = data["results"]["baseline"]["decided_snapshot"]

    assert decided is not None
    assert decided.resistance == 10.0


def test_backbone_styles_are_distinct():
    from software.utils.visualization import get_backbone_style

    first = get_backbone_style(0)
    second = get_backbone_style(1)

    assert first["color"] != second["color"]


def test_evaluate_single_dataset_smoke(tmp_path):
    from software.scripts.evaluate import evaluate_file, plot_results, write_summary
    from software.config.config import SimulationConfig

    csv_path = Path("software/output/testbench/stable20mA.csv")
    assert csv_path.exists(), "expected bundled testbench CSV fixture"

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    sim_config = SimulationConfig()
    data = evaluate_file(str(csv_path), ["baseline"], sim_config, Args())

    assert "results" in data
    assert "baseline" in data["results"]

    out_dir = tmp_path / "evaluate"
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_results(out_dir, str(csv_path), data, show=False)
    write_summary(out_dir, str(csv_path), data)

    assert (out_dir / "stable20mA.png").exists()
    metrics_path = out_dir / "stable20mA-metrics.csv"
    assert metrics_path.exists()

    with metrics_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    row = rows[0]
    assert row["backbone"] == "baseline"
    assert row["decided_snapshot"] == "*"
    assert row["decided_timestamp"]
    assert row["decided_voltage"]
    assert row["decided_current_mA"]


def test_evaluate_transient_plot_mode(tmp_path):
    from software.config.config import SimulationConfig
    from software.scripts.evaluate import evaluate_file, plot_results

    csv_path = Path("software/output/testbench/stable20mALONG.csv")
    assert csv_path.exists(), "expected bundled testbench CSV fixture"

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    sim_config = SimulationConfig()
    data = evaluate_file(str(csv_path), ["baseline", "stddev_window", "hysteresis"], sim_config, Args())

    out_dir = tmp_path / "evaluate-transient"
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_results(out_dir, str(csv_path), data, show=False, plot_mode="transient", animate=False)

    assert (out_dir / "stable20mALONG.png").exists()


def test_evaluate_transient_animation_screen(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    from software.config.config import SimulationConfig
    from software.scripts.evaluate import evaluate_file, plot_results

    monkeypatch.setattr(plt, "pause", lambda *args, **kwargs: None)

    csv_path = Path("software/output/testbench/stable20mALONG.csv")
    assert csv_path.exists(), "expected bundled testbench CSV fixture"

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    sim_config = SimulationConfig()
    data = evaluate_file(str(csv_path), ["baseline", "stddev_window", "hysteresis"], sim_config, Args())

    out_dir = tmp_path / "evaluate-transient-animated"
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_results(
        out_dir,
        str(csv_path),
        data,
        show=False,
        plot_mode="transient",
        animate=True,
        animation_output="screen",
        animation_fps=12,
    )

    assert (out_dir / "stable20mALONG.png").exists()


def test_evaluate_synthetic_source_smoke(tmp_path):
    from software.scripts.evaluate import evaluate_samples, plot_results, write_summary
    from software.config.config import SimulationConfig
    from software.data_source.dummy import dummy_voltage_generator

    class Args:
        hysteresis_enter = 1.0
        hysteresis_exit = 0.8

    sim_config = SimulationConfig(sample_rate_hz=20.0, max_measurement_s=1.0, snapshot_min_duration_s=0.5)
    samples = islice(dummy_voltage_generator(sim_config), int(sim_config.max_measurement_s * sim_config.sample_rate_hz))
    data = evaluate_samples(samples, ["baseline"], sim_config, Args())

    assert "results" in data
    assert "baseline" in data["results"]

    out_dir = tmp_path / "evaluate-synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_results(out_dir, "dummy", data, show=False)
    write_summary(out_dir, "dummy", data)

    metrics_path = out_dir / "dummy-metrics.csv"
    assert metrics_path.exists()
