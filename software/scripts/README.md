# Scripts Guide

This folder contains the repository's developer-facing entrypoints.

## `backbone_workflow.py`

Scaffold a new backbone, update the registry files, and run compliance.

Dry-run example:

```powershell
python software/scripts/backbone_workflow.py running_stat --dry-run
```

Apply changes and run compliance:

```powershell
python software/scripts/backbone_workflow.py running_stat
```

The helper updates `software/config/config.py`, `software/utils/backbone_factory.py`, and `software/backbones/__init__.py`, then runs `software/scripts/ci_compliance.py`. If a matching `software/tests/test_<name>.py` file exists, it runs that test file too.

## `evaluate.py`

Offline evaluation over CSV testbench data.

Typical single-dataset, single-backbone run:

```powershell
python -m software.scripts.evaluate --input software/output/testbench/stable20mA.csv --backbones baseline --out software/output/evaluate/baseline-stable20mA
```

Batch run over the full testbench folder:

```powershell
python -m software.scripts.evaluate --input software/output/testbench --backbones stddev_window,baseline,hysteresis --out software/output/evaluate/batch
```

The script reads CSV replay data from `software/utils/csv_replay.py`, runs each backbone in isolation, and writes PNG and CSV summary outputs.

If your measurements need gain correction, pass `--gain <value>` so the evaluator and `software.main` use the same resistance formula.

Note: `evaluate.py` also supports the built-in synthetic sources (`dummy`, `settling`, `worst_case`) and uses reusable helpers in `software/utils/evaluate_helpers.py`. Backbone construction is delegated to `software/utils/backbone_factory.py`.

For transient behavior analysis, use `--evaluation-plot-mode transient`. You can leave animation screen-only with `--evaluation-animation-output screen`, or export it with `--evaluation-animation-output gif` or `--evaluation-animation-output video`.

Example transient run with multiple backbones:

```powershell
python -m software.scripts.evaluate --input software/output/testbench/stable20mALONG.csv --backbones running_stat,baseline,stddev_window,hysteresis --evaluation-plot-mode transient --evaluation-animate --evaluation-animation-output screen --out software/output/evaluate/transient-demo
```

## `integrate.py`

Programmatic API for downstream use.

Example imports:

```python
from software.scripts.integrate import create_backbone, create_commander, run_pipeline
```

Use `create_backbone(...)` when you need a repository-consistent backbone factory, `create_commander(...)` when you need hardware control, and `run_pipeline(...)` for a small streaming loop that writes snapshots through `CsvLogger`.

## `ci_compliance.py`

Lightweight architecture check used by CI.

Run it directly:

```powershell
python software/scripts/ci_compliance.py
```

The checker validates the current repository shape against `copilot-instructions.md`, including `Snapshot`, backbone inheritance, CSV replay imports, duplicate helper cleanup, and the `add_argument` location rule.