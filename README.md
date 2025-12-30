# NIFTY OI Live (collector + Streamlit dashboard)

Files:
- `collector.py` — Selenium collector that writes to `oi_live.db`.
- `dashboard.py` — Streamlit dashboard that reads `oi_live.db`.
- `start_app.py` — Launcher: starts `collector.py` and runs `streamlit run dashboard.py`.
- `run.sh` — wrapper to run `start_app.py`.
- `requirements.txt` — Python dependencies.

Quick start (macOS/Linux):
1. Install dependencies:
```
python3 -m pip install -r requirements.txt
```
2. Run both collector and dashboard:
```
./run.sh
```
or
```
python3 start_app.py
```

Stop both with Ctrl+C.

Notes:
- This setup runs the collector as a separate Python process and Streamlit as another process; both share the SQLite DB `oi_live.db`.
- For a more robust deployment use a worker + web containers (Docker / Docker Compose) or run the collector as a separate service.
