# 📘 UmiAI Wildcard Processor

[![Join Discord](https://img.shields.io/badge/Discord-Join%20Umi%20AI-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/9K7j7DTfG2)

**A Complete Logic Engine for ComfyUI Prompts.**

UmiAI transforms static prompts into dynamic, context-aware workflows. It introduces **Persistent Variables**, **Advanced Boolean Logic**, **Native LoRA Loading**, **Local LLM Integration**, **Vision Models**, and **External Data Fetching** directly into your prompt text box—all in a single, powerful ComfyUI node.

> 💡 **Note:** If your workflow has issues after updating, right-click the UmiAI Node and select **Fix Node (Recreate)** to reset it with correct default values.

---

## ✨ Key Features

### 🔋 Prompt Processing & Logic
* **🔀 Advanced Logic Engine:** Full support for `AND`, `OR`, `NOT`, `XOR`, and `( )` grouping. Use it to filter wildcards or conditionally change prompt text.
* **🧠 Persistent Variables:** Define a choice once (`$hair={Red|Blue}`) and reuse it (`$hair`) anywhere to ensure consistency across your prompt.
* **🎲 Dynamic Wildcards:** Replace `__tagname__` with random selections from text files, with support for weighted ranges (`1-3$$tagname`).
* **🔄 Random Choices:** Use `{option1|option2|option3}` to randomly pick variants within your prompt.
* **📊 Weighted Choices:** Use `{25%Red|75%Blue}` for precise probability control over random selections.
* **💬 Comment Support:** Add `//` or `#` comments to document your complex prompts without affecting output.

### ✨ Editor Features
* **🎨 Syntax Highlighting:** Real-time color coding:
  - Green: Wildcards (`__tag__`), Prompt files (`__@file__`)
  - Blue: YAML tags (`<[tag]>`)
  - Yellow: Dynamic choices (`{a|b}`)
  - Gold: Range wildcards (`__2-4$$tag__`)
  - Purple: Variables (`$var`)
  - Cyan: Conditionals (`[if:]`)
  - Teal: Functions (`[shuffle:]`, `[clean:]`)
  - Orange: LoRAs (`<lora:>`)
  - Magenta: BREAK keyword
  - Red: Negatives (`**neg**`)
* **🔍 Prompt Linting:** Automatic error detection with expandable error panel. Click the lint bar to see all issues.
* **🔧 Syntax Fix:** Click Fix buttons to automatically repair broken syntax (brackets, wildcards, YAML tags).
* **🧹 Auto-Clean:** Toggle button to automatically clean up spaces, commas, and format BREAK keywords.
* **💡 Smart Autocomplete:** Type trigger characters for suggestions:
  - `__` → Wildcard files
  - `<[` → YAML tags
  - `<lora:` → LoRA models
  - `$` → Variables from globals.yaml
* **👁️ Wildcard Preview:** Hover over any `__wildcard__` to see its contents.

### 🤖 AI-Powered Features
* **👁️ Vision Models (Optional):** Use `[VISION: custom instruction]` to describe images with local AI models (JoyCaption Alpha-2, LLava-1.5).
* **🧠 Integrated Local LLM:** Turn simple tag lists into rich natural language descriptions using `[LLM: tag soup]` syntax (Qwen 2.5, Dolphin-Llama3.1).
* **🎨 Danbooru Integration:** Type `char:character_name` to automatically fetch visual tags from the Danbooru API with configurable filtering.
* **⚙️ Temperature Control:** Separate temperature controls for vision and text LLM models for precise output tuning.

### 🎯 LoRA Management
* **🔋 Native LoRA Loading:** Type `<lora:filename:1.0>` directly in the text. The node patches the model internally—no external LoRA Loader nodes required.
* **📦 LoRA Browser (Ctrl+L):** Visual grid browser with preview images, search, strength slider, and one-click insertion.
* **🌐 CivitAI Integration:** Fetch metadata, preview images, and trigger words from CivitAI with batch or per-card fetch buttons.
* **🛠️ Z-Image Support:** Automatically detects and fixes Z-Image format LoRAs (QKV Fusion) on the fly.
* **📊 LoRA Metadata Extraction:** Automatically pulls training tags from LoRA safetensors files for enhanced prompting.
* **💾 LRU Caching:** Efficient LoRA memory management with configurable cache limits.

### 🖼️ Browser Panels
* **📦 LoRA Browser (Ctrl+L):** Browse, search, and insert LoRAs with CivitAI metadata and preview images.
* **🖼️ Image Browser (Ctrl+I):** Booru-style gallery for generated images with metadata extraction and prompt copying.
* **💾 Preset Manager (Ctrl+P):** Save and load complete node configurations instantly.
* **📜 Prompt History (Ctrl+H):** Automatic tracking of all prompts with search and one-click restore.
* **🏷️ YAML Tag Manager (Ctrl+Y):** Analyze and export your YAML tag database.
* **📝 File Editor (Ctrl+E):** Edit wildcards and YAML files directly in ComfyUI.

### 📁 Data & File Support
* **📊 CSV Data Injection:** Load spreadsheet data (.csv) and map columns to variables (e.g., $name, $outfit) for complex character handling.
* **📝 Multiple File Formats:** Support for TXT (line-by-line lists), YAML (structured cards with metadata), and CSV (tabular data).
* **🌍 Global Presets:** Automatically load variables from `wildcards/globals.yaml` into *every* prompt.
* **🗂️ Hierarchical YAML:** Support for nested category structures with Prefix/Suffix systems.

### 🎨 Advanced Controls
* **📏 Resolution Control:** Set `@@width=1024, height=1536@@` inside your prompt to control image dimensions contextually.
* **➖ Scoped Negatives:** Use `--neg: negative text` syntax to embed negative prompts directly in your workflow.
* **🔁 Recursive Processing:** Iterative prompt refinement with cycle detection (max 50 passes).
* **🎯 Seeded Determinism:** Reproducible random selections via seed control for consistent results.

---

## 🛠️ Installation

### Method 1: Manual Install (Recommended)
1.  Navigate to your `ComfyUI/custom_nodes/` folder.
2.  Clone this repository:
    ```bash
    git clone https://github.com/Tinuva88/Comfy-UmiAI
    ```
3.  **⚠️ IMPORTANT:** Rename the folder to `ComfyUI-UmiAI` if it isn't already.
4.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5.  **Restart ComfyUI** completely.

### Method 2: ComfyUI Manager
* **Install via Git URL:** Copy the URL of this repository and paste it into ComfyUI Manager.

### Optional: Local LLM Support
For vision and text LLM features, the node will automatically download and install `llama-cpp-python` when you first use these features. The installer detects your CUDA version and installs the appropriate build (CUDA 11.7, 11.8, 12.1, 12.4, or CPU).

You can disable auto-updates in the node settings if you prefer manual installation.

---

### Updating

**Node giving you a strange issue after updating? Right click the node and press "Fix Node (recreate)" and it'll repopulate with correct default values**

## 🔌 Wiring Guide (The "Passthrough" Method)

The UmiAI node acts as the "Central Brain". You must pass your **Model** and **CLIP** through it so it can apply LoRAs automatically.

### 1. The Main Chain
* Connect **Checkpoint Loader (Model & CLIP)** → **UmiAI Node (Inputs)**.
* Connect **UmiAI Node (Model & CLIP Outputs)** → **KSampler** or **Text Encode**.

### 2. Prompts & Resolution
* **Text Output** → `CLIP Text Encode` (Positive)
* **Negative Output** → `CLIP Text Encode` (Negative)
* **Width/Height** → `Empty Latent Image`

### 3. Vision Model Support (Optional)
* Connect an **Image Loader** → **UmiAI Node (Image Input)** to enable vision features.

> **⚠️ Setting up Resolution Control:**
> To let the node control image size (e.g., `@@width=1024@@`), right-click your **Empty Latent Image** node and select **Convert width/height to input**, then connect the wires.
<img width="883" height="194" alt="wvQeZXNUmL" src="https://github.com/user-attachments/assets/f6018158-297b-45a1-9593-2ce751e8cf38" />

---

## ⚡ Syntax Cheat Sheet

| Feature | Syntax | Example |
| :--- | :--- | :--- |
| **Load LoRA** | `<lora:name:str>` | `<lora:pixel_art:0.8>` |
| **Random Choice** | `{a\|b\|c}` | `{Red\|Blue\|Green}` |
| **Weighted Choice** | `{25%A\|75%B}` | `{25%Red\|75%Blue}` |
| **Logic (Prompt)** | `[if Logic : True \| False]` | `[if red AND blue : Purple \| Grey]` |
| **Logic (Wildcard)**| `__[Logic]__` | `__[fire OR (ice AND magic)]__` |
| **Operators** | `AND`, `OR`, `NOT`, `XOR` | `[if (A OR B) AND NOT C : ...]` |
| **Variables** | `$var={opts}` | `$hair={Red\|Blue}` |
| **Equality Check** | `$var=val` | `[if $hair=Red : Fire Magic]` |
| **Wildcards** | `__filename__` | `__colors__` |
| **Weighted Range** | `1-3$$filename` | `2-4$$accessories__` |
| **YAML Tags** | `<[tagname]>` | `<[Demihuman]>` |
| **Character** | `@@name:outfit:emotion@@` | `@@elena:casual:happy@@` |
| **Danbooru** | `char:name` | `char:tifa_lockhart` |
| **Vision AI** | `[VISION: instruction]` | `[VISION: describe the mood]` |
| **LLM Naturalize** | `[LLM: tags]` | `[LLM: 1girl, solo, beach]` |
| **Set Size** | `@@w=X, h=Y@@` | `@@width=1024, height=1536@@` |
| **Negative Prompt** | `--neg: text` | `--neg: blurry, low quality` |
| **Comments** | `//` or `#` | `// This is a comment` |

### ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| **Ctrl+L** | Open LoRA Browser |
| **Ctrl+I** | Open Image Browser |
| **Ctrl+P** | Open Preset Manager |
| **Ctrl+H** | Open Prompt History |
| **Ctrl+Y** | Open YAML Tag Manager |
| **Ctrl+E** | Open File Editor |
| **Ctrl+?** | Open Shortcuts & Syntax Reference |
| **Ctrl+M** | Open Model Manager |
| **Ctrl+Shift+B** | Fix syntax errors (in text field) |
| **ESC** | Close any panel |

---

## 🧠 Advanced Boolean Logic

UmiAI features a unified logic engine that works in both your **Prompts** and your **Wildcard Filters**.

### Supported Operators
* **AND**: Both conditions must be true.
* **OR**: At least one condition must be true.
* **NOT**: The condition must be absent/false.
* **XOR**: Only one condition can be true (Exclusive OR).
* **()**: Parentheses for grouping complex logic.

### 1. Logic in Prompts (`[if ...]`)
You can change the text of your prompt based on other words present in the prompt (or variables).

```text
// Simple check: If 'red' AND 'blue' are present, output 'Purple'.
[if red AND blue : Purple | Grey]

// Variable check: If $char is defined as 'robot', add oil.
[if $char=robot : leaking oil | sweating]

// Complex grouping
[if (scifi OR cyber) AND NOT space : futuristic city | nature landscape]

// Nested conditions
[if fantasy : [if magic AND NOT tech : wizard | knight | modern soldier]]
```

### 2. Logic in Wildcards (`__[ ... ]__`)
You can search your Wildcards and YAML cards (Global Index) for entries that match specific tags.

```text
// Find characters tagged as both "Demihuman" and "Dark Skin"
__[Demihuman AND Dark Skin]__

// Find entries tagged "Fire" OR "Ice" but NOT "Water"
__[(fire OR ice) AND NOT water]__
```

---

## 🤖 AI-Powered Features

### 👁️ Vision Models (Image Captioning)

UmiAI can use local vision models to analyze images and generate descriptions automatically.

**Supported Models:**
* **JoyCaption Alpha-2**: High-quality image captioning
* **LLava-1.5**: General-purpose vision understanding

**Usage:**
```text
// Basic image description
[VISION: describe this image in detail]

// Custom instructions
[VISION: describe the character's outfit and pose]

// Combine with other features
A detailed illustration of [VISION: describe the character], $style style
```

**Setup:**
1. Connect an image to the UmiAI node's image input
2. Select a vision model from the dropdown
3. Use `[VISION: instruction]` tags in your prompt
4. The model runs on CPU to preserve GPU VRAM

**Settings:**
* **Vision Temperature**: Controls creativity (default 0.5)
* **Vision Max Tokens**: Limits description length

### 🧠 LLM Prompt Naturalizer

Turn "tag soup" (e.g., 1girl, solo, beach) into lush, descriptive prose using a local Large Language Model.

**Supported Models:**
* **Qwen2.5-1.5B (Fast)**: Low RAM usage, good for quick descriptions
* **Dolphin-Llama3.1-8B (Smart)**: Uncensored, follows complex instructions perfectly

**Usage:**
```text
// Convert tags to natural language
[LLM: 1girl, solo, standing, beach, sunset, happy expression]

// The LLM will output something like:
// "A lone girl stands on the beach at sunset, her face radiating happiness..."

// Mix with other features
[LLM: $char1, $outfit, $location] in the style of __ArtistNames__
```

**Setup:**
1. In the `llm_model` widget, select "Download Recommended"
2. Choose your preferred model (Qwen for speed, Dolphin for quality)
3. Use `[LLM: tags]` syntax in your prompt

**Customization:**
* **Temperature**: Controls creativity (0.7 is standard, lower for literal, higher for creative)
* **Max Tokens**: Limits description length (600 = ~1 paragraph)
* **Custom System Prompt**: Override default behavior
  * Default: "Creative Writer" persona (flowery, descriptive)
  * Example: "You are a horror writer. Describe the tags in a terrifying way."

**Note:** The LLM automatically protects `<lora:...>` tags from being modified or removed.

---

## 🔋 LoRA & Z-Image System

You no longer need to chain multiple LoRA Loader nodes. UmiAI handles it internally.

### Basic Usage
Type `<lora:` to trigger the autocomplete menu with all available LoRAs.
```text
<lora:my_style_v1:0.8>
```

### Z-Image Auto-Detection
If you are using **Z-Image** LoRAs (which normally require special loaders due to QKV mismatch), UmiAI handles this automatically.
1.  Load the file using the standard syntax: `<lora:z-image-anime:1.0>`
2.  The node detects the key format and applies the **QKV Fusion Patch** instantly.

### LoRA Metadata Extraction
UmiAI automatically reads training tags embedded in LoRA safetensors files and can inject them into your prompt.

**Settings:**
* **LoRA Behavior**:
  * **Append**: Add training tags at the end
  * **Prepend**: Add training tags at the beginning
  * **Disabled**: Don't inject tags (manual control only)

### Dynamic LoRAs
You can use wildcards or logic to switch LoRAs per generation:
```text
// Randomly pick a style LoRA
{ <lora:anime_style:1.0> | <lora:realistic_v2:0.8> }

// Conditional LoRA loading
[if fantasy : <lora:medieval_v3:0.9> | <lora:scifi_tech:0.8>]

// Variable-based LoRA
$style={anime **styleA** | realistic **styleB**}
[if styleA : <lora:anime_lora:1.0>]
[if styleB : <lora:photo_lora:0.8>]
```

**Note:** LoRAs may use either their internal filename or their actual filename for matching.

### LoRA Caching
UmiAI uses LRU (Least Recently Used) caching to efficiently manage LoRA models in memory. The cache automatically handles:
* Loading LoRAs only when needed
* Removing old LoRAs when memory limits are reached
* Garbage collection for optimal memory usage

---

## 🎭 Character Consistency System

Maintain consistent character appearances across multiple generations with outfit and emotion variations.

### Character Folder Structure
```
ComfyUI-UmiAI/
└── characters/
    ├── elena/
    │   ├── profile.yaml      # Character definition
    │   └── reference.png     # Reference image for IP-Adapter
    └── kai/
        ├── profile.yaml
        └── reference.png
```

### Creating a Character Profile

Create `characters/[name]/profile.yaml`:

```yaml
name: Elena
base_prompt: 'elena, silver hair, long hair, blue eyes, fair skin'
lora: elena_character_v1
lora_strength: 0.8

outfits:
  casual:
    prompt: 'casual clothes, t-shirt, jeans'
  formal:
    prompt: 'elegant black dress, high heels'
  combat:
    prompt: 'battle armor, wielding sword'

emotions:
  happy: 'smiling, happy expression, bright eyes'
  sad: 'tearful eyes, sad expression'
  angry: 'furrowed brow, intense eyes'
```

### Inline Syntax

Use the `@@character:outfit:emotion@@` syntax directly in your prompts:

```text
// Base character only
@@elena@@

// With outfit
@@elena:casual@@

// With outfit and emotion (full)
@@elena:casual:happy@@

// Combine with other features
A portrait of @@elena:formal:happy@@ in a garden, __ArtStyle__
```

### Character Manager Node

**UmiAI Character Manager** - Single character prompt builder:
- Inputs: character (dropdown), outfit, emotion, pose
- Outputs: `prompt`, `negative`, `lora_string`, `reference_image`, `pose_image`
- Connect `reference_image` to IP-Adapter, `pose_image` to ControlNet

### Character Batch Generator Node

**UmiAI Character Batch Generator** - Generate all variations:
- Modes: `all_outfits`, `all_emotions`, `all_poses`, `outfit_emotion_matrix`
- Outputs: `prompts_list`, `labels_list`, `count`
- Use with batch processing nodes for sprite sheet generation

### Sprite Export Node

**UmiAI Sprite Export** - Organized output:
- Saves to: `output/sprites/character/outfit/emotion_pose.png`
- Formats: PNG, WebP
- Auto-organizes by character for easy management

### Character Info Node

**UmiAI Character Info** - Profile debugging:
- Outputs: character_info, outfits_list, emotions_list, poses_list, counts
- Useful for workflow planning and debugging

### API Endpoint

Access character data via API for external tools:
```
GET /umiapp/characters
```
Returns: character names, outfits, emotions, poses for each profile

---

## 🎬 Camera Control & Pose System

### Camera Control Nodes

Generate camera angle prompts for multi-angle LoRAs:

| Node | Description |
| :--- | :--- |
| **UmiAI Camera Control** | Slider-based azimuth/elevation/distance |
| **UmiAI Visual Camera Control** | Interactive canvas widget |

**Features:**
- Azimuth: 0-360° (snaps to 45° increments)
- Elevation: -30° to 60° (low angle → high angle)
- Distance: close-up, medium shot, wide shot
- Configurable trigger word (default: `<sks>`)

**Output example:** `<sks> front view eye-level shot medium shot`

### Pose Library

**UmiAI Pose Library** - 30+ built-in poses loaded from `presets/poses.yaml`:
- Categories: standing, sitting, action, expressive, lying, kneeling, leaning
- Outputs: `pose_prompt`, `pose_tags`

### Expression Mixer

**UmiAI Expression Mixer** - Blend emotions with weights:
- 40+ emotions from `presets/emotions.yaml`
- Mix up to 3 emotions with percentage weights
- Example: happy:60% + excited:40%

### Scene Composer

**UmiAI Scene Composer** - Combine backgrounds, lighting, atmosphere:
- 50+ backgrounds from `presets/scenes.yaml`
- 11 lighting styles
- 10 atmosphere presets

### Adding Custom Presets

Edit the YAML files in `presets/` folder:

```yaml
# In presets/poses.yaml
my_custom_pose:
  prompt: "your pose description"
  tags: ["tag1", "tag2"]
```

---

## 📊 LoRA Dataset Generation

Generate training data for LoRA fine-tuning:

### Dataset Export

**UmiAI Dataset Export** - Kohya-compatible output:
- Formats: kohya, dreambooth, simple
- Auto-generates captions from character profiles
- Flip augmentation support
- Configurable repeats

### Caption Nodes

| Node | Description |
| :--- | :--- |
| **UmiAI Auto Caption** | Wrapper for external captioners (BLIP, WD14) |
| **UmiAI Caption Enhancer** | Combine captions with character info |
| **UmiAI Caption Generator** | Build captions from components |

---

## 📦 Bundled Wildcards

UmiAI includes ready-to-use wildcards in the `wildcards/` folder:

| Wildcard | Contents |
| :--- | :--- |
| `__poses__` | 40+ character poses |
| `__emotions__` | 45+ facial expressions |
| `__backgrounds__` | 40+ environments |
| `__lighting__` | 30+ lighting setups |

**Usage in prompts:**
```text
A portrait of @@elena:casual@@ with __emotions__, __poses__, __backgrounds__, __lighting__
```

---

## 🔧 Model Manager

Download recommended models directly in ComfyUI:

**Open:** Press `Ctrl+Shift+M`

### Available Categories:
- **Character LoRAs** - Consistency LoRAs
- **ControlNets** - Pose, depth, canny
- **YOLO/SAM** - Detection and segmentation
- **Captioners** - BLIP, WD14, Florence-2
- **Upscalers** - 2x and 4x models

---

## 🎥 Sample Workflows

Import ready-to-use workflows from `workflows/` folder:

| Workflow | Description |
| :--- | :--- |
| `character_basic.json` | Character Manager → Sampler |
| `character_batch.json` | Batch Generator → Sprite Export |
| `camera_control.json` | Visual Camera → Character |
| `lora_dataset.json` | Full dataset generation pipeline |

---

## 📂 Creating Wildcards

UmiAI reads files from the `wildcards/` folder in your ComfyUI-UmiAI installation.

### 1. Simple Text Lists (.txt)
Create `wildcards/colors.txt`:
```text
Red
Blue
Green
Yellow
Purple
```
**Usage:** Type `__` to open autocomplete and select `__colors__`. Each generation will pick one random color.

**Weighted Ranges:**
```text
// Pick 2-4 random colors
__2-4$$colors__
```

### 2. Advanced Tag Lists (.yaml)
Create `wildcards/characters.yaml`:
```yaml
Character Name - Outfit:
  Description:
    - Brief description of the character and outfit
  Prompts:
    - 'First prompt variant with <lora:example:1.0> and tags'
    - 'Second prompt variant with different tags'
  Tags:
    - Category1
    - Category2
    - Trait1
    - Trait2
  Prefix:
    - Text to add before the selected prompt
  Suffix:
    - Text to add after the selected prompt
```

**Full Example:**
```yaml
2.5 Dimensional Temptation - Noa Base:
  Description:
    - Noa from the series '2.5 Dimensional Temptation' without a designated outfit
  Prompts:
    - '<lora:2.5D_Temptation:1> nonoa_def, Noa, blue eyes, black hair, short hair, sailor collar'
    - '<lora:2.5D_Temptation:1> nonoa_cos, Noa, blue eyes, blue hair, short hair, hair ornament'
  Tags:
    - 2.5 Dimensional Temptation
    - Noa
    - Human
    - White Skin
    - Lora
    - Girl Base
  Prefix:
    - masterpiece, best quality,
  Suffix:
    - highly detailed

A-Rank Party - Silk Outfit:
  Description:
    - Silk from the series 'A-Rank Party' wearing her canonical outfits
  Prompts:
    - '<lora:ARankParty_Silk:0.5> dark-skinned female, white hair, orange eyes, pointy ears, earrings, {swept bangs, french braid, long hair|high ponytail, swept bangs, long hair}, {SilkArcherOne, purple scarf, black jacket, long sleeves, black leotard, chest guard, red ribbon, leotard under clothes, underbust, highleg, white gloves, fur-trimmed shorts, white shorts, brown belt|SilkArcherTwo, beret, purple headwear, white ascot, cropped vest, white vest, sleeveless, elbow gloves, white gloves, vambraces, black leotard, leotard under clothes, highleg, fur-trimmed shorts, white shorts, red belt}'
  Tags:
    - A-Rank Party
    - Silk
    - Demihuman
    - Dark Skin
    - Colored Skin
    - Lora
    - Girl Outfit
  Prefix:
    -
  Suffix:
    -
```

**Usage with Tags:** Type `<` to open tag search and select `<[Demihuman]>` to randomly choose from any YAML entry with that tag.

**Tag Logic:**
```text
// AND: Both tags must be present
<[Demihuman AND Dark Skin]>

// OR: At least one tag
<[Fire OR Ice]>

// Complex logic
<[(Human OR Demihuman) AND NOT Robot]>
```

### 3. CSV Data Injection
Create `wildcards/characters.csv`:
```csv
name,outfit,hair,eyes
Alice,red dress,blonde,blue
Bob,suit,black,brown
Carol,armor,silver,green
```

**Usage:**
```text
// UmiAI automatically maps columns to variables
A portrait of $name wearing $outfit, with $hair hair and $eyes eyes
```

### 4. Global Presets
Create `wildcards/globals.yaml` to define variables that load automatically into every prompt:
```yaml
$quality: {masterpiece, best quality|high quality, detailed}
$artist: {artist1|artist2|artist3}
```

These variables are available in all prompts without needing to define them each time.

---

## 🎨 Danbooru Character Integration

Automatically fetch visual tags for characters from the Danbooru API.

### Basic Usage
```text
char:hatsune_miku
// Fetches: twintails, aqua_hair, aqua_eyes, headset, etc.

char:tifa_lockhart
// Fetches: black_hair, red_eyes, white_shirt, black_skirt, etc.
```

### Settings
* **Danbooru Threshold**: Minimum tag score to include (higher = more relevant tags)
* **Max Danbooru Tags**: Maximum number of tags to fetch per character

### Tag Filtering
UmiAI automatically:
* Filters out overly generic tags
* Uses a blacklist to remove common/irrelevant tags
* Caches results locally to avoid repeated API calls
* Respects API rate limits

### Example
```text
// Combine with other features
$char={hatsune_miku|kagamine_rin|megurine_luka}
A portrait of char:$char in __ArtStyle__ style, $pose
```

---

## 🎯 Advanced Techniques

### 1. Persistent Variables
Variables maintain their value throughout the entire prompt, ensuring consistency:

```text
// Define once
$hair={red|blue|green|purple}
$eyes={amber|emerald|sapphire}

// Use multiple times - same value everywhere
A girl with $hair hair and $eyes eyes,
wearing a $hair dress,
$hair theme,
[if $hair=red : fire magic | ice magic]
```

### 2. Compound Variables (Hidden Markers)
Pack multiple "keys" into one variable for complex logic:

```text
// Key 1: Visible text
// Key 2: LoRA trigger (**L1**)
// Key 3: Description trigger (**D1**)
$theme={Fire **L1** **D1**|Ice **L2** **D2**|Lightning **L3** **D3**}

// Use the theme (displays "Fire" but includes hidden **L1** **D1**)
$theme elemental magic

// Conditional LoRA loading (only sees L1, L2, L3)
[if L1: <lora:fire_element:0.8>]
[if L2: <lora:ice_element:0.8>]
[if L3: <lora:lightning_element:0.8>]

// Conditional descriptions (only sees D1, D2, D3)
[if D1: warm lighting, flames, ember particles]
[if D2: cold atmosphere, ice crystals, frost]
[if D3: electric sparks, storm clouds]
```

The `**hidden**` markers are automatically removed from the final output but remain available for logic checks.

### 3. Nested Conditionals
```text
$genre={fantasy **F**|scifi **S**|modern **M**}
$magic={yes **MAG**|no **NOMAG**}

[if F: [if MAG: wizard casting spells | knight with sword] |
[if S: [if MAG: psychic powers | high-tech weapons] |
[if M: modern city]]]
```

### 4. Dynamic Resolution
```text
$aspect={portrait **VERT**|landscape **HORZ**|square **SQ**}

// Set different sizes based on aspect ratio
[if VERT: @@width=768, height=1024@@]
[if HORZ: @@width=1024, height=768@@]
[if SQ: @@width=1024, height=1024@@]

A $aspect composition of...
```

### 5. Combining All Features
```text
// Variables
$char={__CharacterGirls__|__CharacterBoys__}
$style={anime **A**|realistic **R**|painterly **P**}
$location={beach|forest|city|mountains}

// LLM + Vision combo
[VISION: describe the lighting and mood] combined with [LLM: $char, standing, $location, $style style]

// Conditional LoRA
[if A: <lora:anime_style_v3:0.9>]
[if R: <lora:realistic_photo:0.8>]
[if P: <lora:oil_painting:1.0>]

// Dynamic size
@@width=1024, height=1344@@

// Danbooru character
Using visual traits from char:$char

// Logic-based details
[if beach: swimsuit, ocean waves, sunny |
[if forest: nature, trees, dappled sunlight |
[if city: urban, buildings, street |
[if mountains: peaks, clouds, hiking gear]]]]

// Negative
--neg: blurry, low quality, worst quality
```

---

## 🚀 Example Workflows

### Example 1: Compound Variables
```text
// Define complex theme variable
$theme={Fire **L1** **D1**|Ice **L2** **D2**}
$mood={Happy|Angry}
@@width=768, height=768@@

// Main prompt
(Masterpiece), char:hatsune_miku,
$theme theme.

// Logic-based LoRA loading
[if L1: <lora:fire_element_v1:0.8>]
[if L2: <lora:ice_concept:1.0>]

// Logic-based descriptions
[if D1: [if Happy: warm lighting | burning flames]]
[if D2: frozen crystal textures],

// Wildcards with weighted ranges
highlighted in __2$$colors__.

// Negative prompt
--neg: worst quality, lowres
```

### Example 2: Multi-Character Fashion Show
```text
$char1={__RandomGirls__}
$char2={__RandomGirls__}
$color1={__Colors__}
$color2={__Colors__}
$color3={__Colors__}
$color4={__Colors__}

A fullbody illustration of two girls standing together at a fashion show in the style of __ArtistNames__.
$char1 is wearing __RandomOutfit__ with a primary color of $color1 and a secondary color of $color2.
$char2 is wearing __RandomOutfit__ with a primary color of $color3 and a secondary color of $color4.
{Both girls are __SharedPose__|The girls are holding hands and smiling while __MiscPose__}.

The background is __Background__.

--neg: bad anatomy, extra limbs, blurry
```

### Example 3: Genre-Adaptive Workflow
```text
$genre={fantasy **F**|scifi **S**|cyberpunk **C**}
$character={warrior|mage|rogue|scientist|hacker}

// Genre-specific LoRAs
[if F: <lora:fantasy_rpg:0.9>]
[if S: <lora:scifi_concept:0.8>]
[if C: <lora:cyberpunk_2077:1.0>]

[LLM: $character, $genre setting, action pose, detailed]

// Genre-specific environment
[if F: medieval castle, magic particles, fantasy lighting |
[if S: space station, holographic displays, neon lights |
[if C: dystopian city, rain, neon signs, dark atmosphere]]]

@@width=1024, height=1344@@

--neg: low quality, bad hands, mutation
```

### Example 4: Vision-Enhanced Workflow
```text
// Feed an existing image to the node
[VISION: describe the character's appearance, outfit, and pose in detail]

// Enhance with LLM
[LLM: [VISION: describe the character], professional photography, studio lighting, high detail]

// Add style
in the style of __ArtistNames__, <lora:photorealistic_v2:0.7>

@@width=1024, height=1536@@
```

---

## 🔧 Node Settings Reference

### Input Parameters
* **text** (required): Your main prompt with UmiAI syntax
* **seed** (required): Random seed for reproducible results

### Optional Connections
* **model**: Model input for LoRA patching (passthrough)
* **clip**: CLIP input for LoRA patching (passthrough)
* **image**: Image input for vision models

### LLM Settings
* **llm_model**: Select text model (Qwen/Dolphin) or "Download Recommended"
* **llm_temperature**: Text generation creativity (default: 0.7)
* **llm_max_tokens**: Maximum response length (default: 600)
* **llm_system_prompt**: Custom system prompt override
* **vision_model**: Select vision model (JoyCaption/LLava)
* **vision_temperature**: Vision generation creativity (default: 0.5)
* **vision_max_tokens**: Maximum vision response length

### LoRA Settings
* **lora_behavior**: Append/Prepend/Disabled (tag injection mode)
* **lora_cache_limit**: Maximum cached LoRAs

### Danbooru Settings
* **danbooru_threshold**: Minimum tag relevance score
* **max_danbooru_tags**: Maximum tags to fetch per character

### Other Settings
* **resolution_control**: Enable/disable `@@width@@` syntax
* **auto_update_llama_cpp**: Auto-install llama-cpp-python

### Output Parameters
* **model**: Model with LoRAs applied
* **clip**: CLIP with LoRAs applied
* **text**: Processed positive prompt
* **negative_text**: Generated negative prompt
* **width**: Extracted or default width
* **height**: Extracted or default height
* **lora_info**: Metadata from loaded LoRAs

---

## 🎓 Tips & Best Practices

### Performance Optimization
* Use LLM features on CPU to preserve GPU VRAM for image generation
* LoRA caching automatically manages memory—increase cache limit if you use many LoRAs
* Vision models are slower—only use when needed
* Use weighted ranges (`2-4$$tags`) instead of multiple wildcards for variety

### Prompt Organization
* Use comments (`//`) to document complex prompts
* Group related logic together
* Define all variables at the top of your prompt
* Use globals.yaml for frequently-used variables

### Debugging
* Check the console output for processing details
* Use simple prompts first, then add complexity
* Test logic conditions individually before combining
* Verify wildcard files are in the correct folder

### Common Pitfalls
* Don't forget to pass Model/CLIP through the node for LoRA support
* Ensure wildcard filenames match exactly (case-sensitive)
* Close brackets/parentheses in logic expressions
* Use `|` (pipe) for choice separators, not commas
* Remember that `**hidden**` markers affect logic but not output

---

## 🔄 Processing Pipeline

Understanding the order of operations helps build complex prompts:

1. **Comment Stripping**: Remove `//` and `#` comments
2. **Load Globals**: Import variables from `wildcards/globals.yaml`
3. **Iterative Processing** (up to 50 passes):
   - Vision tag replacement (`[VISION]`)
   - LLM tag replacement (`[LLM]`)
   - Variable assignment (`$var={...}`)
   - Variable substitution (`$var`)
   - Wildcard replacement (`__tag__`)
   - Random choices (`{a|b|c}`)
   - Danbooru character fetching (`char:name`)
4. **Conditional Logic**: Apply `[if]` statements
5. **Prefix/Suffix**: Add from YAML metadata
6. **Negative Prompts**: Collect `--neg:` entries
7. **Cleanup**: Remove duplicates, extra commas, spaces
8. **LoRA Extraction**: Parse and load LoRAs
9. **Settings Extraction**: Parse `@@width@@` and `@@height@@`
10. **Output Generation**: Return all processed data

---

## 🆘 Troubleshooting

### LoRAs Not Loading
* Ensure Model and CLIP are connected to the UmiAI node inputs
* Check LoRA filename matches exactly (use autocomplete)
* Verify LoRA files are in ComfyUI's lora folder

### Autocomplete Not Working
* Restart ComfyUI after installation
* Check browser console for JavaScript errors
* Verify `js/umi_wildcards.js` exists in the node folder

### Vision/LLM Features Not Available
* Models download automatically on first use
* Check console for download progress
* Ensure internet connection for HuggingFace downloads
* Verify you have sufficient RAM/disk space

### Wildcards Not Found
* Check files are in `ComfyUI-UmiAI/wildcards/` folder
* Verify file extensions (`.txt`, `.yaml`, `.csv`)
* Use autocomplete to see available wildcards
* Check console for file loading errors

### Logic Not Working
* Verify all brackets are closed: `[if A : B | C]`
* Check operator spelling: `AND`, `OR`, `NOT`, `XOR` (case-sensitive)
* Test simple conditions first before nesting
* Use parentheses for complex expressions

### Node Errors After Update
* Right-click node → "Fix Node (Recreate)"
* Check for breaking changes in update notes
* Clear browser cache
* Restart ComfyUI

---

## 🏗️ Technical Details

### Architecture
* **Language**: Python 3 backend, JavaScript frontend
* **Dependencies**: PyYAML, Requests, PyTorch, SafeTensors
* **Optional**: llama-cpp-python, huggingface-hub
* **Integration**: Native ComfyUI custom node

### File Structure
```
ComfyUI-UmiAI/
├── __init__.py              # ComfyUI registration & API routes
├── nodes.py                 # Main processing engine (1930 lines)
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── js/
│   └── umi_wildcards.js    # Frontend autocomplete UI
├── cache/                  # Cached Danbooru data
├── sample workflow/
│   └── UmiAI-Sample.json   # Example workflow
└── wildcards/              # Your wildcard files
    ├── globals.yaml        # Global variables
    └── [your files here]
```

### API Endpoints
* `GET /umi/wildcards`: Returns all available wildcards, tags, and LoRAs (JSON)

### Core Classes
* `UmiAIWildcardNode`: Main ComfyUI node
* `TagLoader`: File indexing and loading
* `TagSelector`: Random/seeded selection
* `TagReplacer`: Wildcard substitution
* `DynamicPromptReplacer`: Choice syntax handling
* `ConditionalReplacer`: Boolean logic evaluation
* `VariableReplacer`: Variable management
* `DanbooruReplacer`: API integration
* `LoRAHandler`: Model patching and caching
* `VisionReplacer`: Image captioning
* `LLMReplacer`: Text naturalization
* `NegativePromptGenerator`: Negative collection

---

## 💬 Community & Support

Join the **Umi AI** Discord server to share workflows, get help, and see what others are creating!

👉 **[Join our Discord Server](https://discord.gg/9K7j7DTfG2)**

### Contributing
Found a bug? Have a feature request? Open an issue on GitHub!

### Credits
Created and maintained by the Umi AI team.

---

## 📄 License

Check the repository for license information.

---

**Happy Prompting! 🎨✨**
