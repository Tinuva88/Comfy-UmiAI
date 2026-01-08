import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Phase 6: LoRA Browser Panel - Browse and insert LoRAs into Umi nodes

class LoraBrowserPanel {
    constructor() {
        this.element = null;
        this.loras = [];
        this.searchTerm = "";
        this.selectedStrength = 1.0;
        this.editDialog = null;
    }

    async fetchLoras() {
        try {
            const response = await fetch("/umiapp/loras");
            const data = await response.json();
            console.log("[Umi LoRA Browser] Raw response data:", data);
            console.log("[Umi LoRA Browser] Number of LoRAs:", data.loras ? data.loras.length : 0);
            if (data.loras && data.loras.length > 0) {
                console.log("[Umi LoRA Browser] First LoRA sample:", data.loras[0]);
            }
            this.loras = data.loras || [];
            console.log("[Umi LoRA Browser] this.loras length:", this.loras.length);
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
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 850px;
            max-width: 92vw;
            max-height: 85vh;
            background: rgba(30, 30, 30, 0.95);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(97, 175, 239, 0.4);
            border-radius: 12px;
            box-shadow: 0 12px 48px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.05) inset;
            z-index: 10000;
            display: none;
            flex-direction: column;
            overflow: hidden;
        `;

        panel.innerHTML = `
            <div style="
                padding: 18px 20px;
                background: linear-gradient(135deg, rgba(97, 175, 239, 0.15) 0%, rgba(198, 120, 221, 0.1) 100%);
                border-bottom: 1px solid rgba(97, 175, 239, 0.3);
                display: flex;
                justify-content: space-between;
                align-items: center;
            ">
                <h2 style="margin: 0; color: #61afef; font-size: 20px; font-weight: 600; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">📦 LoRA Browser</h2>
                <button class="umi-close-btn" style="
                    background: linear-gradient(135deg, #e06c75 0%, #be5046 100%);
                    color: white;
                    border: none;
                    padding: 6px 14px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 600;
                    transition: all 0.2s ease;
                    box-shadow: 0 2px 8px rgba(224, 108, 117, 0.3);
                " onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(224, 108, 117, 0.4)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 8px rgba(224, 108, 117, 0.3)'">✕ Close</button>
            </div>

            <div style="padding: 15px; border-bottom: 1px solid #444;">
                <input
                    type="text"
                    class="umi-lora-search"
                    placeholder="🔍 Search LoRAs..."
                    style="width: 100%; padding: 8px; background: #2c2c2c; border: 1px solid #555; border-radius: 4px; color: #abb2bf; font-size: 14px;"
                />
                <div style="margin-top: 10px; display: flex; align-items: center; gap: 10px;">
                    <label style="color: #abb2bf; font-size: 13px;">Default Strength:</label>
                    <input
                        type="range"
                        class="umi-strength-slider"
                        min="0"
                        max="5"
                        step="0.1"
                        value="1.0"
                        style="flex: 1;"
                    />
                    <span class="umi-strength-value" style="color: #61afef; font-weight: bold; min-width: 40px;">1.0</span>
                </div>
                <div style="margin-top: 10px;">
                    <button class="umi-civitai-crawl" style="
                        width: 100%;
                        padding: 8px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-weight: 600;
                        font-size: 13px;
                    ">🌐 Fetch All from CivitAI</button>
                    <div class="umi-civitai-progress" style="
                        margin-top: 8px;
                        display: none;
                    ">
                        <div style="background: #333; border-radius: 4px; overflow: hidden; height: 8px;">
                            <div class="umi-civitai-progress-bar" style="
                                width: 0%;
                                height: 100%;
                                background: linear-gradient(90deg, #667eea, #764ba2);
                                transition: width 0.3s ease;
                            "></div>
                        </div>
                        <div class="umi-civitai-progress-text" style="font-size: 11px; color: #888; text-align: center; margin-top: 4px;">0 / 0</div>
                    </div>
                    <div class="umi-civitai-status" style="margin-top: 5px; font-size: 11px; color: #888; text-align: center;"></div>
                </div>
            </div>

            <div class="umi-lora-grid" style="
                padding: 15px;
                overflow-y: auto;
                flex: 1;
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
                align-content: start;
            "></div>

            <div style="padding: 10px; border-top: 1px solid #444; background: #252525; color: #888; font-size: 11px; text-align: center;">
                Click a LoRA to insert into your Umi node prompt
            </div>
        `;

        // Event listeners
        const closeBtn = panel.querySelector(".umi-close-btn");
        closeBtn.addEventListener("click", () => this.hide());

        const searchInput = panel.querySelector(".umi-lora-search");
        searchInput.addEventListener("input", (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.renderLoras();
        });

        const strengthSlider = panel.querySelector(".umi-strength-slider");
        const strengthValue = panel.querySelector(".umi-strength-value");
        strengthSlider.addEventListener("input", (e) => {
            this.selectedStrength = parseFloat(e.target.value);
            strengthValue.textContent = this.selectedStrength.toFixed(1);
        });

        const civitaiBtn = panel.querySelector(".umi-civitai-crawl");
        const civitaiStatus = panel.querySelector(".umi-civitai-status");
        const progressContainer = panel.querySelector(".umi-civitai-progress");
        const progressBar = panel.querySelector(".umi-civitai-progress-bar");
        const progressText = panel.querySelector(".umi-civitai-progress-text");

        civitaiBtn.addEventListener("click", async () => {
            civitaiBtn.disabled = true;
            civitaiBtn.textContent = "🔄 Fetching...";
            civitaiStatus.textContent = "";
            progressContainer.style.display = "block";
            progressBar.style.width = "0%";

            const totalLoras = this.loras.length;
            let processed = 0;
            let fetched = 0;
            let cached = 0;
            let failed = 0;

            try {
                // Fetch individually for progress tracking
                for (const lora of this.loras) {
                    if (lora.civitai?.id) {
                        cached++;
                    } else {
                        try {
                            const response = await fetch("/umiapp/loras/civitai/single", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ lora_name: lora.name })
                            });
                            const data = await response.json();
                            if (data.success) {
                                fetched++;
                            } else {
                                failed++;
                            }
                        } catch (e) {
                            failed++;
                        }
                    }
                    processed++;
                    const pct = Math.round((processed / totalLoras) * 100);
                    progressBar.style.width = `${pct}%`;
                    progressText.textContent = `${processed} / ${totalLoras}`;
                }

                civitaiStatus.textContent = `✓ Done! Fetched: ${fetched}, Cached: ${cached}, Failed: ${failed}`;
                civitaiStatus.style.color = "#98c379";

                // Reload LoRAs to show new data
                await this.fetchLoras();
                this.renderLoras();
            } catch (error) {
                civitaiStatus.textContent = `✗ Failed: ${error.message}`;
                civitaiStatus.style.color = "#e06c75";
            }

            civitaiBtn.disabled = false;
            civitaiBtn.textContent = "🌐 Fetch All from CivitAI";
            setTimeout(() => { progressContainer.style.display = "none"; }, 3000);
        });

        // Close on background click
        panel.addEventListener("click", (e) => {
            if (e.target === panel) {
                this.hide();
            }
        });

        this.element = panel;
        document.body.appendChild(panel);
    }

    renderLoras() {
        const grid = this.element.querySelector(".umi-lora-grid");
        if (!grid) {
            console.log("[Umi LoRA Browser] renderLoras: Grid element not found!");
            return;
        }

        console.log("[Umi LoRA Browser] renderLoras: this.loras.length =", this.loras.length);
        console.log("[Umi LoRA Browser] renderLoras: searchTerm =", this.searchTerm);

        const filtered = this.loras.filter(lora => {
            if (!this.searchTerm) return true;
            return lora.name.toLowerCase().includes(this.searchTerm) ||
                (lora.tags && lora.tags.some(tag => tag.toLowerCase().includes(this.searchTerm)));
        });

        console.log("[Umi LoRA Browser] renderLoras: filtered.length =", filtered.length);

        if (filtered.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">No LoRAs found</div>';
            return;
        }

        grid.innerHTML = filtered.map(lora => this.createLoraCard(lora)).join("");

        // Add click handlers
        grid.querySelectorAll(".umi-lora-card").forEach((card, index) => {
            card.addEventListener("click", (e) => {
                // Don't insert if clicking edit button or fetch button
                if (!e.target.closest(".umi-edit-lora-btn") && !e.target.closest(".umi-fetch-civitai-btn")) {
                    this.insertLora(filtered[index]);
                }
            });

            // Right-click to edit
            card.addEventListener("contextmenu", (e) => {
                e.preventDefault();
                this.showEditDialog(filtered[index]);
            });

            // Edit button click
            const editBtn = card.querySelector(".umi-edit-lora-btn");
            if (editBtn) {
                editBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.showEditDialog(filtered[index]);
                });
            }

            // Per-card CivitAI fetch button
            const fetchBtn = card.querySelector(".umi-fetch-civitai-btn");
            if (fetchBtn) {
                fetchBtn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    const loraName = fetchBtn.dataset.lora;

                    fetchBtn.textContent = "⏳...";
                    fetchBtn.disabled = true;

                    try {
                        const response = await fetch("/umiapp/loras/civitai/single", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ lora_name: loraName })
                        });
                        const data = await response.json();

                        if (data.success) {
                            this.showNotification(`✓ Fetched CivitAI data for ${loraName}`);
                            // Reload to show updated data
                            await this.fetchLoras();
                            this.renderLoras();
                        } else {
                            fetchBtn.textContent = "❌";
                            this.showNotification(`✗ Not found: ${loraName}`, true);
                            setTimeout(() => { fetchBtn.textContent = "🌐 Fetch"; fetchBtn.disabled = false; }, 2000);
                        }
                    } catch (error) {
                        fetchBtn.textContent = "❌";
                        this.showNotification(`✗ Error: ${error.message}`, true);
                        setTimeout(() => { fetchBtn.textContent = "🌐 Fetch"; fetchBtn.disabled = false; }, 2000);
                    }
                });
            }
        });
    }

    createLoraCard(lora) {
        const civitai = lora.civitai || {};
        const override = lora.override || {};
        const hasCivitai = civitai.id !== undefined;
        const hasOverride = Object.keys(override).length > 0;

        // Priority: override > civitai > safetensors tags
        const displayName = override.nickname || lora.name;

        let displayTags = [];
        if (override.tags && override.tags.length > 0) {
            displayTags = override.tags.slice(0, 5);
        } else if (hasCivitai && civitai.trigger_words && civitai.trigger_words.length > 0) {
            displayTags = civitai.trigger_words.slice(0, 5);
        } else if (lora.tags && lora.tags.length > 0) {
            displayTags = lora.tags.slice(0, 5);
        }

        const tagsHtml = displayTags.length > 0
            ? displayTags.map(tag => `<span style="background: #3e4451; padding: 2px 6px; border-radius: 3px; font-size: 10px;">${tag}</span>`).join(" ")
            : '<span style="color: #666; font-size: 11px;">No tags</span>';

        const previewUrl = override.preview_url || (hasCivitai && civitai.preview_url) || null;
        const previewHtml = previewUrl
            ? `<div style="width: 100%; height: 120px; background: url('${previewUrl}') center/cover; border-radius: 4px; margin-bottom: 8px;"></div>`
            : '';

        const civitaiBadge = hasCivitai
            ? `<a href="${civitai.url}" target="_blank" onclick="event.stopPropagation()" style="font-size: 10px; color: #667eea; text-decoration: none;">🌐 CivitAI</a>`
            : `<button class="umi-fetch-civitai-btn" data-lora="${lora.name}" onclick="event.stopPropagation()" style="
                font-size: 10px; 
                color: white; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border: none;
                border-radius: 3px;
                padding: 3px 6px;
                cursor: pointer;
            ">🌐 Fetch</button>`;

        const baseModel = hasCivitai && civitai.base_model
            ? `<div style="font-size: 10px; color: #e5c07b; margin-top: 4px;">${civitai.base_model}</div>`
            : '';

        const overrideBadge = hasOverride
            ? `<span style="font-size: 9px; background: #e5c07b; color: #1e1e1e; padding: 2px 5px; border-radius: 3px; font-weight: 600;">✏️ CUSTOM</span>`
            : '';

        return `
            <div class="umi-lora-card" data-lora-name="${lora.name}" style="
                background: #2c2c2c;
                border: 1px solid ${hasOverride ? '#e5c07b' : hasCivitai ? '#667eea' : '#444'};
                border-radius: 6px;
                padding: 12px;
                cursor: pointer;
                transition: all 0.2s;
                position: relative;
            " onmouseover="this.style.borderColor='#61afef'; this.style.transform='translateY(-2px)'" onmouseout="this.style.borderColor='${hasOverride ? '#e5c07b' : hasCivitai ? '#667eea' : '#444'}'; this.style.transform='translateY(0)'">
                <button class="umi-edit-lora-btn" onclick="event.stopPropagation()" style="
                    position: absolute;
                    top: 8px;
                    right: 8px;
                    background: rgba(97, 175, 239, 0.9);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    cursor: pointer;
                    font-size: 11px;
                    font-weight: 600;
                    z-index: 10;
                " onmouseover="this.style.background='#61afef'" onmouseout="this.style.background='rgba(97, 175, 239, 0.9)'">✏️ Edit</button>
                ${previewHtml}
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                    <div style="font-weight: 600; color: #61afef; font-size: 13px; word-break: break-word; padding-right: 50px;">
                        ${displayName}
                    </div>
                </div>
                ${overrideBadge}
                <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; margin-top: ${hasOverride ? '6px' : '0'};">
                    ${tagsHtml}
                </div>
                ${baseModel}
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">
                    <div style="font-size: 11px; color: #98c379;">
                        @ ${this.selectedStrength.toFixed(1)}
                    </div>
                    ${civitaiBadge}
                </div>
            </div>
        `;
    }

    insertLora(lora) {
        // Use filename (with .safetensors) instead of name
        const loraName = lora.filename || lora.name;
        const loraText = `<lora:${loraName}:${this.selectedStrength.toFixed(1)}>`;

        // Determine which tags to use (priority: override > CivitAI > SafeTensors)
        let activationTags = [];
        const override = lora.override || {};
        const civitai = lora.civitai || {};
        if (override.tags && override.tags.length > 0) {
            activationTags = override.tags.slice(0, 3);
        } else if (civitai.trigger_words && civitai.trigger_words.length > 0) {
            activationTags = civitai.trigger_words.slice(0, 3);
        } else if (lora.tags && lora.tags.length > 0) {
            activationTags = lora.tags.slice(0, 3);
        }

        // Find active Umi node widget
        const activeNode = this.findActiveUmiNode();
        if (activeNode) {
            // The widget name is "text" in Umi nodes
            const promptWidget = activeNode.widgets.find(w => w.name === "text");
            if (promptWidget) {
                const currentValue = promptWidget.value || "";
                let newValue = currentValue ? `${currentValue}, ${loraText}` : loraText;

                // Add activation tags
                if (activationTags.length > 0) {
                    const tagsText = activationTags.join(", ");
                    newValue = `${newValue}, ${tagsText}`;
                }

                promptWidget.value = newValue;

                // Trigger update
                if (promptWidget.callback) {
                    promptWidget.callback(newValue);
                }

                // Trigger input event for syntax highlighting
                if (promptWidget.inputEl) {
                    promptWidget.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                }

                // Force graph redraw
                app.graph.setDirtyCanvas(true, true);

                console.log(`[Umi LoRA Browser] Inserted ${loraText} with tags: ${activationTags.join(", ")}`);
                this.showNotification(`✓ Inserted ${lora.name} into Umi node`);
            } else {
                console.log("[Umi LoRA Browser] No text widget found in Umi node");
                this.showNotification("✗ Could not find text widget", true);
            }
        } else {
            // No active node - copy to clipboard
            navigator.clipboard.writeText(loraText).then(() => {
                console.log(`[Umi LoRA Browser] Copied ${loraText} to clipboard`);
                this.showNotification(`Copied ${loraText} to clipboard`);
            });
        }

        this.hide();
    }

    findActiveUmiNode() {
        // Find the most recently selected Umi node
        const canvas = app.canvas;
        if (!canvas) return null;

        const selectedNodes = canvas.selected_nodes;
        if (selectedNodes) {
            for (const nodeId in selectedNodes) {
                const node = app.graph.getNodeById(parseInt(nodeId));
                if (node && (node.type === "UmiAIWildcardNode" || node.type === "UmiAIWildcardNodeLite")) {
                    return node;
                }
            }
        }

        // Fallback: find any Umi node
        for (const node of app.graph._nodes) {
            if (node.type === "UmiAIWildcardNode" || node.type === "UmiAIWildcardNodeLite") {
                return node;
            }
        }

        return null;
    }

    showNotification(message, isError = false) {
        const notification = document.createElement("div");
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${isError ? '#e06c75' : '#98c379'};
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10001;
            font-size: 14px;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, 2000);
    }

    showEditDialog(lora) {
        // Create edit dialog if it doesn't exist
        if (!this.editDialog) {
            this.createEditDialog();
        }

        const override = lora.override || {};
        const civitai = lora.civitai || {};

        // Populate form with current data (prefer override, fall back to existing data)
        const nicknameInput = this.editDialog.querySelector(".umi-edit-nickname");
        const tagsInput = this.editDialog.querySelector(".umi-edit-tags");
        const previewInput = this.editDialog.querySelector(".umi-edit-preview");
        const loraNameDisplay = this.editDialog.querySelector(".umi-edit-lora-name");

        loraNameDisplay.textContent = lora.name;
        nicknameInput.value = override.nickname || "";
        nicknameInput.placeholder = lora.name;

        // Tags: override > civitai > safetensors
        const currentTags = override.tags || civitai.trigger_words || lora.tags || [];
        tagsInput.value = currentTags.join(", ");

        // Preview: override > civitai
        const currentPreview = override.preview_url || (civitai.preview_url || "");
        previewInput.value = currentPreview;

        // Store lora reference for saving
        this.editDialog.dataset.loraName = lora.name;

        this.editDialog.style.display = "flex";
    }

    createEditDialog() {
        const dialog = document.createElement("div");
        dialog.className = "umi-edit-lora-dialog";
        dialog.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.8);
            z-index: 10002;
            display: none;
            align-items: center;
            justify-content: center;
        `;

        dialog.innerHTML = `
            <div style="
                background: #1e1e1e;
                border: 2px solid #61afef;
                border-radius: 8px;
                padding: 20px;
                width: 500px;
                max-width: 90vw;
            ">
                <h3 style="margin: 0 0 15px 0; color: #61afef;">✏️ Edit LoRA</h3>
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 12px; color: #888; margin-bottom: 5px;">Editing:</div>
                    <div class="umi-edit-lora-name" style="font-weight: 600; color: #abb2bf;"></div>
                </div>

                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; color: #abb2bf; font-size: 13px;">Nickname (optional):</label>
                    <input type="text" class="umi-edit-nickname" style="
                        width: 100%;
                        padding: 8px;
                        background: #2c2c2c;
                        border: 1px solid #555;
                        border-radius: 4px;
                        color: #abb2bf;
                        font-size: 13px;
                    " />
                </div>

                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; color: #abb2bf; font-size: 13px;">Activation Tags (comma-separated):</label>
                    <textarea class="umi-edit-tags" style="
                        width: 100%;
                        padding: 8px;
                        background: #2c2c2c;
                        border: 1px solid #555;
                        border-radius: 4px;
                        color: #abb2bf;
                        font-size: 13px;
                        min-height: 60px;
                        resize: vertical;
                        font-family: inherit;
                    "></textarea>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; color: #abb2bf; font-size: 13px;">Preview Image URL:</label>
                    <input type="text" class="umi-edit-preview" style="
                        width: 100%;
                        padding: 8px;
                        background: #2c2c2c;
                        border: 1px solid #555;
                        border-radius: 4px;
                        color: #abb2bf;
                        font-size: 13px;
                    " placeholder="https://..." />
                </div>

                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="umi-edit-cancel" style="
                        padding: 8px 16px;
                        background: #555;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 13px;
                    ">Cancel</button>
                    <button class="umi-edit-save" style="
                        padding: 8px 16px;
                        background: #61afef;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 13px;
                        font-weight: 600;
                    ">💾 Save</button>
                </div>
            </div>
        `;

        // Event listeners
        const cancelBtn = dialog.querySelector(".umi-edit-cancel");
        cancelBtn.addEventListener("click", () => {
            dialog.style.display = "none";
        });

        const saveBtn = dialog.querySelector(".umi-edit-save");
        saveBtn.addEventListener("click", () => this.saveLoraOverride());

        // Close on background click
        dialog.addEventListener("click", (e) => {
            if (e.target === dialog) {
                dialog.style.display = "none";
            }
        });

        document.body.appendChild(dialog);
        this.editDialog = dialog;
    }

    async saveLoraOverride() {
        const loraName = this.editDialog.dataset.loraName;
        const nickname = this.editDialog.querySelector(".umi-edit-nickname").value.trim();
        const tagsText = this.editDialog.querySelector(".umi-edit-tags").value.trim();
        const previewUrl = this.editDialog.querySelector(".umi-edit-preview").value.trim();

        // Parse tags
        const tags = tagsText ? tagsText.split(',').map(t => t.trim()).filter(t => t) : [];

        // Build override object
        const override = {};
        if (nickname) override.nickname = nickname;
        if (tags.length > 0) override.tags = tags;
        if (previewUrl) override.preview_url = previewUrl;

        try {
            const response = await fetch("/umiapp/loras/overrides/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    lora_name: loraName,
                    override: override
                })
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification("✓ LoRA override saved");
                this.editDialog.style.display = "none";

                // Reload LoRAs to show changes
                await this.fetchLoras();
                this.renderLoras();
            } else {
                this.showNotification(`✗ Save failed: ${data.error}`, true);
            }
        } catch (error) {
            this.showNotification(`✗ Save failed: ${error.message}`, true);
        }
    }

    async show() {
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = "flex";
        await this.fetchLoras();
        this.renderLoras();
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

// Global instance
const loraBrowser = new LoraBrowserPanel();

// Register extension
app.registerExtension({
    name: "Umi.LoraBrowser",

    async setup() {
        // Add menu item
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "📦 LoRA Browser";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => loraBrowser.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+L)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "l") {
                e.preventDefault();
                loraBrowser.show();
            }
        });
    }
});
