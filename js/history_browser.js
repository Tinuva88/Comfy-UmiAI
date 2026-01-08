import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Phase 8: Prompt History Browser - Track and restore previous prompts

class HistoryBrowser {
    constructor() {
        this.element = null;
        this.history = [];
        this.searchTerm = "";
        this.currentPage = 0;
        this.pageSize = 20;
    }

    async loadHistory() {
        try {
            const response = await fetch("/umiapp/history");
            const data = await response.json();
            this.history = data.history || [];
            return this.history;
        } catch (error) {
            console.error("[Umi History Browser] Failed to load history:", error);
            return [];
        }
    }

    async clearHistory() {
        if (!confirm("Clear all prompt history? This cannot be undone.")) {
            return;
        }

        try {
            const response = await fetch("/umiapp/history/clear", {
                method: "POST",
                headers: { "Content-Type": "application/json" }
            });

            const result = await response.json();
            if (result.success) {
                this.history = [];
                this.renderHistory();
                this.showNotification("✓ History cleared");
            }
        } catch (error) {
            this.showNotification(`✗ Failed to clear history: ${error.message}`, true);
        }
    }

    async exportHistory() {
        try {
            const data = JSON.stringify(this.history, null, 2);
            const blob = new Blob([data], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `umi_history_${new Date().toISOString().split('T')[0]}.json`;
            a.click();
            URL.revokeObjectURL(url);
            this.showNotification("✓ History exported");
        } catch (error) {
            this.showNotification(`✗ Export failed: ${error.message}`, true);
        }
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-history-browser";
        panel.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 900px;
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
                <h2 style="margin: 0; color: #61afef; font-size: 18px;">📜 Prompt History</h2>
                <button class="umi-close-btn" style="background: #e06c75; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 16px;">✕</button>
            </div>

            <div style="padding: 15px; border-bottom: 1px solid #444;">
                <input
                    type="text"
                    class="umi-history-search"
                    placeholder="🔍 Search prompts..."
                    style="width: 100%; padding: 8px; background: #2c2c2c; border: 1px solid #555; border-radius: 4px; color: #abb2bf; font-size: 14px; margin-bottom: 10px;"
                />
                <div style="display: flex; gap: 10px;">
                    <button class="umi-export-history" style="
                        flex: 1;
                        padding: 8px;
                        background: #56b6c2;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 13px;
                    ">📤 Export JSON</button>
                    <button class="umi-clear-history" style="
                        flex: 1;
                        padding: 8px;
                        background: #e06c75;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 13px;
                    ">🗑️ Clear All</button>
                </div>
            </div>

            <div class="umi-history-list" style="
                padding: 15px;
                overflow-y: auto;
                flex: 1;
            "></div>

            <div style="padding: 10px; border-top: 1px solid #444; background: #252525; display: flex; justify-content: space-between; align-items: center;">
                <div style="color: #888; font-size: 11px;">
                    <span class="umi-history-count">0 entries</span>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="umi-prev-page" style="padding: 5px 10px; background: #444; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 12px;">← Prev</button>
                    <span class="umi-page-indicator" style="color: #888; font-size: 12px; line-height: 30px;">Page 1</span>
                    <button class="umi-next-page" style="padding: 5px 10px; background: #444; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 12px;">Next →</button>
                </div>
            </div>
        `;

        // Event listeners
        const closeBtn = panel.querySelector(".umi-close-btn");
        closeBtn.addEventListener("click", () => this.hide());

        const searchInput = panel.querySelector(".umi-history-search");
        searchInput.addEventListener("input", (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.currentPage = 0;
            this.renderHistory();
        });

        const exportBtn = panel.querySelector(".umi-export-history");
        exportBtn.addEventListener("click", () => this.exportHistory());

        const clearBtn = panel.querySelector(".umi-clear-history");
        clearBtn.addEventListener("click", () => this.clearHistory());

        const prevBtn = panel.querySelector(".umi-prev-page");
        prevBtn.addEventListener("click", () => {
            if (this.currentPage > 0) {
                this.currentPage--;
                this.renderHistory();
            }
        });

        const nextBtn = panel.querySelector(".umi-next-page");
        nextBtn.addEventListener("click", () => {
            const filtered = this.getFilteredHistory();
            const maxPage = Math.ceil(filtered.length / this.pageSize) - 1;
            if (this.currentPage < maxPage) {
                this.currentPage++;
                this.renderHistory();
            }
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

    getFilteredHistory() {
        if (!this.searchTerm) return this.history;

        return this.history.filter(entry => {
            const prompt = (entry.prompt || "").toLowerCase();
            const negative = (entry.negative || "").toLowerCase();
            return prompt.includes(this.searchTerm) || negative.includes(this.searchTerm);
        });
    }

    renderHistory() {
        const listDiv = this.element.querySelector(".umi-history-list");
        const countSpan = this.element.querySelector(".umi-history-count");
        const pageIndicator = this.element.querySelector(".umi-page-indicator");

        if (!listDiv) return;

        const filtered = this.getFilteredHistory();
        countSpan.textContent = `${filtered.length} entries`;

        if (filtered.length === 0) {
            listDiv.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">No history found</div>';
            return;
        }

        const start = this.currentPage * this.pageSize;
        const end = start + this.pageSize;
        const paginated = filtered.slice(start, end);

        const totalPages = Math.ceil(filtered.length / this.pageSize);
        pageIndicator.textContent = `Page ${this.currentPage + 1} of ${totalPages}`;

        listDiv.innerHTML = paginated.map(entry => this.createHistoryCard(entry)).join("");

        // Add click handlers
        listDiv.querySelectorAll(".umi-history-card").forEach((card, index) => {
            card.addEventListener("click", () => {
                this.restorePrompt(paginated[index]);
            });
        });

        // Add copy handlers
        listDiv.querySelectorAll(".umi-copy-prompt").forEach((btn, index) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const text = paginated[index].prompt || "";
                navigator.clipboard.writeText(text);
                this.showNotification("✓ Copied to clipboard");
            });
        });
    }

    createHistoryCard(entry) {
        const date = new Date(entry.timestamp || Date.now());
        const dateStr = date.toLocaleString();
        const prompt = entry.prompt || "";
        const negative = entry.negative || "";
        const truncatedPrompt = prompt.length > 100 ? prompt.substring(0, 100) + "..." : prompt;
        const truncatedNegative = negative.length > 60 ? negative.substring(0, 60) + "..." : negative;

        return `
            <div class="umi-history-card" style="
                background: #2c2c2c;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 12px;
                margin-bottom: 10px;
                cursor: pointer;
                transition: all 0.2s;
            " onmouseover="this.style.borderColor='#61afef'; this.style.transform='translateX(4px)'" onmouseout="this.style.borderColor='#444'; this.style.transform='translateX(0)'">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                    <div style="color: #666; font-size: 11px;">
                        📅 ${dateStr}
                    </div>
                    <button class="umi-copy-prompt" style="
                        background: #56b6c2;
                        color: white;
                        border: none;
                        padding: 3px 8px;
                        border-radius: 3px;
                        cursor: pointer;
                        font-size: 11px;
                    ">Copy</button>
                </div>
                <div style="color: #98c379; font-size: 13px; margin-bottom: 6px; line-height: 1.4;">
                    <strong>Prompt:</strong> ${truncatedPrompt}
                </div>
                ${negative ? `<div style="color: #e06c75; font-size: 12px; line-height: 1.3;">
                    <strong>Negative:</strong> ${truncatedNegative}
                </div>` : ''}
                ${entry.seed !== undefined ? `<div style="color: #666; font-size: 11px; margin-top: 6px;">
                    🎲 Seed: ${entry.seed}
                </div>` : ''}
            </div>
        `;
    }

    restorePrompt(entry) {
        const activeNode = this.findActiveUmiNode();
        if (!activeNode) {
            this.showNotification("No active Umi node found. Please select a node first.", true);
            return;
        }

        // Set positive prompt
        const promptWidget = activeNode.widgets.find(w => w.name === "input_prompt");
        if (promptWidget && entry.prompt) {
            promptWidget.value = entry.prompt;
            if (promptWidget.callback) {
                promptWidget.callback(entry.prompt);
            }
        }

        // Set negative prompt
        if (entry.negative) {
            const negWidget = activeNode.widgets.find(w => w.name === "input_negative");
            if (negWidget) {
                negWidget.value = entry.negative;
                if (negWidget.callback) {
                    negWidget.callback(entry.negative);
                }
            }
        }

        // Set seed if available
        if (entry.seed !== undefined) {
            const seedWidget = activeNode.widgets.find(w => w.name === "seed");
            if (seedWidget) {
                seedWidget.value = entry.seed;
                if (seedWidget.callback) {
                    seedWidget.callback(entry.seed);
                }
            }
        }

        this.showNotification("✓ Prompt restored");
        this.hide();
    }

    findActiveUmiNode() {
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

    async show() {
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = "flex";
        await this.loadHistory();
        this.currentPage = 0;
        this.renderHistory();
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

// Global instance
const historyBrowser = new HistoryBrowser();

// Register extension
app.registerExtension({
    name: "Umi.HistoryBrowser",

    async setup() {
        // Add menu item
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "📜 History";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => historyBrowser.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+H)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "h") {
                e.preventDefault();
                historyBrowser.show();
            }
        });
    }
});
