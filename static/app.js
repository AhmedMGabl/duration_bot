/**
 * app.js
 * Duration Bot UI - API interactions, polling, and event delegation
 */

class DurationBotUI {
    constructor() {
        this.pollInterval = null;
        this.statusPollInterval = null;
        this.selectedGroups = [];
        this.groups = [];
        this.currentSchedule = null;
        this.isRunning = false;

        this.init();
    }

    /**
     * Initialize UI - load data and attach event listeners
     */
    async init() {
        try {
            // Load initial data
            await this.loadGroups();
            await this.loadSchedule();
            await this.loadHistory();
            await this.loadStatus();
            await this.loadRawdataInfo();
            await this.loadTeamStructureInfo();

            // Attach event listeners
            this.attachEventListeners();

            // Start polling for updates
            this.startPolling();

            console.log('UI initialized successfully');
        } catch (error) {
            console.error('Initialization error:', error);
            this.showError('Failed to initialize UI: ' + error.message);
        }
    }

    /**
     * Attach all event listeners
     */
    attachEventListeners() {
        // Schedule controls
        document.getElementById('saveScheduleBtn').addEventListener('click', () => this.saveSchedule());
        document.getElementById('cronInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.saveSchedule();
        });
        document.getElementById('enableToggle').addEventListener('change', () => this.saveSchedule());

        // Manual control
        document.getElementById('runNowBtn').addEventListener('click', () => this.runPipelineNow());

        // Groups
        document.getElementById('refreshGroupsBtn').addEventListener('click', () => this.loadGroups());

        // Rawdata upload
        const rawdataInput = document.getElementById('rawdataFile');
        rawdataInput.addEventListener('change', () => {
            const name = rawdataInput.files[0] ? rawdataInput.files[0].name : 'No file chosen';
            document.getElementById('rawdataFilename').textContent = name;
            document.getElementById('uploadRawdataBtn').disabled = !rawdataInput.files[0];
        });
        document.getElementById('uploadRawdataBtn').addEventListener('click', () => this.uploadRawdata());

        // Team structure upload
        const fileInput = document.getElementById('teamStructureFile');
        fileInput.addEventListener('change', () => {
            const name = fileInput.files[0] ? fileInput.files[0].name : 'No file chosen';
            document.getElementById('teamStructureFilename').textContent = name;
            document.getElementById('uploadTeamStructureBtn').disabled = !fileInput.files[0];
        });
        document.getElementById('uploadTeamStructureBtn').addEventListener('click', () => this.uploadTeamStructure());

        // Modal close
        const modal = document.getElementById('groupDetailsModal');
        document.querySelector('.close').addEventListener('click', () => this.closeModal());
        window.addEventListener('click', (e) => {
            if (e.target === modal) this.closeModal();
        });

