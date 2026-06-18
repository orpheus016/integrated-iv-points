"""Lightweight compliance checker to enforce core rules from AGENTS.md.

Checks performed:
- `Snapshot` dataclass exists in `software/utils/types.py`.
- Each file in `software/backbones/` defines a class inheriting from `BaseBackbone`.
- `software/scripts/evaluate.py` uses `software/utils/csv_replay.py`, not the test module.
- No duplicate local implementations of `mean_std`/`mean_rms` remain outside `software/utils/math.py`.

Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check_snapshot() -> bool:
    p = ROOT / "software" / "utils" / "types.py"
    if not p.exists():
        print("ERROR: software/utils/types.py not found")
        return False
    text = p.read_text(encoding="utf-8")
    if "class Snapshot" not in text:
        print("ERROR: Snapshot dataclass not found in software/utils/types.py")
        return False
    return True


def check_backbones() -> bool:
    ok = True
    base_path = ROOT / "software" / "backbones"
    base_file = base_path / "base.py"
    if not base_file.exists():
        print("ERROR: backbones/base.py not found")
        return False
    for p in base_path.glob("*.py"):
        if p.name == "base.py" or p.name.startswith("__"):
            continue
        src = p.read_text(encoding="utf-8")
        try:
            mod = ast.parse(src)
        except SyntaxError as e:
            print(f"ERROR: failed to parse {p}: {e}")
            ok = False
            continue
        classes = [n for n in mod.body if isinstance(n, ast.ClassDef)]
        if not classes:
            print(f"WARNING: no classes in {p}")
            ok = False
            continue
        inherits = False
        for c in classes:
            for base in c.bases:
                if getattr(base, 'id', None) == 'BaseBackbone' or (isinstance(base, ast.Attribute) and base.attr == 'BaseBackbone'):
                    inherits = True
        if not inherits:
            print(f"ERROR: no class in {p} inherits from BaseBackbone")
            ok = False
    return ok


def check_evaluate_imports() -> bool:
    evaluate_path = ROOT / "software" / "scripts" / "evaluate.py"
    if not evaluate_path.exists():
        print("ERROR: software/scripts/evaluate.py not found")
        return False
    text = evaluate_path.read_text(encoding="utf-8")
    if "from ..tests.csv_replay import csv_replay_reader" in text:
        print("ERROR: evaluate.py must not import csv_replay_reader from tests module")
        return False
    # acceptable patterns: import csv_replay from utils, or import evaluate helpers
    if ("from ..utils.csv_replay import csv_replay_reader" not in text) and ("from ..utils.evaluate_helpers import" not in text):
        print("ERROR: evaluate.py should either import csv_replay_reader from software/utils/csv_replay.py or use software/utils/evaluate_helpers.py")
        return False
    return True


def check_no_duplicates() -> bool:
    ok = True
    # search for definitions of mean_std or mean_rms outside utils/math.py
    math_path = (ROOT / "software" / "utils" / "math.py").resolve()
    for p in (ROOT / "software").rglob("*.py"):
        # skip this checker file
        if p.resolve() == Path(__file__).resolve():
            continue
        if p.resolve() == math_path:
            continue
        txt = p.read_text(encoding="utf-8")
        if "def mean_std(" in txt or "def mean_rms(" in txt:
            print(f"ERROR: duplicate mean helper found in {p}")
            ok = False
    return ok


def check_instructions_shape() -> bool:
    """Quick sanity check that AGENTS match the current structure.

    This is intentionally lightweight: it does not judge style, just validates
    that key paths and architecture claims line up with the repository.
    """
    instructions = ROOT / "AGENTS.md"
    if not instructions.exists():
        print("ERROR: AGENTS.md not found")
        return False
    text = instructions.read_text(encoding="utf-8")
    required_phrases = [
        "software/utils/csv_replay.py",
        "software/scripts/evaluate.py",
        "software/scripts/integrate.py",
        "software/backbones",
        "software/utils/types.py",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in text]
    if missing:
        print("ERROR: AGENTS.md is missing required architecture references: " + ", ".join(missing))
        return False
    return True


def check_duplicate_top_level_functions() -> bool:
    """Detect duplicate top-level function names across `software/` modules.

    Excludes files under `software/tests/` and any `__init__.py` files.
    Reports names that appear as top-level `def` in more than one file.
    """
    ok = True
    mapping: dict[str, list[Path]] = {}
    for p in (ROOT / "software").rglob("*.py"):
        rel = p.relative_to(ROOT / "software")
        # skip tests and __init__
        if "tests" in rel.parts:
            continue
        if p.name == "__init__.py":
            continue
        src = p.read_text(encoding="utf-8")
        try:
            mod = ast.parse(src)
        except SyntaxError:
            continue
        for node in mod.body:
            if isinstance(node, ast.FunctionDef):
                mapping.setdefault(node.name, []).append(p)

    # ignore common script entrypoints like 'main'
    IGNORE_NAMES = {"main"}
    duplicates = {name: paths for name, paths in mapping.items() if len({str(x) for x in paths}) > 1 and name not in IGNORE_NAMES}
    if duplicates:
        print("ERROR: duplicate top-level function names found across files:")
        for name, paths in duplicates.items():
            print(f" - {name}: {', '.join(str(p) for p in paths)}")
        ok = False
    return ok


def check_add_argument_locations() -> bool:
    """Ensure `add_argument` is only used inside `build_arg_parser` in config.py.

    Any other usage of `add_argument` in the `software/` tree is flagged.
    """
    ok = True
    config_path = (ROOT / "software" / "config" / "config.py").resolve()
    for p in (ROOT / "software").rglob("*.py"):
        # skip this script
        if p.resolve() == Path(__file__).resolve():
            continue
        src = p.read_text(encoding="utf-8")
        try:
            mod = ast.parse(src)
        except SyntaxError:
            continue

        class ArgVisitor(ast.NodeVisitor):
            def __init__(self):
                self.issues: list[str] = []
                self.current_fn: Optional[str] = None

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                prev = self.current_fn
                self.current_fn = node.name
                self.generic_visit(node)
                self.current_fn = prev

            def visit_Call(self, node: ast.Call) -> None:
                func = node.func
                name = None
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name == "add_argument":
                    # record the function context
                    self.issues.append(self.current_fn or "<module>")
                self.generic_visit(node)

        visitor = ArgVisitor()
        visitor.visit(mod)
        if visitor.issues:
            if p.resolve() != config_path:
                print(f"ERROR: add_argument used outside config.py in {p}: functions {visitor.issues}")
                ok = False
            else:
                # ensure all occurrences are inside build_arg_parser
                for fn in visitor.issues:
                    if fn != "build_arg_parser":
                        print(f"ERROR: add_argument used in config.py but outside build_arg_parser (found in {fn})")
                        ok = False
    return ok


def main() -> int:
    checks = [
        (check_snapshot, "Snapshot dataclass present"),
        (check_backbones, "Backbones inherit BaseBackbone"),
        (check_evaluate_imports, "Evaluate imports csv_replay from utils"),
        (check_no_duplicates, "No duplicate mean helpers"),
        (check_duplicate_top_level_functions, "No duplicate top-level function names across modules"),
        (check_add_argument_locations, "add_argument only in build_arg_parser of config.py"),
        (check_instructions_shape, "Instructions align with repo layout"),
    ]
    all_ok = True
    for fn, msg in checks:
        ok = fn()
        print(f"[{ 'OK' if ok else 'FAIL' }] {msg}")
        all_ok = all_ok and ok
    return 0 if all_ok else 2


if __name__ == '__main__':
    sys.exit(main())
