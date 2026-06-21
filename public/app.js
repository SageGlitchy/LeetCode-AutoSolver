// Global application state
let ws = null;
let reconnectInterval = null;

// Tab switcher
function switchTab(tabId) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(el => {
        el.classList.remove('active');
    });
    // Remove active class from nav buttons
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('active');
    });

    // Show selected tab content
    const selectedTab = document.getElementById(`tab-content-${tabId}`);
    if (selectedTab) selectedTab.classList.add('active');

    // Make clicked nav button active
    const selectedBtn = document.getElementById(`nav-btn-${tabId}`);
    if (selectedBtn) selectedBtn.classList.add('active');

    // Trigger tab-specific loads
    if (tabId === 'history') {
        loadHistory();
    } else if (tabId === 'settings') {
        loadConfig();
    } else if (tabId === 'dashboard') {
        loadStatus();
    }
}

// Password toggle helper
function togglePasswordVisibility(fieldId) {
    const input = document.getElementById(fieldId);
    if (!input) return;
    
    const icon = input.nextElementSibling.querySelector('i');
    if (input.type === 'password') {
        input.type = 'text';
        icon.className = 'fa-solid fa-eye-slash';
    } else {
        input.type = 'password';
        icon.className = 'fa-solid fa-eye';
    }
}

// Fetch dashboard status metrics
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error('Failed to fetch status');
        const data = await response.json();
        
        // Update total solved
        document.getElementById('val-solved-count').textContent = data.solved_count;
        
        // Update state
        const stateVal = document.getElementById('val-system-state');
        const stateDesc = document.getElementById('val-system-state-desc');
        const stateIcon = document.getElementById('status-running-icon');
        const runBtn = document.getElementById('btn-trigger-run');

        if (data.is_running) {
            stateVal.textContent = 'Active';
            stateVal.style.color = 'var(--accent-teal)';
            stateDesc.textContent = 'Running solver pipeline...';
            stateIcon.classList.add('spinning');
            runBtn.disabled = true;
            runBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Running...';
        } else {
            stateVal.textContent = 'Idle';
            stateVal.style.color = 'var(--text-main)';
            stateDesc.textContent = 'Ready for tasks';
            stateIcon.classList.remove('spinning');
            runBtn.disabled = false;
            runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run Solver Now';
        }

        // Update Next Scheduled time
        const nextRunVal = document.getElementById('val-next-run');
        const nextRunDesc = document.getElementById('val-next-run-desc');
        if (data.next_run) {
            const date = new Date(data.next_run);
            nextRunVal.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            nextRunDesc.textContent = `Trigger on ${date.toLocaleDateString()}`;
        } else {
            nextRunVal.textContent = 'Disabled';
            nextRunDesc.textContent = 'Scheduler inactive';
        }

        // Update cookie status indicator
        const dot = document.getElementById('header-cookie-dot');
        const statusText = document.getElementById('header-cookie-status');
        
        if (data.cookie_valid) {
            dot.className = 'pulse-dot green';
            statusText.textContent = data.cookie_status || 'Session Active';
            statusText.style.color = 'var(--text-muted)';
        } else {
            dot.className = 'pulse-dot red';
            statusText.textContent = data.cookie_status || 'Session Expired';
            statusText.style.color = 'var(--accent-red)';
        }

    } catch (err) {
        console.error('Error loading system status:', err);
    }
}

// Fetch configs to populate settings
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error('Failed to fetch config');
        const data = await response.json();
        
        document.getElementById('input-run-time').value = data.run_time || '01:00';
        document.getElementById('input-extra-count').value = data.target_extra_count ?? 3;
        
        // Select check boxes
        const diffs = data.difficulties || [];
        document.getElementById('check-diff-easy').checked = diffs.includes('Easy');
        document.getElementById('check-diff-medium').checked = diffs.includes('Medium');
        document.getElementById('check-diff-hard').checked = diffs.includes('Hard');
        
        document.getElementById('input-groq-api-key').value = data.groq_api_key || '';
        document.getElementById('input-lc-session').value = data.leetcode_session || '';
        document.getElementById('input-lc-csrf').value = data.leetcode_csrf || '';
        
    } catch (err) {
        console.error('Error loading config settings:', err);
    }
}

