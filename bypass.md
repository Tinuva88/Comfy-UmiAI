# Umi Text Bypass

## Goal
Create a small ComfyUI node that:
1) Receives a boolean signal from the `UmiAI Wildcard Processor`
2) Sits inline between any data stream (e.g., IMAGE)
3) Automatically bypasses downstream nodes based on the boolean signal

Example: If the wildcard processor's text contains `simple background`, it outputs `bypass_matched=True`. The bypass node receives this and allows downstream nodes to run. Otherwise, they're skipped.

**How it works:**
- UmiAI Wildcard Processor has a `bypass_phrase` input (optional)
- It checks if the generated prompt contains that phrase
- Outputs a `bypass_matched` boolean
- UmiTextBypass receives this boolean as input
- During execution, a custom hook skips nodes connected to UmiTextBypass when `matched=False`
- This happens dynamically DURING the same execution run!

## What Was Added
### Wildcard Processor Enhancement
- Added `bypass_phrase` optional input (STRING)
- Added `bypass_matched` output (BOOLEAN)
- Checks if generated prompt contains the bypass_phrase
- Outputs True if phrase found, False otherwise

### Backend node
- **Node class:** `UmiTextBypass` in `nodes_lite.py`
- **Inputs:**
  - `matched` (BOOLEAN, forceInput) - connects to wildcard processor's `bypass_matched`
  - `passthrough_type` (dropdown): IMAGE, LATENT, CONDITIONING, MODEL, CLIP, STRING
  - Optional inputs for each type (image, latent, conditioning, model, clip, string)
- **Outputs:**
  - One output for each type (image, latent, conditioning, model, clip, string)
- The node:
  1. Receives the `matched` boolean from wildcard processor
  2. Passes through the selected data type
  3. Execution hook checks the `matched` value
  4. If `matched=False`, skips all nodes connected to this bypass node's outputs

### Node registration
- `__init__.py` registers:
  - `UmiTextBypass` (display: "Umi Text Bypass")

### Frontend extension (JS)
- **File:** `js/umi_text_bypass.js`
- Purpose: Toggle bypass on the **first connected output node** every run based on `matched`.
- Current approach: Hook into ComfyUI frontend events and attempt to read the node output cache.

## Current State
**Working with 1-run lag** - Automatic bypass works, but applies to the next run:

1. **Wildcard Processor (nodes_lite.py):**
   - User sets `bypass_phrase` (e.g., "simple background")
   - Generates prompt and checks if it contains the phrase
   - Outputs `bypass_matched=True` if found, `False` otherwise
   - ✅ **Works perfectly!**

2. **UmiTextBypass Node (nodes_lite.py):**
   - Receives `matched` boolean from wildcard processor
   - Passes through image/latent/etc data normally
   - Sends WebSocket signal to frontend with matched value
   - ✅ **Works!**

3. **Frontend (umi_text_bypass.js):**
   - Receives signal from backend
   - Toggles bypass mode on connected downstream nodes
   - ⚠️ **Works with 1-run lag** - mode change affects NEXT execution, not current
   - This is a ComfyUI limitation: execution plan is locked before nodes run

## How to Use
1. Add UmiAI Wildcard Processor to your workflow
2. In wildcard processor, set `bypass_phrase` (e.g., "simple background")
3. Add UmiTextBypass node
4. Connect wildcard's `bypass_matched` → bypass node's `matched` input
5. Connect passthrough data (VAE Decode → UmiTextBypass → Remove Background)
6. **First run**: Establishes the bypass state based on the prompt
7. **Subsequent runs**: Bypass automatically toggles based on previous run's match

**Behavior:**
- Run with "simple background" → Next run will have Remove Background ACTIVE
- Run without "simple background" → Next run will have Remove Background BYPASSED
- Works great for batch workflows where you're generating similar prompts

## Usage Example
Typical workflow setup:
```
[UmiAI Wildcard Processor]
  - bypass_phrase: "simple background"
  ↓ model
  ↓ clip
  ↓ text → (continues to other nodes)
  ↓ bypass_matched
  ↓
  |
  |  [VAE Decode]
  |    ↓ image
  |    ↓
  └─→[Umi Text Bypass]
       - matched: (connected from wildcard)
       - passthrough_type: IMAGE
       ↓ image
       ↓
     [Remove Background]
```

