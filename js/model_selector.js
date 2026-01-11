import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

class UmiSelectorWidget {
    constructor(node, container) {
        this.node = node;
        this.container = container;
        this.models = [];
        this.currentValue = "";
        this.designWidth = 320;

        const w = this.node.widgets.find(x => x.name === "model_name");
        if (w) this.currentValue = w.value;

        this._onRegistryUpdate = () => {
            if (!this.container || !this.container.isConnected) {
                window.removeEventListener("umi-model-registry-updated", this._onRegistryUpdate);
                return;
            }
            this.refresh();
        };
        window.addEventListener("umi-model-registry-updated", this._onRegistryUpdate);

        this.styleContainer();

        const onResize = node.onResize;
        node.onResize = (size) => {
            if (onResize) onResize.apply(node, [size]);
            this.updateScale();
        };

        this.render();
    }

    styleContainer() {
        this.container.style.width = "100%";
        this.container.style.height = "100%";
        this.container.style.padding = "0";
        this.container.style.backgroundColor = "transparent";
        this.container.style.marginTop = "0";
        this.container.style.overflow = "hidden";
        this.container.style.position = "relative";
    }

    updateScale() {
        if (!this.node || !this.innerContent) return;
        const availableWidth = Math.max(this.node.size[0] - 20, 100);
        const scale = availableWidth / this.designWidth;
        this.innerContent.style.transform = `scale(${scale})`;
        this.innerContent.style.transformOrigin = "top left";
        this.innerContent.style.width = `${this.designWidth}px`;
    }

    async refresh() {
        const repoWidget = this.node.widgets.find(w => w.name === "repo_id");
        const nameWidget = this.node.widgets.find(w => w.name === "model_name");
        const repoId = repoWidget ? repoWidget.value : "Tinuva/Comfy-Umi";
        if (nameWidget) this.currentValue = nameWidget.value;

        if (this.refreshBtn) this.refreshBtn.textContent = "...";

        try {
            const response = await api.fetchApi(`/umiapp/models/check?repo_id=${encodeURIComponent(repoId)}`);
            const data = await response.json();
            if (data.models) {
                this.models = data.models;
                this.render();
            }
        } catch (e) {
        } finally {
            if (this.refreshBtn) this.refreshBtn.textContent = "R";
        }
    }

    setValue(name) {
        this.currentValue = name;
        const w = this.node.widgets.find(x => x.name === "model_name");
        if (w) w.value = name;

        const m = this.models.find(x => x.name === name);
        if (m && m.active_version) {
            const vw = this.node.widgets.find(x => x.name === "version");
            if (vw) vw.value = m.active_version;
        }

        this.render();
    }

