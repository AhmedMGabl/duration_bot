# -*- coding: utf-8 -*-
"""
pipeline_cm_eg.py
Full CM-EG daily pipeline:
  Phase 1 — Scrape CRM (crm.51talk.com) → rawdata.xlsx sheet 1
  Phase 2 — Prepare data from Input/
  Phase 3 — POST to dashboard /process backend in CM-EG mode → dashboard HTML
  Phase 4 — Render dashboard HTML with Playwright → screenshot Teams + Ranking
  Phase 5 — Send PNGs to Lark group

The dashboard backend generates the exact same report HTML as the UI.

Usage:
  docker compose run --rm scrap-pipeline python pipeline_cm_eg.py
"""
import os
import sys
import json
from datetime import datetime

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR      = os.path.join(SCRIPT_DIR, 'Input')
OUTPUT_DIR     = os.path.join(SCRIPT_DIR, 'Output')
RAWDATA_FILE   = os.path.join(INPUT_DIR, 'rawdata.xlsx')
STRUCTURE_FILE = os.path.join(INPUT_DIR, 'Team Structure.xlsx')

# Read target groups from environment (set by duration_bot web UI)
TARGET_GROUPS = os.environ.get('TARGET_LARK_GROUPS')
if TARGET_GROUPS:
    target_groups = json.loads(TARGET_GROUPS)
    print(f"Target groups from environment: {target_groups}")
else:
    target_groups = [os.environ.get('LARK_CHAT_ID', 'oc_1ab849cf11a8505ae909eff1928cd052')]
    print(f"Using default target group: {target_groups}")

from crm_scraper_linux import scrape_crm_report_linux
from data_prep         import load_crm_paste_text, load_iur_paste_text, load_cm_team_structure_bytes
from dashboard_client  import get_session, process_cm_eg
from screenshotter     import screenshot_dashboard
from lark_sender       import send_cm_eg_report


def run_pipeline():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'\n{"="*60}')
    print(f'CM-EG Pipeline — {timestamp}')
    print(f'{"="*60}')

    # Phase 1: Scrape CRM
    print('\n[Phase 1] Scraping CRM data...')
    try:
        scrape_crm_report_linux(RAWDATA_FILE, script_dir=SCRIPT_DIR)
        print('CRM scrape OK')
    except Exception as e:
        print(f'WARNING: CRM scrape failed ({e}). Using existing rawdata.xlsx sheet 1.')

    # Phase 2: Prepare data
    print('\n[Phase 2] Preparing data...')
    crm_text   = load_crm_paste_text(RAWDATA_FILE)
    iur_text   = load_iur_paste_text(RAWDATA_FILE)
    team_bytes = load_cm_team_structure_bytes(STRUCTURE_FILE)
    print(f'  CRM rows: {len(crm_text.splitlines()) - 1}')
    print(f'  IUR rows: {len(iur_text.splitlines()) - 1}')
    print(f'  Team structure: {len(team_bytes)} bytes')

    # Phase 3: Call dashboard backend
    print('\n[Phase 3] Calling dashboard /process (CM-EG mode)...')
    session        = get_session()
    result         = process_cm_eg(session, crm_text, iur_text, team_bytes)
    dashboard_html = result['dashboard_html']
    print(f'  Stats: {result.get("stats", {})}')

    # Phase 4: Render + screenshot
    print('\n[Phase 4] Rendering and screenshotting...')
    png_paths = screenshot_dashboard(dashboard_html, OUTPUT_DIR, session)
    if not png_paths:
        print('ERROR: No screenshots produced. Exiting.')
        sys.exit(1)
    print(f'  Saved: {[os.path.basename(p) for p in png_paths]}')

    # Phase 5: Send to Lark
    print('\n[Phase 5] Sending to Lark...')
    send_cm_eg_report(png_paths, target_groups=target_groups)

    print(f'\n{"="*60}')
    print('Pipeline complete.')
    print(f'{"="*60}\n')


if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    log_dir  = os.path.join(OUTPUT_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, datetime.now().strftime('%Y-%m-%d_%H-%M') + '_cmeg.log')

    class Tee:
        def __init__(self, *streams): self.streams = streams
        def write(self, data):
            for s in self.streams: s.write(data)
        def flush(self):
            for s in self.streams: s.flush()

    log_file   = open(log_path, 'w', encoding='utf-8')
    sys.stdout = Tee(sys.stdout, log_file)

    try:
        run_pipeline()
    finally:
        sys.stdout = sys.stdout.streams[0]
        log_file.close()
        print(f'Log saved: {log_path}')
