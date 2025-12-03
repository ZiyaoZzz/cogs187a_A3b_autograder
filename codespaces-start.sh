#!/usr/bin/env bash
set -e

echo "[Codespaces] Bootstrapping COGS 187A LLM Autograder..."

cd /workspaces/cogs187a_A3b_autograder

echo "[Codespaces] Ensuring Python virtual environment..."
if [ ! -d .venv ]; then
  python -m venv .venv
fi

# Activate venv (Linux-style; Codespaces uses Linux containers)
source .venv/bin/activate

echo "[Codespaces] Installing Python dependencies (if needed)..."
pip install -r requirements.txt

echo "[Codespaces] Installing npm dependencies (if needed)..."
npm install

if [ -z "${CODESPACE_NAME}" ]; then
  echo "[Codespaces] WARNING: CODESPACE_NAME is not set. Are you sure you are running inside GitHub Codespaces?"
  echo "[Codespaces] Backend URL in VITE_API_BASE will likely be incorrect."
fi

BACKEND_URL="https://${CODESPACE_NAME}-8000.app.github.dev"
echo "[Codespaces] Expected backend URL: ${BACKEND_URL}"
echo "[Codespaces] Make sure port 8000 is set to Public in the Ports panel."

echo "[Codespaces] Starting backend + frontend (this terminal will stay attached)..."
VITE_API_BASE="${BACKEND_URL}" npm run dev:full


