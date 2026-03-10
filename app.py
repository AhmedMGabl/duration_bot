# -*- coding: utf-8 -*-
"""
app.py
Duration Bot management interface.
Flask app with REST API, static UI, and APScheduler.
"""
import os
import sys
import json
import sqlite3
import subprocess
import logging
import atexit
import threading
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory, g
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter

# Import Lark helper
from lark_sender import get_bot_groups

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
scheduler = BackgroundScheduler()

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'duration_bot.db')
PIPELINE_SCRIPT = os.path.join(os.path.dirname(__file__), 'pipeline_cm_eg.py')
INPUT_DIR = os.path.join(os.path.dirname(__file__), 'Input')
TEAM_STRUCTURE_PATH = os.path.join(INPUT_DIR, 'Team Structure.xlsx')
RAWDATA_PATH = os.path.join(INPUT_DIR, 'rawdata.xlsx')

# Initialize database on startup
from db_init import init_db
init_db()

def get_db():
    """Get database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    """Serve the main UI."""
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory('static', filename)

@app.route('/api/groups', methods=['GET'])
def api_groups():
    """Fetch available Lark groups."""
    try:
        # Try to get from cache first
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT chat_id, chat_name,
                   (julianday('now') - julianday(last_updated)) * 24 * 60 as age_minutes
            FROM available_groups
        ''')
        rows = cursor.fetchall()

        # Refresh if cache is empty or older than 5 minutes
        if not rows or rows[0]['age_minutes'] > 5:
            log.info('Refreshing groups cache from Lark API')
            groups = get_bot_groups()

            # Update cache
            cursor.execute('DELETE FROM available_groups')
            for g in groups:
                cursor.execute('''
                    INSERT INTO available_groups (chat_id, chat_name, last_updated)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (g['chat_id'], g['name']))
            conn.commit()

            return jsonify({'groups': groups})
        else:
            # Return cached
            groups = [{'chat_id': r['chat_id'], 'name': r['chat_name']} for r in rows]
            return jsonify({'groups': groups})

    except Exception as e:
        log.error(f'Failed to fetch groups: {e}')
        return jsonify({'error': str(e)}), 500

def run_pipeline(groups, trigger_type='manual'):
    """
    Execute pipeline with given groups.
    Creates run_history entry, executes subprocess, updates status, and prunes old history.
    Returns run_id.
    """
    try:
        # Create run_history entry with 'running' status
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO run_history (started_at, status, trigger_type, groups_sent)
            VALUES (CURRENT_TIMESTAMP, 'running', ?, ?)
        ''', (trigger_type, json.dumps(groups)))
        conn.commit()
        run_id = cursor.lastrowid
        conn.close()

        log.info(f'Created run_history entry {run_id} with status=running')

        # Build environment with TARGET_LARK_GROUPS
        env = os.environ.copy()
        env['TARGET_LARK_GROUPS'] = json.dumps(groups)

        # Execute pipeline as subprocess
        log.info(f'Executing pipeline subprocess (run_id={run_id}, groups={groups})')
        result = subprocess.run(
            [sys.executable, PIPELINE_SCRIPT],
            cwd=os.path.dirname(PIPELINE_SCRIPT),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )

        # Update run_history with result
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if result.returncode == 0:
            log.info(f'Pipeline execution succeeded (run_id={run_id})')
            cursor.execute('''
                UPDATE run_history
                SET status = 'success', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (run_id,))
        else:
            error_msg = result.stderr or result.stdout
            log.error(f'Pipeline execution failed (run_id={run_id}): {error_msg}')
            cursor.execute('''
                UPDATE run_history
                SET status = 'failed', completed_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
            ''', (error_msg[:1000], run_id))  # Truncate to 1000 chars

        conn.commit()

        # Prune old history (keep last 50)
        cursor.execute('''
            DELETE FROM run_history
            WHERE id NOT IN (
                SELECT id FROM run_history
                ORDER BY id DESC
                LIMIT 50
            )
        ''')
        conn.commit()
        conn.close()

        log.info(f'Pipeline execution complete (run_id={run_id})')
        return run_id

    except subprocess.TimeoutExpired:
        log.error(f'Pipeline execution timeout (run_id={run_id})')
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE run_history
            SET status = 'failed', completed_at = CURRENT_TIMESTAMP, error_message = ?
            WHERE id = ?
        ''', ('Pipeline execution timeout', run_id))
        conn.commit()
        conn.close()
        return run_id

    except Exception as e:
        log.error(f'Error in run_pipeline: {e}')
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE run_history
                SET status = 'failed', completed_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
            ''', (str(e)[:1000], run_id))
            conn.commit()
            conn.close()
        except:
            pass
        return None

@app.route('/api/schedule', methods=['GET'])
def api_schedule_get():
    """Get current schedule configuration with next run time."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cron_expression, enabled, selected_groups, updated_at
            FROM schedule_config
            WHERE id = 1
        ''')
        row = cursor.fetchone()

        if not row:
            return jsonify({'error': 'Schedule config not found'}), 404

        cron_expr = row['cron_expression']
        enabled = bool(row['enabled'])
        selected_groups = json.loads(row['selected_groups'])
        updated_at = row['updated_at']

        # Calculate next run
        next_run = None
        if enabled and cron_expr:
            try:
                cron = croniter(cron_expr)
                next_run = cron.get_next(datetime).isoformat()
            except Exception as e:
                log.error(f'Failed to calculate next run: {e}')

        return jsonify({
            'cron_expression': cron_expr,
            'enabled': enabled,
            'selected_groups': selected_groups,
            'updated_at': updated_at,
            'next_run': next_run
        })
    except Exception as e:
        log.error(f'Failed to fetch schedule: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedule', methods=['POST'])
def api_schedule_post():
    """Update schedule configuration."""
    try:
        data = request.get_json()

        # Validate input
        cron_expr = data.get('cron_expression', '').strip()
        enabled = data.get('enabled', True)
        selected_groups = data.get('selected_groups', [])

        if not cron_expr:
            return jsonify({'error': 'cron_expression is required'}), 400

        # Validate cron expression
        try:
            croniter(cron_expr)
        except Exception as e:
            return jsonify({'error': f'Invalid cron expression: {e}'}), 400

        # Validate groups
        if not isinstance(selected_groups, list):
            return jsonify({'error': 'selected_groups must be a list'}), 400

        # Update database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE schedule_config
            SET cron_expression = ?,
                enabled = ?,
                selected_groups = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (cron_expr, int(enabled), json.dumps(selected_groups)))
        conn.commit()

        # Update scheduler
        update_scheduler()

        # Calculate next run
        next_run = None
        if enabled and cron_expr:
            try:
                cron = croniter(cron_expr)
                next_run = cron.get_next(datetime).isoformat()
            except Exception as e:
                log.error(f'Failed to calculate next run: {e}')

        log.info(f'Schedule updated: enabled={enabled}, cron={cron_expr}, groups={selected_groups}')
        return jsonify({
            'success': True,
            'cron_expression': cron_expr,
            'enabled': enabled,
            'selected_groups': selected_groups,
            'next_run': next_run
        })
    except Exception as e:
        log.error(f'Failed to update schedule: {e}')
        return jsonify({'error': str(e)}), 500

def update_scheduler():
    """Remove old jobs and add new cron job if enabled."""
    try:
        # Remove existing job if any
        if scheduler.get_job('pipeline_job'):
            scheduler.remove_job('pipeline_job')
            log.info('Removed old pipeline job')

        # Read schedule config
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cron_expression, enabled
            FROM schedule_config
            WHERE id = 1
        ''')
        row = cursor.fetchone()
        conn.close()

        if row and row[1]:  # If enabled
            cron_expr = row[0]
            try:
                scheduler.add_job(
                    run_pipeline_scheduled,
                    CronTrigger.from_crontab(cron_expr),
                    id='pipeline_job',
                    name='Scheduled Pipeline Execution',
                    replace_existing=True
                )
                log.info(f'Added cron job with expression: {cron_expr}')
            except Exception as e:
                log.error(f'Failed to add cron job: {e}')
        else:
            log.info('Schedule not enabled, no job added')

    except Exception as e:
        log.error(f'Error updating scheduler: {e}')

