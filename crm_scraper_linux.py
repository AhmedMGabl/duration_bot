# -*- coding: utf-8 -*-
"""
crm_scraper_linux.py
Linux-compatible CRM scraper — adapted from Scripts/scrape_crm_report.py.
Uses Playwright bundled Chromium (headless) instead of Windows Chrome.
"""
import json
import os
import time
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime

CRM_URL       = "https://crm.51talk.com/scReportForms/sc_call_info_new?userType=sc_group"
CRM_LOGIN_URL = "https://crm.51talk.com/admin/admin_login.php?login_employee_type=sideline&redirect_uri="
CRM_USERNAME  = os.environ.get('CRM_USERNAME', '51Hany')
CRM_PASSWORD  = os.environ.get('CRM_PASSWORD', 'b%7DWWtm')

JS_EXTRACT = """
() => {
  const tables = document.querySelectorAll('table');
  const dataTable = Array.from(tables).find(t => t.textContent.includes('Total valid calls'));
  if (!dataTable) return JSON.stringify({error: 'no table'});
  const allRows = Array.from(dataTable.querySelectorAll('tr'));
  const headers = Array.from(allRows[0].querySelectorAll('th')).map(th => th.textContent.trim());
  const data = [];
  for (const row of allRows.slice(1)) {
    const cells = Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim());
    if (cells.length < 10) continue;
    if (!cells[1] || cells[1] === '/') continue;
    if (cells[0] === 'Total') continue;
    data.push(cells);
  }
  return JSON.stringify({headers, data});
}
"""


