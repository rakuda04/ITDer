"""
run.py — start the UEBA dashboard
Usage: python run.py
Then open http://localhost:5000
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

def run():
    print("▸ Checking Python dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "flask", "flask-cors", "-q"],
        check=True
    )

    print("\n  Dashboard → http://localhost:5000")
    print("  Press Ctrl+C to stop.\n")

    subprocess.run([sys.executable, "api.py"], cwd=ROOT)

if __name__ == "__main__":
    run()