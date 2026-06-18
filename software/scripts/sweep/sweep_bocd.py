"""Sweep BOCD parameters and evaluate performance offline on a given CSV.

This script runs grid search over hazard_rate, var0, varx, and cp_reset_threshold.
It outputs a CSV containing the parameters and the results (voltage, RMSE, best_run_length).
"""

from __future__ import annotations

import csv
import itertools
from copy import copy
from pathlib import Path
from typing import List

from ...config.config import build_arg_parser, build_simulation_config
from ...utils.evaluate_helpers import evaluate_samples
from ...utils.csv_replay import csv_replay_reader


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
    out_csv = out_dir / f"{input_path.stem}-bocd.csv"

    # Pre-load samples to memory so we don't re-read the CSV thousands of times
    print(f"Loading samples from {input_path}...")
    samples = list(csv_replay_reader(str(input_path), sample_rate_hz=sim_config.sample_rate_hz))
    print(f"Loaded {len(samples)} samples.")

    # Define the grid
    hazard_rates = [1.0/50.0, 1.0/100.0, 1.0/200.0]
    var0s = [0.5, 1.0, 2.0]
    varxs = [1e-4, 1e-5, 1e-6]
    cp_reset_thresholds = [3, 5, 10]
    
    grid = list(itertools.product(hazard_rates, var0s, varxs, cp_reset_thresholds))
    print(f"Starting sweep of {len(grid)} parameter combinations...")

    results_data = []

    for idx, (hr, v0, vx, cp) in enumerate(grid, 1):
        # Create a fresh args object for each combination
        run_args = copy(args)
        run_args.bocd_hazard_rate = hr
        run_args.bocd_mean0 = 0.0
        run_args.bocd_var0 = v0
        run_args.bocd_varx = vx
        run_args.bocd_cp_reset_threshold = cp
        # Hardcode min_stable_samples just to be sure
        run_args.min_stable_samples = 10

        # Run evaluation (evaluate_samples takes an iterable, but list works fine)
        # Note: evaluate_samples modifies backbones list if it's not a list, wait, it takes Iterable[str]
        data = evaluate_samples(samples, ["bocd"], sim_config, run_args)
        
        bocd_result = data["results"]["bocd"]
        decided = bocd_result.get("decided_snapshot")
        metrics = bocd_result.get("metrics")
        
        if decided is not None:
            v = decided.voltage
            brl = decided.best_run_length if decided.best_run_length is not None else 0
            rmse = metrics.rmse
        else:
            v = 0.0
            brl = 0
            rmse = 0.0
            
        results_data.append({
            "hazard_rate": hr,
            "var0": v0,
            "varx": vx,
            "cp_reset_threshold": cp,
            "voltage": v,
            "rmse": rmse,
            "best_run_length": brl,
        })
        
        if idx % 10 == 0:
            print(f"Completed {idx}/{len(grid)}...")

    # Rank results by best_run_length descending, then rmse ascending
    results_data.sort(key=lambda x: (-x["best_run_length"], x["rmse"]))

    # Write to CSV
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "hazard_rate", "var0", "varx", "cp_reset_threshold",
            "voltage", "rmse", "best_run_length"
        ])
        writer.writeheader()
        writer.writerows(results_data)

    print(f"Sweep complete. Results written to {out_csv}")
    
    # Print the top 3
    print("\nTop 3 Parameter Sets:")
    for i, r in enumerate(results_data[:3], 1):
        print(f"#{i}: HR={r['hazard_rate']:.4f}, var0={r['var0']:.2f}, varx={r['varx']:.1e}, CP={r['cp_reset_threshold']} "
              f"-> RunLen={r['best_run_length']}, Voltage={r['voltage']:.4f}, RMSE={r['rmse']:.6f}")


if __name__ == "__main__":
    main()
