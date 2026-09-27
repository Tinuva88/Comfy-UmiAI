import { app } from "../../scripts/app.js";
import { ensureUmiTheme, T } from "./umi_theme.js";
import { api } from "../../scripts/api.js";

// =============================================================================
// Roll preview
//
// A wildcard prompt cannot be read for its output -- that is the whole point of
// it -- so the only way to see what a template produces has been to queue the
// workflow. This asks the server to expand the prompt with the current seed and
// shows the result under the node, without running anything.
//
// The server reuses the node's own process() with dry_run, so a preview cannot
// drift from what a real run produces.
// =============================================================================

const NODE_TYPES = new Set(["UmiAIWildcardNode", "UmiAIWildcardNodeLite"]);
const PANEL_WIDGET = "umi_roll_preview";

const COLORS = {
    ink: "var(--umi-ink)",
    dim: "var(--umi-ink-3)",
    negative: "var(--umi-negative)",
    ok: "var(--umi-ok)",
    warn: "var(--umi-warn)",
    error: "var(--umi-danger)",
    rule: "var(--umi-rule-strong)",
    ground: "var(--umi-ground)",
};

function makePanel() {
    ensureUmiTheme();
    const wrap = document.createElement("div");
    Object.assign(wrap.style, {
        boxSizing: "border-box",
        width: "100%",
        height: "100%",
        minHeight: "0",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        background: COLORS.ground,
        color: COLORS.ink,
        border: `1px solid ${COLORS.rule}`,
        borderRadius: "10px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        fontSize: "12px",
        lineHeight: "1.6",
    });
    const header = document.createElement("div");
    Object.assign(header.style, {
        display: "flex", alignItems: "center", gap: "8px",
        padding: "8px 12px", flexShrink: "0",
        background: T.surface_alt, borderBottom: `1px solid ${T.rule}`,
    });
    const title = document.createElement("span");
    title.textContent = "Prompt preview";
    Object.assign(title.style, { fontWeight: "600", color: T.ink_strong, flex: "1" });
    const badge = document.createElement("span");
    badge.textContent = "No GPU required";
    Object.assign(badge.style, { fontSize: "10px", color: COLORS.dim });
    header.append(title, badge);
    const body = document.createElement("div");
    body.tabIndex = 0;
    body.setAttribute("aria-label", "Prompt preview results");
    Object.assign(body.style, {
        padding: "10px 12px", overflowY: "auto", minHeight: "0", flex: "1",
        whiteSpace: "pre-wrap", overflowWrap: "anywhere", userSelect: "text",
        scrollbarWidth: "thin",
    });
    wrap.append(header, body);
    wrap.umiBody = body;
    return wrap;
}

function ensurePanel(node) {
    const existing = node.widgets?.find((w) => w.name === PANEL_WIDGET);
    if (existing) return existing;
    if (typeof node.addDOMWidget !== "function") return null;

    const el = makePanel();
    const widget = node.addDOMWidget(PANEL_WIDGET, "div", el, {
        serialize: false,
        hideOnZoom: false,
    });
    widget.umiEl = el.umiBody;
    widget.umiHeight = 104;
    widget.computeSize = () => [node.size?.[0] ?? 300, widget.umiHeight];
    widget.options = { ...widget.options, getMinHeight: () => widget.umiHeight,
        getMaxHeight: () => widget.umiHeight };
    return widget;
}

function line(text, color, opts = {}) {
    const el = document.createElement("div");
    el.textContent = text;
    if (color) el.style.color = color;
    if (opts.top) el.style.marginTop = opts.top;
    if (opts.size) el.style.fontSize = opts.size;
    return el;
}

function label(text) {
    const el = document.createElement("div");
    el.textContent = text;
    Object.assign(el.style, {
        color: COLORS.dim, fontSize: "10px", letterSpacing: "0.06em",
        fontWeight: "600", textTransform: "uppercase", margin: "10px 0 4px",
    });
    return el;
}

