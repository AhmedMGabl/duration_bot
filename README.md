# Duration Bot

Web-based management interface for the call duration report generation pipeline. Provides a centralized control panel for scheduling automated report runs, selecting target Lark groups, monitoring execution history, and triggering manual pipeline executions.

## Features

### Group Selection
- Multi-select interface for choosing target Lark groups
- Real-time group list fetched from Lark API
- 5-minute cache for improved performance
- Visual display of currently selected groups

### Cron Scheduling
- Flexible cron expression configuration (minute hour day month day-of-week format)
- Enable/disable scheduling without losing configuration
- Automatic calculation of next scheduled run time
- Persistent storage of schedule settings

### Status Monitoring
- Real-time execution status indicator
- Active pipeline execution detection
- Visual status feedback in the web interface
- Display of next scheduled run time

### Run History
- Complete log of all pipeline executions
- Automatic retention of last 50 runs
- Status tracking (running, success, failed)
- Trigger type identification (manual vs. scheduled)
- Error message capture for failed runs
- Timestamp recording for all execution events

### Manual Trigger
- "Run Now" button for immediate pipeline execution
- Real-time progress feedback during execution
- Automatic refresh of history after completion
- Non-blocking execution with polling status updates

## Access URLs

### External Access (HTTPS)
```
https://your-domain:8443
```
Replace `your-domain` with your Elestio domain from the DOMAIN variable.

### Internal Access (HTTP)
```
http://172.17.0.1:15001
```
Used for internal container-to-container communication.

## Initial Setup

### Prerequisites
- Docker and Docker Compose installed
- Lark bot credentials (App ID and Secret)
- Access to the call duration dashboard
- Dashboard credentials (username and password)

### Steps

1. **Verify Project Structure**
   ```bash
   ls -la /opt/app/duration_bot/
   ```
   Should contain: `app.py`, `docker-compose.yml`, `static/`, `db/`, and pipeline files.

2. **Configure Environment Variables**
   Edit `/opt/app/duration_bot/docker-compose.yml` and set:
   - `DASHBOARD_URL`: URL of the call duration dashboard
   - `DASHBOARD_USER`: Dashboard login username
   - `DASHBOARD_PASS`: Dashboard login password
   - `LARK_APP_ID`: Lark bot application ID
   - `LARK_APP_SECRET`: Lark bot application secret

3. **Build and Start**
   ```bash
   cd /opt/app/duration_bot
   docker compose build
   docker compose up -d
   ```

4. **Verify Startup**
   ```bash
   docker compose logs -f
   ```
   Wait for message indicating Flask app is running.

5. **Access the Interface**
   Open your browser and navigate to:
   ```
   https://your-domain:8443
   ```

6. **Configure Nginx Routing** (if not already configured)
   The nginx reverse proxy should be configured to forward port 8443 to the duration_bot container (internal port 15001).

## Configuration

### Environment Variables

Located in `/opt/app/duration_bot/docker-compose.yml`, under the `environment` section:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DASHBOARD_URL` | Yes | `http://172.17.0.1:15010` | URL of the call duration dashboard |
| `DASHBOARD_USER` | Yes | - | Username for dashboard authentication |
| `DASHBOARD_PASS` | Yes | - | Password for dashboard authentication |
| `LARK_APP_ID` | Yes | - | Lark bot application ID |
| `LARK_APP_SECRET` | Yes | - | Lark bot application secret |

### Database

- **Location**: `/opt/app/duration_bot/db/duration_bot.db` (inside container)
- **Type**: SQLite3
- **Auto-initialization**: Database and tables are created automatically on first run
- **Tables**:
  - `schedule_config`: Stores cron schedule and selected groups
  - `run_history`: Tracks all pipeline executions
  - `available_groups`: Caches Lark groups (5-minute expiry)

### Docker Compose Configuration

The standalone `docker-compose.yml` includes:
- **Service**: `duration_bot` (Flask application)
- **Image**: Built from local Dockerfile
- **Port Binding**: `172.17.0.1:15001:5000`
- **Volumes**:
  - Input directory for pipeline data
  - Output directory for generated reports
  - Database persistence
  - Static files for web interface

## Usage Guide

