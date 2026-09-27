import datetime
import json
import os
import re
import tempfile

import folder_paths


DEFAULT_UMI_SETTINGS = {
    "use_folder_paths": False,
    "csv_namespace": True,
    "yaml_namespace": True,
    "rng_streams": False,
    "auto_clean": True,
    "preserve_newlines": False,
    "max_expansion_iterations": 50,
    "max_expanded_prompt_chars": 1_000_000,
    "error_lint": False,
    # Live syntax errors in the prompt editor. On by default: the highlighting
    # is finished and a mistyped wildcard otherwise reaches the output as
    # [WILDCARD_NOT_FOUND: name] with no warning while typing.
    "lint_cleaner_enabled": True,
    "enable_tag_autocomplete": True,
    "enable_debug_output": False,
    # Prompt text can be sensitive. Distribution defaults never persist it
    # unless the user explicitly opts in.
    "persist_prompt_history": False,
    "persist_run_inspector": False,
}


PROCESSING_LIMITS = {
    'max_expansion_iterations': (1, 200),
    'max_expanded_prompt_chars': (1000, 10_000_000),
}
BOOLEAN_SETTINGS = tuple(key for key, value in DEFAULT_UMI_SETTINGS.items() if isinstance(value, bool))


def validate_processing_settings(settings):
    for key, (minimum, maximum) in PROCESSING_LIMITS.items():
        if key not in settings:
            continue
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f'{key} must be an integer from {minimum:,} to {maximum:,}.')
    for key in BOOLEAN_SETTINGS:
        if key in settings and not isinstance(settings[key], bool):
            raise ValueError(f'{key} must be true or false.')


def load_umi_settings():
    """Load user settings from umi_settings.json."""
    settings_path = os.path.join(os.path.dirname(__file__), "umi_settings.json")
    defaults = dict(DEFAULT_UMI_SETTINGS)

    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
            for key in (*PROCESSING_LIMITS, *BOOLEAN_SETTINGS):
                if key in user_settings:
                    try:
                        validate_processing_settings({key: user_settings[key]})
                    except ValueError as exc:
                        print(f"[UmiAI] {exc} Using the default.")
                        user_settings.pop(key)
            defaults.update({k: v for k, v in user_settings.items() if k in defaults})
        except Exception as e:
            print(f"[UmiAI] Warning: Could not load umi_settings.json: {e}")

    return defaults


UMI_SETTINGS = load_umi_settings()


def umi_debug_print(*args, **kwargs):
    if UMI_SETTINGS.get("enable_debug_output", False):
        print(*args, **kwargs)


def _metadata_disabled():
    """True when ComfyUI was started with --disable-metadata."""
    try:
        from comfy.cli_args import args
    except Exception:
        return False
    return bool(getattr(args, "disable_metadata", False))


def _add_text_chunk(metadata, key, value):
    """Write a PNG text chunk, returning the chunk type actually used.

    tEXt holds Latin-1 only. Pillow silently falls back to iTXt for anything
    outside that range -- Japanese tags, smart quotes, em dashes, emoji -- and
    while ComfyUI decodes iTXt, many third-party PNG-info readers do not. The
    choice is made explicit here so the fallback can be reported instead of
    turning into a silent "metadata is missing" report.
    """
    try:
        value.encode("latin-1")
    except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
        metadata.add_itxt(key, value, zip=False)
        return "iTXt"
    metadata.add_text(key, value)
    return "tEXt"


_TOKEN_RE = re.compile(r"%([^%]+)%")
_DATE_PART_RE = re.compile(r"dd?|MM?|hh?|mm?|ss?|yyy?y?")


def _format_filename_date(pattern, now):
    """Mirror of the frontend's formatDate: dd/d day, MM/M month, hh/h hour on
    a 24-hour clock, mm/m minute, ss/s second, plus yyyy and yy. Anything else,
    including a bare y and yyy, is left exactly as written."""
    getters = {
        "d": lambda t: t.day,
        "M": lambda t: t.month,
        "h": lambda t: t.hour,
        "m": lambda t: t.minute,
        "s": lambda t: t.second,
    }

    def replace(match):
        token = match.group(0)
        if token == "yy":
            return str(now.year)[2:]
        if token == "yyyy":
            return str(now.year)
        getter = getters.get(token[0])
        return token if getter is None else str(getter(now)).zfill(len(token))

    return _DATE_PART_RE.sub(replace, pattern)


def _lookup_prompt_widget(prompt, node_name, widget_name):
    if not isinstance(prompt, dict):
        return None
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        title = (node.get("_meta") or {}).get("title")
        if node_name not in (title, node.get("class_type")):
            continue
        value = (node.get("inputs") or {}).get(widget_name)
        # A connected input serialises as [node_id, slot]; only a literal
        # widget value can go into a filename.
        if isinstance(value, (str, int, float, bool)):
            return value
    return None


def apply_filename_tokens(filename_prefix, prompt=None):
    """Expand %date:...% and %Node Title.widget% in a save-path prefix.

    ComfyUI resolves these in the frontend, but only for a hardcoded allowlist
    of core save nodes (SaveImage, SaveVideo, SaveAudio and friends). A custom
    node is not on that list, so it receives the raw text and would try to
    create a directory literally named '%date:ddMM%_anima'.

    The rules match the frontend's applyTextReplacements exactly, including the
    quirk that a token containing a dot is read as Node.widget rather than as a
    date format -- so '%date:yyyy.MM.dd%' is left alone here just as it is by a
    core SaveImage. Unrecognised tokens are passed through untouched so that
    folder_paths.get_save_image_path can still expand %width%, %height%,
    %year% and the rest.
    """
    text = str(filename_prefix or "")
    if "%" not in text:
        return text
    now = datetime.datetime.now()

    def replace(match):
        parts = match.group(1).split(".")
        if len(parts) != 2:
            if parts[0].startswith("date:"):
                return _format_filename_date(parts[0][len("date:"):], now)
            return match.group(0)
        value = _lookup_prompt_widget(prompt, parts[0], parts[1])
        return match.group(0) if value is None else str(value)

    return _TOKEN_RE.sub(replace, text)