def _try_requests_cookies(cookie_file, today_str, rawdata_file):
    """Try fetching with saved cookies (fast path)."""
    try:
        import requests
        from bs4 import BeautifulSoup
        with open(cookie_file) as f:
            cookies = json.load(f)
        resp = requests.post(
            CRM_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": CRM_URL,
            },
            cookies=cookies,
            data={
                "start_date": today_str, "end_date": today_str,
                "today_start_time": "00:00:00", "today_end_time": "23:59:59",
                "is_show_group": "y", "": "submit",
            },
            timeout=30,
        )
        if resp.status_code != 200 or "Total valid calls" not in resp.text:
            print(f"  Cookie request: HTTP {resp.status_code}, falling back to browser...")
            return False
        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        data_table = next((t for t in tables if "Total valid calls" in t.get_text()), None)
        if not data_table:
            print("  Table not found via cookies, falling back to browser...")
            return False
        all_rows = data_table.find_all("tr")
        headers = [th.get_text(strip=True) for th in all_rows[0].find_all(["th", "td"])]
        rows = []
        for row in all_rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 10 or not cells[1] or cells[1] == "/" or cells[0] in ("Total", "In total"):
                continue
            rows.append(cells)
        df = pd.DataFrame(rows, columns=headers if rows and len(headers) == len(rows[0]) else None)
        if headers:
            col_map = {
                headers[0]: 'Serial', headers[1]: 'SC',
                headers[4]: 'Total number of calls', headers[5]: 'Total valid calls',
                headers[13]: 'Total effective call time/Minute',
                headers[14]: 'Average call time/Minute',
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        for col in ['Total valid calls', 'Total effective call time/Minute', 'Average call time/Minute', 'Total number of calls']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        print(f"  Shape: {df.shape}")
        _save_to_rawdata(df, rawdata_file)
        return True
    except Exception as ex:
        print(f"  Cookie approach failed: {ex}")
        return False


def _save_to_rawdata(df, rawdata_file):
    with pd.ExcelWriter(rawdata_file, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df.to_excel(writer, sheet_name="1", index=False)
    print(f"  Saved {len(df)} rows to sheet '1' in {rawdata_file}")


def scrape_crm_report_linux(rawdata_file: str, script_dir: str = None) -> None:
    """
    Scrape CRM call data for today and save to rawdata_file sheet '1'.
    Uses headless Playwright Chromium (Linux-compatible, no Windows Chrome needed).
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    today_str   = datetime.now().strftime("%Y-%m-%d")
    cookie_file = os.path.join(script_dir, "Scripts", "crm_cookies.json")

    print("=" * 60)
    print("CRM Call Report Scraper (Linux)")
    print("=" * 60)
    print(f"Target date: {today_str}")

    import time as _time
    # Fast path: try saved cookies if fresh (< 8 hours old)
    if os.path.exists(cookie_file):
        age_hours = (_time.time() - os.path.getmtime(cookie_file)) / 3600
        if age_hours <= 8:
            print(f"Step 1: Trying saved cookies (age: {age_hours:.1f}h)...")
            if _try_requests_cookies(cookie_file, today_str, rawdata_file):
                print("DONE")
                return
            print("  Cookies invalid, falling back to browser...")
        else:
            print(f"Step 1: Cookies stale ({age_hours:.1f}h old), using browser for fresh login...")
    else:
        print("Step 1: No cookies file, using headless browser...")

    # Browser path
    from playwright_stealth import stealth_sync
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        stealth_sync(page)
        page.set_default_timeout(60000)

        try:
            print("Step 1: Logging in to CRM...")
            page.goto(CRM_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            if "admin_login" in page.url:
                page.locator("#user_name").fill(CRM_USERNAME)
                page.locator("#pwd").fill(CRM_PASSWORD)
                page.locator("#Submit").click()
                page.wait_for_load_state("networkidle", timeout=15000)
                print(f"  After login: {page.url}")

            print("Step 2: Navigating to report page...")
            page.goto(CRM_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"  Page: {page.url}")

            print(f"Step 2: Setting date to {today_str}...")
            try:
                page.evaluate(f"""
                    () => {{
                        const inputs = document.querySelectorAll('input#start_date');
                        inputs.forEach(i => i.value = '{today_str}');
                    }}
                """)
                time.sleep(0.5)
            except Exception as e:
                print(f"  WARNING: date set failed: {e}")

            # Uncheck group display to get individual rows
            try:
                cb = page.query_selector('input[name="is_show_group"]')
                if cb and cb.is_checked():
                    cb.uncheck()
            except Exception:
                pass

            print("Step 3: Submitting query...")
            submit = page.query_selector('input[type="submit"][value="submit"], input[value="submit"]')
            if submit:
                submit.click()
                print("  Submitted. Waiting for data...")
                page.wait_for_selector("table:has-text('Total valid calls')", timeout=30000)
            else:
                print("  WARNING: submit button not found")
                time.sleep(3)

            print("Step 4: Extracting table data...")
            result = page.evaluate(JS_EXTRACT)
            parsed = json.loads(result)
            if "error" in parsed:
                raise Exception(f"Table extraction error: {parsed['error']}")

            headers = parsed["headers"]
            rows    = parsed["data"]
            print(f"  Headers: {headers}")
            print(f"  Data rows: {len(rows)}")

            if not rows:
                print("  WARNING: No data rows (no calls yet today)")
                return

            df = pd.DataFrame(rows, columns=headers if len(headers) == len(rows[0]) else None)
            col_map = {
                headers[0]: 'Serial',         headers[1]: 'SC',
                headers[4]: 'Total number of calls',
                headers[5]: 'Total valid calls',
                headers[13]: 'Total effective call time/Minute',
                headers[14]: 'Average call time/Minute',
            }
            df = df.rename(columns=col_map)
            for col in ['Total valid calls', 'Total effective call time/Minute', 'Average call time/Minute', 'Total number of calls']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            print(f"  Shape: {df.shape}")
            print(df[['SC', 'Total valid calls', 'Total effective call time/Minute', 'Average call time/Minute']].head(5).to_string())

            print("Step 5: Saving to rawdata.xlsx sheet '1'...")
            _save_to_rawdata(df, rawdata_file)

            # Refresh cookies for next run
            try:
                cookie_dict = {c["name"]: c["value"] for c in context.cookies()}
                os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
                with open(cookie_file, "w") as cf:
                    json.dump(cookie_dict, cf)
                print("  Cookies saved for next run.")
            except Exception as ce:
                print(f"  Cookie save warning: {ce}")

        except Exception as e:
            print(f"ERROR during CRM scrape: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            browser.close()
            print("DONE")


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    rawdata = os.path.join(base, "Input", "rawdata.xlsx")
    scrape_crm_report_linux(rawdata, script_dir=base)
