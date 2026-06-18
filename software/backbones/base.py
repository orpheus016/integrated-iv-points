"""Backbone base class for snapshot algorithms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..utils.types import Sample, Snapshot


class BaseBackbone(ABC):
    """Abstract backbone interface for streaming snapshot detection."""

    def __init__(self, min_recording_samples: int = 1) -> None:
        if min_recording_samples < 1:
            raise ValueError("min_recording_samples must be >= 1")
        self._min_recording_samples = min_recording_samples
        self._samples_seen = 0

    def _mark_sample(self) -> int:
        self._samples_seen += 1
        return self._samples_seen

    def _has_min_recording(self) -> bool:
        return self._samples_seen >= self._min_recording_samples

    @abstractmethod
    def update(self, sample: Sample) -> Optional[Snapshot]:
        """Process (timestamp, voltage, current_mA) and return a Snapshot if stable."""
        raise NotImplementedError

    def reset(self) -> None:
        """Reset internal state between runs or stages."""
        return None
