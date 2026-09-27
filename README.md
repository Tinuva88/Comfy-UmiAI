# UmiAI Reference Manual

UmiAI is a modular ComfyUI custom-node toolkit. Its small core provides prompt
expansion, prompt inspection, wildcard management, LoRA prompt handling, and
metadata-aware image saving. Krea 2 ideation, Anima/editing tools, the
memory/split-nibble system, and asset-management UI tools are independently
installable overlays.

This manual is written for public release users. It describes the current lean
build: the active nodes, supported prompt language, editable files, optional
browser panels, and common workflow patterns.

## What UmiAI Provides

- A seeded wildcard processor for repeatable prompt variation.
- A prompt language with wildcards, inline choices, variables, conditionals,
  negative prompt extraction, prompt presets, profiles, sections, and settings.
- Inline LoRA references that can load LoRAs and optionally inject trigger text.
- Prompt linting, prompt diff output, and explain JSON for debugging.
- A metadata-aware save node plus settings, wildcard, and run-inspection UI.
- Optional Krea 2 prompt ideation using the model's already-loaded Qwen3-VL
  text encoder, without loading a second LLM.
- Optional Anima wildcard cohesion, artist-chain splitting, prompt ordering,
  sampling, and editing helpers.
- Optional FLUX.2 Klein 9B role-aware references, precision masks, and exact
  source compositing.
- Optional image, LoRA, Danbooru, and series-management browser panels.
- Optional memory diagnostics, MiniMax H3 patches, and split-nibble runtimes.

## Modular Bundles

C-UMI ships as one core archive and five optional overlay archives. Release
filenames include the package version; the current release is `0.5.0`:

- `C-UMI-0.5.0-core.zip`: prompt processing, linting, profiles, metadata saves,
  bypass nodes, and the core settings/wildcard frontend.
- `C-UMI-0.5.0-krea.zip`: Krea 2 ideation, style DNA, and semantic novelty.
- `C-UMI-0.5.0-anima_edit.zip`: Anima prompt/sampling helpers and image editing.
- `C-UMI-0.5.0-klein_edit.zip`: precision-edit helpers and a corrected Klein
  9B workflow.
- `C-UMI-0.5.0-memory.zip`: memory diagnostics, MiniMax H3 patches, and
  split-nibble.
- `C-UMI-0.5.0-ui_tools.zip`: image, LoRA, Danbooru, and series browser tools.

All archives contain the same top-level `C-UMI` folder. Install core first,
then merge any optional archive into `ComfyUI/custom_nodes` and restart. Missing
optional overlays are treated as normal and do not affect core startup. See
`MODULAR_PACKAGING.md` for release-building and installation details.

Each overlay has a sidecar manifest declaring its compatible core API range.
An incompatible overlay is skipped with a warning instead of being imported.

## Installation

1. Extract `C-UMI-0.5.0-core.zip` into `ComfyUI/custom_nodes`.
2. Install the Python requirements from this folder:

   ```bash
   pip install -r requirements.txt
   ```

3. Optionally extract one or more overlay archives into `ComfyUI/custom_nodes`,
   merging their `C-UMI` folder with the core folder.
4. If installing `ui_tools`, also run
   `pip install -r requirements-ui-tools.txt` with ComfyUI's Python.
5. Restart ComfyUI.
6. In ComfyUI, look for nodes under `UmiAI`, `UmiAI/prompt`, and the
   categories contributed by installed overlays.

The core requirement is `pyyaml`. The UI-tools overlay additionally requires
`requests` and `curl_cffi`. UmiAI also uses ComfyUI's own model, LoRA, image,
sampler, and web-server APIs.

## Development Checks

The backend tests use only the Python standard-library runner and provide small
ComfyUI/web stubs, so they can run without starting ComfyUI:

```bash
python -m unittest discover -s tests -v
```

The frontend prompt renderer has a separate structure and round-trip check:

```bash
node tests/check_prompt_structure.mjs
```

## Active Nodes

### UmiAI Wildcard Processor

Main prompt-processing node.

Inputs:

- `text`: source prompt using UmiAI syntax.
- `seed`: controls seeded wildcard and choice expansion.
- `model`, `clip`: optional passthrough connections. Required when inline LoRA
  loading should patch the model/clip.
- `lora_tags_behavior`: `Append to Prompt`, `Prepend to Prompt`, or `Disabled`.
- `lora_cache_limit`: number of loaded LoRAs to keep cached. Set `0` to disable
  caching.
- `width`, `height`: default dimensions returned by the node.
- `input_negative`: optional incoming negative prompt.
- `bypass_phrases`: comma-separated phrases to detect in the processed prompt,
  matched as whole words and ignoring case (`cat` does not match `category`).
- `prompt_profile`: optional model-family prompt profile.
- `prompt_preset`: optional named preset from `prompt_presets.yaml`.
- `preset_placement`: `append`, `prepend`, or `replace`.
- `section_order`: comma-separated order for `[section:name]` blocks.
- `dry_run`: expands text and reports LoRA information without loading LoRAs.
- `anima_prompt_mode` (Anima/edit overlay): leave processing off, order the
  resolved fragments as tags, or compose cohesive visual sentences.
- `anima_artist_mode` (Anima/edit overlay): keep `@artist` fragments in the
  prompt or split them for Anima Artist Mixer.

Outputs:

- `model`, `clip`: patched or passthrough model and clip.
- `text`: final positive prompt.
- `negative_text`: final negative prompt.
- `width`, `height`: final dimensions, including prompt-embedded overrides.
- `lora_info`: loaded LoRA information or dry-run notes.
- `input_text`, `input_negative`: original inputs, useful for metadata saves.
- `bypass_matches`: JSON boolean list matching `bypass_phrases`.
- `explain_json`: processing trace, variables, sections, warnings, and settings.
- `prompt_diff`: added/removed prompt-token summary.
- `artist_chain`: resolved `@artist` fragments for Anima Artist Mixer. This
  compatibility output remains present in core and is empty without Anima/edit.

Typical use: connect the processed `text` to positive text encoding, connect
`negative_text` to negative text encoding, and pass `model`/`clip` onward when
using inline LoRAs.

### Umi Save Image (with metadata)

Saves images through ComfyUI's output folder and embeds Umi prompt metadata in
the PNG. The image browser can later search and display this metadata.

Inputs:

- `images`: image batch to save.
- `filename_prefix`: output filename prefix.
- `positive_prompt`, `negative_prompt`: processed prompts.
- `input_prompt`, `input_negative`: original prompts before expansion.

Use this instead of the stock save node when you want searchable prompt
metadata.

