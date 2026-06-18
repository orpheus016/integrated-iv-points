import math

from software.backbones.hysteresis import HysteresisBackbone


def test_hysteresis_emits_snapshot_after_dwell():
    hb = HysteresisBackbone(window_samples=3, enter_threshold=1.0, exit_threshold=0.8, min_stable_samples=2)

    samples = [
        (0.0, 0.5, 10.0),
        (0.1, 0.6, 10.0),
        (0.2, 1.2, 10.0),
        (0.3, 1.1, 10.0),
        (0.4, 1.05, 10.0),
        (0.5, 1.15, 10.0),
    ]

    snapshot = None
    for s in samples:
        snapshot = hb.update(s)

    assert snapshot is not None, "Expected a snapshot after stable dwell"
    assert math.isclose(snapshot.voltage, (1.2 + 1.1 + 1.05) / 3.0, rel_tol=1e-3) or math.isclose(
        snapshot.voltage, (1.1 + 1.05 + 1.15) / 3.0, rel_tol=1e-3
    )
    assert snapshot.current_mA == 10.0
