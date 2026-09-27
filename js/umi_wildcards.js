import { app } from "../../scripts/app.js";
import { ensureUmiTheme, T } from "./umi_theme.js";

// =============================================================================
// PART 1: AUTOCOMPLETE LOGIC (Enhanced with Fuzzy Search & Context Awareness)
// =============================================================================

class AutoCompletePopup {
    constructor() {
        this.element = document.createElement("div");
        Object.assign(this.element.style, {
            position: "fixed",
            display: "none",
            backgroundColor: T.ground,
            border: `1px solid ${T.rule}`,
            zIndex: "10001",
            maxHeight: "250px",
            overflowY: "auto",
            color: T.ink,
            fontFamily: "'Consolas', 'Monaco', monospace",
            fontSize: "13px",
            borderRadius: "4px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
            boxSizing: "border-box",
            minWidth: "min(250px, calc(100vw - 16px))",
            maxWidth: "min(520px, calc(100vw - 16px))"
        });
        ensureUmiTheme();
        document.body.appendChild(this.element);

        this.visible = false;
        this.items = [];
        this.selectedIndex = 0;
        this.onSelectCallback = null;
        this.listItems = []; // Store references to list item elements
    }

    // anchor is a viewport-space caret box: {left, top, bottom}. The popup
    // opens below the caret when there is room and above it when there is not,
    // so typing near the bottom of a tall textarea no longer covers the text.
    show(anchor, options, onSelect) {
        this.items = options;
        this.onSelectCallback = onSelect;
        this.selectedIndex = 0;
        this.visible = true;

        const GAP = 4;
        const MARGIN = 8;
        const viewportH = window.innerHeight;
        const viewportW = window.innerWidth;

        // Measure at natural height before deciding, with the cap lifted.
        this.element.style.maxHeight = "none";
        this.element.style.visibility = "hidden";
        this.element.style.display = "block";
        this.element.style.top = "0px";
        this.element.style.left = "0px";
        this.render();

        const natural = this.element.offsetHeight;
        const width = this.element.offsetWidth;
        const spaceBelow = viewportH - anchor.bottom - GAP - MARGIN;
        const spaceAbove = anchor.top - GAP - MARGIN;

        const openUp = spaceBelow < Math.min(natural, 120) && spaceAbove > spaceBelow;
        const room = Math.max(80, openUp ? spaceAbove : spaceBelow);
        const height = Math.min(natural, room, 250);

        this.element.style.maxHeight = height + "px";
        this.element.style.top = (openUp ? anchor.top - GAP - height : anchor.bottom + GAP) + "px";

        // Keep long wildcard names from pushing the list off-screen.
        const left = Math.max(MARGIN, Math.min(anchor.left, viewportW - width - MARGIN));
        this.element.style.left = left + "px";

        this.element.style.visibility = "visible";
        this.openedUpward = openUp;
    }

    hide() {
        this.onSelectCallback = null;
        this.owner = null;
        this.element.style.display = "none";
        this.element.style.visibility = "visible";
        this.visible = false;
        this.items = [];
        this.listItems = [];
    }

    // Update visual styles without rebuilding DOM
    updateSelection(newIndex) {
        const oldIndex = this.selectedIndex;
        this.selectedIndex = newIndex;

        // Update old item styles
        if (this.listItems[oldIndex]) {
            this.listItems[oldIndex].style.backgroundColor = "transparent";
            this.listItems[oldIndex].style.color = T.ink;
            this.listItems[oldIndex].style.borderLeft = "3px solid transparent";
        }

        // Update new item styles
        if (this.listItems[newIndex]) {
            this.listItems[newIndex].style.backgroundColor = T.accent_soft;
            this.listItems[newIndex].style.color = T.ink_strong;
            this.listItems[newIndex].style.borderLeft = `3px solid ${T.accent}`;
        }

        // Auto-scroll to selected item
        this.scrollToSelected();
    }

    scrollToSelected() {
        // +1 because first child is the header
        const activeEl = this.element.children[this.selectedIndex + 1];
        if (activeEl) {
            if (activeEl.offsetTop < this.element.scrollTop) {
                this.element.scrollTop = activeEl.offsetTop;
            } else if (activeEl.offsetTop + activeEl.offsetHeight > this.element.scrollTop + this.element.offsetHeight) {
                this.element.scrollTop = activeEl.offsetTop + activeEl.offsetHeight - this.element.offsetHeight;
            }
        }
    }

    render() {
        this.element.innerHTML = "";
        this.listItems = [];

        // Header
        const header = document.createElement("div");
        Object.assign(header.style, {
            padding: "4px 8px", fontSize: "11px", color: T.ink_3,
            borderBottom: `1px solid ${T.rule}`, backgroundColor: T.surface_alt
        });
        header.innerText = this.items.length > 50
            ? `Showing 50 of ${this.items.length} matches...`
            : `${this.items.length} Suggestions`;
        this.element.appendChild(header);

        // List Items (Limit to 50 for performance)
        this.items.slice(0, 50).forEach((opt, index) => {
            const div = document.createElement("div");

            const category = getSuggestionCategory(opt);
            const categoryColor = TAG_CATEGORY_COLORS[category];
            const count = opt && typeof opt === "object" ? opt.count : undefined;

            if (categoryColor || count !== undefined) {
                // Name in its category colour, occurrence count trailing and
                // dimmed, so the two read as separate pieces of information.
                const name = document.createElement("span");
                name.innerText = getSuggestionValue(opt);
                if (categoryColor) name.style.color = categoryColor;
                if (category !== null && TAG_CATEGORY_NAMES[category]) {
                    div.title = `${getSuggestionValue(opt)} — ${TAG_CATEGORY_NAMES[category]}`
                        + (count !== undefined ? ` — ${count} posts` : "");
                }
                div.appendChild(name);

                if (count !== undefined) {
                    const badge = document.createElement("span");
                    badge.innerText = formatTagCount(count);
                    Object.assign(badge.style, {
                        float: "right", color: T.ink_3, fontSize: "11px",
                        marginLeft: "10px", paddingTop: "1px",
                    });
                    div.appendChild(badge);
                }
            } else {
                div.innerText = getSuggestionDisplayText(opt);
            }

            Object.assign(div.style, {
                cursor: "pointer", padding: "6px 10px",
                borderBottom: `1px solid ${T.rule}`, transition: "background 0.05s",
                overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis",
            });

            if (index === this.selectedIndex) {
                div.style.backgroundColor = T.accent_soft;
                div.style.borderLeft = `3px solid ${T.accent}`;
                if (!categoryColor) div.style.color = T.ink_strong;
            } else {
                div.style.backgroundColor = "transparent";
                div.style.borderLeft = "3px solid transparent";
            }

            div.onmouseover = () => {
                // Update selection WITHOUT re-rendering entire DOM
                if (this.selectedIndex !== index) {
                    this.updateSelection(index);
                }
            };

            div.onmousedown = (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.triggerSelection();
            };

            this.element.appendChild(div);
            this.listItems.push(div); // Store reference
        });

        // Auto-Scroll
        this.scrollToSelected();
    }

