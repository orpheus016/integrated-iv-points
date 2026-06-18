Four-point probe voltage simulation and snapshot capture.

## What is this
This folder contains a modular Python simulation that mimics four-point probe voltage
measurements. It generates a true voltage from current and resistance, applies realistic
transient response and noise, and then detects when the signal stabilizes so it can
capture a frozen snapshot of the measurement.

## File overview
- `config/config.py`
   - CLI defaults and tunables for simulation, serial timing, switching policy, and output routing.
- `backbones/base.py`
   - Abstract streaming interface: `update(sample) -> Optional[Snapshot]`.
- `backbones/stddev_window.py`
   - Sliding-window stability detector with incremental variance.
- `backbones/running_stat.py`
   - Running-stat snapshot strategy with the same streaming backbone contract.
- `backbones/baseline.py`
   - Baseline snapshot strategy built on the sliding-window stddev rule.
- `backbones/hysteresis.py`
   - Hysteresis snapshot strategy with enter/exit thresholds and dwell.
- `command/serial_commander.py`
   - Serial protocol state engine for ADS1256 hardware control and stage switching.
- `data_source/ads1256.py`
   - Hardware streaming generator for Arduino/ADS1256.
- `data_source/dummy.py`
   - Synthetic signal generator for smoke tests and local development.
- `data_source/settling.py`
   - Synthetic settling sequence for backbone testing.
- `data_source/worst_case.py`
   - Synthetic worst-case data source for stability experiments.
- `data_source/manual_capture.py`
   - Manual data-capture entrypoint.
- `data_source/instrument_meas.py`
   - Reference hardware capture example kept for comparison.
- `utils/csv_replay.py`
   - CSV replay generator for `voltage,current_mA` datasets.
- `utils/backbone_factory.py`
   - Shared backbone selection helper used by `main.py`, `scripts/evaluate.py`, and `scripts/integrate.py`.
- `utils/filters.py`
   - Moving average and optional low-pass filtering.
- `utils/logger.py`
   - CSV logging for measured, true, and snapshot values.
- `utils/math.py`
   - Shared math helpers for rolling mean/std/RMS calculations.
- `utils/types.py`
   - Frozen `Snapshot` data contract and shared sample alias.
- `utils/visualization.py`
   - Live plot and async plot wrapper.
- `main.py`
   - Real-time orchestration only: data source -> backbone -> logger/visualizer.
- `scripts/evaluate.py`
   - Offline evaluation over testbench CSVs.
- `scripts/integrate.py`
   - Library-style entrypoints for downstream systems.
- `scripts/ci_compliance.py`
   - Lightweight architecture and cleanup checker used by CI.
- `scripts/backbone_workflow.py`
   - Fail-fast helper that scaffolds backbone registry updates and runs compliance.
- `scripts/README.md`
   - Developer guide for script entrypoints and command examples.
- `tests/test_evaluate.py`
   - Smoke test for offline evaluation.
- `tests/test_async_visualizer.py`
   - Headless visualization test.
- `tests/test_baseline.py` and `tests/test_hysteresis.py`
   - Backbone behavior tests.

## Run from repo root
Examples showing common runs. Use `--help` for full CLI options.

### Live plotting with `main`

`software.main` can show a live plot while acquisition is running. The key flags are:

- `--plot-mode full` shows the rolling live trace, current buffer, and snapshot line while samples stream in.
- `--plot-mode comparison` keeps the final comparison-style view.
- `--live-plot` enables the GUI plotter (omit or `--no-live-plot` to disable).
- `--plot-update-hz` throttles how often the plot updates (lower values reduce GUI overhead).
- `--save-plot-on-interrupt` saves the final comparison image on `Ctrl+C` when a snapshot exists.
- `--plot-backend` is optional (use only if you need to force a backend like `TkAgg` or `QtAgg`).
- `--live-backbones` runs multiple backbones on the same stream and shows a live transient comparison.
- `--live-duration` sets how long live multi-backbone capture runs (defaults to `--max-measurement`).

The plot opens in the same process as `main`, so keep the terminal running until you stop the stream or the snapshot completes.

1. One-shot measurement using the default `running_stat` strategy:
   python -m software.main --source dummy --backbone running_stat --current 0.01 --resistance 1.5 \
      --snapshot-threshold 0.0004 --snapshot-window 2.0 --snapshot-min-duration 2.0

   If you need gain correction in the stored resistance, add `--gain <value>`.

   Live plotting version of the same run:
   python -m software.main --source dummy --backbone running_stat \
      --current 0.01 --resistance 1.5 --snapshot-threshold 0.0004 \
      --snapshot-window 2.0 --snapshot-min-duration 2.0 --plot-mode full --live-plot

2. Hysteresis-based snapshot with explicit enter/exit thresholds:
   python -m software.main --source dummy --backbone hysteresis \
      --hysteresis-enter 0.020 --hysteresis-exit 0.015 --snapshot-window 1.0

