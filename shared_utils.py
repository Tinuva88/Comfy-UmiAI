"""
Shared utility functions used by both Full and Lite Umi nodes.
This module contains common functions to avoid code duplication.
"""

import os
import json
import random
import re
import yaml
import hashlib
import difflib
from datetime import datetime
import time
import folder_paths

from .prompt_extensions import get_anima_extension

try:
    from .prompt_parser import find_negative_spans, parse_conditional_specs, parse_function_specs, parse_lora_specs, parse_wildcard_specs, remove_spans, split_escaped_csv
except Exception:
    from prompt_parser import find_negative_spans, parse_conditional_specs, parse_function_specs, parse_lora_specs, parse_wildcard_specs, remove_spans, split_escaped_csv

# ==============================================================================
# CONSTANTS
# ==============================================================================
ANIMA_BASE_POSITIVE_PREFIX = ("masterpiece", "best quality", "score_7")
ANIMA_BASE_NEGATIVE_DEFAULT = (
    "worst quality", "low quality", "score_1", "score_2", "score_3",
    "artist name", "blurry", "jpeg artifacts", "chromatic aberration",
)
ANIMA_AESTHETIC_POSITIVE_PREFIX = ("masterpiece", "best quality")
ANIMA_AESTHETIC_NEGATIVE_DEFAULT = (
    "worst quality", "low quality", "artist name", "blurry",
    "jpeg artifacts", "chromatic aberration",
)
ANIMA_TURBO_POSITIVE_PREFIX = ANIMA_BASE_POSITIVE_PREFIX
ANIMA_TURBO_NEGATIVE_DEFAULT = ANIMA_BASE_NEGATIVE_DEFAULT

# Compatibility names used by existing workflows and third-party imports.
ANIMA_POSITIVE_PREFIX = ANIMA_BASE_POSITIVE_PREFIX
ANIMA_NEGATIVE_DEFAULT = ANIMA_BASE_NEGATIVE_DEFAULT
ANIMA_PROFILE_DEFAULTS = {
    "base": (ANIMA_BASE_POSITIVE_PREFIX, ANIMA_BASE_NEGATIVE_DEFAULT),
    "aesthetic": (ANIMA_AESTHETIC_POSITIVE_PREFIX, ANIMA_AESTHETIC_NEGATIVE_DEFAULT),
    "turbo": (ANIMA_TURBO_POSITIVE_PREFIX, ANIMA_TURBO_NEGATIVE_DEFAULT),
}
ANIMA_SAFETY_TAGS = {"safe", "sensitive", "nsfw", "explicit"}
ANIMA_SUBJECT_RE = re.compile(r"^(?:[1-9]\d*)?(?:girl|boy|other|person|people|woman|man|female|male)s?$")
ANIMA_SCORE_RE = re.compile(r"^score_[1-9]$")
ANIMA_YEAR_RE = re.compile(r"^year\s+\d{4}$")
ANIMA_META_TAGS = {
    "highres", "absurdres", "anime screenshot", "jpeg artifacts", "official art",
    "newest", "recent", "mid", "early", "old", "masterpiece", "best quality",
    "good quality", "normal quality", "low quality", "worst quality",
}
ANIMA_STYLE_PRESETS = {
    "anime illustration": ("anime illustration", "clean lineart", "vibrant colors"),
    "clean lineart": ("clean lineart", "sharp lines", "flat colors"),
    "painterly": ("digital painting", "painterly", "soft brushwork"),
    "official art": ("official art", "polished illustration", "highres"),
    "flat color": ("flat colors", "simple shading", "clean lineart"),
    "high detail": ("highly detailed", "detailed background", "polished illustration"),
}
BASE_DIR = os.path.dirname(__file__)
PROMPT_PRESETS_PATH = os.path.join(BASE_DIR, "prompt_presets.yaml")
PROMPT_PROFILES_PATH = os.path.join(BASE_DIR, "prompt_profiles.yaml")

DEFAULT_PROMPT_PRESETS = {
    "anime portrait base": {
        "prompt": "1girl, solo, upper body, looking at viewer, detailed eyes",
        "negative": "worst quality, low quality, bad anatomy",
        "description": "Simple character portrait scaffold.",
    },
    "studio lighting": {
        "prompt": "soft studio lighting, clean background, balanced composition",
        "negative": "",
        "description": "Quiet controlled lighting for character work.",
    },
    "background detail": {
        "prompt": "detailed background, environmental storytelling, coherent perspective",
        "negative": "empty background, inconsistent perspective",
        "description": "Adds scene richness without picking a specific location.",
    },
}
DEFAULT_PROMPT_PROFILES = {
    "None": {
        "positive": (),
        "negative": (),
        "min_words": 3,
        "style": "generic",
        "description": "No model-specific defaults.",
    },
    "Illustrious": {
        "positive": ("masterpiece", "best quality", "very aesthetic", "absurdres"),
        "negative": ("worst quality", "low quality", "bad anatomy", "bad hands", "text", "watermark"),
        "min_words": 10,
        "style": "anime_tags",
        "description": "Anime tag model profile with quality and artifact defaults.",
    },
    "Pony": {
        "positive": ("score_9", "score_8_up", "score_7_up", "source_anime"),
        "negative": ("score_4", "score_3", "score_2", "score_1", "bad anatomy", "bad hands"),
        "min_words": 10,
        "style": "anime_tags",
        "description": "Pony-style score/source tag defaults.",
    },
    "SDXL": {
        "positive": ("high quality", "detailed", "sharp focus"),
        "negative": ("low quality", "blurry", "jpeg artifacts", "distorted", "bad anatomy"),
        "min_words": 16,
        "style": "prose_or_tags",
        "description": "General SDXL-friendly quality and clarity defaults.",
    },
    "Flux": {
        "positive": (),
        "negative": (),
        "min_words": 24,
        "style": "prose",
        "description": "Flux-style descriptive prose guidance without forced quality soup.",
    },
}
# ==============================================================================
# GLOBAL CACHES
# ==============================================================================
ALIAS_CACHE = {}

# ==============================================================================
# DEBUG PRINTING HELPER (loads settings lazily to avoid circular imports)
# ==============================================================================
_DEBUG_SETTINGS_CACHE = {'loaded': False, 'enabled': False}

