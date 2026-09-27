import { app } from "../../scripts/app.js";
import { ensureUmiTheme, T } from "./umi_theme.js";

const SIDEBAR_STYLE_ID = "umi-sidebar-style";
const FALLBACK_ID = "umi-sidebar-fallback";

function ensureStyles() {
    ensureUmiTheme();
    if (document.getElementById(SIDEBAR_STYLE_ID)) return;

    const style = document.createElement("style");
    style.id = SIDEBAR_STYLE_ID;
    style.textContent = `
        .umi-sidebar-menu {
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 12px;
            background: var(--umi-ground);
            height: 100%;
            box-sizing: border-box;
            overflow-y: auto;
        }
        .umi-sidebar-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--umi-accent);
            margin-bottom: 4px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--umi-rule);
        }
        .umi-sidebar-section {
            color: var(--umi-ink-3);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin: 10px 2px 2px;
        }
        .umi-sidebar-btn {
            background: var(--umi-surface);
            color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong);
            padding: 10px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            text-align: left;
            transition: all 0.18s;
            display: flex;
            align-items: center;
            gap: 8px;
            width: 100%;
            box-sizing: border-box;
        }
        .umi-sidebar-btn-off {
            opacity: 0.55;
            cursor: not-allowed;
            font-style: italic;
        }
        .umi-sidebar-btn-off:hover {
            background: inherit;
        }
        .umi-sidebar-btn-note {
            margin-left: auto;
            font-size: 10px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.8;
        }
        .umi-sidebar-btn:hover {
            background: var(--umi-surface-hover);
            border-color: var(--umi-accent);
            color: var(--umi-ink-strong);
        }
        .umi-sidebar-icon {
            width: 22px;
            height: 22px;
            border-radius: 4px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--umi-sunken);
            border: 1px solid var(--umi-rule-strong);
            color: var(--umi-accent);
            font-weight: 700;
            font-size: 12px;
            flex: 0 0 auto;
        }
        .umi-sidebar-card {
            background: var(--umi-surface);
            border: 1px solid var(--umi-rule);
            border-radius: 6px;
            padding: 10px;
            color: var(--umi-ink-2);
            font-size: 12px;
            line-height: 1.45;
            margin-top: 10px;
        }
        .umi-sidebar-card code {
            display: inline-block;
            color: var(--umi-accent);
            background: var(--umi-sunken);
            border: 1px solid var(--umi-rule);
            border-radius: 3px;
            padding: 1px 4px;
            margin-top: 3px;
        }
        .umi-sidebar-footer {
            margin-top: auto;
            font-size: 10px;
            color: var(--umi-ink-3);
            text-align: center;
            padding-top: 10px;
        }
        .umi-sidebar-fallback {
            position: fixed;
            left: 0;
            top: 96px;
            z-index: 10020;
            display: flex;
            align-items: flex-start;
            pointer-events: none;
        }
        .umi-sidebar-fallback-toggle {
            pointer-events: auto;
            writing-mode: vertical-rl;
            transform: rotate(180deg);
            background: var(--umi-surface);
            color: var(--umi-accent);
            border: 1px solid var(--umi-rule-strong);
            border-left: 0;
            border-radius: 0 6px 6px 0;
            padding: 10px 6px;
            cursor: pointer;
            font-weight: 700;
        }
        .umi-sidebar-fallback-panel {
            pointer-events: auto;
            width: 260px;
            max-height: min(620px, calc(100vh - 120px));
            display: none;
            border: 1px solid var(--umi-rule-strong);
            box-shadow: 0 12px 32px rgba(0,0,0,0.45);
        }
        .umi-sidebar-fallback.open .umi-sidebar-fallback-panel {
            display: block;
        }
    `;
    document.head.appendChild(style);
}