3. Replay a CSV testbench dataset and log outputs to `software/output/testbench`:
   python -m software.main --source csv --csv-path software/output/testbench/stable20mA.csv \
      --backbone running_stat --stop-on-snapshot

   Live plotting while replaying the CSV:
   python -m software.main --source csv --csv-path software/output/testbench/stable20mALONG.csv \
      --backbone baseline --plot-mode full --stop-on-snapshot --live-plot

   Single backbone on a single dataset:
   python -m software.scripts.evaluate --input software/output/testbench/stable20mA.csv \
      --backbones running_stat --out software/output/evaluate/running_stat-stable20mA

   Batch evaluate the whole testbench folder:
   python -m software.scripts.evaluate --input software/output/testbench \
      --backbones running_stat,stddev_window,baseline,hysteresis --out software/output/evaluate/batch

4. Use the hardware ADS1256 input (COM port configured via `--port`):
   python -m software.main --source serial --port COM5 --baud 115200 --backbone baseline \
      --plot-mode full --live-plot --plot-update-hz 15

   If you want the stream to keep running after the first stable snapshot, disable auto-stop:
   python -m software.main --source serial --port COM5 --baud 115200 --backbone baseline \
      --plot-mode full --live-plot --no-stop-on-snapshot

   Save a final comparison image even on manual interrupt:
   python -m software.main --source serial --port COM5 --baud 115200 --backbone baseline \
      --plot-mode full --live-plot --save-plot-on-interrupt

   Live multi-backbone comparison for a fixed duration:
   python -m software.main --source serial --port COM5 --baud 115200 \
      --live-backbones baseline,stddev_window,hysteresis,running_stat --live-duration 20 \
      --plot-mode full --live-plot

Notes:
- Snapshot detection strategies live in `software/backbones/` and implement `update(sample) -> Optional[Snapshot]`.
- `running_stat.py` is the import-safe running-stat backbone implementation; the legacy hyphenated helper file was removed so CI only sees valid modules.
- Runtime parameters and CLI defaults are centralized in `software/config/config.py`.
- Outputs are routed into `software/output/<source>/<run_name>/` to keep hardware and testbench logs separate.
- For live acquisition, `--plot-mode full` is the most useful setting because it shows the running trace instead of only the end-state comparison.
- When a snapshot exists and the run ends, the final comparison image is saved next to the CSV as `*_final.png`.
- Serial runs also save a combined transient plot next to the CSV as `<csv_stem>_transient.png`.
- Serial current switching is snapshot-driven: switching only evaluates on stable snapshots (or a forced snapshot after `--switch-max-settle`). A blanking window (`--switch-blanking`) resets filters and backbones after a stage change before stability checks resume.
- Voltage-based raise thresholds use per-stage hysteresis bands (`--switch-raise-low` and `--switch-raise-high`), while power-limit downshifts apply at all stages (`--switch-power-limit-mw`).
- Stop-on-snapshot can be gated after a stage switch using `--stop-holdoff` (seconds), `--stop-require-post-switch`, and `--stop-final-holdoff` to avoid stopping on the same snapshot that triggers a switch, including on the final stage.
- The preferred developer workflow lives in [CONTRIBUTING.md](../CONTRIBUTING.md) and [scripts README](scripts/README.md).

## Snapshot function: where it is and how it works
The core snapshot behavior is implemented in main.py inside the main loop:
- Rolling buffer collects filtered voltages.
- A rolling stddev check decides when the signal is stable.
- When stable long enough, a snapshot voltage is captured and frozen.
- If stop-on-snapshot is enabled, the loop exits and a final comparison view is shown.

Key variables to look for in main.py:
- `MovingAverageFilter`
- `LowPassFilter`
- `create_backbone(...)`
- `mean_rms(...)`
- `backbone.update((timestamp, voltage, current_mA))`

## How to integrate snapshot into the larger FPP software
Use this as the reference pipeline:
1. Identify your measured voltage stream (raw or filtered).
2. Insert the same rolling/stability logic used by the selected backbone, not a second copy in the orchestration loop.
3. When stddev <= threshold for a minimum duration, compute a snapshot value.
4. Freeze the snapshot and stop acquisition if desired.
5. Display the snapshot next to the true/reference value.

Suggested integration steps:
1. Port the snapshot block from main.py into your acquisition loop.
2. Feed the block with filtered voltage for better stability.
3. Keep the parameters configurable:
    - snapshot_window_s
    - snapshot_std_threshold_v
    - snapshot_min_duration_s
4. Use stop-on-snapshot when you want a one-shot measurement.
5. For continuous monitoring, switch to snapshot-mode continuous.

## Common tuning tips
- If snapshot never triggers, increase snapshot threshold or enable low-pass filtering.
- If snapshot triggers too early, increase snapshot window or min duration.
- For noisy environments, use a lower low-pass alpha (e.g., 0.05 to 0.2).

## Capture Data

### Manual Capture

```bash
# Execute with default config settings (COM12, 115200 baud)
python -m software.data_source.manual_capture
# Override targets using the integrated arg_parser flags
python -m software.data_source.manual_capture --port COM5 --baud 115200 --filename step_response_test
```

