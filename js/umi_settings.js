import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ensureUmiTheme } from "./umi_theme.js";

class UmiSettingsDialog {
    constructor() {
        this.settings = {};
        this.element = document.createElement("div");
        this.element.className = "umi-settings-dialog";

        ensureUmiTheme();
        if (!document.getElementById("umi-settings-styles")) {
            const style = document.createElement("style");
            style.id = "umi-settings-styles";
            style.textContent = `
                .umi-settings-dialog {
                    position: fixed;
                    inset: 0;
                    z-index: 10040;
                    display: none;
                    align-items: center;
                    justify-content: center;
                    background: rgba(0, 0, 0, 0.55);
                }
                .umi-settings-dialog .umi-settings-panel {
                    background: var(--umi-surface);
                    color: var(--umi-ink);
                    border: 1px solid var(--umi-rule-strong);
                    border-radius: 8px;
                    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
                    padding: 20px;
                    min-width: 500px;
                    max-width: min(720px, calc(100vw - 32px));
                    max-height: 80vh;
                    overflow-y: auto;
                    overflow-x: hidden;
                    box-sizing: border-box;
                }
                .umi-settings-dialog button {
                    color: var(--umi-ink-strong);
                }
            `;
            document.head.appendChild(style);
        }

        this.element.addEventListener("mousedown", (event) => {
            if (event.target === this.element) this.close();
        });
    }

    async loadSettings() {
        try {
            const response = await api.fetchApi("/umiapp/settings");
            const data = await response.json();
            this.settings = data.settings || {};
        } catch (error) {
            console.error("[UmiAI Settings] Failed to load settings:", error);
            this.settings = {};
        }
    }

    showMessage(title, message) {
        const body = `
            <div style="padding: 20px;">
                <h3>${title}</h3>
                <p>${message}</p>
            </div>
        `;
        if (app?.ui?.dialog?.show) {
            app.ui.dialog.show(body);
        } else {
            alert(`${title}\n\n${message}`);
        }
    }

