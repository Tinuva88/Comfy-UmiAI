import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ensureUmiTheme } from "./umi_theme.js";

// =============================================================================
// Self check
//
// Everything in this pack's frontend is written against assumptions about the
// host: that node.addDOMWidget exists, that ComfyUI publishes theme variables
// on :root, that the routes are mounted, that panels registered. When one of
// those is false the symptom is usually a feature that silently does not
// appear -- indistinguishable from a feature that was never built.
//
// This asks each question out loud and reports the answer, so a single pass in
// a running ComfyUI produces a definitive list instead of an impression.
//
// Note: this file deliberately uses literal colours rather than the shared
// design tokens. A diagnostic has to stay readable even when the thing it is
// diagnosing -- including the token system -- is the thing that is broken.
// =============================================================================

const STYLE_ID = "umi-self-check-style";

const PASS = "pass";
const FAIL = "fail";
const WARN = "warn";
const INFO = "info";

function ensureStyles() {
    // The panel's own styles are tokens now, so declare them first.
    ensureUmiTheme();
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        .umi-sc-overlay {
            position: fixed; inset: 0; z-index: 10060;
            background: rgba(0,0,0,0.66);
            display: flex; align-items: center; justify-content: center;
        }
        .umi-sc-modal {
            width: min(840px, 94vw); height: min(760px, 90vh);
            display: flex; flex-direction: column;
            background: var(--umi-ground); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 6px;
            box-shadow: 0 18px 48px rgba(0,0,0,0.6);
            font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
        }
        .umi-sc-head {
            display: flex; align-items: center; gap: 12px;
            padding: 12px 16px; border-bottom: 1px solid var(--umi-rule);
        }
        .umi-sc-title { font-size: 15px; font-weight: 600; margin-right: auto; }
        .umi-sc-btn {
            background: var(--umi-surface-alt); color: var(--umi-ink); border: 1px solid var(--umi-rule-strong);
            border-radius: 4px; padding: 6px 11px; cursor: pointer; font: inherit;
        }
        .umi-sc-btn:hover { background: var(--umi-surface-hover); }
        .umi-sc-x {
            background: none; border: none; color: var(--umi-ink);
            font-size: 20px; line-height: 1; cursor: pointer; padding: 0 4px;
        }
        .umi-sc-x:hover { color: var(--umi-ink-strong); }
        .umi-sc-tally {
            padding: 9px 16px; border-bottom: 1px solid var(--umi-rule);
            background: var(--umi-ground); font-family: ui-monospace, Consolas, monospace;
            font-size: 12px;
        }
        .umi-sc-body { flex: 1; overflow-y: auto; padding: 10px 12px; }
        .umi-sc-group {
            font-family: ui-monospace, Consolas, monospace;
            font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
            color: var(--umi-ink-2); margin: 14px 4px 5px;
        }
        .umi-sc-row {
            display: grid; grid-template-columns: 4.2rem 1fr;
            gap: 10px; padding: 6px 8px; border-bottom: 1px solid var(--umi-rule);
            align-items: start;
        }
        .umi-sc-badge {
            font-family: ui-monospace, Consolas, monospace;
            font-size: 9px; font-weight: 700; letter-spacing: 0.09em;
            text-transform: uppercase; padding: 2px 5px; border-radius: 2px;
            text-align: center;
        }
        .umi-sc-pass { color: var(--umi-ok); background: var(--umi-ok-wash); }
        .umi-sc-fail { color: var(--umi-danger); background: var(--umi-surface); }
        .umi-sc-warn { color: var(--umi-warn); background: var(--umi-surface-alt); }
        .umi-sc-info { color: var(--umi-accent); background: var(--umi-accent-wash); }
        .umi-sc-label { font-weight: 600; }
        .umi-sc-detail {
            color: var(--umi-ink); font-family: ui-monospace, Consolas, monospace;
            font-size: 11px; word-break: break-word; margin-top: 2px;
        }
        .umi-sc-fix { color: var(--umi-warn); font-size: 12px; margin-top: 3px; }
    `;
    document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// checks
// ---------------------------------------------------------------------------

/** A node instance to interrogate, preferring a Umi one. */
function sampleNode() {
    const nodes = app.graph?._nodes || [];
    return nodes.find((n) => String(n.comfyClass || n.type || "").startsWith("Umi"))
        || nodes[0]
        || null;
}

function checkHost() {
    const out = [];

    const version = window.__COMFYUI_FRONTEND_VERSION__
        || app.frontendVersion
        || document.querySelector("meta[name='comfyui-frontend-version']")?.content
        || "unknown";
    out.push({ status: INFO, label: "ComfyUI frontend version", detail: String(version) });

    const node = sampleNode();
    if (!node) {
        out.push({
            status: WARN,
            label: "node.addDOMWidget",
            detail: "no nodes on the canvas to test against",
            fix: "Add a UmiAI Wildcard Processor node and run this again — the prompt display and roll preview both depend on this.",
        });
    } else {
        const has = typeof node.addDOMWidget === "function";
        out.push({
            status: has ? PASS : FAIL,
            label: "node.addDOMWidget",
            detail: `tested on ${node.comfyClass || node.type}`,
            fix: has ? null
                : "This frontend has no addDOMWidget. The Save Image prompt display and the roll preview panel cannot render; both fail silently today.",
        });
    }

    const registered = window.LiteGraph?.registered_node_types || {};
    const wanted = ["UmiAIWildcardNode", "UmiSaveImage", "UmiPromptInspector"];
    const missing = wanted.filter((n) => !registered[n]);
    out.push({
        status: missing.length ? FAIL : PASS,
        label: "Umi nodes registered",
        detail: missing.length ? `missing: ${missing.join(", ")}` : `${wanted.length} of ${wanted.length} present`,
        fix: missing.length ? "The Python side did not import cleanly. Check the ComfyUI console for a C-UMI traceback at startup." : null,
    });

    return out;
}

function checkTokens() {
    const out = [];
    const root = getComputedStyle(document.documentElement);
    const injected = Boolean(document.getElementById("umi-theme-tokens"));

    out.push({
        status: injected ? PASS : FAIL,
        label: "token stylesheet injected",
        detail: injected ? "#umi-theme-tokens present" : "not found in <head>",
        fix: injected ? null : "ensureUmiTheme() never ran. Panels will fall back to unstyled colours.",
    });

    const probes = [
        ["--umi-ground", "--comfy-menu-bg"],
        ["--umi-ink", "--input-text"],
        ["--umi-rule", "--border-color"],
    ];
    let inherited = 0;
    let resolved = 0;
    for (const [token, host] of probes) {
        const tokenValue = root.getPropertyValue(token).trim();
        const hostValue = root.getPropertyValue(host).trim();
        if (tokenValue) resolved += 1;
        if (hostValue && tokenValue === hostValue) inherited += 1;
    }

    out.push({
        status: resolved === probes.length ? PASS : FAIL,
        label: "tokens resolve to a value",
        detail: `${resolved} of ${probes.length} resolved`,
        fix: resolved === probes.length ? null : "Tokens are empty; panel colours will be blank rather than themed.",
    });

    // theme_manager.js was retired: it was a second theme system that wrote
    // inline styles over the tokens. Removing it from the bundle cannot remove
    // it from an install that already has it, so say so if it is still loaded.
    const stale = Boolean(globalThis.window && window.umiThemeManager);
    out.push({
        status: stale ? WARN : PASS,
        label: "no retired theme manager loaded",
        detail: stale ? "window.umiThemeManager is present" : "none",
        fix: stale ? "Delete js/theme_manager.js from this install. It writes inline colours over the shared tokens, so panels ignore your theme."
                   : null,
    });

    out.push({
        status: inherited === probes.length ? PASS : WARN,
        label: "tokens follow the ComfyUI theme",
        detail: `${inherited} of ${probes.length} inherited from the host; the rest used the built-in fallback`,
        fix: inherited === probes.length ? null
            : "Panels still render, but with the packaged dark palette rather than your theme. Expected on older frontends.",
    });

    return out;
}

function checkPanels() {
    const expected = [
        ["umiShowHelpModal", "User Guide", "function"],
        ["umiRunInspector", "Run Inspector", "show"],
        ["umiPromptHistory", "Prompt History", "show"],
        ["umiLoraBrowser", "LoRA Browser", "show"],
        ["umiImageBrowser", "Image Browser", "show"],
        ["umiDanbooruBrowser", "Danbooru Browser", "show"],
        ["umiSettingsDialog", "Settings", "show"],
    ];
    const out = expected.map(([global, label, kind]) => {
        const value = window[global];
        const ok = kind === "function"
            ? typeof value === "function"
            : typeof value?.show === "function";
        return {
            status: ok ? PASS : FAIL,
            label,
            detail: `window.${global}`,
            fix: ok ? null : `Did not register. Look for a script error from ${global} in the browser console.`,
        };
    });

    const nativeTab = typeof app.extensionManager?.registerSidebarTab === "function";
    const fallback = Boolean(document.getElementById("umi-sidebar-fallback"));
    out.push({
        status: nativeTab && !fallback ? PASS : (fallback ? WARN : INFO),
        label: "sidebar surface",
        detail: fallback ? "fallback launcher is showing" : (nativeTab ? "native sidebar tab" : "sidebar API unavailable"),
        fix: fallback ? "The native tab did not register within the watch window; the floating UmiAI button is standing in." : null,
    });

    return out;
}

async function checkRoutes() {
    const out = [];

    const probes = [
        ["/umiapp/settings", "GET", null, "settings"],
        ["/umiapp/wildcards", "GET", null, "wildcards"],
        ["/umiapp/prompt-history", "GET", null, "prompt history"],
        // An empty prompt is rejected with 400, which proves the route is
        // mounted without making it expand anything.
        ["/umiapp/preview-roll", "POST", { text: "" }, "roll preview"],
    ];

    for (const [path, method, body, label] of probes) {
        try {
            const response = await api.fetchApi(path, body
                ? { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
                : { method });
            const reachable = response.status !== 404;
            out.push({
                status: reachable ? PASS : FAIL,
                label: `${label} route`,
                detail: `${method} ${path} → ${response.status}`,
                fix: reachable ? null : "Route not mounted. The Python side may have failed to import, or UI tools are disabled.",
            });
        } catch (error) {
            out.push({
                status: FAIL, label: `${label} route`,
                detail: `${method} ${path} → ${error.message}`,
                fix: "Request failed outright. Check the ComfyUI server log.",
            });
        }
    }

    return out;
}

async function checkSettings() {
    const out = [];
    let settings = null;
    try {
        const response = await api.fetchApi("/umiapp/settings");
        settings = (await response.json())?.settings || null;
    } catch { /* reported by the route check */ }

    if (!settings) {
        out.push({ status: WARN, label: "settings readable", detail: "could not read /umiapp/settings" });
        return out;
    }

    // "Off" is not one thing. Prompt history off still leaves a working panel
    // with this session's runs and a toggle; run capture off leaves the Run
    // Inspector with nothing to show at all. Only the second is worth flagging.
    const gates = [
        {
            key: "lint_cleaner_enabled", what: "live syntax errors in the editor",
            offStatus: WARN,
            offFix: "Off, so a mistyped wildcard reaches the output as [WILDCARD_NOT_FOUND: name] with no warning while you type.",
        },
        {
            key: "enable_tag_autocomplete", what: "tag autocomplete",
            offStatus: WARN, offFix: "Off, so no tag suggestions appear while typing.",
        },
        {
            key: "persist_run_inspector", what: "run capture for the inspector",
            offStatus: WARN,
            offFix: "Off, so the Run Inspector has nothing to show. It offers a button to turn this on.",
        },
        {
            key: "persist_prompt_history", what: "prompt history on disk",
            // Deliberately off by default for privacy, and the panel still
            // works from memory, so this is not a problem to report.
            offStatus: PASS,
            offFix: null,
        },
    ];
    for (const gate of gates) {
        const on = Boolean(settings[gate.key]);
        out.push({
            status: on ? PASS : gate.offStatus,
            label: gate.what,
            detail: `${gate.key} = ${on}`,
            fix: on ? null : gate.offFix,
        });
    }

    if (settings.enable_debug_output) {
        out.push({
            status: INFO, label: "debug logging",
            detail: "enable_debug_output = true",
            fix: "Verbose logging is on; expect a noisy console.",
        });
    }

    return out;
}

function checkEditor() {
    const backdrop = document.querySelector(".umi-syntax-backdrop");
    const lintBar = document.querySelector(".umi-lint-bar");
    const out = [];

    out.push({
        status: backdrop ? PASS : WARN,
        label: "syntax highlighting attached",
        detail: backdrop ? "highlight overlay found" : "no highlighted textarea on screen",
        fix: backdrop ? null : "Open a Umi Wildcard Processor node so its prompt box is visible, then run this again.",
    });

    if (backdrop) {
        out.push({
            status: lintBar ? PASS : WARN,
            label: "lint bar present",
            detail: lintBar ? "visible" : "not rendered",
            fix: lintBar ? null : "Live linting may still be switched off, or the bar failed to attach.",
        });
    }

    return out;
}

// ---------------------------------------------------------------------------
// panel
// ---------------------------------------------------------------------------

async function collect() {
    return [
        ["Host", checkHost()],
        ["Design tokens", checkTokens()],
        ["Panels", checkPanels()],
        ["Routes", await checkRoutes()],
        ["Settings", await checkSettings()],
        ["Editor", checkEditor()],
    ];
}

function asText(groups) {
    const lines = ["UmiAI self check", new Date().toISOString(), ""];
    for (const [name, rows] of groups) {
        lines.push(`## ${name}`);
        for (const row of rows) {
            lines.push(`  [${row.status.toUpperCase().padEnd(4)}] ${row.label} — ${row.detail || ""}`);
            if (row.fix) lines.push(`         ${row.fix}`);
        }
        lines.push("");
    }
    const all = groups.flatMap(([, rows]) => rows);
    const count = (s) => all.filter((r) => r.status === s).length;
    lines.push(`pass ${count(PASS)} · fail ${count(FAIL)} · warn ${count(WARN)} · info ${count(INFO)}`);
    return lines.join("\n");
}