def _debug_print(*args, **kwargs):
    """
    Conditionally print debug messages based on enable_debug_output setting.
    Lazily loads settings to avoid circular import issues.
    """
    if not _DEBUG_SETTINGS_CACHE['loaded']:
        try:
            settings_path = os.path.join(os.path.dirname(__file__), "umi_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8-sig') as f:
                    settings = json.load(f)
                    _DEBUG_SETTINGS_CACHE['enabled'] = settings.get('enable_debug_output', False)
            _DEBUG_SETTINGS_CACHE['loaded'] = True
        except Exception:
            _DEBUG_SETTINGS_CACHE['loaded'] = True  # Mark as loaded even on error
    
    if _DEBUG_SETTINGS_CACHE['enabled']:
        print(*args, **kwargs)


def strip_prompt_comments(text):
    """
    Strip prompt comments while preserving // toggle rules and inline # comments.
    - // toggles comment mode until next // or end of line
    - # comments are stripped when preceded by a space (' #')
    """
    if not text:
        return ""

    protected_text = text.replace('__#', '___UMI_HASH_PROTECT___').replace('<#', '<___UMI_HASH_PROTECT___')

    def _strip_double_slash_comments(line):
        i = 0
        in_comment = False
        out = []
        while i < len(line):
            if line[i] == '/' and i + 1 < len(line) and line[i + 1] == '/':
                in_comment = not in_comment
                i += 2
                continue
            if in_comment:
                i += 1
                continue
            out.append(line[i])
            i += 1
        return "".join(out)

    clean_lines = []
    for line in protected_text.splitlines():
        line = _strip_double_slash_comments(line)
        # A line that starts with '#' is a comment in full. This used to be
        # excluded from stripping entirely, so whole-line comments survived
        # into the prompt.
        if line.strip().startswith("#"):
            continue
        if '#' in line:
            if ' #' in line:
                line = line.split(' #')[0]
        line = line.strip()
        if line:
            clean_lines.append(line)

    cleaned = "\n".join(clean_lines)
    return cleaned.replace('___UMI_HASH_PROTECT___', '#').replace('<___UMI_HASH_PROTECT___', '<#')


def _split_prompt_tags(text):
    if not text:
        return []

    parts = []
    current = []
    quote = None
    angle_depth = 0
    paren_depth = 0

    for char in str(text):
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            continue
        if char == '<':
            angle_depth += 1
        elif char == '>' and angle_depth:
            angle_depth -= 1
        elif char == '(':
            paren_depth += 1
        elif char == ')' and paren_depth:
            paren_depth -= 1
        if char == ',' and angle_depth == 0 and paren_depth == 0:
            item = "".join(current).strip()
            if item:
                parts.append(item)
            current = []
            continue
        current.append(char)

    item = "".join(current).strip()
    if item:
        parts.append(item)
    return parts


def _normalize_anima_tag(tag):
    tag = re.sub(r'\s+', ' ', str(tag).strip())
    if not tag:
        return ""
    if tag.startswith("<") or tag.startswith("@") or "__" in tag:
        return tag
    if ANIMA_SCORE_RE.match(tag):
        return tag
    return tag.replace("_", " ")


def _dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _looks_like_character(tag):
    words = tag.split()
    if not words or len(words) > 4:
        return False
    if tag.startswith("@") or ANIMA_SUBJECT_RE.match(tag) or tag in ANIMA_META_TAGS or tag in ANIMA_SAFETY_TAGS:
        return False
    return any(word[:1].isupper() for word in words)


def _looks_like_series(tag):
    lowered = tag.lower()
    series_markers = (" no ", " of ", " yuri", "frieren", "project", "impact", "chronicles", "academy")
    return any(marker in lowered for marker in series_markers)


def order_anima_prompt(text, style_preset="none", add_prefix=False, positive_prefix=None):
    tags = [_normalize_anima_tag(tag) for tag in _split_prompt_tags(text)]
    tags = [tag for tag in tags if tag]

    quality_meta = []
    subjects = []
    characters = []
    series = []
    artists = []
    general = []

    for tag in tags:
        lowered = tag.lower()
        if tag.startswith("@"):
            artists.append(tag)
        elif lowered in ANIMA_META_TAGS or lowered in ANIMA_SAFETY_TAGS or ANIMA_SCORE_RE.match(lowered) or ANIMA_YEAR_RE.match(lowered):
            quality_meta.append(lowered)
        elif ANIMA_SUBJECT_RE.match(lowered):
            subjects.append(lowered)
        elif _looks_like_character(tag):
            characters.append(tag)
        elif _looks_like_series(tag):
            series.append(tag)
        else:
            general.append(lowered if tag == tag.lower() else tag)

    if style_preset and style_preset.lower() not in ("none", "off", "false", "0"):
        general.extend(ANIMA_STYLE_PRESETS.get(style_preset.lower(), (style_preset,)))

    ordered = []
    if add_prefix:
        ordered.extend(positive_prefix or ANIMA_POSITIVE_PREFIX)
    ordered.extend(quality_meta)
    ordered.extend(subjects)
    ordered.extend(characters)
    ordered.extend(series)
    ordered.extend(artists)
    ordered.extend(general)
    return ", ".join(_dedupe_keep_order(ordered))


def lint_anima_prompt(text, negative_text="", variant="base"):
    variant_key = str(variant or "base").strip().lower()
    _, negative_defaults = ANIMA_PROFILE_DEFAULTS.get(
        variant_key, ANIMA_PROFILE_DEFAULTS["base"]
    )
    tags = [_normalize_anima_tag(tag).lower() for tag in _split_prompt_tags(text)]
    tag_set = set(tags)
    warnings = []

    if not tag_set.intersection(ANIMA_SAFETY_TAGS):
        warnings.append("Anima: add a safety tag such as safe, sensitive, nsfw, or explicit.")
    if (
        variant_key != "aesthetic"
        and not ({"masterpiece", "best quality"} & tag_set)
        and not any(ANIMA_SCORE_RE.match(tag) for tag in tag_set)
    ):
        warnings.append("Anima: add quality guidance such as masterpiece, best quality, or score_7.")
    if len([tag for tag in tags if tag]) < 6 and len(str(text).split()) < 18:
        warnings.append("Anima: short prompts can be unstable; add subject, appearance, style, and composition details.")
    if re.search(r"(^|,\s*)(?!@)[a-z0-9 ]+\s+artist(\s*,|$)", str(text), re.IGNORECASE):
        warnings.append("Anima: artist names should be prefixed with @.")
    if re.search(r"\b(realistic|photorealistic|photo|dslr|cinematic photo)\b", str(text), re.IGNORECASE):
        warnings.append("Anima: the base model is illustration/anime focused and does not do realism well.")

    neg_tags = {_normalize_anima_tag(tag).lower() for tag in _split_prompt_tags(negative_text)}
    if negative_text and not neg_tags.intersection(set(negative_defaults)):
        warnings.append("Anima: negative prompt should include low-quality/low-score negatives.")
    if variant_key == "aesthetic" and (
        any(ANIMA_SCORE_RE.match(tag) for tag in tag_set)
        or any(ANIMA_SCORE_RE.match(tag) for tag in neg_tags)
    ):
        warnings.append(
            "Anima Aesthetic: score_* tags are usually unnecessary and can overcook the image."
        )
    return warnings


def apply_anima_profile(
    text,
    negative_text="",
    mode="profile",
    style_preset="none",
    variant="base",
):
    variant_key = str(variant or "base").strip().lower()
    positive_prefix, negative_defaults = ANIMA_PROFILE_DEFAULTS.get(
        variant_key, ANIMA_PROFILE_DEFAULTS["base"]
    )
    mode_key = str(mode or "profile").strip().lower()
    add_prefix = mode_key in ("profile", "base", "full", "prefix")
    prompt = order_anima_prompt(
        text,
        style_preset=style_preset,
        add_prefix=add_prefix,
        positive_prefix=positive_prefix,
    )
    negative = negative_text or ""
    if mode_key in ("profile", "base", "full", "negative"):
        existing = _split_prompt_tags(negative)
        negative = ", ".join(_dedupe_keep_order(list(negative_defaults) + existing))
    return prompt, negative, lint_anima_prompt(prompt, negative, variant=variant_key)


def _coerce_text_list(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in split_escaped_csv(value) if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _load_yaml_mapping(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _debug_print(f"[UmiAI] Failed loading prompt config {path}: {e}")
        return {}


def _normalize_prompt_presets(data):
    normalized = {}
    for name, preset in (data or {}).items():
        if not isinstance(preset, dict):
            continue
        clean_name = str(name).strip().lower()
        if not clean_name:
            continue
        normalized[clean_name] = {
            "prompt": str(preset.get("prompt", "") or ""),
            "negative": str(preset.get("negative", "") or ""),
            "description": str(preset.get("description", "") or ""),
        }
    return normalized


def _normalize_prompt_profiles(data):
    normalized = {}
    for name, profile in (data or {}).items():
        if not isinstance(profile, dict):
            continue
        clean_name = str(name).strip()
        if not clean_name:
            continue
        normalized[clean_name] = {
            "positive": _coerce_text_list(profile.get("positive")),
            "negative": _coerce_text_list(profile.get("negative")),
            "min_words": int(profile.get("min_words", 8) or 8),
            "style": str(profile.get("style", "generic") or "generic"),
            "description": str(profile.get("description", "") or ""),
        }
    return normalized


def load_prompt_presets():
    presets = _normalize_prompt_presets(DEFAULT_PROMPT_PRESETS)
    anima_extension = get_anima_extension()
    if anima_extension is not None:
        presets.update(_normalize_prompt_presets(anima_extension.prompt_presets))
    configured = _normalize_prompt_presets(_load_yaml_mapping(PROMPT_PRESETS_PATH))
    if anima_extension is None:
        configured.pop("anima clean negative", None)
        configured.pop("anima clean lineart", None)
    presets.update(configured)
    return presets


def load_prompt_profiles():
    profiles = _normalize_prompt_profiles(DEFAULT_PROMPT_PROFILES)
    anima_extension = get_anima_extension()
    if anima_extension is not None:
        profiles.update(_normalize_prompt_profiles(anima_extension.prompt_profiles))
    configured = _normalize_prompt_profiles(_load_yaml_mapping(PROMPT_PROFILES_PATH))
    if anima_extension is None:
        for anima_profile in ("Anima Base", "Anima Aesthetic", "Anima Turbo"):
            configured.pop(anima_profile, None)
    profiles.update(configured)
    if "None" not in profiles:
        profiles["None"] = _normalize_prompt_profiles({"None": DEFAULT_PROMPT_PROFILES["None"]})["None"]
    return profiles


def list_prompt_profiles():
    return list(load_prompt_profiles().keys())


def get_prompt_profile(name):
    requested = str(name or "None").strip().lower()
    profiles = load_prompt_profiles()
    for profile_name, profile in profiles.items():
        if profile_name.lower() == requested:
            return profile_name, profile
    return "None", profiles["None"]


def apply_named_prompt_profile(profile_name, prompt, negative_text="", style_preset="none"):
    resolved_name, profile = get_prompt_profile(profile_name)
    if resolved_name in ("Anima Base", "Anima Aesthetic", "Anima Turbo"):
        anima_extension = get_anima_extension()
        if anima_extension is not None:
            variant = resolved_name.removeprefix("Anima ").lower()
            return (*anima_extension.apply_profile(
                prompt,
                negative_text,
                mode="profile",
                style_preset=style_preset,
                variant=variant,
            ), resolved_name)
    if resolved_name == "None":
        return prompt, negative_text or "", lint_prompt_profile(resolved_name, prompt, negative_text), resolved_name

    positive = list(profile.get("positive", ()))
    negative_defaults = list(profile.get("negative", ()))
    prompt_parts = _split_prompt_tags(prompt)
    negative_parts = _split_prompt_tags(negative_text)
    merged_prompt = ", ".join(_dedupe_keep_order(positive + prompt_parts))
    merged_negative = ", ".join(_dedupe_keep_order(negative_defaults + negative_parts))
    warnings = lint_prompt_profile(resolved_name, merged_prompt, merged_negative)
    return merged_prompt, merged_negative, warnings, resolved_name


def expand_anima_natural_language(text):
    prompt = str(text or "").strip()
    if not prompt:
        return ""
    sentence_count = len(re.findall(r'[.!?](?:\s|$)', prompt))
    if sentence_count >= 2 or len(prompt.split()) >= 28:
        return prompt
    return (
        f"{prompt}. Describe the subject's core appearance, outfit, pose, expression, "
        "composition, background, lighting, and illustration style with clear visual details."
    )


ANIMA_COHESION_HINTS = {
    "subject": (
        "character", "subject", "person", "girl", "boy", "woman", "man",
        "species", "creature", "animal", "body", "face", "hair", "eyes",
        "age", "ethnicity", "attire", "outfit", "clothing", "costume",
        "accessor", "appearance",
    ),
    "action": (
        "pose", "action", "gesture", "expression", "emotion", "movement",
        "interaction",
    ),
    "setting": (
        "background", "setting", "scene", "location", "environment",
        "landscape", "interior", "architecture", "weather", "time",
    ),
    "composition": (
        "composition", "camera", "framing", "angle", "shot", "view",
        "perspective", "lens", "focal",
    ),
    "lighting": (
        "lighting", "light", "palette", "color", "colour", "atmosphere",
        "fog", "glow", "shadow",
    ),
    "style": (
        "style", "medium", "render", "aesthetic", "technique", "lineart",
        "illustration", "painting", "artist",
    ),
}


def _is_anima_artist_fragment(value):
    text = str(value or "").strip()
    if not text:
        return False
    return bool(re.search(r"(^|::|\()\s*@[^\s,()]+", text))


def split_anima_artist_chain(text, remove=False):
    """Extract artist tokens in the syntax accepted by Anima Artist Mixer."""

    artists = []
    retained = []
    for part in _split_prompt_tags(text):
        clean = _normalize_anima_tag(part)
        if _is_anima_artist_fragment(clean):
            artists.append(clean)
            if not remove:
                retained.append(clean)
        else:
            retained.append(clean)
    return ", ".join(_dedupe_keep_order(retained)), ", ".join(
        _dedupe_keep_order(artists)
    )


def _anima_cohesion_category(value, hint=""):
    normalized_hint = str(hint or "").lower().replace("_", " ")
    combined = str(value or "").lower().replace("_", " ")
    for category, markers in ANIMA_COHESION_HINTS.items():
        if normalized_hint and any(marker in normalized_hint for marker in markers):
            return category

    if re.search(
        r"\b(standing|sitting|kneeling|running|walking|flying|looking|holding|"
        r"smiling|crying|fighting|reaching|leaning|lying)\b",
        combined,
    ):
        return "action"
    if re.search(
        r"\b(forest|city|street|room|beach|mountain|sky|space|garden|temple|"
        r"castle|school|ocean|indoors|outdoors|background)\b",
        combined,
    ):
        return "setting"
    if re.search(
        r"\b(close[- ]?up|portrait|full body|upper body|wide shot|low angle|"
        r"high angle|from (?:above|below|behind)|depth of field)\b",
        combined,
    ):
        return "composition"
    if re.search(
        r"\b(anime|illustration|painting|watercolor|oil paint|lineart|"
        r"cel shading|sketch|manga|comic|3d render|pixel art)\b",
        combined,
    ):
        return "style"
    if re.search(
        r"\b(rim light|backlight|sunlight|moonlight|neon|chiaroscuro|"
        r"golden hour|soft light|dramatic light|pastel|monochrome)\b",
        combined,
    ):
        return "lighting"
    return "subject"


def _anima_trace_hints(wildcard_trace):
    hints = {}
    for record in wildcard_trace or ():
        if not isinstance(record, dict) or record.get("type") != "wildcard":
            continue
        hint = str(record.get("wildcard", "") or "")
        values = record.get("values")
        if not isinstance(values, (list, tuple)):
            values = [record.get("result", "")]
        for value in values:
            for part in _split_prompt_tags(value):
                key = _normalize_anima_tag(part).lower()
                if key:
                    hints.setdefault(key, hint)
    return hints


def compose_anima_wildcard_prompt(
    text,
    wildcard_trace=None,
    mode="off",
    artist_mode="keep in prompt",
):
    """Turn resolved wildcard fragments into an ordered or cohesive Anima prompt.

    This composer is intentionally deterministic. It uses wildcard source names as
    semantic hints and does not require a second generative text model.
    """

    mode_key = str(mode or "off").strip().lower()
    split_artists = str(artist_mode or "").strip().lower().startswith("split")
    if mode_key in ("off", "none", "disabled"):
        prompt, artist_chain = split_anima_artist_chain(text, remove=split_artists)
        return prompt, artist_chain, {
            "mode": "off",
            "artist_mode": artist_mode,
            "categories": {},
        }

    trace_hints = _anima_trace_hints(wildcard_trace)
    meta = []
    protected = []
    artists = []
    categories = {
        "subject": [],
        "action": [],
        "setting": [],
        "composition": [],
        "lighting": [],
        "style": [],
    }

    for raw_part in _split_prompt_tags(text):
        part = _normalize_anima_tag(raw_part)
        if not part:
            continue
        lowered = part.lower()

        if _is_anima_artist_fragment(part):
            artists.append(part)
            if not split_artists:
                categories["style"].append(part)
            continue
        if part.startswith("<") or "@@" in part:
            protected.append(part)
            continue
        if (
            lowered in ANIMA_META_TAGS
            or lowered in ANIMA_SAFETY_TAGS
            or ANIMA_SCORE_RE.match(lowered)
            or ANIMA_YEAR_RE.match(lowered)
            or lowered in ("masterpiece", "best quality", "high quality")
        ):
            meta.append(lowered)
            continue

        hint = trace_hints.get(lowered, "")
        category = _anima_cohesion_category(part, hint)
        categories[category].append(part)

    meta = _dedupe_keep_order(meta)
    protected = _dedupe_keep_order(protected)
    artists = _dedupe_keep_order(artists)
    categories = {
        key: _dedupe_keep_order(values) for key, values in categories.items()
    }

    if mode_key in ("ordered", "ordered tags", "anima ordered tags"):
        ordered_parts = (
            meta
            + categories["subject"]
            + categories["action"]
            + categories["setting"]
            + categories["composition"]
            + categories["lighting"]
            + categories["style"]
            + protected
        )
        prompt = ", ".join(_dedupe_keep_order(ordered_parts))
    else:
        sentences = []
        if meta:
            sentences.append(", ".join(meta).rstrip(".") + ".")

        subject = categories["subject"]
        action = categories["action"]
        if subject:
            sentence = "Depict " + ", ".join(subject)
            if action:
                sentence += ", " + ", ".join(action)
            sentences.append(sentence.rstrip(".") + ".")
        elif action:
            sentences.append("Show " + ", ".join(action).rstrip(".") + ".")

        if categories["setting"]:
            sentences.append(
                "Place the scene in "
                + ", ".join(categories["setting"]).rstrip(".")
                + "."
            )
        if categories["composition"]:
            sentences.append(
                "Frame it with "
                + ", ".join(categories["composition"]).rstrip(".")
                + "."
            )
        if categories["lighting"]:
            sentences.append(
                "Use "
                + ", ".join(categories["lighting"]).rstrip(".")
                + "."
            )
        if categories["style"]:
            sentences.append(
                "Render it with "
                + ", ".join(categories["style"]).rstrip(".")
                + "."
            )

        prompt = " ".join(sentences).strip()
        if protected:
            prompt = " ".join(
                part for part in (prompt, ", ".join(protected)) if part
            )
        if not prompt:
            prompt = str(text or "").strip()

    return prompt, ", ".join(artists), {
        "mode": "ordered tags" if mode_key in (
            "ordered", "ordered tags", "anima ordered tags"
        ) else "cohesive prompt",
        "artist_mode": "split for artist mixer" if split_artists else "keep in prompt",
        "artists": artists,
        "categories": categories,
        "meta": meta,
        "protected": protected,
    }


def list_prompt_presets():
    return sorted(load_prompt_presets().keys())


def get_prompt_preset(name):
    key = str(name or "").strip().lower()
    return load_prompt_presets().get(key)


def apply_prompt_preset(prompt, negative_text="", preset_name="none", placement="append"):
    preset = get_prompt_preset(preset_name)
    if not preset:
        return prompt, negative_text, []

    preset_prompt = preset.get("prompt", "").strip()
    preset_negative = preset.get("negative", "").strip()
    placement_key = str(placement or "append").strip().lower()

    prompt_parts = [str(prompt or "").strip()]
    if preset_prompt:
        if placement_key == "prepend":
            prompt_parts = [preset_prompt] + prompt_parts
        elif placement_key == "replace":
            prompt_parts = [preset_prompt]
        else:
            prompt_parts.append(preset_prompt)

    negative_parts = [str(negative_text or "").strip()]
    if preset_negative:
        negative_parts.append(preset_negative)

    merged_prompt = ", ".join(part for part in prompt_parts if part)
    merged_negative = ", ".join(part for part in negative_parts if part)
    return merged_prompt, merged_negative, [f"Preset applied: {preset_name}"]


def resolve_preset_directive(content):
    """Resolve the body of a [preset:name | include=...] directive to text."""
    content = str(content or "").strip()
    name = content
    opts = {}
    if "|" in content:
        parts = [part.strip() for part in content.split("|")]
        name = parts[0]
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                opts[key.strip().lower()] = value.strip()
    preset = get_prompt_preset(name)
    if not preset:
        return f"[PRESET_NOT_FOUND: {name}]"
    include = opts.get("include", "prompt").lower()
    if include in ("negative", "neg"):
        return preset.get("negative", "")
    if include == "both":
        prompt = preset.get("prompt", "")
        negative = preset.get("negative", "")
        return ", ".join(part for part in (prompt, f"**{negative}**" if negative else "") if part)
    return preset.get("prompt", "")


def expand_prompt_presets(text):
    return re.sub(
        r'\[preset:([^\]]+)\]',
        lambda match: resolve_preset_directive(match.group(1)),
        str(text or ""),
        flags=re.IGNORECASE,
    )


def lint_prompt_profile(profile, prompt, negative_text="", lora_info=""):
    profile_key = str(profile or "None").strip().lower()
    warnings = []
    if profile_key in ("anima base", "anima aesthetic", "anima turbo"):
        variant = profile_key.removeprefix("anima ")
        warnings.extend(lint_anima_prompt(prompt, negative_text, variant=variant))
    elif profile_key in ("none", ""):
        if len(str(prompt or "").strip()) < 12:
            warnings.append("Prompt is very short; consider adding subject, composition, and style details.")
    else:
        resolved_name, profile_data = get_prompt_profile(profile)
        tag_set = {tag.lower() for tag in _split_prompt_tags(prompt)}
        neg_set = {tag.lower() for tag in _split_prompt_tags(negative_text)}
        expected_positive = {tag.lower() for tag in profile_data.get("positive", ())}
        expected_negative = {tag.lower() for tag in profile_data.get("negative", ())}
        if expected_positive and not tag_set.intersection(expected_positive):
            warnings.append(f"{resolved_name}: consider adding profile quality/source tags.")
        if expected_negative and negative_text and not neg_set.intersection(expected_negative):
            warnings.append(f"{resolved_name}: negative prompt may be missing profile negatives.")
        min_words = int(profile_data.get("min_words", 8))
        if len(str(prompt or "").split()) < min_words and len(_split_prompt_tags(prompt)) < 6:
            warnings.append(f"{resolved_name}: prompt is short; add subject, composition, style, and scene details.")
        if profile_data.get("style") == "prose" and "," in str(prompt or "") and len(str(prompt or "").split(".")) <= 1:
            warnings.append(f"{resolved_name}: this profile tends to work better with descriptive sentences than pure tag lists.")
    if "<lora:" in str(prompt or "").lower() and not lora_info:
        warnings.append("LoRA tags were present but no LoRA info was produced; check filenames or loading mode.")
    return _dedupe_keep_order(warnings)


def extract_prompt_sections(text):
    sections = {}
    order = []
    remainder = []
    pattern = re.compile(r'^\s*\[section:([^\]]+)\]\s*(.*)$', re.IGNORECASE)

    for line in str(text or "").splitlines():
        match = pattern.match(line)
        if not match:
            remainder.append(line)
            continue
        name = match.group(1).strip().lower()
        body = match.group(2).strip()
        if name not in sections:
            sections[name] = []
            order.append(name)
        if body:
            sections[name].append(body)

    return {
        "sections": {name: "\n".join(parts).strip() for name, parts in sections.items()},
        "order": order,
        "remainder": "\n".join(remainder).strip(),
    }


def apply_prompt_sections(text, order=None):
    parsed = extract_prompt_sections(text)
    sections = parsed["sections"]
    if not sections:
        return text, parsed

    requested = []
    if order:
        requested = [name.strip().lower() for name in str(order).split(",") if name.strip()]

    section_order = []
    for name in requested:
        if name in sections and name not in section_order:
            section_order.append(name)
    for name in parsed["order"]:
        if name not in section_order:
            section_order.append(name)

    parts = []
    if parsed["remainder"]:
        parts.append(parsed["remainder"])
    for name in section_order:
        if sections.get(name):
            parts.append(sections[name])
    return "\n".join(part for part in parts if part).strip(), parsed


def build_prompt_diff(before, after):
    before_parts = _split_prompt_tags(before)
    after_parts = _split_prompt_tags(after)
    before_set = {item.lower() for item in before_parts}
    after_set = {item.lower() for item in after_parts}
    added = [item for item in after_parts if item.lower() not in before_set]
    removed = [item for item in before_parts if item.lower() not in after_set]
    changed = str(before or "").strip() != str(after or "").strip()
    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "input_length": len(str(before or "")),
        "output_length": len(str(after or "")),
    }


def lint_prompt_join_boundaries(prompt):
    """Catch likely wildcard/helper joins such as '__pose__in-universe_location'."""
    warnings = []
    text = str(prompt or "")
    text = re.sub(r'\[(?:neg|negative)\]', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\[neg_if:[^\]]+\]', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\[section:[^\]]+\]', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/\s*(?:neg|negative|neg_if|section)\]', ' ', text, flags=re.IGNORECASE)
    patterns = [
        (r"__[A-Za-z0-9_./-]+__[A-Za-z0-9_-]", "wildcard followed by text without comma/space"),
        (r"__[^\r\n_,]+____\s*[A-Za-z0-9]", "wildcard has an extra '__' before following text"),
        (r"@@[A-Za-z0-9_.:-]+@@[A-Za-z0-9_-]", "character helper followed by text without comma/space"),
        # ``]__`` is the normal close of a filtered wildcard such as
        # ``__pose[calm]__``; it is not an inline-helper/text join.
        (r"\](?!__)(?!\s*\[/?(?:neg|negative|neg_if|section)\b)[A-Za-z0-9_-]", "inline helper followed by text without comma/space"),
    ]
    for pattern, message in patterns:
        match = re.search(pattern, text)
        if match:
            warnings.append(f"Possible joined prompt token: {message} near '{match.group(0)}'.")
    return warnings


def _lint_balanced_delimiters(text):
    errors = []
    pairs = {"[": "]", "{": "}", "(": ")"}
    stack = []
    escape = False
    for idx, ch in enumerate(str(text or "")):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch in pairs:
            stack.append((ch, idx))
            continue
        if ch in pairs.values():
            if not stack or pairs[stack[-1][0]] != ch:
                errors.append(f"Unmatched '{ch}' at character {idx}.")
                continue
            stack.pop()
    for ch, idx in stack:
        errors.append(f"Unclosed '{ch}' at character {idx}.")
    return errors


WILDCARD_FILE_EXTENSIONS = ('.txt', '.yaml', '.yml', '.csv')


def scan_wildcard_files(wildcard_paths):
    """(root, relative_path, mtime_ns, size) for every wildcard file, in os.walk
    order; a missing root is (root, "missing") and an unstatable file
    (root, relative_path, "missing").

    DirEntry.stat() is served from the directory listing on Windows, so this
    avoids one stat call per file; on a 5,000-file collection that is about
    20x faster than os.walk plus os.stat. Symlinked folders are not entered,
    as with os.walk.
    """
    signature = []

    def scan(directory, prefix, root):
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            return
        subdirs = []
        for entry in entries:
            try:
                is_dir = entry.is_dir() and not entry.is_symlink()
            except OSError:
                is_dir = False
            if is_dir:
                subdirs.append(entry)
            elif entry.name.endswith(WILDCARD_FILE_EXTENSIONS):
                try:
                    stat = entry.stat()
                    signature.append((root, prefix + entry.name, stat.st_mtime_ns, stat.st_size))
                except OSError:
                    signature.append((root, prefix + entry.name, "missing"))
        for entry in subdirs:
            scan(entry.path, prefix + entry.name + '/', root)

    for wildcard_path in wildcard_paths or ():
        root = os.path.abspath(wildcard_path)
        if not os.path.exists(wildcard_path):
            signature.append((root, "missing"))
            continue
        scan(wildcard_path, '', root)
    return tuple(signature)


def _wildcard_file_catalog(wildcard_paths):
    """Index wildcard names once for linting without parsing file contents."""
    catalog = {}
    for item in scan_wildcard_files(wildcard_paths):
        if len(item) == 2:
            continue
        relative, extension = os.path.splitext(item[1])
        # Match TagLoader's path-first-or-basename behavior. Earlier
        # wildcard roots keep precedence when names collide.
        catalog.setdefault(relative.lower(), (relative, extension))
        catalog.setdefault(relative.rsplit("/", 1)[-1].lower(), (relative, extension))
    return catalog


def lint_prompt_syntax(prompt, negative_text="", profile="None", wildcard_paths=None):
    """Return structured prompt syntax warnings without expanding randomness."""
    text = str(prompt or "")
    errors = []
    warnings = []
    notes = []
    missing_wildcards = []
    wildcard_specs = parse_wildcard_specs(text)

    errors.extend(_lint_balanced_delimiters(text))

    if text.count("__") % 2:
        errors.append("Wildcard marker '__' appears to be unclosed.")
    if text.count("<lora:") > text.count(">"):
        errors.append("LoRA tag appears to be missing a closing '>'.")
    if text.count("@@") % 2:
        errors.append("Settings/helper marker '@@' appears to be unclosed.")

    for spec in wildcard_specs:
        if spec.kind in ("simple", "range", "file_logic", "prompt_file") and not spec.key:
            errors.append("Wildcard has an empty name.")
        if spec.kind == "range":
            if spec.count_min > spec.count_max:
                errors.append(f"Wildcard range for '{spec.key}' has min greater than max.")
            if spec.count_max > 25:
                warnings.append(f"Wildcard range for '{spec.key}' may create a very long prompt.")
        if spec.kind in ("yaml_logic", "file_logic") and not spec.logic:
            errors.append("Wildcard logic filter is empty.")

    if wildcard_paths is not None:
        catalog = _wildcard_file_catalog(wildcard_paths)
        aliases = load_aliases_from_paths(wildcard_paths).get("wildcards", {})
        suggestions = sorted({display for display, _ in catalog.values()}, key=str.lower)
        for spec in wildcard_specs:
            if spec.kind not in ("simple", "range", "file_logic", "prompt_file") or not spec.key:
                continue
            requested = spec.key.strip().replace("\\", "/").strip("/")
            if requested.lower().endswith(".txt"):
                requested = requested[:-4]
            resolved = str(aliases.get(requested.lower(), requested)).replace("\\", "/").strip("/")
            match = catalog.get(resolved.lower())
            if match and (spec.kind != "prompt_file" or match[1] == ".txt"):
                continue

            missing_wildcards.append(spec.key)
            if spec.fallback:
                notes.append(f"Wildcard '{spec.key}' was not found; its fallback will be used.")
                continue
            close = difflib.get_close_matches(resolved, suggestions, n=1, cutoff=0.55)
            suggestion = f" Did you mean '{close[0]}'?" if close else ""
            kind = "Prompt file" if spec.kind == "prompt_file" else "Wildcard"
            warnings.append(f"{kind} '{spec.key}' was not found.{suggestion}")

    for spec in parse_lora_specs(text):
        if spec.strength < -5.0 or spec.strength > 5.0:
            warnings.append(f"LoRA strength for '{spec.name}' will be clamped to [-5.0, 5.0].")
        trigger_option = spec.options.get("trigger") or spec.options.get("triggers")
        if trigger_option and trigger_option not in ("on", "off", "true", "false", "0", "1"):
            warnings.append(f"LoRA trigger option for '{spec.name}' is unusual: {trigger_option}.")

    for spec in parse_conditional_specs(text):
        if not spec.branches and not spec.else_text:
            errors.append("Conditional block has no branches.")

    warnings.extend(lint_prompt_join_boundaries(text))
    warnings.extend(lint_prompt_profile(profile, text, negative_text))

    if "[PRESET_NOT_FOUND:" in text:
        warnings.append("Prompt contains a missing preset marker.")
    if text.strip() != text:
        notes.append("Prompt has leading or trailing whitespace.")

    errors = _dedupe_keep_order(errors)
    warnings = _dedupe_keep_order(warnings)
    notes = _dedupe_keep_order(notes)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
        "counts": {
            "wildcards": len(wildcard_specs),
            "missing_wildcards": len(set(missing_wildcards)),
            "loras": len(parse_lora_specs(text)),
            "conditionals": len(parse_conditional_specs(text)),
            "negative_spans": len(find_negative_spans(text)),
        },
    }


