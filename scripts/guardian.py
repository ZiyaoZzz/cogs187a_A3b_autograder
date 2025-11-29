#!/usr/bin/env python
"""guardian.py

Convenience runner that executes all governance guards in sequence.
"""

import subprocess
import sys
from pathlib import Path


GUARDS = [
    "hollow_repo_guard.py",
    "program_integrity_guard.py",
    "syntax_guard.py",
    "critical_import_guard.py",
    "canon_guard.py",
]


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    python = sys.executable

    for guard in GUARDS:
        guard_path = repo_root / "scripts" / guard
        if not guard_path.exists():
            print(f"guardian: guard script missing: {guard}", file=sys.stderr)
            sys.exit(1)
        print(f"==> Running {guard}...")
        result = subprocess.run([python, str(guard_path)])
        if result.returncode != 0:
            print(
                f"guardian: {guard} failed with exit code {result.returncode}",
                file=sys.stderr,
            )
            sys.exit(result.returncode)

    print("✅ guardian: All governance guards passed.")


if __name__ == "__main__":
    main()
