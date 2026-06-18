"""
signal_quality.py
─────────────────
Evaluates signal quality (Coefficient of Variation, SNR) for four-point probe
voltage measurements taken under different HF-etch conditions.

Metrics
───────
  CV  = (std_plateau / |mean_full|) × 100     [%]
  SNR = 20 · log10(|mean_full| / std_plateau)  [dB]

  std_plateau  : standard deviation of the trailing --plateau-pct % of samples
  mean_full    : mean of all samples (DC reading representing sheet resistance)

Output
──────
  software/plots/output/signal_quality/signal_quality_figure.png
  software/plots/output/signal_quality/signal_quality_metrics.csv

Usage
─────
  python software/plots/signal_quality.py
  python software/plots/signal_quality.py --plateau-pct 25
  python software/plots/signal_quality.py --dpi 600 --output-dir custom/path
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from typing import NamedTuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Signal definitions  (order = top-to-bottom in the stacked figure)
# The list is intentional: best→worst so the narrative reads naturally.
# ─────────────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent.parent / "output" / "testbench"

SIGNAL_DEFS: list[dict] = [
    {
        "csv":   _BASE / "waferIA4.csv",
        "label": "HF:DI 1:10 (Fresh)",
        "color": "#1a6e3c",          # dark green — best condition
    },
    {
        "csv":   _BASE / "waferHF1-20.csv",
        "label": "HF:DI 1:20",
        "color": "#1f4e7d",          # dark blue — moderate condition
    },
    {
        "csv":   _BASE / "waferHF1-10-7days.csv",
        "label": "HF:DI 1:10 (7-day oxide growth)",
        "color": "#8b5e00",          # amber — degraded
    },
    {
        "csv":   _BASE / "waferHF0-1.csv",
        "label": "No HF (oxide layer)",
        "color": "#8b1a1a",          # dark red — worst condition
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Data contracts
# ─────────────────────────────────────────────────────────────────────────────
class SignalMetrics(NamedTuple):
    label: str
    n_samples: int
    mean_full: float
    std_plateau: float
    cv_pct: float
    snr_db: float
    plateau_start: int   # sample index where plateau window begins


# ─────────────────────────────────────────────────────────────────────────────
# Core computation
# ─────────────────────────────────────────────────────────────────────────────
def _load_voltage(csv_path: Path) -> np.ndarray:
    """Load voltage column, dropping NaN/empty trailing rows."""
    df = pd.read_csv(csv_path)
    return df["voltage"].dropna().to_numpy(dtype=float)


def compute_metrics(
    voltage: np.ndarray,
    label: str,
    plateau_pct: float,
) -> SignalMetrics:
    """
    Compute CV and SNR for a single voltage trace.

    Parameters
    ----------
    voltage     : 1-D array of voltage samples
    label       : human-readable condition name
    plateau_pct : percentage of trailing samples to treat as the stable plateau
    """
    n = len(voltage)
    plateau_n = max(1, int(math.ceil(n * plateau_pct / 100.0)))
    plateau_start = n - plateau_n

    mean_full    = float(np.mean(voltage))
    plateau_vals = voltage[plateau_start:]
    std_plateau  = float(np.std(plateau_vals, ddof=1))

    abs_mean = abs(mean_full)

    # Guard: if mean ≈ 0 (unstable/no HF), CV is very large and SNR is -∞
    if abs_mean < 1e-9:
        cv_pct = float("inf")
        snr_db = float("-inf")
    else:
        cv_pct = (std_plateau / abs_mean) * 100.0
        if std_plateau < 1e-12:
            snr_db = float("inf")
        else:
            snr_db = 20.0 * math.log10(abs_mean / std_plateau)

    return SignalMetrics(
        label=label,
        n_samples=n,
        mean_full=mean_full,
        std_plateau=std_plateau,
        cv_pct=cv_pct,
        snr_db=snr_db,
        plateau_start=plateau_start,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plotting
# ─────────────────────────────────────────────────────────────────────────────
def _apply_ieee_style() -> None:
    """Apply IEEE conference paper–style rcParams."""
    plt.rcParams.update({
        # Font
        "font.family":        "serif",
        "font.serif":         ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size":          9,
        "axes.labelsize":     10,
        "axes.titlesize":     10,
        "xtick.labelsize":    8,
        "ytick.labelsize":    8,
        "legend.fontsize":    8,
        # Lines
        "lines.linewidth":    0.9,
        "lines.markersize":   3,
        # Layout
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.grid":          True,
        "grid.linestyle":     ":",
        "grid.alpha":         0.45,
        "grid.linewidth":     0.5,
        # Figure
        "figure.facecolor":   "white",
        "axes.facecolor":     "white",
        "savefig.facecolor":  "white",
    })


def _format_metric(value: float, fmt: str, fallback: str) -> str:
    """Format a metric value, substituting a fallback string for inf/-inf."""
    if not math.isfinite(value):
        return fallback
    return fmt.format(value)


def build_figure(
    voltage_arrays: list[np.ndarray],
    metrics_list: list[SignalMetrics],
    colors: list[str],
    plateau_pct: float,
) -> plt.Figure:
    """
    Build the stacked 4-panel IEEE-style figure.

    Each panel shows:
      • Full raw voltage trace (solid line)
      • Shaded + hatched plateau window
      • Horizontal dashed line at mean_full
      • Inset text box with CV and SNR
    """
    n_signals = len(voltage_arrays)
    fig_height = 2.5 * n_signals   # ~2.5 inches per panel
    fig, axes = plt.subplots(
        n_signals, 1,
        figsize=(7.16, fig_height),   # 7.16 in = standard IEEE double-column
        sharex=False,
        dpi=300,
    )
    if n_signals == 1:
        axes = [axes]

    for ax, voltage, metrics, color in zip(axes, voltage_arrays, metrics_list, colors):
        sample_idx = np.arange(len(voltage))

        # ── Raw trace ────────────────────────────────────────────────────────
        ax.plot(
            sample_idx,
            voltage,
            color=color,
            linewidth=0.85,
            zorder=3,
            label="Measured voltage",
        )

        # ── Plateau shading (hatched for B&W print safety) ──────────────────
        p_start = metrics.plateau_start
        ax.axvspan(
            p_start,
            len(voltage) - 1,
            alpha=0.12,
            facecolor=color,
            hatch="///",
            edgecolor=color,
            linewidth=0.0,
            label=f"Stable plateau (last {plateau_pct:.0f}%)",
            zorder=1,
        )
        ax.axvline(
            x=p_start,
            color=color,
            linestyle="--",
            linewidth=0.9,
            alpha=0.7,
            zorder=2,
        )

        # ── Mean line ────────────────────────────────────────────────────────
        ax.axhline(
            y=metrics.mean_full,
            color="black",
            linestyle="--",
            linewidth=0.75,
            alpha=0.7,
            label=f"Mean = {metrics.mean_full:.4f} V",
            zorder=4,
        )

        # ── Annotation box ───────────────────────────────────────────────────
        cv_str  = _format_metric(metrics.cv_pct,  "{:.2f}%", "inf (unstable)")
        snr_str = _format_metric(metrics.snr_db,  "{:.1f} dB", "-inf (unstable)")
        annot = (
            f"CV = {cv_str}\n"
            f"SNR = {snr_str}"
        )
        ax.text(
            0.985, 0.95,
            annot,
            transform=ax.transAxes,
            fontsize=8,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="white",
                edgecolor=color,
                linewidth=0.8,
                alpha=0.9,
            ),
            zorder=5,
        )

        # ── Panel title & labels ─────────────────────────────────────────────
        ax.set_title(metrics.label, loc="left", fontweight="bold", pad=3)
        ax.set_ylabel("Voltage (V)", labelpad=4)
        ax.legend(loc="upper left", frameon=True, framealpha=0.85, edgecolor="0.7")

        # ── Y-axis: add a small margin around the data ───────────────────────
        v_min, v_max = voltage.min(), voltage.max()
        margin = max((v_max - v_min) * 0.08, 0.05)
        ax.set_ylim(v_min - margin, v_max + margin)
        ax.set_xlim(0, len(voltage) - 1)

    # Shared x-label on bottom panel only
    axes[-1].set_xlabel("Sample index", labelpad=4)

    fig.suptitle(
        "Four-Point Probe Voltage: Signal Quality Under Different HF-Etch Conditions",
        fontsize=10,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout(rect=[0, 0, 1, 1])
    return fig


def build_combined_figure(
    voltage_arrays: list[np.ndarray],
    metrics_list: list[SignalMetrics],
    colors: list[str],
) -> plt.Figure:
    """
    Build a single-panel figure where all signals are overlaid,
    mean-shifted to 0 V, and truncated to the last 228 samples.
    """
    fig, ax = plt.subplots(figsize=(7.16, 3.5), dpi=300)
    
    n_samples = 228
    
    for voltage, metrics, color in zip(voltage_arrays, metrics_list, colors):
        # Take last 228 samples
        tail_voltage = voltage[-n_samples:] if len(voltage) >= n_samples else voltage
        idx = np.arange(len(tail_voltage))
        
        # Mean shift
        mean_tail = np.mean(tail_voltage)
        shifted = tail_voltage - mean_tail
        
        ax.plot(
            idx,
            shifted,
            color=color,
            linewidth=1.2,
            alpha=0.85,
            label=metrics.label,
        )
        
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.5, zorder=1)
    
    ax.set_title("Signal Noise Comparison (Mean-Shifted, Last 228 Samples)", loc="left", fontweight="bold", pad=5)
    ax.set_xlabel("Sample index (Trailing)", labelpad=4)
    ax.set_ylabel("Voltage deviation from mean (V)", labelpad=4)
    ax.legend(loc="best", frameon=True, framealpha=0.85, edgecolor="0.7")
    
    ax.set_xlim(0, n_samples - 1)
    
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# CSV summary export
# ─────────────────────────────────────────────────────────────────────────────
def export_metrics_csv(
    metrics_list: list[SignalMetrics],
    out_path: Path,
) -> None:
    """Write a tidy summary CSV suitable for inclusion in a paper table."""
    rows = []
    for m in metrics_list:
        rows.append({
            "Condition":            m.label,
            "N samples":            m.n_samples,
            "Mean voltage (V)":     f"{m.mean_full:.6f}",
            "Plateau std (V)":      f"{m.std_plateau:.6f}",
            "CV (%)":               f"{m.cv_pct:.4f}" if math.isfinite(m.cv_pct) else "inf",
            "SNR (dB)":             f"{m.snr_db:.2f}"  if math.isfinite(m.snr_db) else "-inf",
            "Plateau start sample": m.plateau_start,
        })
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"  [CSV]    -> {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate signal quality (CV, SNR) for four-point probe voltage signals "
            "under different HF-etch conditions and produce a publication-ready figure."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--plateau-pct",
        type=float,
        default=30.0,
        metavar="PCT",
        help="Percentage of trailing samples to treat as the stable plateau window.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output" / "signal_quality",
        metavar="DIR",
        help="Directory to write the figure and metrics CSV.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        metavar="DPI",
        help="Resolution of the saved figure.",
    )
    parser.add_argument(
        "--fig-name",
        type=str,
        default="signal_quality_figure.png",
        metavar="NAME",
        help="Filename for the saved figure.",
    )
    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    args = build_arg_parser().parse_args()

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    _apply_ieee_style()

    print("Four-Point Probe Signal Quality Evaluation")
    print("=" * 50)
    print(f"  Plateau window : last {args.plateau_pct:.0f}% of samples")
    print(f"  Output dir     : {out_dir}")
    print()

    voltage_arrays: list[np.ndarray] = []
    metrics_list:   list[SignalMetrics] = []
    colors:         list[str] = []

    for sig in SIGNAL_DEFS:
        csv_path: Path = sig["csv"]
        label:    str  = sig["label"]
        color:    str  = sig["color"]

        if not csv_path.is_file():
            raise FileNotFoundError(
                f"CSV not found: {csv_path}\n"
                "Check that the testbench output directory contains the expected files."
            )

        voltage = _load_voltage(csv_path)
        metrics = compute_metrics(voltage, label, args.plateau_pct)

        cv_str  = _format_metric(metrics.cv_pct, "{:.4f}%", "inf (mean~0)")
        snr_str = _format_metric(metrics.snr_db, "{:.2f} dB", "-inf (mean~0)")

        print(f"  [{label}]")
        print(f"    N samples     : {metrics.n_samples}")
        print(f"    Mean voltage  : {metrics.mean_full:+.6f} V")
        print(f"    Plateau std   : {metrics.std_plateau:.6f} V  "
              f"(plateau start = sample {metrics.plateau_start})")
        print(f"    CV            : {cv_str}")
        print(f"    SNR           : {snr_str}")
        print()

        voltage_arrays.append(voltage)
        metrics_list.append(metrics)
        colors.append(color)

    # ── Figure ───────────────────────────────────────────────────────────────
    fig = build_figure(voltage_arrays, metrics_list, colors, args.plateau_pct)
    fig_path = out_dir / args.fig_name
    fig.savefig(fig_path, dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Figure] -> {fig_path}")

    # -- Combined Figure ------------------------------------------------------
    fig_combined = build_combined_figure(voltage_arrays, metrics_list, colors)
    combined_path = out_dir / "signal_quality_combined.png"
    fig_combined.savefig(combined_path, dpi=args.dpi, bbox_inches="tight")
    plt.close(fig_combined)
    print(f"  [Figure] -> {combined_path}")

    # -- Metrics CSV ----------------------------------------------------------
    csv_out = out_dir / "signal_quality_metrics.csv"
    export_metrics_csv(metrics_list, csv_out)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
