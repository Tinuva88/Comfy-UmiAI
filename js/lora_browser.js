import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

class LoraBrowserPanel {
    constructor() {
        this.element = null;
        this.loras = [];
        this.filtered = [];
        this.selected = null;
        this.searchTerm = "";
        this.selectedStrength = 1.0;
        this.currentPage = 0;
        this.pageSize = 30;
        this.sourceFilter = "all";
        this.tagsOnly = false;
        this.editDialog = null;
        this.hasLoaded = false;
    }

    async fetchLoras() {
        try {
            const response = await fetch("/umiapp/loras");
            const data = await response.json();
            this.loras = data.loras || [];
            return this.loras;
        } catch (error) {
            console.error("[Umi LoRA Browser] Failed to fetch LoRAs:", error);
            return [];
        }
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-lora-browser";
        panel.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            width: 100vw;
            height: 100vh;
            background: #0f1115;
            z-index: 10000;
            display: none;
            color: #d7dae0;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        `;

        panel.innerHTML = `
            <style>
                .umi-lb-root { display: flex; flex-direction: column; height: 100%; width: 100%; }
                .umi-lb-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid #20242c; background: linear-gradient(135deg, #1d2230 0%, #151a24 100%); flex-wrap: wrap; gap: 8px; }
                .umi-lb-title { font-size: 18px; font-weight: 600; color: #8fc6ff; }
                .umi-lb-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; row-gap: 6px; }
                .umi-lb-btn { background: #2a303b; color: #d7dae0; border: 1px solid #3b4250; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; }
                .umi-lb-btn:hover { border-color: #5b6b85; }
                .umi-lb-select { background: #1c212b; color: #d7dae0; border: 1px solid #3b4250; padding: 6px 8px; border-radius: 6px; font-size: 12px; }
                .umi-lb-body { display: grid; grid-template-columns: 260px minmax(0, 1fr) 360px; height: 100%; width: 100%; flex: 1; min-height: 0; }
                .umi-lb-sidebar { border-right: 1px solid #20242c; padding: 14px; overflow-y: auto; background: #12161f; min-width: 0; }
                .umi-lb-main { position: relative; overflow: hidden; display: flex; flex-direction: column; min-width: 0; flex: 1; }
                .umi-lb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 220px)); grid-auto-rows: max-content; align-content: start; align-items: start; justify-content: start; gap: 12px; padding: 14px; overflow-y: auto; height: 100%; min-height: 0; }
                .umi-lb-pagination { display: flex; justify-content: center; align-items: center; gap: 8px; padding: 10px; border-top: 1px solid #20242c; background: #10141d; }
                .umi-lb-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; background: #1c212b; border: 1px solid #2a303b; padding: 4px 8px; border-radius: 6px; }
                .umi-lb-details { border-left: 1px solid #20242c; padding: 14px; overflow-y: auto; background: #12161f; min-width: 0; }
                .umi-lb-section { margin-bottom: 16px; }
                .umi-lb-section-title { font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: #8b93a6; margin-bottom: 8px; }
                .umi-lb-input { width: 100%; padding: 6px 8px; background: #1c212b; border: 1px solid #313847; border-radius: 6px; color: #d7dae0; font-size: 12px; }
                .umi-lb-checkbox { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #c1c7d4; }
                .umi-lb-card { background: #1a1f2b; border: 1px solid #2a303b; border-radius: 8px; overflow: hidden; cursor: pointer; transition: transform 0.1s ease, border-color 0.1s ease; position: relative; display: flex; flex-direction: column; }
                .umi-lb-card:hover { border-color: #4c6b9a; transform: translateY(-2px); }
                .umi-lb-card.selected { border-color: #8fc6ff; box-shadow: 0 0 0 1px #8fc6ff inset; }
                .umi-lb-thumb { width: 100%; height: 140px; background: #0f1115; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; }
                .umi-lb-thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; display: block; z-index: 1; }
                .umi-lb-thumb-title { position: absolute; left: 0; right: 0; bottom: 0; padding: 6px 8px; font-size: 11px; color: #e3e7ef; background: linear-gradient(180deg, rgba(15, 17, 21, 0) 0%, rgba(15, 17, 21, 0.85) 60%, rgba(15, 17, 21, 0.95) 100%); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6); z-index: 2; pointer-events: none; }
                .umi-lb-card-meta { padding: 8px; background: #161b25; position: relative; z-index: 2; }
                .umi-lb-card-name { font-size: 11px; color: #c7cbd6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .umi-lb-card-sub { font-size: 10px; color: #7b8499; margin-top: 4px; }
                .umi-lb-badge { position: absolute; top: 6px; right: 6px; background: #2f7d4b; color: #fff; padding: 2px 6px; font-size: 9px; border-radius: 4px; z-index: 2; }
                .umi-lb-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
                .umi-lb-tag { background: #2a303b; color: #c1c7d4; font-size: 9px; padding: 2px 6px; border-radius: 4px; }
                .umi-lb-details-empty { color: #7b8499; text-align: center; padding: 20px; font-size: 12px; }
                .umi-lb-detail-image { width: 100%; border-radius: 6px; margin-bottom: 10px; }
                .umi-lb-detail-title { font-size: 14px; color: #8fc6ff; margin-bottom: 6px; }
                .umi-lb-detail-meta { font-size: 11px; color: #9aa3b2; margin-bottom: 10px; }
                .umi-lb-detail-section { margin-bottom: 12px; }
                .umi-lb-detail-label { font-size: 11px; color: #8b93a6; margin-bottom: 4px; }
                .umi-lb-detail-box { background: #1c212b; border: 1px solid #2a303b; border-radius: 6px; padding: 8px; font-size: 12px; color: #d7dae0; max-height: 160px; overflow-y: auto; white-space: pre-wrap; }
                .umi-lb-detail-actions { display: flex; gap: 8px; margin-top: 6px; flex-wrap: wrap; }
                .umi-lb-progress { margin-top: 8px; display: none; }
                .umi-lb-progress-bar { width: 0%; height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); transition: width 0.3s ease; }
            </style>
            <div class="umi-lb-root">
                <div class="umi-lb-header">
                    <div class="umi-lb-title">LoRA Browser</div>
                    <div class="umi-lb-actions">
                        <label class="umi-lb-checkbox">Strength</label>
                        <input type="range" class="umi-strength-slider" min="0" max="5" step="0.1" value="1.0" />
                        <span class="umi-strength-value" style="min-width:40px;color:#8fc6ff;">1.0</span>
                        <select class="umi-lb-select" data-role="page-size">
                            <option value="15">15</option>
                            <option value="30" selected>30</option>
                            <option value="60">60</option>
                        </select>
                        <button class="umi-lb-btn" data-action="fetch-all">Fetch CivitAI</button>
                        <button class="umi-lb-btn" data-action="close">Close</button>
                    </div>
                </div>
                <div class="umi-lb-body">
                    <aside class="umi-lb-sidebar">
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Search</div>
                            <input class="umi-lb-input" data-role="search" placeholder="Search LoRAs or tags" />
                        </div>
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Source</div>
                            <select class="umi-lb-select" data-role="source">
                                <option value="all">All</option>
                                <option value="override">Override</option>
                                <option value="civitai_info">CivitAI Info</option>
                                <option value="civitai">CivitAI</option>
                                <option value="safetensors">SafeTensors</option>
                                <option value="none">No Tags</option>
                            </select>
                        </div>
                        <div class="umi-lb-section">
                            <label class="umi-lb-checkbox">
                                <input type="checkbox" data-role="tags-only" /> Only with activation tags
                            </label>
                        </div>
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Actions</div>
                            <button class="umi-lb-btn" data-action="refresh">Refresh</button>
                            <button class="umi-lb-btn" data-action="fetch-all">Fetch CivitAI</button>
                        </div>
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Fetch status</div>
                            <div class="umi-lb-progress">
                                <div style="background:#333;border-radius:4px;overflow:hidden;height:8px;">
                                    <div class="umi-lb-progress-bar"></div>
                                </div>
                                <div class="umi-lb-progress-text" style="font-size:11px;color:#888;text-align:center;margin-top:4px;">0 / 0</div>
                            </div>
                            <div class="umi-lb-progress-status" style="font-size:11px;color:#888;text-align:center;margin-top:6px;"></div>
                        </div>
                    </aside>
                    <main class="umi-lb-main">
                        <div class="umi-lb-grid" data-role="grid"></div>
                        <div class="umi-lb-pagination" data-role="pagination"></div>
                    </main>
                    <aside class="umi-lb-details" data-role="details">
                        <div class="umi-lb-details-empty">Select a LoRA to view details.</div>
                    </aside>
                </div>
            </div>
        `;

        this.element = panel;
        document.body.appendChild(panel);
        this.bindEvents();
    }

