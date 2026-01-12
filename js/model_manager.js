/**
 * UmiAI Model Manager (VNCCS-style repo sync)
 */
(function () {
    'use strict';

    let modelManagerPanel = null;
    let models = [];
    let downloadStatuses = {};
    let pollingInterval = null;
    let isLoading = false;

    const DEFAULT_REPO_ID = 'Tinuva/Comfy-Umi';

    function resetRepoId() {
        localStorage.setItem('umi_model_repo', DEFAULT_REPO_ID);
    }

    function getRepoId() {
        return localStorage.getItem('umi_model_repo') || DEFAULT_REPO_ID;
    }

    function setRepoId(value) {
        localStorage.setItem('umi_model_repo', value);
    }

    async function updateUtilitiesBadge() {
        const badge = document.getElementById('umi-mm-mode');
        if (!badge) {
            return;
        }
        try {
            const response = await fetch('/umiapp/utilities/status');
            if (!response.ok) {
                throw new Error('status');
            }
            const data = await response.json();
            if (data && data.installed) {
                badge.textContent = 'Core + Utilities';
                badge.title = 'umi_utilities detected. Showing full model catalog.';
                return;
            }
        } catch (error) {
            // Keep default label if status is unavailable.
        }
        badge.textContent = 'Core models only';
        badge.title = 'Utilities-only models are hidden unless umi_utilities is installed.';
    }

    function showModelManager() {
        if (modelManagerPanel) {
            modelManagerPanel.style.display = 'flex';
            startPolling();
            loadModels();
            return;
        }

        modelManagerPanel = document.createElement('div');
        modelManagerPanel.id = 'umi-model-manager';
        modelManagerPanel.innerHTML = `
            <div class="umi-mm-overlay" onclick="window.umiModelManager.hide()"></div>
            <div class="umi-mm-container">
                <div class="umi-mm-header">
                    <h2>UmiAI Model Manager</h2>
                    <button class="umi-mm-close" onclick="window.umiModelManager.hide()">X</button>
                </div>
                <div class="umi-mm-controls">
                    <label>Repo ID</label>
                    <input id="umi-mm-repo" type="text" placeholder="owner/repo" />
                    <button id="umi-mm-check" class="umi-mm-btn">Check Models</button>
                </div>
                <div class="umi-mm-status-bar">
                    <span id="umi-mm-status-text">Idle</span>
                    <span id="umi-mm-mode" class="umi-mm-mode" title="Utilities-only models are hidden unless umi_utilities is installed.">Core models only</span>
                    <button id="umi-mm-download-all" class="umi-mm-btn-primary">Download All Missing/Updates</button>
                </div>
                <div class="umi-mm-deps" id="umi-mm-deps" style="display:none;"></div>
                <div class="umi-mm-content" id="umi-mm-content">
                    <div class="umi-mm-loading">Loading models...</div>
                </div>
                <div class="umi-mm-footer">
                    <span id="umi-mm-repo-label"></span>
                </div>
            </div>
        `;

        const style = document.createElement('style');
        style.textContent = `
            #umi-model-manager {
                display: flex;
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                z-index: 10000;
                align-items: center;
                justify-content: center;
                font-family: sans-serif;
            }
            .umi-mm-mode {
                font-size: 12px;
                color: #9ad0ff;
                background: rgba(74, 158, 255, 0.15);
                border: 1px solid rgba(74, 158, 255, 0.35);
                padding: 4px 8px;
                border-radius: 999px;
                margin-right: 8px;
                white-space: nowrap;
            }
            .umi-mm-overlay {
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.7);
            }
            .umi-mm-container {
                position: relative;
                background: #1e1e1e;
                border-radius: 12px;
                width: 900px;
                max-width: 92vw;
                max-height: 82vh;
                display: flex;
                flex-direction: column;
                box-shadow: 0 8px 32px rgba(0,0,0,0.5);
            }
            .umi-mm-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 20px;
                border-bottom: 1px solid #333;
            }
            .umi-mm-header h2 {
                margin: 0;
                font-size: 18px;
                color: #fff;
            }
            .umi-mm-close {
                background: none;
                border: none;
                color: #888;
                font-size: 20px;
                cursor: pointer;
            }
            .umi-mm-close:hover { color: #fff; }
            .umi-mm-controls {
                display: flex;
                gap: 10px;
                align-items: center;
                padding: 12px 20px;
                border-bottom: 1px solid #333;
                background: #252525;
            }
            .umi-mm-controls label {
                color: #aaa;
                font-size: 12px;
            }
            .umi-mm-controls input {
                flex: 1;
                background: #111;
                border: 1px solid #444;
                color: #fff;
                padding: 6px 8px;
                border-radius: 6px;
            }
            .umi-mm-btn {
                background: #333;
                border: 1px solid #555;
                color: #ddd;
                padding: 6px 12px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 12px;
            }
            .umi-mm-btn:hover { background: #3a3a3a; }
            .umi-mm-btn-primary {
                background: linear-gradient(135deg, #4a9eff 0%, #3b7ed0 100%);
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 500;
            }
            .umi-mm-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
            .umi-mm-status-bar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 20px;
                border-bottom: 1px solid #333;
            }
            #umi-mm-status-text {
                color: #aaa;
                font-size: 13px;
            }
            .umi-mm-content {
                flex: 1;
                overflow-y: auto;
                padding: 14px 20px;
            }
            .umi-mm-loading {
                text-align: center;
                color: #888;
                padding: 40px;
            }
            .umi-mm-model {
                display: grid;
                grid-template-columns: 1fr 140px 160px 120px;
                gap: 12px;
                align-items: center;
                padding: 10px 12px;
                background: #2a2a2a;
                border-radius: 6px;
                margin-bottom: 8px;
                border: 1px solid #333;
            }
            .umi-mm-model-name {
                color: #fff;
                font-size: 14px;
                font-weight: 600;
            }
            .umi-mm-model-desc {
                color: #888;
                font-size: 11px;
                margin-top: 2px;
            }
            .umi-mm-select {
                background: #111;
                border: 1px solid #444;
                color: #ddd;
                padding: 4px 6px;
                border-radius: 4px;
                font-size: 12px;
                width: 100%;
            }
            .umi-mm-status {
                font-size: 11px;
                color: #bbb;
            }
            .umi-mm-footer {
                padding: 10px 20px;
                border-top: 1px solid #333;
                color: #666;
                font-size: 11px;
            }
            .umi-mm-inline {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .umi-mm-deps {
                padding: 8px 20px;
                border-bottom: 1px dashed #333;
                background: #241d12;
                color: #d6b35c;
                font-size: 12px;
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(modelManagerPanel);

        const repoInput = document.getElementById('umi-mm-repo');
        const checkBtn = document.getElementById('umi-mm-check');
        const downloadAllBtn = document.getElementById('umi-mm-download-all');

        repoInput.value = getRepoId();
        repoInput.addEventListener('change', () => setRepoId(repoInput.value.trim()));
        checkBtn.addEventListener('click', () => loadModels());
        downloadAllBtn.addEventListener('click', () => downloadAll());

        startPolling();
        loadModels();
        updateDependencyStatus();
        updateUtilitiesBadge();
    }

    function hideModelManager() {
        if (modelManagerPanel) modelManagerPanel.style.display = 'none';
    }

    async function loadModels() {
        const content = document.getElementById('umi-mm-content');
        const statusText = document.getElementById('umi-mm-status-text');
        const repoInput = document.getElementById('umi-mm-repo');
        const repoLabel = document.getElementById('umi-mm-repo-label');

        if (isLoading) return;
        isLoading = true;
        content.innerHTML = '<div class="umi-mm-loading">Loading models...</div>';

        const repoId = repoInput.value.trim();
        setRepoId(repoId);
        repoLabel.textContent = repoId ? `Repo: ${repoId}` : '';

        try {
            const response = await fetch(`/umiapp/models/check?repo_id=${encodeURIComponent(repoId)}`);
            const data = await response.json();
            if (data.error) {
                content.innerHTML = `<div class="umi-mm-loading">Error: ${data.error}</div>`;
                statusText.textContent = 'Error fetching models';
                return;
            }

            models = data.models || [];
            statusText.textContent = `Loaded ${models.length} models`;
            renderList();
            await updateStatuses();
            window.dispatchEvent(new CustomEvent("umi-model-registry-updated"));

        } catch (err) {
            content.innerHTML = `<div class="umi-mm-loading">Error: ${err.message}</div>`;
        } finally {
            isLoading = false;
        }
    }

    async function updateStatuses() {
        try {
            const response = await fetch('/umiapp/models/status');
            if (response.ok) {
                downloadStatuses = await response.json();
                if (models.length > 0) renderList();
            }
        } catch (e) {
        }
    }

    async function updateDependencyStatus() {
        const depsBanner = document.getElementById('umi-mm-deps');
        if (!depsBanner) return;
        try {
            const response = await fetch('/umiapp/deps');
            if (!response.ok) return;
            const data = await response.json();
            const missing = data.missing || [];
            if (missing.length) {
                depsBanner.textContent = `Missing optional dependencies: ${missing.join(', ')}. Install with: pip install ${missing.join(' ')}`;
                depsBanner.style.display = 'block';
            } else {
                depsBanner.style.display = 'none';
            }
        } catch (e) {
        }
    }

    function startPolling() {
        if (pollingInterval) clearInterval(pollingInterval);
        pollingInterval = setInterval(updateStatuses, 2000);
    }

    function normalizeVer(v) {
        return String(v || '').toLowerCase().replace(/^v/, '').trim();
    }

    function formatVer(v) {
        if (!v) return '';
        return String(v).startsWith('v') ? String(v) : `v${v}`;
    }

    function modelHasVersion(model, version) {
        const target = normalizeVer(version);
        return (model.installed_versions || []).some(v => normalizeVer(v) === target);
    }

    function renderList() {
        const content = document.getElementById('umi-mm-content');
        if (!models.length) {
            content.innerHTML = '<div class="umi-mm-loading">No models found.</div>';
            return;
        }

        content.innerHTML = '';
        models.forEach(model => {
            const status = downloadStatuses[model.name];
            const activeVer = model.active_version;
            const latestVer = model.version;

            const row = document.createElement('div');
            row.className = 'umi-mm-model';
            row.dataset.modelName = model.name;

            const info = document.createElement('div');
            info.innerHTML = `
                <div class="umi-mm-model-name">${model.name}</div>
                <div class="umi-mm-model-desc">${model.description || ''}</div>
            `;

            const select = document.createElement('select');
            select.className = 'umi-mm-select';
            (model.versions || []).forEach(v => {
                const option = document.createElement('option');
                option.value = v.version;
                option.textContent = formatVer(v.version);
                select.appendChild(option);
            });
            if (activeVer) {
                select.value = activeVer;
            } else if (latestVer) {
                select.value = latestVer;
            }

            select.addEventListener('change', () => {
                if (modelHasVersion(model, select.value)) {
                    setActiveVersion(model.name, select.value);
                }
                renderList();
            });

            const statusEl = document.createElement('div');
            statusEl.className = 'umi-mm-status';

            const action = document.createElement('div');
            action.className = 'umi-mm-inline';

            let buttonText = '';
            let actionHandler = null;

            if (status && (status.status === 'downloading' || status.status === 'queued')) {
                statusEl.textContent = status.message || status.status;
                buttonText = 'Downloading';
                actionHandler = null;
            } else if (status && status.status === 'auth_required') {
                statusEl.textContent = 'API Key Required';
                buttonText = 'Enter Key';
                actionHandler = () => showApiKeyDialog();
            } else if (status && status.status === 'error') {
                statusEl.textContent = status.message || 'Download error';
                buttonText = 'Retry';
                actionHandler = () => downloadModel(model.name, select.value);
            } else {
                const selectedInstalled = modelHasVersion(model, select.value);
                if (!selectedInstalled) {
                    statusEl.textContent = model.status === 'missing' ? 'Missing' : 'Update available';
                    buttonText = 'Download';
                    actionHandler = () => downloadModel(model.name, select.value);
                } else if (activeVer && normalizeVer(activeVer) !== normalizeVer(select.value)) {
                    statusEl.textContent = `Installed (${formatVer(activeVer)})`;
                    buttonText = 'Set Active';
                    actionHandler = () => setActiveVersion(model.name, select.value);
                } else {
                    statusEl.textContent = 'Installed';
                    buttonText = '';
                }
            }

            if (latestVer && activeVer && normalizeVer(activeVer) !== normalizeVer(latestVer)) {
                statusEl.textContent += ` | Latest: ${formatVer(latestVer)}`;
            }

            if (buttonText) {
                const btn = document.createElement('button');
                btn.className = 'umi-mm-btn';
                btn.textContent = buttonText;
                if (actionHandler) btn.onclick = actionHandler;
                else btn.disabled = true;
                action.appendChild(btn);
            }

            row.appendChild(info);
            row.appendChild(select);
            row.appendChild(statusEl);
            row.appendChild(action);
            content.appendChild(row);
        });
    }

    async function setActiveVersion(modelName, version) {
        try {
            await fetch('/umiapp/models/set_active', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_name: modelName, version: version })
            });
            await loadModels();
        } catch (e) {
        }
    }

    async function downloadModel(modelName, version) {
        const repoId = getRepoId();
        try {
            await fetch('/umiapp/models/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_id: repoId, model_name: modelName, version: version })
            });
            await updateStatuses();
        } catch (e) {
        }
    }

    async function downloadAll() {
        const downloadAllBtn = document.getElementById('umi-mm-download-all');
        downloadAllBtn.disabled = true;
        downloadAllBtn.textContent = 'Downloading...';

        for (const model of models) {
            const targetVer = model.active_version || model.version;
            if (!modelHasVersion(model, targetVer)) {
                await downloadModel(model.name, targetVer);
                await new Promise(r => setTimeout(r, 1000));
            }
        }

        downloadAllBtn.textContent = 'Download All Missing/Updates';
        downloadAllBtn.disabled = false;
        await loadModels();
    }

    function showApiKeyDialog() {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.8); z-index: 10001; display:flex; align-items:center; justify-content:center;';

        const dialog = document.createElement('div');
        dialog.style.cssText = 'background:#2a2a2a; border:1px solid #555; border-radius:8px; padding:16px; width:360px; display:flex; flex-direction:column; gap:10px;';

        dialog.innerHTML = `
            <h3 style="margin:0; color:#fff; font-size:14px;">Civitai API Key</h3>
            <input type="password" id="umi-mm-api-key" placeholder="Paste API Key" style="background:#111; border:1px solid #444; color:#fff; padding:6px; border-radius:4px;" />
            <div style="display:flex; gap:8px; justify-content:flex-end;">
                <button id="umi-mm-api-cancel" class="umi-mm-btn">Cancel</button>
                <button id="umi-mm-api-save" class="umi-mm-btn-primary">Save</button>
            </div>
        `;

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        dialog.querySelector('#umi-mm-api-cancel').onclick = () => document.body.removeChild(overlay);
        dialog.querySelector('#umi-mm-api-save').onclick = async () => {
            const token = dialog.querySelector('#umi-mm-api-key').value.trim();
            if (!token) return;
            await fetch('/umiapp/models/save_token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });
            document.body.removeChild(overlay);
            await updateStatuses();
        };
    }

    window.umiModelManager = {
        show: showModelManager,
        hide: hideModelManager,
        refresh: loadModels,
        download: downloadModel,
        downloadAll
    };

    resetRepoId();

    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'm') {
            e.preventDefault();
            e.stopPropagation();
            showModelManager();
        }
    });

    console.log('[UmiAI] Model Manager loaded');
})();
