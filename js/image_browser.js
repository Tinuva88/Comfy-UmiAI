import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Phase 6: Image Browser - Booru-style image gallery with metadata and prompt copying

class ImageBrowser {
    constructor() {
        this.element = null;
        this.images = [];
        this.currentPage = 0;
        this.pageSize = 50;
        this.totalImages = 0;
        this.sortBy = "newest";
        this.searchTerm = "";
        this.dateFilter = "all";
        this.dateFrom = "";
        this.dateTo = "";
        this.selectedImage = null;
    }

    async fetchImages() {
        try {
            const offset = this.currentPage * this.pageSize;
            const response = await fetch(`/umiapp/images/scan?limit=${this.pageSize}&offset=${offset}&sort=${this.sortBy}`);
            const data = await response.json();

            this.images = data.images || [];
            this.totalImages = data.total || 0;

            return this.images;
        } catch (error) {
            console.error("[Umi Image Browser] Failed to fetch images:", error);
            return [];
        }
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-image-browser";
        panel.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(15, 15, 18, 0.98);
            z-index: 10000;
            display: none;
            flex-direction: column;
        `;

        panel.innerHTML = `
            <div style="
                padding: 18px 24px;
                background: linear-gradient(135deg, rgba(97, 175, 239, 0.12) 0%, rgba(198, 120, 221, 0.08) 50%, rgba(86, 182, 194, 0.08) 100%);
                border-bottom: 1px solid rgba(97, 175, 239, 0.25);
                display: flex;
                justify-content: space-between;
                align-items: center;
                backdrop-filter: blur(8px);
            ">
                <h2 style="margin: 0; color: #61afef; font-size: 22px; font-weight: 600; text-shadow: 0 2px 4px rgba(0,0,0,0.4);">🖼️ Image Browser</h2>
                <div style="display: flex; gap: 12px; align-items: center;">
                    <select class="umi-sort-select" style="
                        padding: 8px 12px;
                        background: rgba(44, 44, 44, 0.8);
                        border: 1px solid rgba(85, 85, 85, 0.6);
                        border-radius: 6px;
                        color: #abb2bf;
                        cursor: pointer;
                        transition: all 0.2s ease;
                    ">
                        <option value="newest">Newest First</option>
                        <option value="oldest">Oldest First</option>
                        <option value="name">By Name</option>
                    </select>
                    <select class="umi-date-filter" style="
                        padding: 8px 12px;
                        background: rgba(44, 44, 44, 0.8);
                        border: 1px solid rgba(85, 85, 85, 0.6);
                        border-radius: 6px;
                        color: #abb2bf;
                        cursor: pointer;
                    ">
                        <option value="all">All Time</option>
                        <option value="today">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="custom">Custom Range</option>
                    </select>
                    <div class="umi-date-range" style="display: none; gap: 5px; align-items: center;">
                        <span style="color: #abb2bf; font-size: 12px;">From:</span>
                        <input type="date" class="umi-date-from" style="padding: 6px; background: #2c2c2c; border: 1px solid #555; border-radius: 4px; color: #abb2bf; font-size: 12px;" />
                        <span style="color: #abb2bf; font-size: 12px;">To:</span>
                        <input type="date" class="umi-date-to" style="padding: 6px; background: #2c2c2c; border: 1px solid #555; border-radius: 4px; color: #abb2bf; font-size: 12px;" />
                    </div>
                    <input
                        type="text"
                        class="umi-image-search"
                        placeholder="🔍 Search prompts..."
                        style="
                            padding: 8px 14px;
                            background: rgba(44, 44, 44, 0.8);
                            border: 1px solid rgba(85, 85, 85, 0.6);
                            border-radius: 6px;
                            color: #abb2bf;
                            width: 220px;
                            transition: all 0.2s ease;
                        "
                    />
                    <button class="umi-close-btn" style="
                        background: linear-gradient(135deg, #e06c75 0%, #be5046 100%);
                        color: white;
                        border: none;
                        padding: 8px 18px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 600;
                        transition: all 0.2s ease;
                        box-shadow: 0 2px 8px rgba(224, 108, 117, 0.3);
                    " onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(224, 108, 117, 0.4)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 8px rgba(224, 108, 117, 0.3)'">✕ Close</button>
                </div>
            </div>

            <div style="display: flex; flex: 1; overflow: hidden;">
                <!-- Image Grid -->
                <div class="umi-image-grid-container" style="
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                ">
                    <div class="umi-image-grid" style="
                        display: grid;
                        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                        gap: 15px;
                    "></div>

                    <!-- Pagination -->
                    <div class="umi-pagination" style="
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        gap: 10px;
                        margin-top: 20px;
                        padding: 20px;
                    "></div>
                </div>

                <!-- Image Details Sidebar -->
                <div class="umi-image-details" style="
                    width: 400px;
                    background: #1e1e1e;
                    border-left: 1px solid #444;
                    overflow-y: auto;
                    display: none;
                    flex-direction: column;
                ">
                    <div style="padding: 15px; border-bottom: 1px solid #444;">
                        <h3 style="margin: 0 0 10px 0; color: #61afef; font-size: 16px;">Image Details</h3>
                        <button class="umi-close-details" style="
                            width: 100%;
                            padding: 6px;
                            background: #e06c75;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 12px;
                        ">✕ Close Details</button>
                    </div>

                    <div class="umi-details-content" style="padding: 15px; flex: 1;"></div>
                </div>
            </div>
        `;

        // Event listeners
        const closeBtn = panel.querySelector(".umi-close-btn");
        closeBtn.addEventListener("click", () => this.hide());

        const sortSelect = panel.querySelector(".umi-sort-select");
        sortSelect.addEventListener("change", (e) => {
            this.sortBy = e.target.value;
            this.currentPage = 0;
            this.loadImages();
        });

        const dateFilter = panel.querySelector(".umi-date-filter");
        const dateRangeDiv = panel.querySelector(".umi-date-range");
        const dateFromInput = panel.querySelector(".umi-date-from");
        const dateToInput = panel.querySelector(".umi-date-to");

        dateFilter.addEventListener("change", (e) => {
            this.dateFilter = e.target.value;

            // Show/hide custom date range inputs
            if (e.target.value === "custom") {
                dateRangeDiv.style.display = "flex";
            } else {
                dateRangeDiv.style.display = "none";
                this.filterImages();
            }
        });

        dateFromInput.addEventListener("change", (e) => {
            this.dateFrom = e.target.value;
            if (this.dateFilter === "custom") {
                this.filterImages();
            }
        });

        dateToInput.addEventListener("change", (e) => {
            this.dateTo = e.target.value;
            if (this.dateFilter === "custom") {
                this.filterImages();
            }
        });

        const searchInput = panel.querySelector(".umi-image-search");
        searchInput.addEventListener("input", (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.filterImages();
        });

        const closeDetails = panel.querySelector(".umi-close-details");
        closeDetails.addEventListener("click", () => {
            panel.querySelector(".umi-image-details").style.display = "none";
        });

        // ESC key to close
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && panel.style.display === "flex") {
                if (this.selectedImage) {
                    panel.querySelector(".umi-image-details").style.display = "none";
                    this.selectedImage = null;
                } else {
                    this.hide();
                }
            }
        });

        this.element = panel;
        document.body.appendChild(panel);
    }

    async loadImages() {
        const grid = this.element.querySelector(".umi-image-grid");
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">Loading images...</div>';

        await this.fetchImages();
        this.renderImages();
        this.renderPagination();
    }

    filterImages() {
        this.renderImages();
    }

    renderImages() {
        const grid = this.element.querySelector(".umi-image-grid");

        let filtered = this.images;

        // Apply date filter
        if (this.dateFilter !== "all") {
            if (this.dateFilter === "custom") {
                // Custom date range
                if (this.dateFrom || this.dateTo) {
                    const fromTime = this.dateFrom ? new Date(this.dateFrom).getTime() / 1000 : 0;
                    const toTime = this.dateTo ? new Date(this.dateTo + "T23:59:59").getTime() / 1000 : Date.now() / 1000;

                    filtered = filtered.filter(img => {
                        if (this.dateFrom && this.dateTo) {
                            return img.mtime >= fromTime && img.mtime <= toTime;
                        } else if (this.dateFrom) {
                            return img.mtime >= fromTime;
                        } else if (this.dateTo) {
                            return img.mtime <= toTime;
                        }
                        return true;
                    });
                }
            } else {
                // Preset date filters
                const now = Date.now() / 1000; // Convert to Unix timestamp
                let cutoff = 0;

                if (this.dateFilter === "today") {
                    const today = new Date();
                    today.setHours(0, 0, 0, 0);
                    cutoff = today.getTime() / 1000;
                } else if (this.dateFilter === "week") {
                    cutoff = now - (7 * 24 * 60 * 60);
                } else if (this.dateFilter === "month") {
                    cutoff = now - (30 * 24 * 60 * 60);
                }

                filtered = filtered.filter(img => img.mtime >= cutoff);
            }
        }

        // Apply search filter
        if (this.searchTerm) {
            filtered = filtered.filter(img => {
                const prompt = img.metadata?.prompt || "";
                const negative = img.metadata?.negative || "";
                const a1111 = img.metadata?.a1111_params || "";
                return prompt.toLowerCase().includes(this.searchTerm) ||
                    negative.toLowerCase().includes(this.searchTerm) ||
                    a1111.toLowerCase().includes(this.searchTerm) ||
                    img.filename.toLowerCase().includes(this.searchTerm);
            });
        }

        if (filtered.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">No images found</div>';
            return;
        }

        grid.innerHTML = filtered.map((img, index) => this.createImageCard(img, index)).join("");

        // Add click handlers
        grid.querySelectorAll(".umi-image-card").forEach((card, index) => {
            card.addEventListener("click", () => {
                this.showImageDetails(filtered[index]);
            });
        });
    }

    createImageCard(img) {
        const hasPrompt = img.metadata?.prompt ? '✓' : '';
        const resolution = `${img.metadata?.width || '?'}×${img.metadata?.height || '?'}`;

        return `
            <div class="umi-image-card" style="
                background: #2c2c2c;
                border: 1px solid #444;
                border-radius: 6px;
                overflow: hidden;
                cursor: pointer;
                transition: all 0.2s;
            " onmouseover="this.style.borderColor='#61afef'; this.style.transform='scale(1.02)'" onmouseout="this.style.borderColor='#444'; this.style.transform='scale(1)'">
                <div style="
                    width: 100%;
                    height: 200px;
                    background: url('${img.url}') center/cover;
                    position: relative;
                ">
                    ${hasPrompt ? '<div style="position: absolute; top: 5px; right: 5px; background: #98c379; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600;">Has Prompt</div>' : ''}
                </div>
                <div style="padding: 8px;">
                    <div style="font-size: 11px; color: #abb2bf; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${img.filename}">
                        ${img.filename}
                    </div>
                    <div style="font-size: 10px; color: #666;">
                        ${resolution} • ${(img.size / 1024).toFixed(1)} KB
                    </div>
                </div>
            </div>
        `;
    }

    showImageDetails(img) {
        this.selectedImage = img;
        const sidebar = this.element.querySelector(".umi-image-details");
        const content = this.element.querySelector(".umi-details-content");

        sidebar.style.display = "flex";

        const metadata = img.metadata || {};
        console.log("[Umi Image Browser] Full image metadata:", img);
        console.log("[Umi Image Browser] Metadata object:", metadata);

        // Extract prompts: input (before wildcards) and output (after processing)
        const inputPrompt = metadata.umi_input_prompt || "";
        const inputNegative = metadata.umi_input_negative || "";
        let outputPrompt = metadata.umi_prompt || metadata.prompt || "";
        let outputNegative = metadata.umi_negative || metadata.negative || "";

        // If still no output prompt, try A1111 params
        if (!outputPrompt && metadata.a1111_params) {
            const lines = metadata.a1111_params.split("\n");
            if (lines.length > 0) {
                outputPrompt = lines[0];
            }
        }

        // HTML escape function to properly display <lora:...> tags
        const escapeHtml = (text) => {
            if (!text) return "";
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        };

        // Build sections HTML
        let sectionsHTML = '';

        // Input Prompt Section (before wildcard processing)
        if (inputPrompt) {
            sectionsHTML += `
                <div style="margin-bottom: 15px;">
                    <div style="font-weight: 600; color: #98c379; margin-bottom: 5px; font-size: 13px;">📝 Input Prompt (with wildcards)</div>
                    <div class="umi-input-prompt-box" style="
                        background: #2c2c2c;
                        padding: 10px;
                        border-radius: 4px;
                        font-size: 12px;
                        color: #abb2bf;
                        max-height: 150px;
                        overflow-y: auto;
                        word-wrap: break-word;
                        margin-bottom: 8px;
                    ">${escapeHtml(inputPrompt)}</div>
                    <button class="umi-copy-input-prompt" style="
                        width: 100%;
                        padding: 8px;
                        background: #98c379;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 12px;
                        font-weight: 600;
                    ">📋 Copy Input to Umi Node</button>
                </div>
            `;

            if (inputNegative) {
                sectionsHTML += `
                    <div style="margin-bottom: 15px;">
                        <div style="font-weight: 600; color: #e5c07b; margin-bottom: 5px; font-size: 13px;">📝 Input Negative</div>
                        <div class="umi-input-negative-box" style="
                            background: #2c2c2c;
                            padding: 10px;
                            border-radius: 4px;
                            font-size: 12px;
                            color: #abb2bf;
                            max-height: 150px;
                            overflow-y: auto;
                            word-wrap: break-word;
                        ">${escapeHtml(inputNegative)}</div>
                    </div>
                `;
            }
        }

        // Output Prompt Section (after processing)
        if (outputPrompt) {
            sectionsHTML += `
                <div style="margin-bottom: 15px;">
                    <div style="font-weight: 600; color: #61afef; margin-bottom: 5px; font-size: 13px;">✨ Output Prompt (processed)</div>
                    <div class="umi-output-prompt-box" style="
                        background: #2c2c2c;
                        padding: 10px;
                        border-radius: 4px;
                        font-size: 12px;
                        color: #abb2bf;
                        max-height: 150px;
                        overflow-y: auto;
                        word-wrap: break-word;
                        margin-bottom: 8px;
                    ">${escapeHtml(outputPrompt)}</div>
                    <button class="umi-copy-output-prompt" style="
                        width: 100%;
                        padding: 8px;
                        background: #61afef;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 12px;
                        font-weight: 600;
                    ">📋 Copy Output to Umi Node</button>
                </div>
            `;

            if (outputNegative) {
                sectionsHTML += `
                    <div style="margin-bottom: 15px;">
                        <div style="font-weight: 600; color: #e06c75; margin-bottom: 5px; font-size: 13px;">✨ Output Negative</div>
                        <div class="umi-output-negative-box" style="
                            background: #2c2c2c;
                            padding: 10px;
                            border-radius: 4px;
                            font-size: 12px;
                            color: #abb2bf;
                            max-height: 150px;
                            overflow-y: auto;
                            word-wrap: break-word;
                        ">${escapeHtml(outputNegative)}</div>
                    </div>
                `;
            }
        }

        if (!sectionsHTML) {
            sectionsHTML = '<div style="color: #888; text-align: center; padding: 20px;">No prompt metadata found</div>';
        }

        content.innerHTML = `
            <div style="margin-bottom: 15px;">
                <img src="${img.url}" style="width: 100%; border-radius: 4px; margin-bottom: 10px;" />
                <div style="font-size: 12px; color: #888; margin-bottom: 10px;">
                    ${img.filename}<br>
                    ${metadata.width}×${metadata.height} • ${metadata.format || 'Unknown'}<br>
                    ${new Date(img.mtime * 1000).toLocaleString()}
                </div>
            </div>

            ${sectionsHTML}

            <div style="display: flex; gap: 8px;">
                <button class="umi-open-image" style="
                    flex: 1;
                    padding: 8px;
                    background: #56b6c2;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 12px;
                    font-weight: 600;
                ">🔗 Open Image</button>
            </div>
        `;

        // Add button handlers
        const copyInputBtn = content.querySelector(".umi-copy-input-prompt");
        if (copyInputBtn) {
            copyInputBtn.addEventListener("click", () => {
                this.copyToUmiNode(inputPrompt, inputNegative);
            });
        }

        const copyOutputBtn = content.querySelector(".umi-copy-output-prompt");
        if (copyOutputBtn) {
            copyOutputBtn.addEventListener("click", () => {
                this.copyToUmiNode(outputPrompt, outputNegative);
            });
        }

        content.querySelector(".umi-open-image").addEventListener("click", () => {
            window.open(img.url, "_blank");
        });
    }

    copyToUmiNode(prompt, negative) {
        const activeNode = this.findActiveUmiNode();

        if (activeNode) {
            // Set positive prompt - widget name is "text" for both Full and Lite nodes
            const promptWidget = activeNode.widgets.find(w => w.name === "text");
            if (promptWidget && prompt) {
                promptWidget.value = prompt;
                if (promptWidget.callback) {
                    promptWidget.callback(prompt);
                }
                // Trigger input event for syntax highlighting
                if (promptWidget.inputEl) {
                    promptWidget.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }

            // Set negative prompt if provided
            if (negative) {
                const negWidget = activeNode.widgets.find(w => w.name === "input_negative");
                if (negWidget) {
                    negWidget.value = negative;
                    if (negWidget.callback) {
                        negWidget.callback(negative);
                    }
                    // Trigger input event for syntax highlighting
                    if (negWidget.inputEl) {
                        negWidget.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            }

            // Force graph redraw to ensure visibility
            app.graph.setDirtyCanvas(true, true);

            this.showNotification(`✓ Copied to ${activeNode.type}`);
        } else {
            // Fallback: copy to clipboard
            let text = prompt;
            if (negative) {
                text += `\n\nNegative: ${negative}`;
            }
            navigator.clipboard.writeText(text);
            this.showNotification("📋 Copied to clipboard (no active Umi node)");
        }
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

    renderPagination() {
        const pagination = this.element.querySelector(".umi-pagination");
        const totalPages = Math.ceil(this.totalImages / this.pageSize);

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        const buttons = [];

        // Previous button
        buttons.push(`
            <button class="umi-page-btn" data-page="${this.currentPage - 1}" ${this.currentPage === 0 ? 'disabled' : ''} style="
                padding: 6px 12px;
                background: #2c2c2c;
                color: #abb2bf;
                border: 1px solid #555;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            ">← Prev</button>
        `);

        // Page info
        buttons.push(`
            <span style="color: #888; font-size: 13px;">
                Page ${this.currentPage + 1} of ${totalPages} (${this.totalImages} images)
            </span>
        `);

        // Next button
        buttons.push(`
            <button class="umi-page-btn" data-page="${this.currentPage + 1}" ${this.currentPage >= totalPages - 1 ? 'disabled' : ''} style="
                padding: 6px 12px;
                background: #2c2c2c;
                color: #abb2bf;
                border: 1px solid #555;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            ">Next →</button>
        `);

        pagination.innerHTML = buttons.join('');

        // Add click handlers
        pagination.querySelectorAll(".umi-page-btn:not([disabled])").forEach(btn => {
            btn.addEventListener("click", () => {
                this.currentPage = parseInt(btn.dataset.page);
                this.loadImages();
            });
        });
    }

    showNotification(message) {
        const notification = document.createElement("div");
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #98c379;
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
        this.currentPage = 0;
        await this.loadImages();
    }

    hide() {
        if (this.element) {
            this.element.style.display = "none";
            this.selectedImage = null;
        }
    }
}

// Global instance
const imageBrowser = new ImageBrowser();

// Register extension
app.registerExtension({
    name: "Umi.ImageBrowser",

    async setup() {
        // Add menu button
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "🖼️ Image Browser";
            button.style.cssText = "margin-left: 4px;";
            button.onclick = () => imageBrowser.show();
            menu.appendChild(button);
        }

        // Add keyboard shortcut (Ctrl+I)
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "i") {
                e.preventDefault();
                imageBrowser.show();
            }
        });
    }
});
