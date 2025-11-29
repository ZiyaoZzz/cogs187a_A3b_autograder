#!/usr/bin/env python
"""critical_import_guard.py

Ensures that critical imports specified in v3_governance.yml can be imported.
"""

import importlib
import sys
from pathlib import Path

import yaml


def load_governance(root: Path) -> dict:
    cfg_path = root / "v3_governance.yml"
    if not cfg_path.exists():
        print("critical_import_guard: v3_governance.yml not found", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    cfg = load_governance(repo_root)
    imports = cfg.get("critical_imports", [])

    errors = []

    for item in imports:
        if ":" in item:
            mod_name, attr_name = item.split(":", 1)
        else:
            mod_name, attr_name = item, None

        try:
            module = importlib.import_module(mod_name)
        except Exception as exc:
            errors.append(f"Failed to import module '{mod_name}': {exc}")
            continue

        if attr_name:
            if not hasattr(module, attr_name):
                errors.append(
                    f"Module '{mod_name}' is missing required attribute '{attr_name}'."
                )

    if errors:
        print("critical_import_guard: FAIL", file=sys.stderr)
        for msg in errors:
            print(" -", msg, file=sys.stderr)
        sys.exit(1)

    print("critical_import_guard: OK")


if __name__ == "__main__":
    main()
