import os
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
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    # executables expected next to this script
    collector_exe = os.path.join(base, 'collector.exe')
    dashboard_exe = os.path.join(base, 'run_dashboard.exe')

    # fallback to python scripts if exes not present
    if os.path.exists(collector_exe):
        collector_cmd = [collector_exe]
    else:
        collector_cmd = [sys.executable, os.path.join(base, 'collector.py')]

    if os.path.exists(dashboard_exe):
        dashboard_cmd = [dashboard_exe]
    else:
        dashboard_cmd = [sys.executable, os.path.join(base, 'run_dashboard.py')]

    print('Starting collector:', collector_cmd)
    proc_col = subprocess.Popen(collector_cmd, cwd=base)

    print('Starting dashboard:', dashboard_cmd)
    proc_dash = subprocess.Popen(dashboard_cmd, cwd=base)

    try:
        proc_dash.wait()
    except KeyboardInterrupt:
        print('Interrupted by user — shutting down...')
    finally:
        terminate_proc(proc_dash)
        terminate_proc(proc_col)


if __name__ == '__main__':
    main()