    navigate(direction) {
        if (!this.visible) return;
        const max = Math.min(this.items.length, 50) - 1;
        let newIndex;
        if (direction === 1) {
            newIndex = this.selectedIndex >= max ? 0 : this.selectedIndex + 1;
        } else {
            newIndex = this.selectedIndex <= 0 ? max : this.selectedIndex - 1;
        }
        this.updateSelection(newIndex);
    }

    triggerSelection() {
        if (this.visible && this.items[this.selectedIndex] !== undefined && this.onSelectCallback) {
            this.onSelectCallback(this.items[this.selectedIndex]);
            this.hide();
        }
    }
}

// =============================================================================
// PART 2: THE PROFESSIONAL USER GUIDE UI
// =============================================================================

const HELP_STYLES = `
    .umi-help-modal {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.88); z-index: 10000;
        display: flex; justify-content: center; align-items: center;
        backdrop-filter: blur(12px); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .umi-help-content {
        background: rgba(24, 24, 24, 0.98); width: 1050px; max-width: 95%; height: 92%;
        border-radius: 16px; box-shadow: 0 16px 64px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.08) inset;
        border: 1px solid rgba(97, 175, 239, 0.2); display: flex; flex-direction: column; overflow: hidden;
    }
    .umi-help-header {
        background: linear-gradient(135deg, rgba(97, 175, 239, 0.15) 0%, rgba(198, 120, 221, 0.1) 50%, rgba(86, 182, 194, 0.08) 100%);
        padding: 22px 40px; border-bottom: 1px solid rgba(97, 175, 239, 0.25);
        display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
    }
    .umi-help-header h2 { margin: 0; color: var(--umi-ink-strong); font-size: 26px; font-weight: 600; letter-spacing: 0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    .umi-help-header .version { font-size: 12px; color: var(--umi-ok); font-weight: 600; margin-left: 12px; background: rgba(152, 195, 121, 0.15); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(152, 195, 121, 0.3); }
    .umi-help-close {
        background: linear-gradient(135deg, var(--umi-danger) 0%, var(--umi-danger) 100%); color: white; border: none; padding: 10px 24px;
        border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(224, 108, 117, 0.3);
    }
    .umi-help-close:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(224, 108, 117, 0.4); }
    .umi-help-body {
        padding: 40px; overflow-y: auto; color: var(--umi-ink-2); line-height: 1.7;
        scrollbar-width: thin; scrollbar-color: var(--umi-rule-strong) var(--umi-ground);
    }
    
    /* Layout */
    .umi-section { margin-bottom: 50px; }
    .umi-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 20px; }
    
    /* Typography */
    .umi-help-body h3 { color: var(--umi-accent); border-bottom: 1px solid var(--umi-rule); padding-bottom: 10px; margin-top: 0; font-size: 20px; font-weight: 600; display: flex; align-items: center; }
    .umi-help-body h4 { color: var(--umi-warn); margin-bottom: 8px; margin-top: 20px; font-size: 15px; font-weight: 600; }
    .umi-help-body p { margin-top: 0; font-size: 14px; color: var(--umi-ink); }
    
    /* Components */
    .umi-code {
        background: var(--umi-surface-alt); padding: 2px 6px; border-radius: 4px; 
        font-family: "Consolas", "Monaco", monospace; color: var(--umi-ok); border: 1px solid var(--umi-rule-strong); font-size: 0.9em;
    }
    .umi-block {
        background: var(--umi-surface-alt); padding: 15px; border-radius: 6px; 
        font-family: "Consolas", "Monaco", monospace; color: var(--umi-ink); border-left: 4px solid var(--umi-accent);
        margin: 10px 0; white-space: pre-wrap; font-size: 12px; overflow-x: auto;
    }
    .umi-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 15px; border: 1px solid var(--umi-rule); }
    .umi-table th { text-align: left; background: var(--umi-surface-alt); border-bottom: 1px solid var(--umi-rule-strong); padding: 10px; color: var(--umi-ink-strong); }
    .umi-table td { border-bottom: 1px solid var(--umi-rule); padding: 10px; color: var(--umi-ink-3); background: var(--umi-ground); }
    .umi-table tr:last-child td { border-bottom: none; }
    
    /* Callouts */
    .umi-help-body .callout { padding: 15px; border-radius: 6px; margin-top: 20px; font-size: 13px; border-left: 4px solid; }
    .umi-help-body .callout-info { background: var(--umi-accent-wash); border-color: var(--umi-accent); color: var(--umi-ink); }
    .umi-help-body .callout-warn { background: var(--umi-crit-wash); border-color: var(--umi-danger); color: var(--umi-danger); }
    .umi-help-body .callout-success { background: var(--umi-ok-wash); border-color: var(--umi-ok); color: var(--umi-ok); }
    
    /* Wiring Diagram Style */
    .umi-help-body .step-list { margin: 0; padding: 0; list-style: none; counter-reset: step; }
    .umi-help-body .step-list li { position: relative; padding-left: 30px; margin-bottom: 10px; font-size: 14px; }
    .umi-help-body .step-list li::before {
        counter-increment: step; content: counter(step); 
        position: absolute; left: 0; top: 0; width: 20px; height: 20px; 
        background: var(--umi-rule); color: var(--umi-ink-strong); border-radius: 50%; 
        text-align: center; line-height: 20px; font-size: 11px; font-weight: bold;
    }

    /* Details/Summary */
    .umi-help-body details { background: var(--umi-surface); border-radius: 6px; padding: 10px; margin-bottom: 10px; border: 1px solid var(--umi-rule); transition: 0.2s; }
    .umi-help-body details[open] { background: var(--umi-surface-alt); border-color: var(--umi-rule-strong); }
    .umi-help-body summary { cursor: pointer; font-weight: 600; color: var(--umi-ink); outline: none; list-style: none; display: flex; justify-content: space-between; align-items: center; }
    .umi-help-body summary::after { content: "+"; color: var(--umi-accent); font-weight: bold; font-size: 16px; }
    .umi-help-body details[open] summary::after { content: "−"; }
    .umi-help-body details[open] summary { margin-bottom: 15px; border-bottom: 1px solid var(--umi-rule-strong); padding-bottom: 10px; }
`;

