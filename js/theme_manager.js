import { app } from "../../scripts/app.js";

// Phase 8: Theme Manager - Toggle between dark and light themes for all Umi panels

class ThemeManager {
    constructor() {
        this.currentTheme = this.loadTheme();
        this.themes = {
            dark: {
                background: "#1e1e1e",
                cardBackground: "#2c2c2c",
                border: "#444",
                borderActive: "#61afef",
                text: "#abb2bf",
                textSecondary: "#888",
                textHighlight: "#61afef",
                success: "#98c379",
                error: "#e06c75",
                warning: "#e5c07b",
                info: "#56b6c2",
                hover: "#3e4451"
            },
            light: {
                background: "#ffffff",
                cardBackground: "#f5f5f5",
                border: "#d0d0d0",
                borderActive: "#4078c0",
                text: "#333333",
                textSecondary: "#666666",
                textHighlight: "#4078c0",
                success: "#28a745",
                error: "#d73a49",
                warning: "#f66a0a",
                info: "#0366d6",
                hover: "#e1e4e8"
            }
        };
    }

    loadTheme() {
        const saved = localStorage.getItem("umi_theme");
        return saved || "dark";
    }

    saveTheme(theme) {
        localStorage.setItem("umi_theme", theme);
        this.currentTheme = theme;
    }

    getColors() {
        return this.themes[this.currentTheme];
    }

    toggleTheme() {
        const newTheme = this.currentTheme === "dark" ? "light" : "dark";
        this.saveTheme(newTheme);
        this.applyTheme();
        return newTheme;
    }

    applyTheme() {
        const colors = this.getColors();

        // Apply to all Umi panels
        const panels = [
            ".umi-lora-browser",
            ".umi-image-browser",
            ".umi-preset-manager",
            ".umi-history-browser",
            ".umi-shortcuts-panel"
        ];

        panels.forEach(selector => {
            const panel = document.querySelector(selector);
            if (panel) {
                this.stylePan(panel, colors);
            }
        });

        // Trigger custom event for other components to update
        document.dispatchEvent(new CustomEvent("umi-theme-changed", {
            detail: { theme: this.currentTheme, colors: colors }
        }));
    }

    stylePanel(panel, colors) {
        // Update panel background
        panel.style.background = colors.background;
        panel.style.borderColor = colors.borderActive;

        // Update all card backgrounds
        panel.querySelectorAll("[class*='card']").forEach(card => {
            card.style.background = colors.cardBackground;
            card.style.borderColor = colors.border;
            card.style.color = colors.text;
        });

        // Update inputs
        panel.querySelectorAll("input, select, textarea").forEach(input => {
            input.style.background = colors.cardBackground;
            input.style.borderColor = colors.border;
            input.style.color = colors.text;
        });

        // Update buttons
        panel.querySelectorAll("button:not([class*='close']):not([class*='delete'])").forEach(btn => {
            if (!btn.style.background.includes("gradient")) {
                btn.style.background = colors.info;
            }
        });

        // Update text colors
        panel.querySelectorAll("h2, h3, h4, p, div, span").forEach(el => {
            if (!el.style.color || el.style.color === "") {
                el.style.color = colors.text;
            }
        });
    }

    createToggleButton() {
        const button = document.createElement("button");
        button.className = "umi-theme-toggle";
        button.style.cssText = `
            margin-left: 4px;
            padding: 5px 12px;
            background: ${this.getColors().cardBackground};
            color: ${this.getColors().text};
            border: 1px solid ${this.getColors().border};
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        `;
        this.updateToggleButtonContent(button);

        button.addEventListener("click", () => {
            this.toggleTheme();
            this.updateToggleButtonContent(button);
        });

        button.addEventListener("mouseover", () => {
            button.style.borderColor = this.getColors().borderActive;
        });

        button.addEventListener("mouseout", () => {
            button.style.borderColor = this.getColors().border;
        });

        return button;
    }

    updateToggleButtonContent(button) {
        const colors = this.getColors();
        button.textContent = this.currentTheme === "dark" ? "🌙 Dark" : "☀️ Light";
        button.style.background = colors.cardBackground;
        button.style.color = colors.text;
        button.style.borderColor = colors.border;
    }
}

// Global instance
window.umiThemeManager = new ThemeManager();

// Register extension
app.registerExtension({
    name: "Umi.ThemeManager",

    async setup() {
        // Add theme toggle button to menu
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const toggleButton = window.umiThemeManager.createToggleButton();
            menu.appendChild(toggleButton);
        }

        // Apply theme on startup
        window.umiThemeManager.applyTheme();

        // Listen for panel creation and apply theme
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1 && node.className && typeof node.className === "string") {
                        if (node.className.includes("umi-")) {
                            setTimeout(() => {
                                window.umiThemeManager.applyTheme();
                            }, 100);
                        }
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
});

// Export for use in other modules
export { ThemeManager };
