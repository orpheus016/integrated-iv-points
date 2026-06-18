"""Sweep hysteresis backbone parameters and evaluate offline on a given CSV.

Applies a grid search over enter_threshold, exit_threshold, snapshot_window_s,
and min_stable_duration_s.

Usage::

    python -m software.scripts.sweep.sweep_hysteresis \\
        --csv-path software/output/testbench/waferIA6.csv
"""

from __future__ import annotations

import csv
import itertools
from copy import copy
from pathlib import Path

from ...config.config import build_arg_parser, build_simulation_config
from ...utils.evaluate_helpers import evaluate_samples
from ...utils.csv_replay import csv_replay_reader


# ---------------------------------------------------------------------------
# Search grids
# ---------------------------------------------------------------------------
ENTER_THRESHOLD_V_GRID = [0.5, 0.7, 0.8, 0.9, 1.0]
EXIT_THRESHOLD_V_GRID  = [0.3, 0.5, 0.6, 0.7, 0.8]
WINDOW_S_GRID          = [0.2, 0.5, 1.0, 2.0]
MIN_DURATION_S_GRID    = [0.2, 0.5, 1.0]


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_path = Path(args.csv_path)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return

    sim_config = build_simulation_config(args)
    out_dir = Path(f"software/output/evaluate/{input_path.stem}/sweep")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{input_path.stem}-hysteresis.csv"

    print(f"Loading samples from {input_path}...")
    samples = list(csv_replay_reader(str(input_path), sample_rate_hz=sim_config.sample_rate_hz))
    print(f"Loaded {len(samples)} samples.")

    # Filter out invalid combinations where exit >= enter
    combos = [
        (en, ex, win, dur)
        for en, ex, win, dur in itertools.product(
            ENTER_THRESHOLD_V_GRID, EXIT_THRESHOLD_V_GRID, WINDOW_S_GRID, MIN_DURATION_S_GRID
        )
        if ex < en
    ]
    print(f"Starting sweep of {len(combos)} valid parameter combinations for 'hysteresis'...")

    results_data = []

    for idx, (en, ex, win_s, min_dur_s) in enumerate(combos, 1):
        run_args = copy(args)
        run_args.hysteresis_enter = en
        run_args.hysteresis_exit = ex
        run_args.snapshot_window = win_s
        run_args.snapshot_min_duration = min_dur_s

        from ...config.config import build_simulation_config as _bsc
        run_sim = _bsc(run_args)

        data = evaluate_samples(samples, ["hysteresis"], run_sim, run_args)
        result = data["results"]["hysteresis"]
        decided = result.get("decided_snapshot")
        metrics = result.get("metrics")

        if decided is not None:
            voltage = decided.voltage
            std_dev = decided.std_dev if decided.std_dev is not None else float("nan")
            rmse = metrics.rmse
            num_snapshots = len(result["snapshots"])
        else:
            voltage = float("nan")
            std_dev = float("nan")
            rmse = float("nan")
            num_snapshots = 0

        results_data.append({
            "enter_threshold_v": en,
            "exit_threshold_v": ex,
            "snapshot_window_s": win_s,
            "min_duration_s": min_dur_s,
            "voltage": voltage,
            "std_dev": std_dev,
            "rmse": rmse,
            "num_snapshots": num_snapshots,
        })

        if idx % 20 == 0:
            print(f"  Completed {idx}/{len(combos)}...")

    results_data.sort(key=lambda x: (x["num_snapshots"] == 0, x["rmse"]))

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "enter_threshold_v", "exit_threshold_v", "snapshot_window_s", "min_duration_s",
            "voltage", "std_dev", "rmse", "num_snapshots",
        ])
        writer.writeheader()
        writer.writerows(results_data)

    print(f"\nSweep complete. Results written to {out_csv}")

    print(f"\nTop 5 Parameter Sets:")
    for i, r in enumerate(results_data[:5], 1):
        print(
            f"  #{i}: enter={r['enter_threshold_v']:.2f}V  exit={r['exit_threshold_v']:.2f}V"
            f"  window={r['snapshot_window_s']:.2f}s  min_dur={r['min_duration_s']:.2f}s"
            f"  -> snaps={r['num_snapshots']}  voltage={r['voltage']:.4f}  rmse={r['rmse']:.6f}"
        )


if __name__ == "__main__":
    main()
