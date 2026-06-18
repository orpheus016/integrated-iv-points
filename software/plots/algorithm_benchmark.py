"""
algorithm_benchmark.py
----------------------
Benchmarks four VI-snapshot backbone algorithms by comparing RMSE distributions
across their parameter sweeps.

Algorithms evaluated
--------------------
  - BOCD (Bayesian Online Change-Point Detection)
  - Derivative Integration
  - Hysteresis
  - Standard Deviation Window

Robustness metric (revised)
----------------------------
  robustness = IQR_valid + failure_rate * mean_rmse_at_failure

  IQR_valid          = Q90_valid - Q10_valid   (spread of converged runs)
  failure_rate       = failed_runs / total_runs
  mean_rmse_at_failure = mean RMSE of rows where the backbone produced
                         no snapshot (std_dev is NaN)

  Lower = better. Penalises both noisy valid-run behaviour AND frequent failures.

Input
-----
  Four CSV files from software/output/evaluate/waferIA6/sweep/

Output (to software/plots/output/algorithm_benchmark/)
-------------------------------------------------------
  algorithm_rmse_violin.png / .pdf   -- RMSE distribution violin plot
  algorithm_tradeoff.png   / .pdf   -- min-RMSE vs robustness scatter
  algorithm_benchmark_summary.csv   -- per-algorithm statistics

Usage
-----
  python software/plots/algorithm_benchmark.py
  python software/plots/algorithm_benchmark.py --sweep-dir path/to/sweep
  python software/plots/algorithm_benchmark.py --dpi 600
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import seaborn as sns


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_SWEEP_DIR = (
    Path(__file__).resolve().parent.parent
    / "output" / "evaluate" / "waferIA6" / "sweep"
)
_DEFAULT_OUT_DIR = (
    Path(__file__).resolve().parent / "output" / "algorithm_benchmark"
)

# Algorithm display names -> CSV file stem
ALGORITHM_MAP: dict[str, str] = {
    "BOCD":                     "waferIA6-bocd",
    "Derivative Integration":   "waferIA6-derivative_integration",
    "Hysteresis":               "waferIA6-hysteresis",
    "Std Dev Window":           "waferIA6-stddev_window",
}

# Per-algorithm colours (print-friendly, distinct)
PALETTE: dict[str, str] = {
    "BOCD":                   "#1f4e7d",
    "Derivative Integration": "#1a6e3c",
    "Hysteresis":             "#8b1a1a",
    "Std Dev Window":         "#8b5e00",
}


# ---------------------------------------------------------------------------
# IEEE-style plot formatting
# ---------------------------------------------------------------------------
def _apply_ieee_style() -> None:
    plt.rcParams.update({
        "font.family":        "serif",
        "font.serif":         ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size":          9,
        "axes.labelsize":     10,
        "axes.titlesize":     10,
        "xtick.labelsize":    8,
        "ytick.labelsize":    8,
        "legend.fontsize":    8,
        "lines.linewidth":    1.2,
        "lines.markersize":   5,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.grid":          True,
        "grid.linestyle":     ":",
        "grid.alpha":         0.4,
        "grid.linewidth":     0.5,
        "figure.facecolor":   "white",
        "axes.facecolor":     "white",
        "savefig.facecolor":  "white",
    })


# ---------------------------------------------------------------------------
# Data loading -- returns (valid-only, all-rows) DataFrames
# ---------------------------------------------------------------------------
def load_and_merge(sweep_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load all four sweep CSVs.

    Returns
    -------
    merged_valid : rows where std_dev is NOT NaN (backbone converged)
    merged_all   : every row including failures (std_dev is NaN)

    A row is a 'failure' when std_dev is NaN -- the backbone produced no
    stable snapshot.  BOCD has no std_dev column; all its rows are valid.
    """
    valid_frames: list[pd.DataFrame] = []
    all_frames:   list[pd.DataFrame] = []

    for display_name, stem in ALGORITHM_MAP.items():
        csv_path = sweep_dir / f"{stem}.csv"
        if not csv_path.is_file():
            print(f"  [WARN] CSV not found, skipping: {csv_path}", file=sys.stderr)
            continue

        df = pd.read_csv(csv_path)
        df["algorithm"]  = display_name
        df["is_failure"] = False

        if "std_dev" in df.columns:
            df.loc[df["std_dev"].isna(), "is_failure"] = True

        all_frames.append(df.copy())

        valid_df = df[~df["is_failure"]].copy()
        valid_frames.append(valid_df)

        n_valid = int((~df["is_failure"]).sum())
        n_all   = len(df)
        print(
            f"  Loaded '{display_name}': {n_valid}/{n_all} valid rows "
            f"({(n_all - n_valid) / n_all * 100:.1f}% failure) "
            f"from {csv_path.name}"
        )

    if not valid_frames:
        raise RuntimeError(f"No CSVs found in {sweep_dir}")

    return (
        pd.concat(valid_frames, ignore_index=True, sort=False),
        pd.concat(all_frames,   ignore_index=True, sort=False),
    )


