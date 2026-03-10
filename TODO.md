# duration_bot TODO

## Tasks
- [x] Task 1: Project scaffolding
- [x] Task 2: Database schema
- [x] Task 3: Lark API integration
- [x] Task 4: Flask app foundation
- [x] Task 4b: Critical fixes (DB connection leak + scheduler shutdown)
- [x] Task 5: Flask API endpoints
- [x] Task 6: Scheduler integration
- [x] Task 7: Pipeline execution (Part 1-3 of Task 9 implementation)
- [x] Task 8: Frontend UI
- [x] Task 10: Frontend UI Files (index.html, app.js, style.css)
- [x] Task 11: Frontend UI Styling (CSS)
- [ ] Task 9: Docker containerization
- [ ] Task 12: Nginx configuration
- [ ] Task 13: Integration testing

## Critical Fixes Applied (Task 4b)
- [x] CRITICAL #1: Database connection leak fix - Using Flask g object pattern with teardown_appcontext
- [x] CRITICAL #2: Scheduler shutdown fix - Added atexit handler for graceful scheduler termination

## Task 9 Implementation (Pipeline Execution - Part 1-3)
- [x] Part 1: Modified pipeline_cm_eg.py to read TARGET_LARK_GROUPS from environment
  - Added json import
  - Read TARGET_LARK_GROUPS env var or fallback to default LARK_CHAT_ID
  - Pass target_groups to send_cm_eg_report()
- [x] Part 2: Implemented full run_pipeline() function in app.py
  - Creates run_history entry with 'running' status
  - Executes pipeline as subprocess with TARGET_LARK_GROUPS env var
  - Updates run_history with success/failed status and error messages
  - Prunes old history (keeps last 50 entries)
  - Returns run_id
  - Handles timeout and exception cases
- [x] Part 3: Added POST /api/run endpoint in app.py
  - Checks if pipeline already running (returns 409 if true)
  - Gets groups from request or uses saved schedule config
  - Runs pipeline in background thread
  - Returns 202 Accepted with message
- [x] Updated lark_sender.py to support multiple groups
  - Modified send_card() to accept chat_ids parameter and loop through groups
  - Modified send_cm_eg_report() to accept target_groups parameter
  - Passes target_groups to send_card()
