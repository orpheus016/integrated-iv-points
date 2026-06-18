from __future__ import annotations


from dataclasses import dataclass

from software.data_source.ads1256 import ads1256_reader
from software.command.serial_commander import SerialCommander
from software.config.config import CurrentSwitchConfig, SerialConfig, StreamMarkersConfig


class _FakeSerial:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode("utf-8") for line in lines]
        self.is_open = True
        self.written: list[bytes] = []

    def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        self.is_open = False


@dataclass(frozen=True)
class _ParsedSample:
    timestamp_s: float
    voltage_v: float
    current_mA: float


def test_wait_for_marker_ignores_reset_done_banner() -> None:
    config = SerialConfig(markers=StreamMarkersConfig())
    commander = SerialCommander(config)
    commander._serial = _FakeSerial([
        "*Reset DONE!",
        "*Register defaults updated!",
        "*Commands:",
        "noise",
        "*STREAM_START",
    ])

    commander.wait_for_marker(config.markers.stream_start, timeout_s=0.1)


def test_ads1256_reader_rejects_unknown_marker_after_stream_start(monkeypatch) -> None:
    config = SerialConfig(markers=StreamMarkersConfig())
    commander = SerialCommander(config)
    commander._serial = _FakeSerial([
        "*Reset DONE!",
        "*Register defaults updated!",
        "*Commands:",
        "*STREAM_START",
        "1.0,10.0",
        "*BOGUS",
    ])
    monkeypatch.setattr(SerialCommander, "open", lambda self: None)

    def _parse_sample_line(line: str, timestamp_s: float) -> _ParsedSample:
        voltage_text, current_text = line.split(",")
        return _ParsedSample(timestamp_s=timestamp_s, voltage_v=float(voltage_text), current_mA=float(current_text))

    commander.parse_sample_line = _parse_sample_line  # type: ignore[method-assign]

    try:
        generator = ads1256_reader(config, commander=commander, manage_current_switching=False)
        next(generator)
        next(generator)
    except RuntimeError as exc:
        assert "*BOGUS" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for unknown marker")


def test_ads1256_reader_skips_startup_banners_before_stream_start(monkeypatch) -> None:
    config = SerialConfig(markers=StreamMarkersConfig())
    commander = SerialCommander(config)
    commander._serial = _FakeSerial([
        "*Reset DONE!",
        "*Register defaults updated!",
        "*Commands:",
        "*r [reg] - Read Reg",
        "*w [reg] [val] - Write Reg",
        "*i [0-3] - Direct Stage Select",
        "*C - Continuous CSV stream",
        "*STREAM_START",
        "0.01747251,4",
        "*STREAM_STOP",
    ])
    monkeypatch.setattr(SerialCommander, "open", lambda self: None)

    generator = ads1256_reader(config, commander=commander, manage_current_switching=False)

    timestamp_s, voltage_v, current_mA = next(generator)

    assert voltage_v == 0.01747251
    assert current_mA == 4.0
    assert timestamp_s >= 0.0

    try:
        next(generator)
    except StopIteration:
        pass
    else:
        raise AssertionError("expected StopIteration after stream stop marker")


def test_decide_stage_downshifts_until_power_ok() -> None:
    switch = CurrentSwitchConfig(
        current_mA_by_stage=(4.0, 8.0, 12.0, 20.0),
        power_limit_mw=5.0,
        min_voltage_v=0.001,
        headroom_v=2.0,
        raise_low_v_by_stage=(0.3, 0.25, 0.15, 0.0),
        raise_high_v_by_stage=(0.35, 0.3, 0.2, 0.0),
        blanking_s=0.5,
        max_settle_s=1.0,
    )
    config = SerialConfig(current_switch=switch)
    commander = SerialCommander(config)
    commander._serial = _FakeSerial([])
    commander._current_stage = 3

    decision = commander.decide_stage(1.0, 20.0)

    assert decision.stage == 0
    assert decision.switched is True
    assert commander.current_stage() == 0
    assert commander._serial.written[-1] == b"i0"


def test_decide_stage_raise_uses_hysteresis_band() -> None:
    switch = CurrentSwitchConfig(
        current_mA_by_stage=(4.0, 8.0, 12.0, 20.0),
        power_limit_mw=5.0,
        min_voltage_v=0.001,
        headroom_v=2.0,
        raise_low_v_by_stage=(0.3, 0.25, 0.15, 0.0),
        raise_high_v_by_stage=(0.35, 0.3, 0.2, 0.0),
        blanking_s=0.5,
        max_settle_s=1.0,
    )
    config = SerialConfig(current_switch=switch)
    commander = SerialCommander(config)
    commander._serial = _FakeSerial([])
    commander._current_stage = 0

    decision = commander.decide_stage(0.29, 4.0)

    assert decision.stage == 1
    assert decision.switched is True
    assert commander.current_stage() == 1

    decision = commander.decide_stage(0.27, 8.0)
    assert decision.stage == 1
    assert decision.switched is False

    decision = commander.decide_stage(0.0005, 8.0)
    assert decision.stage == 1
    assert decision.switched is False