# Governance + Autoinstaller Kit — Detailed Guide

This document explains how to adapt the kit to a real project. It is written
to be "AI-complete": an LLM can follow these instructions to integrate the
kit without additional context.

## 1. Determine the repo root

1. Look for:
   - `.git` directory.
   - `pyproject.toml` or `setup.py`.
   - A top-level `backend/`, `src/`, or `app/` directory.
2. Choose the directory that contains the main application code as the
   repo root.

## 2. Copy kit files

- Copy (or move) the following into the repo root:
  - `install.sh`
  - `VERSION` (or merge into existing VERSION semantics)
  - `v3_governance.yml`
  - `governance.lock`
  - `release.keep.yml`
  - `scripts/` directory
  - `docs/` directory

If any of these already exist in the target repo:
  - Read the existing file.
  - Merge content instead of overwriting blindly.
  - Preserve any project-specific behavior.

## 3. Edit v3_governance.yml

- Set `project_name` to the real project name.
- Set `root_package` to the main Python package (e.g., `backend`, `app`).
- Populate `critical_code_roots` with directories that contain real code.
- Populate `canonical_files` with files that must always exist.
- Adjust `stub_allowlist` and `hollow_paths_allowlist` to reflect where
  stubs or hollow dirs are acceptable.
- Add `critical_imports` that must succeed for the app to be healthy.

## 4. Adjust install.sh

- Confirm dependency installation logic matches the project:
  - `requirements.txt` vs `pyproject.toml` vs other tools.
- Decide whether Docker is required:
  - If `docker-compose.yml` exists, keep `REQUIRE_DOCKER=1`.
  - Otherwise, set `REQUIRE_DOCKER=0` or remove the Docker check.
- Add project-specific steps (migrations/tests) at the bottom.

## 5. Wire guards into CI (optional)

- Add a CI workflow (e.g., GitHub Actions) that:
  - Checks out the repo.
  - Sets up Python.
  - Installs dependencies.
  - Runs `python scripts/guardian.py`.

## 6. Use the rot audit prompt

- When nervous about code rot or drift, run:
  - `python scripts/rot_audit_prompt.py`
- Paste the resulting prompt into an LLM and apply its recommendations.
- Re-run `./install.sh` to validate.