    render() {
        const selectedModel = this.models.find(m => m.name === this.currentValue);
        if (selectedModel) {
            const vw = this.node.widgets.find(x => x.name === "version");
            if (vw && selectedModel.active_version) {
                vw.value = selectedModel.active_version;
            } else if (vw) {
                vw.value = "auto";
            }
        }

        this.container.innerHTML = "";
        this.innerContent = document.createElement("div");

        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.width = "100%";
        row.style.alignItems = "stretch";
        row.style.border = "1px solid #444";
        row.style.borderRadius = "4px";
        row.style.overflow = "hidden";
        row.style.backgroundColor = "#2a2a2a";

        const card = document.createElement("div");
        card.style.flex = "1";
        card.style.cursor = "pointer";
        card.style.padding = "8px 10px";
        card.style.display = "flex";
        card.style.flexDirection = "column";
        card.style.justifyContent = "center";
        card.style.position = "relative";
        card.title = "Click to Select Model";
        card.onclick = () => this.showModal();

        if (selectedModel) {
            const activeVer = selectedModel.active_version;
            const hasAnyInstall = selectedModel.installed_versions && selectedModel.installed_versions.length > 0;
            const latestVer = selectedModel.versions && selectedModel.versions.length > 0 ? selectedModel.versions[0].version : null;

            const isConfigured = !!activeVer;
            if (isConfigured) {
                row.style.borderColor = "#484";
                row.style.backgroundColor = "#162816";
            } else if (hasAnyInstall) {
                row.style.borderColor = "#aa4";
                row.style.backgroundColor = "#282816";
            } else {
                row.style.borderColor = "#a44";
                row.style.backgroundColor = "#281616";
            }

            const formatV = (s) => String(s).startsWith('v') ? s : `v${s}`;
            let ver = "";
            if (isConfigured) {
                ver = formatV(activeVer);
                if (latestVer && String(activeVer) !== String(latestVer)) {
                    ver += ` (New: ${formatV(latestVer)})`;
                }
            } else {
                ver = latestVer ? `${formatV(latestVer)} (Not Active)` : "Unknown Version";
            }

            const nameColor = isConfigured ? "#cec" : (hasAnyInstall ? "#fe8" : "#f88");
            const icon = isConfigured ? "OK" : (hasAnyInstall ? "!" : "X");
            const iconColor = isConfigured ? "#4a4" : (hasAnyInstall ? "#fa0" : "#f44");

            card.innerHTML = `
                <div style="font-weight: bold; color: ${nameColor}; word-break: break-word; font-size: 13px; line-height: 1.3; padding-right: 15px;">${selectedModel.name}</div>
                <div style="font-size: 10px; color: #aaa; margin-top: 2px;">${ver}</div>
                <div style="font-size: 10px; color: #8a8; margin-top: 5px; border-top: 1px solid rgba(100,150,100,0.2); padding-top: 4px; line-height: 1.25; font-style: italic;">
                    ${selectedModel.description || "No description available."}
                </div>
                <div style="position: absolute; top: 6px; right: 6px; color: ${iconColor}; font-weight: bold; font-size: 12px;">${icon}</div>
            `;
        } else if (this.currentValue) {
            if (this.models.length === 0) {
                card.innerHTML = `
                    <div style="font-weight: bold; color: #ddd; word-break: break-word; font-size: 13px;">${this.currentValue}</div>
                    <div style="font-size: 10px; color: #888; margin-top: 2px;">Loading info...</div>
                `;
            } else {
                card.innerHTML = `
                    <div style="font-weight: bold; color: #f88; word-break: break-word; font-size: 13px;">${this.currentValue}</div>
                    <div style="font-size: 10px; color: #d66; margin-top: 2px;">Not found in Repo</div>
                `;
            }
        } else {
            card.innerHTML = `
                <div style="color: #ccc; font-style: italic; font-size: 13px; text-align: center; padding: 4px 0;">Select Model...</div>
            `;
        }

        row.appendChild(card);

        const rBtn = document.createElement("div");
        rBtn.textContent = "R";
        rBtn.title = "Refresh List";
        rBtn.style.width = "32px";
        rBtn.style.display = "flex";
        rBtn.style.alignItems = "center";
        rBtn.style.justifyContent = "center";
        rBtn.style.borderLeft = "1px solid #444";
        rBtn.style.fontSize = "14px";
        rBtn.style.cursor = "pointer";
        rBtn.style.backgroundColor = "rgba(0,0,0,0.2)";

        rBtn.onmouseover = () => { rBtn.style.backgroundColor = "#444"; rBtn.style.color = "#fff"; };
        rBtn.onmouseout = () => { rBtn.style.backgroundColor = "rgba(0,0,0,0.2)"; rBtn.style.color = "#888"; };
        rBtn.onclick = (e) => { e.stopPropagation(); this.refresh(); };

        this.refreshBtn = rBtn;
        row.appendChild(rBtn);

        this.innerContent.appendChild(row);
        this.container.appendChild(this.innerContent);
        this.updateScale();
    }

