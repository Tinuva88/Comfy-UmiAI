import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

class YAMLManager {
    constructor() {
        this.element = null;
        this.stats = null;
        this.tagData = null;
        this.searchTerm = "";
        this.mode = "tags";
        this.selectedTag = null;
        this.selectedEntry = null;
        this.importResult = null;
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

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-yaml-manager";
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
                .umi-ym-root { display: flex; flex-direction: column; height: 100%; width: 100%; }
                .umi-ym-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid #20242c; background: linear-gradient(135deg, #1d2230 0%, #151a24 100%); }
                .umi-ym-title { font-size: 18px; font-weight: 600; color: #8fc6ff; }
                .umi-ym-actions { display: flex; gap: 8px; align-items: center; }
                .umi-ym-btn { background: #2a303b; color: #d7dae0; border: 1px solid #3b4250; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; }
                .umi-ym-btn:hover { border-color: #5b6b85; }
                .umi-ym-select { background: #1c212b; color: #d7dae0; border: 1px solid #3b4250; padding: 6px 8px; border-radius: 6px; font-size: 12px; }
                .umi-ym-body { display: grid; grid-template-columns: 260px minmax(0, 1fr) 360px; height: 100%; width: 100%; flex: 1; min-height: 0; }
                .umi-ym-sidebar { border-right: 1px solid #20242c; padding: 14px; overflow-y: auto; background: #12161f; min-width: 0; }
                .umi-ym-main { position: relative; overflow: hidden; display: flex; flex-direction: column; min-width: 0; }
                .umi-ym-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; padding: 14px; overflow-y: auto; height: 100%; min-height: 0; }
                .umi-ym-details { border-left: 1px solid #20242c; padding: 14px; overflow-y: auto; background: #12161f; min-width: 0; }
                .umi-ym-section { margin-bottom: 16px; }
                .umi-ym-section-title { font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: #8b93a6; margin-bottom: 8px; }
                .umi-ym-input { width: 100%; padding: 6px 8px; background: #1c212b; border: 1px solid #313847; border-radius: 6px; color: #d7dae0; font-size: 12px; }
                .umi-ym-card { background: #1a1f2b; border: 1px solid #2a303b; border-radius: 8px; padding: 10px; cursor: pointer; transition: transform 0.1s ease, border-color 0.1s ease; }
                .umi-ym-card:hover { border-color: #4c6b9a; transform: translateY(-2px); }
                .umi-ym-card.selected { border-color: #8fc6ff; box-shadow: 0 0 0 1px #8fc6ff inset; }
                .umi-ym-card-title { font-size: 12px; color: #c7cbd6; font-weight: 600; }
                .umi-ym-card-sub { font-size: 10px; color: #7b8499; margin-top: 4px; }
                .umi-ym-details-empty { color: #7b8499; text-align: center; padding: 20px; font-size: 12px; }
                .umi-ym-detail-section { margin-bottom: 12px; }
                .umi-ym-detail-label { font-size: 11px; color: #8b93a6; margin-bottom: 4px; }
                .umi-ym-detail-box { background: #1c212b; border: 1px solid #2a303b; border-radius: 6px; padding: 8px; font-size: 12px; color: #d7dae0; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }
                .umi-ym-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; background: #1c212b; border: 1px solid #2a303b; padding: 4px 8px; border-radius: 6px; }
                .umi-ym-stat { display: grid; grid-template-columns: 1fr auto; gap: 6px; font-size: 12px; margin-bottom: 6px; color: #c1c7d4; }
                .umi-ym-textarea { width: 100%; min-height: 120px; padding: 8px; background: #1c212b; border: 1px solid #313847; border-radius: 6px; color: #d7dae0; font-size: 12px; }
            </style>
            <div class="umi-ym-root">
                <div class="umi-ym-header">
                    <div class="umi-ym-title">YAML Tag Manager</div>
                    <div class="umi-ym-actions">
                        <select class="umi-ym-select" data-role="mode">
                            <option value="tags" selected>Tags</option>
                            <option value="entries">Entries</option>
                        </select>
                        <button class="umi-ym-btn" data-action="refresh">Refresh</button>
                        <button class="umi-ym-btn" data-action="close">Close</button>
                    </div>
                </div>
                <div class="umi-ym-body">
                    <aside class="umi-ym-sidebar">
                        <div class="umi-ym-section">
                            <div class="umi-ym-section-title">Search</div>
                            <input class="umi-ym-input" data-role="search" placeholder="Search tags or entries" />
                        </div>
                        <div class="umi-ym-section">
                            <div class="umi-ym-section-title">Stats</div>
                            <div class="umi-ym-stats"></div>
                        </div>
                        <div class="umi-ym-section">
                            <div class="umi-ym-section-title">Export</div>
                            <button class="umi-ym-btn" data-action="export-json">Export JSON</button>
                            <button class="umi-ym-btn" data-action="export-csv" style="margin-left:8px;">Export CSV</button>
                        </div>
                        <div class="umi-ym-section">
                            <div class="umi-ym-section-title">Import CSV</div>
                            <textarea class="umi-ym-textarea" data-role="import-csv" placeholder="entry_name,tag1,tag2"></textarea>
                            <div style="margin-top:8px;">
                                <button class="umi-ym-btn" data-action="parse-import">Parse</button>
                            </div>
                        </div>
                    </aside>
                    <main class="umi-ym-main">
                        <div class="umi-ym-list" data-role="list"></div>
                    </main>
                    <aside class="umi-ym-details" data-role="details">
                        <div class="umi-ym-details-empty">Select a tag or entry to view details.</div>
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
        refreshBtn.addEventListener('click', () => this.loadData());

        const modeSelect = this.element.querySelector('[data-role="mode"]');
        modeSelect.addEventListener('change', (e) => {
            this.mode = e.target.value;
            this.selectedTag = null;
            this.selectedEntry = null;
            this.renderList();
            this.renderDetails();
        });

        const searchInput = this.element.querySelector('[data-role="search"]');
        searchInput.addEventListener('input', (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.renderList();
        });

        const exportJsonBtn = this.element.querySelector('[data-action="export-json"]');
        exportJsonBtn.addEventListener('click', () => this.exportToJSON());

        const exportCsvBtn = this.element.querySelector('[data-action="export-csv"]');
        exportCsvBtn.addEventListener('click', () => this.exportToCSV());

        const parseImportBtn = this.element.querySelector('[data-action="parse-import"]');
        parseImportBtn.addEventListener('click', () => this.parseImport());
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
            this.showNotification("Exported JSON");
        } catch (error) {
            this.showNotification(`Export failed: ${error.message}`, true);
        }
    }

    async exportToCSV() {
        try {
            if (!this.tagData) {
                await this.loadTags();
            }

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
            this.showNotification("Exported CSV");
        } catch (error) {
            this.showNotification(`Export failed: ${error.message}`, true);
        }
    }

    async parseImport() {
        const textarea = this.element.querySelector('[data-role="import-csv"]');
        if (!textarea) return;
        const csvData = textarea.value.trim();
        if (!csvData) {
            this.showNotification("Paste CSV data first", true);
            return;
        }
        try {
            const response = await fetch("/umiapp/yaml/tags/import", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ csv_data: csvData })
            });
            this.importResult = await response.json();
            this.renderDetails();
        } catch (error) {
            this.showNotification(`Import failed: ${error.message}`, true);
        }
    }

    renderStats() {
        const statsContainer = this.element.querySelector(".umi-ym-stats");
        if (!statsContainer || !this.stats) return;

        const stats = [
            ["Total Entries", this.stats.total_entries],
            ["Unique Tags", this.stats.total_unique_tags],
            ["With Tags", this.stats.entries_with_tags],
            ["Without Tags", this.stats.entries_without_tags],
            ["Avg Tags/Entry", this.stats.average_tags_per_entry]
        ];

        statsContainer.innerHTML = stats.map(([label, value]) => `
            <div class="umi-ym-stat">
                <div>${label}</div>
                <div>${value}</div>
            </div>
        `).join("");
    }

    getTagsArray() {
        const tagsObj = (this.tagData && this.tagData.tags) ? this.tagData.tags : {};
        return Object.keys(tagsObj).map(name => ({
            name,
            count: tagsObj[name].count,
            entries: tagsObj[name].entries || []
        }));
    }

    getEntriesArray() {
        return (this.tagData && this.tagData.entries) ? this.tagData.entries : [];
    }

    applySearch(list) {
        if (!this.searchTerm) return list;
        const term = this.searchTerm;
        if (this.mode === "tags") {
            return list.filter(tag => tag.name.toLowerCase().includes(term));
        }
        return list.filter(entry => {
            const name = entry.name.toLowerCase();
            const tags = (entry.tags || []).join(" ").toLowerCase();
            return name.includes(term) || tags.includes(term);
        });
    }

    renderList() {
        const listEl = this.element.querySelector('[data-role="list"]');
        if (!listEl || !this.tagData) return;

        if (this.mode === "tags") {
            const tags = this.applySearch(this.getTagsArray());
            if (!tags.length) {
                listEl.innerHTML = '<div class="umi-ym-details-empty">No tags found</div>';
                return;
            }
            listEl.innerHTML = tags.map(tag => {
                const selected = this.selectedTag && this.selectedTag.name === tag.name ? "selected" : "";
                return `
                    <div class="umi-ym-card ${selected}" data-tag="${this.escapeHtmlAttr(tag.name)}">
                        <div class="umi-ym-card-title">#${this.escapeHtml(tag.name)}</div>
                        <div class="umi-ym-card-sub">${tag.count} entries</div>
                    </div>
                `;
            }).join("");

            listEl.querySelectorAll('.umi-ym-card').forEach(card => {
                card.addEventListener('click', () => {
                    const tagName = card.dataset.tag;
                    this.selectedTag = this.getTagsArray().find(tag => tag.name === tagName) || null;
                    this.selectedEntry = null;
                    this.renderDetails();
                    this.renderList();
                });
            });
        } else {
            const entries = this.applySearch(this.getEntriesArray());
            if (!entries.length) {
                listEl.innerHTML = '<div class="umi-ym-details-empty">No entries found</div>';
                return;
            }
            listEl.innerHTML = entries.map(entry => {
                const selected = this.selectedEntry && this.selectedEntry.name === entry.name ? "selected" : "";
                const tagCount = (entry.tags || []).length;
                return `
                    <div class="umi-ym-card ${selected}" data-entry="${this.escapeHtmlAttr(entry.name)}">
                        <div class="umi-ym-card-title">${this.escapeHtml(entry.name)}</div>
                        <div class="umi-ym-card-sub">${tagCount} tags</div>
                    </div>
                `;
            }).join("");

            listEl.querySelectorAll('.umi-ym-card').forEach(card => {
                card.addEventListener('click', () => {
                    const entryName = card.dataset.entry;
                    this.selectedEntry = this.getEntriesArray().find(entry => entry.name === entryName) || null;
                    this.selectedTag = null;
                    this.renderDetails();
                    this.renderList();
                });
            });
        }
    }

    renderDetails() {
        const details = this.element.querySelector('[data-role="details"]');
        if (!details) return;

        if (this.importResult) {
            const updates = this.importResult.updates || [];
            details.innerHTML = `
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Import Preview</div>
                    <div class="umi-ym-detail-box">${this.escapeHtml(JSON.stringify(updates.slice(0, 50), null, 2))}</div>
                </div>
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Note</div>
                    <div class="umi-ym-detail-box">${this.escapeHtml(this.importResult.note || "")}</div>
                </div>
            `;
            return;
        }

        if (this.selectedTag) {
            const entries = this.selectedTag.entries || [];
            details.innerHTML = `
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Tag</div>
                    <div class="umi-ym-detail-box">#${this.escapeHtml(this.selectedTag.name)}</div>
                </div>
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Entries (${entries.length})</div>
                    <div class="umi-ym-detail-box">${this.escapeHtml(entries.join(", "))}</div>
                </div>
            `;
            return;
        }

        if (this.selectedEntry) {
            const tags = (this.selectedEntry.tags || []).join(", ");
            const prompts = (this.selectedEntry.prompts || []).slice(0, 6).join("\n");
            details.innerHTML = `
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Entry</div>
                    <div class="umi-ym-detail-box">${this.escapeHtml(this.selectedEntry.name)}</div>
                </div>
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Tags</div>
                    <div class="umi-ym-detail-box">${this.escapeHtml(tags || "None")}</div>
                </div>
                <div class="umi-ym-detail-section">
                    <div class="umi-ym-detail-label">Prompts</div>
                    <div class="umi-ym-detail-box">${this.escapeHtml(prompts || "None")}</div>
                </div>
            `;
            return;
        }

        details.innerHTML = '<div class="umi-ym-details-empty">Select a tag or entry to view details.</div>';
    }

    async loadData() {
        await Promise.all([this.loadStats(), this.loadTags()]);
        this.renderStats();
        this.renderList();
        this.renderDetails();
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
            .replace(/'/g, "&#039;");
    }

    async show() {
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = "block";
        await this.loadData();
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
        }
    }
}

const yamlManager = new YAMLManager();

app.registerExtension({
    name: "Umi.YAMLManager",

    async setup() {
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "YAML Tags";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => yamlManager.show();
            menu.appendChild(button);
        }

        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "y") {
                e.preventDefault();
                yamlManager.show();
            }
        });
    }
});
