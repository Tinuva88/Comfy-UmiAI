import { app } from "../../scripts/app.js";
import { ensureUmiTheme, T } from "./umi_theme.js";
import { api } from "../../scripts/api.js";

// =============================================================================
// Prompt history
//
// Two surfaces over one store:
//   * a sidebar panel listing recent prompts, searchable, with copy / reuse
//   * a read-only prompt panel under the Umi Save Image node's own output
//
// Persistence is opt-in. The panel always has this session's runs in memory;
// the toggle controls whether they also go to prompt_history.json on disk.
// =============================================================================

const STYLE_ID = "umi-prompt-history-style";
const MAX_SESSION_ENTRIES = 200;

function ensureStyles() {
    ensureUmiTheme();
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        .umi-ph-overlay {
            position: fixed; inset: 0; z-index: 10050;
            background: rgba(0, 0, 0, 0.62);
            display: flex; align-items: center; justify-content: center;
        }
        .umi-ph-modal {
            width: min(860px, 92vw); height: min(720px, 88vh);
            display: flex; flex-direction: column;
            background: var(--umi-surface); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 6px;
            box-shadow: 0 18px 48px rgba(0, 0, 0, 0.6);
            font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
        }
        .umi-ph-head {
            display: flex; align-items: center; gap: 12px;
            padding: 12px 16px; border-bottom: 1px solid var(--umi-rule);
        }
        .umi-ph-title { font-size: 15px; font-weight: 600; margin-right: auto; }
        .umi-ph-x {
            background: none; border: none; color: var(--umi-ink-2);
            font-size: 20px; line-height: 1; cursor: pointer; padding: 0 4px;
        }
        .umi-ph-x:hover { color: var(--umi-ink-strong); }
        .umi-ph-bar {
            display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
            padding: 10px 16px; border-bottom: 1px solid var(--umi-rule);
        }
        .umi-ph-search {
            flex: 1; min-width: 180px;
            background: var(--umi-ground); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 4px;
            padding: 6px 9px; font: inherit;
        }
        .umi-ph-search:focus { outline: 2px solid var(--umi-accent); outline-offset: -1px; }
        .umi-ph-btn {
            background: var(--umi-surface-alt); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 4px;
            padding: 6px 11px; cursor: pointer; font: inherit;
        }
        .umi-ph-btn:hover { background: var(--umi-surface-hover); }
        .umi-ph-btn:focus-visible { outline: 2px solid var(--umi-accent); outline-offset: 1px; }
        .umi-ph-toggle {
            display: flex; align-items: center; gap: 7px;
            cursor: pointer; user-select: none; color: var(--umi-ink-2);
        }
        .umi-ph-toggle input { cursor: pointer; }
        .umi-ph-note {
            padding: 8px 16px; color: var(--umi-ink-2); font-size: 12px;
            border-bottom: 1px solid var(--umi-rule); background: var(--umi-ground);
        }
        .umi-ph-list { flex: 1; overflow-y: auto; padding: 8px 10px; }
        .umi-ph-empty { padding: 32px 16px; text-align: center; color: var(--umi-ink-3); }
        .umi-ph-item {
            border: 1px solid var(--umi-rule); border-radius: 5px;
            margin-bottom: 8px; background: var(--umi-ground);
        }
        .umi-ph-item-head {
            display: flex; align-items: center; gap: 10px;
            padding: 7px 10px; border-bottom: 1px solid var(--umi-rule);
            font-family: ui-monospace, Consolas, monospace; font-size: 11px;
            color: var(--umi-ink-3);
        }
        .umi-ph-src {
            font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
            padding: 1px 5px; border-radius: 2px;
        }
        .umi-ph-src-session { color: var(--umi-ok); background: var(--umi-ok-wash); }
        .umi-ph-src-disk { color: var(--umi-accent); background: var(--umi-accent-wash); }
        .umi-ph-actions { margin-left: auto; display: flex; gap: 6px; }
        .umi-ph-mini {
            background: none; border: 1px solid var(--umi-rule-strong); border-radius: 3px;
            color: var(--umi-ink-2); font-size: 10px; padding: 2px 7px; cursor: pointer;
            font-family: inherit; letter-spacing: 0.04em; text-transform: uppercase;
        }
        .umi-ph-mini:hover { color: var(--umi-ink-strong); border-color: var(--umi-accent); }
        .umi-ph-text {
            padding: 9px 11px; white-space: pre-wrap; word-break: break-word;
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
            line-height: 1.55; max-height: 190px; overflow-y: auto;
        }
        .umi-ph-neg {
            padding: 7px 11px 9px; border-top: 1px dashed var(--umi-rule);
            color: var(--umi-negative); white-space: pre-wrap; word-break: break-word;
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
        }
        .umi-ph-neg-label {
            color: var(--umi-ink-3); font-size: 10px; letter-spacing: 0.08em;
            text-transform: uppercase; display: block; margin-bottom: 3px;
        }
    `;
    document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// store
// ---------------------------------------------------------------------------

const store = {
    session: [],
    add(entry) {
        if (!entry || (!entry.prompt && !entry.negative)) return;
        const last = this.session[0];
        if (last && last.prompt === entry.prompt && last.negative === entry.negative) return;
        this.session.unshift({
            timestamp: new Date().toISOString(),
            prompt: entry.prompt || "",
            negative: entry.negative || "",
            seed: entry.seed ?? null,
            source: "session",
        });
        if (this.session.length > MAX_SESSION_ENTRIES) this.session.length = MAX_SESSION_ENTRIES;
    },
};

async function fetchStored() {
    try {
        const resp = await api.fetchApi("/umiapp/prompt-history");
        if (!resp.ok) return { persist: false, entries: [] };
        const data = await resp.json();
        return {
            persist: !!data.persist,
            entries: (data.entries || []).map((e) => ({ ...e, source: "disk" })),
        };
    } catch (e) {
        console.warn("[UmiAI] Could not read prompt history:", e);
        return { persist: false, entries: [] };
    }
}

async function setPersist(enabled) {
    try {
        const resp = await api.fetchApi("/umiapp/settings/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ settings: { persist_prompt_history: !!enabled } }),
        });
        return resp.ok;
    } catch (e) {
        console.warn("[UmiAI] Could not change prompt history persistence:", e);
        return false;
    }
}

async function clearStored() {
    try {
        const resp = await api.fetchApi("/umiapp/prompt-history/clear", { method: "POST" });
        return resp.ok;
    } catch (e) {
        console.warn("[UmiAI] Could not clear prompt history:", e);
        return false;
    }
}

// ---------------------------------------------------------------------------
// panel
// ---------------------------------------------------------------------------

function formatStamp(iso) {
    if (!iso) return "unknown time";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
}

function sendToSelectedNode(text) {
    const selected = Object.values(app.canvas?.selected_nodes || {});
    const target = selected.find((n) => n.widgets?.some((w) => w.name === "text"));
    if (!target) {
        alert("Select a Umi Wildcard Processor node first, then reuse the prompt.");
        return;
    }
    const widget = target.widgets.find((w) => w.name === "text");
    widget.value = text;
    if (widget.inputEl) widget.inputEl.value = text;
    app.graph.setDirtyCanvas(true, true);
}

class PromptHistoryPanel {
    constructor() {
        this.overlay = null;
        this.filter = "";
        this.persist = false;
        this.stored = [];
    }

    async show() {
        ensureStyles();
        const state = await fetchStored();
        this.persist = state.persist;
        this.stored = state.entries;
        this.render();
    }

    close() {
        this.overlay?.remove();
        this.overlay = null;
        document.removeEventListener("keydown", this._onKey);
    }

    entries() {
        const all = [...store.session, ...this.stored];
        const needle = this.filter.trim().toLowerCase();
        if (!needle) return all;
        return all.filter(
            (e) =>
                (e.prompt || "").toLowerCase().includes(needle) ||
                (e.negative || "").toLowerCase().includes(needle)
        );
    }

    render() {
        this.close();

        const overlay = document.createElement("div");
        overlay.className = "umi-ph-overlay";
        overlay.addEventListener("mousedown", (e) => {
            if (e.target === overlay) this.close();
        });

        const modal = document.createElement("div");
        modal.className = "umi-ph-modal";

        // head
        const head = document.createElement("div");
        head.className = "umi-ph-head";
        const title = document.createElement("div");
        title.className = "umi-ph-title";
        title.textContent = "Prompt History";
        const close = document.createElement("button");
        close.className = "umi-ph-x";
        close.textContent = "×";
        close.title = "Close";
        close.onclick = () => this.close();
        head.append(title, close);

        // controls
        const bar = document.createElement("div");
        bar.className = "umi-ph-bar";

        const search = document.createElement("input");
        search.className = "umi-ph-search";
        search.type = "search";
        search.placeholder = "Filter prompts…";
        search.value = this.filter;
        search.addEventListener("input", () => {
            this.filter = search.value;
            this.paintList();
        });

        const toggleLabel = document.createElement("label");
        toggleLabel.className = "umi-ph-toggle";
        const toggle = document.createElement("input");
        toggle.type = "checkbox";
        toggle.checked = this.persist;
        toggle.addEventListener("change", async () => {
            const ok = await setPersist(toggle.checked);
            if (!ok) {
                toggle.checked = !toggle.checked;
                return;
            }
            this.persist = toggle.checked;
            const state = await fetchStored();
            this.stored = state.entries;
            this.render();
        });
        const toggleText = document.createElement("span");
        toggleText.textContent = "Save history to disk";
        toggleLabel.append(toggle, toggleText);

        const clearBtn = document.createElement("button");
        clearBtn.className = "umi-ph-btn";
        clearBtn.textContent = "Clear saved";
        clearBtn.onclick = async () => {
            if (!confirm("Delete the prompt history saved on disk? This cannot be undone.")) return;
            if (await clearStored()) {
                this.stored = [];
                this.paintList();
            }
        };

        bar.append(search, toggleLabel, clearBtn);

        // note
        const note = document.createElement("div");
        note.className = "umi-ph-note";
        note.textContent = this.persist
            ? "History is being saved to prompt_history.json (last 100 runs)."
            : "History is kept for this session only. Turn on “Save history to disk” to keep it across restarts.";

        // list
        this.list = document.createElement("div");
        this.list.className = "umi-ph-list";

        modal.append(head, bar, note, this.list);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this.overlay = overlay;

        this._onKey = (e) => { if (e.key === "Escape") this.close(); };
        document.addEventListener("keydown", this._onKey);

        this.paintList();
        search.focus();
    }

    paintList() {
        const rows = this.entries();
        this.list.innerHTML = "";

        if (!rows.length) {
            const empty = document.createElement("div");
            empty.className = "umi-ph-empty";
            empty.textContent = this.filter
                ? "No prompts match that filter."
                : "No prompts yet. Run a workflow with Umi Save Image to record one.";
            this.list.appendChild(empty);
            return;
        }

        rows.forEach((entry) => {
            const item = document.createElement("div");
            item.className = "umi-ph-item";

            const itemHead = document.createElement("div");
            itemHead.className = "umi-ph-item-head";

            const src = document.createElement("span");
            src.className = `umi-ph-src umi-ph-src-${entry.source}`;
            src.textContent = entry.source === "session" ? "this session" : "saved";

            const stamp = document.createElement("span");
            stamp.textContent = formatStamp(entry.timestamp);

            itemHead.append(src, stamp);

            if (entry.seed !== null && entry.seed !== undefined) {
                const seed = document.createElement("span");
                seed.textContent = `seed ${entry.seed}`;
                itemHead.appendChild(seed);
            }

            const actions = document.createElement("div");
            actions.className = "umi-ph-actions";

            const copy = document.createElement("button");
            copy.className = "umi-ph-mini";
            copy.textContent = "Copy";
            copy.onclick = async () => {
                try {
                    await navigator.clipboard.writeText(entry.prompt || "");
                    copy.textContent = "Copied";
                    setTimeout(() => { copy.textContent = "Copy"; }, 1200);
                } catch {
                    copy.textContent = "Failed";
                }
            };

            const reuse = document.createElement("button");
            reuse.className = "umi-ph-mini";
            reuse.textContent = "Reuse";
            reuse.title = "Put this prompt into the selected Wildcard Processor node";
            reuse.onclick = () => sendToSelectedNode(entry.prompt || "");

            actions.append(copy, reuse);
            itemHead.appendChild(actions);

            const text = document.createElement("div");
            text.className = "umi-ph-text";
            text.textContent = entry.prompt || "(no positive prompt)";

            item.append(itemHead, text);

            if (entry.negative) {
                const neg = document.createElement("div");
                neg.className = "umi-ph-neg";
                const label = document.createElement("span");
                label.className = "umi-ph-neg-label";
                label.textContent = "Negative";
                neg.appendChild(label);
                neg.appendChild(document.createTextNode(entry.negative));
                item.appendChild(neg);
            }

            this.list.appendChild(item);
        });
    }
}

const panel = new PromptHistoryPanel();
window.umiPromptHistory = panel;
window.umiPromptHistoryStore = store;

// ---------------------------------------------------------------------------
// prompt display under the Umi Save Image node
// ---------------------------------------------------------------------------

const COLLAPSED_H = 22;
const EXPANDED_H = 150;

function ensureNodeWidget(node) {
    let widget = node.widgets?.find((w) => w.name === "umi_prompt_shown");
    if (widget) return widget;
    if (typeof node.addDOMWidget !== "function") return null;

    const wrap = document.createElement("div");
    Object.assign(wrap.style, {
        boxSizing: "border-box",
        width: "100%",
        overflow: "hidden",
        background: "var(--umi-ground)",
        color: "var(--umi-ink)",
        border: "1px solid var(--umi-rule-strong)",
        borderRadius: "4px",
        fontFamily: "ui-monospace, Consolas, monospace",
        fontSize: "11px",
        lineHeight: "1.5",
    });

    // One-line header, always visible; the body is what folds away. Collapsed
    // by default so the image gets the node's vertical space -- ComfyUI draws
    // images below every widget, so a tall panel here squeezes the picture.
    const header = document.createElement("div");
    header.setAttribute('role', 'button');
    header.tabIndex = 0;
    header.setAttribute('aria-expanded', 'false');
    Object.assign(header.style, {
        display: "flex", alignItems: "center", gap: "6px",
        padding: "3px 7px", cursor: "pointer", userSelect: "none",
        color: "var(--umi-ink-3)", fontSize: "10px",
        letterSpacing: "0.06em", textTransform: "uppercase",
    });

    const twisty = document.createElement("span");
    twisty.textContent = "\u25b6";
    twisty.style.transition = "transform 0.12s";

    const title = document.createElement("span");
    title.textContent = "Prompt";
    title.style.flex = "1";

    header.append(twisty, title);

    const body = document.createElement("div");
    Object.assign(body.style, {
        display: "none",
        padding: "0 8px 7px",
        maxHeight: (EXPANDED_H - COLLAPSED_H) + "px",
        overflowY: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
    });

    wrap.append(header, body);

    widget = node.addDOMWidget("umi_prompt_shown", "div", wrap, {
        serialize: false,
        hideOnZoom: false,
    });
    widget.umiEl = body;
    widget.umiHeader = title;
    widget.umiExpanded = false;

    // Declaring the height is what makes node resizing behave: without it the
    // widget's contribution to layout is whatever the DOM happens to measure,
    // which does not track the node's size.
    widget.computeSize = () => [node.size?.[0] ?? 200,
                                widget.umiExpanded ? EXPANDED_H : COLLAPSED_H];

    const setExpanded = (open) => {
        header.setAttribute('aria-expanded', String(open));
        widget.umiExpanded = open;
        body.style.display = open ? "block" : "none";
        twisty.style.transform = open ? "rotate(90deg)" : "none";
        node.setDirtyCanvas?.(true, true);
        node.onResize?.(node.size);
    };
    header.onclick = () => setExpanded(!widget.umiExpanded);
    header.onkeydown = event => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setExpanded(!widget.umiExpanded);
        }
    };
    widget.umiSetExpanded = setExpanded;

    return widget;
}

function paintNodePrompt(node, prompt, negative, warning = "", images = []) {
    const widget = ensureNodeWidget(node);
    if (!widget?.umiEl) return;
    const el = widget.umiEl;
    el.textContent = "";

    // The collapsed header carries enough to be worth reading on its own.
    if (widget.umiHeader) {
        const words = String(prompt || "").split(/\s+/).filter(Boolean).length;
        widget.umiHeader.textContent = warning
            ? "Prompt — metadata warning"
            : prompt || negative
            ? `Prompt — ${words} word${words === 1 ? "" : "s"}`
            : "Prompt — nothing connected";
        if (images?.length) widget.umiHeader.textContent = `Saved ${images.length} · ` + widget.umiHeader.textContent;
    }

    if (images?.length) {
        const saved = document.createElement('div');
        saved.style.cssText = 'margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid var(--umi-rule);overflow-wrap:anywhere;color:var(--umi-ink);';
        const paths = images.map(item => [item.subfolder, item.filename].filter(Boolean).join('/'));
        saved.textContent = `Output: ${paths[0]}` + (paths.length > 1 ? ` (+${paths.length - 1} more)` : '');
        saved.title = 'Saved relative to the ComfyUI output folder:\n' + paths.join('\n');
        el.appendChild(saved);
    }

    if (warning) {
        const warningEl = document.createElement("div");
        Object.assign(warningEl.style, {
            marginBottom: prompt || negative ? "6px" : "0",
            padding: "5px 6px",
            border: "1px solid var(--umi-warn)",
            borderRadius: "4px",
            color: "var(--umi-warn)",
            background: "var(--umi-warn-wash)",
        });
        warningEl.textContent = warning;
        el.appendChild(warningEl);
    }

    if (!prompt && !negative) {
        if (!warning) {
            const hint = document.createElement('div');
            hint.textContent = "No prompt connected. Wire the Wildcard Processor's "
                + "text output into positive_prompt.";
            el.appendChild(hint);
            el.style.color = "var(--umi-ink-3)";
        }
        return;
    }
    el.style.color = "var(--umi-ink)";

    if (prompt) {
        el.appendChild(document.createTextNode(prompt));
    }
    if (negative) {
        const rule = document.createElement("div");
        Object.assign(rule.style, {
            marginTop: "6px", paddingTop: "5px",
            borderTop: "1px dashed var(--umi-rule-strong)", color: "var(--umi-negative)",
        });
        const label = document.createElement("div");
        Object.assign(label.style, {
            color: "var(--umi-ink-3)", fontSize: "9px", letterSpacing: "0.08em",
            textTransform: "uppercase", marginBottom: "2px",
        });
        label.textContent = "Negative";
        rule.appendChild(label);
        rule.appendChild(document.createTextNode(negative));
        el.appendChild(rule);
    }

    node.setDirtyCanvas?.(true, true);
}

function firstValue(payload, key) {
    const value = payload?.[key];
    if (Array.isArray(value)) return value[0] || "";
    return typeof value === "string" ? value : "";
}

app.registerExtension({
    name: "Umi.PromptHistory",

    async setup() {
        ensureStyles();

        // Record every Umi Save Image run, whether or not the panel is open.
        api.addEventListener("executed", ({ detail }) => {
            const payload = detail?.output;
            if (!payload) return;
            const prompt = firstValue(payload, "umi_prompt");
            const negative = firstValue(payload, "umi_negative");
            const warning = firstValue(payload, "umi_metadata_warning");
            if (!prompt && !negative && !warning) return;

            if (prompt || negative) store.add({ prompt, negative });

            const node = app.graph?.getNodeById?.(detail.node);
            if (node && node.comfyClass === "UmiSaveImage") {
                paintNodePrompt(node, prompt, negative, warning, payload.images);
            }
        });
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== "UmiSaveImage") return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            paintNodePrompt(
                this,
                firstValue(message, "umi_prompt"),
                firstValue(message, "umi_negative"),
                firstValue(message, "umi_metadata_warning"),
                message?.images
            );
        };

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            // Give the node its panel up front so it does not jump size on the
            // first execution.
            paintNodePrompt(this, "", "");
        };
    },
});