// Save configs
async function saveSettings() {
    const statusMsg = document.getElementById('settings-save-status');
    const saveBtn = document.getElementById('btn-save-settings');
    
    // Toggle state
    statusMsg.textContent = '';
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

    // Gather difficulties list
    const difficulties = [];
    if (document.getElementById('check-diff-easy').checked) difficulties.push('Easy');
    if (document.getElementById('check-diff-medium').checked) difficulties.push('Medium');
    if (document.getElementById('check-diff-hard').checked) difficulties.push('Hard');

    const payload = {
        target_extra_count: parseInt(document.getElementById('input-extra-count').value, 10),
        difficulties: difficulties,
        run_time: document.getElementById('input-run-time').value,
        leetcode_session: document.getElementById('input-lc-session').value.strip ? document.getElementById('input-lc-session').value.strip() : document.getElementById('input-lc-session').value.trim(),
        leetcode_csrf: document.getElementById('input-lc-csrf').value.trim(),
        groq_api_key: document.getElementById('input-groq-api-key').value.trim()
    };

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Save failed');
        }

        statusMsg.className = 'save-status-msg success';
        statusMsg.innerHTML = '<i class="fa-solid fa-circle-check"></i> Configuration saved!';
        
        // Reload status since cookies or scheduler time could have changed
        loadStatus();
        
    } catch (err) {
        statusMsg.className = 'save-status-msg error';
        statusMsg.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Error: ${err.message}`;
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Settings';
    }
}

// Fetch submission runs history
async function loadHistory() {
    const tbody = document.getElementById('history-tbody');
    tbody.innerHTML = `
        <tr>
            <td colspan="8" class="table-empty"><i class="fa-solid fa-spinner fa-spin"></i> Loading archive...</td>
        </tr>
    `;

    try {
        const response = await fetch('/api/history');
        if (!response.ok) throw new Error('Failed to fetch history');
        const data = await response.json();
        
        if (data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="table-empty">No run history recorded yet.</td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';
        data.forEach(item => {
            const tr = document.createElement('tr');
            
            // Format timestamp
            let formattedDate = 'N/A';
            if (item.timestamp) {
                const date = new Date(item.timestamp);
                formattedDate = date.toLocaleString();
            }

            // Difficulty Class styling
            const diffClass = (item.difficulty || '').toLowerCase();
            
            // Status Class styling
            let statusClass = 'polling';
            if (item.status === 'Accepted') statusClass = 'accepted';
            else if (item.status && item.status.includes('Failed') || item.status && item.status.includes('Error') || item.status === 'Wrong Answer') statusClass = 'failed';

            tr.innerHTML = `
                <td>${formattedDate}</td>
                <td><strong>#${item.problem_id}</strong></td>
                <td>${item.title || 'Unknown'}</td>
                <td><span class="badge-diff ${diffClass}">${item.difficulty || 'Easy'}</span></td>
                <td><span class="badge-status ${statusClass}">${item.status || 'Unknown'}</span></td>
                <td>${item.runtime_percentile || 'N/A'}</td>
                <td>${item.memory_percentile || 'N/A'}</td>
                <td><small>${item.source || 'Groq'}</small></td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="table-empty" style="color: var(--accent-red);">
                    <i class="fa-solid fa-circle-exclamation"></i> Error loading history: ${err.message}
                </td>
            </tr>
        `;
    }
}

// Trigger solver execution now
async function triggerRun() {
    const runBtn = document.getElementById('btn-trigger-run');
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Triggering...';

    try {
        const response = await fetch('/api/run', { method: 'POST' });
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Could not trigger run');
        }
        
        // Wait 1 second and refresh status
        setTimeout(loadStatus, 1000);
        
    } catch (err) {
        alert(`Failed to trigger execution: ${err.message}`);
        loadStatus();
    }
}

// Terminal Console Management
function clearConsole() {
    const output = document.getElementById('console-output');
    output.innerHTML = '<div class="console-line system-msg">Console cleared.</div>';
}

function appendConsoleLine(message) {
    const consoleDiv = document.getElementById('console-output');
    const isAtBottom = consoleDiv.scrollHeight - consoleDiv.clientHeight <= consoleDiv.scrollTop + 50;

    const line = document.createElement('div');
    line.className = 'console-line';
    
    // Style check details or error highlights
    if (message.includes('Error') || message.includes('Exception') || message.includes('Failed')) {
        line.classList.add('error-msg');
    } else if (message.includes('STARTING') || message.includes('COMPLETE') || message.includes('>>>')) {
        line.classList.add('system-msg');
    }
    
    line.textContent = message;
    consoleDiv.appendChild(line);

    // Keep console output scroll pinned to bottom if it was already near the bottom
    if (isAtBottom) {
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    }
}

// Setup WebSocket Log Stream
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUri = `${protocol}//${window.location.host}/ws/logs`;
    
    const badge = document.getElementById('ws-status-badge');
    badge.textContent = 'Connecting...';
    badge.className = 'console-status-badge';

    ws = new WebSocket(wsUri);

    ws.onopen = () => {
        badge.textContent = 'Live';
        badge.className = 'console-status-badge connected';
        console.log('WebSocket terminal log stream connected.');
        if (reconnectInterval) {
            clearInterval(reconnectInterval);
            reconnectInterval = null;
        }
    };

    ws.onmessage = (event) => {
        appendConsoleLine(event.data);
    };

    ws.onclose = () => {
        badge.textContent = 'Disconnected';
        badge.className = 'console-status-badge';
        console.log('WebSocket terminal log stream disconnected.');
        
        // Auto-reconnect in 5 seconds
        if (!reconnectInterval) {
            reconnectInterval = setInterval(connectWebSocket, 5000);
        }
    };

    ws.onerror = (err) => {
        console.error('WebSocket encountered error: ', err);
        ws.close();
    };
}

// Initialize components on window load
window.addEventListener('load', () => {
    // Connect websocket logs
    connectWebSocket();
    
    // Load dashboard metrics
    loadStatus();
    
    // Poll status updates every 4 seconds in the background
    setInterval(loadStatus, 4000);
});
