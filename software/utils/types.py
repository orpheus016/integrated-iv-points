"""Shared data contracts for streaming and snapshotting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

Sample = Tuple[float, float, float]


@dataclass(frozen=True)
class Snapshot:
    """Stable measurement snapshot with optional debug metadata."""

    timestamp: float
    voltage: float
    current_mA: float
    resistance: Optional[float] = None
    std_dev: Optional[float] = None
    stage: Optional[str] = None
    best_run_length: Optional[int] = None