    bindEvents() {
        const closeBtn = this.element.querySelector('[data-action="close"]');
        closeBtn.addEventListener('click', () => this.hide());

        const refreshBtn = this.element.querySelector('[data-action="refresh"]');
        refreshBtn.addEventListener('click', () => this.loadLoras());

        const searchInput = this.element.querySelector('[data-role="search"]');
        searchInput.addEventListener('input', (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.renderLoras();
        });

        const sourceSelect = this.element.querySelector('[data-role="source"]');
        sourceSelect.addEventListener('change', (e) => {
            this.sourceFilter = e.target.value;
            this.renderLoras();
        });

        const tagsOnly = this.element.querySelector('[data-role="tags-only"]');
        tagsOnly.addEventListener('change', (e) => {
            this.tagsOnly = e.target.checked;
            this.renderLoras();
        });

        const strengthSlider = this.element.querySelector('.umi-strength-slider');
        const strengthValue = this.element.querySelector('.umi-strength-value');
        strengthSlider.addEventListener('input', (e) => {
            this.selectedStrength = parseFloat(e.target.value);
            strengthValue.textContent = this.selectedStrength.toFixed(1);
        });

        const pageSizeSelect = this.element.querySelector('[data-role="page-size"]');
        pageSizeSelect.addEventListener('change', (e) => {
            this.pageSize = parseInt(e.target.value, 10);
            this.currentPage = 0;
            this.renderLoras();
        });

        this.element.querySelectorAll('[data-action="fetch-all"]').forEach((btn) => {
            btn.addEventListener('click', () => this.fetchAllCivitai());
        });
    }

