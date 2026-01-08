import { app } from "../../scripts/app.js";

// =============================================================================
// SYNTAX HIGHLIGHTER FOR UMI WILDCARDS
// Notepad++ Style Syntax Highlighting + Prompt Linting + Hover Preview
// =============================================================================

const HIGHLIGHT_COLORS = {
    wildcard: "#98c379",       // Green - __wildcards__
    tagSelect: "#61afef",      // Blue - <[tag]>
    dynamicChoice: "#e5c07b",  // Yellow - {a|b|c}
    variable: "#c678dd",       // Purple - $variable
    conditional: "#56b6c2",    // Cyan - [if ...: ... | ...]
    lora: "#e06c75",           // Red/Pink - <lora:...>
    negative: "#ff6b6b",       // Warning red - **neg** or --neg:
    comment: "#5c6370",        // Gray - # comments
    weight: "#d19a66",         // Orange - (text:1.2)
    function: "#61afef",       // Blue italic - [shuffle:], [clean:]
    rangeSelect: "#e5c07b",    // Yellow - __2-4$$tag__
    promptFile: "#98c379",     // Green - __@filename__
    text: "#abb2bf",           // Default text color
    error: "#ff4444",          // Error red
};

// Store known wildcards and loras for validation
let knownWildcards = [];
let knownLoras = [];

// Cache for wildcard previews
const previewCache = new Map();

// Fetch wildcards data for linting
async function fetchWildcardsForLinting() {
    try {
        const response = await fetch("/umiapp/wildcards");
        if (response.ok) {
            const data = await response.json();
            knownWildcards = data.files || data.wildcards || [];
            knownLoras = data.loras || [];
            console.log(`[UmiAI Lint] Loaded ${knownWildcards.length} wildcards, ${knownLoras.length} loras`);
        }
    } catch (e) {
        console.error("[UmiAI Lint] Failed to fetch wildcards:", e);
    }
}

// Fetch wildcard preview for hover tooltip
async function fetchWildcardPreview(filename) {
    // Check cache first
    if (previewCache.has(filename)) {
        return previewCache.get(filename);
    }

    try {
        const response = await fetch(`/umiapp/preview?file=${encodeURIComponent(filename)}`);
        if (response.ok) {
            const data = await response.json();
            previewCache.set(filename, data);
            return data;
        }
    } catch (e) {
        console.error("[UmiAI Preview] Failed to fetch preview:", e);
    }
    return null;
}

