import math


def test_compute_resistance_ohm_applies_gain_correction():
    from software.utils.math import compute_resistance_ohm

    resistance = compute_resistance_ohm(0.2, 10.0, gain=2.0)

    assert resistance is not None
    assert math.isclose(resistance, 10.0, rel_tol=1e-9)


def test_compute_resistance_ohm_rejects_nonpositive_gain():
    from software.utils.math import compute_resistance_ohm

    assert compute_resistance_ohm(0.2, 10.0, gain=0.0) is None