def run_pipeline_scheduled():
    """Called by scheduler to run pipeline with selected groups."""
    try:
        log.info('run_pipeline_scheduled triggered')

        # Read selected groups from config
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT selected_groups
            FROM schedule_config
            WHERE id = 1
        ''')
        row = cursor.fetchone()
        conn.close()

        if not row:
            log.error('No schedule config found')
            return

        selected_groups = json.loads(row[0])
        if not selected_groups:
            log.warning('No groups selected for scheduled run')
            return

        log.info(f'Running pipeline with groups: {selected_groups}')
        run_pipeline(selected_groups, trigger_type='scheduled')

    except Exception as e:
        log.error(f'Error in run_pipeline_scheduled: {e}')

@app.route('/api/run', methods=['POST'])
def api_run():
    """
    Trigger pipeline run.
    POST body can contain: {'groups': ['chat_id1', 'chat_id2']}
    If groups not provided, uses saved schedule config.
    Returns 409 if already running, 200 with run_id otherwise.
    """
    try:
        # Check if already running
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM run_history
            WHERE status = 'running'
        ''')
        if cursor.fetchone()['count'] > 0:
            log.warning('Pipeline already running')
            return jsonify({'error': 'Pipeline already running'}), 409

        # Get groups from request or use saved config
        data = request.get_json() or {}
        groups = data.get('groups', None)

        if not groups:
            # Use saved config
            cursor.execute('''
                SELECT selected_groups
                FROM schedule_config
                WHERE id = 1
            ''')
            row = cursor.fetchone()
            if row:
                groups = json.loads(row['selected_groups'])
            else:
                groups = []

        if not groups:
            return jsonify({'error': 'No groups specified and no saved config'}), 400

        log.info(f'API /run triggered with groups: {groups}')

        # Run pipeline in background thread
        def background_run():
            try:
                run_pipeline(groups, trigger_type='manual')
            except Exception as e:
                log.error(f'Background run_pipeline failed: {e}')

        thread = threading.Thread(target=background_run, daemon=True)
        thread.start()

        # Return immediately with 202 Accepted
        return jsonify({'success': True, 'message': 'Pipeline started in background'}), 202

    except Exception as e:
        log.error(f'Error in api_run: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def api_history():
    """Get last 20 pipeline runs from run_history table."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, started_at, completed_at, status, trigger_type, groups_sent, error_message
            FROM run_history
            ORDER BY id DESC
            LIMIT 20
        ''')
        rows = cursor.fetchall()

        # Convert rows to dictionaries and parse groups_sent JSON
        history = []
        for row in rows:
            history.append({
                'id': row['id'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'status': row['status'],
                'trigger_type': row['trigger_type'],
                'groups_sent': json.loads(row['groups_sent']) if row['groups_sent'] else None,
                'error_message': row['error_message']
            })

        return jsonify({'runs': history})

    except Exception as e:
        log.error(f'Failed to fetch history: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def api_status():
    """Get bot status: is_running, last_run, next_run."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Check if bot is currently running
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM run_history
            WHERE status = 'running'
        ''')
        is_running = cursor.fetchone()['count'] > 0

        # Get last completed run
        cursor.execute('''
            SELECT started_at, status, groups_sent
            FROM run_history
            WHERE status != 'running'
            ORDER BY id DESC
            LIMIT 1
        ''')
        last_run_row = cursor.fetchone()

        last_run = None
        if last_run_row:
            last_run = {
                'started_at': last_run_row['started_at'],
                'status': last_run_row['status'],
                'groups_sent': json.loads(last_run_row['groups_sent']) if last_run_row['groups_sent'] else None
            }

        # Calculate next run from schedule_config
        cursor.execute('''
            SELECT cron_expression, enabled
            FROM schedule_config
            WHERE id = 1
        ''')
        schedule_row = cursor.fetchone()

        next_run = None
        if schedule_row and schedule_row['enabled'] and schedule_row['cron_expression']:
            try:
                cron = croniter(schedule_row['cron_expression'])
                next_run = cron.get_next(datetime).isoformat()
            except Exception as e:
                log.error(f'Failed to calculate next run: {e}')

        return jsonify({
            'is_running': is_running,
            'last_run': last_run,
            'next_run': next_run
        })

    except Exception as e:
        log.error(f'Failed to fetch status: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/rawdata', methods=['GET'])
def api_rawdata_get():
    """Return info about the current rawdata.xlsx file."""
    try:
        if os.path.exists(RAWDATA_PATH):
            stat = os.stat(RAWDATA_PATH)
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            return jsonify({
                'exists': True,
                'filename': 'rawdata.xlsx',
                'size': stat.st_size,
                'modified': modified,
            })
        else:
            return jsonify({'exists': False})
    except Exception as e:
        log.error(f'Failed to check rawdata: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/rawdata', methods=['POST'])
def api_rawdata_post():
    """Upload a new rawdata.xlsx file (CRM + IUR sheets)."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        f = request.files['file']
        if not f.filename:
            return jsonify({'error': 'Empty filename'}), 400

        if not f.filename.lower().endswith('.xlsx'):
            return jsonify({'error': 'Only .xlsx files are accepted'}), 400

        os.makedirs(INPUT_DIR, exist_ok=True)
        f.save(RAWDATA_PATH)

        stat = os.stat(RAWDATA_PATH)
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        log.info(f'rawdata.xlsx uploaded: {stat.st_size} bytes')
        return jsonify({
            'success': True,
            'filename': 'rawdata.xlsx',
            'size': stat.st_size,
            'modified': modified,
        })
    except Exception as e:
        log.error(f'Failed to upload rawdata: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/team-structure', methods=['GET'])
def api_team_structure_get():
    """Return info about the current Team Structure file."""
    try:
        if os.path.exists(TEAM_STRUCTURE_PATH):
            stat = os.stat(TEAM_STRUCTURE_PATH)
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            return jsonify({
                'exists': True,
                'filename': 'Team Structure.xlsx',
                'size': stat.st_size,
                'modified': modified,
            })
        else:
            return jsonify({'exists': False})
    except Exception as e:
        log.error(f'Failed to check team structure: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/team-structure', methods=['POST'])
def api_team_structure_post():
    """Upload a new Team Structure xlsx file."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        f = request.files['file']
        if not f.filename:
            return jsonify({'error': 'Empty filename'}), 400

        # Only accept xlsx files
        if not f.filename.lower().endswith('.xlsx'):
            return jsonify({'error': 'Only .xlsx files are accepted'}), 400

        os.makedirs(INPUT_DIR, exist_ok=True)
        f.save(TEAM_STRUCTURE_PATH)

        stat = os.stat(TEAM_STRUCTURE_PATH)
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        log.info(f'Team Structure uploaded: {stat.st_size} bytes')
        return jsonify({
            'success': True,
            'filename': 'Team Structure.xlsx',
            'size': stat.st_size,
            'modified': modified,
        })
    except Exception as e:
        log.error(f'Failed to upload team structure: {e}')
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    atexit.register(lambda: scheduler.shutdown(wait=False))
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=False)
