import { app } from "../../scripts/app.js";
import { copyText, escapeHtml, renderPromptStructureHtml, showUmiNotification } from "./umi_frontend_utils.js";
import { ensureUmiTheme } from "./umi_theme.js";

class UmiRunInspector {
    constructor() {
        this.element = null;
        this.data = null;
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-run-inspector";
        panel.style.cssText = `
            position: fixed;
            inset: 0;
            z-index: 10020;
            display: none;
            background: rgba(8,10,14,0.86);
            color: var(--umi-ink);
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        `;
        ensureUmiTheme();
        panel.innerHTML = `
            <style>
                .uri-shell { position:absolute; inset:40px; background:var(--umi-sunken); border:1px solid var(--umi-rule); border-radius:10px; display:flex; flex-direction:column; overflow:hidden; box-shadow:0 12px 40px rgba(0,0,0,0.55); }
                .uri-header { display:flex; align-items:center; gap:10px; padding:12px 16px; border-bottom:1px solid var(--umi-rule); background:var(--umi-ground); }
                .uri-title { color:var(--umi-accent); font-weight:700; font-size:17px; }
                .uri-sub { color:var(--umi-ink-2); font-size:12px; }
                .uri-spacer { flex:1; }
                .uri-btn { background:var(--umi-surface-alt); color:var(--umi-ink); border:1px solid var(--umi-rule-strong); padding:6px 10px; border-radius:6px; cursor:pointer; font-size:12px; }
                .uri-btn:hover { border-color:var(--umi-rule-hover); background:var(--umi-surface-hover); }
                .uri-body { display:grid; grid-template-columns:280px minmax(0,1fr); min-height:0; flex:1; }
                .uri-sidebar { border-right:1px solid var(--umi-rule); background:var(--umi-sunken); padding:14px; overflow:auto; }
                .uri-main { padding:14px; overflow:auto; min-width:0; }
                .uri-card { background:var(--umi-ground); border:1px solid var(--umi-rule); border-radius:8px; padding:12px; margin-bottom:12px; }
                .uri-card h3 { margin:0 0 8px 0; color:var(--umi-accent); font-size:13px; letter-spacing:.04em; text-transform:uppercase; }
                .uri-list { display:flex; flex-direction:column; gap:6px; }
                .uri-chip { display:inline-flex; align-items:center; gap:6px; max-width:100%; background:var(--umi-surface); border:1px solid var(--umi-rule); padding:4px 7px; border-radius:6px; font-size:11px; color:var(--umi-ink); word-break:break-word; }
                .uri-badge { display:inline-flex; align-items:center; padding:2px 6px; border-radius:999px; font-size:10px; border:1px solid var(--umi-rule-strong); background:var(--umi-surface); color:var(--umi-ink); }
                .uri-badge.warn { background:var(--umi-warn-wash); border-color:var(--umi-warn-soft); color:var(--umi-warn); }
                .uri-badge.ok { background:var(--umi-ok-wash); border-color:var(--umi-ok-soft); color:var(--umi-ok); }
                .uri-pre { white-space:pre-wrap; word-break:break-word; background:var(--umi-sunken); border:1px solid var(--umi-rule); border-radius:6px; padding:10px; font-family:Consolas, monospace; font-size:12px; max-height:360px; overflow:auto; }
                .uri-table { width:100%; border-collapse:collapse; font-size:12px; }
                .uri-table th, .uri-table td { border-bottom:1px solid var(--umi-rule); padding:6px; text-align:left; vertical-align:top; }
                .uri-table th { color:var(--umi-ink); font-size:11px; text-transform:uppercase; }
                /* A reused pick and a failed lookup are the two rows a user
                   scanning this table needs to spot without reading it. */
                .uri-table tr.uri-row-cached td { color:var(--umi-ink-2); font-style:italic; }
                .uri-table tr.uri-row-error td { color:var(--umi-danger); }
                .uri-empty { color:var(--umi-ink-2); font-size:12px; padding:12px; text-align:center; }
                /* Prompt structure preview (read-only). The panel supplies its
                   own dark background, so these colors are theme-independent. */
                .umi-sx-brace-d1 { color:var(--umi-choice); font-weight:600; }
                .umi-sx-brace-d2 { color:var(--umi-conditional); font-weight:600; }
                .umi-sx-brace-d3 { color:var(--umi-variable); font-weight:600; }
                .umi-sx-brace-d4 { color:var(--umi-ok); font-weight:600; }
                .umi-sx-brace-d5 { color:var(--umi-weight); font-weight:600; }
                .umi-sx-brace-d6 { color:var(--umi-accent); font-weight:600; }
                .umi-sx-wildcard { color:var(--umi-ok); }
                .umi-sx-sequential { color:var(--umi-warn); }
                .umi-sx-range { color:var(--umi-warn); }
                .umi-sx-promptfile { color:var(--umi-prompt-file); }
                .umi-sx-variable { color:var(--umi-variable); }
                .umi-sx-comment { color:var(--umi-ink-2); font-style:italic; }
                .umi-sx-function { color:var(--umi-function); }
                .umi-sx-conditional { color:var(--umi-conditional); }
                .umi-sx-lora { color:var(--umi-lora); }
                .umi-sx-bracket { color:var(--umi-ink); }
                .umi-sx-error { color:var(--umi-danger); text-decoration:underline wavy var(--umi-danger); text-underline-offset:2px; }
            </style>
            <div class="uri-shell">
                <div class="uri-header">
                    <div>
                        <div class="uri-title">Umi Run Inspector</div>
                        <div class="uri-sub" data-role="subtitle">Latest run</div>
                    </div>
                    <div class="uri-spacer"></div>
                    <button class="uri-btn" data-action="refresh">Refresh</button>
                    <button class="uri-btn" data-action="copy-json">Copy JSON</button>
                    <button class="uri-btn" data-action="close">Close</button>
                </div>
                <div class="uri-body">
                    <aside class="uri-sidebar" data-role="summary"></aside>
                    <main class="uri-main" data-role="main"></main>
                </div>
            </div>
        `;
        panel.addEventListener("click", (event) => {
            if (event.target === panel) this.hide();
        });
        panel.querySelector('[data-action="close"]').addEventListener("click", () => this.hide());
        panel.querySelector('[data-action="refresh"]').addEventListener("click", () => this.load());
        panel.querySelector('[data-action="copy-json"]').addEventListener("click", () => {
            copyText(JSON.stringify(this.data || {}, null, 2), "Inspector JSON copied");
        });
        document.body.appendChild(panel);
        this.element = panel;
    }