        // Event delegation for group checkboxes
        document.getElementById('groupsList').addEventListener('change', (e) => {
            if (e.target.type === 'checkbox') {
                this.toggleGroup(e.target.value, e.target.checked);
            }
        });
    }

    /**
     * Load available groups from API
     */
    async loadGroups() {
        try {
            const response = await fetch('/api/groups');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to load groups');
            }

            this.groups = data.groups || [];
            this.renderGroupsList();
            this.updateSelectedGroupsDisplay();

        } catch (error) {
            console.error('Error loading groups:', error);
            this.showError('Failed to load groups: ' + error.message);
        }
    }

    /**
     * Render groups list with checkboxes
     */
    renderGroupsList() {
        const container = document.getElementById('groupsList');

        if (!this.groups || this.groups.length === 0) {
            container.innerHTML = '<p class="placeholder">No groups available</p>';
            return;
        }

        const html = this.groups.map(group => {
            const isSelected = this.selectedGroups.includes(group.chat_id);
            // Escape group names to prevent XSS
            const escapedName = this.escapeHtml(group.name || group.chat_id);
            const escapedId = this.escapeHtml(group.chat_id);

            return `
                <div class="group-item">
                    <label class="group-label">
                        <input type="checkbox"
                               value="${escapedId}"
                               ${isSelected ? 'checked' : ''} />
                        <span class="group-name">${escapedName}</span>
                        <span class="group-id">(${escapedId})</span>
                    </label>
                </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    /**
     * Toggle group selection
     */
    toggleGroup(chatId, isChecked) {
        const index = this.selectedGroups.indexOf(chatId);

        if (isChecked && index === -1) {
            this.selectedGroups.push(chatId);
        } else if (!isChecked && index > -1) {
            this.selectedGroups.splice(index, 1);
        }

        this.updateSelectedGroupsDisplay();
    }

    /**
     * Update display of selected groups
     */
    updateSelectedGroupsDisplay() {
        const container = document.getElementById('selectedGroupsDisplay');

        if (this.selectedGroups.length === 0) {
            container.innerHTML = '<p class="placeholder">No groups selected yet</p>';
            return;
        }

        const html = this.selectedGroups.map(chatId => {
            const group = this.groups.find(g => g.chat_id === chatId);
            const name = group ? (group.name || chatId) : chatId;
            const escapedName = this.escapeHtml(name);

            return `
                <div class="selected-group-tag">
                    <span>${escapedName}</span>
                    <button class="remove-btn" data-chat-id="${this.escapeHtml(chatId)}"
                            type="button">×</button>
                </div>
            `;
        }).join('');

        container.innerHTML = html;

        // Add event listeners to remove buttons
        container.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const chatId = btn.getAttribute('data-chat-id');
                this.toggleGroup(chatId, false);
                this.renderGroupsList();
            });
        });
    }

    /**
     * Load current schedule configuration
     */
    async loadSchedule() {
        try {
            const response = await fetch('/api/schedule');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to load schedule');
            }

            this.currentSchedule = data;
            this.selectedGroups = data.selected_groups || [];

            // Update UI
            document.getElementById('cronInput').value = data.cron_expression || '';
            document.getElementById('enableToggle').checked = data.enabled || false;
            this.updateNextRunDisplay(data.next_run);
            this.renderGroupsList();
            this.updateSelectedGroupsDisplay();

        } catch (error) {
            console.error('Error loading schedule:', error);
            this.showError('Failed to load schedule: ' + error.message);
        }
    }

    /**
     * Save schedule configuration
     */
    async saveSchedule() {
        try {
            const cronExpr = document.getElementById('cronInput').value.trim();
            const enabled = document.getElementById('enableToggle').checked;

            if (!cronExpr) {
                this.showError('Cron expression is required');
                return;
            }

            const payload = {
                cron_expression: cronExpr,
                enabled: enabled,
                selected_groups: this.selectedGroups
            };

            const response = await fetch('/api/schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to save schedule');
            }

            this.currentSchedule = data;
            this.showSuccess('Schedule saved successfully');
            this.updateNextRunDisplay(data.next_run);

        } catch (error) {
            console.error('Error saving schedule:', error);
            this.showError('Failed to save schedule: ' + error.message);
        }
    }

    /**
     * Update next run display
     */
    updateNextRunDisplay(nextRun) {
        const label = document.getElementById('nextRunLabel');
        if (nextRun) {
            const date = new Date(nextRun);
            const formatted = date.toLocaleString();
            label.textContent = 'Next Scheduled Run: ' + formatted;
        } else {
            label.textContent = 'Next Scheduled Run: Not scheduled';
        }
    }

    /**
     * Load run history
     */
    async loadHistory() {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to load history');
            }

            this.renderHistory(data.runs || []);

        } catch (error) {
            console.error('Error loading history:', error);
            document.getElementById('historyList').innerHTML =
                '<p class="error">Failed to load history</p>';
        }
    }

    /**
     * Render run history
     */
    renderHistory(runs) {
        const container = document.getElementById('historyList');

        if (!runs || runs.length === 0) {
            container.innerHTML = '<p class="placeholder">No runs yet</p>';
            return;
        }

        const html = runs.map(run => {
            const startTime = new Date(run.started_at).toLocaleString();
            const completedTime = run.completed_at ? new Date(run.completed_at).toLocaleString() : '-';
            const statusClass = 'status-' + run.status;
            const escapedStatus = this.escapeHtml(run.status);
            const escapedTrigger = this.escapeHtml(run.trigger_type || 'unknown');
            const escapedError = this.escapeHtml(run.error_message || '');

            let groupsHtml = '';
            if (run.groups_sent && Array.isArray(run.groups_sent)) {
                groupsHtml = run.groups_sent.map(g => this.escapeHtml(g)).join(', ');
            }

            let errorHtml = '';
            if (run.error_message) {
                errorHtml = `<div class="error-message">${escapedError}</div>`;
            }

            return `
                <div class="history-item ${statusClass}">
                    <div class="history-header">
                        <span class="history-status">${escapedStatus}</span>
                        <span class="history-trigger">${escapedTrigger}</span>
                        <span class="history-time">${startTime}</span>
                    </div>
                    <div class="history-body">
                        ${groupsHtml ? `<div class="history-groups">Groups: ${groupsHtml}</div>` : ''}
                        <div class="history-completed">Completed: ${completedTime}</div>
                        ${errorHtml}
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    /**
     * Load current status
     */
    async loadStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to load status');
            }

            this.updateStatusDisplay(data);

        } catch (error) {
            console.error('Error loading status:', error);
        }
    }

    /**
     * Update status display
     */
    updateStatusDisplay(status) {
        const indicator = document.getElementById('statusIndicator');
        const text = document.getElementById('statusText');

        this.isRunning = status.is_running || false;

        if (this.isRunning) {
            indicator.className = 'status-indicator running';
            text.textContent = 'Pipeline Running';
        } else {
            indicator.className = 'status-indicator idle';
            text.textContent = 'Ready';
        }

        // Update run button state
        document.getElementById('runNowBtn').disabled = this.isRunning;
    }

    /**
     * Run pipeline now
     */
    async runPipelineNow() {
        try {
            if (this.isRunning) {
                this.showError('Pipeline is already running');
                return;
            }

            const progressDiv = document.getElementById('runProgress');
            progressDiv.style.display = 'block';

            const response = await fetch('/api/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ groups: this.selectedGroups })
            });

            const data = await response.json();

            if (response.status === 202 || (response.ok && data.success)) {
                this.showSuccess('Pipeline started in background');
                this.isRunning = true;
                document.getElementById('runNowBtn').disabled = true;

                // Start polling for completion
                this.pollForCompletion();
            } else {
                throw new Error(data.error || 'Failed to start pipeline');
            }

        } catch (error) {
            console.error('Error running pipeline:', error);
            this.showError('Failed to run pipeline: ' + error.message);
            document.getElementById('runProgress').style.display = 'none';
        }
    }

    /**
     * Poll for pipeline completion
     */
    pollForCompletion() {
        const pollFn = async () => {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to check status');
                }

                this.updateStatusDisplay(data);

                if (!data.is_running) {
                    // Pipeline completed
                    document.getElementById('runProgress').style.display = 'none';
                    clearInterval(this.completionPollInterval);
                    this.showSuccess('Pipeline completed');
                    await this.loadHistory();
                }

            } catch (error) {
                console.error('Error polling for completion:', error);
            }
        };

        // Poll every 2 seconds
        this.completionPollInterval = setInterval(pollFn, 2000);

        // Stop polling after 1 hour
        setTimeout(() => {
            if (this.completionPollInterval) {
                clearInterval(this.completionPollInterval);
            }
        }, 3600000);
    }

    /**
     * Start regular polling for updates
     */
    startPolling() {
        // Poll status every 30 seconds
        this.statusPollInterval = setInterval(async () => {
            try {
                await this.loadStatus();
                await this.loadHistory();
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 30000);

        // Poll schedule every 60 seconds
        this.pollInterval = setInterval(async () => {
            try {
                await this.loadSchedule();
            } catch (error) {
                console.error('Schedule polling error:', error);
            }
        }, 60000);
    }

    /**
     * Show success message
     */
    showSuccess(message) {
        const statusEl = document.getElementById('scheduleStatus') || document.getElementById('runStatus');
        if (statusEl) {
            statusEl.className = 'status-message success';
            statusEl.textContent = message;
            setTimeout(() => {
                statusEl.textContent = '';
                statusEl.className = 'status-message';
            }, 5000);
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        const statusEl = document.getElementById('scheduleStatus') || document.getElementById('runStatus');
        if (statusEl) {
            statusEl.className = 'status-message error';
            statusEl.textContent = message;
            setTimeout(() => {
                statusEl.textContent = '';
                statusEl.className = 'status-message';
            }, 5000);
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }

    /**
     * Load rawdata file info
     */
    async loadRawdataInfo() {
        try {
            const response = await fetch('/api/rawdata');
            const data = await response.json();
            const container = document.getElementById('rawdataInfo');

            if (data.exists) {
                const modified = new Date(data.modified).toLocaleString();
                const sizeKb = (data.size / 1024).toFixed(1);
                container.innerHTML = `
                    <div class="file-info">
                        <span class="file-icon">📊</span>
                        <span class="file-name">${this.escapeHtml(data.filename)}</span>
                        <span class="file-meta">${sizeKb} KB &bull; Last updated: ${modified}</span>
                    </div>`;
            } else {
                container.innerHTML = '<p class="warning">No rawdata.xlsx found. Please upload one before running the pipeline.</p>';
            }
        } catch (error) {
            console.error('Error loading rawdata info:', error);
            document.getElementById('rawdataInfo').innerHTML =
                '<p class="error">Failed to check rawdata file</p>';
        }
    }

    /**
     * Upload rawdata.xlsx file
     */
    async uploadRawdata() {
        const fileInput = document.getElementById('rawdataFile');
        const btn = document.getElementById('uploadRawdataBtn');
        const statusEl = document.getElementById('rawdataStatus');

        if (!fileInput.files[0]) return;

        btn.disabled = true;
        statusEl.className = 'status-message';
        statusEl.textContent = 'Uploading...';

        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            const response = await fetch('/api/rawdata', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Upload failed');
            }

            statusEl.className = 'status-message success';
            statusEl.textContent = 'rawdata.xlsx uploaded successfully';
            fileInput.value = '';
            document.getElementById('rawdataFilename').textContent = 'No file chosen';

            await this.loadRawdataInfo();

            setTimeout(() => {
                statusEl.textContent = '';
                statusEl.className = 'status-message';
            }, 5000);

        } catch (error) {
            console.error('Error uploading rawdata:', error);
            statusEl.className = 'status-message error';
            statusEl.textContent = 'Upload failed: ' + error.message;
        } finally {
            btn.disabled = false;
        }
    }

    /**
     * Load team structure file info
     */
    async loadTeamStructureInfo() {
        try {
            const response = await fetch('/api/team-structure');
            const data = await response.json();
            const container = document.getElementById('teamStructureInfo');

            if (data.exists) {
                const modified = new Date(data.modified).toLocaleString();
                const sizeKb = (data.size / 1024).toFixed(1);
                container.innerHTML = `
                    <div class="file-info">
                        <span class="file-icon">📄</span>
                        <span class="file-name">${this.escapeHtml(data.filename)}</span>
                        <span class="file-meta">${sizeKb} KB &bull; Last updated: ${modified}</span>
                    </div>`;
            } else {
                container.innerHTML = '<p class="warning">No Team Structure file found. Please upload one.</p>';
            }
        } catch (error) {
            console.error('Error loading team structure info:', error);
            document.getElementById('teamStructureInfo').innerHTML =
                '<p class="error">Failed to check team structure file</p>';
        }
    }

    /**
     * Upload team structure file
     */
    async uploadTeamStructure() {
        const fileInput = document.getElementById('teamStructureFile');
        const btn = document.getElementById('uploadTeamStructureBtn');
        const statusEl = document.getElementById('teamStructureStatus');

        if (!fileInput.files[0]) return;

        btn.disabled = true;
        statusEl.className = 'status-message';
        statusEl.textContent = 'Uploading...';

        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            const response = await fetch('/api/team-structure', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Upload failed');
            }

            statusEl.className = 'status-message success';
            statusEl.textContent = 'File uploaded successfully';
            fileInput.value = '';
            document.getElementById('teamStructureFilename').textContent = 'No file chosen';

            await this.loadTeamStructureInfo();

            setTimeout(() => {
                statusEl.textContent = '';
                statusEl.className = 'status-message';
            }, 5000);

        } catch (error) {
            console.error('Error uploading team structure:', error);
            statusEl.className = 'status-message error';
            statusEl.textContent = 'Upload failed: ' + error.message;
        } finally {
            btn.disabled = false;
        }
    }

    /**
     * Close modal
     */
    closeModal() {
        document.getElementById('groupDetailsModal').style.display = 'none';
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.durationBotUI = new DurationBotUI();
});