class UmiSaveImage:
    """Save images with Umi prompt metadata embedded for the Image Browser."""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "Umi", "tooltip": "PNG name and optional subfolder, relative to ComfyUI's output folder. Example: portraits/Umi. A counter is added automatically; %batch_num% selects the batch index."}),
            },
            "optional": {
                "positive_prompt": ("STRING", {"forceInput": True, "multiline": True, "tooltip": "Connect the Wildcard Processor's text output to embed the resolved prompt as searchable PNG metadata."}),
                "negative_prompt": ("STRING", {"forceInput": True, "multiline": True, "tooltip": "Connect negative_text to embed the resolved negative prompt."}),
                "input_prompt": ("STRING", {"forceInput": True, "multiline": True, "tooltip": "Optional original template, before wildcard expansion. Connect input_text to preserve it alongside the resolved prompt."}),
                "input_negative": ("STRING", {"forceInput": True, "multiline": True, "tooltip": "Optional original negative template. Metadata is omitted when ComfyUI starts with --disable-metadata."}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "UmiAI"

    def save_images(
        self,
        images,
        filename_prefix="Umi",
        positive_prompt="",
        negative_prompt="",
        input_prompt="",
        input_negative="",
        prompt=None,
        extra_pnginfo=None,
    ):
        import numpy as np
        from PIL import Image, PngImagePlugin

        if images is None or len(images) == 0:
            print("[UmiAI] Umi Save Image received an empty image batch; nothing was saved.")
            return {"ui": {"images": []}}

        umi_fields = (
            ("umi_prompt", positive_prompt),
            ("umi_negative", negative_prompt),
            ("umi_input_prompt", input_prompt),
            ("umi_input_negative", input_negative),
        )
        # These four are forceInput sockets, so they stay empty until the user
        # wires them. An unwired node writes a PNG with no Umi metadata and the
        # Image Browser shows nothing, which reads as "metadata is broken".
        metadata_warnings = []
        if not any(value for _, value in umi_fields):
            print(
                "[UmiAI] Umi Save Image: no prompt text connected, so no Umi metadata "
                "was written. Connect the Wildcard Processor's 'text' output to "
                "positive_prompt (and 'negative_text' to negative_prompt) to embed it."
            )
            metadata_warnings.append(
                "No Umi prompt is connected; the image will not contain searchable Umi prompt metadata."
            )

        skip_metadata = _metadata_disabled()
        if skip_metadata:
            umi_debug_print("[UmiAI] --disable-metadata is set; saving images without metadata.")
            metadata_warnings.append(
                "ComfyUI metadata is disabled (--disable-metadata); no prompt or workflow metadata was embedded."
            )

        filename_prefix = apply_filename_tokens(filename_prefix, prompt)
        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )

        results = []
        fallback_keys = []
        for batch_number, image in enumerate(images):
            i = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            metadata = None
            if not skip_metadata:
                metadata = PngImagePlugin.PngInfo()
                written = set()

                for key, value in umi_fields:
                    if not value:
                        continue
                    if _add_text_chunk(metadata, key, value) == "iTXt":
                        fallback_keys.append(key)
                    written.add(key)

                if prompt is not None:
                    _add_text_chunk(metadata, "prompt", json.dumps(prompt))
                    written.add("prompt")
                if extra_pnginfo is not None:
                    for key, value in extra_pnginfo.items():
                        # ComfyUI puts "prompt" in extra_pnginfo too; adding it
                        # again would write a duplicate chunk.
                        if key in written:
                            continue
                        _add_text_chunk(metadata, key, json.dumps(value))
                        written.add(key)

            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
            file = f"{filename_with_batch_num}_{counter:05}_.png"
            destination = os.path.join(full_output_folder, file)
            temp_handle = tempfile.NamedTemporaryFile(
                prefix=".umi-save-", suffix=".png.tmp", dir=full_output_folder, delete=False
            )
            temp_path = temp_handle.name
            temp_handle.close()
            try:
                img.save(
                    temp_path,
                    format="PNG",
                    pnginfo=metadata,
                    compress_level=self.compress_level,
                )
                os.replace(temp_path, destination)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1

        if fallback_keys:
            print(
                "[UmiAI] Umi Save Image: %s stored as iTXt because the text is not "
                "Latin-1 (non-ASCII tags, smart quotes, em dashes or emoji). ComfyUI "
                "reads this fine; some third-party PNG-info viewers only read tEXt."
                % ", ".join(sorted(set(fallback_keys)))
            )

        # Hand the resolved text back to the frontend so the node can show the
        # prompt under its own output, and the history panel can record the run.
        ui = {"images": results}
        shown = positive_prompt or input_prompt or ""
        if shown or negative_prompt or input_negative:
            ui["umi_prompt"] = [shown]
            ui["umi_negative"] = [negative_prompt or input_negative or ""]
        if metadata_warnings:
            ui["umi_metadata_warning"] = [" ".join(metadata_warnings)]
        return {"ui": ui}