### Umi Bypass

Conditionally passes through one selected data type: image, latent,
conditioning, model, clip, or string. It reads `matched_list` from the Wildcard
Processor's `bypass_matches` output and a `match_index`.

When the selected match is false and ComfyUI's execution blocker is available,
downstream execution is blocked. Otherwise the node still reports state to the
frontend and behaves as a passthrough fallback.

### Umi Bypass Model Switch

Chooses between `base_model` and `reference_model` using the same
`matched_list` and `match_index` pattern. This is useful for workflows where a
prompt phrase should switch to a reference or edit model.

### Umi Prompt Preset

Applies one preset from `prompt_presets.yaml` to a prompt and negative prompt.
Placement can append, prepend, or replace the positive prompt. Preset negatives
are appended to the negative prompt.

### Umi Prompt Profile

Applies a named profile from `prompt_profiles.yaml`. Profiles can add positive
defaults, merge negative defaults, and emit warnings when prompts look too short
or mismatched for the target model family.

Core profiles include `None`, `Illustrious`, `Pony`, `SDXL`, and `Flux`. The
Anima/edit overlay adds `Anima Base` and its Anima presets at runtime.

### Umi Prompt Inspector

Compares an input prompt and a processed prompt. It returns:

- `diff_json`: added and removed prompt tokens.
- `lint_warnings`: profile and LoRA-related warnings.
- `sections_json`: parsed prompt sections.

### Umi Prompt Syntax Lint

Checks prompt syntax without expanding randomness. It reports errors, warnings,
and a structured JSON report for:

- unclosed delimiters,
- wildcard range issues,
- malformed LoRA options,
- missing wildcard and prompt files, with typo suggestions and fallback notes,
- missing presets,
- profile warnings,
- suspicious prompt joins,
- negative syntax counts.

### Umi Anima Prompt Helper (Anima/edit overlay)

Formats prompts for Anima-style tag workflows.

Modes:

- `profile`: add Anima quality defaults, order tags, and add default negatives.
- `order_only`: reorder tags without adding positive defaults.
- `natural_language`: expand short natural-language fragments before applying
  Anima ordering.

Style presets include anime illustration, clean lineart, painterly, official
art, flat color, and high detail.

### Cohesive Anima wildcards

With the Anima/edit overlay installed, the Wildcard Processor can turn any
number of resolved wildcards into a single structured Anima prompt without
loading a second text-generation model.
Choose the prompt profile that matches the loaded checkpoint:

- `Anima Base`: standard Base-style checkpoints; includes score-tag defaults.
- `Anima Aesthetic`: Aesthetic checkpoints; intentionally omits score tags.
- `Anima Turbo`: Turbo checkpoints paired with the 8–12 step, CFG 1 path.

Then set:

- `anima_prompt_mode = cohesive prompt`
- `anima_artist_mode = split for artist mixer`

Wildcard source names provide semantic hints. For example, values from pose,
background, camera, lighting, and style wildcards are composed into subject,
action, setting, composition, lighting, and rendering sentences. Quality and
safety tags remain at the front, LoRA syntax remains intact, and artist tokens
are returned separately through `artist_chain`.

The recommended `workflows/anima_cumi_v2_production.json` provides a verified
quality baseline plus explicit muted Turbo, FLS, Corrective Flow, CNS, LLLite,
TeaCache, Cross-Attn, and hires A/B paths. It defaults to the installed
`riakuAnima_v021lily.safetensors` and uses the current core
`ModelPatchLoader -> AnimaLLLiteApply` contract. The older
`anima_cumi_flow_artist_lllite.json` remains available as a legacy reference.

### Umi Krea 2 Prompt Architect (Krea overlay)

Builds seeded, natural-language art direction for Krea 2 image models. Give it
a subject or leave the subject empty to invent a concept. The node coordinates
a conceptual lens, visual event, medium, composition, lighting, palette, and
material detail instead of producing an unstructured list of quality tags.

- `direction` selects a visual discipline or lets the seed choose one.
- `creative_risk` controls how far the premise bends ordinary visual logic.
- `prompt_length` ranges from quick iteration to dense visual direction.
- `style_anchor` and `must_include` preserve user-supplied requirements.
- Outputs include the positive prompt, an optional negative prompt, a compact
  concept summary, and the complete seeded recipe as JSON.

### Umi Krea 2 Prompt Generator (Krea overlay)

The recommended Krea 2 ideation workflow. Connect the same `CLIP` loaded with
type `krea2` that will condition the image model. By default, `scene search`
chooses a coherent subject world, generates 32 variations around one controlled
violation of reality, scores them for feasibility, novelty, lexical diversity,
and cliché avoidance, then compiles the winner into a dense visual caption.
Qwen is used only to encode the finished text.

This default path performs no Qwen text generation and loads no second LLM.
It avoids the learned creative priors that caused repeated clockwork imagery
while preserving normal ComfyUI model management and Krea conditioning.

- `positive` connects directly to the sampler's positive conditioning input.
- `prompt` contains the deterministic, inspectable Krea prompt.
- `keywords` and `llm_prompt` expose the intermediate ideation for inspection.
- `ingredient_source` defaults to `scene search`. `balanced random` and
  `qwen stochastic` remain available for direct comparison.
- `content_scope` controls blank-concept invention in scene-search mode:
  `general` uses the broad all-audiences catalog, `adult` uses dedicated
  clearly-adult consensual portrait, intimacy, fetish, and afterglow worlds,
  and `unrestricted mix` samples both catalogs. A user-written adult concept
  remains the subject anchor even when `general` is selected.
- `style_strategy` selects one entry from the 285-entry cross-disciplinary
  visual-style database. It includes photography, cinema, anime and manga,
  illustration, graphic and print processes, painting, physical craft, and 3D
  rendering—not just named fine-art movements.
  `coherent match` stays within the rendering discipline, `productive contrast`
  crosses into a deliberately different but compatible discipline, `truly
  random` uses the complete database, and `none` disables the layer.
- Every selected style contributes its complete source description verbatim,
  including process, mark-making, rendering, composition, finish, and
  influences. It is never replaced by a shortened capsule. With
  `named_style_references` off, only the leading style label is omitted; the
  full description and source style name in `recipe_json` remain intact.
- `qwen_polish` may rewrite the scene around that style, but a runtime
  integrity check restores the exact full description before conditioning if
  Qwen omits or paraphrases any part of it.
- `novelty_memory` compares distilled scene fingerprints against the last 250,
  last 1000, or complete prompt archive. The fingerprint contains subject,
  action, setting, unfamiliar rule, and narrative tension, avoiding false
  similarity from the compiler's shared prose structure.