**Result:**
- Run 1: Generates "a girl with simple background" → `bypass_matched=True` → Sets Remove Background to ACTIVE for next run
- Run 2: Remove Background runs (because Run 1 set it active)
- Run 3: Generates "a girl in detailed city" → `bypass_matched=False` → Sets Remove Background to BYPASS for next run
- Run 4: Remove Background skipped (because Run 3 set it bypassed)

**The 1-run lag is unavoidable** due to ComfyUI's execution architecture. The execution plan is determined before any nodes run, so mid-execution changes only affect the next queue item.

**Best use cases:**
- Batch generation where consecutive images have similar prompts
- Workflows where you queue multiple variations
- Testing different prompt styles in sequence

## Debug Notes (Same-Run Attempt)
### Goal
Achieve same-run bypass without relying on ComfyUI's ExecutionBlocker (ComfyUI 0.10.0 / frontend 1.37.11).

### What We Tried
1) ExecutionBlocker approach (backend)
   - Added ExecutionBlocker import attempts in `nodes_lite.py` and used it to halt downstream execution.
   - On this ComfyUI build, ExecutionBlocker was unavailable.
   - A temporary fake ExecutionBlocker caused runtime errors in RMBG (`'ExecutionBlocker' object is not iterable`).
   - Result: removed fake blocker; backend_controls stays False.

2) Backend prompt handler (pre-queue)
   - Added `_umi_bypass_prompt_handler` in `__init__.py` to mutate prompt node `mode` before queue execution.
   - Installed handler using PromptServer hooks.
   - Logs show it runs and sets target node mode (0 or 4), but this still behaves like a one-run lag in practice.

3) Frontend preflight (queue-time prompt mutation)
   - Added `/umi/bypass_preview` route in `__init__.py` to run `_umi_bypass_prompt_handler`.
   - Wrapped `api.queuePrompt` and `app.queuePrompt` in `js/umi_text_bypass.js` to:
     - Convert workflow to a prompt graph using `graphToPrompt`.
     - Send prompt to `/umi/bypass_preview`.
     - Apply returned `mode` values back onto `workflow.nodes`.
   - For ComfyUI 0.10.0, `graphToPrompt` returns `{workflow, output}`, and `output` is the prompt graph.
   - Logs confirm: preflight runs, prompt preview applied, and workflow nodes show `mode=4` for bypass.
   - Despite this, RMBG still executes in the same run even when `matched=false`.
   - Later removed: the route only echoed the prompt back, so the wrapper added a
     round-trip to every queue without changing anything.

### Current Observations / Suspects
- `workflow.nodes[].mode` might not be the flag ComfyUI 0.10.0 uses for bypass at execution time.
- The prompt execution path might ignore `workflow.nodes[].mode` and rely on a different field
  (e.g., `node.bypass`, `node.properties.bypass`, or a runtime execution graph not affected by workflow changes).
- The frontend still receives `umi_bypass_signal` and toggles node mode, but that remains next-run.

### Latest Attempt (Trying Multiple Properties) - CONFIRMED NOT WORKING
Added comprehensive logging and tried multiple execution control properties:
- `mode` (0 or 4)
- `properties.bypass` (true/false)
- `muted` (true/false)
- `disabled` (true/false)

**Results:**
- ✅ Frontend successfully sends correct prompt graph (14 nodes) to backend
- ✅ Backend receives graph and finds UmiTextBypass node
- ✅ Backend successfully modifies target node properties
- ❌ **RMBG still executes despite all properties being set**

**Key Finding:**
The prompt graph nodes do NOT have a `mode` property initially - they only have:
- `inputs` (dict of input values)
- `class_type` (string node type)
- `_meta` (metadata like title)

Setting `mode`, `properties.bypass`, `muted`, or `disabled` in the prompt graph has **no effect on execution**.

**Conclusion:**
ComfyUI 0.10.0's execution engine does NOT read execution control flags from the prompt graph. The execution plan is determined elsewhere (likely in `execution.py` or `validate.py`) and cannot be modified by changing the prompt graph structure. Same-run bypass is **architecturally impossible** with this approach.

The **1-run lag approach works perfectly** and is the recommended solution.
