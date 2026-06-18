"""Sweep stddev-family parameters and evaluate offline on a given CSV.

Applies a grid search over snapshot_window_s, snapshot_std_threshold_v, and
snapshot_min_duration_s for the ``stddev_window``, ``baseline``, and
``running_stat`` backbones, which all share the same parameter surface.

Usage::

    python -m software.scripts.sweep.sweep_stddev \\
        --csv-path software/output/testbench/waferIA6.csv \\
        --backbone stddev_window
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
# Search grids — edit these to refine or expand the sweep
# ---------------------------------------------------------------------------
WINDOW_S_GRID = [0.2, 0.5, 1.0, 2.0]
STD_THRESHOLD_V_GRID = [0.0001, 0.0002, 0.0005, 0.001, 0.002]
MIN_DURATION_S_GRID = [0.2, 0.5, 1.0, 2.0]

VALID_BACKBONES = {"stddev_window", "baseline", "running_stat"}


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    backbone_name = args.backbone
    if backbone_name not in VALID_BACKBONES:
        print(
            f"This sweep script targets stddev-family backbones. "
            f"Got '{backbone_name}'. Choose from: {', '.join(sorted(VALID_BACKBONES))}"
        )
        return

    input_path = Path(args.csv_path)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return

    sim_config = build_simulation_config(args)
    out_dir = Path(f"software/output/evaluate/{input_path.stem}/sweep")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{input_path.stem}-{backbone_name}.csv"

    print(f"Loading samples from {input_path}...")
    samples = list(csv_replay_reader(str(input_path), sample_rate_hz=sim_config.sample_rate_hz))
    print(f"Loaded {len(samples)} samples.")

    grid = list(itertools.product(WINDOW_S_GRID, STD_THRESHOLD_V_GRID, MIN_DURATION_S_GRID))
    print(f"Starting sweep of {len(grid)} parameter combinations for '{backbone_name}'...")

    results_data = []

    for idx, (win_s, std_thr, min_dur_s) in enumerate(grid, 1):
        run_args = copy(args)
        run_args.snapshot_window = win_s
        run_args.snapshot_threshold = std_thr
        run_args.snapshot_min_duration = min_dur_s

        # Rebuild sim_config so window/duration are reflected
        from ...config.config import build_simulation_config as _bsc
        run_sim = _bsc(run_args)

        data = evaluate_samples(samples, [backbone_name], run_sim, run_args)
        result = data["results"][backbone_name]
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
            "backbone": backbone_name,
            "snapshot_window_s": win_s,
            "std_threshold_v": std_thr,
            "min_duration_s": min_dur_s,
            "voltage": voltage,
            "std_dev": std_dev,
            "rmse": rmse,
            "num_snapshots": num_snapshots,
        })

        if idx % 20 == 0:
            print(f"  Completed {idx}/{len(grid)}...")

    # Rank: snapshots > 0 first, then lowest rmse
    results_data.sort(key=lambda x: (x["num_snapshots"] == 0, x["rmse"]))

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "backbone", "snapshot_window_s", "std_threshold_v", "min_duration_s",
            "voltage", "std_dev", "rmse", "num_snapshots",
        ])
        writer.writeheader()
        writer.writerows(results_data)

    print(f"\nSweep complete. Results written to {out_csv}")

    print(f"\nTop 5 Parameter Sets:")
    for i, r in enumerate(results_data[:5], 1):
        print(
            f"  #{i}: window={r['snapshot_window_s']:.2f}s  std_thr={r['std_threshold_v']:.4f}V"
            f"  min_dur={r['min_duration_s']:.2f}s"
            f"  -> snaps={r['num_snapshots']}  voltage={r['voltage']:.4f}  rmse={r['rmse']:.6f}"
        )


if __name__ == "__main__":
    main()
