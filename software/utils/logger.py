"""CSV logger for timestamped voltage data."""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Optional

from .types import Snapshot


class CsvLogger:
    """Append timestamped voltage samples to a CSV file."""

    @staticmethod
    def build_run_paths(output_root: str, run_name: str) -> tuple[str, str]:
        run_dir = os.path.join(output_root, run_name)
        csv_name = f"{run_name}.csv"
        return run_dir, csv_name

    def __init__(self, output_dir: str, filename: Optional[str] = None) -> None:
        os.makedirs(output_dir, exist_ok=True)
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"volt_log_{timestamp}.csv"
        self._path = os.path.join(output_dir, filename)
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "timestamp",
            "elapsed_s",
            "measured_v",
            "current_mA",
            "resistance",
            "std_dev",
            "stage_commanded",
            "stage_effective",
            "stage_changed",
        ])
        self._line_count = 0

    @property
    def path(self) -> str:
        return self._path

    def log_sample(
        self,
        timestamp: datetime,
        elapsed_s: float,
        measured_v: float,
        current_mA: float,
        snapshot: Optional[Snapshot] = None,
        stage_commanded: Optional[int] = None,
        stage_effective: Optional[int] = None,
        stage_changed: Optional[bool] = None,
    ) -> None:
        commanded_value = stage_commanded if stage_commanded is not None else (snapshot.stage if snapshot is not None else None)
        self._writer.writerow(
            [
                timestamp.isoformat(timespec="milliseconds"),
                f"{elapsed_s:.6f}",
                f"{measured_v:.8f}",
                f"{current_mA:.8f}",
                "" if snapshot is None or snapshot.resistance is None else f"{snapshot.resistance:.8f}",
                "" if snapshot is None or snapshot.std_dev is None else f"{snapshot.std_dev:.8f}",
                "" if commanded_value is None else commanded_value,
                "" if stage_effective is None else stage_effective,
                "" if stage_changed is None else str(stage_changed).lower(),
            ]
        )
        self._line_count += 1
        if self._line_count % 25 == 0:
            self._file.flush()

    def close(self) -> None:
        self._file.flush()
        self._file.close()
