import { app } from "../../scripts/app.js";

// =============================================================================
// PART 1: AUTOCOMPLETE LOGIC (Enhanced with Fuzzy Search & Context Awareness)
// =============================================================================

class AutoCompletePopup {
    constructor() {
        this.element = document.createElement("div");
        Object.assign(this.element.style, {
            position: "absolute",
            display: "none",
            backgroundColor: "#1e1e1e",
            border: "1px solid #61afef",
            zIndex: "9999",
            maxHeight: "250px",
            overflowY: "auto",
            color: "#e0e0e0",
            fontFamily: "'Consolas', 'Monaco', monospace",
            fontSize: "13px",
            borderRadius: "4px",
            boxShadow: "0 10px 25px rgba(0,0,0,0.8)",
            minWidth: "250px"
        });
        document.body.appendChild(this.element);

        this.visible = false;
        this.items = [];
        this.selectedIndex = 0;
        this.onSelectCallback = null;
    }

    show(x, y, options, onSelect) {
        this.items = options;
        this.onSelectCallback = onSelect;
        this.selectedIndex = 0;
        this.visible = true;

        this.element.style.left = x + "px";
        this.element.style.top = y + "px";
        this.element.style.display = "block";
        this.render();
    }

    hide() {
        this.element.style.display = "none";
        this.visible = false;
        this.items = [];
    }

    render() {
        this.element.innerHTML = "";

        // Header
        const header = document.createElement("div");
        Object.assign(header.style, {
            padding: "4px 8px", fontSize: "11px", color: "#888",
            borderBottom: "1px solid #333", backgroundColor: "#252525"
        });
        header.innerText = this.items.length > 50
            ? `Showing 50 of ${this.items.length} matches...`
            : `${this.items.length} Suggestions`;
        this.element.appendChild(header);

        // List Items (Limit to 50 for performance)
        this.items.slice(0, 50).forEach((opt, index) => {
            const div = document.createElement("div");
            div.innerText = opt;

            Object.assign(div.style, {
                cursor: "pointer", padding: "6px 10px",
                borderBottom: "1px solid #2a2a2a", transition: "background 0.05s"
            });

            if (index === this.selectedIndex) {
                div.style.backgroundColor = "#2d4f6c";
                div.style.color = "#fff";
                div.style.borderLeft = "3px solid #61afef";
            } else {
                div.style.backgroundColor = "transparent";
                div.style.borderLeft = "3px solid transparent";
            }

            div.onmouseover = () => {
                this.selectedIndex = index;
                this.render();
            };

            div.onmousedown = (e) => {
                e.preventDefault();
                this.triggerSelection();
            };

            this.element.appendChild(div);
        });

        // Auto-Scroll
        if (this.element.children[this.selectedIndex + 1]) {
            const activeEl = this.element.children[this.selectedIndex + 1];
            if (activeEl.offsetTop < this.element.scrollTop) {
                this.element.scrollTop = activeEl.offsetTop;
            } else if (activeEl.offsetTop + activeEl.offsetHeight > this.element.scrollTop + this.element.offsetHeight) {
                this.element.scrollTop = activeEl.offsetTop + activeEl.offsetHeight - this.element.offsetHeight;
            }
        }
    }

    navigate(direction) {
        if (!this.visible) return;
        const max = Math.min(this.items.length, 50) - 1;
        if (direction === 1) {
            this.selectedIndex = this.selectedIndex >= max ? 0 : this.selectedIndex + 1;
        } else {
            this.selectedIndex = this.selectedIndex <= 0 ? max : this.selectedIndex - 1;
        }
        this.render();
    }

