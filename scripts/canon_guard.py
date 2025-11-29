#!/usr/bin/env python
"""canon_guard.py

Verifies that canonical files specified in v3_governance.yml exist and, where
applicable, are non-empty.
"""

import sys
from pathlib import Path

import yaml


def load_governance(root: Path) -> dict:
    cfg_path = root / "v3_governance.yml"
    if not cfg_path.exists():
        print("canon_guard: v3_governance.yml not found", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_governance(repo_root)

    canonical_files = cfg.get("canonical_files", [])
    errors = []

    for rel in canonical_files:
        path = repo_root / rel
        if not path.exists():
            errors.append(f"Canonical file missing: {rel}")
        elif path.is_file():
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                content = ""
            if rel == "VERSION" and not content:
                errors.append("VERSION file exists but is empty.")

    if errors:
        print("canon_guard: FAIL", file=sys.stderr)
        for msg in errors:
            print(" -", msg, file=sys.stderr)
        sys.exit(1)

    print("canon_guard: OK")


if __name__ == "__main__":
    main()
