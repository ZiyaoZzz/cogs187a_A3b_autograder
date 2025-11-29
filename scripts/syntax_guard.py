#!/usr/bin/env python
"""syntax_guard.py

Compiles all Python files under critical_code_roots to ensure there are no
syntax errors.
"""

import sys
from pathlib import Path
import compileall

import yaml


def load_governance(root: Path) -> dict:
    cfg_path = root / "v3_governance.yml"
    if not cfg_path.exists():
        print("syntax_guard: v3_governance.yml not found", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_governance(repo_root)

    critical_roots = [repo_root / p for p in cfg.get("critical_code_roots", [])]

    ok = True
    for root in critical_roots:
        if not root.exists():
            continue
        result = compileall.compile_dir(root, quiet=1)
        if not result:
            ok = False

    if not ok:
        print("syntax_guard: FAIL (one or more packages failed to compile)", file=sys.stderr)
        sys.exit(1)

    print("syntax_guard: OK")


if __name__ == "__main__":
    main()