/**
 * What changed between two expansions, at comma-fragment level.
 *
 * Prompts here are tag lists, so a fragment is the unit people think in. A
 * fragment repeated in both is not reported, and counts are preserved so
 * "red, red" -> "red" shows one removal.
 */
export function diffFragments(before, after) {
    const split = (text) => String(text || "")
        .split(",").map((part) => part.trim()).filter(Boolean);

    const tally = (list) => {
        const counts = new Map();
        for (const item of list) counts.set(item, (counts.get(item) || 0) + 1);
        return counts;
    };

    const a = tally(split(before));
    const b = tally(split(after));
    const added = [];
    const removed = [];

    for (const [item, count] of b) {
        const surplus = count - (a.get(item) || 0);
        for (let i = 0; i < surplus; i += 1) added.push(item);
    }
    for (const [item, count] of a) {
        const surplus = count - (b.get(item) || 0);
        for (let i = 0; i < surplus; i += 1) removed.push(item);
    }
    return { added, removed };
}

const PIN_WIDGETS = ["_frozen_text", "_frozen_negative", "_frozen_seed"];

/** Hide the pin carriers: they are machinery, not controls. */
function hidePinWidgets(node) {
    for (const name of PIN_WIDGETS) {
        const widget = node.widgets?.find((w) => w.name === name);
        if (widget && widget.type !== "hidden") {
            widget.type = "hidden";
            widget.computeSize = () => [0, -4];
        }
    }
}

function pinnedText(node) {
    const widget = node.widgets?.find((w) => w.name === "_frozen_text");
    return widget && String(widget.value || "").trim() ? String(widget.value) : "";
}

function setPin(node, prompt, negative, seed) {
    const set = (name, value) => {
        const widget = node.widgets?.find((w) => w.name === name);
        if (widget) widget.value = value;
    };
    set("_frozen_text", prompt || "");
    set("_frozen_negative", negative || "");
    // Stored as a string to match the carrier's schema.
    set("_frozen_seed", Number.isFinite(seed) ? String(seed) : "");
    node.setDirtyCanvas?.(true, true);
}

/**
 * Repair pin carriers whose values came from a stale or mis-ordered workflow.
 *
 * ComfyUI stores widget values positionally, so a workflow saved against a
 * different input order can leave anything in these slots -- a boolean in the
 * text, a mode name in the seed. Left alone they either block the queue or
 * silently pin nonsense, so anything that is not a plausible pin is cleared on
 * load rather than waiting to fail.
 */
export function sanitizePinWidgets(node) {
    const get = (name) => node.widgets?.find((w) => w.name === name);
    const text = get("_frozen_text");
    const negative = get("_frozen_negative");
    const seed = get("_frozen_seed");
    let repaired = false;

    if (text && typeof text.value !== "string") { text.value = ""; repaired = true; }
    if (negative && typeof negative.value !== "string") { negative.value = ""; repaired = true; }
    if (seed) {
        const raw = seed.value;
        const numeric = typeof raw === "number" ? raw : Number.parseFloat(raw);
        if (raw === "" || raw === null || raw === undefined) {
            // already clear
        } else if (!Number.isFinite(numeric)) {
            seed.value = "";
            repaired = true;
        } else if (typeof raw !== "string") {
            seed.value = String(Math.trunc(numeric));
        }
    }

    // A pinned seed with no pinned text is not a pin, just a leftover.
    if (text && typeof text.value === "string" && !text.value.trim() && seed && seed.value !== "") {
        seed.value = "";
        repaired = true;
    }

    if (repaired) {
        console.warn("[UmiAI] Cleared unusable pin values on this node "
            + "(they came from a workflow saved against a different input order).");
        node.setDirtyCanvas?.(true, true);
    }
    return repaired;
}

function paint(node, render, height = 104) {
    const widget = ensurePanel(node);
    if (!widget?.umiEl) return;
    widget.umiEl.textContent = "";
    render(widget.umiEl);
    if (widget.umiHeight !== height) {
        widget.umiHeight = height;
        const minimum = node.computeSize?.();
        if (minimum && node.setSize) {
            node.setSize([Math.max(node.size?.[0] || 0, minimum[0]),
                Math.max(node.size?.[1] || 0, minimum[1])]);
        }
        node.onResize?.(node.size);
    }
    node.setDirtyCanvas?.(true, true);
}