- `novelty_strength` controls the semantic repetition penalty, while
  `style_cooldown` softly avoids recently selected styles.
- `search_candidates` controls how many CPU-only scene recipes are scored.
  The default of 32 adds negligible cost compared with image generation.
- `qwen_polish` is disabled by default. Enabling it lets Qwen rewrite the
  deterministic direction before encoding.
- `keyword_temperature` controls the high-entropy ingredient pass independently
  when `qwen stochastic` is selected.
- `filter_common_cliches` is enabled by default. It rejects frequently repeated
  clock, cog, gear, machinery, time, and steampunk motifs during ingredient generation,
  then validates and retries the finished prompt if Qwen reintroduces one. The
  automatic blacklist is never included in Qwen's request text, avoiding
  accidental visual priming.
- Keyword responses must be valid JSON containing short visual phrases. Qwen
  commentary, copied instructions, and malformed responses are discarded and
  retried; the finished prompt receives the same leakage check before encoding.
- `conditioning_mode` should be `encode positive` for normal text-to-image and
  `prompt only` when feeding an image-aware node such as
  `Krea2EditGroundedEncode`.
- Sampling controls default to a creative non-thinking configuration and are
  available as advanced inputs.

The compiler varies five caption cadences while preserving perceptual order:
medium and style, subject and event, the single unfamiliar rule, physical
evidence, narrative tension, composition, lighting, colour, material detail,
and atmosphere. The primary bundled workflow includes live text previews for
the exact selected recipe and compiled prompt.

Semantic novelty uses the local `BAAI/bge-small-en-v1.5` model on CPU. Its
Safetensors weights occupy about 127 MiB; the first use loads the model once,
then warm candidate batches are fast. The archive is stored in
`cache/krea_novelty.sqlite3`. Each normalized 384-dimensional embedding uses
about 1.5 KiB, so tens of thousands of generations remain small. If the model
is missing or cannot load, scene search records the error in `recipe_json` and
continues with ordinary deterministic scoring.

The model can be restored with:

```powershell
<comfy-python> scripts\download_semantic_novelty_model.py
```

With novelty memory enabled, a fixed seed remains a reproducible candidate
universe but not necessarily a fixed winner: the archive can deliberately
select a less familiar candidate on a later run. Disable novelty memory for
strict seed-for-seed comparison.
It is
`workflows/krea2_text_to_image_umi_prompt.json`. It is a lean Krea 2 Turbo
text-to-image pipeline with no input image and no secondary LLM. The
generator's positive conditioning feeds KSampler directly; a
`ConditioningZeroOut` branch supplies the required negative socket at CFG 1
without another text-encoder pass.

`workflows/krea2_identity_edit_umi_prompt.json` remains available as the
image-edit variant. It uses `prompt only` mode and feeds Qwen's generated text
into `Krea2EditGroundedEncode`.

### Umi Krea 2 Keyword Forge (Krea overlay)

Generates an exact number of seeded visual ingredients, then packages them in a
request ready for a downstream LLM node. Connect `llm_prompt` to the text or
user-message input of the LLM node and use that node's response as the Krea 2
positive prompt.

This standalone fallback uses the local curated ingredient library because it
does not accept a generative `CLIP`. The integrated `Umi Krea 2 Prompt
Generator` is the core workflow node and asks Qwen to invent its ingredients.

- `rendering_mode` supports realism, art, anime, cinematic, graphic design, or
  a seeded surprise.
- `ideation_level` changes whether the ingredient set favors coherence,
  conceptual tension, or experimental visual devices.
- `keyword_count` is exact. A supplied `concept` is treated as one of those
  ingredients and as the non-negotiable subject anchor.
- `prompt_length` tells the LLM how dense its final natural-language caption
  should be.
- `keywords` is a newline-separated ingredient list; `recipe_json` records the
  category and value of every seeded choice.

### Umi CNS Anima Sampler (Anima/edit overlay)

Creates a sampler with colored-noise shaping options for Anima workflows. It
wraps a selected base sampler and exposes controls for noise strength, energy
scale, frequency bins, alpha tilting, gamma matrix loading, and related tuning.

### Umi Anima 2.9B Delta Merger (Anima/edit overlay)

Creates a new 40-layer Anima-2.9B diffusion checkpoint from three inputs:

- `target_29b`: the expanded 40-layer Anima-2.9B checkpoint.
- `source_base`: the original 28-layer Anima checkpoint from which the custom
  checkpoint descends.
- `custom_checkpoint`: the 28-layer fine-tune or merge whose delta should be
  transferred.

The merger computes `target + strength * (custom - source_base)`. It maps the
28 original transformer blocks to their corresponding positions in the
expanded model and preserves inserted blocks 2, 5, 8, 11, 14, 17, 21, 24, 27,
30, 33, and 36 unchanged. Start around `0.20` to `0.30`; stronger deltas can
overpower the 2.9B training. Inputs must be floating-point `.safetensors`
diffusion checkpoints. Quantized and GGUF checkpoints are intentionally
rejected because their values cannot provide a reliable training delta.

A 40-layer `source_base` and `custom_checkpoint` are also accepted; that is a
second 2.9B, which merges one-to-one with nothing to preserve. Optional inputs
add up to three more fine-tunes with their own weights and switch the
combination to `dare_linear`, `ties`, or `dare_ties`; leaving them alone
reproduces the single-model linear merge exactly. Before writing, the merger
samples native blocks and reports how far `target` sits from `source_base`.
Because the 28 -> 2.9B expansion retrained its trunk, some drift there is
expected and the report states the measured figure rather than demanding an
exact match — but a drift near or above `0.5` means the two checkpoints are not
versions of one model and the delta is being measured against the wrong
reference.

The operation runs in an isolated process, writes incrementally with bounded
RAM use, refuses to overwrite files, and leaves all inputs untouched. The
output is saved beside `target_29b` and requires the same expanded-Anima loader
support as the target model.

### Umi Subject Lock Mask (Anima/edit overlay)

Builds a graded redraw-permission mask for local image edits. The edit mask
defines where changes are allowed; optional face, visible-skin, and subject
masks reduce denoising inside protected regions.

- `face_redraw`, `skin_redraw`, and `contour_redraw` are redraw amounts:
  `0` preserves the source and `1` permits full regeneration.
- `subject_mask` is converted into a narrow contour band using
  `contour_radius` and `contour_feather`.
- `redraw_permission` connects to the core `Set Latent Noise Mask` node.
- `preservation_map` and `contour_band` are inspection outputs.

