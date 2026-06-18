import math

from software.backbones.baseline import BaselineBackbone
from software.utils.math import compute_resistance_ohm


def test_baseline_emits_snapshot_after_stable_window():
    b = BaselineBackbone(window_samples=4, std_threshold=0.02, min_stable_samples=2, gain=2.0)

    # values hover then stabilize around ~1.0
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
    for s in samples:
        snapshot = b.update(s)

    assert snapshot is not None
    # mean should be near 1.01 or 1.00 depending on which window produced the snapshot
    assert 0.95 < snapshot.voltage < 1.15
    expected = compute_resistance_ohm(snapshot.voltage, snapshot.current_mA, gain=2.0)
    assert math.isclose(snapshot.resistance, expected, rel_tol=1e-6)