function makeButton(tool, unavailableReason) {
    const btn = document.createElement("button");
    btn.className = "umi-sidebar-btn";

    const icon = document.createElement("span");
    icon.className = "umi-sidebar-icon";
    icon.textContent = tool.icon;
    const label = document.createElement("span");
    label.textContent = tool.label;
    btn.append(icon, label);

    if (unavailableReason) {
        // A panel whose script failed to load used to be filtered out of the
        // menu entirely, which is indistinguishable from a panel that was
        // never built. Show it, disabled, carrying the reason.
        btn.classList.add("umi-sidebar-btn-off");
        btn.disabled = true;
        btn.title = unavailableReason;
        const note = document.createElement("span");
        note.className = "umi-sidebar-btn-note";
        note.textContent = "not loaded";
        btn.appendChild(note);
    } else {
        btn.onclick = () => tool.action?.();
    }
    return btn;
}

function renderMenu(el) {
    const container = document.createElement("div");
    container.className = "umi-sidebar-menu";

    const title = document.createElement("div");
    title.className = "umi-sidebar-title";
    title.textContent = "UmiAI Control Panel";
    container.appendChild(title);

    // Every entry declares the global it needs, so a missing panel can be named
    // in the tooltip and the console instead of vanishing from the menu.
    const sections = [
        {
            title: "Prompting",
            tools: [
                {
                    label: "User Guide", icon: "?", global: "umiShowHelpModal",
                    available: () => typeof window.umiShowHelpModal === "function",
                    action: () => window.umiShowHelpModal?.(),
                },
                {
                    label: "Run Inspector", icon: "i", global: "umiRunInspector",
                    available: () => typeof window.umiRunInspector?.show === "function",
                    action: () => window.umiRunInspector?.show(),
                },
                {
                    label: "Prompt History", icon: "H", global: "umiPromptHistory",
                    available: () => typeof window.umiPromptHistory?.show === "function",
                    action: () => window.umiPromptHistory?.show(),
                },
            ],
        },
        {
            title: "Assets",
            tools: [
                {
                    label: "Wildcards", icon: "W", global: "umiWildcardBrowser",
                    available: () => typeof window.umiWildcardBrowser?.show === "function",
                    action: () => window.umiWildcardBrowser?.show(),
                },
                {
                    label: "LoRA Browser", icon: "L", global: "umiLoraBrowser",
                    available: () => typeof window.umiLoraBrowser?.show === "function",
                    action: () => window.umiLoraBrowser?.show(),
                },
                {
                    label: "Image Browser", icon: "I", global: "umiImageBrowser",
                    available: () => typeof window.umiImageBrowser?.show === "function",
                    action: () => window.umiImageBrowser?.show(),
                },
                {
                    label: "Danbooru Browser", icon: "D", global: "umiDanbooruBrowser",
                    available: () => typeof window.umiDanbooruBrowser?.show === "function",
                    action: () => window.umiDanbooruBrowser?.show(),
                },
            ],
        },
        {
            title: "Diagnostics",
            tools: [
                {
                    label: "Self Check", icon: "!", global: "umiSelfCheck",
                    available: () => typeof window.umiSelfCheck?.show === "function",
                    action: () => window.umiSelfCheck?.show(),
                },
            ],
        },
        {
            title: "Files",
            tools: [
                {
                    label: "Settings", icon: "*", global: "umiSettingsDialog",
                    available: () => typeof window.umiSettingsDialog?.show === "function",
                    action: () => window.umiSettingsDialog?.show(),
                },
            ],
        },
    ];

    const missing = [];
    sections.forEach(section => {
        const heading = document.createElement("div");
        heading.className = "umi-sidebar-section";
        heading.textContent = section.title;
        container.appendChild(heading);
        section.tools.forEach(tool => {
            const ready = !tool.available || tool.available();
            let reason = null;
            if (!ready) {
                const name = tool.global ? `window.${tool.global}` : tool.label;
                reason = `${tool.label} has not registered (${name} is missing). `
                       + `Open the browser console and look for an error in the C-UMI web scripts.`;
                missing.push(tool.global || tool.label);
            }
            container.appendChild(makeButton(tool, reason));
        });
    });

    if (missing.length) {
        console.warn(
            `[UmiAI] Sidebar: ${missing.length} panel(s) did not register: ${missing.join(", ")}. `
            + `Those buttons are shown disabled. A script error earlier in the load order is the usual cause.`
        );
    } else {
        console.log("[UmiAI] Sidebar: all panels registered.");
    }

    const quick = document.createElement("div");
    quick.className = "umi-sidebar-card";
    quick.innerHTML = `
        <strong>Quick Syntax</strong><br>
        <code>__name|fallback__</code><br>
        <code>[choose:a|b:3]</code><br>
        <code>[neg:bad hands]</code><br>
        <code>[lora:name:1 triggers=off]</code>
    `;
    container.appendChild(quick);

    const footer = document.createElement("div");
    footer.className = "umi-sidebar-footer";
    footer.textContent = "UmiAI lean";
    container.appendChild(footer);

    el.innerHTML = "";
    el.appendChild(container);
}

