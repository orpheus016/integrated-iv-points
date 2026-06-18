"""Signal filtering utilities."""

from __future__ import annotations

from collections import deque
from typing import Deque


class MovingAverageFilter:
    """O(1) moving average filter using a fixed-size deque and running sum."""

    def __init__(self, window_size: int) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self._window_size = window_size
        self._values: Deque[float] = deque(maxlen=window_size)
        self._sum = 0.0

    def update(self, value: float) -> float:
        if len(self._values) == self._window_size:
            self._sum -= self._values[0]
        self._values.append(value)
        self._sum += value
        return self._sum / len(self._values)

    def reset(self) -> None:
        self._values.clear()
        self._sum = 0.0


class LowPassFilter:
    """Single-pole low-pass filter: y[n] = a*x[n] + (1-a)*y[n-1]."""

    def __init__(self, alpha: float) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0.0, 1.0]")
        self._alpha = alpha
        self._initialized = False
        self._prev = 0.0

    def update(self, value: float) -> float:
        if not self._initialized:
            self._prev = value
            self._initialized = True
            return value
        filtered = (self._alpha * value) + ((1.0 - self._alpha) * self._prev)
        self._prev = filtered
        return filtered

    def reset(self) -> None:
        self._initialized = False
        self._prev = 0.0

'''
Implement Switching Kalman Filter
Reference to reproduce:
https://arxiv.org/html/2412.06601v1
or
https://share.google/uvIKaRY1qkant3d77
'''