# 📘 UmiAI Wildcard Processor

[![Join Discord](https://img.shields.io/badge/Discord-Join%20Umi%20AI-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/9K7j7DTfG2)

**A "Logic Engine" for ComfyUI Prompts.**

UmiAI transforms static prompts into dynamic, context-aware workflows. It introduces **Persistent Variables**, **Conditional Logic**, **Native LoRA Loading**, and **External Data Fetching** directly into your prompt text box.

## ✨ Key Features

* **🔋 Native LoRA Loading:** Type `<lora:filename:1.0>` directly in the text. The node patches the model internally—no external LoRA Loader nodes required.
* **🛠️ Z-Image Support:** Automatically detects and fixes Z-Image format LoRAs (QKV Fusion) on the fly.
* **🧠 Persistent Variables:** Define a choice once (`$hair={Red|Blue}`) and reuse it (`$hair`) anywhere to ensure consistency.
* **🔀 Conditional Logic:** `[if keyword : True Text | False Text]` logic gates. Perfect for ensuring outfits match genres.
* **🌍 Global Presets:** Automatically load variables from `wildcards/globals.yaml` into *every* prompt.
* **🎨 Danbooru Integration:** Type `char:name` to automatically fetch visual tags from Danbooru.
* **📏 Resolution Control:** Set `@@width=1024@@` inside your prompt to control image size contextually.

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

---

## 🔌 Wiring Guide (The "Passthrough" Method)

The UmiAI node acts as the "Central Brain". You must pass your **Model** and **CLIP** through it so it can apply LoRAs automatically.

### 1. The Main Chain
* Connect **Checkpoint Loader (Model & CLIP)** &#10142; **UmiAI Node (Inputs)**.
* Connect **UmiAI Node (Model & CLIP Outputs)** &#10142; **KSampler** or **Text Encode**.

### 2. Prompts & Resolution
* **Text Output** &#10142; `CLIP Text Encode` (Positive)
* **Negative Output** &#10142; `CLIP Text Encode` (Negative)
* **Width/Height** &#10142; `Empty Latent Image`

> **⚠️ Setting up Resolution Control:**
> To let the node control image size (e.g., `@@width=1024@@`), right-click your **Empty Latent Image** node and select **Convert width/height to input**, then connect the wires.
<img width="883" height="194" alt="wvQeZXNUmL" src="https://github.com/user-attachments/assets/f6018158-297b-45a1-9593-2ce751e8cf38" />

---

## ⚡ Syntax Cheat Sheet

| Feature | Syntax | Example 1 | Example 2 |
| :--- | :--- | :--- | :--- |
| **Load LoRA** | `<lora:name:str>` | `<lora:pixel_art:0.8>` | `<lora:tifa_lockhart:1>` |
| **Random Choice** | `{a\|b\|c}` | `{Red\|Blue\|Green}` | `{Girl\|Boy\|Nonbinary}` |
| **Random Weights** | `{#%a\|#%b\|#%c}` | `{25%Red\|15%Blue\|60%Green}` | `{75%Girl\|115%Boy\|35%Nonbinary}` |
| **Choose X of Y** | `{x-y$$a\|b\|c}` | `{0-2$$Hat\|Scarf\|Belt}` | `{1-3$$Swimming\|Flying\|Jumping}` |
| **Variables** | `$var={opts}` | `$hair={Red\|Blue\|Green}` | `$char1={Tifa\|Aerith\|Zelda}` |
| **Use Variable** | `$var` | `A photo of $hair hair.` | `$char1 hugging $char2` |
| **Danbooru** | `char:name` | `char:zelda` | `char:tifa_lockhart` |
| **Sequential** | `{~a\|b\|c}` | `{~Front\|Side\|Back}` | `{~Seed1\|Seed2\|Seed3}` |
| **Logic Gate** | `[if Key : A \| B]` | `[if Cyberpunk : Techwear \| Armor]` |  |
| **Set Size** | `@@w=X, h=Y@@` | `@@width=1024, height=1536@@` | |
| **Comments** | `//` or `#` | `// This is a comment` | |

---

## 🔋 LoRA & Z-Image System

You no longer need to chain multiple LoRA Loader nodes. UmiAI handles it internally.

### Basic Usage
Type `<lora:` to trigger the autocomplete menu.
```text
<lora:my_style_v1:0.8>
```

### Z-Image Auto-Detection
If you are using **Z-Image** LoRAs (which normally require special loaders due to QKV mismatch), UmiAI handles this automatically.
1.  Load the file using the standard syntax: `<lora:z-image-anime:1.0>`
2.  The node detects the key format and applies the **QKV Fusion Patch** instantly.

### Dynamic LoRAs
You can use wildcards or logic to switch LoRAs per generation:
```text
// Randomly pick a style LoRA
{ <lora:anime_style:1.0> | <lora:realistic_v2:0.8> }
```
Note that LORAs may use either their internal filename or their actual filename.

---

## 📂 Creating Wildcards

UmiAI reads files from the `wildcards/` folder.

### 1. Simple Text Lists (.txt)
Create `wildcards/colors.txt`:
```text
Red
Blue
Green
```
**Usage:** Type `__` to select `__colors__`.

### 2. Advanced Tag Lists (.yaml)
Create `wildcards/styles.yaml` (You can hide LoRAs here!):
```yaml
2.5 Dimensional Temptation - Noa Base:
  Description:
    - Noa from the series '2.5 Dimensional Temptation' without a designated outfit
  Prompts:
    - '<lora:ILL CHAR 2.5 Dimensional Temptation GIRLPACK - Amano Lilisa, Tachibana Mikari, Noa, Kisaki Aria, 753, Makino:1> nonoa_def, Noa, blue eyes, black hair, short hair, sailor collar'
    - '<lora:ILL CHAR 2.5 Dimensional Temptation GIRLPACK - Amano Lilisa, Tachibana Mikari, Noa, Kisaki Aria, 753, Makino:1> nonoa_cos, Noa, blue eyes, blue hair, short hair, hair ornament'
  Tags:
    - 2.5 Dimensional Temptation
    - Noa
    - Human
    - White Skin
    - Lora
    - Girl Base
  Prefix:
    - 
  Suffix:
    - 
A-Rank Party - Silk Outfit:
  Description:
    - Silk from the series 'A-Rank Party' wearing her canonical outfits
  Prompts:
    - '<lora:ILL CHAR A-Rank Party - Silk:0.5> dark-skinned female, white hair, orange eyes, pointy ears, earrings, {swept bangs, french braid, long hair|high ponytail, swept bangs, long hair}, {SilkArcherOne, purple scarf, black jacket, long sleeves, black leotard, chest guard, red ribbon, leotard under clothes, underbust, highleg, white gloves, fur-trimmed shorts, white shorts, brown belt|SilkArcherTwo, beret, purple headwear, white ascot, cropped vest, white vest, sleeveless, elbow gloves, white gloves, vambraces, black leotard, leotard under clothes, highleg, fur-trimmed shorts, white shorts, red belt|SilkCasual, strapless, off-shoulder dress, frilled dress, purple dress, cleavage, long sleeves, light purple sleeves, pleated skirt, miniskirt, light pink skirt}'
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
**Usage:** Type `<` to select `<[Demihuman]>` and randomly choose a prompt between any of the YAML entries using `<[Demihuman]>` as a tag.

---

## 🚀 Example Workflows:

```text
// 1. Define Variables & Style
$genre={High Fantasy|Cyberpunk}
$view={~Portrait|Landscape}

// 2. Logic: Set LoRA and Resolution based on Genre/View
[if Cyberpunk: <lora:cyberpunk_v3:0.8>][if Fantasy: <lora:rpg_tools:1.0>]
[if Portrait: @@width=1024, height=1536@@][if Landscape: @@width=1536, height=1024@@]

// 3. Main Prompt
(Masterpiece), A $view of a warrior, female.

// 4. Context Logic (Outfit changes based on Genre variable)
She is wearing [if Fantasy: plate armor | if Cyberpunk: tech jacket].

The background is a $genre landscape.
**watermark, text, blurry, nsfw**
```

Here's a prompt I like to use all the time:
```text
$char1={__RandomGirls__}
$char2={__RandomGirls__}
$color1={__Colors__}
$color2={__Colors__}
$color3={__Colors__}
$color4={__Colors__}

A fullbody illustration of two girls standing together at a fashion show in the style of __ArtistNames__. $char1 is wearing __RandomOutfit__ with a primary color of $color1 and a secondary color of $color2. $char2 is wearing __RandomOutfit__ with a primary color of $color3 and a secondary color of $color4. {Both girls are __SharedPose__|The girls are holding hands and smiling while __MiscPose__}.

The background is __Background__.
```

---

## 💬 Community & Support

Join the **Umi AI** Discord server to share workflows and get help!

👉 **[Join our Discord Server](https://discord.gg/9K7j7DTfG2)**
