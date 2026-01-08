import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Phase 8: Preset Manager - Save and load Umi node configurations

class PresetManager {
    constructor() {
        this.element = null;
        this.presets = [];
        this.selectedPreset = null;
    }

    async loadPresets() {
        try {
            const response = await fetch("/umiapp/presets");
            const data = await response.json();
            this.presets = data.presets || [];
            return this.presets;
        } catch (error) {
            console.error("[Umi Preset Manager] Failed to load presets:", error);
            return [];
        }
    }

    async savePreset(name, description, nodeData) {
        try {
            const response = await fetch("/umiapp/presets/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: name,
                    description: description,
                    data: nodeData
                })
            });

            const result = await response.json();
            if (result.success) {
                await this.loadPresets();
                this.renderPresets();
                this.showNotification(`✓ Saved preset: ${name}`);
                return true;
            } else {
                this.showNotification(`✗ Error: ${result.error}`, true);
                return false;
            }
        } catch (error) {
            this.showNotification(`✗ Failed to save preset: ${error.message}`, true);
            return false;
        }
    }

    async deletePreset(presetName) {
        try {
            const response = await fetch("/umiapp/presets/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: presetName })
            });

            const result = await response.json();
            if (result.success) {
                await this.loadPresets();
                this.renderPresets();
                this.showNotification(`✓ Deleted preset: ${presetName}`);
                return true;
            } else {
                this.showNotification(`✗ Error: ${result.error}`, true);
                return false;
            }
        } catch (error) {
            this.showNotification(`✗ Failed to delete preset: ${error.message}`, true);
            return false;
        }
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-preset-manager";
        panel.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 700px;
            max-width: 90vw;
            max-height: 80vh;
            background: #1e1e1e;
            border: 2px solid #61afef;
            border-radius: 8px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.8);
            z-index: 10000;
            display: none;
            flex-direction: column;
        `;

        panel.innerHTML = `
            <div style="padding: 15px; border-bottom: 1px solid #444; display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; color: #61afef; font-size: 18px;">💾 Preset Manager</h2>
                <button class="umi-close-btn" style="background: #e06c75; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 16px;">✕</button>
            </div>

            <div style="padding: 15px; border-bottom: 1px solid #444;">
                <button class="umi-save-preset-btn" style="
                    width: 100%;
                    padding: 10px;
                    background: linear-gradient(135deg, #98c379 0%, #56b6c2 100%);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: 600;
                    font-size: 14px;
                ">💾 Save Current Node as Preset</button>
            </div>

            <div class="umi-preset-list" style="
                padding: 15px;
                overflow-y: auto;
                flex: 1;
            "></div>

            <div style="padding: 10px; border-top: 1px solid #444; background: #252525; color: #888; font-size: 11px; text-align: center;">
                Click a preset to load it into the active Umi node
            </div>
        `;

        // Event listeners
        const closeBtn = panel.querySelector(".umi-close-btn");
        closeBtn.addEventListener("click", () => this.hide());

        const saveBtn = panel.querySelector(".umi-save-preset-btn");
        saveBtn.addEventListener("click", () => this.showSaveDialog());

        // Close on background click
        panel.addEventListener("click", (e) => {
            if (e.target === panel) {
                this.hide();
            }
        });

        this.element = panel;
        document.body.appendChild(panel);
    }

    renderPresets() {
        const listDiv = this.element.querySelector(".umi-preset-list");
        if (!listDiv) return;

        if (this.presets.length === 0) {
            listDiv.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">No presets saved yet</div>';
            return;
        }

        listDiv.innerHTML = this.presets.map(preset => this.createPresetCard(preset)).join("");

        // Add click handlers
        listDiv.querySelectorAll(".umi-preset-card").forEach((card, index) => {
            card.addEventListener("click", () => {
                this.loadPreset(this.presets[index]);
            });
        });

        // Add delete handlers
        listDiv.querySelectorAll(".umi-delete-preset").forEach((btn, index) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                if (confirm(`Delete preset "${this.presets[index].name}"?`)) {
                    this.deletePreset(this.presets[index].name);
                }
            });
        });
    }

    createPresetCard(preset) {
        const date = new Date(preset.timestamp || Date.now()).toLocaleDateString();
        const description = preset.description || "No description";

        return `
            <div class="umi-preset-card" style="
                background: #2c2c2c;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 12px;
                margin-bottom: 10px;
                cursor: pointer;
                transition: all 0.2s;
            " onmouseover="this.style.borderColor='#61afef'; this.style.transform='translateX(4px)'" onmouseout="this.style.borderColor='#444'; this.style.transform='translateX(0)'">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                    <div style="font-weight: 600; color: #61afef; font-size: 14px;">
                        ${preset.name}
                    </div>
                    <button class="umi-delete-preset" style="
                        background: #e06c75;
                        color: white;
                        border: none;
                        padding: 3px 8px;
                        border-radius: 3px;
                        cursor: pointer;
                        font-size: 11px;
                    ">Delete</button>
                </div>
                <div style="color: #abb2bf; font-size: 12px; margin-bottom: 6px;">
                    ${description}
                </div>
                <div style="display: flex; gap: 15px; font-size: 11px; color: #666;">
                    <span>📅 ${date}</span>
                    ${preset.data.input_prompt ? `<span>📝 ${preset.data.input_prompt.substring(0, 30)}...</span>` : ''}
                </div>
            </div>
        `;
    }

    showSaveDialog() {
        const activeNode = this.findActiveUmiNode();
        if (!activeNode) {
            this.showNotification("No active Umi node found. Please select a node first.", true);
            return;
        }

        const name = prompt("Enter preset name:");
        if (!name) return;

        const description = prompt("Enter description (optional):") || "";

        // Extract node data
        const nodeData = this.extractNodeData(activeNode);
        this.savePreset(name, description, nodeData);
    }

    extractNodeData(node) {
        const data = {};

        if (node.widgets) {
            for (const widget of node.widgets) {
                data[widget.name] = widget.value;
            }
        }

        return data;
    }

    loadPreset(preset) {
        const activeNode = this.findActiveUmiNode();
        if (!activeNode) {
            this.showNotification("No active Umi node found. Please select a node first.", true);
            return;
        }

        if (!preset.data) {
            this.showNotification("Invalid preset data", true);
            return;
        }

        // Apply preset data to node widgets
        if (activeNode.widgets) {
            for (const widget of activeNode.widgets) {
                if (preset.data.hasOwnProperty(widget.name)) {
                    widget.value = preset.data[widget.name];
                    if (widget.callback) {
                        widget.callback(widget.value);
                    }
                }
            }
        }

        this.showNotification(`✓ Loaded preset: ${preset.name}`);
        this.hide();
    }

    findActiveUmiNode() {
        const canvas = app.canvas;
        if (!canvas) return null;

        // Find selected Umi node
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
        }, 3000);
    }

    async show() {
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = "flex";
        await this.loadPresets();
        this.renderPresets();
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

// Global instance
const presetManager = new PresetManager();

// Register extension
app.registerExtension({
    name: "Umi.PresetManager",

    async setup() {
        // Add menu item
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "💾 Presets";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => presetManager.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+P)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "p") {
                e.preventDefault();
                presetManager.show();
            }
        });
    }
});