// CSS for the overlay system and linting
const HIGHLIGHT_STYLES = `
    .umi-syntax-container {
        position: relative !important;
        width: 100% !important;
        height: 100% !important;
    }
    
    .umi-syntax-backdrop {
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        padding: 6px 8px !important;
        margin: 0 !important;
        border: none !important;
        background: #1e1e1e !important;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
        font-size: 13px !important;
        line-height: 1.5 !important;
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        pointer-events: none !important;
        color: ${HIGHLIGHT_COLORS.text} !important;
        box-sizing: border-box !important;
        z-index: 1 !important;
    }
    
    .umi-syntax-textarea {
        position: relative !important;
        width: 100% !important;
        height: 100% !important;
        padding: 6px 8px !important;
        margin: 0 !important;
        border: none !important;
        background: transparent !important;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
        font-size: 13px !important;
        line-height: 1.5 !important;
        color: transparent !important;
        caret-color: #61afef !important;
        resize: none !important;
        box-sizing: border-box !important;
        z-index: 2 !important;
        outline: none !important;
    }
    
    .umi-syntax-textarea::selection {
        background: rgba(97, 175, 239, 0.3) !important;
    }
    
    /* Syntax highlight spans */
    .umi-hl-wildcard { color: ${HIGHLIGHT_COLORS.wildcard} !important; font-weight: 500; }
    .umi-hl-tag-select { color: ${HIGHLIGHT_COLORS.tagSelect} !important; font-weight: 500; }
    .umi-hl-dynamic { color: ${HIGHLIGHT_COLORS.dynamicChoice} !important; }
    .umi-hl-variable { color: ${HIGHLIGHT_COLORS.variable} !important; font-weight: 500; }
    .umi-hl-conditional { color: ${HIGHLIGHT_COLORS.conditional} !important; }
    .umi-hl-lora { color: ${HIGHLIGHT_COLORS.lora} !important; font-weight: 500; }
    .umi-hl-negative { color: ${HIGHLIGHT_COLORS.negative} !important; font-style: italic; }
    .umi-hl-comment { color: ${HIGHLIGHT_COLORS.comment} !important; font-style: italic; }
    .umi-hl-weight { color: ${HIGHLIGHT_COLORS.weight} !important; }
    .umi-hl-function { color: ${HIGHLIGHT_COLORS.function} !important; font-style: italic; }
    .umi-hl-range { color: ${HIGHLIGHT_COLORS.rangeSelect} !important; }
    .umi-hl-prompt-file { color: ${HIGHLIGHT_COLORS.promptFile} !important; font-weight: 500; }
    
    /* Error highlighting for linting */
    .umi-hl-error { 
        text-decoration: wavy underline !important;
        text-decoration-color: ${HIGHLIGHT_COLORS.error} !important;
        text-underline-offset: 2px !important;
    }
    
    .umi-hl-error-missing {
        color: ${HIGHLIGHT_COLORS.error} !important;
        text-decoration: wavy underline !important;
        text-decoration-color: ${HIGHLIGHT_COLORS.error} !important;
    }
    
    /* Error indicator bar */
    .umi-lint-bar {
        position: absolute !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        height: 20px !important;
        background: rgba(30, 30, 30, 0.95) !important;
        border-top: 1px solid #333 !important;
        display: flex !important;
        align-items: center !important;
        padding: 0 8px !important;
        font-size: 11px !important;
        font-family: 'Consolas', monospace !important;
        z-index: 3 !important;
        pointer-events: auto !important;
    }
    
    .umi-lint-bar-clean {
        color: #98c379 !important;
    }
    
    .umi-lint-bar-errors {
        color: ${HIGHLIGHT_COLORS.error} !important;
    }
    
    .umi-lint-icon {
        margin-right: 5px !important;
    }
    
    /* Hover preview tooltip */
    .umi-preview-tooltip {
        position: fixed !important;
        background: #252526 !important;
        border: 1px solid #454545 !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
        font-family: 'Consolas', 'Monaco', monospace !important;
        font-size: 12px !important;
        color: #e0e0e0 !important;
        max-width: 350px !important;
        max-height: 250px !important;
        overflow-y: auto !important;
        z-index: 10000 !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.5) !important;
        pointer-events: none !important;
    }
    
    .umi-preview-header {
        color: #61afef !important;
        font-weight: 600 !important;
        margin-bottom: 6px !important;
        padding-bottom: 4px !important;
        border-bottom: 1px solid #333 !important;
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
    }
    
    .umi-preview-type {
        font-size: 10px !important;
        color: #888 !important;
        background: #333 !important;
        padding: 1px 5px !important;
        border-radius: 3px !important;
    }
    
    .umi-preview-list {
        margin: 0 !important;
        padding: 0 !important;
        list-style: none !important;
    }
    
    .umi-preview-item {
        padding: 2px 0 !important;
        color: #98c379 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    
    .umi-preview-more {
        color: #888 !important;
        font-style: italic !important;
    }
    
    .umi-preview-error {
        color: ${HIGHLIGHT_COLORS.error} !important;
    }
    
    .umi-preview-loading {
        color: #888 !important;
        font-style: italic !important;
    }
`;

// Inject styles once
let stylesInjected = false;
function injectStyles() {
    if (stylesInjected) return;
    const styleEl = document.createElement("style");
    styleEl.id = "umi-syntax-highlight-styles";
    styleEl.textContent = HIGHLIGHT_STYLES;
    document.head.appendChild(styleEl);
    stylesInjected = true;
    console.log("[UmiAI Syntax] Styles injected");
}

