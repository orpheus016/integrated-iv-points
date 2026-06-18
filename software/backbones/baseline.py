"""Baseline backbone: sliding-window stddev + dwell detection."""

from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Deque, Optional

from .base import BaseBackbone
from ..utils.math import compute_resistance_ohm
from ..utils.types import Sample, Snapshot


class BaselineBackbone(BaseBackbone):
    """Emit a Snapshot when a sliding window's stddev stays below a threshold
    for a configured dwell count.

    The backbone maintains a rolling buffer (deque) and running sums so that
    per-sample updates are O(1) and no full-array recomputation occurs.
    """

    def __init__(
        self,
        window_samples: int,
        std_threshold: float,
        min_stable_samples: int,
        min_recording_samples: int = 1,
        gain: float = 1.0,
    ) -> None:
        super().__init__(min_recording_samples=min_recording_samples)
        if window_samples < 2:
            raise ValueError("window_samples must be >= 2")
        if min_stable_samples < 1:
            raise ValueError("min_stable_samples must be >= 1")
        if std_threshold < 0.0:
            raise ValueError("std_threshold must be >= 0")

        self._window_samples = window_samples
        self._std_threshold = std_threshold
        self._min_stable_samples = min_stable_samples
        self._gain = gain

        self._window: Deque[float] = deque(maxlen=window_samples)
        self._sum = 0.0
        self._sum_squares = 0.0
        self._stable_count = 0
        self._snapshot_emitted = False

    def update(self, sample: Sample) -> Optional[Snapshot]:
        timestamp, voltage, current_mA = sample
        self._mark_sample()

        # remove oldest contribution if window full
        if len(self._window) == self._window_samples:
            oldest = self._window[0]
            self._sum -= oldest
            self._sum_squares -= oldest * oldest

        # append new value
        self._window.append(voltage)
        self._sum += voltage
        self._sum_squares += voltage * voltage

        # not enough samples yet
        if len(self._window) < self._window_samples:
            self._stable_count = 0
            self._snapshot_emitted = False
            return None

        mean = self._sum / self._window_samples
        variance = (self._sum_squares / self._window_samples) - (mean * mean)
        variance = max(0.0, variance)
        std_dev = sqrt(variance)

        if std_dev <= self._std_threshold:
            self._stable_count += 1
        else:
            self._stable_count = 0
            self._snapshot_emitted = False

        if self._stable_count < self._min_stable_samples or not self._has_min_recording() or self._snapshot_emitted:
            return None

        resistance = compute_resistance_ohm(mean, current_mA, self._gain)

        # emit snapshot (timestamp of latest sample)
        self._snapshot_emitted = True
        return Snapshot(
            timestamp=timestamp,
            voltage=mean,
            current_mA=current_mA,
            resistance=resistance,
            std_dev=std_dev,
        )

    def reset(self) -> None:
        self._window.clear()
        self._sum = 0.0
        self._sum_squares = 0.0
        self._stable_count = 0
        self._snapshot_emitted = False
        self._samples_seen = 0