For latent edit models, encode the source image with the model's VAE, attach
`redraw_permission` with `Set Latent Noise Mask`, and use that source latent as
the sampler's `latent_image`. Keep the source connected through the edit
model's normal reference-conditioning path as well. Applying the core
`Differential Diffusion` node to the model makes intermediate mask values act
as spatially varying denoise start times.

For FLUX.2 Klein, replace the `Empty Flux 2 Latent` connected to
`SamplerCustomAdvanced` with:

```text
source image -> VAE Encode -> Set Latent Noise Mask -> latent_image
                                      ^
                         redraw_permission
```

The final output may still be composited over the source outside the original
edit mask for pixel-exact background preservation.

### FLUX.2 Klein 9B Precision Edit (Klein/edit overlay)

The bundled `workflows/klein9b_precision_edit.json` is the recommended
starting graph. It fixes the common topology failures that make edits drift:

- the source stays at its input resolution instead of being forced to one
  megapixel;
- the source and supporting images are VAE-encoded as ordered references and
  attached to both positive and negative conditioning;
- every reference has an explicit semantic role such as `base`, `garment`,
  `identity`, or `style`;
- the source latent, not an empty latent, is sampled under a graded noise mask;
- the original edit mask is used for the final exact composite, so pixels
  outside it are copied directly from the source.

The core precision nodes are:

- **Umi Klein Edit Prompt Compiler**: converts an instruction, ordered roles,
  preservation contract, and edit scope into an unambiguous image-indexed
  prompt.
- **Umi Klein Reference Pack**: stores ordered reference latents on both
  conditioning branches using FLUX.2's indexed reference method.
- **Umi Klein Precision Mask**: creates the sampler redraw mask while allowing
  face, hands, skin, seams, preserve, and force-redraw masks to constrain it.
- **Umi Klein Exact Composite**: resizes the decoded edit if necessary, feathers
  only inside the edit region, and restores every outside pixel exactly.
- **Umi Klein Region Prepare / Restore**: crops a padded mask ROI without
  changing its aspect, scales it to a model-friendly multiple of 16, and maps
  the result back to the original canvas. This raises effective target
  resolution for small, peripheral, foreshortened, and unusual-angle edits.
- **Umi Klein Edit Verifier**: ranks a candidate batch using outside/preserved
  pixel error, seam change, minimum edit activation, and optional masked
  reference color statistics. It selects without assuming matching anatomy,
  focus, or camera angle.

The workflow defaults to Klein 9B Distilled at 4 steps and CFG 1. For major
pose, anatomy, angle, or topology changes, switch to Klein 9B Base and use
40–50 steps with CFG 4. Keep image order and `reference_roles` synchronized.
The experimental `klein9b_precision_region_edit.json` additionally normalizes
the masked ROI and runs a best-of-two batch through the verifier. Set its
`Repeat Latent Batch` amount to `1` when VRAM is limited.
`klein9b_base_precision_region_edit.json` is the hard-edit preset: it selects
`flux-2-klein-base-9b-fp8.safetensors`, 50 steps, CFG 4, transformative prompt
scope, region normalization, and one candidate by default.
`klein9b_base_bf16_precision_region_edit.json` loads the original BF16 Base
checkpoint as the quality baseline. Its conservative 16 GB preset places Qwen
on CPU, uses a 1024-pixel normalized ROI, and keeps a single candidate. The
UNET Loader may be switched to `fp8_e4m3fn_fast` for an in-memory cast without
overwriting the BF16 source.

### Umi Skin Tone Reconcile (Anima/edit overlay)

Transfers visible-skin chroma statistics from a source image to generated skin
without replacing the edited image's OKLab lightness. It is intended for skin
that had to be regenerated and therefore could not be locked to existing
source pixels.

- `source_skin_mask` selects reliable visible skin in the source.
- `output_skin_mask` selects generated skin to correct.
- `strength` blends the correction.
- `match_variance` also matches the source chroma spread, with a bounded scale
  to avoid extreme color changes.

Use softly feathered skin masks. If either mask is empty, the edited image is
returned unchanged.

### MiniMax H3 Production Toolkit (memory overlay)

The production toolkit plans legal H3 durations and checkpoint families,
compiles explicit reference contracts, prepares low-token video references,
extracts calibrated four/six-view character sheets, and selects stable stills
from short image-edit sequences. It is designed for the native ComfyUI FL2VA
and Ref2VA conditioning nodes rather than a private sampler implementation.

- **Production Planner** returns the canvas, `17k+5` frame count, step count,
  MiniMax shifts, checkpoint family, and token estimate for Character Sheet,
  Image Edit, Multi-Image Video, Multi-Video Video, Character Swap, and Voice
  Clone Video tasks.
- **Prompt Director** validates `<Picture n>`, `<Video n>`, and `<Audio n>`
  ordinals and requires an explicit authorized-voice assertion for voice work.
- **Reference Video Prepare** converts IMAGE batches to 24 fps, a legal length,
  and a bounded short edge before native Ref2VA encoding.
- **Character Sheet Extract** returns both the review contact sheet and the
  independent views that should be reused as H3 references.
- **Edit Candidate Select** ranks decoded frames by sharpness, contrast,
  exposure, and temporal stability.

See [the RTX 4080 production guide](docs/minimax-h3-production.md) for complete
per-task graphs, Ref2VA/Turbo asset requirements, Spectrum and SLA compatibility,
voice consent, model-territory restrictions, and the local YouTube-friendly
memory profile.

### Umi MiniMax H3 Image Edit (T=1) (memory overlay)

Creates native one-frame MiniMax H3 reference conditioning and the matching
joint video/audio latent without modifying `comfy_extras/nodes_minimax_h3.py`.
Use the experimental MiniMax H3 single-image VAE; keep the original H3 VAE for
normal multi-frame video.

The node assigns reference images in fixed semantic order:

1. `source_image` becomes `<Picture 1>` with the `base` role.
2. Identity, outfit, pose, background, style, and additional images follow in
   that order when connected.

With `compile_contract` enabled, the output prompt explicitly limits every
reference to its assigned role and requests exactly one still image. Use the
`compiled_prompt` and `reference_manifest` outputs to inspect the final mapping.

- `target_mode=empty` performs a full regeneration. A connected source remains
  the base reference but is not used as the sampler's starting latent.
- `target_mode=source` VAE-encodes the fitted source into the target T=1 latent.
  The sampler's denoise value then controls spatial edit strength.
- `reference_fidelity` maps to H3's visual-conditioning noise augmentation.
  Higher values preserve references more strictly; lower values permit more
  departure. Start at `0.999` and change it only in controlled comparisons.