let nativeTabRegistered = false;

function registerNativeSidebar() {
    if (nativeTabRegistered) return true;

    const registerSidebarTab = app.extensionManager?.registerSidebarTab;
    if (!registerSidebarTab) return false;

    nativeTabRegistered = true;
    registerSidebarTab.call(app.extensionManager, {
        id: "umi.sidebar",
        icon: "mdi mdi-head-cog-outline",
        title: "UmiAI",
        tooltip: "UmiAI Tools",
        type: "custom",
        render: renderMenu
    });
    return true;
}

function createFallbackLauncher() {
    if (document.getElementById(FALLBACK_ID)) return;

    const root = document.createElement("div");
    root.id = FALLBACK_ID;
    root.className = "umi-sidebar-fallback";

    const toggle = document.createElement("button");
    toggle.className = "umi-sidebar-fallback-toggle";
    toggle.textContent = "UmiAI";
    toggle.onclick = () => {
        // Availability used to be snapshotted once at construction, so a panel
        // that registered later stayed missing for the whole session.
        if (!root.classList.contains("open")) renderMenu(panel);
        root.classList.toggle("open");
    };

    const panel = document.createElement("div");
    panel.className = "umi-sidebar-fallback-panel";
    renderMenu(panel);

    root.appendChild(toggle);
    root.appendChild(panel);
    document.body.appendChild(root);
}

// How long to keep watching for the sidebar API, and when to put up the
// fallback in the meantime. The old code gave up permanently after 3s, so a
// frontend that finished loading later was stuck on the fallback for the whole
// session even though the real tab had become available.
const WATCH_MS = 30000;
const FALLBACK_AFTER_MS = 2000;

function watchForSidebarApi() {
    const started = Date.now();
    let delay = 250;
    let fallbackShown = false;

    const showFallback = () => {
        if (fallbackShown) return;
        createFallbackLauncher();
        fallbackShown = true;
    };

    const attempt = () => {
        if (registerNativeSidebar()) {
            document.getElementById(FALLBACK_ID)?.remove();
            return;
        }

        const elapsed = Date.now() - started;
        if (elapsed >= FALLBACK_AFTER_MS) showFallback();

        if (elapsed < WATCH_MS) {
            delay = Math.min(Math.round(delay * 1.6), 3000);
            setTimeout(attempt, delay);
        } else {
            showFallback();
            console.log(
                "[UmiAI] Sidebar Tab API did not appear within "
                + Math.round(WATCH_MS / 1000) + "s; staying on the fallback launcher."
            );
        }
    };

    setTimeout(attempt, delay);
}

app.registerExtension({
    name: "Umi.Sidebar",
    async setup() {
        ensureStyles();
        if (registerNativeSidebar()) return;
        watchForSidebarApi();
    }
});
