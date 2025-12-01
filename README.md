# 📘 UmiAI Wildcard Processor

[![Join Discord](https://img.shields.io/badge/Discord-Join%20Umi%20AI-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/9K7j7DTfG2)

**A "Logic Engine" for ComfyUI Prompts.**

UmiAI transforms static prompts into dynamic, context-aware workflows. It introduces **Persistent Variables**, **Conditional Logic**, **Sequential Cycles**, and **External Data Fetching** (Danbooru) directly into your prompt text box.

## ✨ Key Features

* **🧠 Persistent Variables:** Define a choice once (`$hair={Red|Blue}`) and reuse it (`$hair`) anywhere to ensure consistency across complex prompts.
* **🌍 Global Presets:** Automatically load variables from `wildcards/globals.yaml` (e.g., `$quality`, `$negatives`) into *every* prompt without typing them.
* **🔀 Conditional Logic:** `[if keyword : True Text | False Text]` logic gates. Perfect for ensuring your character's outfit matches the background genre automatically.
* **🎨 Danbooru Integration:** Type `char:name` to automatically fetch visual appearance tags (eyes, hair, outfit) from Danbooru.
* **🔁 Sequential Cycles:** `{~A|B|C}` cycles through options deterministically based on the seed. Essential for XY Plots and Grid comparisons.
* **📝 Comments:** Use `//` or `#` to add notes to your prompts (stripped at runtime).
* **⌨️ Autocomplete:** Built-in popup for Files (`__`) and Tags (`<`) directly in the text box.
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
    * ❌ `ComfyUI-UmiAI v1.0` (Spaces break the Python import!)
    * ✅ `ComfyUI-UmiAI`
4.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5.  **Restart ComfyUI** completely.

### Method 2: ComfyUI Manager
* **Install via Git URL:** Copy the URL of this repository and paste it into the "Install via Git URL" field in ComfyUI Manager.

---

## 🔌 Wiring Guide

The UmiAI node acts as the "Central Brain" of your workflow.

### 1. Connect Prompts
* **Text Output** ➔ `CLIP Text Encode` (Positive)
* **Negative Output** ➔ `CLIP Text Encode` (Negative)
    * *This enables inline features like `**watermark**` removal.*

### 2. Connect Resolution (Crucial!)
To allow the node to control image size (e.g., `@@width=1024@@`), you must connect it to your Latent node.
1.  **Right-Click** your `Empty Latent Image` node.
2.  Select **Convert width to input**.
3.  Select **Convert height to input**.
4.  Connect the **Width/Height** wires from UmiAI to the Latent node.

> **⚠️ Note on Batch Size:**
> Do **not** use the "Batch Size" widget on the Empty Latent node if you want prompt variations. You will get X copies of the same image.
> Instead, use the **"Queue Batch"** setting in the ComfyUI Extra Options menu.

---

## ⚡ Syntax Cheat Sheet

| Feature | Syntax | Example |
| :--- | :--- | :--- |
| **Random Choice** | `{a\|b\|c}` | `{Red\|Blue\|Green}` |
| **Variables** | `$var={opts}` | `$hair={Red\|Blue}` |
| **Use Variable** | `$var` | `A photo of $hair hair.` |
| **String Filters** | `$var.filter` | `$var.clean` / `$var.upper` / `$var.title` |
| **Logic Gate** | `[if Key : A \| B]` | `[if Cyberpunk : Techwear \| Armor]` |
| **Danbooru** | `char:name` | `char:frieren` |
| **Sequential** | `{~a\|b\|c}` | `{~Front\|Side\|Back}` |
| **Set Size** | `@@w=X, h=Y@@` | `@@width=1024, height=1536@@` |
| **Negatives** | `**text**` | `A landscape **text, watermark**` |
| **Comments** | `//` or `#` | `// This is a comment` |

---

## 📂 Creating Wildcards

UmiAI reads files from the `wildcards/` folder.

### 1. Simple Text Lists (.txt)
Create a file named `wildcards/colors.txt`:
```text
Red
Blue
Green
```
**Usage:** Type `__` in ComfyUI to select `__colors__`.

### 2. Advanced Tag Lists (.yaml)
Create a file named `wildcards/styles.yaml`:
```yaml
Cyberpunk:
    Tags: [scifi, neon]
    Prompts: ["neon lights", "chrome", "high tech"]
```
**Usage:** Type `<` in ComfyUI to select `<[scifi]>`.

### 3. Global Presets (globals.yaml)
Variables defined here are available in **every** prompt automatically.
Create `wildcards/globals.yaml`:
```yaml
quality: "masterpiece, best quality, 8k, highly detailed"
negatives: "bad hands, text, watermark, nsfw"
```
**Usage:** Just type `$quality` or `**$negatives**` in any prompt.

---

## 🚀 Example Workflow: The "Context-Aware" Character

Copy this prompt into the node to test the full logic capabilities. It auto-selects a genre, then ensures the **Outfit**, **Weapon**, and **Resolution** all match that genre.

```text
// 1. Define Variables
$genre={High Fantasy|Cyberpunk|Post-Apocalyptic}
$view={~Portrait|Landscape}

// 2. Logic: Set resolution based on View
[if Portrait: @@width=1024, height=1536@@][if Landscape: @@width=1536, height=1024@@]

// 3. Main Prompt
(Masterpiece), A $view of a warrior, female.

// 4. Context Logic (If genre matches, pick specific outfit)
She is wearing [if Fantasy: plate armor | [if Cyberpunk: tech jacket | rags]].
She is holding [if Fantasy: a sword | [if Cyberpunk: a pistol | a crowbar]].

The background is a $genre landscape.

// 5. Inline Negatives
**watermark, text, blurry, nsfw**
```

---

## 💬 Community & Support

Join the **Umi AI** Discord server to share workflows, get help, and discuss new features!

👉 **[Join our Discord Server](https://discord.gg/9K7j7DTfG2)**

---

## ❓ Troubleshooting

**The "User Guide" menu option isn't showing up!**
1.  **Browser Cache:** Press `CTRL+F5` (Windows) or `Cmd+Shift+R` (Mac) to hard refresh ComfyUI.
2.  **Folder Name:** Ensure your installation folder does **not** have spaces or dots (e.g., `UmiAI v1.0`). It must be a valid Python module name like `UmiAI_Wildcards`.
3.  **Console Check:** Press F12 -> Console. If you see red errors, ensure you installed `requests` and `pyyaml`.