- `reference_resolution=identity_max` preserves additional token detail for
  identity and outfit inputs while capping other references by target area.
- `source_fit=center_crop` preserves proportions; choose `stretch` only when
  the source already matches the target aspect ratio or distortion is intended.

The latent has video shape `[1,24,1,H/16,W/16]` and the minimum joint audio
shape required by H3. Width and height must be divisible by 32. The node rejects
VAEs that do not encode a still as exactly `[1,24,1,H,W]`.

Minimal sampling connections:

```text
single-image H3 VAE -> Umi MiniMax H3 Image Edit -> positive -> KSampler
                                                   positive -> ConditioningZeroOut -> KSampler negative
                                                   latent -> KSampler latent_image
single-image H3 VAE -------------------------------------------------> VAE Decode
H3 model -> Turbo/detail LoRAs (optional) -> ModelSamplingMiniMaxH3
         -> Umi MiniMax Optimizer (optional) -> KSampler
```

Use sampler denoise `1.0` for an empty target. For a source target, begin with a
moderate denoise value and increase it only when the requested structural change
does not take. This is independent of `reference_fidelity`: denoise controls the
starting pixels while reference fidelity controls the persistent H3 references.

**Umi MiniMax H3 Reference Fidelity** exposes the same conditioning control for
workflows built with ComfyUI's stock MiniMax H3 conditioning nodes.

### Umi MiniMax Optimizer (memory overlay)

For normal MiniMax workflows, use **Umi MiniMax Optimizer**. It exposes only the
model and an intent-based preset; GPU tier, attention fallback, exact/Sage head
grouping, FFN chunking, safety headroom, and split-weight residency stay
automatic.

- `Balanced` is the recommended default and adapts exact/Sage attention to the
  sequence length.
- `Multitask / YouTube` keeps about 2.5 GB of VRAM free and disables persistent
  split-weight residency so browser playback remains responsive.
- `Lowest VRAM` uses the strongest grouping and smallest FFN chunks.
- `Fastest` spends more spare memory on large chunks and weight residency.
- `Quality First` keeps four blocks at each edge exact and uses Sage in the
  middle when it is installed.

The status output reports the detected GPU, whether Sage and split streaming
were found, and whether an exact fallback will be used. The first forward
chooses and caches the concrete plan. The clearest chain is:

```text
MiniMax loader -> KJ Sage patch (optional) -> Umi MiniMax Optimizer
```

For profiling and manual experiments, **Umi MiniMax H3 Memory Autopilot**
exposes the complete controller. It owns one memory budget and coordinates
three consumers that otherwise compete for the same VRAM:

- exact or installed Sage attention, including automatic head grouping;
- token-chunked FFNs; and
- the split-nibble scheduler's low-plane VRAM residency.

`target_vram_headroom_mb` is the reserve Autopilot tries to keep free. It
creates a plan on the first forward from sequence length, dtype, model shape,
and current free VRAM, then caches the plan by memory bucket. `adaptive` uses
exact attention for short sequences and an installed KJNodes MiniMax Sage
replacement for long sequences. `hybrid_edges` keeps the first and last
`exact_edge_blocks` exact while using Sage in the middle. If Sage is not
installed, both policies safely remain exact.

Autopilot and the split kernels share a leased CUDA scratch arena. A lease is
held through the final consumer of a temporary; an overlapping request falls
back to its ordinary allocation. This lets mutually exclusive decode and
attention-output workspaces reuse storage without aliasing live tensors.

`experimental_sage_bridge` lets C-UMI own QKV projection, in-place Q/K
normalization/RoPE, and head slicing before calling the compatible Sage kernel
already installed by KJNodes. It is off by default. The bridge is deliberately
an integration boundary: it preserves the current math while opening a stable
place for a future split-projection epilogue to emit Sage-ready Q/K/V directly.

Use only one of Optimizer, Autopilot, or the fixed Memory Patch in a workflow.
Sage object patches are detected at execution time, so reversing the final two
clone operations also works.

The fixed **Umi MiniMax H3 Memory Patch** remains available for manual tuning.

Patches native MiniMax H3 transformer blocks through ComfyUI's `ModelPatcher`.
It processes FFN rows in configurable token chunks and releases the normalized
attention input as soon as QKV projection finishes. `head_chunks` also groups
the exact path (or is forwarded to an installed Sage replacement). Model
weights and sampling math are unchanged. Start with `4096` FFN tokens; use
`2048` or `1024` when peak VRAM is still too high, at the cost of more kernel
launches.

For weight memory, phase two adds the architecture-neutral **Umi Split-Nibble
Model Loader**. The legacy **Umi MiniMax H3 Split-Nibble Loader** name remains
available so existing workflows continue to open. Anima, Krea 2, Flux2 Klein,
and MiniMax H3 use the same paired format.
It losslessly decomposes each ConvRot INT8 value as two signed packed nibbles.
The high nibble follows normal ComfyUI/ModelPatcher placement while the low
nibble remains CPU-backed and is copied only for the active linear. Both halves
are decoded inside a bundled CUDA tensor-core tile; the original INT8 value is
never expanded into a full weight tensor. A single INT32 accumulator is scaled
once, matching the native INT8 result. `linear_chunk_rows` caps temporary output
memory (start at `1024`). For H3, chain the memory patch after the loader to
combine weight paging with activation chunking. The CUDA kernel targets NVIDIA
Ampere or newer; unsupported systems fall back to the slower portable dual-INT8
path.

Convert a floating Anima checkpoint directly (the architecture is auto-detected):

```powershell
<comfy-python> scripts\convert_split_nibble.py `
  <ComfyUI>\models\diffusion_models\anima_bf16.safetensors
