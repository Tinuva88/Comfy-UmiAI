import { ensureUmiTheme } from "./umi_theme.js";
export function escapeHtml(text) {
    if (!text) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function showUmiNotification(message, isError = false) {
    // Utilities are called from panels that may not have run setup yet.
    ensureUmiTheme();
    const notification = document.createElement("div");
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${isError ? "var(--umi-danger)" : "var(--umi-ok-soft)"};
        color: white;
        padding: 9px 14px;
        border-radius: 6px;
        z-index: 10050;
        font-size: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.35);
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 2200);
}

export function copyText(text, label = "Copied") {
    navigator.clipboard.writeText(String(text || ""));
    showUmiNotification(label);
}

// =============================================================================
// PROMPT STRUCTURE SCANNER (read-only display helper)
//
// Character scanner that classifies Umi prompt syntax into display tokens.
// Used by the Run Inspector "Prompt Structure" card. It never modifies the
// prompt text; renderPromptStructureHtml escapes every text slice before
// wrapping it in display-only spans.
// =============================================================================

const UMI_BRACE_DEPTH_CYCLE = 6;
const UMI_FUNCTION_NAME_RE = /^([a-z_][a-z0-9_]*)\s*:/i;

export function scanPromptStructure(text) {
    const value = String(text || "");
    const tokens = [];
    const warnings = [];
    const braceStack = [];
    const bracketStack = [];
    const n = value.length;
    let i = 0;

    const push = (start, end, cls) => {
        if (end > start) tokens.push({ start, end, cls });
    };
    const braceClass = (depth) => `umi-sx-brace-d${(depth % UMI_BRACE_DEPTH_CYCLE) + 1}`;

    while (i < n) {
        const ch = value[i];

        // // toggles a comment until the next // or end of line.
        if (ch === "/" && value[i + 1] === "/") {
            let j = i + 2;
            while (j < n && value[j] !== "\n" && !(value[j] === "/" && value[j + 1] === "/")) j++;
            const end = j < n && value[j] === "/" ? j + 2 : j;
            push(i, end, "umi-sx-comment");
            i = end;
            continue;
        }

        // Line-leading '#' comments a whole line; ' #' comments the rest.
        if (ch === "#" && (i === 0 || value[i - 1] === "\n")) {
            let j = i;
            while (j < n && value[j] !== "\n") j++;
            push(i, j, "umi-sx-comment");
            i = j;
            continue;
        }
        if (ch === "#" && value[i - 1] === " ") {
            let j = i;
            while (j < n && value[j] !== "\n") j++;
            push(i - 1, j, "umi-sx-comment");
            i = j;
            continue;
        }

        // Escapes like \{ and \__ keep their literal meaning.
        if (ch === "\\") {
            i += 2;
            continue;
        }

        // __wildcard__, __~sequential__, __N-M$$range__, __@prompt file__.
        if (ch === "_" && value[i + 1] === "_") {
            const close = value.indexOf("__", i + 2);
            const newline = value.indexOf("\n", i + 2);
            if (close !== -1 && (newline === -1 || close < newline)) {
                const inner = value.slice(i + 2, close);
                let cls = "umi-sx-wildcard";
                if (inner.startsWith("@")) cls = "umi-sx-promptfile";
                else if (inner.startsWith("~")) cls = "umi-sx-sequential";
                else if (/^\d+-\d+\$\$/.test(inner)) cls = "umi-sx-range";
                push(i, close + 2, cls);
                i = close + 2;
                continue;
            }
            warnings.push('Unclosed wildcard marker "__".');
            push(i, i + 2, "umi-sx-error");
            i += 2;
            continue;
        }

        // <lora:...> tags.
        if (ch === "<" && value.slice(i + 1, i + 6).toLowerCase() === "lora:") {
            const close = value.indexOf(">", i);
            if (close !== -1) {
                push(i, close + 1, "umi-sx-lora");
                i = close + 1;
                continue;
            }
        }

        // $variables.
        if (ch === "$") {
            let j = i + 1;
            while (j < n && /[A-Za-z0-9_]/.test(value[j])) j++;
            if (j > i + 1) {
                push(i, j, "umi-sx-variable");
                i = j;
                continue;
            }
        }

        // Brace nesting: open/close at the same depth share a class.
        if (ch === "{") {
            braceStack.push(tokens.length);
            push(i, i + 1, braceClass(braceStack.length - 1));
            i++;
            continue;
        }
        if (ch === "}") {
            if (braceStack.length) {
                push(i, i + 1, braceClass(braceStack.length - 1));
                braceStack.pop();
            } else {
                warnings.push('Unbalanced closing brace "}".');
                push(i, i + 1, "umi-sx-error");
            }
            i++;
            continue;
        }

        // Pipes inside braces take the surrounding depth color.
        if (ch === "|" && braceStack.length) {
            push(i, i + 1, braceClass(braceStack.length - 1));
            i++;
            continue;
        }

        // Square brackets: conditionals, prompt functions, plain brackets.
        if (ch === "[") {
            const rest = value.slice(i + 1, i + 32);
            let cls = "umi-sx-bracket";
            let nameLength = 0;
            if (/^if[\s(]/i.test(rest)) {
                cls = "umi-sx-conditional";
                nameLength = 2;
            } else {
                const match = rest.match(UMI_FUNCTION_NAME_RE);
                if (match) {
                    cls = "umi-sx-function";
                    nameLength = match[0].length;
                }
            }
            bracketStack.push({ tokenIndex: tokens.length, cls });
            push(i, i + 1, cls);
            if (nameLength) push(i + 1, i + 1 + nameLength, cls);
            i++;
            continue;
        }
        if (ch === "]") {
            if (bracketStack.length) {
                push(i, i + 1, bracketStack.pop().cls);
            } else {
                warnings.push('Unbalanced closing bracket "]".');
                push(i, i + 1, "umi-sx-error");
            }
            i++;
            continue;
        }

        i++;
    }

    for (const tokenIndex of braceStack) {
        tokens[tokenIndex].cls = "umi-sx-error";
        warnings.push('Unclosed brace "{".');
    }
    for (const open of bracketStack) {
        tokens[open.tokenIndex].cls = "umi-sx-error";
        warnings.push('Unclosed bracket "[".');
    }

    return { tokens, warnings };
}

export function renderPromptStructureHtml(text) {
    const value = String(text || "");
    const { tokens, warnings } = scanPromptStructure(value);
    tokens.sort((a, b) => a.start - b.start || a.end - b.end);

    let html = "";
    let cursor = 0;
    for (const token of tokens) {
        if (token.start < cursor) continue;
        html += escapeHtml(value.slice(cursor, token.start));
        html += `<span class="${token.cls}">${escapeHtml(value.slice(token.start, token.end))}</span>`;
        cursor = token.end;
    }
    html += escapeHtml(value.slice(cursor));

    return { html, warnings: [...new Set(warnings)] };
}