// Escape HTML entities
function escapeHtml(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// =============================================================================
// HOVER PREVIEW TOOLTIP
// =============================================================================

let previewTooltip = null;
let hoverTimeout = null;

function createPreviewTooltip() {
    if (previewTooltip) return previewTooltip;

    previewTooltip = document.createElement("div");
    previewTooltip.className = "umi-preview-tooltip";
    previewTooltip.style.display = "none";
    document.body.appendChild(previewTooltip);

    return previewTooltip;
}

function showPreviewTooltip(x, y, content) {
    const tooltip = createPreviewTooltip();
    tooltip.innerHTML = content;
    tooltip.style.display = "block";

    // Position tooltip
    const rect = tooltip.getBoundingClientRect();
    const viewWidth = window.innerWidth;
    const viewHeight = window.innerHeight;

    // Adjust position to stay in viewport
    let left = x + 15;
    let top = y + 15;

    if (left + rect.width > viewWidth - 20) {
        left = x - rect.width - 15;
    }
    if (top + rect.height > viewHeight - 20) {
        top = y - rect.height - 15;
    }

    tooltip.style.left = `${Math.max(10, left)}px`;
    tooltip.style.top = `${Math.max(10, top)}px`;
}

function hidePreviewTooltip() {
    if (previewTooltip) {
        previewTooltip.style.display = "none";
    }
    if (hoverTimeout) {
        clearTimeout(hoverTimeout);
        hoverTimeout = null;
    }
}

async function handleWildcardHover(e, textareaEl) {
    const text = textareaEl.value;
    const cursorPos = getCursorPositionFromMouse(e, textareaEl);

    if (cursorPos === -1) {
        hidePreviewTooltip();
        return;
    }

    // Check if cursor is inside a wildcard
    const wildcardMatch = findWildcardAtPosition(text, cursorPos);

    if (!wildcardMatch) {
        hidePreviewTooltip();
        return;
    }

    // Show loading state
    showPreviewTooltip(e.clientX, e.clientY, '<span class="umi-preview-loading">Loading...</span>');

    // Fetch preview
    const preview = await fetchWildcardPreview(wildcardMatch.name);

    if (!preview) {
        hidePreviewTooltip();
        return;
    }

    // Build tooltip content
    let content = `<div class="umi-preview-header">
        <span>__${wildcardMatch.name}__</span>
        <span class="umi-preview-type">${preview.type || 'txt'}</span>
    </div>`;

    if (preview.error) {
        content += `<div class="umi-preview-error">${preview.error}</div>`;
    } else if (preview.entries && preview.entries.length > 0) {
        content += '<ul class="umi-preview-list">';
        preview.entries.forEach(entry => {
            if (entry.startsWith('...')) {
                content += `<li class="umi-preview-item umi-preview-more">${escapeHtml(entry)}</li>`;
            } else {
                content += `<li class="umi-preview-item">${escapeHtml(entry)}</li>`;
            }
        });
        content += '</ul>';
    } else {
        content += '<div class="umi-preview-error">No entries found</div>';
    }

    showPreviewTooltip(e.clientX, e.clientY, content);
}

function getCursorPositionFromMouse(e, textareaEl) {
    // Approximate cursor position based on mouse coordinates
    const rect = textareaEl.getBoundingClientRect();
    const style = getComputedStyle(textareaEl);
    const lineHeight = parseFloat(style.lineHeight) || 19.5;
    const charWidth = 7.8; // Approximate for monospace
    const paddingLeft = parseFloat(style.paddingLeft) || 6;
    const paddingTop = parseFloat(style.paddingTop) || 6;

    const x = e.clientX - rect.left - paddingLeft;
    const y = e.clientY - rect.top - paddingTop + textareaEl.scrollTop;

    const lines = textareaEl.value.split('\n');
    const lineIndex = Math.floor(y / lineHeight);

    if (lineIndex < 0 || lineIndex >= lines.length) return -1;

    const charIndex = Math.floor(x / charWidth);

    // Calculate absolute position
    let pos = 0;
    for (let i = 0; i < lineIndex; i++) {
        pos += lines[i].length + 1; // +1 for newline
    }
    pos += Math.min(charIndex, lines[lineIndex].length);

    return pos;
}

function findWildcardAtPosition(text, pos) {
    // Find wildcards in the text
    const wildcardRe = /__([a-zA-Z0-9_\-\/]+)__/g;
    let match;

    while ((match = wildcardRe.exec(text)) !== null) {
        if (pos >= match.index && pos <= match.index + match[0].length) {
            return {
                name: match[1],
                start: match.index,
                end: match.index + match[0].length,
                full: match[0]
            };
        }
    }

    return null;
}

// =============================================================================
// LINTING LOGIC
// =============================================================================

function lintPrompt(text) {
    const errors = [];

    if (!text) return errors;

    // 1. Check for unclosed braces { }
    let braceCount = 0;
    let braceStart = -1;
    for (let i = 0; i < text.length; i++) {
        if (text[i] === '{') {
            if (braceCount === 0) braceStart = i;
            braceCount++;
        } else if (text[i] === '}') {
            braceCount--;
            if (braceCount < 0) {
                errors.push({ type: 'unclosed', message: 'Unexpected closing brace }', index: i, length: 1 });
                braceCount = 0;
            }
        }
    }
    if (braceCount > 0) {
        errors.push({ type: 'unclosed', message: 'Unclosed brace {', index: braceStart, length: 1 });
    }

    // 2. Check for unclosed wildcards __ (improved pattern)
    // Look for __ followed by valid wildcard characters that don't end with __
    // This finds cases like "__colors" without the closing "__"
    const unclosedWildcardRe = /__([a-zA-Z0-9_\-\/]+)(?!__)/g;
    let lastWildcardMatch = null;
    let wcTestMatch;

    // Find all potential wildcard starts
    while ((wcTestMatch = unclosedWildcardRe.exec(text)) !== null) {
        // Check if this is actually unclosed (not followed by __)
        const afterMatch = text.slice(wcTestMatch.index + wcTestMatch[0].length);
        // If the next characters are __, it's closed - skip it
        if (afterMatch.startsWith('__')) {
            continue;
        }
        // If we're at the end of text or followed by non-wildcard chars, it might be unclosed
        // But only if there's no closing __ anywhere after
        const restOfText = text.slice(wcTestMatch.index);
        const fullWildcard = restOfText.match(/^__[\w\-\/]+__/);
        if (!fullWildcard) {
            lastWildcardMatch = wcTestMatch;
        }
    }

    if (lastWildcardMatch && !text.slice(lastWildcardMatch.index).match(/^__[\w\-\/]+__/)) {
        // Double check it's actually unclosed
        const textAfterStart = text.slice(lastWildcardMatch.index);
        if (!textAfterStart.match(/^__[\w\-\/]+__/)) {
            errors.push({ type: 'unclosed', message: 'Unclosed wildcard __', index: lastWildcardMatch.index, length: lastWildcardMatch[0].length });
        }
    }

    // 3. Check for unclosed tag selections <[
    let angleCount = 0;
    let tagStart = -1;
    for (let i = 0; i < text.length - 1; i++) {
        if (text.slice(i, i + 2) === '<[') {
            if (angleCount === 0) tagStart = i;
            angleCount++;
            i++;
        } else if (text.slice(i, i + 2) === ']>') {
            angleCount--;
            i++;
        }
    }
    if (angleCount > 0) {
        errors.push({ type: 'unclosed', message: 'Unclosed tag selection <[...]>', index: tagStart, length: 2 });
    }

    // 4. Check for unclosed conditionals [if
    const ifPattern = /\[if\s+[^\]]*$/i;
    const ifMatch = text.match(ifPattern);
    if (ifMatch) {
        errors.push({ type: 'unclosed', message: 'Unclosed conditional [if ...]', index: ifMatch.index, length: ifMatch[0].length });
    }

    // 5. Check for missing wildcard files (only if we have the list)
    if (knownWildcards.length > 0) {
        const wildcardRe = /__([a-zA-Z0-9_\-\/]+)__/g;
        let wcMatch;
        while ((wcMatch = wildcardRe.exec(text)) !== null) {
            const wcName = wcMatch[1];
            // Skip special prefixes
            if (wcName.startsWith('@') || wcName.startsWith('~') || wcName.includes('[')) continue;
            // Skip if it looks like a range ($$)
            if (wcMatch[0].includes('$$')) continue;

            const normalizedName = wcName.toLowerCase();
            const exists = knownWildcards.some(w => w.toLowerCase() === normalizedName);
            if (!exists) {
                errors.push({
                    type: 'missing',
                    message: `Wildcard file not found: ${wcName}`,
                    index: wcMatch.index,
                    length: wcMatch[0].length,
                    content: wcMatch[0]
                });
            }
        }
    }

    // 6. Check for missing LoRA files (only if we have the list)
    if (knownLoras.length > 0) {
        const loraRe = /<lora:([^:>]+)/gi;
        let loraMatch;
        while ((loraMatch = loraRe.exec(text)) !== null) {
            const loraName = loraMatch[1];
            const exists = knownLoras.some(l => {
                const lName = l.replace(/\.(safetensors|ckpt|pt)$/i, '');
                return lName.toLowerCase() === loraName.toLowerCase() ||
                    l.toLowerCase() === loraName.toLowerCase();
            });
            if (!exists) {
                errors.push({
                    type: 'missing',
                    message: `LoRA not found: ${loraName}`,
                    index: loraMatch.index,
                    length: loraMatch[0].length + 1,
                    content: loraMatch[0]
                });
            }
        }
    }

    // 7. Check for unclosed parentheses (weights)
    let parenCount = 0;
    let parenStart = -1;
    for (let i = 0; i < text.length; i++) {
        if (text[i] === '(') {
            if (parenCount === 0) parenStart = i;
            parenCount++;
        } else if (text[i] === ')') {
            parenCount--;
            if (parenCount < 0) {
                errors.push({ type: 'unclosed', message: 'Unexpected closing parenthesis )', index: i, length: 1 });
                parenCount = 0;
            }
        }
    }
    if (parenCount > 0) {
        errors.push({ type: 'unclosed', message: 'Unclosed parenthesis (', index: parenStart, length: 1 });
    }

    return errors;
}

// Main syntax highlighting function with linting
function highlightSyntax(text, errors = []) {
    if (!text) return "&nbsp;";

    // First escape HTML
    let result = escapeHtml(text);

    // Order matters! Apply patterns from most specific to least specific

    // 1. Comments (lines starting with # or //)
    result = result.replace(/(^|\n)(#[^\n]*)/g, '$1<span class="umi-hl-comment">$2</span>');
    result = result.replace(/(^|\n)(\/\/[^\n]*)/g, '$1<span class="umi-hl-comment">$2</span>');

    // 2. LoRA tags: <lora:name:strength> or <lora:name>
    result = result.replace(/(&lt;lora:[^&]*?&gt;)/gi, '<span class="umi-hl-lora">$1</span>');

    // 3. Tag selection: <[...]>
    result = result.replace(/(&lt;\[[^\]]*?\]&gt;)/g, '<span class="umi-hl-tag-select">$1</span>');

    // 4. Prompt file loader: __@filename__
    result = result.replace(/(__@[\w\-\/]+__)/g, '<span class="umi-hl-prompt-file">$1</span>');

    // 5. Range wildcards: __2-4$$tag__ or __~tag__
    result = result.replace(/(__[\d\-]+\$\$[^_]+__)/g, '<span class="umi-hl-range">$1</span>');
    result = result.replace(/(__~[\w\-\/]+__)/g, '<span class="umi-hl-range">$1</span>');

    // 6. Regular wildcards: __tag__
    result = result.replace(/(__[\w\-\/\[\]]+__)/g, '<span class="umi-hl-wildcard">$1</span>');

    // 7. Conditionals: [if condition: true | false]
    result = result.replace(/(\[if\s+[^\]]+\])/gi, '<span class="umi-hl-conditional">$1</span>');

    // 8. Functions: [shuffle:...] and [clean:...]
    result = result.replace(/(\[(shuffle|clean):[^\]]*\])/gi, '<span class="umi-hl-function">$1</span>');

    // 9. Negative markers: **text** and --neg: text
    result = result.replace(/(\*\*[^*]+\*\*)/g, '<span class="umi-hl-negative">$1</span>');
    result = result.replace(/(--neg:[^\n,]+)/gi, '<span class="umi-hl-negative">$1</span>');

    // 10. Variables: $variable (word characters only)
    result = result.replace(/(\$[\w]+)/g, '<span class="umi-hl-variable">$1</span>');

    // 11. Dynamic choices: {option1|option2|option3}
    result = result.replace(/(\{[^{}]+\})/g, '<span class="umi-hl-dynamic">$1</span>');

    // 12. Weights: (text:1.2) - SD weight syntax
    result = result.replace(/(\([^():]+:\d+\.?\d*\))/g, '<span class="umi-hl-weight">$1</span>');

    // Add trailing newline to match textarea behavior
    result += "\n";

    return result;
}