    getActivationTags(lora) {
        const override = lora.override || {};
        const civitai = lora.civitai || {};
        const civitaiInfoTags = lora.civitai_info_tags || [];
        if (override.tags && override.tags.length > 0) {
            return { tags: override.tags, source: "override" };
        }
        if (civitaiInfoTags.length > 0) {
            return { tags: civitaiInfoTags, source: "civitai_info" };
        }
        if (civitai.trigger_words && civitai.trigger_words.length > 0) {
            return { tags: civitai.trigger_words, source: "civitai" };
        }
        if (lora.tags && lora.tags.length > 0) {
            return { tags: lora.tags, source: "safetensors" };
        }
        return { tags: [], source: "none" };
    }

    getPreviewUrl(lora) {
        const override = lora.override || {};
        const civitai = lora.civitai || {};
        if (override.preview_url) return override.preview_url;
        if (lora.local_preview) return `/umiapp/preview?path=${encodeURIComponent(lora.local_preview)}`;
        if (civitai.preview_url) return civitai.preview_url;
        return null;
    }

    applyFilters(list) {
        return list.filter(lora => {
            const name = lora.name.toLowerCase();
            const tags = (lora.tags || []).join(" ").toLowerCase();
            const activations = this.getActivationTags(lora);
            const activationText = activations.tags.join(" ").toLowerCase();
            const matchesSearch = !this.searchTerm || name.includes(this.searchTerm) || tags.includes(this.searchTerm) || activationText.includes(this.searchTerm);
            if (!matchesSearch) return false;
            if (this.sourceFilter !== "all" && activations.source !== this.sourceFilter) return false;
            if (this.tagsOnly && activations.tags.length === 0) return false;
            return true;
        });
    }

    async loadLoras(force = false) {
        const grid = this.element.querySelector('[data-role="grid"]');
        if (this.loras.length > 0 && this.hasLoaded && !force) {
            this.renderLoras();
            return;
        }
        grid.innerHTML = '<div class="umi-lb-details-empty">Loading LoRAs...</div>';
        await this.fetchLoras();
        this.hasLoaded = true;
        this.renderLoras();
    }

