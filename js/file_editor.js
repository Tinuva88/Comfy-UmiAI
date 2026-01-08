import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Phase 8: File Editor - Edit wildcards and YAML files in-app

class FileEditor {
    constructor() {
        this.element = null;
        this.currentFile = null;
        this.currentContent = "";
        this.files = [];
        this.hasUnsavedChanges = false;
    }

    async loadFileList() {
        try {
            const response = await fetch("/umiapp/files/list");
            const data = await response.json();
            this.files = data.files || [];
            return this.files;
        } catch (error) {
            console.error("[Umi File Editor] Failed to load file list:", error);
            return [];
        }
    }

    async loadFile(filepath) {
        try {
            const response = await fetch("/umiapp/files/read", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filepath })
            });
            const data = await response.json();

            if (data.success) {
                this.currentFile = filepath;
                this.currentContent = data.content;
                this.hasUnsavedChanges = false;
                return data.content;
            } else {
                this.showNotification(`✗ Error: ${data.error}`, true);
                return null;
            }
        } catch (error) {
            this.showNotification(`✗ Failed to load file: ${error.message}`, true);
            return null;
        }
    }

    async saveFile() {
        if (!this.currentFile) {
            this.showNotification("No file loaded", true);
            return false;
        }

        try {
            const editor = this.element.querySelector(".umi-editor-textarea");
            const content = editor.value;

            const response = await fetch("/umiapp/files/write", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filepath: this.currentFile,
                    content: content
                })
            });

            const data = await response.json();

            if (data.success) {
                this.currentContent = content;
                this.hasUnsavedChanges = false;
                this.updateSaveIndicator();
                this.showNotification("✓ File saved");
                return true;
            } else {
                this.showNotification(`✗ Error: ${data.error}`, true);
                return false;
            }
        } catch (error) {
            this.showNotification(`✗ Save failed: ${error.message}`, true);
            return false;
        }
    }

    async createNewFile() {
        const filename = prompt("Enter filename (with extension .txt or .yaml):");
        if (!filename) return;

        if (!filename.endsWith('.txt') && !filename.endsWith('.yaml')) {
            this.showNotification("Filename must end with .txt or .yaml", true);
            return;
        }

        try {
            const response = await fetch("/umiapp/files/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename })
            });

            const data = await response.json();

            if (data.success) {
                await this.loadFileList();
                this.renderFileList();
                await this.loadFile(data.filepath);
                this.renderEditor();
                this.showNotification(`✓ Created ${filename}`);
            } else {
                this.showNotification(`✗ Error: ${data.error}`, true);
            }
        } catch (error) {
            this.showNotification(`✗ Create failed: ${error.message}`, true);
        }
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-file-editor";
        panel.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: #1e1e1e;
            z-index: 10000;
            display: none;
            flex-direction: row;
        `;

        panel.innerHTML = `
            <div class="umi-file-sidebar" style="
                width: 280px;
                border-right: 1px solid #444;
                display: flex;
                flex-direction: column;
            ">
                <div style="padding: 15px; border-bottom: 1px solid #444;">
                    <h2 style="margin: 0 0 12px 0; color: #61afef; font-size: 16px;">📁 Files</h2>
                    <button class="umi-new-file-btn" style="
                        width: 100%;
                        padding: 8px;
                        background: #98c379;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 13px;
                        font-weight: 600;
                    ">+ New File</button>
                </div>
                <div class="umi-file-list" style="
                    flex: 1;
                    overflow-y: auto;
                    padding: 10px;
                "></div>
            </div>

            <div class="umi-editor-container" style="
                flex: 1;
                display: flex;
                flex-direction: column;
            ">
                <div style="padding: 12px 15px; border-bottom: 1px solid #444; display: flex; justify-content: space-between; align-items: center; background: #252525;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span class="umi-current-file" style="color: #61afef; font-size: 14px; font-weight: 600;">No file selected</span>
                        <span class="umi-save-indicator" style="color: #888; font-size: 12px;"></span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="umi-save-btn" style="
                            padding: 6px 16px;
                            background: #56b6c2;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 13px;
                            font-weight: 600;
                        ">💾 Save (Ctrl+S)</button>
                        <button class="umi-close-editor-btn" style="
                            padding: 6px 12px;
                            background: #e06c75;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 14px;
                        ">✕ Close</button>
                    </div>
                </div>

                <textarea class="umi-editor-textarea" style="
                    flex: 1;
                    padding: 20px;
                    background: #1e1e1e;
                    color: #abb2bf;
                    border: none;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 14px;
                    line-height: 1.6;
                    resize: none;
                    outline: none;
                " placeholder="Select a file from the sidebar or create a new one..."></textarea>

                <div style="padding: 8px 15px; border-top: 1px solid #444; background: #252525; display: flex; justify-content: space-between; color: #888; font-size: 11px;">
                    <span class="umi-editor-info">Ready</span>
                    <span class="umi-editor-stats"></span>
                </div>
            </div>
        `;

        // Event listeners
        const newFileBtn = panel.querySelector(".umi-new-file-btn");
        newFileBtn.addEventListener("click", () => this.createNewFile());

        const saveBtn = panel.querySelector(".umi-save-btn");
        saveBtn.addEventListener("click", () => this.saveFile());

        const closeBtn = panel.querySelector(".umi-close-editor-btn");
        closeBtn.addEventListener("click", () => this.hide());

        const editor = panel.querySelector(".umi-editor-textarea");
        editor.addEventListener("input", () => {
            this.hasUnsavedChanges = true;
            this.updateSaveIndicator();
            this.updateStats();
        });

        // Keyboard shortcuts
        document.addEventListener("keydown", (e) => {
            if (panel.style.display === "flex") {
                if (e.ctrlKey && e.key === "s") {
                    e.preventDefault();
                    this.saveFile();
                }
            }
        });

        this.element = panel;
        document.body.appendChild(panel);
    }

    renderFileList() {
        const fileList = this.element.querySelector(".umi-file-list");
        if (!fileList) return;

        if (this.files.length === 0) {
            fileList.innerHTML = '<div style="text-align: center; color: #888; padding: 20px; font-size: 12px;">No wildcard files found</div>';
            return;
        }

        // Group by extension
        const txtFiles = this.files.filter(f => f.endsWith('.txt'));
        const yamlFiles = this.files.filter(f => f.endsWith('.yaml'));

        let html = "";

        if (yamlFiles.length > 0) {
            html += '<div style="margin-bottom: 15px;">';
            html += '<div style="color: #98c379; font-size: 12px; font-weight: 600; margin-bottom: 6px; padding: 0 8px;">YAML Files</div>';
            html += yamlFiles.map(file => this.createFileItem(file, "yaml")).join("");
            html += '</div>';
        }

        if (txtFiles.length > 0) {
            html += '<div>';
            html += '<div style="color: #56b6c2; font-size: 12px; font-weight: 600; margin-bottom: 6px; padding: 0 8px;">Text Files</div>';
            html += txtFiles.map(file => this.createFileItem(file, "txt")).join("");
            html += '</div>';
        }

        fileList.innerHTML = html;

        // Add click handlers
        fileList.querySelectorAll(".umi-file-item").forEach(item => {
            item.addEventListener("click", async () => {
                const filepath = item.dataset.filepath;

                if (this.hasUnsavedChanges) {
                    if (!confirm("You have unsaved changes. Discard them?")) {
                        return;
                    }
                }

                await this.loadFile(filepath);
                this.renderEditor();

                // Highlight selected file
                fileList.querySelectorAll(".umi-file-item").forEach(i => {
                    i.style.background = "#2c2c2c";
                    i.style.borderColor = "#444";
                });
                item.style.background = "#3e4451";
                item.style.borderColor = "#61afef";
            });
        });
    }

    createFileItem(filepath, type) {
        const filename = filepath.split('/').pop().split('\\').pop();
        const icon = type === "yaml" ? "📋" : "📄";
        const color = type === "yaml" ? "#98c379" : "#56b6c2";

        return `
            <div class="umi-file-item" data-filepath="${filepath}" style="
                padding: 8px 12px;
                margin-bottom: 4px;
                background: #2c2c2c;
                border: 1px solid #444;
                border-radius: 4px;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
            " onmouseover="this.style.borderColor='#61afef'" onmouseout="if(this.style.background!='rgb(62, 68, 81)') this.style.borderColor='#444'">
                <span style="font-size: 16px;">${icon}</span>
                <span style="color: ${color}; font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${filename}</span>
            </div>
        `;
    }

    renderEditor() {
        const editor = this.element.querySelector(".umi-editor-textarea");
        const currentFileSpan = this.element.querySelector(".umi-current-file");

        if (this.currentFile) {
            const filename = this.currentFile.split('/').pop().split('\\').pop();
            currentFileSpan.textContent = filename;
            editor.value = this.currentContent;
            editor.disabled = false;
            this.updateStats();
        } else {
            currentFileSpan.textContent = "No file selected";
            editor.value = "";
            editor.disabled = true;
        }

        this.updateSaveIndicator();
    }

    updateSaveIndicator() {
        const indicator = this.element.querySelector(".umi-save-indicator");
        if (this.hasUnsavedChanges) {
            indicator.textContent = "● Unsaved changes";
            indicator.style.color = "#e5c07b";
        } else if (this.currentFile) {
            indicator.textContent = "✓ Saved";
            indicator.style.color = "#98c379";
        } else {
            indicator.textContent = "";
        }
    }

    updateStats() {
        const editor = this.element.querySelector(".umi-editor-textarea");
        const statsSpan = this.element.querySelector(".umi-editor-stats");

        const content = editor.value;
        const lines = content.split('\n').length;
        const chars = content.length;
        const words = content.trim() ? content.trim().split(/\s+/).length : 0;

        statsSpan.textContent = `Lines: ${lines} | Words: ${words} | Characters: ${chars}`;
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
        await this.loadFileList();
        this.renderFileList();
    }

    hide() {
        if (this.hasUnsavedChanges) {
            if (!confirm("You have unsaved changes. Close anyway?")) {
                return;
            }
        }

        if (this.element) {
            this.element.style.display = "none";
            this.currentFile = null;
            this.currentContent = "";
            this.hasUnsavedChanges = false;
        }
    }
}

// Global instance
const fileEditor = new FileEditor();

// Register extension
app.registerExtension({
    name: "Umi.FileEditor",

    async setup() {
        // Add menu item
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "📝 Editor";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => fileEditor.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+E)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "e") {
                e.preventDefault();
                fileEditor.show();
            }
        });
    }
});