def expand_prompt_files(text, tag_loader, max_depth=5):
    """Expand __@prompt__ file references without other wildcard processing."""
    if not text:
        return ""

    expanded = text

    for _ in range(max_depth):
        prompt_file_specs = [spec for spec in parse_wildcard_specs(expanded) if spec.kind == "prompt_file"]
        if not prompt_file_specs:
            break
        spec = prompt_file_specs[0]

        filename = spec.key
        try:
            content = tag_loader.load_prompt_file(filename)
        except (OSError, ValueError, UnicodeError) as e:
            content = spec.fallback or f"[PROMPT_FILE_ERROR: {filename}: {e}]"
        if not content:
            content = spec.fallback or f"[PROMPT_FILE_NOT_FOUND: {filename}]"

        start = spec.span.start
        end = spec.span.end
        before = expanded[start - 1] if start > 0 else ""
        after = expanded[end] if end < len(expanded) else ""

        if content:
            if before and before != "\n":
                content = "\n" + content
            if after and after != "\n":
                content = content + "\n"

        expanded = expanded[:start] + content + expanded[end:]

    return expanded


def _lock_path_for(target_path):
    return f"{target_path}.lock"


def _acquire_lock(lock_path, timeout=5.0, poll=0.05):
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return fd
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError(f"Timeout waiting for lock: {lock_path}")
            time.sleep(poll)


def _release_lock(lock_path, fd):
    try:
        os.close(fd)
    finally:
        try:
            os.unlink(lock_path)
        except OSError:
            pass


class _FileLock:
    def __init__(self, target_path, timeout=5.0, poll=0.05):
        self.lock_path = _lock_path_for(target_path)
        self.timeout = timeout
        self.poll = poll
        self.fd = None

    def __enter__(self):
        self.fd = _acquire_lock(self.lock_path, self.timeout, self.poll)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            _release_lock(self.lock_path, self.fd)
        return False


def _atomic_write_json(path, data, indent=2, ensure_ascii=False, default=None):
    """Atomically replace `path` with the JSON serialization of `data`.

    Writes to a unique temp file in the same directory, fsyncs it, then
    os.replace()s it over the target so readers never observe a truncated or
    half-written file. On failure the original file is left untouched and the
    temp file is removed."""
    directory = os.path.dirname(path) or "."
    base = os.path.basename(path)
    tmp_name = f".{base}.tmp.{os.getpid()}.{random.randint(0, 999999)}"
    tmp_path = os.path.join(directory, tmp_name)
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii, default=default)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default


def _normalize_aliases(data):
    wildcards = {}
    loras = {}

    if not isinstance(data, dict):
        return {'wildcards': wildcards, 'loras': loras}

    if 'wildcards' in data or 'loras' in data:
        wild_map = data.get('wildcards', {})
        lora_map = data.get('loras', {})
    else:
        wild_map = data
        lora_map = {}

    if isinstance(wild_map, dict):
        for k, v in wild_map.items():
            if isinstance(v, str):
                wildcards[str(k).strip().lower()] = v.strip()

    if isinstance(lora_map, dict):
        for k, v in lora_map.items():
            if isinstance(v, str):
                loras[str(k).strip().lower()] = v.strip()

    return {'wildcards': wildcards, 'loras': loras}


