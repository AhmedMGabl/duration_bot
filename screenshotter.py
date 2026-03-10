# -*- coding: utf-8 -*-
"""
screenshotter.py
Navigates to the live duration dashboard, injects the processed dashboard_html
into the page DOM, then screenshots specific table elements.
This ensures screenshots come from the real dashboard (same CSS, fonts, layout).
"""
import os
import json
from playwright.sync_api import sync_playwright

DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://172.17.0.1:15010')

import base64

# Elements to export using the dashboard's html2canvas (same as "Download PNG" button)
SCREENSHOT_TARGETS = [
    ('CM_EG_Teams_Totals.png',    'teamsTable'),
    ('CM_EG_Teams_Breakdown.png', 'teamDetailsContainer'),
]


def screenshot_dashboard(dashboard_html: str, output_dir: str, session) -> list:
    """
    Navigate to the live dashboard using the authenticated requests session's cookies,
    inject dashboard_html into the page, and export each target element via html2canvas
    (identical to clicking the "Download PNG" button in the UI).

    Args:
        dashboard_html: HTML fragment returned by /process endpoint
        output_dir:     Directory to save PNGs
        session:        Authenticated requests.Session (for cookie transfer)

    Returns:
        List of PNG file paths successfully created.
    """
    os.makedirs(output_dir, exist_ok=True)
    saved = []

    # Transfer cookies from requests.Session to Playwright
    from urllib.parse import urlparse as _urlparse
    _dashboard_host = _urlparse(DASHBOARD_URL).hostname or '172.17.0.1'
    req_cookies = []
    for c in session.cookies:
        req_cookies.append({
            'name':   c.name,
            'value':  c.value,
            'domain': c.domain or _dashboard_host,
            'path':   c.path or '/',
        })

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        context = browser.new_context(viewport={'width': 1600, 'height': 1000})
        context.add_cookies(req_cookies)

        page = context.new_page()
        page.goto(DASHBOARD_URL + '/', wait_until='networkidle', timeout=30000)

        if '/login' in page.url:
            browser.close()
            raise RuntimeError(f'Dashboard session expired or invalid — redirected to login page: {page.url}')

        # Inject the processed dashboard HTML into the page
        container_info = page.evaluate("""
            (html) => {
                let selector = null;
                let container = document.querySelector('#dashboardContainer');
                if (container) { selector = '#dashboardContainer'; }
                else {
                    container = document.querySelector('#dashboard-content');
                    if (container) { selector = '#dashboard-content'; }
                    else {
                        container = document.querySelector('.dashboard-result');
                        if (container) { selector = '.dashboard-result'; }
                        else {
                            container = document.querySelector('main');
                            if (container) { selector = 'main'; }
                            else {
                                container = document.createElement('div');
                                container.id = 'injectedDashboard';
                                document.body.appendChild(container);
                                selector = 'div#injectedDashboard (created)';
                            }
                        }
                    }
                }
                container.innerHTML = html;
                return selector;
            }
        """, dashboard_html)
        print(f'  Injected dashboard HTML into: {container_info}')

        # Make all sub-tab sections visible (they are hidden by default)
        page.evaluate("""
            document.querySelectorAll('.sub-tab-content').forEach(el => {
                el.style.display = 'block';
            });
        """)

        # Wait for html2canvas library to be available (loaded from CDN on the dashboard page)
        try:
            page.wait_for_function('typeof html2canvas === "function"', timeout=15000)
        except Exception:
            browser.close()
            raise RuntimeError('html2canvas not available on dashboard page — CDN may be unreachable')

        # Wait for target elements to appear
        try:
            page.wait_for_selector('#teamsTable, #teamDetailsContainer', timeout=10000)
        except Exception:
            page.wait_for_timeout(1000)

        for filename, element_id in SCREENSHOT_TARGETS:
            print(f'  Exporting #{element_id} via html2canvas...')
            png_b64 = page.evaluate("""async (elementId) => {
                const element = document.getElementById(elementId);
                if (!element) return null;
                const canvas = await html2canvas(element, {
                    backgroundColor: '#ffffff',
                    scale: 2
                });
                return canvas.toDataURL('image/png').split(',')[1];
            }""", element_id)

            if png_b64 is None:
                print(f'  WARNING: #{element_id} not found — skipping {filename}')
                continue

            out_path = os.path.join(output_dir, filename)
            with open(out_path, 'wb') as f:
                f.write(base64.b64decode(png_b64))
            print(f'  PNG saved: {out_path}')
            saved.append(out_path)

        browser.close()

    return saved
