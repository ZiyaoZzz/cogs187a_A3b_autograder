#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-cogs187-llm-autograder}"
LOG_DIR="${LOG_DIR:-logs}"
REQUIRE_DOCKER="${REQUIRE_DOCKER:-0}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/install_$(date +%s).log"

# Dual logging: console + file
exec > >(tee -i "$LOG_FILE") 2>&1

echo "==> [$PROJECT_NAME] Starting install at $(date)"

# 1. Find Python and check version
PYTHON_CMD=$(command -v python3 || command -v python || true)
if [ -z "${PYTHON_CMD}" ]; then
  echo "❌ Critical: No python or python3 found on PATH."
  exit 1
fi

# Check Python version (require 3.8+)
PYTHON_VERSION=$("${PYTHON_CMD}" --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
  echo "❌ Critical: Python 3.8+ required. Found: $PYTHON_VERSION"
  exit 1
fi

echo "✅ Using Python: ${PYTHON_CMD} (version $PYTHON_VERSION)"

# 2. Ensure venv
if [ -z "${VIRTUAL_ENV:-}" ]; then
  echo "⚠️  No virtualenv detected. Creating .venv at repo root..."
  "${PYTHON_CMD}" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "✅ Activated .venv"
else
  echo "✅ Running inside existing virtualenv: $VIRTUAL_ENV"
fi

# 3. Optional Docker check
if [ "${REQUIRE_DOCKER}" -eq 1 ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Fatal: Docker is required but not found. Set REQUIRE_DOCKER=0 to skip."
    exit 1
  fi
  echo "✅ Docker is available"
fi

# 4. Upgrade pip to latest version
echo "==> Upgrading pip..."
"${PYTHON_CMD}" -m pip install --upgrade pip setuptools wheel

# 5. Install Python dependencies
if [ -f "requirements.txt" ]; then
  echo "==> Installing Python dependencies from requirements.txt..."
  pip install -r requirements.txt
  echo "✅ Python dependencies installed"
else
  echo "⚠️  Warning: requirements.txt not found. Skipping Python dependency install."
fi

# 6. Install Playwright browsers (required for scripts)
if command -v playwright >/dev/null 2>&1 || python -c "import playwright" 2>/dev/null; then
  echo "==> Installing Playwright browsers..."
  python -m playwright install chromium
  echo "✅ Playwright browsers installed"
else
  echo "⚠️  Warning: Playwright not installed. Some scripts may not work."
fi

# 7. Run governance guards
echo "==> Running governance guards to verify project structure..."
python scripts/hollow_repo_guard.py
python scripts/program_integrity_guard.py
python scripts/syntax_guard.py
python scripts/critical_import_guard.py
python scripts/canon_guard.py
echo "✅ All governance guards passed"

# 8. Verify critical imports
echo "==> Verifying critical imports..."
if python -c "from backend.main import app" 2>/dev/null; then
  echo "✅ FastAPI app import successful"
else
  echo "⚠️  Warning: Could not import backend.main.app"
fi

# 9. Project-specific setup steps
echo "==> Running project-specific setup steps..."

# Check if frontend dependencies are installed
if [ -f "package.json" ]; then
  if [ ! -d "node_modules" ]; then
    echo "⚠️  Warning: node_modules not found. Run 'npm install' to install frontend dependencies."
  else
    echo "✅ Frontend dependencies detected (node_modules exists)"
  fi
fi

# Verify critical files exist
if [ ! -f "rubrics/a3_rubric.json" ]; then
  echo "⚠️  Warning: rubrics/a3_rubric.json not found"
fi

if [ ! -f "backend/main.py" ]; then
  echo "❌ Error: backend/main.py not found (critical file)"
  exit 1
fi

echo "✅ Project structure verified"

echo "✅ [$PROJECT_NAME] Install completed successfully."