# ---------------------------------------------------------------------------
# Statistics -- failure-penalized robustness
# ---------------------------------------------------------------------------
def compute_benchmark_stats(
    merged_valid: pd.DataFrame,
    merged_all: pd.DataFrame,
    sweep_dir: Path,
) -> pd.DataFrame:
    """
    Compute per-algorithm benchmark statistics.

    robustness_metric = IQR_valid + failure_rate * mean_rmse_at_failure
    """
    rows = []

    for display_name, stem in ALGORITHM_MAP.items():
        if not (sweep_dir / f"{stem}.csv").is_file():
            continue

        algo_valid = merged_valid[merged_valid["algorithm"] == display_name]["rmse"]
        algo_all   = merged_all[merged_all["algorithm"] == display_name]
        algo_fail  = algo_all[algo_all["is_failure"]]["rmse"]

        total_runs   = len(algo_all)
        valid_runs   = int(algo_valid.shape[0])
        failed_runs  = total_runs - valid_runs
        failure_rate = failed_runs / total_runs if total_runs > 0 else 0.0

        min_rmse    = float(algo_valid.min())
        median_rmse = float(algo_valid.median())
        mean_rmse   = float(algo_valid.mean())
        std_rmse    = float(algo_valid.std(ddof=1))
        q10_rmse    = float(algo_valid.quantile(0.10))
        q90_rmse    = float(algo_valid.quantile(0.90))
        iqr_valid   = q90_rmse - q10_rmse

        mean_rmse_fail = float(algo_fail.mean()) if len(algo_fail) > 0 else 0.0
        robustness     = iqr_valid + failure_rate * mean_rmse_fail

        rows.append({
            "algorithm":            display_name,
            "total_runs":           total_runs,
            "valid_runs":           valid_runs,
            "failed_runs":          failed_runs,
            "failure_rate":         round(failure_rate, 4),
            "minimum_rmse":         min_rmse,
            "median_rmse":          median_rmse,
            "mean_rmse":            mean_rmse,
            "std_rmse":             std_rmse,
            "q10_rmse":             q10_rmse,
            "q90_rmse":             q90_rmse,
            "iqr_valid":            iqr_valid,
            "mean_rmse_at_failure": mean_rmse_fail,
            "robustness_metric":    robustness,
        })

    return pd.DataFrame(rows).sort_values("minimum_rmse").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Figure 1 -- Violin plot (ghost + foreground)
