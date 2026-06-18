"""Dummy voltage generator for local testing."""

from __future__ import annotations

import math
import random
from typing import Iterator

from ..config.config import SimulationConfig
from ..utils.types import Sample


def dummy_voltage_generator(config: SimulationConfig) -> Iterator[Sample]:
	rng = random.Random()
	timestamp_s = 0.0
	dt_s = 1.0 / config.sample_rate_hz
	true_voltage_v = config.current_source_a * config.sample_resistance_ohm
	current_mA = config.current_source_a * 1000.0

	while True:
		settled_voltage_v = true_voltage_v * (1.0 - math.exp(-timestamp_s / max(config.tau_s, 1e-9)))
		measured_voltage_v = settled_voltage_v + rng.gauss(0.0, config.noise_sigma_v)
		yield (timestamp_s, measured_voltage_v, current_mA)
		timestamp_s += dt_s


__all__ = ["dummy_voltage_generator"]
