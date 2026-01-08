import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Phase 8: YAML Tag Manager - Export/import and manage YAML tags

class YAMLManager {
    constructor() {
        this.element = null;
        this.stats = null;
        this.tagData = null;
    }

    async loadStats() {
        try {
            const response = await fetch("/umiapp/yaml/stats");
            this.stats = await response.json();
            return this.stats;
        } catch (error) {
            console.error("[Umi YAML Manager] Failed to load stats:", error);
            return null;
        }
    }

    async loadTags() {
        try {
            const response = await fetch("/umiapp/yaml/tags");
            this.tagData = await response.json();
            return this.tagData;
        } catch (error) {
            console.error("[Umi YAML Manager] Failed to load tags:", error);
            return null;
        }
    }

    async exportToJSON() {
        try {
            if (!this.tagData) {
                await this.loadTags();
            }

            const data = JSON.stringify(this.tagData, null, 2);
            const blob = new Blob([data], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `umi_yaml_tags_${new Date().toISOString().split('T')[0]}.json`;
            a.click();
            URL.revokeObjectURL(url);
            this.showNotification("✓ Tags exported to JSON");
        } catch (error) {
            this.showNotification(`✗ Export failed: ${error.message}`, true);
        }
    }

    async exportToCSV() {
        try {
            if (!this.tagData) {
                await this.loadTags();
            }

            // Create CSV: entry_name, tag1, tag2, tag3...
            let csv = "Entry Name,Tags\n";
            for (const entry of this.tagData.entries) {
                const tags = entry.tags.join(",");
                csv += `"${entry.name}","${tags}"\n`;
            }

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `umi_yaml_tags_${new Date().toISOString().split('T')[0]}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            this.showNotification("✓ Tags exported to CSV");
        } catch (error) {
            this.showNotification(`✗ Export failed: ${error.message}`, true);
        }
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-yaml-manager";
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
                <h2 style="margin: 0; color: #61afef; font-size: 18px;">🏷️ YAML Tag Manager</h2>
                <button class="umi-close-btn" style="background: #e06c75; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 16px;">✕</button>
            </div>

            <div class="umi-yaml-content" style="
                padding: 20px;
                overflow-y: auto;
                flex: 1;
            ">
                <div class="umi-stats-section" style="margin-bottom: 25px;">
                    <h3 style="color: #98c379; font-size: 15px; margin-bottom: 12px;">📊 Statistics</h3>
                    <div class="umi-stats-grid" style="
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                        gap: 12px;
                        margin-bottom: 15px;
                    "></div>
                </div>

                <div class="umi-actions-section" style="margin-bottom: 25px;">
                    <h3 style="color: #98c379; font-size: 15px; margin-bottom: 12px;">⚡ Actions</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <button class="umi-export-json" style="
                            padding: 12px;
                            background: #56b6c2;
                            color: white;
                            border: none;
                            border-radius: 6px;
                            cursor: pointer;
                            font-size: 13px;
                            font-weight: 600;
                        ">📥 Export to JSON</button>
                        <button class="umi-export-csv" style="
                            padding: 12px;
                            background: #98c379;
                            color: white;
                            border: none;
                            border-radius: 6px;
                            cursor: pointer;
                            font-size: 13px;
                            font-weight: 600;
                        ">📊 Export to CSV</button>
                    </div>
                </div>

                <div class="umi-top-tags-section">
                    <h3 style="color: #98c379; font-size: 15px; margin-bottom: 12px;">🔥 Top Tags</h3>
                    <div class="umi-top-tags-list" style="
                        display: grid;
                        gap: 8px;
                    "></div>
                </div>
            </div>

            <div style="padding: 10px; border-top: 1px solid #444; background: #252525; color: #888; font-size: 11px; text-align: center;">
                Export your YAML tags for documentation or batch editing
            </div>
        `;

        // Event listeners
        const closeBtn = panel.querySelector(".umi-close-btn");
        closeBtn.addEventListener("click", () => this.hide());

        const exportJsonBtn = panel.querySelector(".umi-export-json");
        exportJsonBtn.addEventListener("click", () => this.exportToJSON());

        const exportCsvBtn = panel.querySelector(".umi-export-csv");
        exportCsvBtn.addEventListener("click", () => this.exportToCSV());

        // Close on background click
        panel.addEventListener("click", (e) => {
            if (e.target === panel) {
                this.hide();
            }
        });

        this.element = panel;
        document.body.appendChild(panel);
    }

    renderStats() {
        if (!this.stats) return;

        const statsGrid = this.element.querySelector(".umi-stats-grid");
        if (!statsGrid) return;

        const statCards = [
            { label: "Total Entries", value: this.stats.total_entries, icon: "📝" },
            { label: "Unique Tags", value: this.stats.total_unique_tags, icon: "🏷️" },
            { label: "With Tags", value: this.stats.entries_with_tags, icon: "✓" },
            { label: "Without Tags", value: this.stats.entries_without_tags, icon: "✗" },
            { label: "Avg Tags/Entry", value: this.stats.average_tags_per_entry, icon: "📊" }
        ];

        statsGrid.innerHTML = statCards.map(stat => `
            <div style="
                background: #2c2c2c;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 12px;
                text-align: center;
            ">
                <div style="font-size: 24px; margin-bottom: 6px;">${stat.icon}</div>
                <div style="font-size: 20px; font-weight: 600; color: #61afef; margin-bottom: 4px;">
                    ${stat.value}
                </div>
                <div style="font-size: 11px; color: #888;">
                    ${stat.label}
                </div>
            </div>
        `).join("");
    }

    renderTopTags() {
        if (!this.stats || !this.stats.top_tags) return;

        const tagsList = this.element.querySelector(".umi-top-tags-list");
        if (!tagsList) return;

        tagsList.innerHTML = this.stats.top_tags.map((item, index) => {
            const percentage = (item.count / this.stats.total_entries * 100).toFixed(1);
            return `
                <div style="
                    background: #2c2c2c;
                    border: 1px solid #444;
                    border-radius: 6px;
                    padding: 10px 12px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                ">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="
                            width: 24px;
                            height: 24px;
                            background: #3e4451;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 11px;
                            color: #61afef;
                            font-weight: 600;
                        ">${index + 1}</span>
                        <span style="color: #abb2bf; font-size: 13px; font-weight: 500;">${item.tag}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="
                            background: #3e4451;
                            border-radius: 4px;
                            height: 6px;
                            width: 100px;
                            overflow: hidden;
                        ">
                            <div style="
                                background: linear-gradient(90deg, #61afef, #98c379);
                                height: 100%;
                                width: ${percentage}%;
                            "></div>
                        </div>
                        <span style="color: #98c379; font-size: 12px; font-weight: 600; min-width: 60px; text-align: right;">
                            ${item.count} (${percentage}%)
                        </span>
                    </div>
                </div>
            `;
        }).join("");
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

        // Load data
        await this.loadStats();
        await this.loadTags();

        // Render
        this.renderStats();
        this.renderTopTags();
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

// Global instance
const yamlManager = new YAMLManager();

// Register extension
app.registerExtension({
    name: "Umi.YAMLManager",

    async setup() {
        // Add menu item
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "🏷️ YAML Tags";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => yamlManager.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+Y)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "y") {
                e.preventDefault();
                yamlManager.show();
            }
        });
    }
});
