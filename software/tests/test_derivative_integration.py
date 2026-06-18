"""Tests for Derivative Integration backbone."""

import pytest

from software.backbones.derivative_integration import DerivativeIntegrationBackbone


def test_derivative_integration_baseline() -> None:
    # A small steady signal shouldn't trigger integration thresholds
    # dt=0.01, it=0.05
    backbone = DerivativeIntegrationBackbone(
        window_samples=5,
        derivative_threshold=0.01,
        integration_threshold=0.05,
        min_stable_samples=3,
        min_recording_samples=1,
        leakage_factor=0.9,
        iir_window=2,
    )

    # 1st sample, initializes average
    snapshot = backbone.update((0.0, 1.0, 4.0))
    assert snapshot is None

    # Small variations below dt=0.01
    for i in range(1, 10):
        val = 1.0 + (i % 2) * 0.005
        snapshot = backbone.update((i * 0.1, val, 4.0))
        if snapshot is not None:
            assert snapshot.voltage == pytest.approx(1.0, abs=0.05)
            break
    else:
        pytest.fail("Snapshot not emitted")


def test_derivative_integration_transient() -> None:
    backbone = DerivativeIntegrationBackbone(
        window_samples=5,
        derivative_threshold=0.01,
        integration_threshold=0.05,
        min_stable_samples=3,
        min_recording_samples=1,
        leakage_factor=0.9,
        iir_window=2,
    )

    # Steady state
    backbone.update((0.0, 1.0, 4.0))
    backbone.update((0.1, 1.0, 4.0))
    
    # Large transient jumps
    backbone.update((0.2, 1.5, 4.0))
    snapshot = backbone.update((0.3, 2.0, 4.0))
    assert snapshot is None  # Should be actively tracking transient

    # Stabilize
    for i in range(4, 60):
        snapshot = backbone.update((i * 0.1, 2.0, 4.0))
        if snapshot is not None:
            break
    
    assert snapshot is not None
    assert snapshot.voltage == pytest.approx(2.0, abs=0.05)

def test_derivative_integration_reset() -> None:
    backbone = DerivativeIntegrationBackbone(
        window_samples=5,
        derivative_threshold=0.01,
        integration_threshold=0.05,
        min_stable_samples=3,
    )

    # Initialize
    backbone.update((0.0, 1.0, 4.0))
    
    # Reset
    backbone.reset()
    
    assert backbone._avg_prev is None
    assert backbone._stable_count == 0
    assert len(backbone._window) == 0
