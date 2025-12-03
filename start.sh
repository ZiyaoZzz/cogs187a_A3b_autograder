#!/bin/bash
# Start script for COGS 187 Autograder
# Starts both frontend and backend servers reliably

set -e

echo "🚀 Starting COGS 187 Autograder..."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure .env exists (copy from template on first run)
if [ ! -f ".env" ]; then
    if [ -f "env.template" ]; then
        cp env.template .env
        echo "🆕 Created .env from env.template."
        echo "   Please open .env and paste your real GEMINI_API_KEY."
    else
        echo "⚠️  No .env found. Create one with GEMINI_API_KEY=your-key."
    fi
fi

if [ -f ".env" ]; then
    GEMINI_VALUE="$(grep -E '^GEMINI_API_KEY=' .env | cut -d'=' -f2-)"
    if [ -z "$GEMINI_VALUE" ] || [ "$GEMINI_VALUE" = "PASTE_GEMINI_KEY_HERE" ]; then
        echo "⚠️  GEMINI_API_KEY in .env is empty or still the placeholder."
        echo "   The app will start, but AI grading endpoints will return an error until you add a key."
    fi
fi

# Check and install frontend dependencies
if [ ! -d "node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    npm install
fi

# Check and create virtual environment
if [ ! -d ".venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv .venv
    echo "📦 Installing Python dependencies..."
    .venv/bin/pip install --upgrade pip setuptools wheel
    .venv/bin/pip install -r requirements.txt
fi

# Determine Python command
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD="$(pwd)/.venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_CMD="$(pwd)/.venv/Scripts/python.exe"
else
    PYTHON_CMD="python3"
    echo "⚠️  Warning: Using system Python. Virtual environment not found."
fi

# Check if backend dependencies are installed
echo "🔍 Checking Python dependencies..."
if ! $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing missing Python dependencies..."
    $PYTHON_CMD -m pip install --upgrade pip setuptools wheel
    $PYTHON_CMD -m pip install -r requirements.txt
else
    echo "✅ Python dependencies are installed"
fi

echo ""
echo "✅ Starting servers..."
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Start both servers using concurrently
npx concurrently \
  --names "FRONTEND,BACKEND" \
  --prefix-colors "blue,green" \
  --kill-others-on-fail \
  "npm run dev" \
  "cd backend && $PYTHON_CMD -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
