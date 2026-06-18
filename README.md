# four-point-probe
Four point probe for semiconductor instrumentation system

## Software: voltage simulation pipeline

This repo includes a modular Python simulation for voltage acquisition with
filters, live plotting, and CSV logging. It is designed to be swapped later with
ADS1256 serial input from Arduino.

## Development

If you plan to change code, start with:

- [CONTRIBUTING.md](CONTRIBUTING.md) for the CI contract, local preflight, and PR checklist.
- [software/scripts/README.md](software/scripts/README.md) for `evaluate`, `integrate`, and the compliance checker.
- [software/README.md](software/README.md) for the software module overview and run examples.
- `CONTRIBUTING.md` also explains how to write new tests under `software/tests/` and run them from the repo root.

### Setup

Install dependencies:

```bash
pip install matplotlib
```

Optional (for future ADS1256 serial input):

```bash
pip install pyserial
```

### Run

From the repo root:

```bash
python -m software.main
```

Example with custom settings:

```bash
python -m software.main --sample-rate 100 --window-seconds 8 --noise 0.0005 --step
```

## Offline data paths

There are two ways to work with recorded CSV data:

1. Replay a CSV through the live runtime when you want the same pipeline as hardware, including the backbone, logger, and visualizer:

```bash
python -m software.main --source csv --csv-path software/output/testbench/stable20mA.csv --backbone baseline
```

2. Run offline evaluation when you want metrics and snapshot comparison without hardware commands or the live plot loop:

```bash
python -m software.scripts.evaluate --input software/output/testbench/stable20mA.csv --backbones baseline --out software/output/evaluate/baseline-stable20mA
```

The offline evaluator writes a metrics CSV with the decided snapshot fields, marks that chosen snapshot with a star in the plot, and keeps the result separate from the live runtime output.

The default snapshot recording gate is configured in [software/config/config.py](software/config/config.py), including the minimum recording duration used before a backbone may decide on a VI snapshot.

## Serial protocol and CLI

Hardware integration uses a small text protocol implemented by the Arduino firmware and
managed by `software/command/serial_commander.py`.

Framing markers (exact strings):

- `*STREAM_START` — emitted by the Arduino to mark stream beginning
- `*STREAM_STOP` — emitted by the Arduino to mark stream termination

Control commands sent from host to Arduino (single ASCII characters):

- `R` — reset device
- `C` — start streaming samples
- `s` — stop streaming
- `iN` — set current stage to `N` (e.g. `i2`)

The serial reader expects CSV-style measurement lines containing `voltage,current_mA`.

Common CLI execution examples:

- Replay testbench CSVs and write evaluation results:
	python -m software.scripts.evaluate --input software/output/testbench --out results/

Single backbone on single dataset (example):
	python -m software.scripts.evaluate \
		--input software/output/testbench/stable20mA.csv \
		--backbones baseline \
		--out results/single_baseline_stable20mA
- Run main with hardware ADS1256 on COM5:
	python -m software.main --source serial --port COM5 --baud 115200 --backbone baseline
- Run headless evaluation from Python:
	python -c "from software.scripts.evaluate import main; main(['--input','software/output/testbench'])"

See `software/config/config.py` for all CLI defaults and flags (backbone selection, hysteresis thresholds, plot mode, etc.).