```

Floating checkpoints are converted to per-channel ConvRot INT8 before being
split. Diffusion-model embedding tables and non-matrix tensors remain in their
source format.
The split itself is exact relative to the resulting INT8 weights; any quality
change comes from floating-point-to-INT8 quantization. The same command accepts
native Comfy `int8_tensorwise` checkpoints and repacks those losslessly.

The converter writes paired `_core.safetensors` and `_low.safetensors` files.
Select both in the split-nibble loader. The pair has the same total weight size
as INT8; its benefit is reducing persistent GPU weight storage to four bits per
weight while retaining the complete INT8 value through streamed correction.
This is an experimental throughput/VRAM trade: on the local RTX 4080 synthetic
H3 `fc1` shape (`5376 -> 28672`, 256 rows), resident weight memory fell from
147 MiB to 73.5 MiB and the fused path used about 89 MiB of temporary memory.
Against the relevant full-INT8 streaming baseline, it measured 18.32 ms versus
15.66 ms (about 1.17x slower) while producing bit-identical BF16 output. A fully
GPU-resident native INT8 linear is still substantially faster; this format is
intended for the case where the complete INT8 model cannot remain resident.
For the local 2.09B Anima checkpoint, 515 eligible Linear layers require about
1.03 GB of persistent high-nibble storage; the other half streams from CPU.

### Anima split-nibble text encoder

The **Umi Anima Split-Nibble CLIP Loader** applies the same paired format to
Anima's separate Qwen3 0.6B encoder. Its token embedding is supported directly:
only requested token rows are reconstructed, and the complete low-nibble table
never moves to the GPU.

Maximum compression converts all 197 weight matrices:

```powershell
<comfy-python> scripts\convert_split_nibble.py `
  <ComfyUI>\models\text_encoders\animaLLMLayerwiseFP8_v1.safetensors `
  --architecture anima_te
```

The balanced quality profile keeps the token embedding and the first and last
two transformer blocks in source precision:

```powershell
<comfy-python> scripts\convert_split_nibble.py `
  <ComfyUI>\models\text_encoders\animaLLMLayerwiseFP8_v1.safetensors `
  --architecture anima_te --preserve-embedding --preserve-edge-layers 2
