#!/usr/bin/env python
"""hollow_repo_guard.py

Fails if any critical code root is effectively "hollow" (no real Python files),
unless it is explicitly allowed in v3_governance.yml.
"""

import sys
from pathlib import Path

import yaml


def load_governance(root: Path) -> dict:
    cfg_path = root / "v3_governance.yml"
    if not cfg_path.exists():
        print("hollow_repo_guard: v3_governance.yml not found", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_governance(repo_root)

    critical_roots = [repo_root / p for p in cfg.get("critical_code_roots", [])]
    hollow_allowlist = cfg.get("hollow_paths_allowlist", [])

    import fnmatch

    def is_hollow_allowed(path: Path) -> bool:
        rel = path.relative_to(repo_root).as_posix()
        return any(fnmatch.fnmatch(rel, pattern) for pattern in hollow_allowlist)

    errors = []

    for root in critical_roots:
        if not root.exists():
            errors.append(f"Critical code root does not exist: {root}")
            continue

        py_files = [p for p in root.rglob("*.py") if p.name != "__init__.py"]
        if not py_files and not is_hollow_allowed(root):
            errors.append(
                f"Critical code root appears hollow (no .py files): {root}"
            )

    if errors:
        print("hollow_repo_guard: FAIL", file=sys.stderr)
        for msg in errors:
            print(" -", msg, file=sys.stderr)
        sys.exit(1)

    print("hollow_repo_guard: OK")


if __name__ == "__main__":
    main()