You might want to use manual capture to test the VI capture algorithm on specific datasets, or to collect custom datasets for testing and development. Alternatively, you can use the algorithmic based data_source to generate synthetic data with specific characteristics (e.g. noise, transient response, line interference) to test the snapshot algorithm under controlled conditions.

Use the csv_replay generator to replay existing datasets in the same format as the ads1256 reader, which is what the snapshot algorithm is currently built and tested on.

### Auto Capture

You can use ads1256 capture for more automated data collection. this data_source is going to be integrated into the automated four point probe system measurement

## Offline evaluation (evaluate.py)

You can run the offline evaluator against either recorded CSVs or the built-in synthetic generators (`dummy`, `settling`, `worst_case`). The evaluator is useful for batch comparisons and produces a per-run PNG and a `*-metrics.csv` file with simple snapshot metrics and a marker for the decided snapshot.

Examples (run from the repo root):

- Dummy source (5 s at 50 Hz, compare two backbones):
- Dummy source (5 s at 50 Hz, compare the new running-stat backbone against the existing strategies):

```bash
python -m software.scripts.evaluate --source dummy \
   --max-measurement 5 --sample-rate 50 \
   --backbones running_stat,stddev_window,baseline \
   --out software/output/evaluate
```

- Settling source (3 s at 100 Hz, baseline only):

```bash
python -m software.scripts.evaluate --source settling \
   --max-measurement 3 --sample-rate 100 \
   --backbones baseline \
   --out software/output/evaluate
```

- Worst-case source (10 s, full compare):

```bash
python -m software.scripts.evaluate --source worst_case \
   --max-measurement 10 --sample-rate 50 \
   --backbones running_stat,stddev_window,baseline,hysteresis \
   --out software/output/evaluate
```

- Manual Capture
```bash
python -m software.scripts.evaluate --input software/output/testbench/stable20mALONG.csv --backbones baseline --out software/output/evaluate/baseline-stable20mALONG
```

- Transient playback with animation shown on screen only:
```bash
python -m software.scripts.evaluate --input software/output/testbench/stable20mALONG.csv \
   --backbones running_stat,baseline,stddev_window,hysteresis \
   --evaluation-plot-mode transient --evaluation-animate --evaluation-animation-output screen \
   --out software/output/evaluate/transient-demo
```

- Transient playback exported to GIF or video:
```bash
python -m software.scripts.evaluate --input software/output/testbench/stable20mALONG.csv \
   --backbones running_stat,baseline,stddev_window,hysteresis \
   --evaluation-plot-mode transient --evaluation-animate --evaluation-animation-output gif \
   --out software/output/evaluate/transient-gif
```

Key flags:
- `--source`: `csv`, `dummy`, `settling`, or `worst_case`.
- `--max-measurement`: maximum generator duration (seconds) for synthetic sources.
- `--sample-rate`: sample frequency used by synthetic generators.
- `--backbones`: comma-separated backbone names to run (e.g. `running_stat,baseline`).
- `--show`: display interactive plots (omit for CI/headless runs).
- `--evaluation-plot-mode`: `comparison` for IV plots or `transient` for time-based playback.
- `--evaluation-animate`: enable incremental playback in transient mode.
- `--evaluation-animation-output`: `screen`, `gif`, or `video` when animation is enabled.
- `--evaluation-animation-fps`: frame rate used for exported animation files.

Outputs created:
- `--out`/`<name>.png` — IV comparison plot, or transient plot when `--evaluation-plot-mode transient` is selected.
- `--out`/`<name>.gif` or `--out`/`<name>.mp4` — exported animation when the output mode is set accordingly.
- `--out`/`<name>-metrics.csv` — CSV summary with decided snapshot metadata and metrics (RMSE, MAE, MaxAbs).
- `software/scripts/backbone_workflow.py` can scaffold registry updates for a new backbone name, create a module stub if needed, and then run compliance plus tests.

Programmatic usage (call helpers directly):

```python
from software.config.config import build_arg_parser, build_simulation_config
from software.utils.evaluate_helpers import build_source_iterator_eval, evaluate_samples

args = build_arg_parser().parse_args(['--source','dummy','--max-measurement','2'])
sim = build_simulation_config(args)
samples = build_source_iterator_eval('dummy', sim, args)
data = evaluate_samples(samples, ['baseline'], sim, args)
```

Pointers:
- CLI defaults and all flags live in `software/config/config.py`.
- Reusable evaluation utilities are in `software/utils/evaluate_helpers.py`.
- Use `software/utils/backbone_factory.py` to construct backbones consistently across `main.py` and evaluation scripts.

### Output Folder Structure

output offline eval structure
```bash
output/evaluate/[data_source(.py/.csv)]/
|
-- transient-demo
|	|
|	-- [backbone name] (specific transient backbone)
|
-- [backbone name] (specific static backbone)
|
-- .png and.csv of all backbone
```

output/ads1256 for online evaluation with hardware

output/testbench for manual capture dataset from hardware

## CI Contract

TBA