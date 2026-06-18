# Contributing

This repository uses a Windows CI runner and a lightweight compliance checker to keep the software layout aligned with `copilot-instructions.md`.

## CI Contract

Every pull request should pass the same checks that run in GitHub Actions:

```powershell
$env:PYTHONPATH="."
$env:MPLBACKEND="Agg"
python -m pytest -q
python software/scripts/ci_compliance.py
```

The CI workflow runs on `windows-latest` and uses the Agg matplotlib backend so tests stay headless.

## Local Preflight

Before opening a PR, run the same checks locally and keep the output clean:

1. Install dependencies used by the software and tests.
2. Run the test suite.
3. Run the compliance checker.
4. Update the docs if you changed CLI flags, scripts, or file locations.
5. When adding a new backbone, use `software/scripts/backbone_workflow.py <name>` to scaffold the registry changes, then rerun the same checks locally.

Run the suite from the repository root so paths match CI:

```powershell
$env:PYTHONPATH="."
$env:MPLBACKEND="Agg"
python -m pytest -q
python software/scripts/ci_compliance.py
```

## Test Discipline

- Prefer deterministic tests.
- Keep default tests hardware-free.
- Add or update tests when you change backbone behavior, CSV replay behavior, or orchestration logic.
- Keep fixtures small and readable.

## How to Write Tests

Create new test files under `software/tests/` and name them `test_*.py` so `pytest` discovers them automatically.

Good patterns for this repository:

- Use `tmp_path` for files the test creates.
- Use `monkeypatch` when a test needs to isolate matplotlib, serial I/O, or other external state.
- Prefer bundled CSV fixtures from `software/output/testbench/` for offline evaluation tests.
- Keep hardware-specific behavior out of the default test suite unless the test is fully mocked.
- Keep one behavior per test file when practical so failures are easy to localize.

Example structure:

1. Arrange a small fixture or in-memory input.
2. Act by calling the backbone, script helper, or evaluator.
3. Assert on the returned snapshot, generated metrics, or output files.

## Breaking Changes

If you change any of these areas, update tests and docs together:

- `software/backbones/`
- `software/data_source/`
- `software/utils/`
- `software/scripts/evaluate.py`
- `software/scripts/integrate.py`
- `software/utils/types.py`

## Pull Request Checklist

- Tests added or updated.
- Compliance script passes locally.
- README or script docs updated if CLI usage changed.
- CI remains Windows-compatible.