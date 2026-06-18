"""Helper for scaffolding a new backbone and validating the repository contract.

This script is intentionally narrow: it updates the small set of repository files
that declare backbone names and then runs the lightweight compliance checker.
It is meant to reduce repetitive manual edits when exploring new snapshot
strategies on Windows.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "software" / "config" / "config.py"
FACTORY_PATH = ROOT / "software" / "utils" / "backbone_factory.py"
INIT_PATH = ROOT / "software" / "backbones" / "__init__.py"
BACKBONES_DIR = ROOT / "software" / "backbones"


@dataclass(frozen=True)
class WorkflowArgs:
    name: str
    class_name: str
    default_backbone: str
    dry_run: bool
    skip_tests: bool


def _pascal_case(name: str) -> str:
    parts = [part for part in name.replace("-", "_").split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _replace_once(text: str, old: str, new: str, path: Path) -> str:
    if old not in text:
        raise ValueError(f"expected to find target text in {path}: {old!r}")
    return text.replace(old, new, 1)


def _update_config(text: str, backbone_name: str, default_backbone: str) -> str:
    text = _replace_once(
        text,
        '    backbone: str = "running_stat"',
        f'    backbone: str = "{default_backbone}"',
        CONFIG_PATH,
    )
    old_choices = '    parser.add_argument("--backbone", choices=["running_stat", "stddev_window", "baseline", "hysteresis"], default=defaults.backbone)'
    if backbone_name not in old_choices:
        updated_choices = '    parser.add_argument("--backbone", choices=["running_stat", "stddev_window", "baseline", "hysteresis", "' + backbone_name + '"], default=defaults.backbone)'
        text = _replace_once(text, old_choices, updated_choices, CONFIG_PATH)
    return text


def _update_factory(text: str, backbone_name: str, class_name: str) -> str:
    import_line = f"from ..backbones.{backbone_name} import {class_name}"
    if import_line not in text:
        anchor = 'from ..backbones.hysteresis import HysteresisBackbone\n'
        text = _replace_once(text, anchor, anchor + import_line + "\n", FACTORY_PATH)

    if f'if name == "{backbone_name}":' not in text:
        anchor = '    if name == "baseline":\n        return BaselineBackbone(max(2, window_samples), sim_config.snapshot_std_threshold_v, min_stable_samples, min_recording_samples)\n\n'
        insertion = (
            anchor
            + f'    if name == "{backbone_name}":\n'
            + f'        return {class_name}(max(2, window_samples), sim_config.snapshot_std_threshold_v, min_stable_samples, min_recording_samples)\n\n'
        )
        text = _replace_once(text, anchor, insertion, FACTORY_PATH)

    return text


def _update_init(text: str, backbone_name: str, class_name: str) -> str:
    import_line = f"from .{backbone_name} import {class_name}"
    if import_line not in text:
        anchor = "from .baseline import BaselineBackbone\n"
        text = _replace_once(text, anchor, anchor + import_line + "\n", INIT_PATH)

    export_name = f'"{class_name}"'
    if export_name not in text:
        anchor = '"BaselineBackbone"]\n'
        replacement = '"BaselineBackbone", "' + class_name + '"]\n'
        text = _replace_once(text, anchor, replacement, INIT_PATH)

    return text


def _create_module(module_path: Path, class_name: str) -> None:
    if module_path.exists():
        return
    module_path.write_text(
        f'''"""Streaming snapshot backbone scaffold for {class_name}."""\n\nfrom __future__ import annotations\n\nfrom typing import Optional\n\nfrom .base import BaseBackbone\nfrom ..utils.types import Sample, Snapshot\n\n\nclass {class_name}(BaseBackbone):\n    """Implement incremental snapshot detection for the {class_name} strategy."""\n\n    def update(self, sample: Sample) -> Optional[Snapshot]:\n        raise NotImplementedError\n\n    def reset(self) -> None:\n        self._samples_seen = 0\n''',
        encoding="utf-8",
    )


def _write_file(path: Path, text: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] would update {path}")
        return
    path.write_text(text, encoding="utf-8")


def _run_command(args: list[str]) -> int:
    completed = subprocess.run(args, cwd=ROOT, check=False)
    return completed.returncode


def _print_usage() -> None:
    print(
        "Usage: python software/scripts/backbone_workflow.py <name> [--class-name NAME] [--default-backbone NAME] [--dry-run] [--skip-tests]"
    )


def _parse_args(argv: list[str] | None = None) -> WorkflowArgs:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or "-h" in values or "--help" in values:
        _print_usage()
        raise SystemExit(0)

    name = values.pop(0).strip()
    class_name = ""
    default_backbone = "running_stat"
    dry_run = False
    skip_tests = False

    while values:
        token = values.pop(0)
        if token == "--class-name":
            if not values:
                raise SystemExit("--class-name requires a value")
            class_name = values.pop(0)
        elif token == "--default-backbone":
            if not values:
                raise SystemExit("--default-backbone requires a value")
            default_backbone = values.pop(0)
        elif token == "--dry-run":
            dry_run = True
        elif token == "--skip-tests":
            skip_tests = True
        else:
            raise SystemExit(f"unknown argument: {token}")

    return WorkflowArgs(
        name=name,
        class_name=class_name,
        default_backbone=default_backbone,
        dry_run=dry_run,
        skip_tests=skip_tests,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    backbone_name = args.name.strip()
    if not backbone_name:
        raise SystemExit("backbone name cannot be empty")

    class_name = args.class_name.strip() or f"{_pascal_case(backbone_name)}Backbone"
    module_path = BACKBONES_DIR / f"{backbone_name}.py"

    if not args.dry_run:
        _create_module(module_path, class_name)

    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    factory_text = FACTORY_PATH.read_text(encoding="utf-8")
    init_text = INIT_PATH.read_text(encoding="utf-8")

    _write_file(CONFIG_PATH, _update_config(config_text, backbone_name, args.default_backbone), args.dry_run)
    _write_file(FACTORY_PATH, _update_factory(factory_text, backbone_name, class_name), args.dry_run)
    _write_file(INIT_PATH, _update_init(init_text, backbone_name, class_name), args.dry_run)

    if args.dry_run:
        return 0

    compliance_rc = _run_command([sys.executable, str(ROOT / "software" / "scripts" / "ci_compliance.py")])
    if compliance_rc != 0:
        return compliance_rc

    if not args.skip_tests:
        test_path = ROOT / "software" / "tests" / f"test_{backbone_name}.py"
        if test_path.exists():
            return _run_command([sys.executable, "-m", "pytest", "-q", str(test_path.relative_to(ROOT))])

    return 0


if __name__ == "__main__":
    sys.exit(main())