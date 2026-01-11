/**
 * UmiAI Character Designer Widget
 * Premium form-based character design with modern dark UI.
 * Now renders as a floating side panel attached to the node.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

class UmiCharacterDesignerWidget {
    constructor(node, app) {
        this.node = node;
        this.app = app;

        // Character data
        this.data = {
            name: "",
            sex: "female",
            age: "young adult",
            race: "human",
            eyes: "",
            hair: "",
            face: "",
            body: "",
            skin: ""
        };

        // Create floating panel
        this.panel = document.createElement("div");
        this.panel.className = "umi-character-designer-panel";
        document.body.appendChild(this.panel);

        this.injectStyles();
        this.buildUI();
        this.updateDependencyStatus();

        // Initial positioning
        this.updatePosition();
    }

    injectStyles() {
        if (document.getElementById("umi-character-designer-styles")) return;

        const style = document.createElement("style");
        style.id = "umi-character-designer-styles";
        style.textContent = `
            .umi-character-designer-panel {
                position: absolute;
                top: 0;
                left: 0;
                width: 320px;
                background: linear-gradient(180deg, #13131f 0%, #0f1016 100%);
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.08);
                padding: 16px;
                box-sizing: border-box;
                color: #fff;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                z-index: 1000;
                box-shadow: 4px 4px 20px rgba(0,0,0,0.5);
                transform-origin: 0 0;
                pointer-events: auto;
                will-change: transform;
            }
            
            .umi-character-designer-panel * {
                box-sizing: border-box;
            }
            
            .ucd-header {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 16px;
                padding-bottom: 12px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
            
            .ucd-header h3 {
                margin: 0;
                font-size: 15px;
                font-weight: 600;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                letter-spacing: 0.5px;
            }
            
            .ucd-icon { font-size: 20px; }
            
            .ucd-name-input {
                width: 100%;
                padding: 10px 14px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                color: #fff;
                font-size: 14px;
                font-weight: 500;
                margin-bottom: 16px;
                transition: all 0.2s;
            }
            
            .ucd-name-input:focus {
                outline: none;
                border-color: #667eea;
                background: rgba(102, 126, 234, 0.08);
            }
            
            .ucd-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px;
                margin-bottom: 20px;
            }
            
            .ucd-field {
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
            }
            
            .ucd-field.full { grid-column: 1 / -1; }
            
            .ucd-label {
                font-size: 11px;
                color: rgba(255,255,255,0.5);
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-weight: 600;
            }
            
            .ucd-input, .ucd-select {
                width: 100%;
                padding: 8px 12px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                color: #fff;
                font-size: 13px;
                transition: all 0.2s;
                height: 34px;
            }
            
            .ucd-input:focus, .ucd-select:focus {
                outline: none;
                border-color: #667eea;
                background: rgba(102, 126, 234, 0.08);
            }
            
            .ucd-select {
                cursor: pointer;
                appearance: none;
                background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
                background-position: right 0.5rem center;
                background-repeat: no-repeat;
                background-size: 1.5em 1.5em;
                padding-right: 2.5rem;
            }
            
            .ucd-select option { background: #1a1a2e; color: #fff; }
            
            .ucd-btn-row {
                display: flex;
                gap: 10px;
                margin-top: auto;
            }
            
            .ucd-btn {
                flex: 1;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                text-align: center;
            }
            
            .ucd-btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                box-shadow: 0 1px 2px rgba(0,0,0,0.2);
            }
            
            .ucd-btn-primary:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            }
            
            .ucd-btn-secondary {
                background: rgba(255,255,255,0.05);
                color: rgba(255,255,255,0.7);
                border: 1px solid rgba(255,255,255,0.1);
            }
            
            .ucd-btn-secondary:hover {
                background: rgba(255,255,255,0.1);
                color: #fff;
                border-color: rgba(255,255,255,0.2);
            }
            
            .ucd-status {
                margin-top: 12px;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 12px;
                text-align: center;
                display: none;
                animation: ucd-fadeIn 0.3s ease-out;
            }
            
            @keyframes ucd-fadeIn {
                from { opacity: 0; transform: translateY(-5px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .ucd-status.success {
                display: block;
                background: rgba(16, 185, 129, 0.1);
                color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.2);
            }
            
            .ucd-status.error {
                display: block;
                background: rgba(239, 68, 68, 0.1);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.2);
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
            <div class="ucd-header">
                <span class="ucd-icon">✨</span>
                <h3>Character Designer</h3>
            </div>

            <div class="umi-deps-banner" id="ucd-deps"></div>
            
            <input type="text" class="ucd-name-input" placeholder="Enter character name..." data-key="name">
            
            <div class="ucd-grid">
                <div class="ucd-field">
                    <span class="ucd-label">Sex</span>
                    <select class="ucd-select" data-key="sex">
                        <option value="female">Female</option>
                        <option value="male">Male</option>
                        <option value="androgynous">Androgynous</option>
                    </select>
                </div>
                
                <div class="ucd-field">
                    <span class="ucd-label">Age</span>
                    <select class="ucd-select" data-key="age">
                        <option value="teen">Teen</option>
                        <option value="young adult" selected>Young Adult</option>
                        <option value="adult">Adult</option>
                        <option value="middle-aged">Middle-Aged</option>
                    </select>
                </div>
                
                <div class="ucd-field">
                    <span class="ucd-label">Race</span>
                    <select class="ucd-select" data-key="race">
                        <option value="human">Human</option>
                        <option value="elf">Elf</option>
                        <option value="demon">Demon</option>
                        <option value="angel">Angel</option>
                        <option value="catgirl">Catgirl</option>
                        <option value="foxgirl">Foxgirl</option>
                    </select>
                </div>
                
                <div class="ucd-field">
                    <span class="ucd-label">Skin</span>
                    <input type="text" class="ucd-input" placeholder="fair, tan, dark..." data-key="skin">
                </div>
                
                <div class="ucd-field full">
                    <span class="ucd-label">Eyes</span>
                    <input type="text" class="ucd-input" placeholder="blue eyes, heterochromia..." data-key="eyes">
                </div>
                
                <div class="ucd-field full">
                    <span class="ucd-label">Hair</span>
                    <input type="text" class="ucd-input" placeholder="long blonde hair, twin tails..." data-key="hair">
                </div>
                
                <div class="ucd-field full">
                    <span class="ucd-label">Face</span>
                    <input type="text" class="ucd-input" placeholder="beautiful, freckles..." data-key="face">
                </div>
                
                <div class="ucd-field full">
                    <span class="ucd-label">Body</span>
                    <input type="text" class="ucd-input" placeholder="slim, athletic, curvy..." data-key="body">
                </div>
            </div>
            
            <div class="ucd-btn-row">
                <button class="ucd-btn ucd-btn-secondary" id="ucd-load">📂 Load</button>
                <button class="ucd-btn ucd-btn-primary" id="ucd-create">✨ Create</button>
            </div>
            
            <div class="ucd-status" id="ucd-status"></div>
        `;

        // Bind events
        this.panel.querySelectorAll("[data-key]").forEach(el => {
            el.addEventListener("change", (e) => {
                this.data[e.target.dataset.key] = e.target.value;
                this.syncToNode();
            });
            el.addEventListener("input", (e) => {
                this.data[e.target.dataset.key] = e.target.value;
            });
        });

        this.panel.querySelector("#ucd-create").addEventListener("click", () => this.createCharacter());
        this.panel.querySelector("#ucd-load").addEventListener("click", () => this.loadCharacter());
    }

    async updateDependencyStatus() {
        const banner = this.panel.querySelector("#ucd-deps");
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

    updatePosition() {
        if (!this.node || !this.panel) return;

        // Hide if node is collapsed or removed
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

        // Position to the right of the node
        // Use fixed 10px screen-space gap to prevent visual drift
        const x = (nodeX + nodeW) * scale + offset[0] + 10;
        const y = nodeY * scale + offset[1];

        // Round to avoid subpixel jitter
        const rx = Math.round(x);
        const ry = Math.round(y);

        this.panel.style.transform = `translate(${rx}px, ${ry}px) scale(${scale})`;
    }

    syncToNode() {
        if (!this.node.widgets) return;

        const keyMap = {
            "name": "new_character_name",
            "skin": "skin_color",
        };

        const ageMap = {
            "teen": 18,
            "young adult": 24,
            "adult": 30,
            "middle-aged": 45
        };

        for (const widget of this.node.widgets) {
            let value = null;

            if (widget.name === "age") {
                value = ageMap[this.data.age] || 24;
            }

            if (this.data.hasOwnProperty(widget.name)) {
                value = this.data[widget.name];
            }

            for (const [dataKey, widgetName] of Object.entries(keyMap)) {
                if (widget.name === widgetName) {
                    value = this.data[dataKey];
                }
            }

            if (value !== null) {
                widget.value = value;
            }
        }
        this.node.setDirtyCanvas(true, true);
    }

    forceHideWidgets() {
        if (!this.node.widgets) return;

        const widgetsToHide = [
            "new_character_name", "sex", "age", "race", "eyes",
            "hair", "face", "body", "skin_color"
        ];

        // Aggressively hide any matching widget
        for (const w of this.node.widgets) {
            if (widgetsToHide.includes(w.name)) {
                w.type = "hidden";
                w.computeSize = () => [0, -4];
                w.hidden = true; // Extra safety for some nodes
            }
        }
    }

    showStatus(message, type) {
        const status = this.panel.querySelector("#ucd-status");
        if (status) {
            status.textContent = message;
            status.className = `ucd-status ${type}`;

            setTimeout(() => {
                status.className = "ucd-status";
            }, 3000);
        }
    }

    async createCharacter() {
        if (!this.data.name) {
            this.showStatus("Please enter a character name", "error");
            return;
        }

        try {
            const response = await api.fetchApi("/umiapp/character/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(this.data)
            });

            if (response.ok) {
                this.showStatus(`✨ Created: ${this.data.name}`, "success");
                this.syncToNode();
            } else {
                this.showStatus("Failed to create character", "error");
            }
        } catch (e) {
            this.showStatus("Error: " + e.message, "error");
        }
    }

    async loadCharacter() {
        try {
            const response = await api.fetchApi("/umiapp/characters");
            const data = await response.json();

            if (data?.characters?.length > 0) {
                const name = prompt("Enter character name to load:\n\nAvailable: " + data.characters.join(", "));
                if (name && data.characters.includes(name)) {
                    const charResponse = await api.fetchApi(`/umiapp/character/${name}`);
                    const charData = await charResponse.json();
                    if (charData?.Info) {
                        Object.assign(this.data, charData.Info);
                        this.data.name = name;
                        this.updateInputs();
                        this.showStatus(`Loaded: ${name}`, "success");
                    }
                }
            } else {
                this.showStatus("No characters found", "error");
            }
        } catch (e) {
            this.showStatus("Failed to load", "error");
        }
    }

    updateInputs() {
        this.panel.querySelectorAll("[data-key]").forEach(el => {
            if (this.data[el.dataset.key]) {
                el.value = this.data[el.dataset.key];
            }
        });
    }

    destroy() {
        if (this.panel && this.panel.parentNode) {
            this.panel.parentNode.removeChild(this.panel);
        }
        this.panel = null;
    }
}

// Extension Registration
app.registerExtension({
    name: "Umi.CharacterDesigner",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UmiCharacterDesigner") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }

                const widget = new UmiCharacterDesignerWidget(this, app);
                this.characterWidget = widget;

                // Initial hide
                widget.forceHideWidgets();
            };

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }
                // Re-hide on load from workflow
                if (this.characterWidget) {
                    this.characterWidget.forceHideWidgets();
                }
            };

            // Hook into Draw Foreground for perfect sync
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function (ctx) {
                if (onDrawForeground) {
                    onDrawForeground.apply(this, arguments);
                }
                if (this.characterWidget) {
                    this.characterWidget.updatePosition();
                }
            };

            const onRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function () {
                if (this.characterWidget) {
                    this.characterWidget.destroy();
                }
                if (onRemoved) {
                    onRemoved.apply(this, arguments);
                }
            }
        }
    }
});
