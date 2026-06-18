"""Hysteresis-based snapshot backbone."""

from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Deque, Optional

from .base import BaseBackbone
from ..utils.math import compute_resistance_ohm
from ..utils.types import Sample, Snapshot


class HysteresisBackbone(BaseBackbone):
    """Emit a Snapshot when the sliding-mean crosses an upper trigger and remains
    stable for a dwell count; clear the state when the mean drops below the lower trigger.

    Uses an incremental sliding window (deque with running sums) so no full-array
    recomputation is needed.
    """

    def __init__(
        self,
        window_samples: int,
        enter_threshold: float,
        exit_threshold: float,
        min_stable_samples: int,
        min_recording_samples: int = 1,
        gain: float = 1.0,
    ) -> None:
        super().__init__(min_recording_samples=min_recording_samples)
        if window_samples < 1:
            raise ValueError("window_samples must be >= 1")
        if min_stable_samples < 1:
            raise ValueError("min_stable_samples must be >= 1")
        if exit_threshold > enter_threshold:
            raise ValueError("exit_threshold must be <= enter_threshold")

        self._window_samples = window_samples
        self._enter_threshold = enter_threshold
        self._exit_threshold = exit_threshold
        self._min_stable_samples = min_stable_samples
        self._gain = gain

        self._window: Deque[float] = deque(maxlen=window_samples)
        self._sum = 0.0
        self._sum_squares = 0.0

        # tracking stable dwell once above enter_threshold
        self._stable_count = 0
        self._in_snapshot = False

    def update(self, sample: Sample) -> Optional[Snapshot]:
        timestamp, voltage, current_mA = sample
        self._mark_sample()

        # adjust sums for sliding window
        if len(self._window) == self._window_samples:
            oldest = self._window[0]
            self._sum -= oldest
            self._sum_squares -= oldest * oldest

        self._window.append(voltage)
        self._sum += voltage
        self._sum_squares += voltage * voltage

        if len(self._window) < self._window_samples:
            return None

        mean = self._sum / self._window_samples
        variance = (self._sum_squares / self._window_samples) - (mean * mean)
        variance = max(0.0, variance)
        std_dev = sqrt(variance)

        if not self._in_snapshot:
            # waiting to enter snapshot region
            if mean >= self._enter_threshold:
                self._stable_count += 1
            else:
                self._stable_count = 0

            if self._stable_count >= self._min_stable_samples:
                if not self._has_min_recording():
                    return None
                self._in_snapshot = True
                resistance = compute_resistance_ohm(mean, current_mA, self._gain)
                return Snapshot(
                    timestamp=timestamp,
                    voltage=mean,
                    current_mA=current_mA,
                    resistance=resistance,
                    std_dev=std_dev,
                )
            return None

        # currently in snapshot; watch for exit condition
        if mean < self._exit_threshold:
            # exit immediately when falling below exit threshold
            self._in_snapshot = False
            self._stable_count = 0
            return None

        # remain in snapshot but do not re-emit on every frame
        return None

    def reset(self) -> None:
        self._window.clear()
        self._sum = 0.0
        self._sum_squares = 0.0
        self._stable_count = 0
        self._in_snapshot = False
        self._samples_seen = 0
