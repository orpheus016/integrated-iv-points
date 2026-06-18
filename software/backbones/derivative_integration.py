"""Derivative integration backbone.

Algorithm reference: Derivative Integration Algorithm for Proximity Sensing,
David Wang, TI, 2015 (internal reference document).
"""

from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Deque, Optional

import numpy as np

from .base import BaseBackbone
from ..utils.math import compute_resistance_ohm
from ..utils.types import Sample, Snapshot


def analyze_trace_vectorized(raw_signals: np.ndarray, dt: float, it: float, l: float, n: int = 16):
    # Vectorized IIR Filter equivalent via scipy lfilter or manual iteration
    # Since IIR relies strictly on previous step, a sequential loop over tracking arrays is required:
    samples = len(raw_signals)
    smoothed = np.zeros(samples)
    integrals = np.zeros(samples)
    detections = np.zeros(samples, dtype=bool)
    
    # Initialize
    smoothed[0] = raw_signals[0]
    
    for i in range(1, samples):
        # IIR Equation
        smoothed[i] = ((smoothed[i-1] * n) - smoothed[i-1] + raw_signals[i]) / n
        
        # Derivative
        d = smoothed[i] - smoothed[i-1]
        
        # Integrate
        if abs(d) > dt:
            integrals[i] = integrals[i-1] + d
        else:
            integrals[i] = integrals[i-1]
            
        # Threshold Check & Leak
        if abs(integrals[i]) >= it:
            detections[i] = True
        else:
            integrals[i] = integrals[i] * l
            detections[i] = False
            
    return detections, smoothed, integrals


class DerivativeIntegrationBackbone(BaseBackbone):
    """Implement incremental snapshot detection using a Derivative Integration strategy.
    
    This detector integrates large derivatives (transients) and applies a leakage factor 
    when the derivative is small. When the integral falls below the integration threshold, 
    the signal is considered stable.
    """

    def __init__(
        self,
        window_samples: int,
        derivative_threshold: float,
        integration_threshold: float,
        min_stable_samples: int,
        min_recording_samples: int = 1,
        leakage_factor: float = 0.99,
        iir_window: int = 16,
        gain: float = 1.0,
    ) -> None:
        super().__init__(min_recording_samples=min_recording_samples)
        
        if window_samples < 2:
            raise ValueError("window_samples must be >= 2")
        if min_stable_samples < 1:
            raise ValueError("min_stable_samples must be >= 1")

        self._window_samples = window_samples
        self._dt = derivative_threshold
        self._it = integration_threshold
        self._min_stable_samples = min_stable_samples
        self._l = leakage_factor
        self._n = iir_window
        self._gain = gain

        # Internal state tracking for DI
        self._avg_prev: Optional[float] = None
        self._x_prev: Optional[float] = None
        self._i_prev = 0.0
        
        # Tracking for stability
        self._stable_count = 0
        self._snapshot_emitted = False
        
        # For standard deviation reporting
        self._window: Deque[float] = deque(maxlen=window_samples)
        self._sum = 0.0
        self._sum_squares = 0.0

    def update(self, sample: Sample) -> Optional[Snapshot]:
        timestamp, voltage, current_mA = sample
        self._mark_sample()

        # Update std_dev window using raw voltage
        if len(self._window) == self._window_samples:
            oldest = self._window[0]
            self._sum -= oldest
            self._sum_squares -= oldest * oldest

        self._window.append(voltage)
        self._sum += voltage
        self._sum_squares += voltage * voltage

        # Step 1: IIR Filter Preprocessing (Page 4, Eq 1)
        if self._avg_prev is None:
            self._avg_prev = voltage
            self._x_prev = voltage
            return None
        
        avg_curr = ((self._avg_prev * self._n) - self._avg_prev + voltage) / self._n
        
        # Step 2: Compute Derivative (Page 2)
        d_curr = avg_curr - self._x_prev  # type: ignore
        
        # Step 3: Evaluate Derivative Threshold (with sign retention)
        if abs(d_curr) > self._dt:
            i_curr = self._i_prev + d_curr
        else:
            # Apply Leakage Factor when below derivative threshold to dissipate transient state
            i_curr = self._i_prev * self._l
            
        # Step 4: Evaluate Integration Threshold
        if abs(i_curr) >= self._it:
            transient_detected = True
        else:
            transient_detected = False
            
        # Update historical state markers
        self._i_prev = i_curr
            
        # Update historical state markers
        self._x_prev = avg_curr
        self._avg_prev = avg_curr

        # Evaluate stability
        if transient_detected:
            self._stable_count = 0
            self._snapshot_emitted = False
        else:
            self._stable_count += 1
            
        if self._stable_count < self._min_stable_samples or not self._has_min_recording() or self._snapshot_emitted:
            return None

        # Calculate standard deviation if window is reasonably filled
        num_samples = len(self._window)
        mean = self._sum / num_samples
        variance = (self._sum_squares / num_samples) - (mean * mean)
        variance = max(0.0, variance)
        std_dev = sqrt(variance)

        # We use the smoothed value `avg_curr` for calculating resistance
        resistance = compute_resistance_ohm(avg_curr, current_mA, self._gain)

        self._snapshot_emitted = True
        return Snapshot(
            timestamp=timestamp,
            voltage=avg_curr,
            current_mA=current_mA,
            resistance=resistance,
            std_dev=std_dev,
        )

    def reset(self) -> None:
        self._avg_prev = None
        self._x_prev = None
        self._i_prev = 0.0
        self._stable_count = 0
        self._snapshot_emitted = False
        self._samples_seen = 0
        self._window.clear()
        self._sum = 0.0
        self._sum_squares = 0.0