function widgetValue(node, name, fallback = undefined) {
    const widget = node.widgets?.find((w) => w.name === name);
    return widget ? widget.value : fallback;
}

async function previewRoll(node) {
    const requestId = node.__umiPreviewRequest = (node.__umiPreviewRequest || 0) + 1;
    const isCurrent = () => !node.__umiPreviewRemoved && node.__umiPreviewRequest === requestId;
    const text = widgetValue(node, "text", "");
    if (!String(text).trim()) {
        paint(node, (el) => el.appendChild(line("Nothing to preview: the prompt is empty.", COLORS.dim)));
        return;
    }

    paint(node, (el) => el.appendChild(line("Rolling…", COLORS.dim)));

    const body = {
        text,
        seed: widgetValue(node, "seed", 0),
        prompt_profile: widgetValue(node, "prompt_profile"),
        prompt_preset: widgetValue(node, "prompt_preset"),
        preset_placement: widgetValue(node, "preset_placement"),
        section_order: widgetValue(node, "section_order"),
        anima_prompt_mode: widgetValue(node, "anima_prompt_mode"),
        anima_artist_mode: widgetValue(node, "anima_artist_mode"),
        bypass_phrases: widgetValue(node, "bypass_phrases"),
        input_negative: widgetValue(node, "input_negative"),
        lora_tags_behavior: widgetValue(node, "lora_tags_behavior"),
        lora_cache_limit: widgetValue(node, "lora_cache_limit"),
        width: widgetValue(node, "width"),
        height: widgetValue(node, "height"),
    };

    let data;
    try {
        const response = await api.fetchApi("/umiapp/preview-roll", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        data = await response.json();
    } catch (error) {
        if (!isCurrent()) return;
        paint(node, (el) => el.appendChild(line(`Preview failed: ${error.message}`, COLORS.error)));
        return;
    }

    if (!isCurrent()) return;
    if (!data?.success) {
        paint(node, (el) => {
            el.appendChild(label("Preview failed"));
            el.appendChild(line(data?.error || "Unknown error", COLORS.error));
        });
        return;
    }

    const previous = node.__umiLastRoll || null;
    node.__umiLastRoll = {
        prompt: data.prompt || "",
        frozenPrompt: data.frozen_prompt || data.prompt || "",
        negative: data.negative || "",
        seed: body.seed,
    };

    paint(node, (el) => {
        // Summary first: how many wildcards rolled, and how many reused an
        // earlier pick, which is the thing that surprises people most.
        // The seed is listed first and deliberately: a seed widget gets an
        // auto-attached control that defaults to randomize, so being able to
        // check this against the widget is the difference between trusting the
        // preview and verifying it.
        const bits = [`seed ${body.seed}`, `${data.picks} pick${data.picks === 1 ? "" : "s"}`];
        if (data.reused) bits.push(`${data.reused} reused`);
        if (data.width && data.height) bits.push(`${data.width}x${data.height}`);
        el.appendChild(line(bits.join("  ·  "), COLORS.dim, { size: "10px" }));

        // "I bumped the seed -- what changed?" is the question people actually
        // ask, and it needs this roll against the previous one.
        if (previous && previous.prompt !== data.prompt) {
            const { added, removed } = diffFragments(previous.prompt, data.prompt);
            if (added.length || removed.length) {
                const changes = label("Changed from the last roll");
                changes.style.marginTop = "6px";
                el.appendChild(changes);
                if (added.length) el.appendChild(line("+ " + added.join(", "), COLORS.ok));
                if (removed.length) el.appendChild(line("− " + removed.join(", "), COLORS.negative));
            }
        }

        el.appendChild(label("Prompt"));
        el.appendChild(line(data.prompt || "(empty)", COLORS.ink));

        if (data.negative) {
            const neg = label("Negative");
            neg.style.marginTop = "7px";
            el.appendChild(neg);
            el.appendChild(line(data.negative, COLORS.negative));
        }

        if (data.warnings?.length) {
            const warn = label(`${data.warnings.length} warning${data.warnings.length === 1 ? "" : "s"}`);
            warn.style.marginTop = "7px";
            el.appendChild(warn);
            data.warnings.forEach((w) => el.appendChild(line(String(w), COLORS.warn)));
        }
    }, 230);
}

app.registerExtension({
    name: "Umi.RollPreview",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_TYPES.has(nodeData?.name)) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            this.__umiPreviewRemoved = false;

            // The promise is returned rather than dropped: ComfyUI ignores a
            // widget callback's return value, but returning it makes the button
            // awaitable from a test.
            this.addWidget("button", "Preview prompt output", null, () =>
                previewRoll(this).catch((error) => {
                    console.error("[UmiAI] Roll preview error:", error);
                })
            );

            this.__umiPinButton = this.addWidget("button", "Lock seed and prompt below", null, () =>
                togglePin(this)
            );

            hidePinWidgets(this);
            sanitizePinWidgets(this);
            refreshPinLabel(this);
            paintIdle(this);
        };

        const onRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this.__umiPreviewRemoved = true;
            this.__umiPreviewRequest = (this.__umiPreviewRequest || 0) + 1;
            return onRemoved?.apply(this, arguments);
        };

        // onNodeCreated runs before a saved workflow's values are applied, so
        // the repair has to happen again once they land.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            this.__umiPreviewRequest = (this.__umiPreviewRequest || 0) + 1;
            onConfigure?.apply(this, arguments);
            hidePinWidgets(this);
            sanitizePinWidgets(this);
            refreshPinLabel(this);
            paintIdle(this);
        };
    },
});

