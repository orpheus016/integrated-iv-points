import math

from software.backbones.running_stat import RunningStatBackbone
from software.config.config import SimulationConfig
from software.utils.backbone_factory import create_backbone
from software.utils.math import compute_resistance_ohm


def test_running_stat_emits_snapshot_after_stable_window():
    backbone = RunningStatBackbone(window_samples=4, std_threshold=0.02, min_stable_samples=2, gain=2.0)

    samples = [
        (0.0, 0.9, 5.0),
        (0.1, 1.1, 5.0),
        (0.2, 0.98, 5.0),
        (0.3, 1.02, 5.0),
        (0.4, 1.01, 5.0),
        (0.5, 1.00, 5.0),
        (0.6, 1.005, 5.0),
    ]

    snapshot = None
    for sample in samples:
        snapshot = backbone.update(sample)

    assert snapshot is not None
    assert 0.95 < snapshot.voltage < 1.15
    expected_resistance = compute_resistance_ohm(snapshot.voltage, snapshot.current_mA, gain=2.0)
    assert math.isclose(snapshot.resistance, expected_resistance, rel_tol=1e-6)
    assert snapshot.std_dev is not None
    assert snapshot.std_dev <= 0.02


def test_running_stat_reset_allows_a_second_snapshot():
    backbone = RunningStatBackbone(window_samples=3, std_threshold=0.02, min_stable_samples=1)

    stable_samples = [
        (0.0, 1.0, 10.0),
        (0.1, 1.0, 10.0),
        (0.2, 1.01, 10.0),
    ]

    first_snapshot = None
    for sample in stable_samples:
        first_snapshot = backbone.update(sample)

    assert first_snapshot is not None

    backbone.reset()

    second_snapshot = None
    for sample in stable_samples:
        second_snapshot = backbone.update(sample)

    assert second_snapshot is not None
    assert math.isclose(first_snapshot.voltage, second_snapshot.voltage, rel_tol=1e-6)


def test_running_stat_is_available_through_factory():
    sim_config = SimulationConfig(snapshot_window_s=1.0, snapshot_std_threshold_v=0.02, snapshot_min_duration_s=0.2, gain=2.0)
    backbone = create_backbone("running_stat", sim_config)

    assert backbone.__class__.__name__ == "RunningStatBackbone"