    renderLoras() {
        const grid = this.element.querySelector('[data-role="grid"]');
        this.filtered = this.applyFilters(this.loras);
        if (!this.filtered.length) {
            grid.innerHTML = '<div class="umi-lb-details-empty">No LoRAs found</div>';
            this.renderPagination();
            return;
        }

        const start = this.currentPage * this.pageSize;
        const end = start + this.pageSize;
        const pageItems = this.filtered.slice(start, end);
        grid.innerHTML = pageItems.map(lora => this.createCardHTML(lora)).join('');
        grid.querySelectorAll('.umi-lb-card').forEach((card, idx) => {
            card.addEventListener('click', () => {
                this.selected = pageItems[idx];
                this.renderDetails();
                this.renderLoras();
            });
        });
        this.renderPagination();
    }

    renderPagination() {
        const pagination = this.element.querySelector('[data-role="pagination"]');
        if (!pagination) return;
        const totalPages = Math.ceil(this.filtered.length / this.pageSize);
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }
        pagination.innerHTML = `
            <button class="umi-lb-btn" data-page="${this.currentPage - 1}" ${this.currentPage === 0 ? 'disabled' : ''}>Prev</button>
            <span class="umi-lb-chip">Page ${this.currentPage + 1} of ${totalPages} (${this.filtered.length})</span>
            <button class="umi-lb-btn" data-page="${this.currentPage + 1}" ${this.currentPage >= totalPages - 1 ? 'disabled' : ''}>Next</button>
        `;
        pagination.querySelectorAll('button[data-page]:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
                this.currentPage = parseInt(btn.dataset.page, 10);
                this.renderLoras();
            });
        });
    }

    createCardHTML(lora) {
        const activation = this.getActivationTags(lora);
        const previewUrl = this.getPreviewUrl(lora);
        const tags = activation.tags.slice(0, 3);
        const extra = activation.tags.length - tags.length;
        const tagHtml = tags.map(tag => `<span class="umi-lb-tag">#${this.escapeHtml(tag)}</span>`).join('') + (extra > 0 ? `<span class="umi-lb-tag">+${extra}</span>` : '');
        const badge = activation.source !== "none" ? `<div class="umi-lb-badge">${activation.source}</div>` : '';
        const selectedClass = this.selected && this.selected.name === lora.name ? "selected" : "";

        return `
            <div class="umi-lb-card ${selectedClass}">
                <div class="umi-lb-thumb">
                    ${previewUrl ? `<img src="${previewUrl}" alt="${this.escapeHtmlAttr(lora.name)}" loading="lazy" />` : ''}
                    ${badge}
                    <div class="umi-lb-thumb-title" title="${this.escapeHtml(lora.name)}">${this.escapeHtml(lora.name)}</div>
                </div>
                <div class="umi-lb-card-meta">
                    <div class="umi-lb-card-name" title="${this.escapeHtml(lora.name)}">${this.escapeHtml(lora.name)}</div>
                    <div class="umi-lb-card-sub">${this.escapeHtml(lora.filename || "")}</div>
                    <div class="umi-lb-tags">${tagHtml}</div>
                </div>
            </div>
        `;
    }

    renderDetails() {
        const details = this.element.querySelector('[data-role="details"]');
        if (!this.selected) {
            details.innerHTML = '<div class="umi-lb-details-empty">Select a LoRA to view details.</div>';
            return;
        }

        const lora = this.selected;
        const activation = this.getActivationTags(lora);
        const civitai = lora.civitai || {};
        const override = lora.override || {};
        const previewUrl = this.getPreviewUrl(lora);
        const tagList = activation.tags.length ? activation.tags.join(", ") : "None";
        const baseModel = civitai.base_model || "Unknown";
        const sourceLabel = activation.source;
        const rawDescription = civitai.description || override.description || lora.local?.description || "";
        const description = this.stripHtml(rawDescription);

        details.innerHTML = `
            <div class="umi-lb-detail-section">
                ${previewUrl ? `<img class="umi-lb-detail-image" src="${previewUrl}" />` : ""}
                <div class="umi-lb-detail-title">${this.escapeHtml(lora.name)}</div>
                <div class="umi-lb-detail-meta">${this.escapeHtml(lora.filename || "")}<br />Source: ${this.escapeHtml(sourceLabel)} | Base: ${this.escapeHtml(baseModel)}</div>
                <div class="umi-lb-detail-actions">
                    <button class="umi-lb-btn" data-action="insert">Insert</button>
                    <button class="umi-lb-btn" data-action="copy">Copy Tag</button>
                    <button class="umi-lb-btn" data-action="edit">Edit Override</button>
                    ${civitai.url ? `<button class="umi-lb-btn" data-action="open">Open CivitAI</button>` : `<button class="umi-lb-btn" data-action="fetch">Fetch CivitAI</button>`}
                </div>
            </div>
            <div class="umi-lb-detail-section">
                <div class="umi-lb-detail-label">Activation Tags</div>
                <div class="umi-lb-detail-box">${this.escapeHtml(tagList)}</div>
            </div>
            <div class="umi-lb-detail-section">
                <div class="umi-lb-detail-label">Description</div>
                <div class="umi-lb-detail-box">${this.escapeHtml(description || "No description")}</div>
            </div>
        `;

        details.querySelector('[data-action="insert"]').addEventListener('click', () => this.insertLora(lora));
        details.querySelector('[data-action="copy"]').addEventListener('click', () => {
            const text = `<lora:${lora.filename || lora.name}:${this.selectedStrength.toFixed(1)}>`;
            navigator.clipboard.writeText(text);
            this.showNotification("LoRA tag copied");
        });
        details.querySelector('[data-action="edit"]').addEventListener('click', () => this.showEditDialog(lora));
        const openBtn = details.querySelector('[data-action="open"]');
        if (openBtn) {
            openBtn.addEventListener('click', () => window.open(civitai.url, "_blank"));
        }
        const fetchBtn = details.querySelector('[data-action="fetch"]');
        if (fetchBtn) {
            fetchBtn.addEventListener('click', () => this.fetchSingleCivitai(lora));
        }
    }

    insertLora(lora) {
        const loraName = lora.filename || lora.name;
        const loraText = `<lora:${loraName}:${this.selectedStrength.toFixed(1)}>`;
        const activation = this.getActivationTags(lora);
        const activationTags = activation.tags.slice(0, 3);

        const activeNode = this.findActiveUmiNode();
        if (activeNode) {
            const promptWidget = activeNode.widgets.find(w => w.name === "text");
            if (promptWidget) {
                const currentValue = promptWidget.value || "";
                let newValue = currentValue ? `${currentValue}, ${loraText}` : loraText;
                if (activationTags.length > 0) {
                    newValue = `${newValue}, ${activationTags.join(", ")}`;
                }
                promptWidget.value = newValue;
                if (promptWidget.callback) {
                    promptWidget.callback(newValue);
                }
                if (promptWidget.inputEl) {
                    promptWidget.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
                app.graph.setDirtyCanvas(true, true);
                this.showNotification(`Inserted ${lora.name}`);
            }
        } else {
            navigator.clipboard.writeText(loraText);
            this.showNotification("Copied to clipboard");
        }
    }

    findActiveUmiNode() {
        const canvas = app.canvas;
        if (!canvas) return null;
        const selectedNodes = canvas.selected_nodes;
        if (selectedNodes) {
            for (const nodeId in selectedNodes) {
                const node = app.graph.getNodeById(parseInt(nodeId, 10));
                if (node && (node.type === "UmiAIWildcardNode" || node.type === "UmiAIWildcardNodeLite")) {
                    return node;
                }
            }
        }
        for (const node of app.graph._nodes) {
            if (node.type === "UmiAIWildcardNode" || node.type === "UmiAIWildcardNodeLite") {
                return node;
            }
        }
        return null;
    }

    async fetchSingleCivitai(lora) {
        try {
            const response = await fetch("/umiapp/loras/civitai/single", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lora_name: lora.name })
            });
            const data = await response.json();
            if (data.success) {
                this.showNotification(`Fetched CivitAI data for ${lora.name}`);
                await this.loadLoras();
                this.selected = this.loras.find(item => item.name === lora.name) || null;
                this.renderDetails();
            } else {
                this.showNotification(`Not found: ${lora.name}`, true);
            }
        } catch (error) {
            this.showNotification(`Error: ${error.message}`, true);
        }
    }

    async fetchAllCivitai() {
        const progress = this.element.querySelector('.umi-lb-progress');
        const bar = this.element.querySelector('.umi-lb-progress-bar');
        const text = this.element.querySelector('.umi-lb-progress-text');
        const status = this.element.querySelector('.umi-lb-progress-status');
        progress.style.display = "block";
        bar.style.width = "0%";
        status.textContent = "";

        let processed = 0;
        const total = this.loras.length;
        for (const lora of this.loras) {
            if (lora.civitai?.id) {
                processed += 1;
            } else {
                await this.fetchSingleCivitai(lora);
                processed += 1;
            }
            const pct = total ? Math.round((processed / total) * 100) : 0;
            bar.style.width = `${pct}%`;
            text.textContent = `${processed} / ${total}`;
        }
        status.textContent = "Fetch complete";
        setTimeout(() => { progress.style.display = "none"; }, 2000);
    }

    showEditDialog(lora) {
        if (this.editDialog) {
            this.editDialog.remove();
        }

        const dialog = document.createElement("div");
        dialog.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #1c212b;
            border: 1px solid #3b4250;
            border-radius: 8px;
            padding: 16px;
            z-index: 10001;
            width: 420px;
        `;

        const override = lora.override || {};
        const tags = (override.tags || []).join(", ");
        const preview = override.preview_url || "";
        const nickname = override.nickname || "";

        dialog.innerHTML = `
            <div style="font-size:14px;color:#8fc6ff;margin-bottom:10px;">Edit LoRA Override</div>
            <div style="margin-bottom:8px;">
                <input class="umi-lb-input" data-role="nickname" placeholder="Nickname" value="${this.escapeHtmlAttr(nickname)}" />
            </div>
            <div style="margin-bottom:8px;">
                <input class="umi-lb-input" data-role="tags" placeholder="Tags (comma separated)" value="${this.escapeHtmlAttr(tags)}" />
            </div>
            <div style="margin-bottom:12px;">
                <input class="umi-lb-input" data-role="preview" placeholder="Preview URL" value="${this.escapeHtmlAttr(preview)}" />
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;">
                <button class="umi-lb-btn" data-action="cancel">Cancel</button>
                <button class="umi-lb-btn" data-action="save">Save</button>
            </div>
        `;

        document.body.appendChild(dialog);
        this.editDialog = dialog;

        dialog.querySelector('[data-action="cancel"]').addEventListener('click', () => dialog.remove());
        dialog.querySelector('[data-action="save"]').addEventListener('click', async () => {
            const nicknameVal = dialog.querySelector('[data-role="nickname"]').value.trim();
            const tagsVal = dialog.querySelector('[data-role="tags"]').value.split(",").map(t => t.trim()).filter(Boolean);
            const previewVal = dialog.querySelector('[data-role="preview"]').value.trim();
            await this.saveLoraOverride(lora.name, { nickname: nicknameVal, tags: tagsVal, preview_url: previewVal });
            dialog.remove();
        });
    }

    async saveLoraOverride(loraName, override) {
        try {
            const response = await fetch("/umiapp/loras/overrides/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lora_name: loraName, override })
            });
            const data = await response.json();
            if (data.success) {
                this.showNotification("Override saved");
                await this.loadLoras();
                this.selected = this.loras.find(item => item.name === loraName) || null;
                this.renderDetails();
            } else {
                this.showNotification("Save failed", true);
            }
        } catch (error) {
            this.showNotification(`Error: ${error.message}`, true);
        }
    }

    showNotification(message, isError = false) {
        const notification = document.createElement("div");
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${isError ? "#be5046" : "#2f7d4b"};
            color: white;
            padding: 10px 16px;
            border-radius: 6px;
            z-index: 10002;
            font-size: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 2000);
    }

    escapeHtml(text) {
        if (!text) return "";
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    escapeHtmlAttr(text) {
        if (!text) return "";
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;")
            .replace(/\n/g, " ");
    }

    stripHtml(value) {
        if (!value) return "";
        const parser = new DOMParser();
        const doc = parser.parseFromString(String(value), "text/html");
        return (doc.body && doc.body.textContent) ? doc.body.textContent.trim() : "";
    }

    async show() {
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = "block";
        await this.loadLoras(false);
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

const loraBrowser = new LoraBrowserPanel();

app.registerExtension({
    name: "Umi.LoraBrowser",

    async setup() {
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "LoRA Browser";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => loraBrowser.show();
            menu.appendChild(button);
        }

        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "l") {
                e.preventDefault();
                loraBrowser.show();
            }
        });
    }
});