    async show() {
        if (!this.element) this.createPanel();
        this.element.style.display = "block";
        await this.load();
    }

    hide() {
        if (this.element) this.element.style.display = "none";
    }

    async load() {
        try {
            const response = await fetch("/umiapp/run_inspector/latest");
            const data = await response.json();
            if (!response.ok || !data.success) {
                // "Disabled" is a setting, not a failure, and it has a fix the
                // user can apply from here. Reporting it as an error message
                // left the panel looking broken with no way forward.
                if (data.disabled) {
                    this.data = null;
                    this.renderDisabled();
                    return;
                }
                throw new Error(data.error || "No run inspector data available");
            }
            this.data = data;
            this.render();
        } catch (error) {
            this.data = null;
            this.renderError(error.message);
        }
    }

    async enablePersistence() {
        try {
            const response = await fetch("/umiapp/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ settings: { persist_run_inspector: true } }),
            });
            if (!response.ok) return false;
            await this.load();
            return true;
        } catch (error) {
            console.warn("[UmiAI] Could not enable run inspector persistence:", error);
            return false;
        }
    }

    renderDisabled() {
        const summary = this.element.querySelector('[data-role="summary"]');
        const main = this.element.querySelector('[data-role="main"]');
        summary.innerHTML = `<div class="uri-empty">Run capture is turned off.</div>`;
        main.innerHTML = `<div class="uri-card">
            <h3>Nothing Is Being Captured</h3>
            <div class="uri-empty">
                The inspector reads a cached copy of the last Umi run, and caching is off.
                Turning it on writes the resolved prompt to
                <code>cache/run_inspector_latest.json</code> after each run.
            </div>
            <div class="uri-list" style="margin-top:10px;">
                <button class="uri-btn" data-action="enable-capture">Turn on run capture</button>
            </div>
        </div>`;
        main.querySelector('[data-action="enable-capture"]')
            ?.addEventListener("click", () => this.enablePersistence());
    }

    renderError(message) {
        const summary = this.element.querySelector('[data-role="summary"]');
        const main = this.element.querySelector('[data-role="main"]');
        summary.innerHTML = `<div class="uri-empty">${escapeHtml(message)}</div>`;
        main.innerHTML = `<div class="uri-card"><h3>No Run Yet</h3><div class="uri-empty">Queue the Umi node once, then refresh this inspector.</div></div>`;
    }

    render() {
        const explain = this.data?.explain || {};
        const diff = this.data?.prompt_diff || {};
        const subtitle = this.element.querySelector('[data-role="subtitle"]');
        subtitle.textContent = `Latest run${this.data?.updated_at ? ` - ${this.data.updated_at}` : ""}`;
        this.renderSummary(explain, diff);
        this.renderMain(explain, diff);
    }

    renderSummary(explain, diff) {
        const warnings = explain.warnings || [];
        const wildcards = explain.wildcard_trace || [];
        const summary = this.element.querySelector('[data-role="summary"]');
        summary.innerHTML = `
            <div class="uri-card">
                <h3>Status</h3>
                <div class="uri-list">
                    <span class="uri-badge ${warnings.length ? "warn" : "ok"}">${warnings.length} warning${warnings.length === 1 ? "" : "s"}</span>
                    <span class="uri-badge">${wildcards.length || Object.keys(explain.wildcard_resolutions || {}).length} wildcard picks</span>
                    <span class="uri-badge">${diff.changed ? "Prompt changed" : "Prompt unchanged"}</span>
                    <span class="uri-badge">${explain.dry_run ? "Dry run" : "Normal run"}</span>
                    <span class="uri-badge">${escapeHtml(explain.profile || "No profile")}</span>
                </div>
            </div>
            <div class="uri-card">
                <h3>Settings</h3>
                <div class="uri-list">
                    <span class="uri-chip">Seed: ${escapeHtml(explain.seed)}</span>
                    <span class="uri-chip">Size: ${escapeHtml(explain.settings?.width || "?")} x ${escapeHtml(explain.settings?.height || "?")}</span>
                    <span class="uri-chip">Preset: ${escapeHtml(explain.prompt_preset || "none")}</span>
                </div>
            </div>
        `;
    }

    renderMain(explain, diff) {
        const main = this.element.querySelector('[data-role="main"]');
        main.innerHTML = [
            this.warningsCard(explain.warnings || []),
            this.structureCard(explain.input_prompt || ""),
            this.wildcardsCard(explain.wildcard_trace || [], explain.wildcard_resolutions || {}),
            this.functionsCard(explain.wildcard_trace || []),
            this.diffCard(diff),
            this.loraCard(explain.lora_info || "", explain.lora_load_trace || []),
            this.promptCard("Final Prompt", explain.final_prompt || ""),
            this.promptCard("Negative Prompt", explain.negative_prompt || ""),
        ].join("");
    }

    warningsCard(warnings) {
        if (!warnings.length) return `<div class="uri-card"><h3>Warnings</h3><div class="uri-empty">No warnings.</div></div>`;
        return `<div class="uri-card"><h3>Warnings</h3><div class="uri-list">${warnings.map(w => `<span class="uri-chip">${escapeHtml(w)}</span>`).join("")}</div></div>`;
    }

    wildcardsCard(trace, fallbackMap = {}) {
        // prompt_function records get their own card (functionsCard).
        const wildcardTrace = trace.filter(item => item.type !== "prompt_function");
        if (wildcardTrace.length) {
            const cached = wildcardTrace.filter(item => item.mode === "cached").length;
            const note = cached
                ? `<div class="uri-list" style="margin-bottom:8px;">
                       <span class="uri-chip">${cached} of ${wildcardTrace.length} reused an earlier pick</span>
                   </div>`
                : "";
            return `<div class="uri-card"><h3>Wildcard Trace</h3>${note}<table class="uri-table">
                <tr><th>Wildcard</th><th>Mode</th><th>Value</th><th>Picked</th><th>Source</th><th>Index</th><th>Scope</th></tr>
                ${wildcardTrace.map(item => {
                    // A reused pick did not roll: it returned a value chosen
                    // earlier in the same prompt. Marking those rows is the
                    // difference between "the seed did nothing" and "this
                    // wildcard was already resolved".
                    const isCached = item.mode === "cached";
                    const isError = Boolean(item.error);
                    const pool = item.available_count;
                    const picked = pool === undefined || pool === null
                        ? escapeHtml(item.count ?? "")
                        : `${escapeHtml(item.count ?? 0)} of ${escapeHtml(pool)}`;
                    const rowClass = isError ? "uri-row-error" : (isCached ? "uri-row-cached" : "");
                    return `<tr class="${rowClass}">
                    <td>${escapeHtml(item.wildcard)}</td>
                    <td>${escapeHtml(item.mode || item.type || "")}${isCached ? " ↺" : ""}</td>
                    <td>${escapeHtml(item.result || (item.values || []).join(", "))}</td>
                    <td>${picked}</td>
                    <td>${escapeHtml(item.relative_path || item.path || "")}</td>
                    <td>${escapeHtml((item.selected_indices || []).filter(v => v !== null && v !== undefined).join(", "))}</td>
                    <td>${escapeHtml(item.scope || "")}</td>
                </tr>`;
                }).join("")}
            </table></div>`;
        }

        const entries = Object.entries(fallbackMap);
        if (!entries.length) return `<div class="uri-card"><h3>Wildcard Picks</h3><div class="uri-empty">No wildcard picks recorded.</div></div>`;
        return `<div class="uri-card"><h3>Wildcard Picks</h3><table class="uri-table"><tr><th>Wildcard</th><th>Value</th></tr>${entries.map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`).join("")}</table></div>`;
    }

    structureWarningChips(warnings) {
        if (!warnings.length) return "";
        return `<div class="uri-list" style="margin-top:8px;">${warnings.map(w => `<span class="uri-chip">${escapeHtml(w)}</span>`).join("")}</div>`;
    }

    structureCard(inputPrompt) {
        // Read-only syntax preview of the original prompt. Highlighted markup
        // lives only in this card; the prompt value is never modified.
        const source = String(inputPrompt || "");
        if (!source.trim()) return "";
        const { html, warnings } = renderPromptStructureHtml(source);
        return `<div class="uri-card"><h3>Prompt Structure</h3><div class="uri-pre">${html}</div>${this.structureWarningChips(warnings)}</div>`;
    }

    functionsCard(trace = []) {
        const records = trace.filter(item => item.type === "prompt_function");
        if (!records.length) return "";
        return `<div class="uri-card"><h3>Boolean Prompt Functions</h3><table class="uri-table">
            <tr><th>Function</th><th>Items</th><th>Selected</th><th>Result</th></tr>
            ${records.map(item => {
                const args = item.args || [];
                const selected = (item.selected_indices || [])
                    .map(index => args[index])
                    .filter(value => value !== undefined);
                const name = `[${item.name || "?"}:]` + (item.selection_mode ? ` (${item.selection_mode})` : "");
                return `<tr>
                    <td>${escapeHtml(name)}</td>
                    <td>${escapeHtml(args.join(" | "))}</td>
                    <td>${escapeHtml(selected.join(", "))}</td>
                    <td>${escapeHtml(item.result || "")}</td>
                </tr>`;
            }).join("")}
        </table></div>`;
    }

    diffCard(diff) {
        return `<div class="uri-card"><h3>Prompt Diff</h3><div class="uri-pre">Added: ${escapeHtml((diff.added || []).join(", ") || "none")}\nRemoved: ${escapeHtml((diff.removed || []).join(", ") || "none")}</div></div>`;
    }

    loraCard(loraInfo, trace = []) {
        const traceTable = trace.length ? `<table class="uri-table">
            <tr><th>LoRA</th><th>Strength</th><th>Status</th><th>Cache</th><th>Path</th></tr>
            ${trace.map(item => `<tr>
                <td>${escapeHtml(item.lora || "")}</td>
                <td>${escapeHtml(item.strength ?? "")}</td>
                <td>${escapeHtml(item.status || (item.applied ? "applied" : ""))}</td>
                <td>${escapeHtml(item.weights_cache_hit ? "weights hit" : "weights miss")}</td>
                <td>${escapeHtml(item.error || item.path || "")}</td>
            </tr>`).join("")}
        </table>` : `<div class="uri-empty">No LoRA loads recorded.</div>`;

        return `<div class="uri-card"><h3>LoRAs</h3><div class="uri-pre">${escapeHtml(loraInfo || "No LoRA info.")}</div>${traceTable}</div>`;
    }

    promptCard(title, prompt) {
        // Same read-only structure highlighting as the input-prompt card, so
        // any syntax that survives into the final/negative prompt (loras,
        // stray braces, variables) stays readable. Text is escaped by the
        // renderer and never written back to the prompt value.
        const source = String(prompt || "");
        if (!source.trim()) {
            return `<div class="uri-card"><h3>${escapeHtml(title)}</h3><div class="uri-pre">Empty</div></div>`;
        }
        const { html, warnings } = renderPromptStructureHtml(source);
        return `<div class="uri-card"><h3>${escapeHtml(title)}</h3><div class="uri-pre">${html}</div>${this.structureWarningChips(warnings)}</div>`;
    }
}

const inspector = new UmiRunInspector();
window.umiRunInspector = inspector;

app.registerExtension({
    name: "Umi.RunInspector",
    async setup() {
        const menu = document.querySelector(".comfy-menu");
        if (menu) {
            const button = document.createElement("button");
            button.textContent = "Run Inspector";
            button.onclick = () => inspector.show();
            menu.appendChild(button);
        }
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "UmiAIWildcardNode" && nodeData.name !== "UmiAIWildcardNodeLite") return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            if (!this.widgets?.some(w => w.name === "Open Run Inspector")) {
                this.addWidget("button", "Open Run Inspector", null, () => inspector.show(), { serialize: false });
            }
            return result;
        };
        const onDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            onDrawForeground?.apply(this, arguments);
            const widgetValue = (name) => this.widgets?.find(w => w.name === name)?.value;
            const badges = [];
            const profile = widgetValue("prompt_profile");
            const preset = widgetValue("prompt_preset");
            const dryRun = widgetValue("dry_run");
            if (profile && profile !== "None") badges.push(`Profile: ${profile}`);
            if (preset && preset !== "none") badges.push(`Preset: ${preset}`);
            if (dryRun) badges.push("Dry run");
            if (!badges.length || !ctx) return;

            ctx.save();
            ctx.font = "10px sans-serif";
            let x = 8;
            let y = this.size?.[1] ? this.size[1] - 18 : 8;
            for (const badge of badges.slice(0, 4)) {
                const width = Math.min(ctx.measureText(badge).width + 12, this.size[0] - 16);
                if (x + width > this.size[0] - 6) break;
                ctx.fillStyle = "rgba(31, 43, 62, 0.92)";
                ctx.strokeStyle = "rgba(143, 198, 255, 0.45)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.roundRect(x, y, width, 14, 5);
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = "var(--umi-ink)";
                ctx.fillText(badge, x + 6, y + 10);
                x += width + 5;
            }
            ctx.restore();
        };
    },
});