class SelfCheckPanel {
    constructor() {
        this.overlay = null;
    }

    close() {
        this.overlay?.remove();
        this.overlay = null;
        document.removeEventListener("keydown", this._onKey);
    }

    async show() {
        ensureStyles();
        this.close();
        const groups = await collect();
        this.groups = groups;

        const overlay = document.createElement("div");
        overlay.className = "umi-sc-overlay";
        overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) this.close(); });

        const modal = document.createElement("div");
        modal.className = "umi-sc-modal";

        const head = document.createElement("div");
        head.className = "umi-sc-head";
        const title = document.createElement("div");
        title.className = "umi-sc-title";
        title.textContent = "UmiAI Self Check";

        const copy = document.createElement("button");
        copy.className = "umi-sc-btn";
        copy.textContent = "Copy report";
        copy.onclick = async () => {
            try {
                await navigator.clipboard.writeText(asText(this.groups));
                copy.textContent = "Copied";
                setTimeout(() => { copy.textContent = "Copy report"; }, 1400);
            } catch {
                copy.textContent = "Copy failed";
            }
        };

        const rerun = document.createElement("button");
        rerun.className = "umi-sc-btn";
        rerun.textContent = "Run again";
        rerun.onclick = () => this.show();

        const close = document.createElement("button");
        close.className = "umi-sc-x";
        close.textContent = "×";
        close.onclick = () => this.close();

        head.append(title, rerun, copy, close);

        const all = groups.flatMap(([, rows]) => rows);
        const count = (s) => all.filter((r) => r.status === s).length;
        const tally = document.createElement("div");
        tally.className = "umi-sc-tally";
        tally.textContent = `${count(PASS)} pass · ${count(FAIL)} fail · ${count(WARN)} warn · ${count(INFO)} info`;

        const body = document.createElement("div");
        body.className = "umi-sc-body";

        for (const [name, rows] of groups) {
            const heading = document.createElement("div");
            heading.className = "umi-sc-group";
            heading.textContent = name;
            body.appendChild(heading);

            for (const row of rows) {
                const el = document.createElement("div");
                el.className = "umi-sc-row";

                const badge = document.createElement("span");
                badge.className = `umi-sc-badge umi-sc-${row.status}`;
                badge.textContent = row.status;

                const right = document.createElement("div");
                const labelEl = document.createElement("div");
                labelEl.className = "umi-sc-label";
                labelEl.textContent = row.label;
                right.appendChild(labelEl);

                if (row.detail) {
                    const detail = document.createElement("div");
                    detail.className = "umi-sc-detail";
                    detail.textContent = row.detail;
                    right.appendChild(detail);
                }
                if (row.fix) {
                    const fix = document.createElement("div");
                    fix.className = "umi-sc-fix";
                    fix.textContent = row.fix;
                    right.appendChild(fix);
                }

                el.append(badge, right);
                body.appendChild(el);
            }
        }

        modal.append(head, tally, body);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this.overlay = overlay;

        this._onKey = (e) => { if (e.key === "Escape") this.close(); };
        document.addEventListener("keydown", this._onKey);
    }

    /** Console-friendly: umiSelfCheck.report() -> plain text. */
    async report() {
        const text = asText(await collect());
        console.log(text);
        return text;
    }
}

const panel = new SelfCheckPanel();
window.umiSelfCheck = panel;

app.registerExtension({
    name: "Umi.SelfCheck",
    async setup() {
        ensureStyles();
    },
});

export { collect, asText, checkHost, checkTokens, checkPanels, checkEditor };
