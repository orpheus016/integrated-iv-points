"""Worst-case artificial data generator for snapshot stress testing."""

from __future__ import annotations

import math
import random
from typing import Iterator

from ..config.config import SimulationConfig
from ..utils.types import Sample


def worst_case_signal_generator(config: SimulationConfig) -> Iterator[Sample]:
	"""Yield a noisy, slowly settling stream to stress backbone logic."""
	rng = random.Random()
	timestamp_s = 0.0
	dt_s = 1.0 / config.sample_rate_hz
	true_voltage_v = config.current_source_a * config.sample_resistance_ohm

	while True:
		slow_settle = 1.0 - math.exp(-timestamp_s / max(config.tau_s * 3.0, 1e-9))
		ripple = 0.05 * math.sin(2.0 * math.pi * 0.5 * timestamp_s)
		drift = config.drift_amplitude_v * 4.0 * math.sin(2.0 * math.pi * config.drift_frequency_hz * timestamp_s)
		noise = rng.gauss(0.0, config.noise_sigma_v * 8.0)
		measured_voltage_v = (true_voltage_v * slow_settle) + ripple + drift + noise
		yield (timestamp_s, measured_voltage_v, config.current_source_a * 1000.0)
		timestamp_s += dt_s