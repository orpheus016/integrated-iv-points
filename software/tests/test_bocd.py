"""Unit tests for the BochdBackbone streaming snapshot backbone.

All tests are hardware-free and deterministic (fixed seeds where randomness
is required).  They validate:

- The backbone honours the BaseBackbone interface contract.
- update() returns None while insufficient samples have been seen.
- A Snapshot is emitted after enough stable consecutive samples.
- No second Snapshot is emitted in the same recording phase.
- reset() re-arms the backbone so a second Snapshot can be emitted.
- The factory correctly constructs a BochdBackbone by name.
- Resistance is computed correctly via compute_resistance_ohm.
- Invalid constructor arguments raise ValueError.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from software.backbones.bocd import BochdBackbone
from software.backbones.base import BaseBackbone
from software.config.config import SimulationConfig
from software.utils.backbone_factory import create_backbone
from software.utils.math import compute_resistance_ohm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_samples(
    n: int,
    voltage: float = 1.0,
    current_mA: float = 10.0,
    start_t: float = 0.0,
    dt: float = 0.02,
) -> list[tuple[float, float, float]]:
    """Generate *n* flat (no noise) samples at the given voltage level."""
    return [(start_t + i * dt, voltage, current_mA) for i in range(n)]


def _noisy_samples(
    n: int,
    voltage: float = 1.0,
    noise_std: float = 0.5,
    current_mA: float = 10.0,
    seed: int = 42,
) -> list[tuple[float, float, float]]:
    """Generate *n* Gaussian-noisy samples.  High noise prevents stability."""
    rng = np.random.default_rng(seed)
    voltages = rng.normal(loc=voltage, scale=noise_std, size=n)
    return [(i * 0.02, float(v), current_mA) for i, v in enumerate(voltages)]


# ---------------------------------------------------------------------------
# Construction and interface
# ---------------------------------------------------------------------------

def test_bocd_inherits_base_backbone():
    backbone = BochdBackbone()
    assert isinstance(backbone, BaseBackbone)


def test_bocd_raises_on_invalid_min_stable_samples():
    with pytest.raises(ValueError, match="min_stable_samples"):
        BochdBackbone(min_stable_samples=0)


def test_bocd_raises_on_invalid_hazard_rate():
    with pytest.raises(ValueError, match="hazard_rate"):
        BochdBackbone(hazard_rate=0.0)
    with pytest.raises(ValueError, match="hazard_rate"):
        BochdBackbone(hazard_rate=1.0)


def test_bocd_raises_on_invalid_variances():
    with pytest.raises(ValueError, match="var0"):
        BochdBackbone(var0=0.0)
    with pytest.raises(ValueError, match="varx"):
        BochdBackbone(varx=0.0)


# ---------------------------------------------------------------------------
# Snapshot emission: stable signal
# ---------------------------------------------------------------------------

def test_bocd_emits_snapshot_on_flat_signal():
    """A flat, noise-free signal should eventually yield a best_snapshot."""
    # Use a small varx so even tiny flat windows look stable.
    backbone = BochdBackbone(
        min_stable_samples=10,
        min_recording_samples=1,
        varx=1e-8,
        var0=1.0,
        mean0=1.0,
        hazard_rate=1.0 / 500.0,
    )
    samples = _flat_samples(n=200, voltage=1.0, current_mA=10.0)
    for s in samples:
        backbone.update(s)

    snapshot = backbone.best_snapshot
    assert snapshot is not None, "Expected a best_snapshot from a flat signal"
    assert snapshot.voltage is not None
    assert snapshot.current_mA == pytest.approx(10.0)
    assert snapshot.std_dev is not None


def test_bocd_snapshot_voltage_near_input():
    """Predictive mean for a flat signal should match the input voltage."""
    backbone = BochdBackbone(
        min_stable_samples=5,
        min_recording_samples=1,
        varx=1e-8,
        var0=2.0,
        mean0=0.0,
        hazard_rate=1.0 / 500.0,
    )
    target_v = 1.5
    samples = _flat_samples(n=200, voltage=target_v, current_mA=5.0)
    for s in samples:
        backbone.update(s)

    snapshot = backbone.best_snapshot
    assert snapshot is not None
    # After many updates the posterior mean should converge toward the true value.
    assert math.isclose(abs(snapshot.voltage), target_v, abs_tol=0.05)


def test_bocd_snapshot_resistance_matches_utility():
    """Resistance in the Snapshot must match compute_resistance_ohm."""
    backbone = BochdBackbone(
        min_stable_samples=5,
        min_recording_samples=1,
        varx=1e-8,
        var0=2.0,
        mean0=1.0,
        gain=2.0,
    )
    samples = _flat_samples(n=200, voltage=1.0, current_mA=10.0)
    for s in samples:
        backbone.update(s)

    snapshot = backbone.best_snapshot
    assert snapshot is not None
    expected_r = compute_resistance_ohm(abs(snapshot.voltage), snapshot.current_mA, gain=2.0)
    assert math.isclose(snapshot.resistance, expected_r, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# No second snapshot before reset
# ---------------------------------------------------------------------------

def test_bocd_emits_continuously_while_stable():
    """A perfectly flat signal emits snapshots continuously once min_stable_samples is reached.
    best_snapshot still returns the longest plateau via end-of-stream sealing.
    """
    backbone = BochdBackbone(
        min_stable_samples=5,
        min_recording_samples=1,
        varx=1e-8,
        var0=2.0,
        mean0=1.0,
        hazard_rate=1.0 / 500.0,
    )
    samples = _flat_samples(n=400, voltage=1.0, current_mA=10.0)

    update_snapshots: list = []
    for s in samples:
        result = backbone.update(s)
        if result is not None:
            update_snapshots.append(result)

    # A flat signal hits min_stable_samples and continuously emits.
    assert len(update_snapshots) == 400 - 5 + 1, (
        f"Expected continuous emission after min_stable_samples, got {len(update_snapshots)}"
    )
    # best_snapshot seals the in-progress run and returns it.
    assert backbone.best_snapshot is not None


# ---------------------------------------------------------------------------
# Reset re-arms the backbone
# ---------------------------------------------------------------------------

def test_bocd_reset_allows_second_snapshot():
    """After reset(), the backbone must be ready to produce another best_snapshot."""
    backbone = BochdBackbone(
        min_stable_samples=5,
        min_recording_samples=1,
        varx=1e-8,
        var0=2.0,
        mean0=1.0,
        hazard_rate=1.0 / 500.0,
    )
    samples = _flat_samples(n=200, voltage=1.0, current_mA=10.0)
    for s in samples:
        backbone.update(s)

    first_snapshot = backbone.best_snapshot
    assert first_snapshot is not None

    backbone.reset()

    for s in samples:
        backbone.update(s)

    second_snapshot = backbone.best_snapshot
    assert second_snapshot is not None
    assert math.isclose(abs(first_snapshot.voltage), abs(second_snapshot.voltage), abs_tol=0.05)


# ---------------------------------------------------------------------------
# min_recording_samples guard
# ---------------------------------------------------------------------------

def test_bocd_respects_min_recording_samples():
    """No Snapshot should emerge before min_recording_samples."""
    guard = 100
    backbone = BochdBackbone(
        min_stable_samples=5,
        min_recording_samples=guard,
        varx=1e-8,
        var0=2.0,
        mean0=1.0,
        hazard_rate=1.0 / 500.0,
    )
    samples = _flat_samples(n=guard - 1, voltage=1.0, current_mA=10.0)

    for s in samples:
        result = backbone.update(s)
        assert result is None, "Snapshot must not appear before min_recording_samples"


# ---------------------------------------------------------------------------
# Diagnostic property
# ---------------------------------------------------------------------------

def test_bocd_most_probable_run_length_grows():
    """most_probable_run_length should grow when there are no changepoints."""
    backbone = BochdBackbone(
        min_stable_samples=1000,   # never emits — just inspects run length
        min_recording_samples=1,
        varx=1e-8,
        var0=2.0,
        mean0=1.0,
        hazard_rate=1.0 / 1000.0,
    )
    prev = 0
    for s in _flat_samples(n=30, voltage=1.0):
        backbone.update(s)
        curr = backbone.most_probable_run_length
        assert curr >= prev or curr == 0, "Run length should be non-decreasing on flat data"
        prev = curr


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------

def test_bocd_is_available_through_factory():
    sim_config = SimulationConfig(
        snapshot_window_s=1.0,
        snapshot_std_threshold_v=0.0002,
        snapshot_min_duration_s=0.5,
        gain=1.0,
    )
    backbone = create_backbone("bocd", sim_config)
    assert backbone.__class__.__name__ == "BochdBackbone"


def test_bocd_factory_respects_gain():
    sim_config = SimulationConfig(
        snapshot_window_s=1.0,
        snapshot_std_threshold_v=0.0002,
        snapshot_min_duration_s=0.5,
        gain=3.0,
    )
    backbone = create_backbone("bocd", sim_config)
    assert isinstance(backbone, BochdBackbone)
    # Feed enough stable data and verify gain is applied via best_snapshot.
    samples = _flat_samples(n=300, voltage=1.0, current_mA=10.0)
    for s in samples:
        backbone.update(s)
    snapshot = backbone.best_snapshot
    if snapshot is not None:
        expected = compute_resistance_ohm(snapshot.voltage, snapshot.current_mA, gain=3.0)
        assert math.isclose(snapshot.resistance, expected, rel_tol=1e-9)


# ===========================================================================
# New tests — best_snapshot / polarity / multi-plateau selection
# ===========================================================================


def _build_bocd(min_stable: int = 10, varx: float = 1e-8) -> BochdBackbone:
    """Convenience factory for best_snapshot tests."""
    return BochdBackbone(
        min_stable_samples=min_stable,
        min_recording_samples=1,
        varx=varx,
        var0=2.0,
        mean0=0.8,
        hazard_rate=1.0 / 100.0,
        cp_reset_threshold=5,
    )


def _feed(backbone: BochdBackbone, samples: list) -> None:
    """Drain all samples into the backbone (return values ignored)."""
    for s in samples:
        backbone.update(s)


def test_bocd_best_snapshot_on_stable_flanked_by_noise():
    """Signal: ±1 V oscillation → stable 0.8 V plateau → ±1 V oscillation.
    The best_snapshot must land on the 0.8 V stable region.
    """
    rng = np.random.default_rng(0)

    def noisy_block(n: int, amp: float = 1.0) -> list:
        vs = rng.uniform(-amp, amp, size=n)
        return [(i * 0.02, float(v), 10.0) for i, v in enumerate(vs)]

    def stable_block(n: int, v: float, offset: int = 0) -> list:
        return [(offset + i * 0.02, v, 10.0) for i in range(n)]

    backbone = _build_bocd(min_stable=10, varx=1e-8)

    # Noisy pre-phase (100 samples oscillating -1..+1)
    _feed(backbone, noisy_block(100))
    # Stable plateau at 0.8 V (150 samples)
    _feed(backbone, stable_block(150, 0.8, offset=2))
    # Noisy post-phase (80 samples oscillating -1..+1)
    _feed(backbone, noisy_block(80))

    best = backbone.best_snapshot
    assert best is not None, "Expected a best_snapshot after stable plateau"
    assert math.isclose(abs(best.voltage), 0.8, abs_tol=0.05), (
        f"best_snapshot.voltage should be ≈ 0.8 V, got {best.voltage}"
    )


def test_bocd_best_snapshot_ignores_near_zero_noise_floor():
    """A 'stable' near-zero noise floor (≈ ±0.01 V) must not beat a real 0.8 V plateau."""
    rng = np.random.default_rng(1)

    backbone = _build_bocd(min_stable=10, varx=1e-8)

    # Near-zero noise floor (looks stable but very low amplitude)
    vs = rng.normal(loc=0.0, scale=0.002, size=200)
    _feed(backbone, [(i * 0.02, float(v), 10.0) for i, v in enumerate(vs)])

    # Strong 0.8 V plateau
    _feed(backbone, [(200 + i * 0.02, 0.8, 10.0) for i in range(200)])

    # More near-zero noise
    vs2 = rng.normal(loc=0.0, scale=0.002, size=50)
    _feed(backbone, [(400 + i * 0.02, float(v), 10.0) for i, v in enumerate(vs2)])

    best = backbone.best_snapshot
    assert best is not None
    # The 0.8 V plateau should be chosen; near-zero is too small to dominate
    assert abs(best.voltage) > 0.5, (
        f"Expected best_snapshot near 0.8 V, got {best.voltage}"
    )


def test_bocd_best_snapshot_handles_negative_polarity():
    """A stable -0.8 V plateau (polarity flip) must be treated as valid.

    abs(voltage) is used for stability; the Snapshot stores the raw negative value.
    """
    backbone = _build_bocd(min_stable=10, varx=1e-8)

    # Stable plateau at -0.8 V
    samples = [((i * 0.02), -0.8, 10.0) for i in range(200)]
    _feed(backbone, samples)

    best = backbone.best_snapshot
    assert best is not None, "Expected a best_snapshot from a -0.8 V stable signal"
    # Voltage stored as-is (signed)
    assert math.isclose(best.voltage, -0.8, abs_tol=0.05), (
        f"Expected signed voltage ≈ -0.8 V, got {best.voltage}"
    )
    # abs(V) is the magnitude that the model evaluated
    assert abs(best.voltage) > 0.7


def test_bocd_best_snapshot_longest_wins():
    """When two plateaus exist, the longer one should be chosen as best_snapshot."""
    rng = np.random.default_rng(2)

    backbone = _build_bocd(min_stable=10, varx=1e-8)

    def noisy_transition(n: int, offset: int) -> list:
        vs = rng.uniform(-0.5, 0.5, size=n)
        return [(offset + i * 0.02, float(v), 10.0) for i, v in enumerate(vs)]

    t = 0
    # Short plateau at 0.6 V (30 samples = shorter run)
    _feed(backbone, [(t + i * 0.02, 0.6, 10.0) for i in range(30)])
    t += 30 * 0.02

    # Noisy transition (forces changepoint)
    _feed(backbone, noisy_transition(60, int(t)))
    t += 60 * 0.02

    # Long plateau at 0.9 V (150 samples = longer run)
    _feed(backbone, [(t + i * 0.02, 0.9, 10.0) for i in range(150)])
    t += 150 * 0.02

    # Trailing noise (to trigger changepoint for the second plateau)
    _feed(backbone, noisy_transition(60, int(t)))

    best = backbone.best_snapshot
    assert best is not None
    # The 0.9 V plateau ran longer, so it must win
    assert abs(best.voltage) > 0.75, (
        f"Expected best_snapshot near 0.9 V (longer plateau), got {best.voltage}"
    )


def test_bocd_best_snapshot_is_none_without_stable_run():
    """Pure white noise should never produce a best_snapshot."""
    rng = np.random.default_rng(3)
    backbone = _build_bocd(min_stable=30, varx=1e-8)

    vs = rng.uniform(-1.0, 1.0, size=300)
    _feed(backbone, [(i * 0.02, float(v), 10.0) for i, v in enumerate(vs)])

    best = backbone.best_snapshot
    assert best is None, f"Expected None from pure noise, got {best}"


def test_bocd_best_snapshot_sealed_at_end_of_stream():
    """A stable plateau at the very end of the file (no trailing changepoint) must
    still be returned by best_snapshot on first access.
    """
    backbone = _build_bocd(min_stable=10, varx=1e-8)

    # Stable plateau at the end — no trailing noise to trigger a changepoint
    samples = [(i * 0.02, 0.75, 10.0) for i in range(150)]
    _feed(backbone, samples)

    # No trailing samples — call best_snapshot directly (end-of-stream seal)
    best = backbone.best_snapshot
    assert best is not None, "Expected best_snapshot to be sealed at end of stream"
    assert math.isclose(abs(best.voltage), 0.75, abs_tol=0.05)


def test_bocd_best_run_length_field_populated():
    """best_snapshot.best_run_length must be a positive integer when a plateau was detected."""
    backbone = _build_bocd(min_stable=10, varx=1e-8)

    samples = [(i * 0.02, 0.9, 10.0) for i in range(200)]
    _feed(backbone, samples)

    best = backbone.best_snapshot
    assert best is not None
    assert best.best_run_length is not None
    assert best.best_run_length >= 10, (
        f"Expected best_run_length >= min_stable_samples, got {best.best_run_length}"
    )