const HELP_HTML = `
    <div class="umi-section">
        <h3>What this node does</h3>
        <p>The Wildcard Processor takes one prompt template and expands it into a
        finished prompt: wildcard files, inline choices, variables, conditionals,
        negatives, LoRA tags and size hints. The same seed always produces the
        same result.</p>
        <div class="callout callout-info">
            <strong>Cannot tell what a template will produce?</strong> That is the
            point of it &mdash; press <span class="umi-code">Preview roll</span> on the
            node to expand it with the current seed without running the graph.
        </div>
    </div>

    <div class="umi-section">
        <h3>Wildcards</h3>
        <table class="umi-table">
            <tr><th>Syntax</th><th>Meaning</th></tr>
            <tr><td><span class="umi-code">__name__</span></td><td>One random line from <span class="umi-code">wildcards/name.txt</span>.</td></tr>
            <tr><td><span class="umi-code">__name|fallback__</span></td><td>Use the fallback text if the file is missing.</td></tr>
            <tr><td><span class="umi-code">__1-3$$name__</span></td><td>Pick one to three lines, comma joined.</td></tr>
            <tr><td><span class="umi-code">__~name__</span></td><td>Sequential: line <span class="umi-code">seed % lines</span>. Set the seed to increment to walk the file.</td></tr>
            <tr><td><span class="umi-code">__@name__</span></td><td>Insert a whole prompt file, not one line.</td></tr>
            <tr><td><span class="umi-code">__name[tag AND tag]__</span></td><td>Only lines matching the tag logic. Supports AND, OR, NOT, XOR, parentheses.</td></tr>
            <tr><td><span class="umi-code">&lt;[Entry Name]&gt;</span></td><td>Pull a prompt from a YAML entry.</td></tr>
            <tr><td><span class="umi-code">\__name__</span></td><td>Escaped: kept as literal text.</td></tr>
        </table>
    </div>

    <div class="umi-section">
        <h3>Repeating a wildcard</h3>
        <p>This one surprises people, so it is worth being explicit.</p>
        <table class="umi-table">
            <tr><th>Written as</th><th>Result</th></tr>
            <tr><td><span class="umi-code">__color__ shirt, __color__ pants</span></td><td><strong>Same</strong> colour. Bare repeats agree with each other.</td></tr>
            <tr><td><span class="umi-code">$top={__color__}<br>$skirt={__color__}</span></td><td><strong>Different</strong> colours. Separate variables are separate requests.</td></tr>
            <tr><td><span class="umi-code">$c={__color__}, $c ... $c</span></td><td>Same colour. A variable holds one resolved value.</td></tr>
            <tr><td><span class="umi-code">__@a:color__ / __@b:color__</span></td><td>Different colours, without variables. <span class="umi-code">@name:</span> gives an occurrence its own scope.</td></tr>
        </table>
        <div class="callout callout-info">
            Scoped and variable picks are drawn <em>without replacement</em>, so they
            differ wherever the file has enough lines to go around. Once the pool runs
            out it starts reusing values rather than failing &mdash; three variables on a
            two&#8209;line file give two distinct values and one repeat.
        </div>
    </div>

    <div class="umi-section">
        <h3>Choices, variables and conditionals</h3>
        <table class="umi-table">
            <tr><th>Syntax</th><th>Meaning</th></tr>
            <tr><td><span class="umi-code">{a|b|c}</span></td><td>One inline option.</td></tr>
            <tr><td><span class="umi-code">{25%a|b}</span></td><td>Weighted by percentage. Unassigned options split the remainder.</td></tr>
            <tr><td><span class="umi-code">{2-3$$a|b|c|d}</span></td><td>Pick two or three of the options.</td></tr>
            <tr><td><span class="umi-code">$hair={red|blue}</span></td><td>Assign a variable, then use <span class="umi-code">$hair</span> anywhere after.</td></tr>
            <tr><td><span class="umi-code">\${hair|silver}</span></td><td>Use a default when the variable is unset.</td></tr>
            <tr><td><span class="umi-code">[if $x==a: yes elif $x==b: maybe else: no]</span></td><td>Branch on a variable.</td></tr>
        </table>
    </div>

    <div class="umi-section">
        <h3>Prompt functions</h3>
        <p>All eighteen are highlighted in the editor. Items split on top-level
        <span class="umi-code">|</span> only, so pipes inside nested braces stay put.</p>
        <table class="umi-table">
            <tr><th>Function</th><th>Meaning</th></tr>
            <tr><td><span class="umi-code">[choose: a|b]</span></td><td>Exactly one. Supports <span class="umi-code">item:weight</span>.</td></tr>
            <tr><td><span class="umi-code">[sample 2-3 from: a|b|c]</span></td><td>A fixed or ranged count.</td></tr>
            <tr><td><span class="umi-code">[and: a|b]</span> <span class="umi-code">[or: a|b]</span> <span class="umi-code">[xor: a|b]</span></td><td>All, a seeded non-empty subset, or exactly one.</td></tr>
            <tr><td><span class="umi-code">[shuffle: a, b]</span> <span class="umi-code">[clean: a,, b]</span></td><td>Reorder, or tidy comma spacing.</td></tr>
            <tr><td><span class="umi-code">[preset:name]</span></td><td>Insert a chunk from <span class="umi-code">prompt_presets.yaml</span>.</td></tr>
            <tr><td><span class="umi-code">[section:name]</span></td><td>Mark a block for reordering via <span class="umi-code">section_order</span>.</td></tr>
            <tr><td><span class="umi-code">[require:...]</span> <span class="umi-code">[assert:...]</span> <span class="umi-code">[forbid:...]</span> <span class="umi-code">[prefer:...]</span> <span class="umi-code">[warn:...]</span></td><td>Validation helpers. <span class="umi-code">warn</span> only speaks when <span class="umi-code">$debug</span> or <span class="umi-code">$trace</span> is set.</td></tr>
            <tr><td><span class="umi-code">[lora:alias:0.8]</span></td><td>Expands an alias into the angle-bracket form. Angle brackets are what actually loads.</td></tr>
            <tr><td><span class="umi-code">[anima:...]</span> and friends</td><td>Only present when the Anima overlay is installed.</td></tr>
        </table>
    </div>

    <div class="umi-section">
        <h3>Negatives</h3>
        <table class="umi-table">
            <tr><th>Syntax</th><th>Meaning</th></tr>
            <tr><td><span class="umi-code">[neg: blurry, bad hands]</span></td><td>Move text to the negative output.</td></tr>
            <tr><td><span class="umi-code">**watermark**</span></td><td>Shorthand for a single negative tag.</td></tr>
            <tr><td><span class="umi-code">--neg: "blurry"</span></td><td>CLI-style negative.</td></tr>
            <tr><td><span class="umi-code">[negative] ... [/negative]</span></td><td>A whole negative block.</td></tr>
            <tr><td><span class="umi-code">[neg_if:$style==photo]cartoon[/neg_if]</span></td><td>Conditional negative.</td></tr>
        </table>
    </div>

    <div class="umi-section">
        <h3>On the node</h3>
        <ul class="step-list">
            <li><strong>Preview roll</strong> &mdash; expand with the current seed and show the
            result, the seed used, how many wildcards were picked, and how many reused an
            earlier pick. Nothing is queued. Press it twice and it also shows what changed
            since the last roll.</li>
            <li><strong>Pin this roll</strong> &mdash; hold the last previewed expansion and
            reuse it verbatim, ignoring the seed and the template, until you unpin. Useful
            for keeping a prompt fixed while changing samplers or models.</li>
            <li><strong>Live syntax errors</strong> &mdash; the prompt box underlines unknown
            wildcards and unclosed delimiters as you type. Turn it off in Settings if you
            would rather not see it.</li>
            <li><strong>Autocomplete</strong> &mdash; type <span class="umi-code">__</span>,
            <span class="umi-code">&lt;[</span>, <span class="umi-code">&lt;lora:</span> or
            <span class="umi-code">$</span> for suggestions. Tags are coloured by category
            and show how many posts use them. Arrow keys navigate, Enter or Tab accepts.</li>
        </ul>
    </div>

    <div class="umi-section">
        <h3>Panels</h3>
        <ul class="step-list">
            <li><strong>Wildcards</strong> &mdash; browse and edit your wildcard files with
            their candidate counts. Blank lines and comments are not counted, so a file of
            comments correctly reads as offering nothing. <span class="umi-code">.yaml</span>
            files are listed alongside <span class="umi-code">.txt</span> ones and counted by
            entry rather than by line; saving one that would not parse is refused, with the
            parse error shown, rather than leaving a file that quietly matches nothing.
            <strong>Health</strong> reports empty files, single&#8209;candidate files, lines
            repeated inside a file, and lines duplicated across three or more files.</li>
            <li><strong>Run Inspector</strong> &mdash; the last run in detail: every wildcard
            pick with the file it came from, how many candidates it chose between, and
            whether it rolled or reused an earlier value. Needs run capture switched on;
            the panel offers a button.</li>
            <li><strong>Prompt History</strong> &mdash; recent prompts, searchable, with copy
            and reuse. Kept in memory for the session; saving to disk is opt&#8209;in.</li>
            <li><strong>Self Check</strong> &mdash; confirms this install is wired correctly:
            panels registered, routes reachable, theme picked up, node capabilities present.
            Copy the report if you need to send it to someone.</li>
        </ul>
    </div>

    <div class="umi-section">
        <h3>Comments and settings</h3>
        <table class="umi-table">
            <tr><th>Syntax</th><th>Meaning</th></tr>
            <tr><td><span class="umi-code"># note</span></td><td>A line starting with # is a comment, in prompts and in wildcard files.</td></tr>
            <tr><td><span class="umi-code">tag # note</span></td><td>A space then # comments out the rest. <span class="umi-code">deep#blue</span> stays intact.</td></tr>
            <tr><td><span class="umi-code">// note //</span></td><td>Toggles comment mode until the next // or end of line.</td></tr>
            <tr><td><span class="umi-code">@@width=832,height=1216@@</span></td><td>Set size from inside the prompt.</td></tr>
        </table>
        <div class="callout callout-success">
            The full syntax reference lives in <span class="umi-code">SYNTAX.md</span>, and
            <span class="umi-code">Umi Prompt Syntax Lint</span> checks a prompt without
            expanding any randomness.
        </div>
    </div>
`;