    triggerSelection() {
        if (this.visible && this.items[this.selectedIndex] && this.onSelectCallback) {
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
    .umi-help-header h2 { margin: 0; color: #fff; font-size: 26px; font-weight: 600; letter-spacing: 0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    .umi-help-header .version { font-size: 12px; color: #98c379; font-weight: 600; margin-left: 12px; background: rgba(152, 195, 121, 0.15); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(152, 195, 121, 0.3); }
    .umi-help-close {
        background: linear-gradient(135deg, #e06c75 0%, #be5046 100%); color: white; border: none; padding: 10px 24px;
        border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(224, 108, 117, 0.3);
    }
    .umi-help-close:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(224, 108, 117, 0.4); }
    .umi-help-body {
        padding: 40px; overflow-y: auto; color: #ccc; line-height: 1.7;
        scrollbar-width: thin; scrollbar-color: #444 #181818;
    }
    
    /* Layout */
    .umi-section { margin-bottom: 50px; }
    .umi-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 20px; }
    
    /* Typography */
    h3 { color: #61afef; border-bottom: 1px solid #333; padding-bottom: 10px; margin-top: 0; font-size: 20px; font-weight: 600; display: flex; align-items: center; }
    h4 { color: #e5c07b; margin-bottom: 8px; margin-top: 20px; font-size: 15px; font-weight: 600; }
    p { margin-top: 0; font-size: 14px; color: #abb2bf; }
    
    /* Components */
    .umi-code {
        background: #282c34; padding: 2px 6px; border-radius: 4px; 
        font-family: "Consolas", "Monaco", monospace; color: #98c379; border: 1px solid #3e4451; font-size: 0.9em;
    }
    .umi-block {
        background: #282c34; padding: 15px; border-radius: 6px; 
        font-family: "Consolas", "Monaco", monospace; color: #abb2bf; border-left: 4px solid #61afef;
        margin: 10px 0; white-space: pre-wrap; font-size: 12px; overflow-x: auto;
    }
    .umi-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 15px; border: 1px solid #333; }
    .umi-table th { text-align: left; background: #252525; border-bottom: 1px solid #444; padding: 10px; color: #fff; }
    .umi-table td { border-bottom: 1px solid #333; padding: 10px; color: #bbb; background: #1e1e1e; }
    .umi-table tr:last-child td { border-bottom: none; }
    
    /* Callouts */
    .callout { padding: 15px; border-radius: 6px; margin-top: 20px; font-size: 13px; border-left: 4px solid; }
    .callout-info { background: #1c242c; border-color: #61afef; color: #d1d9e6; }
    .callout-warn { background: #2c2222; border-color: #e06c75; color: #e6d1d1; }
    .callout-success { background: #1e2620; border-color: #98c379; color: #d1e6d6; }
    
    /* Wiring Diagram Style */
    .step-list { margin: 0; padding: 0; list-style: none; counter-reset: step; }
    .step-list li { position: relative; padding-left: 30px; margin-bottom: 10px; font-size: 14px; }
    .step-list li::before { 
        counter-increment: step; content: counter(step); 
        position: absolute; left: 0; top: 0; width: 20px; height: 20px; 
        background: #333; color: #fff; border-radius: 50%; 
        text-align: center; line-height: 20px; font-size: 11px; font-weight: bold;
    }

    /* Details/Summary */
    details { background: #21252b; border-radius: 6px; padding: 10px; margin-bottom: 10px; border: 1px solid #333; transition: 0.2s; }
    details[open] { background: #282c34; border-color: #444; }
    summary { cursor: pointer; font-weight: 600; color: #e0e0e0; outline: none; list-style: none; display: flex; justify-content: space-between; align-items: center; }
    summary::after { content: "+"; color: #61afef; font-weight: bold; font-size: 16px; }
    details[open] summary::after { content: "−"; }
    details[open] summary { margin-bottom: 15px; border-bottom: 1px solid #3e4451; padding-bottom: 10px; }
`;

const HELP_HTML = `
    <div class="umi-section">
        <h3>🔌 Setup & Wiring (The "Passthrough")</h3>
        <p>The UmiAI node acts as the "Central Brain". You must pass your <strong>Model</strong> and <strong>CLIP</strong> through it so it can apply LoRAs automatically.</p>

        <div class="umi-grid-2">
            <div class="callout callout-success" style="margin-top: 0;">
                <h4 style="margin-top:0">Step 1: The Main Chain</h4>
                <ul class="step-list">
                    <li>Connect <strong>Checkpoint Loader</strong> (Model & CLIP) &#10142; <strong>UmiAI Node</strong> (Inputs).</li>
                    <li>Connect <strong>UmiAI Node</strong> (Model & CLIP Outputs) &#10142; <strong>KSampler</strong> or <strong>Text Encode</strong> nodes.</li>
                </ul>
                <p style="margin-top:10px; font-size:12px; opacity:0.8"><em>This "Passthrough" connection allows the node to inject LoRAs on the fly.</em></p>
            </div>

            <div class="callout callout-info" style="margin-top: 0;">
                <h4 style="margin-top:0">Step 2: Prompts & Auto-Reload</h4>
                <ul class="step-list">
                    <li>Connect <strong>Text/Negative</strong> outputs to your CLIP Text Encodes.</li>
                    <li><strong>🔥 Auto-Reload:</strong> Files auto-reload when edited! Just save and generate - no manual refresh needed.</li>
                    <li><strong>Manual Refresh:</strong> Use the <strong>"🔄 Refresh"</strong> button in the Wildcards tab to force reload all files.</li>
                </ul>
            </div>
        </div>

         <div class="callout callout-warn">
            <strong>⚠️ Note on Batch Size:</strong><br>
            Use the <strong>"Queue Batch"</strong> setting in the ComfyUI Extra Options menu (checkboxes on the right menu) to generate variations. Do not use the widget batch size on the Latent node, or you will get identical duplicates.
        </div>
    </div>

    <div class="umi-section">
        <h3>⚡ Syntax Cheat Sheet</h3>
        <div class="umi-grid-2">
            <div>
                <h4 style="margin-top:0">🎲 Dynamic Prompts</h4>
                <table class="umi-table">
                    <tr><td><span class="umi-code">{a|b}</span></td><td>Random choice.</td></tr>
                    <tr><td><span class="umi-code">{25%A|75%B}</span></td><td><strong>Weighted:</strong> 25% A, 75% B.</td></tr>
                    <tr><td><span class="umi-code">{a|b} ... {1|2}</span></td><td><strong>Sync:</strong> 2 lists of equal size will always match indices.</td></tr>
                    <tr><td><span class="umi-code">{2$$a|b|c}</span></td><td>Pick 2 unique.</td></tr>
                    <tr><td><span class="umi-code">__*__</span></td><td><strong>Wildcard:</strong> Pick from ANY file.</td></tr>
                    <tr><td><span class="umi-code">&lt;[Tag]&gt;</span></td><td><strong>Tag Aggregation:</strong> Pick from any entry with this tag.</td></tr>
                </table>
            </div>
            <div>
                <h4 style="margin-top:0">🎛️ Tools & Logic</h4>
                <table class="umi-table">
                    <tr><td><span class="umi-code">$var={...}</span></td><td>Define variable.</td></tr>
                    <tr><td><span class="umi-code">[if K : A | B]</span></td><td>Logic Gate.</td></tr>
                    <tr><td><span class="umi-code">[shuffle: a, b]</span></td><td>Randomize order.</td></tr>
                    <tr><td><span class="umi-code">[clean: a, , b]</span></td><td>Fix bad formatting.</td></tr>
                    <tr><td><span class="umi-code">text --neg: bad</span></td><td>Scoped Negative.</td></tr>
                    <tr><td><span class="umi-code">&lt;lora:name:1.0&gt;</span></td><td>Load LoRA (Auto).</td></tr>
                    <tr><td><span class="umi-code">@@width=768...@@</span></td><td>Set Resolution.</td></tr>
                </table>
            </div>
        </div>
    </div>

    <div class="umi-section">
        <h3>✨ Editor Features</h3>
        <p>The prompt editor includes powerful features to help you write and debug prompts faster!</p>

        <div class="umi-grid-2">
            <div>
                <h4 style="margin-top:0">🎨 Syntax Highlighting</h4>
                <p style="font-size:12px">Real-time color coding for all UmiAI syntax elements:</p>
                <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                    <li><span style="color:#98c379">__wildcards__</span> - Green</li>
                    <li><span style="color:#61afef">&lt;[tags]&gt;</span> - Blue</li>
                    <li><span style="color:#e5c07b">{choices}</span> - Yellow</li>
                    <li><span style="color:#ffd43b">__2-4$$range__</span> - Gold</li>
                    <li><span style="color:#c678dd">$variables</span> - Purple</li>
                    <li><span style="color:#ff922b">&lt;lora:name&gt;</span> - Orange</li>
                    <li><span style="color:#56b6c2">[conditionals]</span> - Cyan</li>
                    <li><span style="color:#20c997">[functions]</span> - Teal</li>
                    <li><span style="color:#ff79c6">BREAK</span> - Magenta</li>
                </ul>
            </div>
            <div>
                <h4 style="margin-top:0">🔍 Prompt Linting</h4>
                <p style="font-size:12px">Automatic error detection shows issues at the bottom:</p>
                <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                    <li>Unclosed brackets <code>{</code> <code>[</code> <code>(</code></li>
                    <li>Unclosed wildcards <code>__name</code></li>
                    <li>Missing wildcard files</li>
                    <li>Missing LoRA files</li>
                </ul>
                <p style="font-size:11px; color:#888">Click the lint bar to expand error details</p>
            </div>
        </div>

        <div class="umi-grid-2" style="margin-top:15px">
            <div>
                <h4 style="margin-top:0">🔧 Fix & Clean Tools</h4>
                <p style="font-size:12px">Automate prompt cleanup:</p>
                <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                    <li><strong>Fix:</strong> Repair broken brackets, wildcards, YAML tags</li>
                    <li><strong>Auto-Clean:</strong> Toggle to clean spaces, commas, BREAK formatting</li>
                    <li><strong>Ctrl+Shift+B:</strong> Keyboard shortcut for fix</li>
                </ul>
            </div>
            <div>
                <h4 style="margin-top:0">👁️ Wildcard Preview</h4>
                <p style="font-size:12px">Hover over any <code>__wildcard__</code> to see its contents!</p>
                <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                    <li>Shows first 15 entries</li>
                    <li>Works with .txt, .yaml, .csv</li>
                    <li>Cached for performance</li>
                </ul>
            </div>
        </div>
    </div>

    <div class="umi-section">
        <h3>🔋 LoRA Loading (Internal)</h3>
        <p>The node now patches the Model and CLIP for you. You do not need any external LoRA Loader nodes.</p>

        <div class="umi-block">// Syntax: &lt;lora:Filename:Strength&gt;

// Basic usage (Strength defaults to 1.0)
&lt;lora:pixel_art_v2&gt;

// With Strength (Range: 0.0 to 5.0)
&lt;lora:add_detail:0.5&gt;
&lt;lora:strong_effect:3.5&gt;

// Inside logic or variables!
$style={ &lt;lora:anime:1.0&gt; | &lt;lora:realistic:0.8&gt; }
A photo of a cat, $style</div>

        <div class="callout callout-warn" style="margin-top:15px">
            <strong>⚡ Strength Range:</strong> 0.0 to 5.0 (extended for fringe cases). Out-of-range values are automatically clamped. Invalid formats default to 1.0.
        </div>

        <div class="callout callout-info">
            <h4 style="margin-top:0">🔍 New: LoRA Tag Inspector & Injector</h4>
            <p>Don't know the trigger words for your LoRA? The node can now read the .safetensors metadata.</p>
            <div class="umi-grid-2" style="margin-bottom:0; gap:15px; margin-top:10px;">
                <div style="background: #151515; padding: 10px; border-radius: 6px;">
                    <strong>👁️ See the Tags</strong><br>
                    <span style="font-size:12px; color:#888;">Connect the new <strong>lora_info</strong> output string to a "Show Text" or "Preview Text" node. It will list every loaded LoRA and their top training tags.</span>
                </div>
                <div style="background: #151515; padding: 10px; border-radius: 6px;">
                    <strong>💉 Auto-Inject</strong><br>
                    <span style="font-size:12px; color:#888;">Use the <strong>lora_tags_behavior</strong> widget to automatically <em>Append</em> or <em>Prepend</em> the most common training tags to your prompt.</span>
                </div>
            </div>
        </div>
    </div>
    
    <div class="umi-section">
        <h3>📂 Creating & Using Wildcards</h3>
        <p>You can create your own lists in the <code>wildcards/</code> folder or <code>models/wildcards/</code>.</p>

        <div class="umi-grid-2">
            <div>
                <h4>1. Simple Text Lists (.txt)</h4>
                <p>Create a file named <code>colors.txt</code>:</p>
                <div class="umi-block">Red
Blue
Green</div>
                <p><strong>Usage:</strong></p>
                <div class="umi-block">A __colors__ dress.</div>
            </div>

            <div>
                <h4>2. YAML Files (Tag-Based Selection)</h4>
                <div class="umi-block">FireKnight:
  Prompts: ["knight in flame armor"]
  Tags: [Fire, Warrior, Heavy]

IceMage:
  Prompts: ["ice wizard"]
  Tags: [Ice, Mage, Light]</div>
                <p style="font-size:12px"><strong>Tag-based:</strong> <code>&lt;[Fire]&gt;</code> (any entry with 'Fire' tag)</p>
                <p style="font-size:12px"><strong>Specific entry:</strong> <code>&lt;FireKnight&gt;</code> or <code>&lt;filename:FireKnight&gt;</code></p>
                <p style="font-size:12px"><strong>Logic:</strong> <code>&lt;[Fire AND Warrior]&gt;</code>, <code>&lt;[Ice OR Fire]&gt;</code>, <code>&lt;[NOT Heavy]&gt;</code></p>
            </div>
        </div>

        <details style="margin-top:20px">
            <summary style="cursor:pointer; font-weight:600; font-size:14px; color:#61afef">🧠 Boolean Logic Engine (YAML Tags)</summary>
            <p style="margin-top:10px">Use boolean logic to select YAML entries based on complex tag combinations!</p>

            <table class="umi-table" style="margin-top:10px">
                <tr><th>Operator</th><th>Syntax</th><th>Meaning</th></tr>
                <tr><td><strong>AND</strong></td><td><code>&&</code> or <code>AND</code></td><td>Both conditions must be true</td></tr>
                <tr><td><strong>OR</strong></td><td><code>||</code> or <code>OR</code></td><td>Either condition must be true</td></tr>
                <tr><td><strong>XOR</strong></td><td><code>^</code> or <code>XOR</code></td><td>Exactly one condition must be true</td></tr>
                <tr><td><strong>NOT</strong></td><td><code>!</code> or <code>NOT</code></td><td>Inverts the condition</td></tr>
                <tr><td><strong>NAND</strong></td><td><code>NAND</code></td><td>NOT (both conditions true)</td></tr>
                <tr><td><strong>NOR</strong></td><td><code>NOR</code></td><td>NOT (either condition true)</td></tr>
                <tr><td><strong>Grouping</strong></td><td><code>( )</code></td><td>Control precedence</td></tr>
            </table>

            <div style="margin-top:15px">
                <h4 style="margin:10px 0 5px 0; font-size:13px">Examples:</h4>
                <div class="umi-block" style="font-size:12px">// YAML File
FireKnight:
  Prompts: ["knight in flame armor"]
  Tags: [Fire, Warrior, Heavy]

IceMage:
  Prompts: ["ice wizard"]
  Tags: [Ice, Mage, Light]

// Logic Expressions
&lt;[Fire AND Warrior]&gt;          → FireKnight
&lt;[Ice OR Fire]&gt;               → Either one
&lt;[(Fire OR Ice) AND Mage]&gt;    → IceMage only
&lt;[NOT Heavy]&gt;                 → IceMage only
&lt;[Fire XOR Heavy]&gt;            → Nothing (both are true)</div>
            </div>

            <div class="callout callout-info" style="margin-top:10px">
                <strong>💡 Precedence:</strong> NOT (highest) → AND → OR/XOR/NAND/NOR (lowest). Use parentheses for clarity!
            </div>

            <div style="margin-top:15px; border-top:1px solid #444; padding-top:10px">
                <h4 style="margin:10px 0 5px 0; font-size:13px">🆕 Logic with .txt Wildcards</h4>
                <p style="font-size:12px">You can add tags to .txt file entries and filter them with logic!</p>
                <div class="umi-block" style="font-size:12px">// colors.txt with tags
Red::Fire,Warm,Bright
Blue::Ice,Cool,Calm
Green::Nature,Earth

// Usage with logic filter
__colors[Fire OR Ice]__       → Red or Blue only
__colors[NOT Warm]__          → Blue or Green
__colors[Bright AND Fire]__   → Red only</div>

                <p style="font-size:12px; margin-top:10px"><strong>Syntax formats:</strong></p>
                <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                    <li><code>text::tag1,tag2</code> - Entry with tags</li>
                    <li><code>__file[logic]__</code> - Filter by logic expression</li>
                </ul>
            </div>

            <div style="margin-top:15px; border-top:1px solid #444; padding-top:10px">
                <h4 style="margin:10px 0 5px 0; font-size:13px">🔀 Variable Comparisons</h4>
                <p style="font-size:12px">Logic expressions now support variable comparisons!</p>
                <div class="umi-block" style="font-size:12px">// globals.yaml
$theme: cyberpunk
$mood: dark

// YAML with conditional logic
CyberKnight:
  Prompts: ["neon knight"]
  Tags: [Cyberpunk, Dark]

// Usage
&lt;[$theme==cyberpunk AND Dark]&gt;  → CyberKnight
&lt;[$mood==happy OR Light]&gt;       → Won't match CyberKnight</div>

                <p style="font-size:12px; margin-top:10px"><strong>Comparison operators:</strong></p>
                <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                    <li><code>$var==value</code> - Check if variable equals value</li>
                    <li><code>$var</code> - Check if variable is truthy</li>
                    <li>Works with all boolean operators (AND, OR, NOT, etc.)</li>
                </ul>
            </div>
        </details>
    </div>

    <div class="umi-section">
        <h3>🎲 Advanced Features</h3>

        <details>
            <summary>⚖️ Weighted Wildcards (NEW)</summary>
            <p>Control selection probability by adding weights to entries. Higher weights = more likely to appear.</p>
            <div class="umi-block">// colors.txt with weights
vibrant red:10
deep blue:5
soft pink:1</div>
            <p>Result: "vibrant red" is 10x more likely than "soft pink"</p>
            <table class="umi-table" style="margin-top:15px">
                <tr><th>Syntax</th><th>Meaning</th></tr>
                <tr><td><code>text:5</code></td><td>Weight of 5 (5x more likely than weight 1)</td></tr>
                <tr><td><code>text:0.5</code></td><td>Half probability (decimals supported)</td></tr>
                <tr><td><code>text</code></td><td>Default weight = 1.0</td></tr>
            </table>
            <div class="callout callout-info" style="margin-top:10px">
                <strong>💡 Tip:</strong> Weights are parsed from the last colon. Text like "time: 3pm:2.0" works correctly (value="time: 3pm", weight=2.0).
            </div>
        </details>

        <details>
            <summary>🔗 Nested Variable Resolution (NEW)</summary>
            <p>Variables can now reference other variables for cascading theme systems!</p>
            <div class="umi-block">// globals.yaml
$theme: cyberpunk
$theme_color: neon $theme
$theme_outfit: futuristic $theme attire

// Prompt
A portrait with $theme_outfit
// Output: A portrait with futuristic cyberpunk attire</div>
            <div class="callout callout-success" style="margin-top:10px">
                <strong>✨ Cascading Updates:</strong> Change <code>$theme</code> to "steampunk" and all dependent variables update automatically!
            </div>
            <p style="margin-top:10px; font-size:13px"><strong>Features:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>Up to 10 levels of nesting</li>
                <li>Infinite loop protection</li>
                <li>Works with variable methods in Full version (.upper, .clean, etc.)</li>
            </ul>
        </details>

        <details>
            <summary>🛡️ Escape Mechanism (NEW)</summary>
            <p>Need to write literal wildcard syntax? Use backslash escaping!</p>
            <table class="umi-table">
                <tr><th>Input</th><th>Output</th></tr>
                <tr><td><code>\__colors__</code></td><td><code>__colors__</code> (not processed)</td></tr>
                <tr><td><code>\{red|blue}</code></td><td><code>{red|blue}</code> (not processed)</td></tr>
                <tr><td><code>\&lt;lora:model:1&gt;</code></td><td><code>&lt;lora:model:1&gt;</code> (not processed)</td></tr>
            </table>
            <p style="margin-top:10px; font-size:13px"><strong>Use Cases:</strong> Documentation, tutorials, or showing syntax examples in prompts.</p>
        </details>

        <details>
            <summary>🚨 Improved Error Messages (NEW)</summary>
            <p>Clear, actionable feedback when things go wrong!</p>
            <table class="umi-table">
                <tr><th>Error Type</th><th>Meaning</th></tr>
                <tr><td><code>[WILDCARD_NOT_FOUND: filename]</code></td><td>File doesn't exist or is empty</td></tr>
                <tr><td><code>[NO_MATCHES: expression]</code></td><td>No YAML entries matched the logic</td></tr>
                <tr><td><code>[GLOB_NO_MATCHES: pattern]</code></td><td>Glob pattern found nothing</td></tr>
            </table>
            <p style="margin-top:10px; font-size:13px">Console warnings guide you to fix issues with clear error messages.</p>
        </details>

        <details>
            <summary>♻️ Auto-Reload & Deduplication (NEW)</summary>
            <div class="umi-grid-2" style="margin-bottom:0">
                <div>
                    <h4 style="margin-top:0">📝 File Auto-Reload</h4>
                    <p style="font-size:13px">Wildcard files now reload automatically when modified! Edit your files and generate - changes appear immediately.</p>
                </div>
                <div>
                    <h4 style="margin-top:0">🧹 Negative Deduplication</h4>
                    <p style="font-size:13px">Negative prompts automatically remove duplicates (case-insensitive) while preserving order. "blurry, BLURRY" becomes just "blurry".</p>
                </div>
            </div>
        </details>
    </div>

    <div class="umi-section">
        <h3>👤 Character Consistency System</h3>
        <p>Maintain consistent characters across generations with YAML profiles!</p>

        <div class="umi-grid-2">
            <div>
                <h4 style="margin-top:0">Character Syntax</h4>
                <table class="umi-table">
                    <tr><td><span class="umi-code">@@name@@</span></td><td>Character only</td></tr>
                    <tr><td><span class="umi-code">@@name:outfit@@</span></td><td>With outfit</td></tr>
                    <tr><td><span class="umi-code">@@name:outfit:emotion@@</span></td><td>Full syntax</td></tr>
                </table>
            </div>
            <div>
                <h4 style="margin-top:0">Character Nodes</h4>
                <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                    <li><strong>Character Manager</strong> - Single character builder</li>
                    <li><strong>Character Batch</strong> - Generate all variations</li>
                    <li><strong>Sprite Export</strong> - Organized image output</li>
                    <li><strong>Character Info</strong> - Debug profiles</li>
                </ul>
            </div>
        </div>

        <div class="callout callout-info" style="margin-top:10px">
            <strong>💡 Create profiles in:</strong> <code>characters/name/profile.yaml</code>
        </div>
    </div>

    <div class="umi-section">
        <h3>🎬 Power Features</h3>

        <details>
            <summary>📷 Camera Control</summary>
            <p>Generate camera angle prompts for multi-angle LoRAs!</p>
            <div class="umi-grid-2">
                <div>
                    <h4 style="margin-top:0">Camera Control Node</h4>
                    <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                        <li>Azimuth: 0-360° (snaps to 45°)</li>
                        <li>Elevation: -30° to 60°</li>
                        <li>Distance: close-up, medium, wide</li>
                        <li>Configurable trigger word</li>
                    </ul>
                </div>
                <div>
                    <h4 style="margin-top:0">Visual Camera Control</h4>
                    <p style="font-size:12px">Interactive canvas widget - drag to set camera angle!</p>
                </div>
            </div>
        </details>

        <details>
            <summary>🎭 Pose Library & Expression Mixer</summary>
            <p>Pre-built poses and emotion blending!</p>
            <div class="umi-grid-2">
                <div>
                    <h4 style="margin-top:0">Pose Library</h4>
                    <p style="font-size:12px">30+ poses: standing, sitting, action, expressive, lying, kneeling</p>
                    <p style="font-size:12px">Edit <code>presets/poses.yaml</code> to add custom poses!</p>
                </div>
                <div>
                    <h4 style="margin-top:0">Expression Mixer</h4>
                    <p style="font-size:12px">40+ emotions with weighted blending</p>
                    <p style="font-size:12px">Example: happy:60% + excited:40%</p>
                </div>
            </div>
        </details>

        <details>
            <summary>🎨 Scene Composer</summary>
            <p>Combine backgrounds, lighting, and atmosphere presets!</p>
            <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                <li>50+ backgrounds (studio, outdoor, indoor, fantasy, sci-fi)</li>
                <li>11 lighting styles (natural, dramatic, neon, cinematic)</li>
                <li>10 atmosphere presets (cheerful, mysterious, romantic)</li>
            </ul>
            <p style="font-size:12px">Edit <code>presets/scenes.yaml</code> to add custom scenes!</p>
        </details>

        <details>
            <summary>📊 LoRA Dataset Export</summary>
            <p>Generate training data for LoRA fine-tuning!</p>
            <ul style="margin:5px 0; padding-left:20px; font-size:12px">
                <li><strong>Kohya-compatible</strong> folder structure</li>
                <li>Auto-generated captions</li>
                <li>Flip augmentation support</li>
                <li>Caption nodes for processing external captioner output</li>
            </ul>
        </details>
    </div>

    <div class="umi-section">
        <h3>📦 Bundled Wildcards</h3>
        <p>Ready-to-use wildcards in the <code>wildcards/</code> folder:</p>
        <table class="umi-table">
            <tr><td><span class="umi-code">__poses__</span></td><td>40+ character poses</td></tr>
            <tr><td><span class="umi-code">__emotions__</span></td><td>45+ facial expressions</td></tr>
            <tr><td><span class="umi-code">__backgrounds__</span></td><td>40+ environments</td></tr>
            <tr><td><span class="umi-code">__lighting__</span></td><td>30+ lighting setups</td></tr>
        </table>
    </div>

    <div class="umi-section">
        <h3>🎨 Browser & Tools</h3>

        <details>
            <summary>📦 LoRA Browser (Ctrl+L)</summary>
            <p>Visual browser for all your LoRAs with CivitAI integration!</p>

            <div class="umi-block">Press Ctrl+L to open the LoRA Browser

Features:
• Grid view with preview images
• Search by name or tags
• Adjustable strength slider (0-5)
• One-click insert into Umi node
• Right-click or Edit button to customize

Click any LoRA card to insert:
&lt;lora:model_name:strength&gt; + activation tags</div>

            <p style="margin-top:10px; font-size:13px"><strong>CivitAI Integration (v1.5):</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li><strong>Batch Fetch:</strong> "Fetch All" with progress bar</li>
                <li><strong>Per-Card Fetch:</strong> 🌐 button on each LoRA card</li>
                <li>Exact match only (hash or name)</li>
                <li>Shows preview images, trigger words, base model</li>
                <li>Purple border = has CivitAI data</li>
            </ul>
        </details>

        <details>
            <summary>🖼️ Image Browser (Ctrl+I)</summary>
            <p>Booru-style gallery for browsing generated images with metadata extraction!</p>

            <div class="umi-block">Press Ctrl+I to open Image Browser

Features:
• Full-screen grid gallery
• Sort by newest/oldest/name
• Pagination (50 per page)
• Search prompts
• Click image to copy prompt to Umi node
• Extracts metadata from PNG/JPG/WebP

Metadata Support:
✓ ComfyUI workflow JSON
✓ A1111 parameters
✓ Custom Umi tags
✓ EXIF data</div>

            <p style="margin-top:10px; font-size:13px"><strong>Quick Actions:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>Click image → Copy prompt + negative to active node</li>
                <li>Search bar → Filter by prompt content</li>
                <li>ESC or click outside → Close browser</li>
            </ul>
        </details>

        <details>
            <summary>📝 Sequential Wildcards (__~file__)</summary>
            <p>Deterministic selection based on seed - same seed, same result!</p>

            <div class="umi-block">// characters.txt
Alice
Bob
Charlie
Dave

// Usage
__~characters__

Seed 0 → Alice
Seed 1 → Bob
Seed 2 → Charlie
Seed 3 → Dave
Seed 4 → Alice (cycles)

Same seed always picks same entry!</div>

            <div class="callout callout-info" style="margin-top:10px">
                <strong>💡 Use Case:</strong> Perfect for creating consistent character series or batch generations with predictable variation.
            </div>
        </details>

        <details>
            <summary>📄 Prompt File Loader (__@file__)</summary>
            <p>Load entire .txt file content as a prompt - perfect for mega-prompts!</p>

            <div class="umi-block">// mega_prompt.txt
masterpiece, best quality, highly detailed,
professional photography, studio lighting,
bokeh, depth of field, sharp focus,
vibrant colors, perfect composition,
award winning, trending on artstation

// Usage
__@mega_prompt__, portrait of a woman

Result: Full file content + your addition
No parsing - raw content loaded</div>

            <p style="margin-top:10px; font-size:13px"><strong>Benefits:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>Manage complex prompts in separate files</li>
                <li>Reuse quality tag collections</li>
                <li>Better organization and readability</li>
                <li>Easy to edit and maintain</li>
            </ul>
        </details>

        <details>
            <summary>🏷️ LoRA Tag Control</summary>
            <p>Fine-tune how many tags are automatically added from LoRAs!</p>

            <div class="umi-block">Node Parameter: lora_max_tags
Default: 5 tags
Range: 0-20 tags

0 = No automatic tags
5 = Balanced (default)
20 = All available tags

Tags come from:
1. CivitAI trigger words (if available)
2. SafeTensors metadata (fallback)</div>

            <div class="callout callout-success" style="margin-top:10px">
                <strong>✨ Smart Selection:</strong> Most relevant tags are picked first (usually trigger words or character-specific tags).
            </div>
        </details>
    </div>

    <div class="umi-section">
        <h3>🔧 Workflow & Productivity</h3>

        <details>
            <summary>💾 Preset Manager (Ctrl+P)</summary>
            <p>Save and load complete node configurations instantly!</p>

            <div class="umi-block">Press Ctrl+P to open Preset Manager

Save a preset:
1. Configure your Umi node perfectly
2. Ctrl+P → "Save Current Node as Preset"
3. Enter name: "Anime Portrait"
4. Enter description (optional)

Load a preset:
1. Ctrl+P
2. Click any preset card
3. All settings restored instantly!

Saves everything:
• Prompts (positive & negative)
• Seed, dimensions
• LoRA settings
• LLM/Vision settings
• All other parameters</div>

            <p style="margin-top:10px; font-size:13px"><strong>Use Cases:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>"Anime Style" - Quick switch to anime workflow</li>
                <li>"Realistic Portrait" - Professional photo settings</li>
                <li>"Landscape" - Wide format with specific LoRAs</li>
                <li>"Character Batch" - Consistent settings for series</li>
            </ul>
        </details>

        <details>
            <summary>📜 Prompt History (Ctrl+H)</summary>
            <p>Never lose a successful prompt again - automatic tracking with search!</p>

            <div class="umi-block">Press Ctrl+H to open History Browser

Features:
• Auto-logs every prompt (both Full & Lite nodes)
• Search across all prompts
• Pagination (20 per page)
• One-click restore to active node
• Export entire history to JSON
• Clear all with confirmation

Tracked data:
✓ Positive prompt
✓ Negative prompt
✓ Seed value
✓ Timestamp

Storage: Last 500 entries (auto-pruned)</div>

            <p style="margin-top:10px; font-size:13px"><strong>Workflow:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>Generate images (history logs automatically)</li>
                <li>Find that perfect prompt from yesterday</li>
                <li>Search keywords → Click → Restored!</li>
                <li>Export for documentation or backup</li>
            </ul>
        </details>

        <details>
            <summary>⌨️ Keyboard Shortcuts (Ctrl+?)</summary>
            <p>Quick reference for all shortcuts and syntax - your built-in cheat sheet!</p>

            <div class="umi-block">Press Ctrl+? or Ctrl+/ to view shortcuts

Browser Panels:
Ctrl+L → LoRA Browser
Ctrl+I → Image Browser
Ctrl+P → Preset Manager
Ctrl+H → Prompt History
Ctrl+Y → YAML Tag Manager
Ctrl+E → File Editor
Ctrl+? → This shortcuts panel

Panel Actions:
ESC → Close any panel
Click outside → Close panel

Also shows:
• Wildcard syntax reference
• Logic operators guide
• Variable methods
• All available shortcuts</div>

            <div class="callout callout-info" style="margin-top:10px">
                <strong>💡 Tip:</strong> Press Ctrl+? anytime while working to refresh your memory on syntax!
            </div>
        </details>

        <details>
            <summary>🎨 Theme Toggle</summary>
            <p>Switch between dark and light themes for comfortable viewing in any environment!</p>

            <div class="umi-block">Click theme button in menu bar:
🌙 Dark or ☀️ Light

Features:
• Instant switching
• Persists across sessions
• Applies to ALL Umi panels:
  - LoRA Browser
  - Image Browser
  - Preset Manager
  - History Browser
  - Shortcuts Panel
  - YAML Manager
  - File Editor

Dark Theme (default):
• Background: #1e1e1e
• Blue accents: #61afef
• Easy on eyes at night

Light Theme:
• Background: #ffffff
• Blue accents: #4078c0
• Better for bright rooms</div>
        </details>

        <details>
            <summary>🏷️ YAML Tag Manager (Ctrl+Y)</summary>
            <p>Analyze, export, and manage your YAML tags with statistics dashboard!</p>

            <div class="umi-block">Press Ctrl+Y to open YAML Tag Manager

Statistics Dashboard:
📝 Total Entries
🏷️ Unique Tags
✓ Entries With Tags
✗ Entries Without Tags
📊 Average Tags/Entry
🔥 Top 20 Most-Used Tags

Export Options:
📥 Export to JSON - Complete data with all entries
📊 Export to CSV - Simple format for spreadsheets

Perfect for:
• Documentation
• Tag analysis
• Finding unused tags
• Sharing tag schemas
• Batch editing preparation</div>

            <p style="margin-top:10px; font-size:13px"><strong>Top Tags View:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>Visual bars showing usage percentage</li>
                <li>Count and percentage for each tag</li>
                <li>Understand your most common themes</li>
                <li>Identify organization opportunities</li>
            </ul>
        </details>

        <details>
            <summary>📝 File Editor (Ctrl+E)</summary>
            <p>Edit wildcards and YAML files directly in ComfyUI - no more alt-tabbing!</p>

            <div class="umi-block">Press Ctrl+E to open File Editor

Features:
• Two-pane layout (sidebar + editor)
• Browse all .txt and .yaml files
• Monospace font for readability
• Syntax-friendly editing
• Create new files
• Auto-save indicator
• Line/word/character counts
• Ctrl+S to save

Workflow:
1. Ctrl+E → Open editor
2. Click file in sidebar
3. Edit content
4. Ctrl+S → Save
5. Changes active immediately!

Security:
✓ Only edits files in wildcard paths
✓ No access outside safe directories
✓ Confirmation on unsaved changes</div>

            <p style="margin-top:10px; font-size:13px"><strong>Perfect For:</strong></p>
            <ul style="margin:5px 0; padding-left:20px; font-size:13px">
                <li>Quick typo fixes</li>
                <li>Adding new wildcard entries</li>
                <li>Updating YAML tags</li>
                <li>Creating new wildcard files</li>
                <li>Iterative prompt development</li>
            </ul>
        </details>

        <details>
            <summary>🔄 Simplified YAML Format</summary>
            <p>Unified, tag-based YAML system - one format, no confusion!</p>

            <div class="umi-block">Standard YAML Format:
EntryName:
  Prompts: ["prompt text"]
  Tags: [Tag1, Tag2, Tag3]
  Prefix: ["prefix"]
  Suffix: ["suffix"]

All keys optional except entry name!

Tag Selection:
&lt;[tag]&gt;              → Any entry with tag
&lt;[tag1][tag2]&gt;       → AND (both tags)
&lt;[tag1|tag2]&gt;        → OR (either tag)
&lt;[--tag]&gt;            → NOT (exclude tag)
&lt;file:[tag]&gt;         → Specific file

Full Logic Support:
&lt;[Fire AND Warrior]&gt;              → Both required
&lt;[Ice OR Fire]&gt;                   → Either one
&lt;[(Fire OR Ice) AND Mage]&gt;        → Complex logic
&lt;[NOT Heavy]&gt;                     → Exclusion
&lt;[$theme==cyberpunk AND Dark]&gt;   → Variable comparison</div>

            <div class="callout callout-success" style="margin-top:10px">
                <strong>✨ Simplified:</strong> No more "Umi YAML" vs "Alternative YAML" - just one clean format!
            </div>
        </details>
    </div>

    <div class="umi-section">
        <h3>📋 Quick Reference</h3>

        <details open>
            <summary>⌨️ All Keyboard Shortcuts</summary>
            <table class="umi-table">
                <tr><th>Shortcut</th><th>Action</th></tr>
                <tr><td><code>Ctrl+L</code></td><td>Open LoRA Browser</td></tr>
                <tr><td><code>Ctrl+I</code></td><td>Open Image Browser</td></tr>
                <tr><td><code>Ctrl+P</code></td><td>Open Preset Manager</td></tr>
                <tr><td><code>Ctrl+H</code></td><td>Open Prompt History</td></tr>
                <tr><td><code>Ctrl+Y</code></td><td>Open YAML Tag Manager</td></tr>
                <tr><td><code>Ctrl+E</code></td><td>Open File Editor</td></tr>
                <tr><td><code>Ctrl+?</code> or <code>Ctrl+/</code></td><td>Show Shortcuts Panel</td></tr>
                <tr><td><code>Ctrl+S</code></td><td>Save File (in editor)</td></tr>
                <tr><td><code>ESC</code></td><td>Close Active Panel</td></tr>
            </table>
        </details>

        <details>
            <summary>🎯 Common Workflows</summary>

            <div style="margin-bottom:15px">
                <h4 style="margin:10px 0 5px 0; font-size:13px">Style Switching:</h4>
                <div class="umi-block" style="font-size:12px">1. Configure node for "Anime" style
2. Ctrl+P → Save as "Anime Style"
3. Configure for "Realistic" style
4. Ctrl+P → Save as "Realistic"
5. Switch anytime: Ctrl+P → Click preset!</div>
            </div>

            <div style="margin-bottom:15px">
                <h4 style="margin:10px 0 5px 0; font-size:13px">Prompt Recovery:</h4>
                <div class="umi-block" style="font-size:12px">1. "I had a great prompt yesterday..."
2. Ctrl+H → Open history
3. Search keywords
4. Click to restore
5. Generate again!</div>
            </div>

            <div style="margin-bottom:15px">
                <h4 style="margin:10px 0 5px 0; font-size:13px">Wildcard Editing:</h4>
                <div class="umi-block" style="font-size:12px">1. Ctrl+E → Open editor
2. Click file in sidebar
3. Edit content
4. Ctrl+S → Save
5. Use immediately in prompts!</div>
            </div>

            <div>
                <h4 style="margin:10px 0 5px 0; font-size:13px">LoRA Discovery:</h4>
                <div class="umi-block" style="font-size:12px">1. Ctrl+L → Open LoRA browser
2. Click "Fetch from CivitAI"
3. Browse with preview images
4. Click LoRA → Auto-insert with tags!</div>
            </div>
        </details>
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
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

    modal.innerHTML = `
        <div class="umi-help-content">
            <div class="umi-help-header">
                <div>
                    <h2>📘 UmiAI Reference Manual <span class="version">v1.5</span></h2>
                </div>
                <button class="umi-help-close" onclick="this.closest('.umi-help-modal').remove()">CLOSE</button>
            </div>
            <div class="umi-help-body">
                ${HELP_HTML}
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

// =============================================================================
// PART 3: REGISTRATION & DYNAMIC VISIBILITY
// =============================================================================

// Helper: Custom fuzzy search function for client-side filtering
function getFuzzyMatches(query, allItems) {
    // FIX: If query is empty, return everything!
    if (!query || query.trim() === "") {
        return allItems.sort();
    }

    // Normalize query
    const lowerQuery = query.toLowerCase();

    // Score items
    const scored = allItems.map(item => {
        const lowerItem = item.toLowerCase();

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

app.registerExtension({
    name: "UmiAI.WildcardSystem",
    async setup() {
        this.wildcards = [];
        this.loras = [];
        this.globals = {};  // { $varname: "value" }

        // Define a function we can call later to refresh the lists
        this.fetchWildcards = async () => {
            try {
                // Fetch from the correct endpoint (matches your new Python)
                const resp = await fetch("/umiapp/wildcards");
                if (resp.ok) {
                    const data = await resp.json();

                    if (Array.isArray(data)) {
                        this.wildcards = data;
                        this.loras = [];
                        this.yamlTags = [];
                        this.basenames = {};
                    } else {
                        // New structure: separate txt wildcards from yaml tags
                        this.wildcards = data.wildcards || data.files || [];
                        this.loras = data.loras || [];
                        this.yamlTags = data.tags || [];           // Tags from YAML for <[
                        this.basenames = data.basenames || {};     // Basename -> full path

                        // Add basenames to wildcards list for easy lookup
                        // This allows typing just the filename without folder
                        const basenameList = Object.keys(this.basenames);
                        console.log(`[UmiAI] Loaded ${this.wildcards.length} txt files, ${this.yamlTags.length} yaml tags, ${basenameList.length} basenames`);
                    }
                } else {
                    this.wildcards = [];
                    this.loras = [];
                    this.yamlTags = [];
                    this.basenames = {};
                }
            } catch (e) {
                console.error("[UmiAI] Failed to load wildcards:", e);
                this.wildcards = [];
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

        // Initial fetch
        await this.fetchWildcards();
        await this.fetchGlobals();
        this.popup = new AutoCompletePopup();
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Support BOTH Full and Lite nodes
        if (nodeData.name !== "UmiAIWildcardNode" && nodeData.name !== "UmiAIWildcardNodeLite") return;

        // 1. Add Help Menu
        const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (_, options) {
            if (getExtraMenuOptions) getExtraMenuOptions.apply(this, arguments);
            options.push(null);
            options.push({
                content: "📘 Open UmiAI User Guide",
                callback: () => { showHelpModal(); }
            });
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);
            const self = this;

            // ============================================================
            // DYNAMIC WIDGET VISIBILITY LOGIC
            // ============================================================
            const llmWidgets = ["llm_model", "llm_temperature", "llm_max_tokens", "custom_system_prompt"];
            const triggerName = "llm_prompt_enhancer";

            const triggerWidget = this.widgets.find(w => w.name === triggerName);

            if (triggerWidget) {
                this.widgets.forEach(w => {
                    if (llmWidgets.includes(w.name)) {
                        w.origType = w.type;
                        w.origComputeSize = w.origComputeSize;
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
            if (!textWidget || !textWidget.inputEl) return;

            const inputEl = textWidget.inputEl;
            const ext = app.extensions.find(e => e.name === "UmiAI.WildcardSystem");

            // 1. INTERCEPT NAVIGATION (Arrow Keys, Enter, Tab)
            inputEl.addEventListener("keydown", (e) => {
                if (ext.popup.visible) {
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
                        ext.popup.hide();
                        return;
                    }
                }
            });

            // 2. LISTEN FOR TYPING (To show the popup)
            inputEl.addEventListener("keyup", (e) => {
                // Ignore nav keys in this listener to prevent flashing
                if (["ArrowUp", "ArrowDown", "Enter", "Escape"].includes(e.key)) return;

                const cursor = inputEl.selectionStart;
                const text = inputEl.value;
                const beforeCursor = text.substring(0, cursor);

                // Regex for __ (wildcards - txt files)
                const matchWildcard = beforeCursor.match(/__([a-zA-Z0-9_\/\-]*)$/);
                // Regex for <[ (tags from yaml files)
                const matchTag = beforeCursor.match(/<\[([a-zA-Z0-9_\/\-\s]*)$/);
                const matchLora = beforeCursor.match(/<lora:([^>]*)$/);

                if (!ext) return;

                let options = [];
                let triggerType = "";
                let matchIndex = 0;
                let query = "";
                let opener = "";

                // -- Wildcard Logic (__ = txt files only) --
                if (matchWildcard) {
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
                }

                if (triggerType && options.length > 0) {
                    const rect = inputEl.getBoundingClientRect();
                    const topOffset = rect.top + 20 + (rect.height / 2); // Approximate pos

                    ext.popup.show(rect.left + 20, topOffset, options, (selected) => {
                        let completion = "";

                        // Smart Completion based on trigger type
                        if (triggerType === "wildcard") {
                            // Resolve basename to full path if needed
                            const resolvedPath = ext.basenames?.[selected] || selected;
                            completion = `__${resolvedPath}__`;
                        }
                        else if (triggerType === "tag") {
                            completion = `<[${selected}]>`;
                        }
                        else if (triggerType === "lora") {
                            completion = `<lora:${selected}:1.0>`;
                        }
                        else if (triggerType === "variable") {
                            completion = `$${selected}`;
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
                    });
                } else {
                    ext.popup.hide();
                }
            });

            // Close on outside click
            document.addEventListener("mousedown", (e) => {
                if (ext && ext.popup && e.target !== ext.popup.element && !ext.popup.element.contains(e.target) && e.target !== inputEl) {
                    ext.popup.hide();
                }
            });
        };
    }
});