def load_aliases_from_paths(paths):
    combined = {'wildcards': {}, 'loras': {}}
    for path in paths:
        alias_path = os.path.join(path, 'aliases.yaml')
        if not os.path.exists(alias_path):
            continue
        try:
            mtime = os.path.getmtime(alias_path)
        except OSError:
            continue

        cached = ALIAS_CACHE.get(alias_path)
        if cached and cached.get('mtime') == mtime:
            data = cached.get('data', {})
        else:
            try:
                with open(alias_path, 'r', encoding='utf-8-sig') as f:
                    raw = yaml.safe_load(f) or {}
            except Exception:
                raw = {}
            data = _normalize_aliases(raw)
            ALIAS_CACHE[alias_path] = {'mtime': mtime, 'data': data}

        combined['wildcards'].update(data.get('wildcards', {}))
        combined['loras'].update(data.get('loras', {}))

    return combined


def resolve_lora_alias(name, wildcard_paths):
    if not name:
        return name
    aliases = load_aliases_from_paths(wildcard_paths)
    return aliases.get('loras', {}).get(str(name).strip().lower(), name)


def parse_wildcard_weight(line):
    """
    Parse a wildcard file line to extract value and tags.
    
    Format: "text::tag1,tag2" or just "text"
    Weight parsing via colon has been removed to avoid conflicts with entries like "show:1988"
    
    Returns:
        dict: {'value': str, 'weight': float, 'tags': list}
    """
    value = line
    weight = 1.0  # Weight is always 1.0 now (feature removed)
    tags = []

    # Check for tags (using :: separator only - unambiguous)
    if '::' in line:
        parts = line.split('::', 1)
        value = parts[0].strip()
        remainder = parts[1].strip()
        # Parse tags from remainder
        tags = [t.strip() for t in remainder.split(',') if t.strip()]

    return {
        'value': value,
        'weight': weight,
        'tags': tags
    }


def get_all_wildcard_paths():
    """
    Get all wildcard search paths.
    Returns list of directories to search for wildcard files.
    """
    paths = []

    def add_path(path):
        if not path or not os.path.exists(path):
            return
        normalized = os.path.abspath(path)
        if normalized not in paths:
            paths.append(normalized)

    # Prefer user/configured wildcard roots over bundled defaults when names collide.
    try:
        ext_paths = folder_paths.get_folder_paths("wildcards")
        if ext_paths:
            for p in ext_paths:
                add_path(p)
    except:
        pass

    # Root wildcards path
    add_path(os.path.join(folder_paths.base_path, "wildcards"))

    # Models wildcards path
    add_path(os.path.join(folder_paths.models_dir, "wildcards"))

    # Bundled extension wildcards are a fallback.
    add_path(os.path.join(os.path.dirname(__file__), "wildcards"))

    return paths