# ---------------------------------------------------------------------------
def build_violin_figure(
    merged_valid: pd.DataFrame,
    merged_all: pd.DataFrame,
    summary: pd.DataFrame,
) -> plt.Figure:
    """
    Violin plot (log y-axis) with:
      - Ghost background violin showing ALL runs (including failures) for
        algorithms that have a non-zero failure rate -- visually demonstrates
        the full RMSE penalty landscape
      - Solid foreground violin for valid runs only
      - Strip-plot overlay of individual valid-run sweep points
      - Median diamond + Q10-Q90 IQR bar
      - Failure rate annotated on x-axis for affected algorithms
      - Legend in lower right
    """
    order = summary.sort_values("median_rmse")["algorithm"].tolist()

    failure_rates = {
        algo: summary.loc[summary["algorithm"] == algo, "failure_rate"].values[0]
        for algo in order
    }

    fig, ax = plt.subplots(figsize=(7.16, 4.5), dpi=300)

    # -- Ghost background violin (all runs, including failures) ---------------
    ghost_algos = [a for a, fr in failure_rates.items() if fr > 0]
    ghost_df = merged_all[merged_all["algorithm"].isin(ghost_algos)].copy()

    if not ghost_df.empty:
        sns.violinplot(
            data=ghost_df,
            x="algorithm",
            y="rmse",
            hue="algorithm",
            order=order,
            palette=PALETTE,
            inner=None,
            cut=0,
            linewidth=0.5,
            alpha=0.15,
            legend=False,
            ax=ax,
        )

    # -- Foreground violin (valid runs only) ----------------------------------
    sns.violinplot(
        data=merged_valid,
        x="algorithm",
        y="rmse",
        hue="algorithm",
        order=order,
        palette=PALETTE,
        inner=None,
        cut=0,
        linewidth=0.8,
        alpha=0.60,
        legend=False,
        ax=ax,
    )

    # -- Strip-plot (valid runs) ----------------------------------------------
    sns.stripplot(
        data=merged_valid,
        x="algorithm",
        y="rmse",
        hue="algorithm",
        order=order,
        palette=PALETTE,
        size=2.5,
        alpha=0.55,
        jitter=True,
        legend=False,
        ax=ax,
        zorder=3,
    )

    # -- Median diamond -------------------------------------------------------
    for i, algo in enumerate(order):
        med = summary.loc[summary["algorithm"] == algo, "median_rmse"].values[0]
        ax.scatter(i, med, color="white", s=30, zorder=5,
                   linewidths=0.8, edgecolors="black", marker="D")

    # -- Q10-Q90 IQR bar ------------------------------------------------------
    for i, algo in enumerate(order):
        row = summary[summary["algorithm"] == algo].iloc[0]
        ax.vlines(i, row["q10_rmse"], row["q90_rmse"],
                  colors="black", linewidth=1.4, alpha=0.75, zorder=4)

    # -- Log y-axis -----------------------------------------------------------
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ticker.LogFormatterMathtext())
    ax.yaxis.set_minor_formatter(ticker.NullFormatter())

    # -- Failure rate annotations under x-tick labels -------------------------
    ax.set_xlabel("", labelpad=5)
    xlabels = []
    for algo in order:
        fr = failure_rates[algo]
        if fr > 0:
            xlabels.append(f"{algo}\n(Fail: {fr*100:.0f}%)")
        else:
            xlabels.append(algo)
    import matplotlib.ticker as mticker
    ax.xaxis.set_major_locator(mticker.FixedLocator(range(len(order))))
    ax.set_xticklabels(xlabels, fontsize=8)

    ax.set_ylabel("RMSE (log scale)", labelpad=5)
    ax.set_title(
        "Algorithm RMSE Distribution -- waferIA6 Parameter Sweep",
        loc="left", fontweight="bold", pad=6,
    )

    # -- Legend (lower right) -------------------------------------------------
    legend_elements = [
        Patch(facecolor="gray", alpha=0.20, edgecolor="gray",
              label="All runs incl. failures (ghost)"),
        Patch(facecolor="gray", alpha=0.60, edgecolor="gray",
              label="Valid runs only"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor="white",
               markeredgecolor="black", markersize=5, label="Median (valid)"),
        Line2D([0], [0], color="black", linewidth=1.4, alpha=0.75,
               label="Q10 - Q90 IQR (valid)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right",
              frameon=True, framealpha=0.88, edgecolor="0.7")

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure 2 -- Tradeoff scatter (revised robustness on x-axis)
# ---------------------------------------------------------------------------
def build_tradeoff_figure(summary: pd.DataFrame) -> plt.Figure:
    """
    min-RMSE (y) vs failure-penalized robustness (x) scatter.
    Lower-left corner = ideal algorithm.
    """
    fig, ax = plt.subplots(figsize=(5.5, 4.0), dpi=300)

    for _, row in summary.iterrows():
        algo  = row["algorithm"]
        x     = row["robustness_metric"]
        y     = row["minimum_rmse"]
        color = PALETTE.get(algo, "gray")

        ax.scatter(x, y, color=color, s=80, zorder=4,
                   edgecolors="black", linewidths=0.6)
        ax.annotate(
            algo, (x, y),
            textcoords="offset points", xytext=(6, 4),
            fontsize=7.5, color=color, fontweight="bold",
        )

    ax.set_xlabel(
        "Robustness Metric\n(IQR_valid + failure_rate x mean_RMSE_at_failure)",
        labelpad=5,
    )
    ax.set_ylabel("Best Achievable RMSE (minimum)", labelpad=5)
    ax.set_title(
        "Algorithm Benchmark Tradeoff\nBest RMSE vs. Failure-Penalized Robustness",
        loc="left", fontweight="bold", pad=6,
    )
    ax.text(0.97, 0.97, "<-- Ideal direction\n    (lower-left)",
            transform=ax.transAxes, fontsize=7, ha="right", va="top",
            color="0.5", fontstyle="italic")

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Console ranking table
# ---------------------------------------------------------------------------
def print_ranking_table(summary: pd.DataFrame) -> None:
    SEP = "-" * 70

    print()
    print("=" * 70)
    print("  ALGORITHM BENCHMARK RESULTS -- waferIA6 Parameter Sweep")
    print("=" * 70)

    print()
    print("  Ranking by best achievable RMSE (ascending):")
    print(SEP)
    print(f"  {'Rank':<5} {'Algorithm':<26} {'Min RMSE':>12} {'Median RMSE':>12}")
    print(SEP)
    for i, row in summary.sort_values("minimum_rmse").reset_index(drop=True).iterrows():
        print(f"  {i+1:<5} {row['algorithm']:<26} "
              f"{row['minimum_rmse']:>12.6f} {row['median_rmse']:>12.6f}")
    print(SEP)

    print()
    print("  Ranking by robustness (lower = less tuning sensitivity + fewer failures):")
    print(SEP)
    print(f"  {'Rank':<5} {'Algorithm':<26} {'Robustness':>12} "
          f"{'IQR_valid':>10} {'Fail%':>7}")
    print(SEP)
    for i, row in summary.sort_values("robustness_metric").reset_index(drop=True).iterrows():
        print(f"  {i+1:<5} {row['algorithm']:<26} "
              f"{row['robustness_metric']:>12.6f} "
              f"{row['iqr_valid']:>10.6f} "
              f"{row['failure_rate']*100:>6.1f}%")
    print(SEP)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark four VI-snapshot algorithms by RMSE distribution from "
            "parameter sweep CSVs. Produces publication-quality figures and a "
            "summary CSV."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sweep-dir", type=Path, default=_DEFAULT_SWEEP_DIR, metavar="DIR",
        help="Directory containing the four sweep CSV files.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUT_DIR, metavar="DIR",
        help="Directory to write all output files.",
    )
    parser.add_argument(
        "--dpi", type=int, default=300, metavar="DPI",
        help="Resolution of raster outputs (.png).",
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    args = build_arg_parser().parse_args()
    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    _apply_ieee_style()

    print("Algorithm Benchmark Analysis")
    print("=" * 50)
    print(f"  Sweep dir  : {args.sweep_dir}")
    print(f"  Output dir : {out_dir}")
    print()

    # Load data
    merged_valid, merged_all = load_and_merge(args.sweep_dir)

    # Statistics
    summary = compute_benchmark_stats(merged_valid, merged_all, args.sweep_dir)

    # Print rankings
    print_ranking_table(summary)

    # Export summary CSV
    csv_path = out_dir / "algorithm_benchmark_summary.csv"
    summary.to_csv(csv_path, index=False)
    print(f"  [CSV]    -> {csv_path}")

    # Figure 1: Violin plot
    fig_violin = build_violin_figure(merged_valid, merged_all, summary)
    for ext in ("png", "pdf"):
        p = out_dir / f"algorithm_rmse_violin.{ext}"
        fig_violin.savefig(p, dpi=args.dpi, bbox_inches="tight")
        print(f"  [Figure] -> {p}")
    plt.close(fig_violin)

    # Figure 2: Tradeoff scatter
    fig_tradeoff = build_tradeoff_figure(summary)
    for ext in ("png", "pdf"):
        p = out_dir / f"algorithm_tradeoff.{ext}"
        fig_tradeoff.savefig(p, dpi=args.dpi, bbox_inches="tight")
        print(f"  [Figure] -> {p}")
    plt.close(fig_tradeoff)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