    showModal() {
        if (!this.models.length) {
            if (confirm("Model list empty. Refresh now?")) this.refresh();
            return;
        }

        const overlay = document.createElement("div");
        Object.assign(overlay.style, {
            position: "fixed", top: "0", left: "0", width: "100vw", height: "100vh",
            background: "rgba(0,0,0,0.6)", zIndex: "10000",
            display: "flex", justifyContent: "center", alignItems: "center"
        });

        const dialog = document.createElement("div");
        Object.assign(dialog.style, {
            width: "400px", maxWidth: "90%", maxHeight: "80vh",
            background: "#222", border: "1px solid #444", borderRadius: "8px",
            display: "flex", flexDirection: "column", boxShadow: "0 10px 30px rgba(0,0,0,0.5)"
        });

        const header = document.createElement("div");
        header.innerHTML = "Select Model <span style='float:right; cursor:pointer'>X</span>";
        Object.assign(header.style, {
            padding: "10px 15px", background: "#1a1a1a", borderBottom: "1px solid #333",
            fontWeight: "bold", color: "#ddd"
        });
        header.querySelector("span").onclick = () => document.body.removeChild(overlay);
        dialog.appendChild(header);

        const search = document.createElement("input");
        search.placeholder = "Filter models...";
        Object.assign(search.style, {
            padding: "10px", background: "#111", border: "none",
            borderBottom: "1px solid #333", color: "#fff", outline: "none", width: "100%", boxSizing: "border-box"
        });
        dialog.appendChild(search);

        const list = document.createElement("div");
        Object.assign(list.style, { flex: "1", overflowY: "auto", padding: "0" });

        const renderItems = (filter = "") => {
            list.innerHTML = "";
            const lowerFilter = filter.toLowerCase();
            this.models
                .filter(m => m.name.toLowerCase().includes(lowerFilter))
                .sort((a, b) => a.name.localeCompare(b.name))
                .forEach(m => {
                    const el = document.createElement("div");
                    const isSelected = m.name === this.currentValue;
                    Object.assign(el.style, {
                        padding: "8px 15px", borderBottom: "1px solid #333", cursor: "pointer",
                        background: isSelected ? "#2a3a2a" : "transparent"
                    });

                    el.onmouseover = () => { if (!isSelected) el.style.background = "#333"; };
                    el.onmouseout = () => { if (!isSelected) el.style.background = "transparent"; };

                    el.innerHTML = `
                        <div style="color: ${isSelected ? '#6c6' : '#eee'}; font-weight: bold;">${m.name}</div>
                        <div style="color: #888; font-size: 11px;">${m.description || ""}</div>
                    `;

                    el.onclick = () => {
                        this.setValue(m.name);
                        document.body.removeChild(overlay);
                    };
                    list.appendChild(el);
                });

            if (!list.hasChildNodes()) {
                list.innerHTML = "<div style='padding:20px; text-align:center; color:#666'>No matches found</div>";
            }
        };

        renderItems();
        search.oninput = (e) => renderItems(e.target.value);

        dialog.appendChild(list);
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        overlay.onclick = (e) => {
            if (e.target === overlay) document.body.removeChild(overlay);
        };

        search.focus();
    }
}

app.registerExtension({
    name: "UmiAI.ModelSelector",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "UmiModelSelector") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            let textWidget = this.widgets?.find(w => w.name === "model_name");
            if (!textWidget) {
                textWidget = this.addWidget("text", "model_name", "", () => {}, { serialize: true });
            }
            textWidget.computeSize = () => [0, -4];
            textWidget.type = "hidden";
            textWidget.draw = () => {};

            let verWidget = this.widgets?.find(w => w.name === "version");
            if (!verWidget) {
                verWidget = this.addWidget("text", "version", "auto", () => {}, { serialize: true });
            }
            verWidget.computeSize = () => [0, -4];
            verWidget.type = "hidden";
            verWidget.draw = () => {};

            const container = document.createElement("div");
            Object.assign(container.style, {
                width: "100%",
                display: "flex",
                flexDirection: "column",
                boxSizing: "border-box"
            });

            this.addDOMWidget("SelectorWidget", "div", container, {
                serialize: false,
                hideOnZoom: false
            });

            this.selectorWidget = new UmiSelectorWidget(this, container);

            setTimeout(() => {
                this.selectorWidget.refresh();
            }, 100);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            if (onConfigure) onConfigure.apply(this, arguments);
            if (this.selectorWidget) {
                const w = this.widgets.find(x => x.name === "model_name");
                if (w) {
                    this.selectorWidget.currentValue = w.value;
                    setTimeout(() => this.selectorWidget.refresh(), 500);
                }
            }
        };
    }
});
