#!/usr/bin/env python
"""program_integrity_guard.py

Enforces basic program integrity:
- No stray "..." ellipses in code bodies.
- `# STUB:` markers only allowed under stub_allowlist paths.
"""

import sys
from pathlib import Path
import fnmatch

import yaml


def load_governance(root: Path) -> dict:
    cfg_path = root / "v3_governance.yml"
    if not cfg_path.exists():
        print("program_integrity_guard: v3_governance.yml not found", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_governance(repo_root)

    critical_roots = [repo_root / p for p in cfg.get("critical_code_roots", [])]
    stub_allowlist = cfg.get("stub_allowlist", [])

    def path_allowed_for_stubs(path: Path) -> bool:
        rel = path.relative_to(repo_root).as_posix()
        return any(fnmatch.fnmatch(rel, pattern) for pattern in stub_allowlist)

    errors = []

    for root in critical_roots:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            try:
                text = py.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            rel = py.relative_to(repo_root).as_posix()
            allow_stubs_here = path_allowed_for_stubs(py)

            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()

                # Disallow "..." in non-comment lines, but allow:
                # - String literals: "..." or '...'
                # - Function calls: File(...), Ellipsis, etc.
                # - Type hints: Tuple[..., ...]
                if "..." in stripped and not stripped.startswith("#"):
                    # Check if it's in a string literal (quoted)
                    import re
                    # Remove string literals to check if ... is outside them
                    # This is a simple heuristic: if ... appears outside quotes, it's likely a problem
                    # But we allow common patterns like File(...), Ellipsis, etc.
                    line_without_strings = re.sub(r'["\'].*?["\']', '', stripped)
                    # Allow ellipsis in function calls (common pattern like File(...))
                    if re.search(r'\w+\(\.\.\.\)', stripped):
                        continue
                    # Allow ellipsis in type hints
                    if '...' in line_without_strings and not any(keyword in stripped for keyword in ['File(', 'Ellipsis', 'Tuple[', 'List[', 'Dict[', 'Optional[', 'Union[']):
                        # Check if it's actually a problem (not in a string)
                        if '"...' not in stripped and "'..." not in stripped and '..."' not in stripped and "...'" not in stripped:
                            errors.append(
                                f"{rel}:{lineno} contains '...' in code; ellipsis is not allowed (except in strings or function calls like File(...))."
                            )

                # Disallow # STUB: where not allowed.
                if stripped.startswith("# STUB:") and not allow_stubs_here:
                    errors.append(
                        f"{rel}:{lineno} uses '# STUB:' outside stub_allowlist."
                    )

    if errors:
        print("program_integrity_guard: FAIL", file=sys.stderr)
        for msg in errors:
            print(" -", msg, file=sys.stderr)
        sys.exit(1)

    print("program_integrity_guard: OK")


if __name__ == "__main__":
    main()
