#!/usr/bin/env python3
"""
Start script for COGS 187 Autograder
Starts both frontend and backend servers
"""
import subprocess
import sys
import os
from pathlib import Path

def check_and_install_dependencies():
    """Check and install dependencies if needed"""
    # Check node_modules
    if not Path("node_modules").exists():
        print("📦 Installing frontend dependencies...")
        subprocess.run(["npm", "install"], check=True)
    
    # Check virtual environment
    venv_path = Path(".venv")
    if not venv_path.exists() and "VIRTUAL_ENV" not in os.environ:
        print("🐍 Creating Python virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", ".venv"], check=True)
        print("📦 Installing Python dependencies...")
        if sys.platform == "win32":
            pip = venv_path / "Scripts" / "pip.exe"
        else:
            pip = venv_path / "bin" / "pip"
        subprocess.run([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
        subprocess.run([str(pip), "install", "-r", "requirements.txt"], check=True)
    
    # Verify backend dependencies
    if venv_path.exists():
        if sys.platform == "win32":
            python = venv_path / "Scripts" / "python.exe"
        else:
            python = venv_path / "bin" / "python"
    else:
        python = Path(sys.executable)
    
    # Check if fastapi is installed
    try:
        subprocess.run([str(python), "-c", "import fastapi"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("📦 Installing missing Python dependencies...")
        if sys.platform == "win32":
            pip = venv_path / "Scripts" / "pip.exe" if venv_path.exists() else sys.executable.replace("python.exe", "pip.exe")
        else:
            pip = venv_path / "bin" / "pip" if venv_path.exists() else sys.executable.replace("python", "pip")
        subprocess.run([str(pip), "install", "-r", "requirements.txt"], check=True)

def start_servers():
    """Start both frontend and backend servers"""
    print("🚀 Starting COGS 187 Autograder...")
    print("")
    print("✅ Starting servers...")
    print("   Frontend: http://localhost:5173")
    print("   Backend:  http://localhost:8000")
    print("")
    print("Press Ctrl+C to stop both servers")
    print("")
    
    # Determine Python command (use the same one from check_and_install_dependencies)
    venv_path = Path(".venv")
    if venv_path.exists():
        if sys.platform == "win32":
            python = venv_path / "Scripts" / "python.exe"
        else:
            python = venv_path / "bin" / "python"
    else:
        python = Path(sys.executable)
    
    # Start frontend
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=Path.cwd()
    )
    
    # Start backend
    backend = subprocess.Popen(
        [str(python), "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=Path("backend")
    )
    
    try:
        # Wait for both processes
        frontend.wait()
        backend.wait()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping servers...")
        frontend.terminate()
        backend.terminate()
        frontend.wait()
        backend.wait()
        print("✅ Servers stopped")

if __name__ == "__main__":
    try:
        check_and_install_dependencies()
        start_servers()
    except KeyboardInterrupt:
        print("\n\n✅ Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

