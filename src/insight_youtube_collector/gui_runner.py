"""
GUI runner script for launching Streamlit app.

Usage:
    iyc-gui
    # or
    python -m insight_youtube_collector.gui_runner
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the Streamlit GUI."""
    gui_path = Path(__file__).parent / "gui.py"

    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(gui_path)],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error launching GUI: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Streamlit is not installed.")
        print("Install it with: pip install insight-youtube-collector[gui]")
        sys.exit(1)


if __name__ == "__main__":
    main()