def log_prompt_to_history(prompt, negative="", seed=None):
    """
    Log a prompt to history file for tracking generations.

    Args:
        prompt (str): The positive prompt
        negative (str): The negative prompt
        seed (int): The seed used for generation
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        history_file = os.path.join(current_dir, "prompt_history.json")

        with _FileLock(history_file):
            history = _read_json_file(history_file, [])
            entry = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "negative": negative,
                "seed": seed
            }
            history.append(entry)
            history = history[-100:]
            _atomic_write_json(history_file, history)
    except Exception as e:
        _debug_print(f"[UmiAI] Warning: Could not log prompt to history: {e}")


def parse_wildcard_range(range_str, num_variants):
    """Parse range syntax like '2-5' or '3'"""
    if range_str is None:
        return 1, 1

    if "-" in range_str:
        parts = range_str.split("-")
        if len(parts) == 2:
            start = int(parts[0]) if parts[0] else 1
            end = int(parts[1]) if parts[1] else num_variants
            return min(start, end), max(start, end)

    try:
        val = int(range_str)
        return val, val
    except:
        return 1, 1


# ==============================================================================
# LOGIC EVALUATOR
# ==============================================================================
class LogicEvaluator:
    """
    Evaluates boolean logic expressions against a context dictionary.
    Supports: AND, OR, NOT, XOR, NAND, NOR operators (word and symbolic forms)
    Also supports variable comparisons ($var==value) and boolean checks ($var)
    """
    def __init__(self, expression, variables=None):
        self.expression = self._normalize_expression(expression.strip())
        self.variables = variables or {}

    def _strip_line_comments(self, expr):
        if not expr:
            return expr

        result = []
        i = 0
        in_quote = False
        quote_char = ""
        in_comment = False
        while i < len(expr):
            char = expr[i]
            if in_comment:
                if char == '\n':
                    in_comment = False
                    result.append(char)
                    i += 1
                    continue
                if char == '/' and i + 1 < len(expr) and expr[i + 1] == '/':
                    in_comment = False
                    i += 2
                    continue
                i += 1
                continue
            if in_quote:
                result.append(char)
                if char == quote_char:
                    in_quote = False
                    quote_char = ""
                i += 1
                continue

            if char in ('"', "'"):
                in_quote = True
                quote_char = char
                result.append(char)
                i += 1
                continue

            if char == '/' and i + 1 < len(expr) and expr[i + 1] == '/':
                in_comment = True
                i += 2
                continue

            result.append(char)
            i += 1

        return "".join(result)

    def _normalize_expression(self, expr):
        if not expr:
            return expr

        expr = self._strip_line_comments(expr)

        # Normalize single '=' to '==' outside of quotes.
        result = []
        in_quote = False
        quote_char = ""
        i = 0
        while i < len(expr):
            char = expr[i]
            if char in ('"', "'"):
                if in_quote and char == quote_char:
                    in_quote = False
                    quote_char = ""
                elif not in_quote:
                    in_quote = True
                    quote_char = char
                result.append(char)
                i += 1
                continue

            if not in_quote and char == '=':
                prev_char = expr[i - 1] if i > 0 else ""
                next_char = expr[i + 1] if i + 1 < len(expr) else ""
                if prev_char not in ('!', '=') and next_char != '=':
                    result.append('==')
                else:
                    result.append(char)
                i += 1
                continue

            result.append(char)
            i += 1

        normalized = "".join(result)
        # Remove spaces around comparison operators for tokenization stability
        normalized = re.sub(r'\s*(==|!=)\s*', r'\1', normalized)
        return normalized

    def _strip_quotes(self, value):
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            return value[1:-1]
        return value

    def evaluate(self, context):
        tokens = self.tokenize(self.expression)
        postfix = self.to_postfix(tokens)
        return self.evaluate_postfix(postfix, context)

    def tokenize(self, expr):
        tokens = []
        current = ""
        i = 0
        in_quote = False
        quote_char = ""
        
        def is_word_boundary(pos):
            """Check if position is at a word boundary (start, end, space, or paren)"""
            if pos < 0 or pos >= len(expr):
                return True
            return expr[pos] in ' \t\n()'
        
        while i < len(expr):
            char = expr[i]

            if in_quote:
                current += char
                if char == quote_char:
                    in_quote = False
                    quote_char = ""
                i += 1
                continue

            if char in ('"', "'"):
                in_quote = True
                quote_char = char
                current += char
                i += 1
                continue

            if char in '()':
                if current.strip():
                    tokens.append(current.strip())
                    current = ""
                tokens.append(char)
                i += 1
            else:
                # Check for symbolic operators first (these don't need word boundaries)
                if expr[i:i+2] == '&&':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('AND')
                    i += 2
                elif expr[i:i+2] == '||':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('OR')
                    i += 2
                elif char == '!':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NOT')
                    i += 1
                elif char == '^':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('XOR')
                    i += 1
                # Word operators - must be standalone words (preceded and followed by word boundary)
                elif (expr[i:i+4].upper() == 'NAND' and 
                      is_word_boundary(i-1) and is_word_boundary(i+4)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NAND')
                    i += 4
                elif (expr[i:i+3].upper() == 'AND' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('AND')
                    i += 3
                elif (expr[i:i+3].upper() == 'NOT' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NOT')
                    i += 3
                elif (expr[i:i+3].upper() == 'XOR' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('XOR')
                    i += 3
                elif (expr[i:i+3].upper() == 'NOR' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NOR')
                    i += 3
                elif (expr[i:i+2].upper() == 'OR' and 
                      is_word_boundary(i-1) and is_word_boundary(i+2)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('OR')
                    i += 2
                elif (expr[i:i+2].upper() == 'IN' and 
                      is_word_boundary(i-1) and is_word_boundary(i+2)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('IN')
                    i += 2
                elif (expr[i:i+8].upper() == 'CONTAINS' and 
                      is_word_boundary(i-1) and is_word_boundary(i+8)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('CONTAINS')
                    i += 8
                elif (expr[i:i+7].upper() == 'MATCHES' and 
                      is_word_boundary(i-1) and is_word_boundary(i+7)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('MATCHES')
                    i += 7
                elif (expr[i:i+10].upper() == 'STARTSWITH' and 
                      is_word_boundary(i-1) and is_word_boundary(i+10)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('STARTSWITH')
                    i += 10
                elif (expr[i:i+8].upper() == 'ENDSWITH' and 
                      is_word_boundary(i-1) and is_word_boundary(i+8)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('ENDSWITH')
                    i += 8
                else:
                    current += char
                    i += 1

        if current.strip():
            tokens.append(current.strip())

        return tokens

    def to_postfix(self, tokens):
        precedence = {
            'NOT': 3, 'AND': 2, 'NAND': 2, 'XOR': 1, 'OR': 1, 'NOR': 1,
            'IN': 4, 'CONTAINS': 4, 'MATCHES': 4, 'STARTSWITH': 4, 'ENDSWITH': 4
        }
        output = []
        stack = []

        for token in tokens:
            if token in precedence:
                while (stack and stack[-1] != '(' and
                       stack[-1] in precedence and
                       precedence[stack[-1]] >= precedence[token]):
                    output.append(stack.pop())
                stack.append(token)
            elif token == '(':
                stack.append(token)
            elif token == ')':
                while stack and stack[-1] != '(':
                    output.append(stack.pop())
                if stack:
                    stack.pop()
            else:
                output.append(token)

        while stack:
            output.append(stack.pop())

        return output

    def evaluate_postfix(self, postfix, context):
        stack = []

        context_text = None
        if isinstance(context, str):
            context_text = context.lower()

        def _coerce_bool(operand):
            if isinstance(operand, dict):
                kind = operand.get('kind')
                if kind == 'var':
                    val = self.variables.get(operand.get('name', ''), False)
                    return bool(val) and str(val).lower() not in ['false', '0', 'no', '']
                if kind == 'quoted':
                    return bool(operand.get('value', ''))
                if kind == 'bare':
                    token_lower = operand.get('value', '').lower()
                    if context_text is not None:
                        if re.search(r'\s', token_lower):
                            return token_lower in context_text
                        return re.search(r'\b' + re.escape(token_lower) + r'\b', context_text) is not None
                    if isinstance(context, dict):
                        if token_lower in context:
                            return _coerce_bool(context[token_lower])
                        for key, value in context.items():
                            if str(key).lower() == token_lower:
                                return _coerce_bool(value)
                        return False
                    return token_lower in context
                if kind == 'bool':
                    return bool(operand.get('value'))
            return bool(operand)

        def _coerce_str(operand):
            if isinstance(operand, dict):
                kind = operand.get('kind')
                if kind == 'var':
                    return str(self.variables.get(operand.get('name', ''), ''))
                if kind == 'quoted':
                    return str(operand.get('value', ''))
                if kind == 'bare':
                    return str(operand.get('value', ''))
                if kind == 'bool':
                    return str(bool(operand.get('value')))
            return str(operand)

        for token in postfix:
            if token == 'AND':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(a and b)
            elif token == 'OR':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(a or b)
            elif token == 'NOT':
                if len(stack) < 1:
                    return False
                a = _coerce_bool(stack.pop())
                stack.append(not a)
            elif token == 'XOR':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(a != b)
            elif token == 'NAND':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(not (a and b))
            elif token == 'NOR':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(not (a or b))
            elif token == 'IN':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                if ',' in right or '|' in right:
                    parts = [p.strip() for p in re.split(r'[,\|]', right) if p.strip()]
                    stack.append(left in parts)
                else:
                    stack.append(left in right)
            elif token == 'CONTAINS':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                stack.append(right in left)
            elif token == 'MATCHES':
                if len(stack) < 2:
                    return False
                pattern = _coerce_str(stack.pop())
                target = _coerce_str(stack.pop())
                try:
                    stack.append(re.search(pattern, target, re.IGNORECASE) is not None)
                except re.error:
                    stack.append(False)
            elif token == 'STARTSWITH':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                stack.append(left.startswith(right))
            elif token == 'ENDSWITH':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                stack.append(left.endswith(right))
            else:
                # Variable comparison support ($var==value, $var!=value, $var=value)
                if '!=' in token:
                    parts = token.split('!=', 1)
                    left = parts[0].strip()
                    right = self._strip_quotes(parts[1].strip())

                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value != right.lower())
                    else:
                        stack.append(self._strip_quotes(left).lower() != right.lower())
                elif '==' in token:
                    parts = token.split('==', 1)
                    left = parts[0].strip()
                    right = self._strip_quotes(parts[1].strip())

                    # Check if left side is a variable
                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value == right.lower())
                    else:
                        # Regular comparison
                        stack.append(self._strip_quotes(left).lower() == right.lower())
                elif '=' in token:
                    parts = token.split('=', 1)
                    left = parts[0].strip()
                    right = self._strip_quotes(parts[1].strip())

                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value == right.lower())
                    else:
                        stack.append(self._strip_quotes(left).lower() == right.lower())
                elif token.startswith('$'):
                    stack.append({'kind': 'var', 'name': token[1:]})
                elif token.startswith(("'", '"')) and token.endswith(("'", '"')) and len(token) >= 2:
                    stack.append({'kind': 'quoted', 'value': self._strip_quotes(token)})
                else:
                    stack.append({'kind': 'bare', 'value': token})

        if not stack:
            return False
        return _coerce_bool(stack[0])


# ==============================================================================
# DYNAMIC PROMPT REPLACER
# ==============================================================================
class DynamicPromptReplacer:
    """
    Handles dynamic prompt syntax like {option1|option2|option3}
    Supports: random choice, percentage chance, range selection, sequential mode
    """
    def __init__(self, seed):
        self.re_combinations = re.compile(r"(?<!\\)\{([^{}]*)\}")
        self.seed = seed
        self.rng = random.Random(seed)
        self.sync_indices = {}

    def replace_combinations(self, match):
        if not match:
            return ""
        content = match.group(1)
        
        # Sequential mode: ~{opt1|opt2|opt3} picks based on seed
        if content.startswith('~'):
            content = content[1:]
            if '$$' not in content:
                variants = [s.strip() for s in content.split("|")]
                if not variants:
                    return ""
                return variants[self.seed % len(variants)]

        # Enhanced percentage support with new algorithm:
        # {Red|Blue|Yellow|Green} - Equal 25% each (no percentages)
        # {15%Red|15%Blue|15%Yellow|10%Green} - Total 55%, 45% blank chance
        # {35%Red|35%Blue|35%Yellow|35%Green} - Total 140%, normalized to ~25% each
        # {115%Red|25%Blue|Yellow|Green} - Total 140%, Y/G get 0%
        # {75%Red|Blue|Yellow|Green} - 75% R, remaining 25% split among B/Y/G (8.33% each)
        if '%' in content and '$$' not in content:
            parts = content.split('|')
            options = []
            total_explicit_pct = 0
            unassigned_count = 0
            has_percentage = False
            
            for part in parts:
                part = part.strip()
                if '%' in part:
                    # Parse percentage: "25%Red" -> (25, "Red")
                    pct_split = part.split('%', 1)
                    try:
                        pct = float(pct_split[0])
                        text = pct_split[1].strip() if len(pct_split) > 1 else ""
                        options.append({'pct': pct, 'text': text, 'has_pct': True})
                        total_explicit_pct += pct
                        has_percentage = True
                    except ValueError:
                        # Not a valid percentage, treat as regular option
                        options.append({'pct': None, 'text': part, 'has_pct': False})
                        unassigned_count += 1
                else:
                    # No percentage specified
                    options.append({'pct': None, 'text': part, 'has_pct': False})
                    unassigned_count += 1
            
            if has_percentage:
                # Calculate the effective max and distribute unassigned options
                # Rule: Unassigned options get 0% if sum >= 100%, else split remaining
                
                if total_explicit_pct >= 100:
                    # No room for unassigned options - they get 0%
                    for opt in options:
                        if opt['pct'] is None:
                            opt['pct'] = 0
                else:
                    # Distribute remaining (100 - sum) equally among unassigned
                    remaining = 100 - total_explicit_pct
                    share = remaining / unassigned_count if unassigned_count > 0 else 0
                    for opt in options:
                        if opt['pct'] is None:
                            opt['pct'] = share
                
                # Recalculate total after distribution
                total_pct = sum(opt['pct'] for opt in options)
                
                # Normalize if total > 100
                if total_pct > 100:
                    scale = 100 / total_pct
                    for opt in options:
                        opt['pct'] *= scale
                    total_pct = 100
                
                # Roll and pick
                roll = self.rng.random() * 100
                cumulative = 0
                
                for opt in options:
                    cumulative += opt['pct']
                    if roll < cumulative:
                        return opt['text']
                
                # If we're here and total < 100, roll landed in "blank" zone
                # If total == 100, return last option as fallback
                if total_pct >= 100 and options:
                    return options[-1]['text']
                return ""

        # Range selection: {2-3$$opt1|opt2|opt3|opt4} picks 2-3 random options
        if '$$' in content:
            range_str, variants_str = content.split('$$', 1)
            variants = [s.strip() for s in variants_str.split("|")]
            low, high = parse_wildcard_range(range_str, len(variants))
            count = self.rng.randint(low, high)
            if count <= 0:
                return ""
            selected = self.rng.sample(variants, min(count, len(variants)))
            return ", ".join(selected)

        # Standard random choice.
        #
        # Each occurrence rolls on its own. This used to be cached on the
        # literal brace text, so ten identical {0|1|2|3|4} all produced the
        # same digit -- and, because the key was the raw text, {a|b} and
        # {a |b} were treated as unrelated, making the sharing inconsistent
        # even on its own terms. SYNTAX.md has always presented inline choices
        # as the way to get independent picks. To make two places agree, assign
        # once and reuse: $c={red|blue}, $c shirt, $c pants.
        variants = [s.strip() for s in content.split("|")]
        if not variants:
            return ""
        return variants[self.rng.randrange(len(variants))]

    def replace(self, template):
        if not template:
            return ""
        self.sync_indices = {}
        # Replace nested choice blocks iteratively
        prev = None
        while prev != template:
            prev = template
            template = self.re_combinations.sub(self.replace_combinations, template)
        return template


# ==============================================================================
# VARIABLE REPLACER
# ==============================================================================
class VariableReplacer:
    """
    Handles variable assignment ($var = value) and usage ($var)
    Supports: nested variable resolution, string methods (.upper, .lower, .clean, etc.)
    """
    def __init__(self):
        # Updated regex to support multiple assignments per line using ';' as separator
        # Matches $var=val until ';' or end of line/string
        # greedy match up to the separator to handle spaces correctly
        self.assign_regex = re.compile(r'\$([a-zA-Z0-9_]+)\s*=\s*([^;]+?)(?:\s*;|(?=\n)|$)', re.MULTILINE)
        self.use_regex = re.compile(r'\$([a-zA-Z0-9_]+)((?:\.[a-zA-Z_]+)*)')
        self.default_regex = re.compile(r'\$\{([a-zA-Z0-9_]+)\|([^}]*)\}')
        self.coalesce_regex = re.compile(r'coalesce\(([^)]+)\)', re.IGNORECASE)
        self.variables = {}
        self.variable_sources = {}

    def load_globals(self, globals_dict):
        self.variables.update(globals_dict)

    def find_matching_bracket(self, text, start):
        """Find the matching closing bracket for the one at text[start]."""
        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
            i += 1
        return i - 1 if depth == 0 else -1

    def store_variables(self, text, tag_replacer, dynamic_replacer):
        # 1. Mask conditional blocks (e.g. [if ... ]) to prevent premature variable assignment
        masked_text = text
        blocks = {}
        counter = 0
        if_start = re.compile(r'\[if\s+', re.IGNORECASE)

        while True:
            # Always search from the beginning of current masked_text
            match = if_start.search(masked_text)
            if not match:
                break
            
            # Match start is at "[if"
            bracket_idx = match.start()
            end = self.find_matching_bracket(masked_text, bracket_idx)
            
            if end == -1:
                # Malformed or unmatched check, just break to be safe
                break
                
            # Extract content including brackets
            block_content = masked_text[bracket_idx:end+1]
            token = f"%%UMI_IF_BLOCK_{counter}%%"
            blocks[token] = block_content
            
            # Replace strictly this occurrence
            masked_text = masked_text[:bracket_idx] + token + masked_text[end+1:]
            counter += 1

        def _find_matching(text_value, start, open_char, close_char):
            depth = 1
            i = start + 1
            while i < len(text_value) and depth > 0:
                if text_value[i] == open_char:
                    depth += 1
                elif text_value[i] == close_char:
                    depth -= 1
                i += 1
            return i - 1 if depth == 0 else -1

        def _starts_assignment(text_value, idx):
            """True when text_value[idx] begins a `$name=` assignment.

            Used to end an undelimited value before the next assignment rather
            than consuming it.
            """
            j = idx + 1
            while j < len(text_value) and (text_value[j].isalnum() or text_value[j] == '_'):
                j += 1
            if j == idx + 1:
                return False
            while j < len(text_value) and text_value[j].isspace():
                j += 1
            return j < len(text_value) and text_value[j] == '=' and \
                not (j + 1 < len(text_value) and text_value[j + 1] == '=')

        def _parse_assignment(text_value, idx):
            if text_value[idx] != '$':
                return None

            j = idx + 1
            while j < len(text_value) and (text_value[j].isalnum() or text_value[j] == '_'):
                j += 1
            if j == idx + 1:
                return None

            var_name = text_value[idx + 1:j]

            k = j
            while k < len(text_value) and text_value[k].isspace():
                k += 1
            if k >= len(text_value) or text_value[k] != '=':
                return None
            if k + 1 < len(text_value) and text_value[k + 1] == '=':
                return None

            k += 1
            while k < len(text_value) and text_value[k].isspace():
                k += 1
            if k >= len(text_value):
                return None

            value_start = k

            if text_value[k] == '{':
                end = _find_matching(text_value, k, '{', '}')
                if end == -1:
                    end = k
                value_end = end + 1
            elif text_value[k] == '[':
                end = _find_matching(text_value, k, '[', ']')
                if end == -1:
                    end = k
                value_end = end + 1
            elif text_value[k] in ("'", '"'):
                quote_char = text_value[k]
                k += 1
                while k < len(text_value):
                    if text_value[k] == quote_char and text_value[k - 1] != '\\':
                        k += 1
                        break
                    k += 1
                value_end = k
            elif text_value[k:k + 2] == '__':
                end = text_value.find('__', k + 2)
                value_end = end + 2 if end != -1 else len(text_value)
            elif text_value[k] == '<':
                end = text_value.find('>', k + 1)
                value_end = end + 1 if end != -1 else len(text_value)
            else:
                # An undelimited value is one fragment. It used to run to ';' or
                # end of line, so "$m=happy, portrait" swallowed the rest of the
                # prompt and left nothing to render. A comma ends it, as does
                # the start of the next assignment, so "$a=1 $b=2" works too.
                # Use braces or quotes for a value that must contain a comma.
                k = value_start
                while k < len(text_value):
                    ch = text_value[k]
                    if ch in ',;\n':
                        break
                    if ch == '$' and _starts_assignment(text_value, k):
                        break
                    k += 1
                value_end = k

            raw_value = text_value[value_start:value_end].strip()

            # A quoted value keeps its quotes otherwise, which shows up verbatim
            # in the prompt. Quotes are the way to put a comma inside a value
            # now that a bare one ends at the first comma, so they have to come
            # back off.
            if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in ("'", '"'):
                raw_value = raw_value[1:-1]

            # Skip a trailing semicolon if present
            value_end = value_end + 1 if value_end < len(text_value) and text_value[value_end] == ';' else value_end

            return var_name, raw_value, value_end

        # 2. Run assignment on MASKED text
        processed_parts = []
        i = 0
        while i < len(masked_text):
            if masked_text[i] != '$':
                processed_parts.append(masked_text[i])
                i += 1
                continue

            parsed = _parse_assignment(masked_text, i)
            if not parsed:
                processed_parts.append(masked_text[i])
                i += 1
                continue

            var_name, raw_value, end_idx = parsed
            resolved_value = raw_value
            # Each assignment is its own roll context: two variables fed by the
            # same wildcard file are separate requests, while bare occurrences in
            # body text keep sharing one resolved value.
            selector = getattr(tag_replacer, 'tag_selector', None)
            if selector is not None:
                selector.assignment_scope = var_name
            try:
                for _ in range(10):  # Max iterations to prevent infinite loops
                    prev_value = resolved_value
                    resolved_value = tag_replacer.replace(resolved_value)
                    resolved_value = dynamic_replacer.replace(resolved_value)
                    if prev_value == resolved_value:
                        break
            finally:
                if selector is not None:
                    selector.assignment_scope = None

            self.variables[var_name] = resolved_value
            self.variable_sources[var_name] = self._infer_source(raw_value)
            self.variables['trace_last_var'] = var_name
            self.variables['trace_last_var_source'] = self.variable_sources[var_name]
            i = end_idx

        processed_text = "".join(processed_parts)
        
        # 3. Restore blocks
        for token, content in blocks.items():
            processed_text = processed_text.replace(token, content)
            
        return processed_text

    def replace_variables(self, text):
        def _apply_methods(value, methods_str):
            value = str(value)
            if methods_str:
                methods = methods_str.split('.')[1:]
                for method in methods:
                    if method == 'clean':
                        value = value.replace('_', ' ').replace('-', ' ')
                    elif method == 'anima':
                        # Anima prompt form uses spaces for booru underscores,
                        # while meaningful tag hyphens (for example
                        # ``back-to-back``) must remain intact.
                        value = value.replace('_', ' ')
                    elif method == 'upper':
                        value = value.upper()
                    elif method == 'lower':
                        value = value.lower()
                    elif method == 'title':
                        value = value.title()
                    elif method == 'capitalize':
                        value = value.capitalize()
            return value

        # Nested variable resolution - resolve variables that reference other variables
        max_depth = 10
        resolved_vars = {}

        for var_name, var_value in self.variables.items():
            resolved_value = str(var_value)
            depth = 0

            # Keep resolving until no more $ references or max depth reached
            while '$' in resolved_value and depth < max_depth:
                changed = False

                def _replace_nested_use(match):
                    nonlocal changed
                    other_var_name = match.group(1)
                    methods_str = match.group(2)
                    if other_var_name == var_name or other_var_name not in self.variables:
                        return match.group(0)
                    changed = True
                    return _apply_methods(self.variables[other_var_name], methods_str)

                resolved_value = self.use_regex.sub(_replace_nested_use, resolved_value)
                if not changed:
                    break
                depth += 1

            resolved_vars[var_name] = resolved_value

        # Temporarily update variables dict with resolved values for method application
        original_vars = self.variables.copy()
        self.variables.update(resolved_vars)

        def _split_fallbacks(value):
            parts = []
            current = ""
            in_quote = False
            quote_char = ""
            for c in value:
                if in_quote:
                    current += c
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    current += c
                    continue
                if c == '|':
                    parts.append(current.strip())
                    current = ""
                else:
                    current += c
            parts.append(current.strip())
            return parts

        def _normalize_literal(val):
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                return val[1:-1]
            return val

        def _get_value_or_literal(token):
            token = token.strip()
            if not token:
                return ""
            if token.startswith('$'):
                return str(self.variables.get(token[1:], ""))
            return _normalize_literal(token)

        def _replace_default(match):
            var_name = match.group(1)
            fallback_raw = match.group(2).strip()

            value = self.variables.get(var_name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                fallbacks = _split_fallbacks(fallback_raw)
                for fb in fallbacks:
                    fb_val = _get_value_or_literal(fb)
                    if fb_val.strip() != "":
                        return fb_val
                return ""
            return str(value)

        def _split_args(value):
            parts = []
            current = ""
            in_quote = False
            quote_char = ""
            depth = 0
            for c in value:
                if in_quote:
                    current += c
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    current += c
                    continue
                if c == '(':
                    depth += 1
                    current += c
                    continue
                if c == ')':
                    depth = max(0, depth - 1)
                    current += c
                    continue
                if c == ',' and depth == 0:
                    parts.append(current.strip())
                    current = ""
                else:
                    current += c
            if current.strip():
                parts.append(current.strip())
            return parts

        def _replace_coalesce(match):
            content = match.group(1)
            args = _split_args(content)
            for arg in args:
                val = _get_value_or_literal(arg)
                if val.strip() != "":
                    return val
            return ""

        def _replace_use(match):
            var_name = match.group(1)
            methods_str = match.group(2)

            value = self.variables.get(var_name)
            if value is None:
                return match.group(0)
            return _apply_methods(value, methods_str)

        result = self.default_regex.sub(_replace_default, text)
        result = self.coalesce_regex.sub(_replace_coalesce, result)
        result = self.use_regex.sub(_replace_use, result)
        self.variables.clear()
        self.variables.update(original_vars)  # Preserve shared references for selector-injected variables.
        return result

    def _infer_source(self, raw_value):
        raw = raw_value.strip()
        if raw.startswith(('{', '[')) and '|' in raw:
            return "choice"
        if raw.startswith('__@') or '__@' in raw:
            return "prompt_file"
        if '__[' in raw or '<[' in raw:
            return "yaml"
        if '__' in raw:
            return "wildcard"
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')):
            return "literal"
        return "literal"


# ==============================================================================
# NEGATIVE PROMPT GENERATOR
# ==============================================================================
class NegativePromptGenerator:
    """
    Collects and manages negative prompt tags from various sources.
    Supports: **tag** syntax, --neg: syntax, list addition, deduplication
    """
    def __init__(self):
        self.negative_list = []  # Preserve order
        self.seen_lower = set()  # Track lowercase versions for deduplication

    def add(self, negative_text):
        """Add a single negative tag"""
        if negative_text:
            tag = negative_text.strip()
            tag_lower = tag.lower()
            if tag and tag_lower not in self.seen_lower:
                self.seen_lower.add(tag_lower)
                self.negative_list.append(tag)

    def add_list(self, tags):
        """Add multiple negative tags"""
        for t in tags:
            self.add(t)

    def _split_neg_list(self, text):
        return split_escaped_csv(text)

    def _extract_negatives(self, text):
        if not text or "--neg:" not in text:
            return text, []
        negatives = []
        out = []
        i = 0
        token = "--neg:"
        while True:
            idx = text.find(token, i)
            if idx == -1:
                out.append(text[i:])
                break
            out.append(text[i:idx])
            j = idx + len(token)
            while j < len(text) and text[j] in " \t":
                j += 1
            if j >= len(text):
                i = j
                break
            if text[j] in ("'", '"'):
                quote = text[j]
                j += 1
                buf = []
                while j < len(text):
                    ch = text[j]
                    if ch == '\\' and j + 1 < len(text):
                        buf.append('\\')
                        buf.append(text[j + 1])
                        j += 2
                        continue
                    if ch == quote:
                        j += 1
                        break
                    buf.append(ch)
                    j += 1
                neg_text = "".join(buf)
            else:
                buf = []
                while j < len(text) and text[j] != '\n':
                    ch = text[j]
                    if ch == '\\' and j + 1 < len(text):
                        buf.append('\\')
                        buf.append(text[j + 1])
                        j += 2
                        continue
                    buf.append(ch)
                    j += 1
                neg_text = "".join(buf)
            negatives.extend(self._split_neg_list(neg_text))
            i = j
        return "".join(out), negatives

    def _extract_bracket_negatives(self, text, variables=None):
        if not text:
            return text, []

        variables = variables or {}
        negatives = []

        def _add_parts(raw):
            negatives.extend(self._split_neg_list(raw))
            return ""

        def _neg_if(match):
            condition = match.group(1).strip()
            neg_text = match.group(2).strip()
            if not condition or not neg_text:
                return ""
            try:
                should_add = LogicEvaluator(condition, variables).evaluate(text)
            except Exception:
                should_add = condition.lower() in text.lower()
            if should_add:
                _add_parts(neg_text)
            return ""

        text = re.sub(r'\[neg_if:([^\]]+)\]([\s\S]*?)\[/neg_if\]', _neg_if, text, flags=re.IGNORECASE)
        text = re.sub(r'\[(?:neg|negative)\]([\s\S]*?)\[/\s*(?:neg|negative)\]', lambda m: _add_parts(m.group(1)), text, flags=re.IGNORECASE)
        text = re.sub(r'\[(?:neg|negative):([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', lambda m: _add_parts(m.group(1)), text, flags=re.IGNORECASE)

        return text, negatives

    def strip_negative_tags(self, text, variables=None):
        """Extract **negatives** from text and add them, return cleaned text"""
        if not text:
            return text

        variables = variables or {}
        spans = []
        for span in find_negative_spans(text):
            if span.condition:
                try:
                    if not LogicEvaluator(span.condition, variables).evaluate(text):
                        continue
                except Exception:
                    if span.condition.lower() not in text.lower():
                        continue
            spans.append(span)

        if not spans:
            return text

        cursor = 0
        for span in spans:
            if span.start < cursor:
                continue
            self.add_list(split_escaped_csv(span.content))
            cursor = span.end
        return remove_spans(text, spans)

    def get_negative_string(self):
        """Return combined negative string, deduplicated"""
        return ", ".join(self.negative_list)


# ==============================================================================
# CONDITIONAL REPLACER
# ==============================================================================
class ConditionalReplacer:
    """
    Handles conditional text: [if condition: true_text | false_text]
    Supports: tag existence, variable checks, logical operators (AND, OR, NOT, XOR, NAND, NOR)
    """
    def __init__(self):
        # Simple pattern to find [if starts - we'll parse brackets manually
        self.if_start = re.compile(r'\[if\s+', re.IGNORECASE)
        self.local_assign_prefix = "$@"
        # Optional replacers used to resolve a $@ value once, at assignment.
        self.value_replacers = None

    def set_value_replacers(self, tag_replacer=None, dynamic_replacer=None):
        """Let $@name pin one value.

        Without these, a $@ assignment substitutes its value as raw text, so
        "$@d={soft|sharp}" used three times rolled three times -- the opposite
        of what a variable is for. Resolving once at assignment makes every
        later use agree.
        """
        self.value_replacers = (tag_replacer, dynamic_replacer)

    def _resolve_local_value(self, raw_value):
        if not self.value_replacers:
            return raw_value
        tag_replacer, dynamic_replacer = self.value_replacers
        resolved = raw_value
        try:
            if tag_replacer is not None:
                resolved = tag_replacer.replace(resolved)
            if dynamic_replacer is not None:
                resolved = dynamic_replacer.replace(resolved)
        except Exception:
            return raw_value
        return resolved

    def apply_local_vars(self, text_value, variables):
        """Public entry point for $@ assignments outside a conditional."""
        return self._apply_local_vars(text_value, variables)

    def _starts_assignment(self, text_value, idx):
        """True when text_value[idx] begins a `$name=` or `$@name=` assignment."""
        j = idx + 1
        if j < len(text_value) and text_value[j] == '@':
            j += 1
        start = j
        while j < len(text_value) and (text_value[j].isalnum() or text_value[j] == '_'):
            j += 1
        if j == start:
            return False
        while j < len(text_value) and text_value[j].isspace():
            j += 1
        if j >= len(text_value) or text_value[j] != '=':
            return False
        return not (j + 1 < len(text_value) and text_value[j + 1] == '=')

    def _parse_local_assignment(self, text_value, idx):
        if text_value[idx:idx + 2] != self.local_assign_prefix:
            return None

        j = idx + 2
        while j < len(text_value) and (text_value[j].isalnum() or text_value[j] == '_'):
            j += 1
        if j == idx + 2:
            return None

        var_name = text_value[idx + 2:j]

        k = j
        while k < len(text_value) and text_value[k].isspace():
            k += 1
        if k >= len(text_value) or text_value[k] != '=':
            return None
        if k + 1 < len(text_value) and text_value[k + 1] == '=':
            return None

        k += 1
        while k < len(text_value) and text_value[k].isspace():
            k += 1
        if k >= len(text_value):
            return None

        value_start = k

        def _find_matching(text_src, start, open_char, close_char):
            depth = 1
            i = start + 1
            while i < len(text_src) and depth > 0:
                if text_src[i] == open_char:
                    depth += 1
                elif text_src[i] == close_char:
                    depth -= 1
                i += 1
            return i - 1 if depth == 0 else -1

        if text_value[k] == '{':
            end = _find_matching(text_value, k, '{', '}')
            if end == -1:
                end = k
            value_end = end + 1
        elif text_value[k] == '[':
            end = _find_matching(text_value, k, '[', ']')
            if end == -1:
                end = k
            value_end = end + 1
        elif text_value[k] in ("'", '"'):
            quote_char = text_value[k]
            k += 1
            while k < len(text_value):
                if text_value[k] == quote_char and text_value[k - 1] != '\\':
                    k += 1
                    break
                k += 1
            value_end = k
        elif text_value[k:k + 2] == '__':
            end = text_value.find('__', k + 2)
            value_end = end + 2 if end != -1 else len(text_value)
        elif text_value[k] == '<':
            end = text_value.find('>', k + 1)
            value_end = end + 1 if end != -1 else len(text_value)
        else:
            # An undelimited value is one fragment, ending at a comma just as
            # a plain $name= assignment does. Running to ';' or end of line
            # made "$@d=soft, $@d a, $@d b" swallow every later use as part of
            # the value, leaving nothing behind to substitute into. Use braces
            # or quotes for a value that must contain a comma.
            k = value_start
            while k < len(text_value):
                ch = text_value[k]
                if ch in ',;' or ch == chr(10):
                    break
                if ch == '$' and self._starts_assignment(text_value, k):
                    break
                k += 1
            value_end = k

        raw_value = text_value[value_start:value_end].strip()
        # A quoted value keeps its quotes out of the prompt, as $name= does.
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in ("'", '"'):
            raw_value = raw_value[1:-1]
        value_end = value_end + 1 if value_end < len(text_value) and text_value[value_end] == ';' else value_end

        return var_name, raw_value, value_end

    def _apply_local_vars(self, text_value, variables):
        local_vars = {}
        output = []
        i = 0
        while i < len(text_value):
            if text_value[i:i + 2] != self.local_assign_prefix:
                output.append(text_value[i])
                i += 1
                continue

            parsed = self._parse_local_assignment(text_value, i)
            if not parsed:
                output.append(text_value[i])
                i += 1
                continue

            var_name, raw_value, end_idx = parsed
            local_vars[var_name] = self._resolve_local_value(raw_value)

            if isinstance(variables, dict):
                trace_val = variables.get('trace')
                if str(trace_val).strip().lower() in ("1", "true", "yes", "on"):
                    variables['trace_last_var'] = var_name
                    variables['trace_last_var_source'] = "local"
            i = end_idx

        cleaned = "".join(output)
        for name, value in local_vars.items():
            pattern = r'\$@' + re.escape(name) + r'(?!\w)'
            cleaned = re.sub(pattern, value, cleaned)
        return cleaned

    def mask_conditionals(self, text):
        """Mask [if ...] blocks to prevent premature expansion."""
        masked_text = text
        blocks = {}
        counter = 0

        for spec in reversed(parse_conditional_specs(masked_text)):
            bracket_idx = spec.span.start
            end = spec.span.end
            block_content = masked_text[bracket_idx:end]
            token = f"%%UMI_IF_BLOCK_{counter}%%"
            blocks[token] = block_content
            masked_text = masked_text[:bracket_idx] + token + masked_text[end:]
            counter += 1

        return masked_text, blocks

    def unmask_conditionals(self, text, blocks):
        """Restore masked [if ...] blocks."""
        for token, content in blocks.items():
            text = text.replace(token, content)
        return text

    def evaluate_logic(self, condition, context, variables=None):
        """Evaluate a logical condition against the context."""
        if variables is None: 
            variables = {}
        evaluator = LogicEvaluator(condition, variables)
        return evaluator.evaluate(context)

    def replace(self, prompt, variables=None):
        """Replace conditional tags in the prompt."""
        if variables is None: 
            variables = {}
        
        max_iterations = 100  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            specs = parse_conditional_specs(prompt)
            if not specs:
                break
            spec = specs[0]
            start_pos = spec.span.start
            end_pos = spec.span.end
            branches = spec.branches
            else_text = spec.else_text
            
            # Clean the context by removing current tag to avoid self-reference
            context = prompt[:start_pos] + prompt[end_pos:]

            replacement = self._apply_local_vars(else_text, variables) if else_text else else_text
            for idx, (cond, text_value) in enumerate(branches):
                if self.evaluate_logic(cond, context, variables):
                    replacement = self._apply_local_vars(text_value, variables)
                    trace_val = variables.get('trace')
                    if str(trace_val).strip().lower() in ("1", "true", "yes", "on"):
                        variables['trace_last_condition'] = cond
                        variables['trace_last_branch'] = str(idx)
                    break
            
            prompt = prompt[:start_pos] + replacement + prompt[end_pos:]
            iteration += 1
        
        return prompt


# ==============================================================================
# TAG LOADER BASE
# ==============================================================================
class TagLoaderBase:
    """
    Base class for TagLoader with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self, wildcard_paths, options):
        if isinstance(wildcard_paths, str):
            self.wildcard_paths = [wildcard_paths]
        else:
            self.wildcard_paths = wildcard_paths
            
        self.options = options
        self.verbose = options.get('verbose', False)
        self.files_index = set()
        self.umi_tags = set()
        self.aliases = load_aliases_from_paths(self.wildcard_paths)

    def resolve_wildcard_alias(self, name):
        if not name:
            return name
        return self.aliases.get('wildcards', {}).get(str(name).strip().lower(), name)

    def resolve_lora_alias(self, name):
        if not name:
            return name
        return self.aliases.get('loras', {}).get(str(name).strip().lower(), name)

    def load_globals(self):
        """Load global variables from globals.yaml files in wildcard folders."""
        merged_globals = {}
        for location in self.wildcard_paths:
            global_path = os.path.join(location, 'globals.yaml')
            if not os.path.exists(global_path):
                continue
            try:
                with open(global_path, 'r', encoding='utf-8-sig') as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    # Store by bare name: $hair in a prompt resolves
                    # variables['hair'], so "$hair:" and "hair:" keys
                    # must both land on the same un-prefixed key.
                    for k, v in data.items():
                        key = str(k).strip().lstrip('$')
                        if key:
                            merged_globals[key] = str(v)
            except yaml.YAMLError as e:
                print(f"[UmiAI] ERROR: Malformed globals.yaml at {global_path}: {e}")
                print("[UmiAI] Global variables from this file will not be loaded. Please fix YAML syntax.")
            except UnicodeDecodeError as e:
                print(f"[UmiAI] ERROR: Encoding issue in globals.yaml at {global_path}: {e}")
            except Exception as e:
                print(f"[UmiAI] WARNING: Error loading globals.yaml at {global_path}: {e}")
        return merged_globals

    def process_yaml_entry(self, title, entry_data):
        """Process a YAML entry to extract structured data."""
        return {
            'title': title,
            'description': entry_data.get('Description', [None])[0] if isinstance(entry_data.get('Description', []), list) else None,
            'prompts': entry_data.get('Prompts', []),
            'prefixes': entry_data.get('Prefix', []),
            'suffixes': entry_data.get('Suffix', []),
            'tags': [str(x).lower().strip() for x in entry_data.get('Tags', [])]
        }


