"""Sweep Derivative Integration parameters and evaluate offline on a given CSV.

Applies a grid search over derivative_threshold, integration_threshold,
leakage_factor, and iir_window.

Usage::

    python -m software.scripts.sweep.sweep_derivative_integration \\
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
DERIVATIVE_THRESHOLD_GRID  = [0.001, 0.005, 0.01, 0.02, 0.05]
INTEGRATION_THRESHOLD_GRID = [0.01, 0.05, 0.1, 0.2, 0.5]
LEAKAGE_FACTOR_GRID        = [0.7, 0.8, 0.9, 0.95, 0.99]
IIR_WINDOW_GRID            = [4, 8, 16, 32]


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
    out_csv = out_dir / f"{input_path.stem}-derivative_integration.csv"

    print(f"Loading samples from {input_path}...")
    samples = list(csv_replay_reader(str(input_path), sample_rate_hz=sim_config.sample_rate_hz))
    print(f"Loaded {len(samples)} samples.")

    grid = list(itertools.product(
        DERIVATIVE_THRESHOLD_GRID,
        INTEGRATION_THRESHOLD_GRID,
        LEAKAGE_FACTOR_GRID,
        IIR_WINDOW_GRID,
    ))
    print(f"Starting sweep of {len(grid)} parameter combinations for 'derivative_integration'...")

    results_data = []

    for idx, (dt, it, lf, iir) in enumerate(grid, 1):
        run_args = copy(args)
        run_args.di_dt_threshold = dt
        run_args.di_it_threshold = it
        run_args.di_leakage_factor = lf
        run_args.di_iir_window = iir

        data = evaluate_samples(samples, ["derivative_integration"], sim_config, run_args)
        result = data["results"]["derivative_integration"]
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
            "derivative_threshold": dt,
            "integration_threshold": it,
            "leakage_factor": lf,
            "iir_window": iir,
            "voltage": voltage,
            "std_dev": std_dev,
            "rmse": rmse,
            "num_snapshots": num_snapshots,
        })

        if idx % 50 == 0:
            print(f"  Completed {idx}/{len(grid)}...")

    results_data.sort(key=lambda x: (x["num_snapshots"] == 0, x["rmse"]))

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "derivative_threshold", "integration_threshold", "leakage_factor", "iir_window",
            "voltage", "std_dev", "rmse", "num_snapshots",
        ])
        writer.writeheader()
        writer.writerows(results_data)

    print(f"\nSweep complete. Results written to {out_csv}")

    print(f"\nTop 5 Parameter Sets:")
    for i, r in enumerate(results_data[:5], 1):
        print(
            f"  #{i}: dt={r['derivative_threshold']:.4f}  it={r['integration_threshold']:.4f}"
            f"  leakage={r['leakage_factor']:.3f}  iir_win={r['iir_window']}"
            f"  -> snaps={r['num_snapshots']}  voltage={r['voltage']:.4f}  rmse={r['rmse']:.6f}"
        )


if __name__ == "__main__":
    main()
