"""Temporal robustness evaluation.

Picks the best hyperparameters for each backbone algorithm from a sweep
directory, then applies those params to paired datasets measured at two
time-points (t=15 min: ADS1256 hardware CSV; t=30 min: testbench replay CSV).

For each (algorithm × wafer-point) cell the script computes:

    drift = |V_30 − V_15|

where V_t is the first snapshot voltage produced by the backbone on that CSV.
If a backbone produces no snapshot the cell is recorded as NaN and counted
toward the algorithm's **failure rate**.

Outputs
-------
software/plots/output/temporal_robustness/
    summary_table.csv        — mean drift, std drift, failure rate per algo
    drift_matrix.csv         — full (n_points × n_algos) drift values
    boxplot.png              — boxplot of |V_30 − V_15| per algorithm
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import types
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np

from ..config.config import SimulationConfig
from ..utils.backbone_factory import create_backbone
from ..utils.csv_replay import csv_logged_reader, csv_replay_reader
from ..utils.types import Sample, Snapshot

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALGO_SWEEP_MAP: Dict[str, str] = {
    "bocd": "waferIA6-bocd.csv",
    "derivative_integration": "waferIA6-derivative_integration.csv",
    "hysteresis": "waferIA6-hysteresis.csv",
    "stddev_window": "waferIA6-stddev_window.csv",
}

_DISPLAY_NAMES: Dict[str, str] = {
    "bocd": "BOCD",
    "derivative_integration": "Derivative",
    "hysteresis": "Hysteresis",
    "stddev_window": "StdDev",
}

# ---------------------------------------------------------------------------
# Sweep param loading
# ---------------------------------------------------------------------------


def _load_best_params(sweep_dir: Path) -> Dict[str, Dict[str, float]]:
    """Return {algo_name: {param: value}} for the best (row 0) of each sweep CSV.

    Row 0 is assumed to have the lowest RMSE (sweep CSVs are sorted ascending).
    """
    best: Dict[str, Dict[str, float]] = {}
    for algo, filename in _ALGO_SWEEP_MAP.items():
        path = sweep_dir / filename
        if not path.exists():
            log.warning("Sweep CSV not found for %s: %s — skipping algorithm", algo, path)
            continue
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                # Convert all numeric columns; skip non-numeric gracefully
                params: Dict[str, float] = {}
                for key, val in row.items():
                    try:
                        params[key] = float(val)
                    except (ValueError, TypeError):
                        pass
                best[algo] = params
                break  # only row 0 needed
    return best


# ---------------------------------------------------------------------------
# Backbone construction helpers
# ---------------------------------------------------------------------------


def _make_sim_config(sample_rate_hz: float, params: Dict[str, float], algo: str) -> SimulationConfig:
    """Build a SimulationConfig for the given algorithm with sweep-derived params."""
    defaults = SimulationConfig()

    # Pull window / duration / threshold from sweep params if present
    snapshot_window_s = params.get("snapshot_window_s", defaults.snapshot_window_s)
    snapshot_min_duration_s = params.get("min_duration_s", defaults.snapshot_min_duration_s)
    snapshot_std_threshold_v = params.get("std_threshold_v", defaults.snapshot_std_threshold_v)

    return SimulationConfig(
        sample_rate_hz=sample_rate_hz,
        snapshot_window_s=snapshot_window_s,
        snapshot_min_duration_s=snapshot_min_duration_s,
        snapshot_std_threshold_v=snapshot_std_threshold_v,
        snapshot_min_recording_s=defaults.snapshot_min_recording_s,
        gain=defaults.gain,
    )


def _make_args_namespace(params: Dict[str, float], algo: str) -> types.SimpleNamespace:
    """Build a SimpleNamespace that mimics argparse args for backbone-specific params."""
    ns = types.SimpleNamespace()

    if algo == "bocd":
        ns.bocd_hazard_rate = params.get("hazard_rate", 1.0 / 200.0)
        ns.bocd_mean0 = params.get("mean0", 0.0)
        ns.bocd_var0 = params.get("var0", 1.0)
        ns.bocd_varx = params.get("varx", 1e-6)
        ns.bocd_cp_reset_threshold = int(params.get("cp_reset_threshold", 5))

    elif algo == "hysteresis":
        ns.hysteresis_enter = params.get("enter_threshold_v", 1.0)
        ns.hysteresis_exit = params.get("exit_threshold_v", 0.8)

    elif algo == "derivative_integration":
        ns.di_dt_threshold = params.get("derivative_threshold", 0.005)
        ns.di_it_threshold = params.get("integration_threshold", 0.05)
        ns.di_leakage_factor = params.get("leakage_factor", 0.9)
        ns.di_iir_window = int(params.get("iir_window", 16))

    # stddev_window has no extra args beyond sim_config fields
    return ns


# ---------------------------------------------------------------------------
# CSV streaming helpers
# ---------------------------------------------------------------------------


def _stream_ads1256(csv_path: Path) -> Iterator[Sample]:
    """Yield (elapsed_s, measured_v, current_mA) from an ADS1256 logger CSV."""
    yield from csv_logged_reader(str(csv_path))


def _stream_testbench(csv_path: Path, sample_rate_hz: float) -> Iterator[Sample]:
    """Yield (timestamp_s, voltage_v, current_mA) from a testbench CSV."""
    yield from csv_replay_reader(str(csv_path), sample_rate_hz=sample_rate_hz)


# ---------------------------------------------------------------------------
# Backbone runner
# ---------------------------------------------------------------------------


def _first_snapshot_voltage(
    samples: Iterator[Sample],
    algo: str,
    sim_config: SimulationConfig,
    args_ns: types.SimpleNamespace,
) -> Optional[float]:
    """Run backbone on the sample stream and return the first snapshot voltage.

    Returns None if the backbone emits no snapshot.
    """
    backbone = create_backbone(algo, sim_config, args_ns)
    for sample in samples:
        snap: Optional[Snapshot] = backbone.update(sample)
        if snap is not None:
            return snap.voltage
    # Also check best_snapshot attribute (used by BOCD)
    if hasattr(backbone, "best_snapshot") and backbone.best_snapshot is not None:
        return backbone.best_snapshot.voltage
    return None


# ---------------------------------------------------------------------------
# Pair collection
# ---------------------------------------------------------------------------


def _collect_pairs(
    ads1256_dir: Path,
    testbench_dir: Path,
    ads1256_pattern: str,
    testbench_pattern: str,
    num_pairs: int = 6,
) -> List[Tuple[Path, Path]]:
    """Glob + sort both directories and zip into ordered (ads1256, testbench) pairs.

    If the glob matches more folders than ``num_pairs``, the *last* N entries
    (lexicographically = chronologically for timestamp-named folders) are used.
    """
    ads_candidates = sorted(ads1256_dir.glob(ads1256_pattern))
    # ads1256 entries are subdirectories; find the CSV inside each
    ads_csvs: List[Path] = []
    for entry in ads_candidates:
        if entry.is_dir():
            inner = sorted(entry.glob("*.csv"))
            if inner:
                ads_csvs.append(inner[0])
            else:
                log.warning("No CSV found inside %s — skipping", entry)
        elif entry.suffix == ".csv":
            ads_csvs.append(entry)

    # Trim to the last N if we matched too many
    if len(ads_csvs) > num_pairs:
        log.info(
            "ADS1256 glob matched %d entries; keeping last %d (most recent).",
            len(ads_csvs),
            num_pairs,
        )
        ads_csvs = ads_csvs[-num_pairs:]

    tb_csvs = sorted(testbench_dir.glob(testbench_pattern))

    if not ads_csvs:
        raise ValueError(f"No ADS1256 CSVs matched pattern '{ads1256_pattern}' under {ads1256_dir}")
    if not tb_csvs:
        raise ValueError(f"No testbench CSVs matched pattern '{testbench_pattern}' under {testbench_dir}")
    if len(ads_csvs) != len(tb_csvs):
        raise ValueError(
            f"ADS1256 file count ({len(ads_csvs)}) ≠ testbench file count ({len(tb_csvs)}). "
            "Check your --ads1256-pattern and --testbench-pattern."
        )

    return list(zip(ads_csvs, tb_csvs))


# ---------------------------------------------------------------------------
# Drift matrix computation
# ---------------------------------------------------------------------------


def _compute_drift_matrix(
    pairs: List[Tuple[Path, Path]],
    best_params: Dict[str, Dict[str, float]],
    sample_rate_hz: float,
) -> Tuple[List[str], List[str], np.ndarray, np.ndarray, np.ndarray]:
    """Return (point_labels, algo_labels, drift_matrix, v15_matrix, v30_matrix).

    drift_matrix shape: (n_points, n_algos), values are |V_30 - V_15| or NaN.
    v15_matrix shape: (n_points, n_algos), values are V_15 or NaN.
    v30_matrix shape: (n_points, n_algos), values are V_30 or NaN.
    """
    algos = list(best_params.keys())
    n_points = len(pairs)
    n_algos = len(algos)

    drift = np.full((n_points, n_algos), math.nan)
    v15_matrix = np.full((n_points, n_algos), math.nan)
    v30_matrix = np.full((n_points, n_algos), math.nan)
    point_labels = [f"IA{i + 1}" for i in range(n_points)]

    for pt_idx, (ads_csv, tb_csv) in enumerate(pairs):
        label = point_labels[pt_idx]
        for al_idx, algo in enumerate(algos):
            params = best_params[algo]
            sim_config = _make_sim_config(sample_rate_hz, params, algo)
            args_ns = _make_args_namespace(params, algo)

            # --- t=15 min: ADS1256 hardware CSV ---
            try:
                v15 = _first_snapshot_voltage(_stream_ads1256(ads_csv), algo, sim_config, args_ns)
            except Exception as exc:  # noqa: BLE001
                log.warning("Error running %s on ADS1256 %s: %s", algo, ads_csv.name, exc)
                v15 = None

            # Reset backbone (recreated inside _first_snapshot_voltage each call)
            args_ns2 = _make_args_namespace(params, algo)
            sim_config2 = _make_sim_config(sample_rate_hz, params, algo)

            # --- t=30 min: testbench CSV ---
            try:
                v30 = _first_snapshot_voltage(
                    _stream_testbench(tb_csv, sample_rate_hz), algo, sim_config2, args_ns2
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Error running %s on testbench %s: %s", algo, tb_csv.name, exc)
                v30 = None

            if v15 is not None:
                v15_matrix[pt_idx, al_idx] = v15
            if v30 is not None:
                v30_matrix[pt_idx, al_idx] = v30

            if v15 is None or v30 is None:
                log.warning(
                    "No snapshot for %s on point %s (V15=%s, V30=%s) — recording NaN",
                    _DISPLAY_NAMES.get(algo, algo),
                    label,
                    v15,
                    v30,
                )
            else:
                drift[pt_idx, al_idx] = abs(v30 - v15)

    return point_labels, algos, drift, v15_matrix, v30_matrix


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


def _build_summary(
    algos: List[str],
    drift: np.ndarray,
) -> List[Dict[str, object]]:
    """Compute per-algorithm mean drift, std drift, and failure rate."""
    rows = []
    n_points = drift.shape[0]
    for al_idx, algo in enumerate(algos):
        col = drift[:, al_idx]
        valid = col[~np.isnan(col)]
        n_failed = int(np.sum(np.isnan(col)))
        failure_rate = n_failed / n_points if n_points > 0 else math.nan
        rows.append(
            {
                "Algorithm": _DISPLAY_NAMES.get(algo, algo),
                "Mean Drift (V)": float(np.mean(valid)) if len(valid) > 0 else math.nan,
                "Std Drift (V)": float(np.std(valid, ddof=1)) if len(valid) > 1 else math.nan,
                "Failure Rate": f"{failure_rate:.0%}",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_summary(summary_rows: List[Dict[str, object]]) -> None:
    header = f"{'Algorithm':<22} {'Mean Drift (V)':>16} {'Std Drift (V)':>14} {'Failure Rate':>14}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for r in summary_rows:
        mean_str = f"{r['Mean Drift (V)']:.6f}" if not _is_nan(r["Mean Drift (V)"]) else "    N/A"
        std_str = f"{r['Std Drift (V)']:.6f}" if not _is_nan(r["Std Drift (V)"]) else "    N/A"
        print(f"{r['Algorithm']:<22} {mean_str:>16} {std_str:>14} {r['Failure Rate']:>14}")
    print(sep)


def _is_nan(v: object) -> bool:
    try:
        return math.isnan(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _save_summary_csv(out_dir: Path, summary_rows: List[Dict[str, object]]) -> Path:
    path = out_dir / "summary_table.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Algorithm", "Mean Drift (V)", "Std Drift (V)", "Failure Rate"])
        writer.writeheader()
        writer.writerows(summary_rows)
    return path


def _save_matrix_csv(
    path: Path,
    point_labels: List[str],
    algos: List[str],
    matrix: np.ndarray,
) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        display_algos = [_DISPLAY_NAMES.get(a, a) for a in algos]
        writer.writerow(["Point"] + display_algos)
        for pt_idx, label in enumerate(point_labels):
            row_vals = []
            for al_idx in range(len(algos)):
                v = matrix[pt_idx, al_idx]
                row_vals.append("" if math.isnan(v) else f"{v:.8f}")
            writer.writerow([label] + row_vals)
    return path


def _save_boxplot(
    out_dir: Path,
    algos: List[str],
    drift: np.ndarray,
    show: bool,
) -> Path:
    # Set IEEE style parameters via rcParams
    plt.rcParams.update({
        "font.family":        "serif",
        "font.serif":         ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size":          9,
        "axes.labelsize":     10,
        "axes.titlesize":     10,
        "xtick.labelsize":    8,
        "ytick.labelsize":    8,
        "lines.linewidth":    1.2,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "figure.facecolor":   "white",
        "axes.facecolor":     "white",
        "savefig.facecolor":  "white",
    })

    fig, ax = plt.subplots(figsize=(5.5, 4.0), dpi=300)

    display_algos = [_DISPLAY_NAMES.get(a, a) for a in algos]
    algo_colors = {
        "bocd": "#1f4e7d",
        "derivative_integration": "#1a6e3c",
        "hysteresis": "#8b1a1a",
        "stddev_window": "#8b5e00",
    }
    palette = [algo_colors.get(a, "#555555") for a in algos]

    # Collect data columns (NaN excluded from box but we show count)
    data_columns = [drift[:, al_idx] for al_idx in range(len(algos))]
    valid_columns = [col[~np.isnan(col)] for col in data_columns]

    positions = list(range(1, len(algos) + 1))

    bp = ax.boxplot(
        valid_columns,
        positions=positions,
        patch_artist=True,
        widths=0.45,
        medianprops=dict(color="black", linewidth=1.5),
        whiskerprops=dict(color="#555555", linewidth=1.2),
        capprops=dict(color="#555555", linewidth=1.2),
        flierprops=dict(marker="", alpha=0),
    )
    for patch, color in zip(bp["boxes"], palette):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
        patch.set_edgecolor("black")
        patch.set_linewidth(1.0)

    # Overlay individual dots with jitter
    rng = np.random.default_rng(42)
    for al_idx, (col, color) in enumerate(zip(data_columns, palette)):
        valid = col[~np.isnan(col)]
        if len(valid) == 0:
            continue
        jitter = rng.uniform(-0.12, 0.12, size=len(valid))
        ax.scatter(
            positions[al_idx] + jitter,
            valid,
            color=color,
            edgecolors="black",
            linewidths=0.6,
            s=35,
            zorder=5,
            alpha=0.8,
        )

    # Annotate failure counts
    for al_idx, col in enumerate(data_columns):
        n_nan = int(np.sum(np.isnan(col)))
        if n_nan > 0:
            ax.text(
                positions[al_idx],
                0.95,
                f"({n_nan} fail)",
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=8,
                color="#c0392b",
                fontweight="bold",
            )

    ax.set_xticks(positions)
    ax.set_xticklabels(display_algos)
    ax.set_ylabel("|V₃₀ − V₁₅|  (V)", labelpad=5)
    ax.set_xlabel("Algorithm", labelpad=5)
    ax.set_title("Temporal Robustness: Voltage Drift per Algorithm", loc="left", fontweight="bold", pad=8)
    
    # Tick parameters
    ax.tick_params(axis="both", which="both", direction="in", top=False, right=False, colors="black")
    
    for spine in ax.spines.values():
        spine.set_edgecolor("black")
        
    ax.yaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator())
    ax.grid(axis="y", which="major", color="gray", linestyle=":", linewidth=0.5, alpha=0.4)
    ax.grid(axis="y", which="minor", color="gray", linestyle=":", linewidth=0.3, alpha=0.2)

    fig.tight_layout()
    path = out_dir / "boxplot.png"
    fig.savefig(path, dpi=300, facecolor="white", bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    defaults = SimulationConfig()
    parser = argparse.ArgumentParser(
        description=(
            "Temporal robustness evaluation: compare snapshot voltages at t=15 min "
            "(ADS1256 hardware) vs t=30 min (testbench replay) for each backbone algorithm."
        )
    )
    parser.add_argument(
        "--sweep-dir",
        type=str,
        default="software/output/evaluate/waferIA6/sweep",
        help="Directory containing per-algorithm sweep CSVs (default: waferIA6 sweep folder).",
    )
    parser.add_argument(
        "--ads1256-dir",
        type=str,
        default="software/output/ads1256",
        help="Parent directory of ADS1256 volt_log sub-folders.",
    )
    parser.add_argument(
        "--testbench-dir",
        type=str,
        default="software/output/testbench",
        help="Directory containing waferIA#.csv testbench files.",
    )
    parser.add_argument(
        "--ads1256-pattern",
        type=str,
        default="volt_log_20260529_16*",
        help="Glob pattern to select ADS1256 sub-folders (matched inside --ads1256-dir).",
    )
    parser.add_argument(
        "--testbench-pattern",
        type=str,
        default="waferIA[1-6].csv",
        help="Glob pattern to select testbench CSVs (matched inside --testbench-dir).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="software/plots/output/temporal_robustness",
        help="Output directory for summary CSV and boxplot PNG.",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=float,
        default=defaults.sample_rate_hz,
        dest="sample_rate_hz",
        help="Sample rate (Hz) for synthetic timestamps in testbench CSVs.",
    )
    parser.add_argument(
        "--num-pairs",
        type=int,
        default=6,
        dest="num_pairs",
        help="Number of wafer-point pairs to use (takes the N most-recent ADS1256 folders).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        default=False,
        help="Display the boxplot interactively after saving.",
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sweep_dir = Path(args.sweep_dir)
    ads1256_dir = Path(args.ads1256_dir)
    testbench_dir = Path(args.testbench_dir)
    out_dir = Path(args.out_dir)

    # Timestamped sub-folder for this run
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = out_dir / run_tag
    run_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading best params from %s", sweep_dir)
    best_params = _load_best_params(sweep_dir)
    if not best_params:
        log.error("No sweep CSVs found. Check --sweep-dir.")
        return
    log.info("Algorithms loaded: %s", list(best_params.keys()))

    log.info("Collecting paired CSV files …")
    pairs = _collect_pairs(
        ads1256_dir, testbench_dir,
        args.ads1256_pattern, args.testbench_pattern,
        num_pairs=args.num_pairs,
    )
    log.info("Found %d wafer-point pairs", len(pairs))
    for i, (a, b) in enumerate(pairs):
        log.info("  IA%d: %s  ↔  %s", i + 1, a.name, b.name)

    log.info("Running backbones …")
    point_labels, algos, drift, v15, v30 = _compute_drift_matrix(pairs, best_params, args.sample_rate_hz)

    summary_rows = _build_summary(algos, drift)

    print("\n=== Temporal Robustness Summary ===")
    _print_summary(summary_rows)

    summary_path = _save_summary_csv(run_dir, summary_rows)
    drift_path = _save_matrix_csv(run_dir / "drift_matrix.csv", point_labels, algos, drift)
    v15_path = _save_matrix_csv(run_dir / "measured_voltages_ads1256.csv", point_labels, algos, v15)
    v30_path = _save_matrix_csv(run_dir / "measured_voltages_testbench.csv", point_labels, algos, v30)
    plot_path = _save_boxplot(run_dir, algos, drift, show=args.show)

    log.info("Summary table       → %s", summary_path)
    log.info("Drift matrix        → %s", drift_path)
    log.info("ADS1256 Voltages    → %s", v15_path)
    log.info("Testbench Voltages  → %s", v30_path)
    log.info("Boxplot             → %s", plot_path)


if __name__ == "__main__":
    main()
