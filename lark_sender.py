# -*- coding: utf-8 -*-
"""
lark_sender.py
Uploads PNG images to Lark and sends an interactive card to a Lark group.
"""
import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

LARK_APP_ID     = os.environ.get('LARK_APP_ID',     'cli_a9bf7d0d8438dbdc')
LARK_APP_SECRET = os.environ.get('LARK_APP_SECRET', 'fLNIH2ElbH9mChpijh4tbeKd36dJHKtq')
LARK_CHAT_ID    = os.environ.get('LARK_CHAT_ID',    'oc_1ab849cf11a8505ae909eff1928cd052')


def get_token() -> str:
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': LARK_APP_ID, 'app_secret': LARK_APP_SECRET},
        timeout=10,
    )
    result = resp.json()
    if result.get('code') == 0:
        return result['tenant_access_token']
    raise RuntimeError(f'Lark auth failed: {result}')


def upload_image(token: str, image_path: str) -> str:
    with open(image_path, 'rb') as f:
        resp = requests.post(
            'https://open.feishu.cn/open-apis/im/v1/images',
            headers={'Authorization': f'Bearer {token}'},
            files={'image': (os.path.basename(image_path), f, 'image/png')},
            data={'image_type': 'message'},
            timeout=120,
        )
    result = resp.json()
    if result.get('code') == 0:
        return result['data']['image_key']
    raise RuntimeError(f'Upload failed for {image_path}: {result}')


def send_card(token: str, title: str, color: str, image_keys: list, labels: list, chat_ids: list = None) -> None:
    if not chat_ids:
        chat_ids = [LARK_CHAT_ID]

    elements = []
    for label, key in zip(labels, image_keys):
        if key:
            elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**{label}**'}})
            elements.append({'tag': 'img', 'img_key': key, 'alt': {'tag': 'plain_text', 'content': label}})
            elements.append({'tag': 'hr'})
    card = {
        'config': {'wide_screen_mode': True},
        'header': {'title': {'tag': 'plain_text', 'content': title}, 'template': color},
        'elements': elements,
    }

    for chat_id in chat_ids:
        resp = requests.post(
            'https://open.feishu.cn/open-apis/im/v1/messages',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            params={'receive_id_type': 'chat_id'},
            json={'receive_id': chat_id, 'msg_type': 'interactive', 'content': json.dumps(card)},
            timeout=10,
        )
        result = resp.json()
        if result.get('code') != 0:
            raise RuntimeError(f'Lark send to {chat_id} failed: {result}')


def get_bot_groups(app_id=None, app_secret=None):
    """
    Fetch list of groups the bot has access to.

    Note: Returns up to 100 groups (pagination not implemented).
    If more than 100 groups exist, implement pagination using page_token.

    Returns:
        list: [{'chat_id': 'oc_...', 'name': 'Group Name'}, ...]
    """
    app_id = app_id or os.environ.get('LARK_APP_ID')
    app_secret = app_secret or os.environ.get('LARK_APP_SECRET')

    if not app_id or not app_secret:
        raise ValueError('LARK_APP_ID and LARK_APP_SECRET required')

    # Get tenant access token
    token_resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': app_id, 'app_secret': app_secret},
        timeout=10
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    if token_data.get('code') != 0:
        raise RuntimeError(f"Failed to get token: {token_data}")

    token = token_data['tenant_access_token']

    # List groups (chats) the bot is in
    groups_resp = requests.get(
        'https://open.feishu.cn/open-apis/im/v1/chats',
        headers={'Authorization': f'Bearer {token}'},
        params={'page_size': 100},
        timeout=10
    )
    groups_resp.raise_for_status()
    groups_data = groups_resp.json()

    if groups_data.get('code') != 0:
        raise RuntimeError(f"Failed to list groups: {groups_data}")

    groups = []
    for item in groups_data.get('data', {}).get('items', []):
        groups.append({
            'chat_id': item.get('chat_id'),
            'name': item.get('name', 'Unnamed Group')
        })

    return groups


def send_cm_eg_report(png_paths: list, target_groups: list = None) -> None:
    """Upload PNGs and send CM-EG report card to Lark group(s)."""
    if not target_groups:
        target_groups = [LARK_CHAT_ID]

    label_map = {
        'CM_EG_Teams_Summary.png': 'Teams Summary',
        'CM_EG_Ranking.png':       'Individual Ranking',
    }
    valid = [(label_map.get(os.path.basename(p), os.path.basename(p)), p)
             for p in png_paths if os.path.exists(p)]
    if not valid:
        print('WARNING: No PNGs to send')
        return

    token = get_token()
    print(f'Lark token OK. Uploading {len(valid)} image(s)...')

    keys = [upload_image(token, pair[1]) for pair in valid]

    today = datetime.now().strftime('%Y-%m-%d')
    send_card(
        token=token,
        title=f'CM-EG Daily Report — {today}',
        color='blue',
        image_keys=keys,
        labels=[p[0] for p in valid],
        chat_ids=target_groups,
    )
    print(f'Lark card sent to {len(target_groups)} group(s) ({len(keys)} image(s)).')
