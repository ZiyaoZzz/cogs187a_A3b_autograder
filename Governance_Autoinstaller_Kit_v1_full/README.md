# Governance + Autoinstaller Kit (v0.1.0)

This kit packages a hardened `install.sh` and a small Governance / Rot Shield
module that you can drop into any Python-based project. It is designed to be
easy for both humans and AI assistants to integrate into existing repos.

## Contents

- `install.sh`
  - Strict-mode autoinstaller.
  - Creates / activates a virtualenv.
  - Optionally asserts that Docker is available.
  - Runs a sequence of governance guards.
  - Leaves space for project-specific migrations/tests.

- `v3_governance.yml`
  - Declarative governance specification:
    - Critical code roots.
    - Canonical files.
    - Stub/hollow allowlists.
    - Critical imports and entrypoints.

- `governance.lock`
  - Frozen snapshot of governance version and notes.
  - Update this file only after consciously revising `v3_governance.yml`.

- `release.keep.yml`
  - Keep-list for drift-shield / orphan-sweeper tools.

- `scripts/`
  - `hollow_repo_guard.py`
  - `program_integrity_guard.py`
  - `syntax_guard.py`
  - `critical_import_guard.py`
  - `canon_guard.py`
  - `guardian.py` — runs all guards in sequence.
  - `rot_audit_prompt.py` — prints a rot-focused Ruthless prompt.

- `docs/`
  - `GOVERNANCE_KIT_README.md`
  - `ROT_RUTHLESS_PROMPT.md`
  - `RUTHLESS_MULTIPANEL_PROMPT.md`

## Quick Start (for a target repo)

1. Copy the kit contents into your repo root (or add as a subtree).
2. Edit `v3_governance.yml`:
   - Set `project_name`, `root_package`, `critical_code_roots`,
     `canonical_files`, and `critical_imports`.
3. Adjust `install.sh`:
   - Confirm the dependency section matches your project
     (`requirements.txt`, `pyproject.toml`, or other).
   - Add your migrations/tests in the "project-specific steps" section.
4. Run:
   - `chmod +x install.sh`
   - `./install.sh`

If any guard fails, it will print a clear error and exit non-zero.

## Using the Rot Audit Prompt

- Run `python scripts/rot_audit_prompt.py` to print a fully-assembled
  "Rot Tribunal" prompt that includes your project name, code roots,
  and governance spec.
- Paste that prompt into an LLM and follow its recommendations, then
  update your code and re-run `./install.sh`.