function showHelpModal() {
    if (!document.getElementById("umi-help-style")) {
        const style = document.createElement("style");
        style.id = "umi-help-style";
        style.innerHTML = HELP_STYLES;
        document.head.appendChild(style);
    }

    const modal = document.createElement("div");
    modal.className = "umi-help-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", "UmiAI User Guide");

    modal.innerHTML = `
        <div class="umi-help-content">
            <div class="umi-help-header">
                <div>
                    <h2>UmiAI User Guide <span class="version">lean</span></h2>
                </div>
                <button class="umi-help-close" type="button">CLOSE</button>
            </div>
            <div class="umi-help-body">
                ${HELP_HTML}
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    const close = () => {
        document.removeEventListener("keydown", onKeyDown);
        modal.remove();
    };
    const onKeyDown = (event) => {
        if (event.key === "Escape") {
            event.preventDefault();
            close();
        }
    };
    modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
    modal.querySelector(".umi-help-close")?.addEventListener("click", close);
    document.addEventListener("keydown", onKeyDown);
    modal.querySelector(".umi-help-close")?.focus();
}

window.umiShowHelpModal = showHelpModal;

// =============================================================================
// PART 3: REGISTRATION & DYNAMIC VISIBILITY
// =============================================================================

const UMI_WILDCARD_NODE_NAMES = new Set(["UmiAIWildcardNode", "UmiAIWildcardNodeLite"]);

function patchUmiHelpMenu(nodeType) {
    if (!nodeType?.prototype || nodeType.prototype._umiHelpMenuPatched) return;

    const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (_, options) {
        if (getExtraMenuOptions) getExtraMenuOptions.apply(this, arguments);
        if (!Array.isArray(options)) return;
        if (options.some(option => option?.__umiHelpMenu)) return;

        options.push(null);
        options.push({
            __umiHelpMenu: true,
            content: "Open UmiAI User Guide",
            callback: () => { showHelpModal(); }
        });
    };

    nodeType.prototype._umiHelpMenuPatched = true;
}

function patchRegisteredUmiNodeMenus() {
    const registered = window.LiteGraph?.registered_node_types || {};
    for (const [name, nodeType] of Object.entries(registered)) {
        if (UMI_WILDCARD_NODE_NAMES.has(name) || UMI_WILDCARD_NODE_NAMES.has(nodeType?.type)) {
            patchUmiHelpMenu(nodeType);
        }
    }
}

// Helper: Custom fuzzy search function for client-side filtering
function getSuggestionValue(option) {
    if (option === null || option === undefined) return "";
    if (typeof option === "string") return option;
    if (typeof option === "number" || typeof option === "boolean") return String(option);

    if (typeof option === "object") {
        const preferred = option.value ?? option.tag ?? option.name ?? option.label ?? option.text ?? option.title;
        if (preferred !== null && preferred !== undefined) return String(preferred);

        const firstString = Object.values(option).find(value => typeof value === "string" && value.trim());
        if (firstString) return firstString;
    }

    return "";
}

function getSuggestionDisplayText(option) {
    const value = getSuggestionValue(option);
    if (!value) return "";

    if (option && typeof option === "object" && option.count !== undefined) {
        return `${value} (${option.count})`;
    }

    return value;
}

// Danbooru tag categories, as the CSVs encode them in column 2. The server
// already returns this per tag; colouring by it is most of what makes a tag
// list scannable, since an artist and a character read very differently.
const TAG_CATEGORY_COLORS = {
    0: T.cat_general,
    1: T.cat_artist,
    3: T.cat_copyright,
    4: T.cat_character,
    5: T.cat_meta,
};
const TAG_CATEGORY_NAMES = {
    0: "general", 1: "artist", 3: "copyright", 4: "character", 5: "meta",
};

function getSuggestionCategory(option) {
    if (!option || typeof option !== "object") return null;
    const category = option.category;
    return category === undefined || category === null ? null : Number(category);
}

function formatTagCount(count) {
    const n = Number(count);
    if (!Number.isFinite(n)) return "";
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1000) return Math.round(n / 1000) + "k";
    return String(n);
}

// Tag lookups scan CSVs on the server, so one request per keystroke is waste --
// and the input/compositionend listeners needed for paste and IME make it
// worse. Results are cached by query, and the server is only consulted after a
// short quiet period. A superseded lookup resolves to null so its caller bails
// instead of leaving a promise pending forever.
const TAG_CACHE_LIMIT = 300;
const TAG_DEBOUNCE_MS = 120;
const tagQueryCache = new Map();
let tagDebounceTimer = null;
let supersedePendingLookup = null;

function rememberTags(query, tags) {
    tagQueryCache.set(query, tags);
    while (tagQueryCache.size > TAG_CACHE_LIMIT) {
        tagQueryCache.delete(tagQueryCache.keys().next().value);
    }
    return tags;
}

function lookupTags(ext, query) {
    if (tagQueryCache.has(query)) {
        const hit = tagQueryCache.get(query);
        tagQueryCache.delete(query);
        tagQueryCache.set(query, hit);          // move to most-recent
        return Promise.resolve(hit);
    }

    if (supersedePendingLookup) supersedePendingLookup();
    clearTimeout(tagDebounceTimer);

    return new Promise((resolve) => {
        supersedePendingLookup = () => resolve(null);
        tagDebounceTimer = setTimeout(async () => {
            supersedePendingLookup = null;
            const tags = await ext.fetchAutocompleteTags(query);
            resolve(rememberTags(query, tags || []));
        }, TAG_DEBOUNCE_MS);
    });
}

function getFuzzyMatches(query, allItems) {
    // FIX: If query is empty, return everything!
    if (!query || query.trim() === "") {
        return allItems.sort((a, b) => getSuggestionValue(a).localeCompare(getSuggestionValue(b)));
    }

    // Normalize query
    const lowerQuery = query.toLowerCase();

    // Score items
    const scored = allItems.map(item => {
        const itemText = getSuggestionValue(item);
        const lowerItem = itemText.toLowerCase();

        // 1. Exact Match
        if (lowerItem === lowerQuery) return { item, score: 100 };

        // 2. Starts With
        if (lowerItem.startsWith(lowerQuery)) return { item, score: 75 };

        // 3. Contains
        if (lowerItem.includes(lowerQuery)) return { item, score: 50 };

        // 4. Fuzzy Sequence Check
        let qIdx = 0;
        let fuzzyScore = 0;
        for (let i = 0; i < lowerItem.length; i++) {
            if (lowerItem[i] === lowerQuery[qIdx]) {
                qIdx++;
                fuzzyScore += (100 - i);
            }
            if (qIdx === lowerQuery.length) break;
        }

        if (qIdx === lowerQuery.length) {
            return { item, score: 10 + (fuzzyScore / 100) };
        }

        return { item, score: 0 };
    });

    // Filter out 0 scores and Sort by score DESC
    return scored
        .filter(s => s.score > 0)
        .sort((a, b) => b.score - a.score)
        .map(s => s.item);
}

// Viewport-space box of the text caret inside a textarea/input.
//
// Textareas expose selectionStart but no caret geometry, so the standard
// approach is to render the text up to the caret into a hidden mirror element
// copying every property that affects wrapping and glyph advance, then read the
// position of a marker span. Without this the suggestion list can only be
// placed relative to the field as a whole.
function caretViewportRect(el) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2 || 16;

    const mirror = document.createElement("div");
    const s = mirror.style;
    [
        "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant",
        "letterSpacing", "wordSpacing", "textTransform", "textIndent",
        "lineHeight", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
        "boxSizing", "tabSize",
    ].forEach((prop) => { s[prop] = style[prop]; });

    s.position = "absolute";
    s.visibility = "hidden";
    s.left = "-9999px";
    s.top = "0px";
    s.width = style.width;
    s.height = "auto";
    s.whiteSpace = style.whiteSpace === "nowrap" ? "pre" : "pre-wrap";
    s.overflowWrap = "break-word";

    // Two markers: one at the content origin, one at the caret. Measuring the
    // delta between them sidesteps any question of which edge offsetLeft and
    // offsetTop are relative to, which differs between the two axes.
    const origin = document.createElement("span");
    origin.textContent = "​";
    const marker = document.createElement("span");
    marker.textContent = "​";

    const caret = el.selectionStart ?? (el.value ? el.value.length : 0);
    mirror.appendChild(origin);
    mirror.appendChild(document.createTextNode((el.value || "").slice(0, caret)));
    mirror.appendChild(marker);
    document.body.appendChild(mirror);

    const deltaLeft = marker.offsetLeft - origin.offsetLeft;
    const deltaTop = marker.offsetTop - origin.offsetTop;
    document.body.removeChild(mirror);

    const contentLeft = rect.left + parseFloat(style.borderLeftWidth || 0) + parseFloat(style.paddingLeft || 0);
    const contentTop = rect.top + parseFloat(style.borderTopWidth || 0) + parseFloat(style.paddingTop || 0);
    const x = contentLeft + deltaLeft - el.scrollLeft;
    const y = contentTop + deltaTop - el.scrollTop;

    // A caret scrolled out of the field must not drag the popup outside it.
    const top = Math.min(Math.max(y, rect.top), Math.max(rect.top, rect.bottom - lineHeight));
    return { left: x, top, bottom: top + lineHeight };
}

function resolveWidgetInputElement(widget) {
    if (!widget) return null;

    const candidates = [
        widget.inputEl,
        widget.element,
        widget.domElement,
        widget.input,
    ];

    for (const candidate of candidates) {
        if (!candidate) continue;
        if (candidate instanceof HTMLTextAreaElement || candidate instanceof HTMLInputElement) {
            return candidate;
        }
        if (candidate instanceof HTMLElement) {
            const input = candidate.querySelector("textarea, input");
            if (input) return input;
        }
    }

    return null;
}

app.registerExtension({
    name: "UmiAI.WildcardSystem",
    async setup() {
        this.wildcards = [];
        this.loras = [];
        this.globals = {};  // { $varname: "value" }
        this.autocompleteTags = [];  // Tags from CSV files
        this.settings = {};

        this.fetchSettings = async () => {
            try {
                const resp = await fetch("/umiapp/settings");
                if (resp.ok) {
                    const data = await resp.json();
                    this.settings = data.settings || {};
                }
            } catch (e) {
                console.error("[UmiAI] Failed to load settings:", e);
                this.settings = {};
            }
            return this.settings;
        };

        this.setWidgetVisibility = (widget, visible) => {
            if (!widget) return false;

            if (!widget._umiOriginalType) {
                widget._umiOriginalType = widget.type;
            }
            if (!widget._umiOriginalComputeSize) {
                widget._umiOriginalComputeSize = widget.computeSize;
            }

            const nextType = visible ? widget._umiOriginalType : "hidden";
            const nextHidden = !visible;
            const nextComputeSize = visible ? widget._umiOriginalComputeSize : (() => [0, -4]);
            const changed = (
                widget.type !== nextType
                || widget.hidden !== nextHidden
                || widget.computeSize !== nextComputeSize
            );

            widget.type = nextType;
            widget.hidden = nextHidden;
            widget.computeSize = nextComputeSize;
            return changed;
        };

        this.resetWidgetToDefault = (widget, defaultValue) => {
            if (!widget) return false;
            const changed = widget.value !== defaultValue;
            widget.value = defaultValue;
            if (changed && typeof widget.callback === "function") {
                try {
                    widget.callback(defaultValue);
                } catch (e) {
                    console.warn(`[UmiAI] Failed to run callback for widget ${widget.name}:`, e);
                }
            }
            return changed;
        };

        this.sanitizeDisabledFeatureValues = (node) => {
            if (!node?.widgets?.length) return false;

            let changed = false;

            return changed;
        };

        this.applyFeatureVisibility = async (node) => {
            if (!node?.widgets?.length) return;

            if (!Object.keys(this.settings || {}).length) {
                await this.fetchSettings();
            }

            const rules = [];

            let changed = false;
            for (const widget of node.widgets) {
                const rule = rules.find((entry) => entry.names.includes(widget.name));
                if (rule) {
                    changed = this.setWidgetVisibility(widget, rule.enabled) || changed;
                }
            }

            if (changed) {
                node.setSize(node.computeSize());
                app.graph?.setDirtyCanvas?.(true, true);
            }
        };

        // Define a function we can call later to refresh the lists
        this.fetchWildcards = async () => {
            try {
                // Fetch from the correct endpoint (matches your new Python)
                const resp = await fetch("/umiapp/wildcards");
                if (resp.ok) {
                    const data = await resp.json();

                    if (Array.isArray(data)) {
                        this.wildcards = data;
                        this.promptFiles = data;
                        this.loras = [];
                        this.yamlTags = [];
                        this.basenames = {};
                    } else {
                        // New structure: separate txt wildcards from yaml tags
                        this.wildcards = data.wildcards || data.files || [];
                        this.promptFiles = data.prompt_files || this.wildcards;
                        this.loras = data.loras || [];
                        this.yamlTags = [...new Set([...(data.tags || []), ...(data.entry_names || [])])];
                        this.basenames = data.basenames || {};     // Basename -> full path

                        // Add basenames to wildcards list for easy lookup
                        // This allows typing just the filename without folder
                        const basenameList = Object.keys(this.basenames);
                        console.log(`[UmiAI] Loaded ${this.wildcards.length} wildcard files, ${this.yamlTags.length} YAML tags/entries, ${basenameList.length} basenames`);
                    }
                } else {
                    this.wildcards = [];
                    this.promptFiles = [];
                    this.loras = [];
                    this.yamlTags = [];
                    this.basenames = {};
                }
            } catch (e) {
                console.error("[UmiAI] Failed to load wildcards:", e);
                this.wildcards = [];
                this.promptFiles = [];
                this.loras = [];
                this.yamlTags = [];
                this.basenames = {};
            }
        };

        // Fetch globals/variables
        this.fetchGlobals = async () => {
            try {
                const resp = await fetch("/umiapp/globals");
                if (resp.ok) {
                    const data = await resp.json();
                    this.globals = data.variables || {};
                    console.log(`[UmiAI] Loaded ${Object.keys(this.globals).length} global variables`);
                }
            } catch (e) {
                console.error("[UmiAI] Failed to load globals:", e);
                this.globals = {};
            }
        };

        // Fetch autocomplete tags from CSV files (on-demand with query)
        this.fetchAutocompleteTags = async (query = "") => {
            try {
                const resp = await fetch(`/umiapp/autocomplete/tags?query=${encodeURIComponent(query)}&limit=50`);
                if (resp.ok) {
                    const data = await resp.json();
                    // Only return the filtered tags, don't store all tags in memory
                    if (query) {
                        return data.tags || [];
                    } else {
                        // Initial load - just log the total available
                        console.log(`[UmiAI] Tag autocomplete initialized: ${data.total || 0} tags available`);
                        return [];
                    }
                }
                return [];
            } catch (e) {
                console.error("[UmiAI] Failed to load autocomplete tags:", e);
                return [];
            }
        };

        // Independent startup reads can happen together.  Settings completes
        // before the optional tag-index warmup so disabling autocomplete also
        // avoids its server scan entirely.
        await Promise.all([this.fetchWildcards(), this.fetchGlobals(), this.fetchSettings()]);
        if (this.settings.enable_tag_autocomplete !== false) {
            await this.fetchAutocompleteTags();
        }
        this.popup = new AutoCompletePopup();
        patchRegisteredUmiNodeMenus();
        setTimeout(patchRegisteredUmiNodeMenus, 500);
        setTimeout(patchRegisteredUmiNodeMenus, 1500);

        window.addEventListener("umi-settings-updated", (event) => {
            this.settings = event.detail?.settings || {};
            for (const node of app.graph?._nodes || []) {
                if (node?.type === "UmiAIWildcardNode" || node?.type === "UmiAIWildcardNodeLite") {
                    this.applyFeatureVisibility(node);
                }
            }
        });
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Support BOTH Full and Lite nodes
        if (nodeData.name !== "UmiAIWildcardNode" && nodeData.name !== "UmiAIWildcardNodeLite") return;

        // 1. Add Help Menu
        patchUmiHelpMenu(nodeType);

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);
            const self = this;
            const ext = app.extensions.find(e => e.name === "UmiAI.WildcardSystem");

            // ============================================================
            // DYNAMIC WIDGET VISIBILITY LOGIC
            // ============================================================
            const legacyBypassWidget = this.widgets.find(w => w.name === "bypass_phrase");
            if (legacyBypassWidget) {
                legacyBypassWidget.type = "hidden";
                legacyBypassWidget.hidden = true;
                legacyBypassWidget.computeSize = () => [0, -4];
                this.setSize(this.computeSize());
            }
            const legacyBypassOutputIndex = this.outputs?.findIndex(o => o?.name === "bypass_matched");
            if (legacyBypassOutputIndex !== undefined && legacyBypassOutputIndex >= 0) {
                this.removeOutput(legacyBypassOutputIndex);
                this.setSize(this.computeSize());
            }

            ext?.applyFeatureVisibility?.(this);

            const llmWidgets = ["llm_model", "llm_temperature", "llm_max_tokens", "custom_system_prompt"];
            const triggerName = "llm_prompt_enhancer";

            const triggerWidget = this.widgets.find(w => w.name === triggerName);

            if (triggerWidget) {
                this.widgets.forEach(w => {
                    if (llmWidgets.includes(w.name)) {
                        w.origType = w.type;
                        w.origComputeSize = w.computeSize;
                    }
                });

                const refreshWidgets = () => {
                    const visible = triggerWidget.value === "Yes";
                    let changed = false;

                    for (const w of this.widgets) {
                        if (llmWidgets.includes(w.name)) {
                            if (visible && w.type === "hidden") {
                                w.type = w.origType;
                                w.computeSize = w.origComputeSize;
                                changed = true;
                            } else if (!visible && w.type !== "hidden") {
                                w.type = "hidden";
                                w.computeSize = () => [0, -4];
                                changed = true;
                            }
                        }
                    }
                    if (changed) this.setSize(this.computeSize());
                };

                const prevCallback = triggerWidget.callback;
                triggerWidget.callback = (value) => {
                    if (prevCallback) prevCallback(value);
                    refreshWidgets();
                };
                refreshWidgets();
            }

            // ============================================================
            // AUTOCOMPLETE LOGIC (WITH ARROW KEYS & FUZZY SEARCH)
            // ============================================================
            const textWidget = this.widgets.find(w => w.name === "text");
            const inputEl = resolveWidgetInputElement(textWidget);
            if (!textWidget || !inputEl) return;


            if (!ext) {
                console.error("[UmiAI] Extension not found for autocomplete");
                return;
            }

            let autocompleteRequestId = 0;
            let removed = false;
            let blurTimer;
            const listeners = [];
            const listen = (target, name, callback) => {
                target.addEventListener(name, callback);
                listeners.push(() => target.removeEventListener(name, callback));
            };
            const hideAutocomplete = () => {
                autocompleteRequestId++;
                if (ext.popup.owner === inputEl) ext.popup.hide();
            };
            const previousRemoved = this.onRemoved;
            this.onRemoved = function () {
                removed = true;
                clearTimeout(blurTimer);
                listeners.splice(0).forEach(remove => remove());
                hideAutocomplete();
                return previousRemoved?.apply(this, arguments);
            };
            inputEl.placeholder ||= "Write a prompt with __folder/name__ or {red|blue}. Browse files in the Wildcards panel.";

            // 1. INTERCEPT NAVIGATION (Arrow Keys, Enter, Tab)
            listen(inputEl, "keydown", (e) => {
                if (ext.popup.visible && ext.popup.owner === inputEl) {
                    if (e.key === "ArrowDown") {
                        e.preventDefault();
                        ext.popup.navigate(1); // Next
                        return;
                    }
                    if (e.key === "ArrowUp") {
                        e.preventDefault();
                        ext.popup.navigate(-1); // Prev
                        return;
                    }
                    if (e.key === "Enter" || e.key === "Tab") {
                        e.preventDefault();
                        ext.popup.triggerSelection();
                        return;
                    }
                    if (e.key === "Escape") {
                        hideAutocomplete();
                        return;
                    }
                }
            });

            listen(inputEl, "blur", () => {
                clearTimeout(blurTimer);
                blurTimer = setTimeout(() => {
                    if (document.activeElement !== inputEl && !ext.popup.element.contains(document.activeElement)) {
                        hideAutocomplete();
                    }
                }, 0);
            });

            // 2. LISTEN FOR TYPING (To show the popup)
            const handleTyping = async (e) => {
                if (removed) return;
                // Ignore nav keys in this listener to prevent flashing
                if (["ArrowUp", "ArrowDown", "Enter", "Escape", "Tab"].includes(e.key)) return;

                if (!ext || !ext.popup) {
                    console.warn("[UmiAI] Extension or popup not available");
                    return;
                }

                const cursor = inputEl.selectionStart;
                const text = inputEl.value;
                const beforeCursor = text.substring(0, cursor);
                const requestId = ++autocompleteRequestId;

                // Regex for __@ (prompt files - full text file as prompt)
                const matchPromptFile = beforeCursor.match(/__@((?:(?!__)[^\r\n<>|{}])*)$/u);
                // Regex for __ (wildcards - txt files, picks random line)
                const matchWildcard = beforeCursor.match(/__((?:(?!__)[^\r\n<>|{}])*)$/u);
                // Regex for <[ (tags from yaml files)
                const matchTag = beforeCursor.match(/<\[([^\r\n<>\]]*)$/u);
                const matchLora = beforeCursor.match(/<lora:([^>]*)$/);

                let options = [];
                let triggerType = "";
                let matchIndex = 0;
                let query = "";
                let opener = "";

                // -- Prompt File Logic (__@ = full text files as prompts) --
                if (matchPromptFile) {
                    triggerType = "promptfile";
                    opener = "__@";
                    query = matchPromptFile[1];
                    matchIndex = matchPromptFile.index;

                    // Use wildcards list for __@ autocomplete (same txt files, but loads full content)
                    const allWildcards = [...(ext.promptFiles || ext.wildcards)];
                    const basenameKeys = allWildcards.map(name => name.split('/').pop());

                    basenameKeys.forEach(basename => {
                        if (!allWildcards.includes(basename)) {
                            allWildcards.push(basename);
                        }
                    });

                    options = getFuzzyMatches(query, allWildcards);
                }
                // -- Wildcard Logic (__ = TXT, YAML/YML and CSV files) --
                else if (matchWildcard) {
                    triggerType = "wildcard";
                    opener = "__";
                    query = matchWildcard[1];
                    matchIndex = matchWildcard.index;

                    // Combine full paths with basenames for search
                    // This allows users to type just the filename without folder
                    const allWildcards = [...ext.wildcards];
                    const basenameKeys = Object.keys(ext.basenames || {});

                    // Add basenames that aren't already in the list
                    basenameKeys.forEach(basename => {
                        if (!allWildcards.includes(basename)) {
                            allWildcards.push(basename);
                        }
                    });

                    options = getFuzzyMatches(query, allWildcards);
                }
                // -- Tag Logic (<[ = yaml tags only) --
                else if (matchTag) {
                    triggerType = "tag";
                    opener = "<[";
                    query = matchTag[1];
                    matchIndex = matchTag.index;

                    // Use yaml tags for <[ autocomplete
                    options = getFuzzyMatches(query, ext.yamlTags || []);
                }
                // -- LoRA Logic --
                else if (matchLora) {
                    triggerType = "lora";
                    query = matchLora[1];
                    matchIndex = matchLora.index;

                    // Use fuzzy matching on the fetched LoRA list
                    options = getFuzzyMatches(query, ext.loras);
                }
                // -- Variable Logic (Smart Variable Suggestions) --
                else {
                    const matchVar = beforeCursor.match(/\$([\w]*)$/);
                    if (matchVar && ext.globals && Object.keys(ext.globals).length > 0) {
                        triggerType = "variable";
                        query = matchVar[1];
                        matchIndex = matchVar.index;

                        // Get variable names and filter by query
                        const varNames = Object.keys(ext.globals);
                        options = getFuzzyMatches(query, varNames.map(v => v.replace(/^\$/, '')));
                    }
                    // -- Tag Autocomplete Logic (after comma or space) --
                    else if (ext.settings?.enable_tag_autocomplete !== false) {
                        // Match tags after comma or space, or at the start
                        const matchGeneralTag = beforeCursor.match(/(?:^|[,\s]+)([a-zA-Z0-9_\-]{2,})$/);
                        if (matchGeneralTag && matchGeneralTag[1].length >= 2) {
                            triggerType = "generaltag";
                            query = matchGeneralTag[1];
                            matchIndex = beforeCursor.length - query.length;

                            // Debounced and cached; null means a later keystroke
                            // superseded this lookup.
                            const tags = await lookupTags(ext, query);
                            if (tags === null) return;
                            if (requestId !== autocompleteRequestId || document.activeElement !== inputEl) {
                                return;
                            }
                            options = tags;
                        }
                    }
                }

                if (requestId !== autocompleteRequestId || document.activeElement !== inputEl) {
                    return;
                }

                if (triggerType && options.length > 0) {
                    ext.popup.owner = inputEl;
                    ext.popup.show(caretViewportRect(inputEl), options, (selected) => {
                        const selectedValue = getSuggestionValue(selected);
                        if (!selectedValue) {
                            hideAutocomplete();
                            return;
                        }

                        let completion = "";

                        // Smart Completion based on trigger type
                        if (triggerType === "promptfile") {
                            // Resolve basename to full path if needed
                            const resolvedPath = ext.basenames?.[selectedValue] || selectedValue;
                            completion = `__@${resolvedPath}__`;
                        }
                        else if (triggerType === "wildcard") {
                            // Resolve basename to full path if needed
                            const resolvedPath = ext.basenames?.[selectedValue] || selectedValue;
                            completion = `__${resolvedPath}__`;
                        }
                        else if (triggerType === "tag") {
                            completion = `<[${selectedValue}]>`;
                        }
                        else if (triggerType === "lora") {
                            completion = `<lora:${selectedValue}:1.0>`;
                        }
                        else if (triggerType === "variable") {
                            completion = `$${selectedValue}`;
                        }
                        else if (triggerType === "generaltag") {
                            completion = selectedValue;
                        }

                        const prefix = text.substring(0, matchIndex);
                        const suffix = text.substring(cursor);

                        inputEl.value = prefix + completion + suffix;

                        // Notify ComfyUI of change
                        if (textWidget.callback) textWidget.callback(inputEl.value);

                        // Trigger input event for syntax highlighting
                        inputEl.dispatchEvent(new Event('input', { bubbles: true }));

                        // Move cursor to end of inserted tag
                        const newCursorPos = (prefix + completion).length;
                        inputEl.setSelectionRange(newCursorPos, newCursorPos);
                        inputEl.focus();
                        autocompleteRequestId++;
                    });
                } else {
                    hideAutocomplete();
                }
            };

            // keyup alone misses pasted text, middle-click paste and IME commits.
            listen(inputEl, "keyup", handleTyping);
            listen(inputEl, "input", handleTyping);
            listen(inputEl, "compositionend", handleTyping);

            // Close on outside click
            listen(document, "mousedown", (e) => {
                if (ext && ext.popup && e.target !== ext.popup.element && !ext.popup.element.contains(e.target) && e.target !== inputEl) {
                    hideAutocomplete();
                }
            });
        };

        const onSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (info) {
            if (onSerialize) onSerialize.apply(this, arguments);
            if (!info) return;
            if (!info.properties) info.properties = {};
            const valuesByName = {};
            for (const widget of this.widgets || []) {
                if (!widget?.name) continue;
                valuesByName[widget.name] = widget.value;
            }
            info.properties.umi_widget_values_by_name = valuesByName;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            if (onConfigure) onConfigure.apply(this, arguments);
            const valuesByName = info?.properties?.umi_widget_values_by_name;
            if (valuesByName && typeof valuesByName === "object") {
                for (const widget of this.widgets || []) {
                    if (!widget?.name || !(widget.name in valuesByName)) continue;
                    widget.value = valuesByName[widget.name];
                    if (widget.inputEl) {
                        widget.inputEl.value = widget.value ?? "";
                    }
                }
            }
            const ext = app.extensions.find(e => e.name === "UmiAI.WildcardSystem");
            ext?.applyFeatureVisibility?.(this);
        };
    }
});