// Apply syntax highlighting to a textarea element
function applyHighlighting(textareaEl) {
    if (!textareaEl) {
        console.log("[UmiAI Syntax] No textarea element provided");
        return null;
    }

    // Skip if already enhanced
    if (textareaEl.dataset.umiSyntax === "true") {
        console.log("[UmiAI Syntax] Already enhanced, skipping");
        return null;
    }

    console.log("[UmiAI Syntax] Applying highlighting to textarea");
    textareaEl.dataset.umiSyntax = "true";

    // Get the parent container
    const parent = textareaEl.parentElement;
    if (!parent) {
        console.log("[UmiAI Syntax] No parent element");
        return null;
    }

    // Create backdrop for highlighting
    const backdrop = document.createElement("div");
    backdrop.className = "umi-syntax-backdrop";

    // Create lint status bar
    const lintBar = document.createElement("div");
    lintBar.className = "umi-lint-bar umi-lint-bar-clean";
    lintBar.innerHTML = '<span class="umi-lint-icon">✓</span> No issues';

    // Ensure parent has relative positioning
    const parentStyle = getComputedStyle(parent);
    if (parentStyle.position === "static") {
        parent.style.position = "relative";
    }

    // Save original styles and apply new ones
    textareaEl.dataset.origBackground = textareaEl.style.background || "";
    textareaEl.dataset.origColor = textareaEl.style.color || "";

    // Apply transparent overlay style to textarea
    textareaEl.classList.add("umi-syntax-textarea");

    // Add some bottom padding for the lint bar
    textareaEl.style.paddingBottom = "26px";
    backdrop.style.paddingBottom = "26px";

    // Insert backdrop before textarea
    parent.insertBefore(backdrop, textareaEl);
    parent.appendChild(lintBar);

    // Sync function
    const syncHighlight = () => {
        const text = textareaEl.value;
        const errors = lintPrompt(text);

        // Update highlighting
        backdrop.innerHTML = highlightSyntax(text, errors);

        // Update lint bar
        if (errors.length === 0) {
            lintBar.className = "umi-lint-bar umi-lint-bar-clean";
            lintBar.innerHTML = '<span class="umi-lint-icon">✓</span> No issues';
            lintBar.title = "";
        } else {
            lintBar.className = "umi-lint-bar umi-lint-bar-errors";
            const errorCount = errors.length;
            const firstError = errors[0].message;
            lintBar.innerHTML = `<span class="umi-lint-icon">⚠</span> ${errorCount} issue${errorCount > 1 ? 's' : ''}: ${firstError}`;
            lintBar.title = errors.map(e => e.message).join('\n');
        }
    };

    // Sync scroll positions
    const syncScroll = () => {
        backdrop.scrollTop = textareaEl.scrollTop;
        backdrop.scrollLeft = textareaEl.scrollLeft;
    };

    // Event listeners for highlighting
    textareaEl.addEventListener("input", syncHighlight);
    textareaEl.addEventListener("scroll", syncScroll);
    textareaEl.addEventListener("keyup", syncHighlight);
    textareaEl.addEventListener("change", syncHighlight);

    // Event listeners for hover preview
    textareaEl.addEventListener("mousemove", (e) => {
        if (hoverTimeout) clearTimeout(hoverTimeout);
        hoverTimeout = setTimeout(() => handleWildcardHover(e, textareaEl), 300);
    });

    textareaEl.addEventListener("mouseleave", () => {
        hidePreviewTooltip();
    });

    textareaEl.addEventListener("mousedown", () => {
        hidePreviewTooltip();
    });

    // Initial sync
    syncHighlight();

    console.log("[UmiAI Syntax] Highlighting applied successfully");

    return { backdrop, lintBar, syncHighlight, syncScroll };
}