```

On the local encoder, maximum compression staged 297 MiB instead of 1136 MiB.
The balanced profile staged 610 MiB and produced conditioning cosine similarity
of 0.99946--0.99953 against FP16 over three test prompts. Use the balanced pair
for the default quality/VRAM trade and maximum compression for very small GPUs.

### Krea 2 and FLUX.2 Klein split-nibble support

Krea 2 and Klein have matching CLIP loaders and converters in addition to the
architecture-neutral diffusion-model loader:

- **Umi Krea 2 Split-Nibble CLIP Loader/Converter** uses `CLIPType.KREA2` and
  supports the mixed FP8 Qwen3-VL 4B encoder. Its balanced profile preserves
  the BF16 embedding, the first and last two language blocks, and the complete
  visual tower.
- **Umi Klein Split-Nibble CLIP Loader/Converter** uses `CLIPType.FLUX2` and
  supports Qwen3 4B/8B encoders. Native NVFP4 matrices remain native; eligible
  FP8/BF16 matrices are split instead of expanding already-efficient 4-bit
  weights.

The local balanced Krea encoder reduced measured prompt-encoding peak VRAM
from 5166 MiB to 3633 MiB and retained 0.99992 conditioning cosine similarity.
The local balanced Klein 8B encoder reduced peak VRAM from 8597 MiB to 5271 MiB
and retained 0.99988 cosine similarity. CPU streaming makes this a
VRAM/throughput trade; the diffusion denoiser and text encoder can use
different profiles independently.

The tested diffusion pairs stage about 6123 MiB for the 12.82B Krea model and
4336 MiB for the official 9B Klein model. In both cases the low-nibble file
stays CPU-backed and a real BF16 layer forward completed with finite output.

All split-nibble model and CLIP loaders also expose an optional transfer
pipeline:

- `transfer_mode = synchronous` preserves the original one-layer-at-a-time
  behavior. `async_double_buffer` learns the split-layer order during the first
  forward, then overlaps GPU work on layer N, pinned-memory H-to-D transfer for
  N+1, and a pageable-to-pinned CPU copy for N+2.
- `staging_buffer_mb` limits each of the two pinned-host and two CUDA buffers.
  Only this small conveyor belt is pinned; the complete low-nibble checkpoint
  remains ordinary pageable RAM. A layer larger than the limit safely uses the
  synchronous path.
- `profile_passes` prints total staged bytes, CPU staging time, H-to-D time,
  visible GPU stall, hidden-transfer percentage, compute time, per-tier layer
  counts, and the five worst layer stalls. The buffers are persistent between
  forwards and their CUDA allocations are released when Comfy detaches the
  model. If host staging is large relative to compute, the log prints the
  `pinned_residency_mb` value that would remove it.

### Residency tiers

Streaming every low nibble on every forward is only necessary for layers that
have nowhere cheaper to live. Two budgets let spare memory buy the transfer
away, and both are pure caches: output is bit-identical either way.

- `pinned_residency_mb` holds low nibbles in page-locked **system RAM**. This
  removes the pageable-to-pinned memcpy, leaving only the DMA. It costs ordinary
  RAM, not VRAM, so it is usually the first thing to raise. Setting it to the
  whole low-file size is normal on a machine with 32 GB or more.
- `vram_residency_mb` holds low nibbles in **VRAM**, removing their transfer
  entirely. Layers are chosen by measured stall per byte, so the budget lands on
  the layers that actually cause GPU bubbles. Before any measurement exists the
  scheduler uses smallest-first, since short layers have the least compute to
  hide a transfer behind.

Text encoders benefit most: they run before the diffusion model is staged, so
the VRAM is free at that point in the workflow, and their low files are small.
The Krea 2 balanced encoder's low half is 336 MiB, which fits easily.

Both tiers are released when Comfy detaches or cleans up the model.

### Schedule cache

The learned layer order is written to `cache/split_schedules/` keyed by
checkpoint name and size. On the next load the order is restored, so the very
first forward prefetches instead of running the synchronous learning pass. A
changed or rebuilt checkpoint misses the cache and relearns normally.

### Compute path

Where the shape allows it (more than 16 activation rows, with `k` and `n` both
multiples of 8), the linear rebuilds the layer's INT8 weight into a **single
reused scratch buffer** and lets cuBLAS run the GEMM, followed by a fused
scale/bias/cast kernel. Peak VRAM grows by the largest single layer rather than
by the model, and no layer is ever held expanded across calls. Everything else
uses the fused nibble-decoding tensor-core tile as before. Both paths accumulate
exactly in INT32 and share the same epilogue, so they agree bit-for-bit.

Measured on an RTX 4080 against a 5376x3584 layer, versus the fused tile alone:

| Activation rows | Fused tile | Reconstruct + cuBLAS | vs resident INT8 |
| --- | --- | --- | --- |
| 17 | 0.260 ms | 0.178 ms | 1.24x |
| 512 | 1.188 ms | 0.339 ms | 1.15x |
| 4096 | 9.928 ms | 1.934 ms | 1.04x |

Replaying 32 real Krea layers through the scheduler, the combined effect of the
reconstruct path, the staging worker, and both residency tiers was 5.2x at 128
activation rows and 6.8x at 4096. The two halves cover different regimes: the
reconstruct path dominates when rows are plentiful, residency dominates when
they are not. Reproduce either with:

```
python scripts/bench_split_nibble_kernel.py
python scripts/bench_split_nibble_pipeline.py --low <path to *_low.safetensors> --rows 4096
```

The fused CUDA tile reconstructs each INT8 value from its two packed nibbles in
shared memory immediately before tensor-core accumulation. It never constructs
a complete INT8 layer in VRAM, and now writes FP16 as well as BF16/FP32 output
directly. This matters for the Krea and Klein text encoders, which Comfy runs in
FP16 on the test system.

Warm local RTX 4080 measurements with identical prompt tensors were:

| Encoder | Synchronous | Async pipeline | Measured H-to-D hidden |
| --- | ---: | ---: | ---: |
| Krea 2 balanced | 0.249 s | 0.151 s | 81.2% |
| Klein 8B balanced | 0.812 s | 0.729 s | 99.3% |

Complete tiny-latent denoiser forwards also learned stable schedules and
returned bit-identical output across passes: Krea covered 263 calls and hid
75.1% of transfer, while Klein covered 121 calls and hid 64.1%. Their staging
rings used 2 x 108 MiB and 2 x 72 MiB respectively with a 128 MiB limit. These
micro-forward timings are diagnostic rather than generation-speed claims;
actual concealment varies with resolution, token count, PCIe bandwidth, and
free VRAM. The first forward is deliberately synchronous while its order is
recorded, so benchmark subsequent sampling steps or repeated encodes.

Both conversions are also available directly in ComfyUI as output nodes:

- **Umi Split-Nibble Model Converter** converts supported diffusion-model
  `.safetensors` files. Architecture auto-detection covers Anima, Krea 2,
  Flux2 Klein, and MiniMax H3; native Comfy INT8 inputs are repacked exactly.
- **Umi Anima Split-Nibble CLIP Converter** exposes the balanced and maximum
  compression text-encoder profiles.
- **Umi Krea 2 Split-Nibble CLIP Converter** and **Umi Klein Split-Nibble CLIP
  Converter** expose family-specific balanced and maximum-compression profiles.

Converters preserve the source, refuse to overwrite an existing pair, check
free disk space, and run in an isolated process so temporary conversion memory
is returned to the operating system. After conversion, refresh Comfy's node
widgets and select the returned core/low names in the matching loader.

### Umi Anima INT8 ConvRot Converter (Anima/edit overlay)

Quantizes a floating Anima checkpoint into a **single** native ComfyUI
`int8_tensorwise` file with ConvRot, rather than a split-nibble pair. Each
eligible linear becomes three keys — an `int8` weight, a `float32` per-channel
`weight_scale`, and a `comfy_quant` config — which is exactly the layout
ComfyUI's own quantized `state_dict` writes. Because ComfyUI switches to
quantized ops as soon as it sees any `.comfy_quant` key under the model prefix,
the result loads through the stock **Load Diffusion Model** node with no custom
loader and runs on the fused INT8 path.

Use this when the model fits in VRAM; prefer the split-nibble pair only when it
does not and the low plane genuinely has to stream. On `Anima-2.9B-preview-v1`
it quantizes 707 linears (706 with ConvRot at group size 256) and takes the
file from 5.84 GB to 2.96 GB.

Norms, biases, and embeddings pass through untouched **in their original
dtype**. That is deliberate: ComfyUI infers the model's compute dtype from the
tensors that stay unquantized, so promoting or demoting them silently changes
how the whole model executes. The report states the passthrough dtype inventory
and warns if it is mixed.

Wire the delta merger's `output_model` into `source_model_override` to merge
and convert in one graph run instead of refreshing the widget list in between.
Quantizing an already-quantized checkpoint is refused.

## Prompt Language

The Wildcard Processor evaluates prompt text in a seeded, repeatable way. See
`SYNTAX.md` for a compact syntax reference. The essentials are below.

### Wildcards

Pick one line from `wildcards/pose.txt`:

```text
__pose__
```

Use a fallback when a wildcard is missing:

```text
__pose|standing confidently__
```

Pick a seeded range of values:

```text
__1-3$$accessories__
```

Use a sequential stream:

```text
__~pose__
```

Insert an entire prompt file:

```text
__@scene_intro__
```

YAML/tag logic is supported with boolean expressions:

```text
__[soft AND light]__
__lighting[dramatic OR backlit]__
```

### Inline Choices

```text
{red dress|blue dress|black armor}
```

### Variables

Variables are assigned with `$name=value` and reused with `$name`.

```text
$hair={red|blue|silver}, $hair hair, portrait
```

Variables can also drive conditionals:

```text
$mood=happy, [if $mood==happy: smiling | neutral expression]
```

### Conditionals

```text
[if $weather==rain: wet hair elif $weather==snow: winter coat else: sunny day]
```

Boolean logic supports `AND`, `OR`, `NOT`, `XOR`, and grouped expressions.

### Negative Prompt Extraction

Any of these remove text from the positive prompt and add it to the negative
output:

```text
portrait [neg: blurry, bad hands]
portrait **watermark** **text**
portrait --neg: "jpeg artifacts, low quality"
[negative]worst quality, bad anatomy[/negative]
[neg_if:$style==photo]cartoon shading[/neg_if]
```

### Prompt Functions

Bracket functions are processed before final cleanup:

```text
[clean: masterpiece,, best quality,  detailed]
[shuffle: red, blue, green]
[choose: red|blue|green]
[sample 2-3 from: hat|gloves|boots|scarf]
[preset:studio lighting]
[preset:anima clean negative | include=negative]
[anima:1girl, solo, @artist_name | style=clean lineart]
[anima_order:solo, 1girl, blue hair | prefix=true]
```

Validation helpers are also available:

```text
[require:$character | character]
[assert:$mode==portrait | expected portrait mode]
[forbid:$rating==safe | explicit, nude]
[prefer:$scene==night | moonlight, rim light]
```

### LoRAs

Standard LoRA syntax:

```text
<lora:style_model.safetensors:0.8>
```

The processor can load the LoRA when `model` and `clip` are connected. Trigger
tags can be appended, prepended, or disabled with `lora_tags_behavior`.

Disable trigger injection for one LoRA:

```text
<lora:style_model.safetensors:0.8 trigger=off>
```

LoRA aliases can be declared in `wildcards/aliases.yaml`:

```yaml
loras:
  hero: real_hero.safetensors
