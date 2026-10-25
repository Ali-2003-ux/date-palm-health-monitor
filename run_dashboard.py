"""Convenience launcher for the Streamlit dashboard.

Usage:
    python run_dashboard.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    port = os.getenv("STREAMLIT_SERVER_PORT", "8501")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(PROJECT_ROOT / "frontend" / "app.py"),
        "--server.port",
        port,
        "--browser.gatherUsageStats",
        "false",
    ]
    print(f"Starting dashboard on http://localhost:{port} (API: "
          f"{os.getenv('STREAMLIT_API_URL', 'http://localhost:8000')})")
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


if __name__ == "__main__":
    main()