/** Reflect pin state on the button, so one control reads both ways. */
function refreshPinLabel(node) {
    const button = node.__umiPinButton;
    if (!button) return;
    button.name = pinnedText(node) ? "Unlock seed and prompt" : "Lock seed and prompt below";
}

function paintIdle(node) {
    const pinned = pinnedText(node);
    paint(node, (el) => {
        if (pinned) {
            el.appendChild(line("Locked — this exact prompt and seed are reused instead of rolling.", COLORS.warn));
            el.appendChild(line(pinned, COLORS.ink, { top: "5px" }));
            return;
        }
        el.appendChild(line(
            "Press “Preview prompt output” to expand this prompt without running the graph.",
            COLORS.dim));
    }, pinned ? 230 : 104);
}

/**
 * Pin the last previewed roll, or clear an existing pin.
 *
 * Pinning without a preview would have nothing to pin, so it asks for one
 * first rather than silently doing nothing.
 */
function togglePin(node) {
    if (pinnedText(node)) {
        // null, not -1: the carrier's "nothing pinned" value is the empty
        // string, and setPin maps any non-finite seed to it.
        setPin(node, "", "", null);
        node.__umiLastRoll = null;
        refreshPinLabel(node);
        paintIdle(node);
        return;
    }

    const last = node.__umiLastRoll;
    if (!last || !String(last.prompt || "").trim()) {
        paint(node, (el) => el.appendChild(
            line("Nothing to lock yet — press “Preview prompt output” first.", COLORS.warn)));
        return;
    }

    // Keep the pre-LoRA form in the carrier so execution can still detect and
    // apply the LoRA.  The panel continues to show the final preview text.
    setPin(node, last.frozenPrompt || last.prompt, last.negative, last.seed);
    refreshPinLabel(node);
    paint(node, (el) => {
        el.appendChild(line("Locked — this prompt and seed are reused until you unlock.", COLORS.warn));
        el.appendChild(line(last.prompt, COLORS.ink, { top: "5px" }));
        if (last.negative) {
            const neg = label("Negative");
            neg.style.marginTop = "6px";
            el.appendChild(neg);
            el.appendChild(line(last.negative, COLORS.negative));
        }
    }, 230);
}

export { togglePin, refreshPinLabel, pinnedText, hidePinWidgets, paintIdle };
