"""Serial protocol helper for the Instrument Arduino firmware."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional, Tuple

from ..config.config import CurrentSwitchConfig, SerialConfig

try:
    import serial
except ImportError as exc:  # pragma: no cover - dependency availability depends on environment
    serial = None  # type: ignore[assignment]
    _SERIAL_IMPORT_ERROR = exc
else:
    _SERIAL_IMPORT_ERROR = None


@dataclass(frozen=True)
class StreamSample:
    timestamp_s: float
    voltage_v: float
    current_mA: float


@dataclass(frozen=True)
class StageDecision:
    stage: int
    switched: bool


class SerialCommander:
    """Owns the Arduino stream protocol, handshake, and current switching."""

    def __init__(self, config: SerialConfig) -> None:
        self._config = config
        self._serial: Optional["serial.Serial"] = None
        self._current_stage = 0

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        if serial is None:  # pragma: no cover - runtime dependency path
            raise RuntimeError("pyserial is required for hardware streaming") from _SERIAL_IMPORT_ERROR
        if self._serial is not None and self._serial.is_open:
            return
        self._serial = serial.Serial(
            port=self._config.port,
            baudrate=self._config.baud_rate,
            timeout=self._config.protocol.line_timeout_s,
        )

    def close(self) -> None:
        if self._serial is not None:
            if self._serial.is_open:
                self._serial.close()
            self._serial = None

    def reset(self) -> None:
        self._write_text(self._config.protocol.reset_command)
        self._current_stage = 0

    def start_stream(self) -> None:
        self._write_text(self._config.protocol.stream_command)

    def stop_stream(self) -> None:
        self._write_text(self._config.protocol.stop_command)

    def set_stage(self, stage: int) -> None:
        if stage < self._config.protocol.stage_command_min or stage > self._config.protocol.stage_command_max:
            raise ValueError(f"stage must be in [{self._config.protocol.stage_command_min}, {self._config.protocol.stage_command_max}]")
        self._write_text(f"{self._config.protocol.stage_command_prefix}{stage}")
        self._current_stage = stage

    def current_stage(self) -> int:
        return self._current_stage

    def decide_stage(self, voltage_v: float, current_mA: float) -> StageDecision:
        policy = self._config.current_switch
        protocol = self._config.protocol
        next_stage = self._current_stage

        power_mw = voltage_v * current_mA
        if power_mw > policy.power_limit_mw:
            next_stage = self._downshift_for_power(voltage_v)
        elif self._can_raise(voltage_v):
            low_threshold, high_threshold = self._raise_band_for_stage(next_stage)
            if voltage_v < low_threshold and next_stage < protocol.stage_command_max:
                next_stage += 1

        switched = next_stage != self._current_stage
        if switched:
            self.set_stage(next_stage)
        return StageDecision(stage=next_stage, switched=switched)

    def parse_sample_line(self, line: str, timestamp_s: float) -> StreamSample:
        parts = line.split(",")
        if len(parts) != 2:
            raise ValueError(f"expected 'voltage,current_mA' line, got: {line!r}")
        voltage_v = float(parts[0])
        current_mA = float(parts[1])
        return StreamSample(timestamp_s=timestamp_s, voltage_v=voltage_v, current_mA=current_mA)

    def read_line(self) -> str:
        self._ensure_open()
        assert self._serial is not None
        raw = self._serial.readline()
        return raw.decode("utf-8", errors="replace").strip()

    def wait_for_marker(self, marker: str, timeout_s: Optional[float] = None) -> None:
        self._ensure_open()
        if timeout_s is None:
            timeout_s = self._config.protocol.line_timeout_s
        deadline = time.monotonic() + timeout_s
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out waiting for marker: {marker}")
            line = self.read_line()
            if line == marker:
                return

            if line.startswith("*"):
                continue

    def flush_input(self) -> None:
        self._ensure_open()
        assert self._serial is not None
        self._serial.reset_input_buffer()

    def _write_text(self, command: str) -> None:
        self._ensure_open()
        assert self._serial is not None
        self._serial.write(command.encode("utf-8"))

    def _raise_band_for_stage(self, stage: int) -> Tuple[float, float]:
        policy = self._config.current_switch
        return policy.raise_low_v_by_stage[stage], policy.raise_high_v_by_stage[stage]

    def _can_raise(self, voltage_v: float) -> bool:
        policy = self._config.current_switch
        return policy.min_voltage_v <= voltage_v <= policy.headroom_v

    def _downshift_for_power(self, voltage_v: float) -> int:
        policy = self._config.current_switch
        protocol = self._config.protocol
        next_stage = self._current_stage
        while next_stage > protocol.stage_command_min:
            candidate = next_stage - 1
            candidate_current = policy.current_mA_by_stage[candidate]
            if voltage_v * candidate_current <= policy.power_limit_mw:
                return candidate
            next_stage = candidate
        return protocol.stage_command_min

    def _ensure_open(self) -> None:
        if not self.is_open:
            self.open()
