# Modular C-UMI Packaging

C-UMI is distributed as one core archive and five optional overlay archives.
All archives use the same top-level `C-UMI` directory. Install the core first,
then extract any optional archives into `ComfyUI/custom_nodes`; allow matching
folders to merge and restart ComfyUI.

## Upgrading over an existing install

Extracting merges folders; it never removes a file. A file that was dropped
from a bundle therefore stays behind, still loaded, still doing whatever it
did. Delete these by hand when upgrading:

- `js/theme_manager.js` -- retired. It was a second theme system that wrote
  inline colours over the shared design tokens, so panels ignored the ComfyUI
  theme they now follow. **Umi Control Panel -> Self Check** reports it if a
  copy is still loaded.

Archive names include the version from `version.py`, for example
`C-UMI-0.5.0-core.zip`. Overlay sidecar manifests declare a supported core API
range. Core validates that range before importing an overlay, so a mismatched
overlay is reported and skipped without preventing core startup.

## Bundles

- `C-UMI-<version>-core.zip`: wildcard and LoRA prompt processing, prompt
  presets and profiles, linting and inspection, metadata saving, bypass nodes,
  core settings/wildcard frontend, autocomplete data, and two example
  wildcards. Packaged settings disable prompt-history and run-inspector disk
  persistence by default.
- `C-UMI-<version>-krea.zip`: Krea 2 Prompt Architect, Prompt Generator, Keyword Forge,
  style DNA, workflows, and semantic-novelty support. The optional 127 MiB BGE
  model is intentionally not embedded; run
  `scripts/download_semantic_novelty_model.py` after installation to add it.
- `C-UMI-<version>-anima_edit.zip`: Anima Prompt Helper, cohesive wildcard
  extension, CNS sampler, architecture-aware Anima-2.9B delta merger, Subject
  Lock Mask, Skin Tone Reconcile, and the Anima example workflow.
- `C-UMI-<version>-klein_edit.zip`: FLUX.2 Klein edit prompt compilation,
  ordered reference conditioning, precision masks, exact compositing, and the
  Klein 9B precision-edit workflow.
- `C-UMI-<version>-memory.zip`: native MiniMax H3 T=1 image editing, memory
  preflight, H3 memory patch/autopilot, the complete split-nibble runtime,
  converters, kernels, scripts, and technical documentation.
- `C-UMI-<version>-ui_tools.zip`: LoRA, image, Danbooru, and series browser
  panels and routes. Install `requirements-ui-tools.txt` for `requests` and
  `curl_cffi`. This overlay is also what enables LoRA preview/media routes.

Optional overlays are detected by their `optional_*.py` registration modules.
Their absence is normal and does not produce an import warning. An installed
overlay that fails because of a missing or incompatible dependency is skipped,
logged as a warning, and does not prevent the prompt-engine core from loading.

## Building release archives

Run from the C-UMI directory with the Python used by ComfyUI:

```powershell
<comfy-python> scripts\build_distributions.py
```

Archives and `SHA256SUMS.txt` are written to `dist/`. Build selected bundles by
passing their names, for example:

```powershell
<comfy-python> scripts\build_distributions.py core krea
```

The file lists live in `packaging/bundles.json`. Runtime caches, personal
wildcards, local models, prompt history, Civitai data, and the repository archive
are excluded from releases unless explicitly added to that manifest.
