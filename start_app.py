#!/usr/bin/env python3
"""Launcher: starts collector.py as a background process and runs Streamlit dashboard.

Usage:
  python3 start_app.py

Press Ctrl+C to stop both processes.
"""
import subprocess
import sys
import time


def terminate_proc(p):
    try:
        if p and p.poll() is None:
            p.terminate()
            time.sleep(1)
            if p.poll() is None:
                p.kill()
    except Exception:
        pass


def main():
    # start collector
    collector_cmd = [sys.executable, "collector.py"]
    print("Starting collector:", " ".join(collector_cmd))
    collector = subprocess.Popen(collector_cmd)

    # start streamlit
    streamlit_cmd = ["streamlit", "run", "dashboard.py"]
    print("Starting Streamlit:", " ".join(streamlit_cmd))
    try:
        streamlit = subprocess.Popen(streamlit_cmd)
        # wait until streamlit exits
        streamlit.wait()
    except KeyboardInterrupt:
        print("Interrupted by user — shutting down...")
    finally:
        terminate_proc(streamlit if 'streamlit' in locals() else None)
        terminate_proc(collector)


if __name__ == "__main__":
    main()