    async saveSettings() {
        try {
            const response = await api.fetchApi("/umiapp/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ settings: this.settings })
            });
            const data = await response.json();

            if (data.status === "success") {
                window.dispatchEvent(new CustomEvent("umi-settings-updated", {
                    detail: { settings: data.settings || this.settings }
                }));
                this.close();
                this.showMessage("Settings Updated", data.message || "UmiAI settings were saved.");
            } else {
                this.showMessage("Error", data.message || "Failed to save settings.");
            }
        } catch (error) {
            this.showMessage("Error", `Failed to save settings: ${error.message}`);
        }
    }

    async resetSettings() {
        if (!confirm("Reset all settings to defaults?")) return;

        try {
            const response = await api.fetchApi("/umiapp/settings/reset", { method: "POST" });
            const data = await response.json();

            if (data.status === "success") {
                this.settings = data.settings;
                window.dispatchEvent(new CustomEvent("umi-settings-updated", {
                    detail: { settings: data.settings || this.settings }
                }));
                this.show();
                this.showMessage("Settings Reset", data.message || "UmiAI settings were reset.");
            }
        } catch (error) {
            this.showMessage("Error", `Failed to reset settings: ${error.message}`);
        }
    }

    close() {
        this.element.style.display = "none";
    }

    formatKey(key) {
        return key
            .split("_")
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" ");
    }

    getDescription(key) {
        const descriptions = {
            use_folder_paths: "Show folder paths in wildcards (__Series/File__ vs __File__)",
            csv_namespace: "Add $csv_ prefixed variables from CSV files",
            yaml_namespace: "Add $yaml_ prefixed variables from YAML files",
            rng_streams: "Use deterministic RNG streams per scope/tag",
            auto_clean: "Auto-clean prompts (remove extra commas/spaces, fix BREAK)",
            preserve_newlines: "Keep line breaks in expanded prompts; spacing is cleaned within each line. Off preserves existing behavior.",
            max_expansion_iterations: "Maximum expansion passes (1–200). Default: 50. Lower this to diagnose recursive files.",
            max_expanded_prompt_chars: "Stop growing prompts at this character limit (1,000–10,000,000). Default: 1,000,000.",
            error_lint: "Show detailed error messages instead of user-friendly warnings",
            lint_cleaner_enabled: "Show prompt linting and cleaning UI banner",
            enable_tag_autocomplete: "Enable tag autocomplete from CSV files",
            enable_debug_output: "Enable debug console output (warnings, errors, info)",
            persist_prompt_history: "Keep the last 100 processed prompts in prompt_history.json",
            persist_run_inspector: "Keep the latest complete prompt trace for the Run Inspector panel"
        };
        return descriptions[key] || "No description available";
    }

    createSettingRow(key, value, description) {
        const row = document.createElement("div");
        row.style.cssText = "margin: 15px 0; display: flex; align-items: center; gap: 10px;";

        const label = document.createElement("label");
        label.style.cssText = "flex: 1; cursor: pointer;";
        label.innerHTML = `
            <strong>${this.formatKey(key)}</strong>
            <div style="font-size: 0.9em; color: var(--umi-ink); margin-top: 2px;">${description}</div>
        `;

        const input = document.createElement("input");
        const limits = {
            max_expansion_iterations: [1, 200],
            max_expanded_prompt_chars: [1000, 10000000],
        };
        if (limits[key]) {
            input.type = "number";
            [input.min, input.max] = limits[key];
            input.step = "1";
            input.value = value;
            input.setAttribute("aria-label", this.formatKey(key));
            input.style.cssText = "width: 110px; padding: 6px; background: var(--umi-field); color: var(--umi-ink); border: 1px solid var(--umi-rule); border-radius: 4px;";
            input.onchange = () => { this.settings[key] = input.value === "" ? null : Number(input.value); };
            label.onclick = () => input.focus();
            row.append(label, input);
            return row;
        }
        input.type = "checkbox";
        input.checked = Boolean(value);
        input.style.cssText = "width: 20px; height: 20px; cursor: pointer;";
        input.onchange = () => {
            this.settings[key] = input.checked;
        };

        label.onclick = () => {
            input.checked = !input.checked;
            input.onchange();
        };

        row.appendChild(label);
        row.appendChild(input);
        return row;
    }

    async show() {
        await this.loadSettings();

        const content = document.createElement("div");
        content.className = "umi-settings-panel";

        const title = document.createElement("h2");
        title.textContent = "UmiAI Settings";
        title.style.cssText = "margin-top: 0; margin-bottom: 20px; color: var(--umi-ink-strong);";
        content.appendChild(title);

        const settingsContainer = document.createElement("div");
        settingsContainer.style.cssText = "margin-bottom: 20px;";

        const categories = {
            "Core Settings": ["use_folder_paths", "csv_namespace", "yaml_namespace", "rng_streams"],
            Processing: ["auto_clean", "preserve_newlines", "max_expansion_iterations", "max_expanded_prompt_chars", "error_lint"],
            "UI Settings": ["lint_cleaner_enabled"],
            "Feature Toggles": ["enable_tag_autocomplete"],
            Privacy: ["persist_prompt_history", "persist_run_inspector"],
            Debug: ["enable_debug_output"]
        };

        Object.entries(categories).forEach(([categoryName, keys]) => {
            const categoryTitle = document.createElement("h3");
            categoryTitle.textContent = categoryName;
            categoryTitle.style.cssText = "margin-top: 20px; margin-bottom: 10px; color: var(--umi-ink); font-size: 1em; border-bottom: 1px solid var(--umi-rule-strong); padding-bottom: 5px;";
            settingsContainer.appendChild(categoryTitle);

            keys.forEach(key => {
                if (key in this.settings) {
                    settingsContainer.appendChild(
                        this.createSettingRow(key, this.settings[key], this.getDescription(key))
                    );
                }
            });
        });

        content.appendChild(settingsContainer);

        const buttonContainer = document.createElement("div");
        buttonContainer.style.cssText = "display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;";

        const resetBtn = document.createElement("button");
        resetBtn.textContent = "Reset to Defaults";
        resetBtn.style.cssText = "padding: 8px 16px; cursor: pointer; background: var(--umi-surface-hover); border: 1px solid var(--umi-rule-hover); border-radius: 4px;";
        resetBtn.onclick = () => this.resetSettings();

        const cancelBtn = document.createElement("button");
        cancelBtn.textContent = "Cancel";
        cancelBtn.style.cssText = "padding: 8px 16px; cursor: pointer; background: var(--umi-surface-hover); border: 1px solid var(--umi-rule-hover); border-radius: 4px;";
        cancelBtn.onclick = () => this.close();

        const saveBtn = document.createElement("button");
        saveBtn.textContent = "Save Settings";
        saveBtn.style.cssText = "padding: 8px 16px; cursor: pointer; background: var(--umi-accent); border: 1px solid var(--umi-accent-soft); border-radius: 4px; font-weight: bold;";
        saveBtn.onclick = () => this.saveSettings();

        buttonContainer.appendChild(resetBtn);
        buttonContainer.appendChild(cancelBtn);
        buttonContainer.appendChild(saveBtn);
        content.appendChild(buttonContainer);

        this.element.innerHTML = "";
        this.element.appendChild(content);
        if (!this.element.isConnected) document.body.appendChild(this.element);
        this.element.style.display = "flex";
    }
}

app.registerExtension({
    name: "UmiAI.Settings",
    async setup() {
        const settingsDialog = new UmiSettingsDialog();
        window.umiSettingsDialog = settingsDialog;

        const addMenuButton = () => {
            const menu = document.querySelector(".comfy-menu");
            if (!menu || document.getElementById("umi-settings-menu-button")) return false;

            const settingsBtn = document.createElement("button");
            settingsBtn.id = "umi-settings-menu-button";
            settingsBtn.textContent = "UmiAI Settings";
            settingsBtn.style.cssText = "margin-left: 5px;";
            settingsBtn.onclick = () => settingsDialog.show();
            menu.appendChild(settingsBtn);
            return true;
        };

        if (!addMenuButton()) {
            setTimeout(addMenuButton, 500);
            setTimeout(addMenuButton, 1500);
            setTimeout(addMenuButton, 3000);
        }
    }
});
