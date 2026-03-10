# -*- coding: utf-8 -*-
"""
dashboard_client.py
Logs into the duration dashboard and calls /process in CM-EG mode.
"""
import os
import requests

DASHBOARD_URL  = os.environ.get('DASHBOARD_URL', 'http://172.17.0.1:15010')
DASHBOARD_USER = os.environ.get('DASHBOARD_USER', 'pipeline_bot')
DASHBOARD_PASS = os.environ.get('DASHBOARD_PASS', 'Pipeline2026!')


def get_session() -> requests.Session:
    """Login to the dashboard and return an authenticated session."""
    session = requests.Session()
    session.get(f'{DASHBOARD_URL}/login', timeout=10)
    resp = session.post(
        f'{DASHBOARD_URL}/login',
        data={'username': DASHBOARD_USER, 'password': DASHBOARD_PASS},
        allow_redirects=True,
        timeout=15,
    )
    if resp.status_code not in (200, 302):
        raise RuntimeError(f'Login HTTP error: {resp.status_code}')
    if 'login' in resp.url and 'logout' not in resp.text.lower():
        raise RuntimeError(f'Login failed — still on login page. Check credentials.')
    print(f'Dashboard login OK ({DASHBOARD_USER})')
    return session


def process_cm_eg(
    session: requests.Session,
    crm_paste_text: str,
    iur_paste_text: str,
    team_structure_bytes: bytes,
) -> dict:
    """POST to /process with CM-EG mode. Returns JSON response dict."""
    files = {
        'team_structure_file': (
            'Team_Structure_CM.xlsx',
            team_structure_bytes,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ),
    }
    data = {
        'raw_data_mode': 'paste',
        'raw_data_text': crm_paste_text,
        'iur_data_text': iur_paste_text,
        'active_mode': 'CM-EG',
        'use_saved_team': 'false',
        'excluded_agents': '',
    }
    resp = session.post(f'{DASHBOARD_URL}/process', files=files, data=data, timeout=60)
    result = resp.json()
    if not result.get('success'):
        raise RuntimeError(f'/process failed: {result.get("error")}')
    print(f"Dashboard processed OK — stats: {result.get('stats', {})}")
    return result
