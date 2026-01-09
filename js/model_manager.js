/**
 * UmiAI Model Manager
 * Dedicated panel for downloading recommended models for character consistency workflows.
 */

(function () {
    'use strict';

    // Panel state
    let modelManagerPanel = null;
    let isLoading = false;

    // Create and show the Model Manager panel
    function showModelManager() {
        if (modelManagerPanel) {
            modelManagerPanel.style.display = 'flex';
            loadModelStatus();
            return;
        }

        // Create panel
        modelManagerPanel = document.createElement('div');
        modelManagerPanel.id = 'umi-model-manager';
        modelManagerPanel.innerHTML = `
            <div class="umi-mm-overlay" onclick="window.umiModelManager.hide()"></div>
            <div class="umi-mm-container">
                <div class="umi-mm-header">
                    <h2>📦 UmiAI Model Manager</h2>
                    <button class="umi-mm-close" onclick="window.umiModelManager.hide()">×</button>
                </div>
                <div class="umi-mm-status-bar">
                    <span id="umi-mm-status-text">Loading...</span>
                    <button id="umi-mm-download-all" class="umi-mm-btn-primary" onclick="window.umiModelManager.downloadAllRequired()">
                        ⬇️ Download All Required
                    </button>
                </div>
                <div class="umi-mm-content" id="umi-mm-content">
                    <div class="umi-mm-loading">Loading model status...</div>
                </div>
                <div class="umi-mm-footer">
                    <p>Models hosted at <a href="https://huggingface.co/Tinuva/Comfy-Umi" target="_blank">Tinuva/Comfy-Umi</a></p>
                </div>
            </div>
        `;

        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            #umi-model-manager {
                display: flex;
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                z-index: 10000;
                align-items: center;
                justify-content: center;
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
                width: 800px;
                max-width: 90vw;
                max-height: 80vh;
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
                font-size: 24px;
                cursor: pointer;
            }
            .umi-mm-close:hover { color: #fff; }
            .umi-mm-status-bar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 20px;
                background: #252525;
                border-bottom: 1px solid #333;
            }
            #umi-mm-status-text {
                color: #aaa;
                font-size: 14px;
            }
            .umi-mm-btn-primary {
                background: linear-gradient(135deg, #4a9eff 0%, #3b7ed0 100%);
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 500;
            }
            .umi-mm-btn-primary:hover { opacity: 0.9; }
            .umi-mm-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
            .umi-mm-content {
                flex: 1;
                overflow-y: auto;
                padding: 16px 20px;
            }
            .umi-mm-loading {
                text-align: center;
                color: #888;
                padding: 40px;
            }
            .umi-mm-category {
                margin-bottom: 20px;
            }
            .umi-mm-cat-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 10px;
            }
            .umi-mm-cat-header h3 {
                margin: 0;
                font-size: 15px;
                color: #ddd;
            }
            .umi-mm-model {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 10px 12px;
                background: #2a2a2a;
                border-radius: 6px;
                margin-bottom: 6px;
            }
            .umi-mm-model-info {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .umi-mm-model-name {
                color: #fff;
                font-size: 14px;
            }
            .umi-mm-model-size {
                color: #666;
                font-size: 12px;
            }
            .umi-mm-model-required {
                background: #4a9eff33;
                color: #4a9eff;
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 4px;
            }
            .umi-mm-status-icon {
                font-size: 16px;
            }
            .umi-mm-btn-download {
                background: #333;
                color: #4a9eff;
                border: 1px solid #4a9eff;
                padding: 4px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            }
            .umi-mm-btn-download:hover { background: #4a9eff22; }
            .umi-mm-progress {
                width: 100px;
                height: 6px;
                background: #333;
                border-radius: 3px;
                overflow: hidden;
            }
            .umi-mm-progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #4a9eff, #7c3aed);
                transition: width 0.3s;
            }
            .umi-mm-footer {
                padding: 12px 20px;
                border-top: 1px solid #333;
                text-align: center;
            }
            .umi-mm-footer p { margin: 0; font-size: 12px; color: #666; }
            .umi-mm-footer a { color: #4a9eff; }
        `;
        document.head.appendChild(style);
        document.body.appendChild(modelManagerPanel);

        loadModelStatus();
    }

    // Load and display model status
    async function loadModelStatus() {
        const content = document.getElementById('umi-mm-content');
        const statusText = document.getElementById('umi-mm-status-text');

        if (isLoading) return;
        isLoading = true;

        try {
            const response = await fetch('/umiapp/models/status');
            const data = await response.json();

            if (data.error) {
                content.innerHTML = `<div class="umi-mm-loading">Error: ${data.error}</div>`;
                return;
            }

            // Update status bar
            const summary = data.summary || {};
            const ready = summary.ready;
            statusText.innerHTML = ready
                ? `✅ Ready! ${summary.installed_required}/${summary.total_required} required models installed`
                : `⚠️ ${summary.installed_required}/${summary.total_required} required models installed`;

            // Render categories
            let html = '';
            for (const [catId, category] of Object.entries(data.status || {})) {
                const installedCount = category.models.filter(m => m.installed).length;
                const totalCount = category.models.length;

                html += `
                    <div class="umi-mm-category" data-category="${catId}">
                        <div class="umi-mm-cat-header">
                            <h3>${category.name}</h3>
                            <span class="umi-mm-model-size">(${installedCount}/${totalCount} installed)</span>
                        </div>
                `;

                for (const model of category.models) {
                    const icon = model.installed ? '✅' : '⬇️';
                    const action = model.installed
                        ? `<span class="umi-mm-status-icon">✅</span>`
                        : `<button class="umi-mm-btn-download" onclick="window.umiModelManager.download('${catId}', '${model.name}')">Download</button>`;

                    html += `
                        <div class="umi-mm-model" data-model="${model.name}">
                            <div class="umi-mm-model-info">
                                <span class="umi-mm-model-name">${model.name}</span>
                                <span class="umi-mm-model-size">${model.size_mb} MB</span>
                                ${model.required ? '<span class="umi-mm-model-required">Required</span>' : ''}
                            </div>
                            <div class="umi-mm-model-action">${action}</div>
                        </div>
                    `;
                }

                html += '</div>';
            }

            content.innerHTML = html;

        } catch (err) {
            content.innerHTML = `<div class="umi-mm-loading">Error loading status: ${err.message}</div>`;
        } finally {
            isLoading = false;
        }
    }

    // Download a single model
    async function downloadModel(category, modelName) {
        const modelEl = document.querySelector(`[data-model="${modelName}"]`);
        if (modelEl) {
            const actionEl = modelEl.querySelector('.umi-mm-model-action');
            actionEl.innerHTML = `
                <div class="umi-mm-progress">
                    <div class="umi-mm-progress-bar" style="width: 0%"></div>
                </div>
            `;
        }

        try {
            const response = await fetch('/umiapp/models/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category, model: modelName })
            });

            const data = await response.json();
            if (data.error) {
                console.error('Download error:', data.error);
                return;
            }

            // Poll for progress
            const downloadId = data.download_id;
            pollProgress(downloadId, modelEl);

        } catch (err) {
            console.error('Download failed:', err);
        }
    }

    // Poll download progress
    async function pollProgress(downloadId, modelEl) {
        const progressBar = modelEl?.querySelector('.umi-mm-progress-bar');

        const poll = async () => {
            try {
                const response = await fetch(`/umiapp/models/progress?id=${downloadId}`);
                const data = await response.json();

                if (progressBar) {
                    progressBar.style.width = `${data.progress || 0}%`;
                }

                if (data.status === 'complete') {
                    if (modelEl) {
                        const actionEl = modelEl.querySelector('.umi-mm-model-action');
                        actionEl.innerHTML = '<span class="umi-mm-status-icon">✅</span>';
                    }
                    loadModelStatus(); // Refresh
                    return;
                }

                if (data.status === 'error') {
                    if (modelEl) {
                        const actionEl = modelEl.querySelector('.umi-mm-model-action');
                        actionEl.innerHTML = `<span style="color:#f66">Error</span>`;
                    }
                    return;
                }

                // Continue polling
                setTimeout(poll, 500);

            } catch (err) {
                console.error('Poll error:', err);
            }
        };

        poll();
    }

    // Download all required models
    async function downloadAllRequired() {
        const btn = document.getElementById('umi-mm-download-all');
        btn.disabled = true;
        btn.textContent = 'Checking...';

        try {
            const response = await fetch('/umiapp/models/download-all', { method: 'POST' });
            const data = await response.json();

            if (data.queued && data.queued.length > 0) {
                btn.textContent = `Downloading ${data.queued.length} models...`;

                // Download sequentially
                for (const item of data.queued) {
                    await downloadModel(item.category, item.model);
                    // Wait a bit between downloads
                    await new Promise(r => setTimeout(r, 1000));
                }
            }

            btn.textContent = '⬇️ Download All Required';
            btn.disabled = false;
            loadModelStatus();

        } catch (err) {
            console.error('Download all failed:', err);
            btn.textContent = 'Error - Try Again';
            btn.disabled = false;
        }
    }

    // Hide the panel
    function hideModelManager() {
        if (modelManagerPanel) {
            modelManagerPanel.style.display = 'none';
        }
    }

    // Expose API
    window.umiModelManager = {
        show: showModelManager,
        hide: hideModelManager,
        download: downloadModel,
        downloadAllRequired: downloadAllRequired,
        refresh: loadModelStatus
    };

    // Register keyboard shortcut (Ctrl+Shift+M to avoid conflicts)
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'm') {
            e.preventDefault();
            e.stopPropagation();
            showModelManager();
        }
    });

    console.log('[UmiAI] Model Manager loaded');
    console.log('[UmiAI] Open with: Ctrl+Shift+M or run: window.umiModelManager.show()');
})();