# ==============================================================================
# TAG SELECTOR BASE
# ==============================================================================
class TagSelectorBase:
    """
    Base class for TagSelector with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self, tag_loader, options):
        self.tag_loader = tag_loader
        self.options = options
        self.verbose = options.get('verbose', False)
        self.seed = options.get('seed', 0)
        self.rng = random.Random(self.seed)
        self.rng_streams_enabled = options.get('rng_streams', False)
        self.rng_streams_cache = {}
        self.variables = {}
        self.seeded_values = {}
        self.scoped_negatives = []

    def is_debug_enabled(self):
        val = self.variables.get('debug')
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    def is_trace_enabled(self):
        val = self.variables.get('trace')
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    def is_failfast_enabled(self):
        val = self.variables.get('fail_fast')
        if val is None:
            val = self.variables.get('failfast')
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    def init_debug_context(self):
        if not self.is_debug_enabled():
            return
        if 'debug_seed' not in self.variables:
            self.variables['debug_seed'] = str(self.seed)
        if 'debug_run_id' not in self.variables:
            run_id = f"{self.seed}-{int(datetime.now().timestamp() * 1000)}"
            self.variables['debug_run_id'] = run_id
        if 'debug_summary' not in self.variables:
            self.variables['debug_summary'] = "1"

    def init_trace_context(self):
        if not self.is_trace_enabled():
            return
        if 'trace_seed' not in self.variables:
            self.variables['trace_seed'] = str(self.seed)
        if 'trace_run_id' not in self.variables:
            run_id = f"{self.seed}-{int(datetime.now().timestamp() * 1000)}"
            self.variables['trace_run_id'] = run_id
        if 'trace_summary' not in self.variables:
            self.variables['trace_summary'] = "1"

    def set_trace_info(self, info):
        if not self.is_trace_enabled():
            return
        for k, v in info.items():
            self.variables[k] = v

    def update_variables(self, variables):
        """Update the variables dictionary."""
        self.variables = variables

    def clear_seeded_values(self):
        """Clear cached seeded values for a fresh run."""
        self.seeded_values = {}
        self.scoped_negatives = []

    def get_rng(self, scope=None):
        if not self.rng_streams_enabled:
            return self.rng

        scope_prefix = str(self.variables.get('rng_scope', '')).strip()
        if scope_prefix and scope:
            scope_key = f"{scope_prefix}:{scope}"
        elif scope_prefix:
            scope_key = scope_prefix
        else:
            scope_key = scope or ""

        if scope_key not in self.rng_streams_cache:
            seed_key = f"{self.seed}:{scope_key}"
            seed_int = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) % (2 ** 32)
            self.rng_streams_cache[scope_key] = random.Random(seed_int)

        return self.rng_streams_cache[scope_key]

    def get_scoped_index(self, scope, count):
        if count <= 0:
            return 0
        scope_key = scope or ""
        seed_key = f"{self.seed}:{scope_key}:index"
        seed_int = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) % (2 ** 32)
        return seed_int % count

    def _weighted_choice(self, items, rng=None):
        """Weighted random selection for lists with weights."""
        has_weights = all(isinstance(item, dict) and 'weight' in item for item in items)

        if not has_weights:
            return (rng or self.rng).choice(items)

        weights = [item.get('weight', 1.0) for item in items]
        total_weight = sum(weights)
        rand_val = (rng or self.rng).random() * total_weight
        cumsum = 0

        for item in items:
            cumsum += item.get('weight', 1.0)
            if rand_val <= cumsum:
                return item

        return items[-1]

    def get_prefixes_and_suffixes(self):
        """Get collected prefixes and suffixes. Override in subclasses."""
        return {
            'prefixes': getattr(self, 'prefixes', []),
            'suffixes': getattr(self, 'suffixes', []),
            'neg_prefixes': getattr(self, 'neg_prefixes', []),
            'neg_suffixes': getattr(self, 'neg_suffixes', [])
        }


# ==============================================================================
# LORA HANDLER BASE
# ==============================================================================
class LoRAHandlerBase:
    """
    Base class for LoRAHandler with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self):
        self.regex = re.compile(r'<lora:([^>]+)>', re.IGNORECASE)
        self.blacklist = {
            "1girl", "1boy", "solo", "monochrome", "greyscale", "comic", "scenery",
            "translated", "commentary_request", "highres", "absurdres", "masterpiece",
            "best quality", "simple background", "white background", "transparent background"
        }

    def apply_qkv_fusion(self, lora_dict):
        """Apply QKV fusion for Z-Image format LoRAs."""
        fused_dict = {}

        for key in lora_dict.keys():
            if 'to_k_lora' in key or 'to_v_lora' in key:
                continue

            if 'to_q_lora' in key:
                new_key = key.replace('to_q_lora', 'to_qkv_lora')

                q_weight = lora_dict[key]
                k_key = key.replace('to_q_lora', 'to_k_lora')
                v_key = key.replace('to_q_lora', 'to_v_lora')

                k_weight = lora_dict.get(k_key, None)
                v_weight = lora_dict.get(v_key, None)

                if k_weight is not None and v_weight is not None:
                    try:
                        import torch
                        fused_weight = torch.cat([q_weight, k_weight, v_weight], dim=0)
                        fused_dict[new_key] = fused_weight
                    except:
                        fused_dict[key] = q_weight
                else:
                    fused_dict[key] = q_weight
            else:
                fused_dict[key] = lora_dict[key]

        return fused_dict

