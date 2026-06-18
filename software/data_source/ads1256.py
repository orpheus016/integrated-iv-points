"""ADS1256 hardware data generator using the Arduino stream protocol."""

from __future__ import annotations

import time
from typing import Iterator

from ..config.config import SerialConfig
from ..utils.types import Sample
from ..command.serial_commander import SerialCommander


def ads1256_reader(
    config: SerialConfig,
    commander: SerialCommander | None = None,
    manage_current_switching: bool = True,
) -> Iterator[Sample]:
    """Yield (timestamp_s, voltage_v, current_mA) tuples from the Arduino stream.

    If an external `commander` is provided, it will be used but not closed by this
    generator; the caller is responsible for lifecycle management. If no commander
    is provided, this function will create and own one and will close it on exit.
    """
    owner = False
    if commander is None:
        commander = SerialCommander(config)
        owner = True

    # ensure the serial port is open
    commander.open()
    try:
        # Match manual_capture: clear boot chatter, start the stream, and wait
        # until the exact stream header arrives before yielding any samples.
        commander.reset()
        time.sleep(config.protocol.stream_startup_delay_s)
        commander.flush_input()
        commander.start_stream()
        commander.wait_for_marker(config.markers.stream_start, timeout_s=config.protocol.stream_start_timeout_s)
        start_time_s = time.perf_counter()

        while True:
            line = commander.read_line()
            if not line:
                continue

            if line == config.markers.stream_stop:
                return

            if line == config.markers.reset_done:
                continue

            if line.startswith("*"):
                raise RuntimeError(f"unexpected stream marker: {line}")

            sample_time_s = time.perf_counter() - start_time_s
            parsed = commander.parse_sample_line(line, sample_time_s)
            yield (parsed.timestamp_s, parsed.voltage_v, parsed.current_mA)

            if manage_current_switching and owner:
                commander.decide_stage(parsed.voltage_v, parsed.current_mA)
    finally:
        if owner:
            try:
                commander.stop_stream()
                time.sleep(config.protocol.stream_restart_delay_s)
            finally:
                commander.close()


def ads1256_passive_reader(
    config: SerialConfig,
    commander: SerialCommander | None = None,
    manage_current_switching: bool = True,
) -> Iterator[Sample]:
    """Yield samples after *STREAM_START and stop on *STREAM_STOP.

    This variant does not send the stream start command. It is intended for the
    passive integration path where the Arduino owns the stream lifecycle.
    """
    owner = False
    if commander is None:
        commander = SerialCommander(config)
        owner = True

    commander.open()
    try:
        time.sleep(config.protocol.stream_startup_delay_s)
        commander.flush_input()
        commander.wait_for_marker(config.markers.stream_start, timeout_s=config.protocol.stream_start_timeout_s)
        start_time_s = time.perf_counter()

        while True:
            line = commander.read_line()
            if not line:
                continue

            if line == config.markers.stream_stop:
                return

            if line == config.markers.reset_done:
                continue

            if line.startswith("*"):
                raise RuntimeError(f"unexpected stream marker: {line}")

            sample_time_s = time.perf_counter() - start_time_s
            parsed = commander.parse_sample_line(line, sample_time_s)
            yield (parsed.timestamp_s, parsed.voltage_v, parsed.current_mA)

            if manage_current_switching and owner:
                commander.decide_stage(parsed.voltage_v, parsed.current_mA)
    finally:
        if owner:
            commander.close()