```

Then used as:

```text
<lora:hero:0.8>
```

### Sections

Sections let you write prompts in named blocks and reorder them from the node:

```text
[section:quality] masterpiece, best quality
[section:character] 1girl, silver hair
[section:scene] moonlit garden
```

Set `section_order` to:

```text
quality, character, scene
```

### Embedded Settings

Width and height can be embedded in the prompt:

```text
portrait @@width=832,height=1216@@
```

These override the node's width and height outputs and are removed from the
final prompt.

## Editable Files

### `wildcards/`

Text wildcards are plain `.txt` files. Each non-empty line is a candidate.
Subfolders can be used when folder paths are enabled in settings.

### `wildcards/aliases.yaml`

Optional alias file for wildcard and LoRA names.

Example:

```yaml
wildcards:
  pose: poses/standing
loras:
  hero: real_hero.safetensors
```

### `wildcards/globals.yaml`

Optional global variables available to every prompt. Keys may be written with
or without the `$` prefix:

```yaml
$hair: silver
mood: calm
```

Use them in prompts as `$hair` or in conditionals as `[if $mood==calm: ...]`.
Inline assignments in a prompt override globals for that run.

### `prompt_presets.yaml`

Named reusable prompt fragments.

```yaml
studio lighting:
  prompt: "soft studio lighting, clean background"
  negative: ""
  description: "Controlled lighting for character work."
```

### `prompt_profiles.yaml`

Model-family defaults and lint rules.

```yaml
SDXL:
  positive: ["high quality", "detailed", "sharp focus"]
  negative: ["low quality", "blurry", "jpeg artifacts"]
  min_words: 16
  style: "prose_or_tags"
  description: "General SDXL-friendly defaults."
```

### `umi_settings.json`

Runtime settings:

```json
{
  "use_folder_paths": false,
  "csv_namespace": true,
  "yaml_namespace": true,
  "rng_streams": false,
  "auto_clean": true,
  "error_lint": false,
  "lint_cleaner_enabled": false,
  "enable_tag_autocomplete": true,
  "enable_debug_output": false,
  "persist_prompt_history": false,
  "persist_run_inspector": false
}
```

Most users should leave these at their defaults. Use the settings panel or edit
the file while ComfyUI is stopped. Prompt history and the last run-inspector
trace are not written to disk unless their individual persistence settings are
enabled.

## Sidebar And Browser Tools

Core registers these frontend tools:

- Settings: view, update, or reset Umi settings.
- Wildcards: list, preview, refresh, read, and edit wildcard text files.
- Run Inspector: read the most recent Umi processing trace. Its disk-backed
  endpoint is disabled until `persist_run_inspector` is enabled.
- Tag Autocomplete: serves tags from CSV files in `autocomplete-tags/` when
  enabled.

The UI-tools overlay adds:

- Danbooru Browser: search posts by tag, select tags, save to wildcards, copy
  tags, inject tags into a selected Umi prompt node, or open the Series
  Character Importer.
- Series Character Importer: search AniList anime or manga, fetch a
  popularity-sorted cast, filter by gender, role, AniList favourites, and
  Danbooru post count, review canonical tag matches, optionally verify
  Danbooru character variants, and write or refresh wildcard files. Flat and
  grouped variant output are supported; grouped output uses nested wildcard
  files so every base character keeps one slot in the parent wildcard.
- LoRA Browser: scan LoRAs, inspect tags, save overrides, upload previews, and
  fetch Civitai metadata when available.
- Image Browser: scan output images and search Umi prompt metadata.

The LoRA preview route accepts image/video media only. It does not serve model
weights or arbitrary files under ComfyUI's LoRA directories.

Network-backed features such as AniList, Danbooru, and Civitai require working
internet access from the ComfyUI environment. The Series Character Importer
uses the bundled `autocomplete-tags/` database for normal character matching;
only AniList cast retrieval and optional Danbooru implication verification are
live requests. Previous imports are recorded in `cache/series_imports/` so
manual matches and output options can be refreshed later.

## Recommended First Workflow

1. Add `UmiAI Wildcard Processor`.
2. Put your prompt in `text`.
3. Connect `text` output to your positive text encode node.
4. Connect `negative_text` output to your negative text encode node.
5. Connect `width` and `height` outputs to generation nodes that accept them.
6. If using inline LoRAs, connect model and clip through the Umi node.
7. Save with `Umi Save Image (with metadata)`.
8. Use `Umi Prompt Syntax Lint` while building complex prompts.

Example:

```text
[section:quality] masterpiece, best quality
[section:character] $hair={silver|blue|pink}, 1girl, $hair hair
[section:scene] __background|simple studio background__
[preset:studio lighting]
[neg: blurry, bad hands, watermark]
@@width=832,height=1216@@
```

With `section_order` set to `quality, character, scene`, this becomes a clean,
seeded prompt with dimensions and negative text separated for the workflow.

## Troubleshooting

### Nodes Do Not Appear

Restart ComfyUI after installing requirements. Check the console for import
errors. Core needs `pyyaml`; `requests` and `curl_cffi` are needed only by the
UI-tools overlay. C-UMI logs and skips an overlay whose core API range is
incompatible with the installed core.

### Wildcard Is Not Found

Check that the file exists under `wildcards/`, that the name matches the prompt,
and that the extension is `.txt`, `.yaml`, `.yml`, or `.csv` where appropriate.
Use fallback syntax while building shared prompts:

```text
__missing_name|fallback text__
```

### Random Choices Are Not Changing

Change the node seed. UmiAI is intentionally seeded so results are repeatable.

### Inline LoRAs Are Not Loading

Connect `model` and `clip` through the Wildcard Processor. Use `dry_run` to
verify which LoRAs would be loaded. Confirm the LoRA filename or alias exists in
ComfyUI's LoRA paths.

### Negative Text Stays In The Positive Prompt

Run `Umi Prompt Syntax Lint` and check for unclosed brackets or quotes. For
complex negatives, prefer block syntax:

```text
[negative]
worst quality, low quality, bad anatomy
[/negative]
```

### Browser Panels Do Not Refresh

Confirm that the UI-tools overlay and `requirements-ui-tools.txt` dependencies
are installed, use the panel refresh action, then reload the ComfyUI page. If
network searches fail, confirm that the ComfyUI Python environment has internet
access.

## Removed From This Lean Build

Older experimental or personal workflow pieces are intentionally not part of
this release-facing build, including legacy camera, pose, character, emotion,
dataset, local LLM, older full-node, TIPO, obsolete manager panels, the legacy
Anima model-merge tools superseded by the 2.9B delta merger, and bundled example
workflows. Existing workflows that
depended on those older nodes should be migrated to the active nodes listed in
this manual.
