#!/usr/bin/env python
"""rot_audit_prompt.py

Prints a rot-focused Ruthless prompt, pre-filled with project-specific
information from v3_governance.yml. This is meant to be pasted into an LLM.
"""

import sys
from pathlib import Path

import yaml


def load_governance(root: Path) -> dict:
    cfg_path = root / "v3_governance.yml"
    if not cfg_path.exists():
        raise SystemExit("rot_audit_prompt: v3_governance.yml not found")
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def load_prompt_template(root: Path) -> str:
    tmpl_path = root / "docs" / "ROT_RUTHLESS_PROMPT.md"
    if not tmpl_path.exists():
        raise SystemExit("rot_audit_prompt: docs/ROT_RUTHLESS_PROMPT.md not found")
    return tmpl_path.read_text(encoding="utf-8")


def main(argv=None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_governance(repo_root)
    tmpl = load_prompt_template(repo_root)

    project_name = cfg.get("project_name", "UnknownProject")
    root_package = cfg.get("root_package", "backend")
    critical_roots = cfg.get("critical_code_roots", [])
    canonical_files = cfg.get("canonical_files", [])
    critical_imports = cfg.get("critical_imports", [])

    header = [
        "# Rot Tribunal Context Block",
        "",
        f"- Project name: {project_name}",
        f"- Root package: {root_package}",
        f"- Critical code roots: {', '.join(critical_roots) if critical_roots else '(none)'}",
        f"- Canonical files: {', '.join(canonical_files) if canonical_files else '(none)'}",
        f"- Critical imports: {', '.join(critical_imports) if critical_imports else '(none)'}",
        "",
        "---",
        "",
    ]

    sys.stdout.write("\n".join(header))
    sys.stdout.write(tmpl)


if __name__ == "__main__":
    main()
