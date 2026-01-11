/**
 * UmiAI Emotion Studio Widget
 * Visual picker for emotions with image grid, costume selection, and category filtering.
 * VNCCS-compatible with full costume support.
 * Now renders as a floating side panel.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Constants
const GRID_COLS = 6;
const ITEM_SIZE = 64;
const ITEM_GAP = 8;

class UmiEmotionStudioWidget {
    constructor(node, app) {
        this.node = node;
        this.app = app;

        // State
        this.emotionsData = {};
        this.selectedEmotions = new Set();
        this.selectedCostumes = new Set();
        this.availableCostumes = [];
        this.currentCategory = "All";
        this.currentCharacter = "";

        // Create floating panel
        this.panel = document.createElement("div");
        this.panel.className = "umi-emotion-studio-panel";
        document.body.appendChild(this.panel);

        this.injectStyles();
        this.buildUI();
        this.loadEmotions();
        this.updateDependencyStatus();

        // Initial positioning
        this.updatePosition();
    }

    injectStyles() {
        if (document.getElementById("umi-emotion-studio-styles")) return;

        const style = document.createElement("style");
        style.id = "umi-emotion-studio-styles";
        style.textContent = `
            .umi-emotion-studio-panel {
                position: absolute;
                top: 0;
                left: 0;
                width: 360px;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                padding: 12px;
                background: linear-gradient(180deg, #13131f 0%, #0f1016 100%);
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.08);
                box-sizing: border-box;
                color: #fff;
                z-index: 1000;
                box-shadow: 4px 4px 20px rgba(0,0,0,0.5);
                transform-origin: 0 0;
                pointer-events: auto;
                will-change: transform;
            }
            
            .umi-emotion-studio-panel * {
                box-sizing: border-box;
            }
            
            .ues-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 12px;
                padding-bottom: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
            
            .ues-title {
                font-size: 14px;
                font-weight: 600;
                letter-spacing: 0.5px;
                color: #e0e0e0;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            
            .ues-btn {
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                line-height: 1.2;
            }
            
            .ues-btn-primary {
                background: #3b82f6;
                color: white;
                box-shadow: 0 1px 2px rgba(0,0,0,0.2);
            }
            
            .ues-btn-primary:hover {
                background: #2563eb;
            }
            
            .ues-selected-display {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                min-height: 38px;
                padding: 8px;
                background: rgba(0,0,0,0.2);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 6px;
                margin-bottom: 4px;
            }
            
            .ues-tag {
                display: inline-flex;
                align-items: center;
                padding: 2px 8px;
                background: rgba(59, 130, 246, 0.2);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 4px;
                color: #bfdbfe;
                font-size: 11px;
                cursor: pointer;
                transition: background 0.2s;
            }
            
            .ues-tag:hover {
                background: rgba(59, 130, 246, 0.3);
                color: #fff;
                text-decoration: line-through;
            }
            
            .ues-placeholder {
                color: rgba(255,255,255,0.3);
                font-size: 12px;
                font-style: italic;
                padding: 2px 0;
            }
            
            .ues-costume-row {
                display: flex;
                gap: 6px;
                margin-bottom: 12px;
                flex-wrap: wrap;
            }
            
            .ues-costume-btn {
                padding: 3px 10px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                color: rgba(255,255,255,0.6);
                font-size: 11px;
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .ues-costume-btn:hover {
                background: rgba(255,255,255,0.1);
                color: #fff;
            }
            
            .ues-costume-btn.selected {
                background: rgba(236, 72, 153, 0.2);
                border-color: rgba(236, 72, 153, 0.5);
                color: #fbcfe8;
            }
            
            /* Modal Styles */
            .ues-modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(2px);
                z-index: 99999; /* Ensure on top of side panel */
                justify-content: center;
                align-items: center;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            
            .ues-modal * {
                box-sizing: border-box;
            }
            
            .ues-modal-content {
                background: #18181b;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                padding: 0;
                width: 90%;
                max-width: 800px;
                max-height: 85vh;
                display: flex;
                flex-direction: column;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                animation: ues-fadeIn 0.2s ease-out;
            }
            
            @keyframes ues-fadeIn {
                from { opacity: 0; transform: scale(0.95); }
                to { opacity: 1; transform: scale(1); }
            }
            
            .ues-modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 20px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                background: rgba(255,255,255,0.02);
            }
            
            .ues-modal-title {
                font-size: 16px;
                font-weight: 600;
                color: #fff;
            }
            
            .ues-close-btn {
                background: transparent;
                border: none;
                color: rgba(255,255,255,0.5);
                font-size: 20px;
                cursor: pointer;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 4px;
                transition: all 0.2s;
            }
            
            .ues-close-btn:hover {
                background: rgba(255,255,255,0.1);
                color: #fff;
            }
            
            .ues-category-filter {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding: 16px 20px 8px;
            }
            
            .ues-category-btn {
                padding: 4px 12px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
                color: rgba(255,255,255,0.6);
                font-size: 12px;
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .ues-category-btn:hover {
                background: rgba(255,255,255,0.1);
                color: #fff;
            }
            
            .ues-category-btn.active {
                background: #3b82f6;
                border-color: #3b82f6;
                color: white;
            }
            
            .ues-grid-container {
                flex: 1;
                overflow-y: auto;
                padding: 12px 20px 20px;
            }
            
            /* Custom Scrollbar */
            .ues-grid-container::-webkit-scrollbar {
                width: 8px;
            }
            .ues-grid-container::-webkit-scrollbar-track {
                background: rgba(0,0,0,0.1);
            }
            .ues-grid-container::-webkit-scrollbar-thumb {
                background: rgba(255,255,255,0.1);
                border-radius: 4px;
            }
            .ues-grid-container::-webkit-scrollbar-thumb:hover {
                background: rgba(255,255,255,0.2);
            }
            
            .ues-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(${ITEM_SIZE}px, 1fr));
                gap: 12px;
                justify-content: center;
            }
            
            .ues-emotion-item {
                display: flex;
                flex-direction: column;
                align-items: center;
                cursor: pointer;
                border-radius: 6px;
                border: 2px solid transparent;
                background: rgba(255,255,255,0.03);
                padding: 6px;
                transition: all 0.2s;
                height: 100%;
            }
            
            .ues-emotion-item:hover {
                background: rgba(255,255,255,0.08);
                transform: translateY(-2px);
            }
            
            .ues-emotion-item.selected {
                border-color: #ec4899;
                background: rgba(236, 72, 153, 0.1);
            }
            
            .ues-emotion-img {
                width: 100%;
                aspect-ratio: 1;
                object-fit: contain;
                border-radius: 4px;
                background: rgba(0,0,0,0.2);
                margin-bottom: 6px;
            }
            
            .ues-emotion-label {
                font-size: 10px;
                color: rgba(255,255,255,0.7);
                text-align: center;
                line-height: 1.2;
                word-break: break-word;
            }
            
            .ues-modal-footer {
                display: flex;
                justify-content: flex-end;
                gap: 12px;
                padding: 16px 20px;
                border-top: 1px solid rgba(255,255,255,0.08);
                background: rgba(255,255,255,0.02);
            }
            
            .ues-btn-secondary {
                background: transparent;
                color: rgba(255,255,255,0.7);
                border: 1px solid rgba(255,255,255,0.15);
            }
            
            .ues-btn-secondary:hover {
                background: rgba(255,255,255,0.05);
                color: #fff;
                border-color: rgba(255,255,255,0.3);
            }

            .umi-deps-banner {
                display: none;
                margin: 8px 0 12px;
                padding: 8px 10px;
                border-radius: 6px;
                background: rgba(229, 192, 123, 0.12);
                border: 1px solid rgba(229, 192, 123, 0.35);
                color: #e5c07b;
                font-size: 12px;
            }
        `;
        document.head.appendChild(style);
    }

    buildUI() {
        this.panel.innerHTML = `
            <div class="ues-header">
                <span class="ues-title">🎭 Emotion Studio</span>
                <button class="ues-btn ues-btn-primary" id="ues-open">📋 Open Picker</button>
            </div>

            <div class="umi-deps-banner" id="ues-deps"></div>
            
            <div class="ues-costume-row" id="ues-costumes"></div>
            
            <div class="ues-selected-display" id="ues-selected">
                <span class="ues-placeholder">No emotions selected</span>
            </div>
        `;

        this.panel.querySelector("#ues-open").addEventListener("click", () => this.openModal());

        // Create modal (attached to body independently)
        this.modal = this.createModal();
        document.body.appendChild(this.modal);
    }

    updatePosition() {
        if (!this.node || !this.panel) return;

        // Hide if node is removed or collapsed
        if (!this.node.graph || this.node.flags?.collapsed) {
            this.panel.style.display = "none";
            return;
        } else {
            this.panel.style.display = "block";
        }

        // Calculate position
        const transform = this.app.canvas.ds;
        if (!transform) return;

        const scale = transform.scale;
        const offset = transform.offset;

        const nodeX = this.node.pos[0];
        const nodeY = this.node.pos[1];
        const nodeW = this.node.size[0];

        // Position to the right (CharacterDesigner is +10px, let's keep consistent)
        // Usign fixed 10px gap in screen space + rounding
        const x = (nodeX + nodeW) * scale + offset[0] + 10;
        const y = nodeY * scale + offset[1];

        const rx = Math.round(x);
        const ry = Math.round(y);

        this.panel.style.transform = `translate(${rx}px, ${ry}px) scale(${scale})`;
    }

    createModal() {
        const modal = document.createElement("div");
        modal.className = "ues-modal";
        modal.innerHTML = `
            <div class="ues-modal-content">
                <div class="ues-modal-header">
                    <span class="ues-modal-title">🎭 Select Emotions</span>
                    <button class="ues-close-btn" id="ues-close">✕</button>
                </div>
                
                <div class="ues-category-filter" id="ues-categories"></div>
                
                <div class="ues-grid-container">
                    <div class="ues-grid" id="ues-grid"></div>
                </div>
                
                <div class="ues-modal-footer">
                    <button class="ues-btn ues-btn-secondary" id="ues-clear">Clear All</button>
                    <button class="ues-btn ues-btn-primary" id="ues-apply">✨ Apply Selection</button>
                </div>
            </div>
        `;

        modal.querySelector("#ues-close").addEventListener("click", () => this.closeModal());
        modal.querySelector("#ues-clear").addEventListener("click", () => this.clearSelection());
        modal.querySelector("#ues-apply").addEventListener("click", () => this.applySelection());
        modal.addEventListener("click", (e) => {
            if (e.target === modal) this.closeModal();
        });

        return modal;
    }

    async loadEmotions() {
        try {
            const response = await api.fetchApi("/umiapp/emotions");
            this.emotionsData = await response.json();
            this.buildCategoryFilter();
        } catch (e) {
            console.error("[UmiAI Emotion Studio] Failed to load emotions:", e);
        }
    }

    async updateDependencyStatus() {
        const banner = this.panel.querySelector("#ues-deps");
        if (!banner) return;
        try {
            const response = await api.fetchApi("/umiapp/deps");
            if (!response.ok) return;
            const data = await response.json();
            const missing = data.missing || [];
            if (missing.length) {
                banner.textContent = `Missing optional dependencies: ${missing.join(", ")}. Install with: pip install ${missing.join(" ")}`;
                banner.style.display = "block";
            } else {
                banner.style.display = "none";
            }
        } catch (e) {
        }
    }

    async loadCostumes(character) {
        if (!character || character === "None") {
            this.availableCostumes = [];
            this.renderCostumes();
            return;
        }

        try {
            const response = await api.fetchApi(`/umiapp/character/costumes?character=${encodeURIComponent(character)}`);
            this.availableCostumes = await response.json();
            this.renderCostumes();
        } catch (e) {
            console.error("[UmiAI Emotion Studio] Failed to load costumes:", e);
        }
    }

    renderCostumes() {
        const container = this.panel.querySelector("#ues-costumes");
        container.innerHTML = "";

        if (this.availableCostumes.length === 0) {
            container.innerHTML = '<span class="ues-placeholder">No costumes available</span>';
            return;
        }

        this.availableCostumes.forEach(costume => {
            const btn = document.createElement("button");
            btn.className = `ues-costume-btn ${this.selectedCostumes.has(costume) ? 'selected' : ''}`;
            btn.textContent = costume;
            btn.addEventListener("click", () => this.toggleCostume(costume));
            container.appendChild(btn);
        });
    }

    toggleCostume(costume) {
        if (this.selectedCostumes.has(costume)) {
            this.selectedCostumes.delete(costume);
        } else {
            this.selectedCostumes.add(costume);
        }
        this.renderCostumes();
        this.updateNode();
    }

    buildCategoryFilter() {
        const container = this.modal.querySelector("#ues-categories");
        container.innerHTML = "";

        const categories = ["All", ...Object.keys(this.emotionsData)];

        categories.forEach(cat => {
            const btn = document.createElement("button");
            btn.className = `ues-category-btn ${cat === this.currentCategory ? 'active' : ''}`;
            btn.textContent = cat;
            btn.addEventListener("click", () => this.filterByCategory(cat));
            container.appendChild(btn);
        });
    }

    filterByCategory(category) {
        this.currentCategory = category;
        this.buildCategoryFilter();
        this.renderGrid();
    }

    renderGrid() {
        const grid = this.modal.querySelector("#ues-grid");
        grid.innerHTML = "";

        let emotions = [];
        if (this.currentCategory === "All") {
            Object.values(this.emotionsData).forEach(catEmotions => {
                if (Array.isArray(catEmotions)) {
                    emotions = emotions.concat(catEmotions);
                }
            });
        } else {
            emotions = this.emotionsData[this.currentCategory] || [];
        }

        emotions.forEach(emotion => {
            const item = this.createEmotionItem(emotion);
            grid.appendChild(item);
        });
    }

    createEmotionItem(emotion) {
        const safeName = emotion.safe_name || emotion.key;
        const isSelected = this.selectedEmotions.has(safeName);

        const item = document.createElement("div");
        item.className = `ues-emotion-item ${isSelected ? 'selected' : ''}`;

        const img = document.createElement("img");
        img.className = "ues-emotion-img";
        img.src = `/umiapp/emotion/image?name=${encodeURIComponent(safeName)}`;
        img.alt = safeName;
        img.loading = "lazy";
        img.onerror = () => {
            img.style.opacity = "0.3";
        };

        const label = document.createElement("span");
        label.className = "ues-emotion-label";
        label.textContent = safeName.replace(/-/g, " ").slice(0, 10);

        item.appendChild(img);
        item.appendChild(label);

        item.addEventListener("click", () => this.toggleEmotion(safeName));
        item.title = `${emotion.key}\n${emotion.description || ""}`;

        return item;
    }

    toggleEmotion(safeName) {
        if (this.selectedEmotions.has(safeName)) {
            this.selectedEmotions.delete(safeName);
        } else {
            this.selectedEmotions.add(safeName);
        }
        this.renderGrid();
        this.updateSelectedDisplay();
    }

    updateSelectedDisplay() {
        const container = this.panel.querySelector("#ues-selected");
        container.innerHTML = "";

        if (this.selectedEmotions.size === 0) {
            container.innerHTML = '<span class="ues-placeholder">No emotions selected</span>';
            return;
        }

        this.selectedEmotions.forEach(name => {
            const tag = document.createElement("span");
            tag.className = "ues-tag";
            tag.textContent = name;
            tag.addEventListener("click", () => {
                this.selectedEmotions.delete(name);
                this.updateSelectedDisplay();
                this.renderGrid();
                this.updateNode();
            });
            container.appendChild(tag);
        });
    }

    clearSelection() {
        this.selectedEmotions.clear();
        this.renderGrid();
        this.updateSelectedDisplay();
    }

    applySelection() {
        this.updateNode();
        this.closeModal();
    }

    updateNode() {
        const emotionsStr = Array.from(this.selectedEmotions).join(",");
        const costumesStr = Array.from(this.selectedCostumes).join(",");

        if (this.node.widgets) {
            for (const widget of this.node.widgets) {
                if (widget.name === "selected_emotions") {
                    widget.value = emotionsStr;
                }
                if (widget.name === "selected_costumes") {
                    widget.value = costumesStr;
                }
            }
        }

        this.node.setDirtyCanvas(true, true);
    }

    forceHideWidgets() {
        if (!this.node.widgets) return;
        const widgetsToHide = ["selected_emotions", "selected_costumes"];
        for (const w of this.node.widgets) {
            if (widgetsToHide.includes(w.name)) {
                w.type = "hidden";
                w.computeSize = () => [0, -4];
                w.hidden = true;
            }
        }
    }

    openModal() {
        this.modal.style.display = "flex";
        this.renderGrid();
    }

    closeModal() {
        this.modal.style.display = "none";
    }

    setCharacter(character) {
        if (character !== this.currentCharacter) {
            this.currentCharacter = character;
            this.loadCostumes(character);
        }
    }

    destroy() {
        if (this.panel && this.panel.parentNode) {
            this.panel.parentNode.removeChild(this.panel);
        }
        if (this.modal && this.modal.parentNode) {
            this.modal.parentNode.removeChild(this.modal);
        }
        this.panel = null;
        this.modal = null;
    }
}

// Extension Registration
app.registerExtension({
    name: "Umi.EmotionStudio",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UmiEmotionStudio") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }

                const widget = new UmiEmotionStudioWidget(this, app);
                this.emotionWidget = widget;
                this.setSize([300, 100]);

                widget.forceHideWidgets();

                // Watch for character widget changes
                const charWidget = this.widgets?.find(w => w.name === "character");
                if (charWidget) {
                    const originalCallback = charWidget.callback;
                    charWidget.callback = (value) => {
                        if (originalCallback) originalCallback(value);
                        widget.setCharacter(value);
                    };
                    widget.setCharacter(charWidget.value);
                }
            };

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }
                if (this.emotionWidget) {
                    this.emotionWidget.forceHideWidgets();
                }
            };

            // Hook into Draw Foreground for perfect sync
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function (ctx) {
                if (onDrawForeground) {
                    onDrawForeground.apply(this, arguments);
                }
                if (this.emotionWidget) {
                    this.emotionWidget.updatePosition();
                }
            };

            const onRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function () {
                if (this.emotionWidget) {
                    this.emotionWidget.destroy();
                }
                if (onRemoved) {
                    onRemoved.apply(this, arguments);
                }
            };
        }
    }
});

console.log("[UmiAI] Emotion Studio widget loaded");