### Setting the Schedule

1. **Open the Schedule Configuration panel**

2. **Enter a Cron Expression**
   - Format: `minute hour day month day-of-week`
   - Examples:
     - `0 9 * * MON-FRI` - Every weekday at 9:00 AM
     - `0 0 * * *` - Every day at midnight
     - `0 */6 * * *` - Every 6 hours
     - `30 8 * * 1-5` - Weekdays at 8:30 AM

3. **Enable the Schedule**
   - Check the "Enable Schedule" checkbox

4. **Verify Next Run Time**
   - The interface will show when the next execution is scheduled

5. **Click "Save Schedule"**
   - A success message confirms the configuration was saved

### Selecting Target Groups

1. **Open the Target Groups panel**

2. **Click "Refresh Groups"** (if groups don't load automatically)
   - This fetches the latest list from Lark API

3. **In Schedule Configuration panel, check the groups you want**
   - Multi-select is supported
   - Selected groups appear in the Target Groups display area

4. **Save Schedule** to persist your group selections

### Running Manually

1. **Navigate to Manual Control panel**

2. **Click "Run Pipeline Now"**
   - A spinner appears indicating execution is in progress
   - Do not close the browser during execution (typically takes 5-30 minutes)

3. **Monitor Progress**
   - Status updates in real-time
   - Browser continues polling for completion

4. **Check Results**
   - New entry appears in Run History
   - Reports are generated and sent to selected groups

### Monitoring Run History

The Run History panel shows:
- **Run ID**: Unique identifier for each execution
- **Started**: Timestamp when pipeline began
- **Completed**: Timestamp when pipeline finished (if completed)
- **Status**: One of:
  - `running` - Pipeline is currently executing
  - `success` - Pipeline completed successfully
  - `failed` - Pipeline encountered an error
- **Type**: Either `manual` (triggered by button) or `scheduled` (cron-based)
- **Groups**: Which Lark groups were targeted
- **Error**: Error message (if status is failed)

Only the last 50 runs are retained; older entries are automatically removed.

## Troubleshooting

### Groups Not Loading

**Problem**: The "Loading groups..." message persists.

**Solutions**:
1. Check Lark API credentials in docker-compose.yml
2. Verify the container can reach Lark API:
   ```bash
   docker compose exec duration_bot python -c "from lark_sender import get_bot_groups; print(get_bot_groups())"
   ```
3. Check container logs: `docker compose logs -f`

### Pipeline Execution Fails

**Problem**: Runs show status "failed" with error message.

**Solutions**:
1. Check error message in Run History for specific details
2. Verify all environment variables are set correctly
3. Test dashboard connectivity:
   ```bash
   curl -u $DASHBOARD_USER:$DASHBOARD_PASS $DASHBOARD_URL
   ```
4. Check container logs: `docker compose logs -f duration_bot`
5. Verify pipeline script exists: `ls -la pipeline_cm_eg.py`

### Schedule Not Executing

**Problem**: Cron schedule is enabled but pipeline doesn't run automatically.

**Solutions**:
1. Verify schedule is enabled (checkbox is checked)
2. Confirm next run time has passed (check "Next Scheduled Run" display)
3. Check container logs for scheduler errors: `docker compose logs -f`
4. Try manual "Run Now" to verify the pipeline itself works
5. Restart the container: `docker compose restart duration_bot`

### Port 8443 Connection Refused

**Problem**: Cannot access `https://your-domain:8443`

**Solutions**:
1. Verify nginx reverse proxy is configured for port 8443
2. Check container is running: `docker compose ps`
3. Verify port binding: `docker compose port duration_bot 5000`
4. Test internal connectivity: `curl -k https://172.17.0.1:15001`
5. Check nginx logs: `docker compose -f /opt/elestio/nginx/docker-compose.yml logs -f`

### Database Errors

**Problem**: "Database locked" or similar SQLite errors.

**Solutions**:
1. Restart the container: `docker compose restart duration_bot`
2. Check disk space: `df -h /opt/app/duration_bot/db/`
3. Verify file permissions: `ls -l /opt/app/duration_bot/db/`
4. Remove lock file if present: `rm -f /opt/app/duration_bot/db/duration_bot.db-*`

### Pipeline Timeout

**Problem**: Pipeline execution hits timeout (1 hour).

**Solutions**:
1. Check if dashboard is responding slowly
2. Verify screenshotter/CRM scraper functionality is working
3. Check system resources: `docker compose stats`
4. Review pipeline logs in container: `docker compose exec duration_bot tail -f logs/pipeline.log` (if available)

## Architecture Overview

### Components

```
┌─────────────────────────────────────────────────────────┐
│               Duration Bot Container                     │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Flask Application (app.py)                              │
│  ├── REST API Endpoints                                  │
│  ├── Static File Serving (index.html, app.js, style.css) │
│  └── Database Connection Management                      │
│                                                           │
│  APScheduler (Background)                                │
│  └── Cron Job Execution                                  │
│                                                           │
│  Pipeline Executor                                       │
│  ├── Subprocess Management                               │
│  ├── Environment Variable Passing                        │
│  └── Run History Tracking                                │
│                                                           │
│  Lark Integration (lark_sender.py)                       │
│  ├── Group List Fetching                                 │
│  └── Report Delivery                                     │
│                                                           │
│  Dashboard Client (dashboard_client.py)                  │
│  └── Call Duration Data Retrieval                        │
│                                                           │
│  Data Processing Pipeline (pipeline_cm_eg.py)            │
│  ├── Data Preparation (data_prep.py)                     │
│  ├── Screenshotting (screenshotter.py)                   │
│  ├── CRM Scraping (crm_scraper_linux.py)                 │
│  └── Report Generation & Delivery                        │
│                                                           │
│  SQLite Database (duration_bot.db)                       │
│  ├── Schedule Configuration                              │
│  ├── Run History                                         │
│  └── Groups Cache                                        │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### API Endpoints

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/` | GET | Serves main UI | HTML page |
| `/api/groups` | GET | Fetch available Lark groups | `{groups: [{chat_id, name}]}` |
| `/api/schedule` | GET | Get current schedule config | `{cron_expression, enabled, selected_groups, next_run}` |
| `/api/schedule` | POST | Update schedule config | `{success: true}` or error |
| `/api/history` | GET | Fetch run history | `{history: []}` |
| `/api/status` | GET | Get current execution status | `{running: bool, ...}` |
| `/api/run` | POST | Trigger immediate pipeline run | `{run_id: int}` |
| `/static/<file>` | GET | Serve static files | CSS, JS, etc. |

### Data Flow

1. **User Interaction**: Web UI (index.html + app.js)
2. **Request**: JavaScript fetch to Flask API
3. **Processing**:
   - Schedule config stored in SQLite
   - Groups fetched from Lark API (cached)
   - Pipeline execution via subprocess
4. **Tracking**: Run history recorded in database
5. **Response**: Status JSON returned to frontend

### Scheduler

- **Type**: APScheduler BackgroundScheduler
- **Trigger**: CronTrigger based on stored expression
- **Execution**: Spawns separate Python subprocess
- **Environment**: TARGET_LARK_GROUPS passed as JSON env var
- **Isolation**: Pipeline runs independently, doesn't block UI

### Database Schema

**schedule_config** table:
- `id`: Primary key (1)
- `cron_expression`: Cron pattern string
- `enabled`: Boolean flag
- `selected_groups`: JSON array of group IDs
- `updated_at`: Timestamp

**run_history** table:
- `id`: Auto-increment run ID
- `started_at`: Execution start timestamp
- `completed_at`: Execution end timestamp
- `status`: 'running', 'success', or 'failed'
- `trigger_type`: 'manual' or 'scheduled'
- `groups_sent`: JSON array of targeted groups
- `error_message`: Error details if failed

**available_groups** table:
- `chat_id`: Lark group ID
- `chat_name`: Lark group name
- `last_updated`: Cache timestamp

### Deployment Notes

- **Container Network**: Binds to `172.17.0.1` for internal communication
- **External Port**: 8443 (HTTPS via nginx reverse proxy)
- **Internal Port**: 5000 (Flask development server)
- **Persistence**: All data stored in `/opt/app/duration_bot/db/`
- **Restart Policy**: Always (automatically restarts on failure)
