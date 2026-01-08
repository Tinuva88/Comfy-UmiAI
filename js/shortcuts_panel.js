import { app } from "../../scripts/app.js";

// Phase 8: Keyboard Shortcuts Panel - Show all available shortcuts

class ShortcutsPanel {
    constructor() {
        this.element = null;
        this.shortcuts = [
            {
                category: "Browser Panels",
                items: [
                    { keys: "Ctrl+L", description: "Open LoRA Browser", icon: "📦" },
                    { keys: "Ctrl+I", description: "Open Image Browser", icon: "🖼️" },
                    { keys: "Ctrl+P", description: "Open Preset Manager", icon: "💾" },
                    { keys: "Ctrl+H", description: "Open Prompt History", icon: "📜" },
                    { keys: "Ctrl+?", description: "Show Keyboard Shortcuts", icon: "⌨️" }
                ]
            },
            {
                category: "Panel Actions",
                items: [
                    { keys: "ESC", description: "Close active panel", icon: "✕" },
                    { keys: "Click outside", description: "Close active panel", icon: "🖱️" }
                ]
            },
            {
                category: "Wildcard Syntax",
                items: [
                    { keys: "__filename__", description: "Simple wildcard", icon: "📝" },
                    { keys: "__~filename__", description: "Sequential wildcard", icon: "🔄" },
                    { keys: "__@filename__", description: "Load full file as prompt", icon: "📄" },
                    { keys: "<[tag]>", description: "YAML tag selection", icon: "🏷️" },
                    { keys: "{option1|option2}", description: "Dynamic choice", icon: "🎲" }
                ]
            },
            {
                category: "Logic Operators",
                items: [
                    { keys: "[tag1 AND tag2]", description: "Both tags required", icon: "∧" },
                    { keys: "[tag1 OR tag2]", description: "Either tag", icon: "∨" },
                    { keys: "[NOT tag]", description: "Exclude tag", icon: "¬" },
                    { keys: "[tag1 XOR tag2]", description: "Exactly one tag", icon: "⊕" },
                    { keys: "[tag1 NAND tag2]", description: "NOT(both tags)", icon: "⊼" },
                    { keys: "[tag1 NOR tag2]", description: "NOT(either tag)", icon: "⊽" }
                ]
            }
        ];
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-shortcuts-panel";
        panel.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 800px;
            max-width: 90vw;
            max-height: 85vh;
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
                <h2 style="margin: 0; color: #61afef; font-size: 18px;">⌨️ Keyboard Shortcuts & Syntax</h2>
                <button class="umi-close-btn" style="background: #e06c75; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 16px;">✕</button>
            </div>

            <div class="umi-shortcuts-content" style="
                padding: 20px;
                overflow-y: auto;
                flex: 1;
            ">
                ${this.renderShortcuts()}
            </div>

            <div style="padding: 10px; border-top: 1px solid #444; background: #252525; color: #888; font-size: 11px; text-align: center;">
                Press Ctrl+? anytime to view this guide
            </div>
        `;

        // Event listeners
        const closeBtn = panel.querySelector(".umi-close-btn");
        closeBtn.addEventListener("click", () => this.hide());

        // Close on background click
        panel.addEventListener("click", (e) => {
            if (e.target === panel) {
                this.hide();
            }
        });

        // Close on ESC key
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && panel.style.display === "flex") {
                this.hide();
            }
        });

        this.element = panel;
        document.body.appendChild(panel);
    }

    renderShortcuts() {
        return this.shortcuts.map(category => `
            <div style="margin-bottom: 25px;">
                <h3 style="color: #98c379; font-size: 15px; margin-bottom: 12px; border-bottom: 1px solid #444; padding-bottom: 6px;">
                    ${category.category}
                </h3>
                <div style="display: grid; gap: 10px;">
                    ${category.items.map(item => `
                        <div style="
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                            padding: 10px 12px;
                            background: #2c2c2c;
                            border-radius: 6px;
                            border: 1px solid #444;
                            transition: all 0.2s;
                        " onmouseover="this.style.borderColor='#61afef'" onmouseout="this.style.borderColor='#444'">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="font-size: 20px;">${item.icon}</span>
                                <span style="color: #abb2bf; font-size: 13px;">${item.description}</span>
                            </div>
                            <kbd style="
                                padding: 4px 10px;
                                background: #3e4451;
                                color: #61afef;
                                border-radius: 4px;
                                font-family: monospace;
                                font-size: 12px;
                                border: 1px solid #555;
                                box-shadow: 0 2px 0 #222;
                            ">${item.keys}</kbd>
                        </div>
                    `).join("")}
                </div>
            </div>
        `).join("");
    }

    show() {
        if (!this.element) {
            this.createPanel();
        }
        this.element.style.display = "flex";
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

// Global instance
const shortcutsPanel = new ShortcutsPanel();

// Register extension
app.registerExtension({
    name: "Umi.ShortcutsPanel",

    async setup() {
        // Add menu item
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "⌨️ Shortcuts";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => shortcutsPanel.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+?)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && (e.key === "?" || e.key === "/")) {
                e.preventDefault();
                shortcutsPanel.show();
            }
        });
    }
});
