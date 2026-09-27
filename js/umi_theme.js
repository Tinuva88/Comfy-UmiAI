// =============================================================================
// Shared design tokens
//
// Every panel in this pack used to define its own colours inline -- around 300
// hardcoded hex values across thirteen files, thirteen small independent dark
// designs, none of which followed ComfyUI's own theme. A light-theme user got
// black boxes on a white canvas.
//
// Tokens are declared once here and derived from ComfyUI's own custom
// properties where it publishes a suitable one, with a hex fallback for when it
// does not (older frontends, or a theme that omits a variable). So the panels
// track the host theme when it is available and still look deliberate when it
// is not.
//
// Usage:
//     import { ensureUmiTheme, T } from "./umi_theme.js";
//     ensureUmiTheme();                       // once, before styling
//     el.style.background = T.surface;        // -> "var(--umi-surface)"
// =============================================================================

const STYLE_ID = "umi-theme-tokens";

/** Token name -> [ComfyUI variable to inherit, fallback]. */
const TOKENS = {
    // surfaces
    "sunken":        ["--comfy-input-bg",     "#0f131a"],
    "ground":        ["--comfy-menu-bg",     "#15171c"],
    "surface":       ["--content-bg",        "#1b1e25"],
    "surface-alt":   ["--comfy-input-bg",    "#21252d"],
    // A hover surface has to be distinct from the resting one, or the state is
    // invisible. Kept separate so a colour sweep cannot collapse the two.
    "surface-hover": [null,                  "#2f3540"],
    "field":         ["--comfy-input-bg",    "#15171c"],

    // text
    "ink":          ["--input-text",        "#d8dbe1"],
    "ink-2":        ["--descrip-text",      "#98a1b0"],
    "ink-3":        ["--descrip-text",       "#8992a3"],
    "ink-strong":   ["--fg-color",          "#ffffff"],
    // Dark text, for the few places text sits on a bright fill. Tiering
    // these with the rest would have made a gold button's label mid-grey
    // on gold.
    "ink-inverse":  [null,                  "#10141d"],
    // Light text over the dark scrim on a thumbnail; the scrim is dark in
    // every theme, so this must not follow the theme's ink.
    "ink-on-media": [null,                  "#f4f6fa"],

    // lines
    "rule":         ["--border-color",      "#2a2f38"],
    "rule-strong":  [null,                  "#3b4250"],
    // A hovered border has to read brighter than a resting strong one, for the
    // same reason surface-hover is kept apart from surface-alt.
    "rule-hover":   [null,                  "#5b6b85"],

    // accent and state
    "accent":       [null,                  "#61afef"],
    "accent-soft":  [null,                  "#2d4f6c"],
    "danger":       ["--error-text",        "#ff6b6b"],
    "warn":         [null,                  "#ffd43b"],
    // A filled warning control and its hover, kept apart so the state shows.
    "warn-fill":       [null,               "#b58900"],
    "warn-fill-hover": [null,               "#dcb538"],
    "ok":           [null,                  "#98c379"],

    // prompt-syntax families, shared by the highlighter and every panel that
    // renders resolved prompt text
    "wildcard":     [null,                  "#98c379"],
    "prompt-file":  [null,                  "#7ec699"],
    "choice":       [null,                  "#e5c07b"],
    "range":        [null,                  "#ffd43b"],
    "tag-select":   [null,                  "#61afef"],
    "conditional":  [null,                  "#56b6c2"],
    "function":     [null,                  "#20c997"],
    "lora":         [null,                  "#ff922b"],
    "trigger":      [null,                  "#ff79c6"],
    "variable":     [null,                  "#c678dd"],
    "weight":       [null,                  "#d19a66"],
    "negative":     [null,                  "#ff6b6b"],
    "comment":      [null,                  "#6b7383"],

    // faint backing washes behind coloured labels
    "ok-wash":      [null,                  "#212c1e"],
    "accent-wash":  [null,                  "#1c2833"],
    "danger-wash":  [null,                  "#3b2020"],
    "warn-wash":    [null,                  "#3a2b18"],

    // muted borders for the same states, dark enough to sit on a wash
    "ok-soft":      [null,                  "#2f7d4b"],
    "danger-soft":  [null,                  "#6d3732"],
    "warn-soft":    [null,                  "#7b571d"],

    // danbooru tag categories
    "cat-general":   [null, "#89c4f4"],
    "cat-artist":    [null, "#ff922b"],
    "cat-copyright": [null, "#c678dd"],
    "cat-character": [null, "#98c379"],
    "cat-meta":      [null, "#e5c07b"],
};

/** Accessor: T.surface -> "var(--umi-surface)". Kebab names work too. */
export const T = new Proxy({}, {
    get(_target, prop) {
        const name = String(prop).replace(/_/g, "-");
        return `var(--umi-${name})`;
    },
});

/** The raw fallback for a token, for the rare place a var() cannot be used. */
export function rawToken(name) {
    const entry = TOKENS[String(name).replace(/_/g, "-")];
    return entry ? entry[1] : null;
}

export function umiTokenNames() {
    return Object.keys(TOKENS);
}

/**
 * Inject the token declarations once per document.
 *
 * Safe to call from every module's setup; later calls are no-ops.
 */
export function ensureUmiTheme() {
    if (document.getElementById(STYLE_ID)) return;

    const lines = Object.entries(TOKENS).map(([name, [inherit, fallback]]) => {
        const value = inherit ? `var(${inherit}, ${fallback})` : fallback;
        return `    --umi-${name}: ${value};`;
    });

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `:root {\n${lines.join("\n")}\n}\n`;
    style.textContent += `
        @supports (color: color-mix(in srgb, white, black)) {
            :root {
                --umi-ink-3: color-mix(in srgb, var(--umi-ink-2) 80%, var(--umi-surface));
                --umi-surface-hover: color-mix(in srgb, var(--umi-ink) 10%, var(--umi-surface));
                --umi-rule-strong: color-mix(in srgb, var(--umi-ink) 22%, var(--umi-surface));
                --umi-rule-hover: color-mix(in srgb, var(--umi-ink) 40%, var(--umi-surface));
                --umi-accent-soft: color-mix(in srgb, var(--umi-accent) 22%, var(--umi-surface));
                --umi-accent-wash: color-mix(in srgb, var(--umi-accent) 10%, var(--umi-surface));
                --umi-danger-wash: color-mix(in srgb, var(--umi-danger) 10%, var(--umi-surface));
                --umi-warn-wash: color-mix(in srgb, var(--umi-warn) 10%, var(--umi-surface));
            }
        }
        :is(.umi-lora-browser, .umi-image-browser, .umi-wb-modal) :is(button, input, select, textarea, [role="button"]):focus-visible {
            outline: 2px solid var(--umi-accent); outline-offset: 2px;
        }
        :is(.umi-lora-browser, .umi-image-browser) button:disabled { opacity: .45; cursor: not-allowed; }
    `;
    document.head.appendChild(style);
}