# ==============================================================================
# TAG REPLACER BASE
# ==============================================================================
class TagReplacerBase:
    """
    Base class for TagReplacer with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self, tag_selector):
        self.tag_selector = tag_selector
        self.replacement_history = []  # Track replacements for cycle detection

    def _split_pipe_args(self, content):
        """Split function arguments on top-level '|' only.

        Pipes inside nested {...} or [...] (e.g. "[choose: {red|blue} hair | green]")
        belong to the nested construct and must not split the argument list.
        """
        parts = []
        current = []
        escape = False
        quote = ""
        depth_brace = 0
        depth_bracket = 0
        for ch in str(content or ""):
            if escape:
                current.append(ch)
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if quote:
                if ch == quote:
                    quote = ""
                current.append(ch)
                continue
            if ch in ("'", '"'):
                quote = ch
                current.append(ch)
                continue
            if ch == "{":
                depth_brace += 1
            elif ch == "}":
                depth_brace = max(0, depth_brace - 1)
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket = max(0, depth_bracket - 1)
            elif ch == "|" and depth_brace == 0 and depth_bracket == 0:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        if escape:
            current.append("\\")
        parts.append("".join(current).strip())
        return [part for part in parts if part]

    def _weighted_local_choice_detailed(self, content):
        """Weighted exactly-one choice.

        Returns (result, values, weights, selected_index). Consumes exactly
        one rng draw for non-empty input, none for empty input.
        """
        items = []
        for part in self._split_pipe_args(content):
            value = part
            weight = 1.0
            if ":" in part:
                maybe_value, maybe_weight = part.rsplit(":", 1)
                try:
                    weight = max(0.0, float(maybe_weight.strip()))
                    value = maybe_value.strip()
                except ValueError:
                    value = part
                    weight = 1.0
            if value and weight > 0:
                items.append((value, weight))

        if not items:
            return "", [], [], None

        values = [value for value, _ in items]
        weights = [weight for _, weight in items]
        rng = getattr(self.tag_selector, 'rng', None) or getattr(self.tag_selector, 'random', None) or random
        total = sum(weights)
        roll = rng.random() * total
        upto = 0.0
        for index, (value, weight) in enumerate(items):
            upto += weight
            if roll <= upto:
                return value, values, weights, index
        return values[-1], values, weights, len(items) - 1

    def _weighted_local_choice(self, content):
        return self._weighted_local_choice_detailed(content)[0]

    def _expand_lora_alias(self, content):
        content = str(content or "").strip()
        if not content:
            return ""

        tokens = content.split()
        option_tokens = []
        while tokens and "=" in tokens[-1]:
            option_tokens.insert(0, tokens.pop())
        spec = " ".join(tokens).strip()
        options = " ".join(option_tokens).strip()
        if not spec:
            return ""

        name = spec
        strength = "1.0"
        if ":" in spec:
            candidate_name, candidate_strength = spec.rsplit(":", 1)
            try:
                float(candidate_strength)
                name = candidate_name.strip()
                strength = candidate_strength.strip()
            except ValueError:
                name = spec

        resolver = getattr(getattr(self.tag_selector, "tag_loader", None), "resolve_lora_alias", None)
        if resolver:
            name = resolver(name)

        suffix = f" {options}" if options else ""
        return f"<lora:{name}:{strength}{suffix}>"

    def replace_functions(self, text):
        """Process bracket function tags."""
        def _shuffle_content(content):
            items = [x.strip() for x in content.split(',')]
            # Use rng if available (base class), otherwise random
            rng = getattr(self.tag_selector, 'rng', None) or getattr(self.tag_selector, 'random', None)
            if rng:
                rng.shuffle(items)
            else:
                random.shuffle(items)
            return ", ".join(items)

        def _clean_content(content):
            # Remove extra whitespace
            content = re.sub(r'\s+', ' ', content)
            # Remove empty commas (,,)
            content = re.sub(r',\s*,+', ',', content)
            # Clean up spaces around commas
            content = content.replace(' ,', ',')
            content = re.sub(r',\s+', ', ', content)
            # Remove leading/trailing commas and spaces
            return content.strip(', ')

        def _sample_content(content):
            match = re.match(r'^(\d+)(?:\s*-\s*(\d+))?\s+from\s*:\s*(.*)$', str(content or "").strip(), flags=re.IGNORECASE | re.DOTALL)
            if not match:
                return ""
            min_count = int(match.group(1))
            max_count = int(match.group(2) or match.group(1))
            if max_count < min_count:
                min_count, max_count = max_count, min_count
            items = self._split_pipe_args(match.group(3))
            if not items or max_count <= 0:
                return ""
            rng = getattr(self.tag_selector, 'rng', None) or getattr(self.tag_selector, 'random', None) or random
            count = rng.randint(min_count, max_count) if max_count > min_count else min_count
            count = max(0, min(count, len(items)))
            return ", ".join(rng.sample(items, count))

        def _record_function_trace(name, raw, args, result, selected_indices, mode, **extra):
            # Additive trace for the Run Inspector. Rides the selector's
            # existing wildcard_trace list, which explain_json already emits.
            trace = getattr(self.tag_selector, 'wildcard_trace', None)
            if not isinstance(trace, list):
                return
            record = {
                "type": "prompt_function",
                "name": name,
                "raw": raw,
                "args": list(args),
                "result": result,
                "selected_indices": list(selected_indices),
                "selection_mode": mode,
            }
            record.update(extra)
            trace.append(record)

        def _and_content(content, raw=""):
            # [and: a | b | c] -> every item, source order, deterministic.
            items = self._split_pipe_args(content)
            if not items:
                return ""
            result = ", ".join(items)
            _record_function_trace("and", raw, items, result, range(len(items)), "all")
            return result

        def _or_content(content, raw=""):
            # [or: a | b | c] -> seeded non-empty subset: k uniform in 1..n,
            # k items sampled without replacement, emitted in source order.
            items = self._split_pipe_args(content)
            if not items:
                return ""
            rng = getattr(self.tag_selector, 'rng', None) or getattr(self.tag_selector, 'random', None) or random
            count = rng.randint(1, len(items))
            selected = sorted(rng.sample(range(len(items)), count))
            result = ", ".join(items[idx] for idx in selected)
            _record_function_trace("or", raw, items, result, selected, "subset", count=count)
            return result

        def _xor_content(content, raw=""):
            # Exactly-one selection; same weighted machinery as [choose:].
            result, values, weights, selected_index = self._weighted_local_choice_detailed(content)
            if not values:
                return ""
            extra = {}
            if any(weight != 1.0 for weight in weights):
                extra["weights"] = list(weights)
            _record_function_trace(
                "xor", raw, values, result,
                [selected_index] if selected_index is not None else [],
                "exactly_one", **extra,
            )
            return result

        def _replace_parser_functions(value):
            specs = parse_function_specs(value, names=(
                "clean", "shuffle", "choose", "lora", "sample",
                "and", "or", "xor",
                "require", "forbid", "prefer", "assert", "warn",
                "anima", "anima_order", "anima_natural", "anima_lint", "preset",
            ))
            if not specs:
                return value
            parts = []
            cursor = 0
            for spec in specs:
                span = spec.span
                if span.start < cursor:
                    continue
                parts.append(value[cursor:span.start])
                if spec.name == "clean":
                    parts.append(_clean_content(spec.content))
                elif spec.name == "shuffle":
                    parts.append(_shuffle_content(spec.content))
                elif spec.name == "choose":
                    parts.append(self._weighted_local_choice(spec.content))
                elif spec.name == "and":
                    parts.append(_and_content(spec.content, value[span.start:span.end]))
                elif spec.name == "or":
                    parts.append(_or_content(spec.content, value[span.start:span.end]))
                elif spec.name == "xor":
                    parts.append(_xor_content(spec.content, value[span.start:span.end]))
                elif spec.name == "lora":
                    parts.append(self._expand_lora_alias(spec.content))
                elif spec.name == "sample":
                    parts.append(_sample_content(spec.content))
                elif spec.name == "require":
                    parts.append(_require_content(spec.content))
                elif spec.name == "forbid":
                    parts.append(_forbid_content(spec.content, value))
                elif spec.name == "prefer":
                    parts.append(_prefer_content(spec.content, value))
                elif spec.name == "assert":
                    parts.append(_assert_content(spec.content, value))
                elif spec.name == "warn":
                    parts.append(_warn_content(spec.content, value))
                elif spec.name == "anima":
                    parts.append(_anima_content(spec.content))
                elif spec.name == "anima_order":
                    parts.append(_anima_order_content(spec.content))
                elif spec.name == "anima_natural":
                    parts.append(expand_anima_natural_language(spec.content.strip()))
                elif spec.name == "anima_lint":
                    parts.append(_anima_lint_content(spec.content))
                elif spec.name == "preset":
                    parts.append(resolve_preset_directive(spec.content))
                else:
                    parts.append(value[span.start:span.end])
                cursor = span.end
            parts.append(value[cursor:])
            return "".join(parts)

        def _require_content(content):
            content = str(content or "").strip()
            if not content:
                return ""
            var_part = content
            label = None
            if '|' in content:
                var_part, label = [s.strip() for s in content.split('|', 1)]
            var_name = var_part[1:] if var_part.startswith('$') else var_part
            if not var_name:
                return ""

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            value = variables.get(var_name)
            missing = value is None or (isinstance(value, str) and value.strip() == "")
            if missing:
                return f"<<ERROR_MISSING:{label or var_name}>>"
            return ""

        def _split_forbid(content):
            in_quote = False
            quote_char = ""
            for i, c in enumerate(content):
                if in_quote:
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    continue
                if c == '|':
                    prev_c = content[i - 1] if i > 0 else ""
                    next_c = content[i + 1] if i + 1 < len(content) else ""
                    if (prev_c.isspace() or prev_c == "") and (next_c.isspace() or next_c == ""):
                        return content[:i].strip(), content[i + 1:].strip()
            return "", ""

        def _forbid_content(content, context_text):
            content = str(content or "").strip()
            if not content:
                return ""
            condition, neg_text = _split_forbid(content)
            if not condition or not neg_text:
                return ""

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            evaluator = LogicEvaluator(condition, variables)
            if not evaluator.evaluate(context_text):
                return ""

            parts = [t.strip() for t in neg_text.split(',') if t.strip()]
            return " ".join(f"**{t}**" for t in parts)

        def _prefer_content(content, context_text):
            content = str(content or "").strip()
            if not content:
                return ""
            condition, pos_text = _split_forbid(content)
            if not condition or not pos_text:
                return ""

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            evaluator = LogicEvaluator(condition, variables)
            if not evaluator.evaluate(context_text):
                return ""

            parts = [t.strip() for t in pos_text.split(',') if t.strip()]
            return ", ".join(parts)

        def _assert_content(content, context_text):
            content = str(content or "").strip()
            if not content:
                return ""
            condition, label = _split_forbid(content)
            if not condition:
                return ""
            if not label:
                label = condition

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            evaluator = LogicEvaluator(condition, variables)
            if evaluator.evaluate(context_text):
                return ""
            return f"<<ERROR_ASSERT:{label}>>"

        def _warn_content(content, context_text):
            content = str(content or "").strip()
            if not content:
                return ""
            condition, message = _split_forbid(content)
            if not condition:
                return ""
            if not message:
                message = condition

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            trace = variables.get('trace')
            debug = variables.get('debug')
            enabled = str(trace).strip().lower() in ("1", "true", "yes", "on") or str(debug).strip().lower() in ("1", "true", "yes", "on")
            if not enabled:
                return ""
            evaluator = LogicEvaluator(condition, variables)
            if evaluator.evaluate(context_text):
                return f"<<WARN:{message}>>"
            return ""

        def _split_anima_args(content):
            parts = [part.strip() for part in content.split('|')]
            prompt_text = parts[0] if parts else ""
            opts = {}
            for part in parts[1:]:
                if '=' in part:
                    key, value = part.split('=', 1)
                    opts[key.strip().lower()] = value.strip()
            return prompt_text, opts

        def _anima_content(content):
            prompt_text, opts = _split_anima_args(str(content or "").strip())
            profile_prompt, _, warnings = apply_anima_profile(
                prompt_text,
                mode=opts.get("mode", "profile"),
                style_preset=opts.get("style", "none"),
            )
            if opts.get("warn", "").lower() in ("1", "true", "yes", "on") and warnings:
                return profile_prompt + ", " + ", ".join(f"<<WARN:{warning}>>" for warning in warnings)
            return profile_prompt

        def _anima_order_content(content):
            prompt_text, opts = _split_anima_args(str(content or "").strip())
            return order_anima_prompt(
                prompt_text,
                style_preset=opts.get("style", "none"),
                add_prefix=opts.get("prefix", "").lower() in ("1", "true", "yes", "on"),
            )

        def _anima_lint_content(content):
            prompt_text, opts = _split_anima_args(str(content or "").strip())
            warnings = lint_anima_prompt(prompt_text, opts.get("negative", ""))
            if not warnings:
                return ""
            return ", ".join(f"<<WARN:{warning}>>" for warning in warnings)

        text = _replace_parser_functions(text)
        return text

    def get_prompt_file_content(self, filename):
        """Load full file content as a prompt."""
        try:
            file_content = self.tag_selector.tag_loader.load_prompt_file(filename)
            if file_content:
                return file_content
            else:
                return f"[PROMPT_FILE_NOT_FOUND: {filename}]"
        except Exception as e:
            return f"[PROMPT_FILE_ERROR: {filename}: {str(e)}]"


# ==============================================================================
# CHARACTER REPLACER
# ==============================================================================

class CharacterReplacer:
    """
    Replaces @@character:outfit:emotion@@ syntax with expanded character prompts.
    
    Syntax:
        @@elena@@                   - Base character only
        @@elena:casual@@            - Character with outfit
        @@elena:casual:happy@@      - Character with outfit and emotion
    """
    
    # Regex pattern for @@character:outfit:emotion@@
    pattern = re.compile(r'@@([a-zA-Z0-9_-]+)(?::([a-zA-Z0-9_-]+))?(?::([a-zA-Z0-9_-]+))?@@')
    
    # Cache for character data
    _cache = {}
    _mtime_cache = {}
    
    @classmethod
    def get_characters_path(cls):
        """Get the path to the characters folder."""
        # Check in the UmiAI custom node folder
        node_path = os.path.dirname(os.path.abspath(__file__))
        util_chars_path = os.path.join(node_path, "umi_utilities", "characters")
        if os.path.isdir(util_chars_path):
            return util_chars_path
        chars_path = os.path.join(node_path, "characters")
        if os.path.isdir(chars_path):
            return chars_path
        return None
    
    @classmethod
    def list_characters(cls):
        """List all available character names."""
        chars_path = cls.get_characters_path()
        if not chars_path:
            return []
        
        characters = []
        for item in os.listdir(chars_path):
            item_path = os.path.join(chars_path, item)
            profile_path = os.path.join(item_path, "profile.yaml")
            if os.path.isdir(item_path) and os.path.isfile(profile_path):
                characters.append(item)
        
        return characters
    
    @classmethod
    def load_character(cls, name):
        """Load a character profile, using cache if available."""
        chars_path = cls.get_characters_path()
        if not chars_path:
            return None
        
        profile_path = os.path.join(chars_path, name, "profile.yaml")
        if not os.path.isfile(profile_path):
            return None
        
        # Check if cached and still valid
        mtime = os.path.getmtime(profile_path)
        if name in cls._cache and cls._mtime_cache.get(name) == mtime:
            return cls._cache[name]
        
        # Load fresh
        try:
            with open(profile_path, 'r', encoding='utf-8-sig') as f:
                data = yaml.safe_load(f)
                cls._cache[name] = data
                cls._mtime_cache[name] = mtime
                return data
        except Exception as e:
            print(f"[UmiAI Character] Error loading {name}: {e}")
            return None
    
    @classmethod
    def expand_character(cls, name, outfit=None, emotion=None, include_lora=True):
        """
        Expand a character reference into a full prompt.
        
        Args:
            name: Character folder name (e.g., 'elena')
            outfit: Outfit name (e.g., 'casual')
            emotion: Emotion name (e.g., 'happy')
            include_lora: Whether to include the LoRA tag
            
        Returns:
            Expanded prompt string or original reference if not found
        """
        data = cls.load_character(name)
        if not data:
            return f"@@{name}@@"  # Return original if not found
        
        parts = []
        
        # Add LoRA if available
        if include_lora and data.get('lora'):
            lora_name = data['lora']
            lora_strength = data.get('lora_strength', 1.0)
            parts.append(f"<lora:{lora_name}:{lora_strength}>")
        
        # Add base prompt
        if data.get('base_prompt'):
            parts.append(data['base_prompt'])
        
        # Add outfit if specified
        if outfit and 'outfits' in data:
            outfit_lower = outfit.lower()
            if outfit_lower in data['outfits']:
                outfit_data = data['outfits'][outfit_lower]
                if isinstance(outfit_data, dict):
                    parts.append(outfit_data.get('prompt', ''))
                else:
                    parts.append(str(outfit_data))
        
        # Add emotion if specified
        if emotion and 'emotions' in data:
            emotion_lower = emotion.lower()
            if emotion_lower in data['emotions']:
                emotion_data = data['emotions'][emotion_lower]
                if isinstance(emotion_data, dict):
                    parts.append(emotion_data.get('prompt', ''))
                else:
                    parts.append(str(emotion_data))
        
        return ", ".join(filter(None, parts))
    
    @classmethod
    def get_costume_parts(cls, name, costume_name, part=None):
        """
        Get costume parts from character data (VNCCS-style).
        
        Args:
            name: Character folder name
            costume_name: Costume name (e.g., 'school_uniform')
            part: Specific part (face/head/top/bottom/shoes) or None for all
            
        Returns:
            Prompt string for the costume/part
        """
        data = cls.load_character(name)
        if not data:
            return ""
        
        costumes = data.get('Costumes', data.get('costumes', {}))
        if not costumes:
            return ""
        
        costume_lower = costume_name.lower()
        costume_data = None
        for k, v in costumes.items():
            if k.lower() == costume_lower:
                costume_data = v
                break
        
        if not costume_data:
            return ""
        
        if part:
            # Return specific part
            part_lower = part.lower()
            return str(costume_data.get(part_lower, ""))
        else:
            # Return all parts combined
            valid_parts = ['face', 'head', 'top', 'bottom', 'shoes']
            part_prompts = []
            for p in valid_parts:
                val = costume_data.get(p, "")
                if val:
                    part_prompts.append(str(val))
            return ", ".join(part_prompts)
    
    @classmethod
    def get_emotion(cls, name, emotion_name):
        """
        Get emotion prompt from character data (VNCCS-style).
        
        Args:
            name: Character folder name
            emotion_name: Emotion name (e.g., 'happy')
            
        Returns:
            Emotion prompt string
        """
        data = cls.load_character(name)
        if not data:
            return ""
        
        emotions = data.get('Emotions', data.get('emotions', {}))
        if not emotions:
            return ""
        
        emotion_lower = emotion_name.lower()
        for k, v in emotions.items():
            if k.lower() == emotion_lower:
                if isinstance(v, dict):
                    return str(v.get('prompt', ''))
                return str(v)
        return ""
    
    @classmethod
    def get_info(cls, name, field):
        """
        Get character info field (VNCCS-style).
        
        Args:
            name: Character folder name
            field: Info field (sex/age/race/eyes/hair/face/body/skin_color)
            
        Returns:
            Info field value
        """
        data = cls.load_character(name)
        if not data:
            return ""
        
        info = data.get('Info', data.get('info', {}))
        if not info:
            return ""
        
        field_lower = field.lower()
        return str(info.get(field_lower, ""))
    
    @classmethod
    def replace(cls, text):
        """
        Replace all character patterns in text.
        
        Supports:
            @@character:outfit:emotion@@         - Original syntax
            @@character.costume.name@@           - Full costume
            @@character.costume.name.part@@      - Specific part
            @@character.emotion.name@@           - Emotion
            @@character.info.field@@             - Character info field
        
        Args:
            text: Input text with character references
            
        Returns:
            Text with character references expanded
        """
        # Extended pattern for dot-notation: @@char.category.name(.part)?@@
        dot_pattern = re.compile(r'@@([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9_-]+))?@@')
        
        def _replace_dot(match):
            char_name = match.group(1)
            category = match.group(2).lower()  # costume, emotion, info
            item_name = match.group(3)
            sub_item = match.group(4)  # May be None (for costume parts)
            
            if category == 'costume':
                return cls.get_costume_parts(char_name, item_name, sub_item)
            elif category == 'emotion':
                return cls.get_emotion(char_name, item_name)
            elif category == 'info':
                return cls.get_info(char_name, item_name)
            else:
                return match.group(0)  # Return unchanged
        
        # Original pattern for colon notation: @@char:outfit:emotion@@
        def _replace_colon(match):
            name = match.group(1)
            outfit = match.group(2)  # May be None
            emotion = match.group(3)  # May be None
            return cls.expand_character(name, outfit, emotion)
        
        # Apply dot notation first (more specific)
        text = dot_pattern.sub(_replace_dot, text)
        
        # Then apply colon notation (original behavior)
        text = cls.pattern.sub(_replace_colon, text)
        
        return text
