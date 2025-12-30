import time
import json
import sqlite3
from datetime import datetime, date

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ================= USER SETTINGS =================
SYMBOL = "NIFTY"
INTERVAL_SECONDS = 300          # 5 minutes
ATM_RANGE = 300                # ATM ± points
DB_FILE = "oi_live.db"
HEADLESS = False               # set True after testing
# ================================================

OPTION_CHAIN_URL = f"https://www.nseindia.com/option-chain?symbol={SYMBOL}"
API_KEYWORD = "option-chain"

# ---------------- Selenium setup ----------------
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if HEADLESS:
        options.add_argument("--headless=new")

    # Enable performance logging for network interception
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )

    # Enable Network domain via CDP so response events appear in performance logs
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'}
    )

    return driver


def intercept_option_chain_json(driver):
    logs = driver.get_log("performance")

    for log in logs:
        message = json.loads(log["message"])  # outer wrapper
        msg = message.get("message", {})
        if msg.get("method") == "Network.responseReceived":
            params = msg.get("params", {})
            resp = params.get("response", {})
            url = resp.get("url", "")
            if API_KEYWORD in url:
                request_id = params.get("requestId")
                try:
                    body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                    if body and body.get("body"):
                        try:
                            parsed = json.loads(body["body"])
                            if isinstance(parsed, dict) and "records" in parsed:
                                return parsed
                            else:
                                continue
                        except Exception:
                            continue
                except Exception:
                    continue

    return None


# ---------------- Data helpers ----------------
def get_nearest_expiry(records):
    today = date.today()
    expiries = []

    for e in records["expiryDates"]:
        try:
            d = datetime.strptime(e, "%d-%b-%Y").date()
            if d >= today:
                expiries.append((d, e))
        except:
            pass

    expiries.sort()
    return expiries[0][1]


def extract_rows(api_data):
    records = api_data["records"]
    expiry = get_nearest_expiry(records)
    underlying = records["underlyingValue"]

    # Some API versions use 'expiryDate' per-item, others use 'expiryDates' (string)
    items = [
        i for i in records["data"]
        if str(i.get("expiryDate") or i.get("expiryDates", "")).strip() == str(expiry).strip()
    ]

    if not items:
        return None, []

    strikes = [i["strikePrice"] for i in items]

    atm = min(strikes, key=lambda x: abs(x - underlying))
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []

    for item in items:
        strike = item["strikePrice"]
        if abs(strike - atm) > ATM_RANGE:
            continue

        ce = item.get("CE") or {}
        pe = item.get("PE") or {}

        ce_oi = ce.get("openInterest", 0)
        pe_oi = pe.get("openInterest", 0)

        rows.append((
            ts,
            expiry,
            strike,
            ce_oi,
            ce.get("changeinOpenInterest", 0),
            pe_oi,
            pe.get("changeinOpenInterest", 0),
            pe_oi - ce_oi,  # NET OI
        ))

    return atm, rows


# ---------------- SQLite setup ----------------
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS oi_data (
    time TEXT,
    expiry TEXT,
    strike INTEGER,
    ce_oi INTEGER,
    ce_oi_change INTEGER,
    pe_oi INTEGER,
    pe_oi_change INTEGER,
    net_oi INTEGER
)
""")
conn.commit()


# ---------------- Main loop ----------------
def main():
    driver = setup_driver()
    print("Collector started (Selenium + CDP interception)")

    try:
        while True:
            print("Loading NSE option chain page...")
            driver.get(OPTION_CHAIN_URL)
            time.sleep(8)  # allow API calls to complete

            api_data = intercept_option_chain_json(driver)

            if not api_data or "records" not in api_data:
                print("❌ Could not intercept API data, retrying...")
                time.sleep(INTERVAL_SECONDS)
                continue

            atm, rows = extract_rows(api_data)

            cur.executemany(
                "INSERT INTO oi_data VALUES (?,?,?,?,?,?,?,?)",
                rows
            )
            conn.commit()

            print(
                f"{datetime.now():%H:%M:%S} | "
                f"ATM={atm} | Rows={len(rows)}"
            )

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("Stopped by user")

    finally:
        driver.quit()
        conn.close()


if __name__ == "__main__":
    main()