// =============================================================================
// AUTO-APPLY TO UMI NODES
// =============================================================================
app.registerExtension({
    name: "UmiAI.SyntaxHighlight",

    async setup() {
        console.log("[UmiAI Syntax] Extension setup");
        injectStyles();
        // Fetch wildcards for linting
        await fetchWildcardsForLinting();
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Use correct internal node names
        if (nodeData.name !== "UmiAIWildcardNode" && nodeData.name !== "UmiAIWildcardNodeLite") {
            return;
        }

        console.log("[UmiAI Syntax] Registering for node:", nodeData.name);

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const self = this;

            // Function to apply syntax highlighting
            const applySyntaxHighlighting = () => {
                // Find the text widget
                const textWidget = self.widgets?.find(w => w.name === "text");
                if (!textWidget) {
                    console.log("[UmiAI Syntax] No 'text' widget found");
                    return;
                }

                const inputEl = textWidget.inputEl;
                if (!inputEl) {
                    console.log("[UmiAI Syntax] No inputEl found on text widget");
                    return;
                }

                console.log("[UmiAI Syntax] Found text widget inputEl:", inputEl.tagName);

                // Apply highlighting
                const result = applyHighlighting(inputEl);
                if (result) {
                    self._syntaxHighlight = result;
                }
            };

            // Try immediately
            setTimeout(applySyntaxHighlighting, 100);

            // Also try after a longer delay in case widget isn't ready
            setTimeout(applySyntaxHighlighting, 500);
            setTimeout(applySyntaxHighlighting, 1000);
        };
    }
});

console.log("[UmiAI Syntax] Module loaded");
