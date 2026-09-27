import asyncio
import copy
import glob
import hashlib
import importlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.parse
from collections import Counter
from datetime import datetime, time
from functools import lru_cache

import folder_paths
import yaml
from aiohttp import web
from server import PromptServer
from .version import CORE_API_VERSION, __version__


BASE_DIR = os.path.dirname(__file__)


def _read_overlay_manifest(module_name):
    module_path = os.path.join(BASE_DIR, f"{module_name}.py")
    if not os.path.isfile(module_path):
        return None, "not installed"
    manifest_path = os.path.join(BASE_DIR, f"{module_name}.manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        minimum_api = int(manifest["minimum_core_api"])
        maximum_api = int(manifest["maximum_core_api"])
        bundle_version = str(manifest["bundle_version"])
    except Exception as exc:
        return None, f"error: invalid or missing overlay manifest: {exc}"
    if not minimum_api <= CORE_API_VERSION <= maximum_api:
        return None, (
            f"incompatible: bundle {bundle_version} requires core API "
            f"{minimum_api}..{maximum_api}; installed API is {CORE_API_VERSION}"
        )
    return manifest, None


UI_TOOLS_MANIFEST, _UI_TOOLS_ERROR = _read_overlay_manifest("optional_ui_tools")
UI_TOOLS_ENABLED = UI_TOOLS_MANIFEST is not None


class _DisabledRouteRegistry:
    def get(self, *args, **kwargs):
        return lambda function: function

    def post(self, *args, **kwargs):
        return lambda function: function


_UI_ROUTES = PromptServer.instance.routes if UI_TOOLS_ENABLED else _DisabledRouteRegistry()

from .nodes_core import (
    DEFAULT_UMI_SETTINGS,
    UMI_SETTINGS,
    UmiSaveImage,
    load_umi_settings,
    validate_processing_settings,
    umi_debug_print,
)
from .shared_utils import _atomic_write_json, get_all_wildcard_paths
if UI_TOOLS_ENABLED:
    from . import series_importer
else:
    series_importer = None
from .nodes_lite import (
    TagLoader,
    FILE_MTIME_CACHE_LITE,
    GLOBAL_CACHE_LITE,
    GLOBAL_INDEX_LITE,
    PROMPT_CACHE_LOCK,
    UmiAIWildcardNodeLite,
    UmiBypassModelSwitch,
    UmiPromptInspector,
    UmiPromptPreset,
    UmiPromptProfile,
    UmiPromptSyntaxLint,
    UmiTextBypass,
)


WEB_DIRECTORY = "./js"
CIVITAI_SITE_BASE = "https://civitai.red"
CIVITAI_LEGACY_BASE = "https://civitai.com"
DANBOORU_BASE = "https://danbooru.donmai.us"
DANBOORU_TAG_CACHE = None

# One lock per runtime JSON file that can be written concurrently. Atomic
# replacement keeps the files parseable; these locks keep read-modify-write
# flows from losing updates to each other.
_IMAGE_ANNOTATIONS_LOCK = threading.Lock()
_IMAGE_SCAN_CACHE_LOCK = threading.Lock()
_CIVITAI_CACHE_LOCK = threading.Lock()
_LORA_OVERRIDES_LOCK = threading.Lock()

# Non-blocking guard so only one Civitai batch fetch runs at a time. Never
# held while parsing requests; acquired for the duration of the batch loop.
_CIVITAI_BATCH_GUARD = threading.Lock()


def _is_path_inside(path, root):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except (OSError, ValueError):
        return False


def _safe_join(root, *parts):
    candidate = os.path.abspath(os.path.join(root, *parts))
    if not _is_path_inside(candidate, root):
        return None
    return candidate


def _wildcard_root():
    return os.path.join(BASE_DIR, "wildcards")


# The editor handles both. Text files are one candidate per line; YAML files
# are a mapping of named entries. Everything else in wildcards/ is ignored.
WILDCARD_EXTENSIONS = ("txt", "yaml", "yml")


def _normalize_wildcard_name(name):
    normalized = str(name or "").replace("\\", "/").strip().strip("/")
    for ext in WILDCARD_EXTENSIONS:
        if normalized.lower().endswith("." + ext):
            normalized = normalized[: -(len(ext) + 1)]
            break
    normalized = re.sub(r"[^A-Za-z0-9_./ -]+", "_", normalized).strip(" .")
    return normalized


def _wildcard_ext(value, default="txt"):
    """Normalise a requested extension, refusing anything unrecognised.

    Defaults to txt so every existing caller keeps working without sending it.
    """
    ext = str(value or default).strip().lstrip(".").lower()
    return ext if ext in WILDCARD_EXTENSIONS else default


def _is_yaml_ext(ext):
    return _wildcard_ext(ext) in ("yaml", "yml")


def _wildcard_file_path(name, ext="txt"):
    existing = _safe_join(_wildcard_root(), f"{str(name or '').replace(chr(92), '/')}.{_wildcard_ext(ext)}")
    if existing and os.path.isfile(existing):
        return existing
    normalized = _normalize_wildcard_name(name)
    if not normalized:
        return None
    return _safe_join(_wildcard_root(), f"{normalized}.{_wildcard_ext(ext)}")


def _content_version(text):
    """Identifies the text an editor started from, so an overwrite can tell
    whether the file changed underneath it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_yaml_text(text):
    """None when the text is a usable wildcard mapping, else why it is not.

    Saving a YAML file that does not parse means it stops matching anything,
    with nothing said about it until someone notices a prompt has gone quiet.
    """
    if not str(text or "").strip():
        return None
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        return "YAML did not parse: " + str(exc).split("\n")[0]
    if data is None:
        return None
    if not isinstance(data, dict):
        return "A YAML wildcard must be a mapping of entry names, not a list or a bare value."
    return None


def _count_yaml_entries(path):
    """Candidates in a YAML wildcard, and why it cannot be read if it cannot.

    A YAML file's candidates are its named entries, not its lines, so counting
    lines the way a text wildcard is counted would report a number that means
    nothing to the person reading it.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            data = yaml.safe_load(handle)
    except Exception as exc:
        return None, str(exc).split("\n")[0]
    if data is None:
        return 0, None
    if not isinstance(data, dict):
        return None, "the file is not a mapping of entries"
    return sum(1 for value in data.values() if isinstance(value, dict)), None


def _list_wildcard_text_files():
    root = _wildcard_root()
    files = []
    if not os.path.isdir(root):
        return files
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.lower().endswith(".txt"):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root).replace("\\", "/")
            files.append(rel[:-4])
    return sorted(files, key=str.lower)


def _image_browser_data_path():
    return os.path.join(BASE_DIR, "image_browser_data.json")


def _image_scan_cache_path():
    return os.path.join(BASE_DIR, "cache", "image_scan_cache.json")


def _load_image_annotations():
    path = _image_browser_data_path()
    if not os.path.exists(path):
        return {"items": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"items": {}}
        items = data.get("items")
        if not isinstance(items, dict):
            data["items"] = {}
        return data
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed loading image browser annotations: {e}")
        return {"items": {}}


def _save_image_annotations(data):
    _atomic_write_json(_image_browser_data_path(), data, indent=2)


def _load_image_scan_cache():
    path = _image_scan_cache_path()
    if not os.path.exists(path):
        return {"items": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"items": {}}
        if not isinstance(data.get("items"), dict):
            data["items"] = {}
        return data
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed loading image scan cache: {e}")
        return {"items": {}}


def _save_image_scan_cache(data):
    try:
        with _IMAGE_SCAN_CACHE_LOCK:
            os.makedirs(os.path.dirname(_image_scan_cache_path()), exist_ok=True)
            _atomic_write_json(_image_scan_cache_path(), data, indent=2)
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed saving image scan cache: {e}")


def _metadata_has_embedded_details(metadata):
    if not isinstance(metadata, dict):
        return False
    return any(key not in ("width", "height") for key in metadata)


def _derived_has_details(derived):
    if not isinstance(derived, dict):
        return False
    if derived.get("models") or derived.get("loras"):
        return True
    return any(derived.get(key) not in (None, "", []) for key in ("sampler", "steps", "cfg", "seed"))


def _cached_image_metadata(cache_items, relative_path, stat, path, quick):
    cached = cache_items.get(relative_path)
    valid = (
        isinstance(cached, dict)
        and cached.get("size") == stat.st_size
        and cached.get("mtime") == stat.st_mtime
    )
    if valid:
        metadata = cached.get("metadata") if isinstance(cached.get("metadata"), dict) else {}
        derived = cached.get("derived") if isinstance(cached.get("derived"), dict) else {}
        complete = bool(cached.get("metadata_complete"))
        cache_updated = False
        if _metadata_has_embedded_details(metadata):
            if not _derived_has_details(derived):
                derived = _derive_image_metadata(metadata)
                cached["derived"] = derived
                cache_updated = True
            if not complete:
                cached["metadata_complete"] = True
                complete = True
                cache_updated = True
        if metadata and (quick or complete):
            return metadata, derived, cache_updated, complete

    raw_metadata = _metadata_from_image(path, quick=quick)
    read_ok = raw_metadata is not None
    metadata = raw_metadata or {}
    if quick:
        derived = cached.get("derived", {}) if valid and isinstance(cached, dict) else {}
        complete = bool(cached.get("metadata_complete")) if valid and isinstance(cached, dict) else False
    else:
        derived = _derive_image_metadata(metadata)
        # A read that failed must not be remembered as complete, or the file
        # stays blank in the browser until its size or mtime changes again.
        complete = read_ok
    cache_items[relative_path] = {
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "metadata": metadata,
        "derived": derived,
        "metadata_complete": complete,
    }
    return metadata, derived, True, complete


def _image_output_root():
    return os.path.abspath(folder_paths.get_output_directory())


def _image_url(relative_path):
    normalized = relative_path.replace("\\", "/").strip("/")
    subfolder = os.path.dirname(normalized)
    filename = os.path.basename(normalized)
    return "/view?" + urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": "output",
    })


_THUMBNAIL_LOCK = threading.Lock()
_IMAGE_SCAN_TASKS = {}


@lru_cache(maxsize=64)
def _cached_image_thumbnail(path, mtime_ns, ctime_ns, size):
    from PIL import Image, ImageOps
    with Image.open(path) as original:
        # JPEG draft reduces decoding work where the format supports it.
        original.draft("RGB", (512, 512))
        preview = ImageOps.exif_transpose(original)
        preview.thumbnail((512, 512), Image.Resampling.LANCZOS)
        if preview.mode not in ("RGB", "RGBA"):
            preview = preview.convert("RGBA" if "transparency" in preview.info else "RGB")
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG")
        return buffer.getvalue()


def _image_thumbnail_sync(relative_path):
    root = os.path.realpath(_image_output_root())
    path = _safe_join(root, relative_path)
    if path:
        path = os.path.realpath(path)
        if not _is_path_inside(path, root):
            path = None
    if not path or os.path.splitext(path)[1].lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Invalid image path")
    # One decoder at a time bounds peak source-image memory and prevents
    # duplicate generation while another request populates the cache.
    with _THUMBNAIL_LOCK:
        stat = os.stat(path)
        return _cached_image_thumbnail(path, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)


@_UI_ROUTES.get("/umiapp/images/thumbnail")
async def image_thumbnail(request):
    try:
        data = await asyncio.to_thread(_image_thumbnail_sync, request.query.get("relative_path", ""))
        etag = '"' + hashlib.sha256(data).hexdigest() + '"'
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers=headers)
        return web.Response(body=data, content_type="image/png", headers=headers)
    except ValueError:
        return web.json_response({"error": "Invalid image path"}, status=400)
    except FileNotFoundError:
        return web.json_response({"error": "Image no longer exists"}, status=404)
    except Exception:
        logging.exception("[UmiAI] Could not generate image thumbnail")
        return web.json_response({"error": "Could not generate image thumbnail"}, status=500)


def _wildcard_roots():
    roots = [_wildcard_root()]
    try:
        roots.extend(folder_paths.get_folder_paths("wildcards") or [])
    except Exception:
        pass
    try:
        roots.append(os.path.join(folder_paths.models_dir, "wildcards"))
    except Exception:
        pass
    return [os.path.abspath(root) for root in roots if root and os.path.isdir(root)]


def _load_yaml_tags(filepath):
    tags = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            for entry in data.values():
                if isinstance(entry, dict):
                    for tag in entry.get("Tags", []) or []:
                        tags.add(str(tag).strip())
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed reading YAML tags from {filepath}: {e}")
    return tags


def _coerce_number(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value, end_of_day=False):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
        clock = time.max if end_of_day else time.min
        return datetime.combine(parsed, clock).timestamp()
    except ValueError:
        return None


def _find_values_recursive(value, keys):
    found = []
    wanted = {key.lower() for key in keys}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in wanted and item not in (None, ""):
                found.append(item)
            found.extend(_find_values_recursive(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_values_recursive(item, keys))
    return found


def _first_recursive(value, keys):
    values = _find_values_recursive(value, keys)
    return values[0] if values else None


def _metadata_from_image(path, quick=False):
    """Read size and text chunks from an image.

    Returns None when the file could not be read, so callers can avoid caching
    a failed read as a complete one. A file still being written by a running
    generation is the common case.
    """
    metadata = {}
    try:
        from PIL import Image
        with Image.open(path) as img:
            width, height = img.size
            metadata["width"] = width
            metadata["height"] = height
            if quick:
                return metadata
            # Text chunks placed after IDAT only land in img.info once the
            # image data has been consumed, so load() before reading it.
            try:
                img.load()
            except Exception as e:
                umi_debug_print(f"[UmiAI] Partial image data in {path}: {e}")
                return None
            for key, value in (img.info or {}).items():
                if isinstance(value, (str, int, float, bool)):
                    metadata[key] = value
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed reading image metadata from {path}: {e}")
        return None
    return metadata


def _json_metadata(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _derive_image_metadata(metadata):
    prompt_text = " ".join(str(metadata.get(key, "")) for key in ("umi_prompt", "umi_input_prompt", "prompt"))
    prompt_json = _json_metadata(metadata.get("prompt")) or {}
    workflow_json = _json_metadata(metadata.get("workflow")) or {}
    search_root = {"prompt": prompt_json, "workflow": workflow_json}

    models = []
    for value in _find_values_recursive(search_root, ("ckpt_name", "unet_name", "model_name", "model")):
        if isinstance(value, str) and value not in models:
            models.append(value)

    loras = []
    for match in re.finditer(r'<lora:([^:>]+)', prompt_text, flags=re.IGNORECASE):
        name = match.group(1).strip()
        if name and name not in loras:
            loras.append(name)
    for value in _find_values_recursive(search_root, ("lora_name", "lora")):
        if isinstance(value, str) and value not in loras:
            loras.append(value)

    sampler = _first_recursive(search_root, ("sampler_name", "sampler")) or ""
    steps = _first_recursive(search_root, ("steps",))
    cfg = _first_recursive(search_root, ("cfg", "cfg_scale"))
    seed = _first_recursive(search_root, ("seed", "noise_seed"))

    return {
        "models": models,
        "loras": loras,
        "sampler": str(sampler) if sampler not in (None, "") else "",
        "steps": steps,
        "cfg": cfg,
        "seed": seed,
    }


def _image_matches_query(item, query):
    metadata = item.get("metadata", {})
    derived = item.get("derived", {})
    annotations = item.get("annotations", {})

    search = (query.get("search", "") or "").strip().lower()
    if search:
        haystack = " ".join([
            item.get("filename", ""),
            item.get("relative_path", ""),
            str(metadata.get("umi_prompt", "")),
            str(metadata.get("umi_negative", "")),
            str(metadata.get("prompt", "")),
            " ".join(derived.get("models", [])),
            " ".join(derived.get("loras", [])),
            " ".join(annotations.get("tags", [])),
        ]).lower()
        if search not in haystack:
            return False

    if query.get("favorites") == "1" and not annotations.get("favorite"):
        return False

    date_from = _parse_date(query.get("date_from"))
    date_to = _parse_date(query.get("date_to"), end_of_day=True)
    if date_from and item.get("mtime", 0) < date_from:
        return False
    if date_to and item.get("mtime", 0) > date_to:
        return False

    for field, key in (("steps", "steps"), ("cfg", "cfg"), ("width", "width"), ("height", "height")):
        value = _coerce_number(derived.get(key) if key in derived else metadata.get(key))
        min_value = _coerce_number(query.get(f"{field}_min"))
        max_value = _coerce_number(query.get(f"{field}_max"))
        if min_value is not None and (value is None or value < min_value):
            return False
        if max_value is not None and (value is None or value > max_value):
            return False

    orientation = (query.get("orientation", "any") or "any").lower()
    width = _coerce_number(metadata.get("width"))
    height = _coerce_number(metadata.get("height"))
    if orientation == "portrait" and width is not None and height is not None and width >= height:
        return False
    if orientation == "landscape" and width is not None and height is not None and width <= height:
        return False
    if orientation == "square" and width is not None and height is not None and width != height:
        return False

    folder = query.get("folder")
    if folder and item.get("folder") != folder:
        return False

    def _matches_any(param, values):
        requested = {part.strip() for part in (query.get(param, "") or "").split(",") if part.strip()}
        return not requested or bool(requested.intersection(set(values)))

    if not _matches_any("models", derived.get("models", [])):
        return False
    if not _matches_any("loras", derived.get("loras", [])):
        return False
    if not _matches_any("samplers", [derived.get("sampler", "")]):
        return False
    if not _matches_any("tags", annotations.get("tags", [])):
        return False

    return True


def _facet_items(counter):
    return [{"name": name, "count": count} for name, count in counter.most_common() if name]


def _split_danbooru_tags(value):
    return [tag for tag in str(value or "").split() if tag]


def _load_danbooru_tag_cache():
    global DANBOORU_TAG_CACHE
    if DANBOORU_TAG_CACHE is not None:
        return DANBOORU_TAG_CACHE

    tags = set()
    tag_dir = os.path.join(BASE_DIR, "autocomplete-tags")
    if os.path.isdir(tag_dir):
        for csv_path in glob.glob(os.path.join(tag_dir, "*.csv")):
            if "danbooru" not in os.path.basename(csv_path).lower():
                continue
            try:
                with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        tag = line.split(",", 1)[0].strip()
                        if tag:
                            tags.add(tag)
            except Exception as e:
                umi_debug_print(f"[UmiAI] Failed loading Danbooru tag cache from {csv_path}: {e}")
    DANBOORU_TAG_CACHE = tags
    return DANBOORU_TAG_CACHE


def _danbooru_tag_exists(tag):
    clean = str(tag or "").strip()
    return bool(clean) and clean in _load_danbooru_tag_cache()


def _normalize_danbooru_chunk(chunk):
    clean = str(chunk or "").strip()
    if not clean:
        return []
    if not re.search(r"\s", clean):
        return [clean]

    candidate = re.sub(r"\s+", "_", clean)
    if _danbooru_tag_exists(candidate):
        return [candidate]

    words = [word.strip() for word in clean.split() if word.strip()]
    tokens = []
    index = 0
    while index < len(words):
        matched = None
        max_words = min(4, len(words) - index)
        for size in range(max_words, 1, -1):
            candidate = "_".join(words[index:index + size])
            if _danbooru_tag_exists(candidate):
                matched = candidate
                index += size
                break
        if matched:
            tokens.append(matched)
        else:
            tokens.append(words[index])
            index += 1
    return tokens


def _normalize_danbooru_search_tags(value):
    raw = str(value or "").strip()
    if not raw:
        return ""

    tokens = []
    chunks = [part.strip() for part in re.split(r"[,;\n\r]+", raw) if part.strip()]
    for chunk in chunks:
        tokens.extend(_normalize_danbooru_chunk(chunk))

    normalized = []
    seen = set()
    for token in tokens:
        clean = token.strip().strip(",")
        if not clean:
            continue
        if ":" not in clean:
            clean = clean.replace(" ", "_")
        if clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    return " ".join(normalized)


def _limit_danbooru_public_query(tags, has_auth):
    if has_auth:
        return tags

    content_tags = []
    meta_tags = []
    for token in str(tags or "").split():
        if ":" in token:
            meta_tags.append(token)
        else:
            content_tags.append(token)
    if len(content_tags) <= 2:
        return tags
    return " ".join(content_tags[:2] + meta_tags)


def _safe_int(value, default, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _danbooru_media_variant_url(post, preferred_types):
    media_asset = post.get("media_asset")
    variants = media_asset.get("variants") if isinstance(media_asset, dict) else None
    if not isinstance(variants, list):
        return None
    by_type = {
        str(variant.get("type") or ""): variant.get("url")
        for variant in variants
        if isinstance(variant, dict) and variant.get("url")
    }
    for variant_type in preferred_types:
        url = by_type.get(variant_type)
        if url:
            return url
    for url in by_type.values():
        if url:
            return url
    return None


def _response_text_sample(response):
    try:
        return response.text[:1000]
    except Exception:
        return ""


def _is_cloudflare_challenge(response):
    text = _response_text_sample(response).lower()
    return response.status_code in (403, 503) and (
        "cloudflare" in text
        or "just a moment" in text
        or "enable javascript and cookies" in text
    )


def _danbooru_get_posts(params, headers, auth):
    try:
        from curl_cffi import requests as curl_requests
        curl_headers = dict(headers)
        curl_headers.pop("User-Agent", None)
        return curl_requests.get(
            f"{DANBOORU_BASE}/posts.json",
            params=params,
            headers=curl_headers,
            auth=auth,
            timeout=20,
            impersonate="chrome",
        )
    except ImportError:
        pass

    import requests
    return requests.get(
        f"{DANBOORU_BASE}/posts.json",
        params=params,
        headers=headers,
        auth=auth,
        timeout=20,
    )


def _is_allowed_danbooru_image_url(url):
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return False
    return parsed.scheme == "https" and parsed.netloc.lower() in {
        "cdn.donmai.us",
        "danbooru.donmai.us",
    }


_PREVIEW_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif",
    ".mp4", ".webm", ".mov",
}


def _is_allowed_lora_preview_file(path):
    return (
        bool(path)
        and os.path.isfile(path)
        and os.path.splitext(path)[1].lower() in _PREVIEW_MEDIA_EXTENSIONS
    )


def _danbooru_image_proxy_url(url):
    if not url:
        return ""
    return "/umiapp/danbooru/image?" + urllib.parse.urlencode({"url": url})


def _danbooru_get_image(url):
    headers = {
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": f"{DANBOORU_BASE}/",
    }
    try:
        from curl_cffi import requests as curl_requests
        return curl_requests.get(
            url,
            headers=headers,
            timeout=30,
            impersonate="chrome",
        )
    except ImportError:
        pass

    import requests
    headers["User-Agent"] = "Mozilla/5.0"
    return requests.get(url, headers=headers, timeout=30)


def _danbooru_post_payload(post):
    categories = {
        "artist": _split_danbooru_tags(post.get("tag_string_artist")),
        "copyright": _split_danbooru_tags(post.get("tag_string_copyright")),
        "character": _split_danbooru_tags(post.get("tag_string_character")),
        "general": _split_danbooru_tags(post.get("tag_string_general")),
        "meta": _split_danbooru_tags(post.get("tag_string_meta")),
    }
    all_tags = []
    for tags in categories.values():
        for tag in tags:
            if tag not in all_tags:
                all_tags.append(tag)
    preview_url = post.get("preview_file_url") or _danbooru_media_variant_url(post, ("180x180", "360x360")) or post.get("large_file_url") or post.get("file_url")
    large_url = post.get("large_file_url") or _danbooru_media_variant_url(post, ("sample", "720x720", "original")) or post.get("file_url") or post.get("preview_file_url")
    file_url = post.get("file_url") or _danbooru_media_variant_url(post, ("original", "sample")) or post.get("large_file_url") or post.get("preview_file_url")
    return {
        "id": post.get("id"),
        "rating": post.get("rating"),
        "score": post.get("score"),
        "source": post.get("source") or "",
        "post_url": f"{DANBOORU_BASE}/posts/{post.get('id')}",
        "preview_url": _danbooru_image_proxy_url(preview_url),
        "large_url": _danbooru_image_proxy_url(large_url),
        "file_url": _danbooru_image_proxy_url(file_url),
        "source_preview_url": preview_url or "",
        "source_large_url": large_url or "",
        "source_file_url": file_url or "",
        "width": post.get("image_width"),
        "height": post.get("image_height"),
        "tags": categories,
        "all_tags": all_tags,
    }


def _format_tag_line(tags, separator=", "):
    seen = []
    for tag in tags or []:
        clean = str(tag).strip().replace(" ", "_")
        if clean and clean not in seen:
            seen.append(clean)
    return separator.join(seen)


def _wildcard_sources():
    return {hashlib.sha256(os.path.normcase(os.path.abspath(root)).encode('utf-8')).hexdigest()[:16]: root
            for root in get_all_wildcard_paths()}


def get_wildcard_data():
    # Use the execution catalog, including external roots, YML and CSV. Legacy
    # `files` remains TXT-only for older consumers; `wildcards` is the full list.
    with PROMPT_CACHE_LOCK:
        loader = TagLoader(get_all_wildcard_paths(), {'verbose': False, 'use_folder_paths': True})
        sources = {}
        txt_files = set()
        yaml_files = set()
        basenames = {}
        source_ids = {root: key for key, root in _wildcard_sources().items()}
        for entry in loader.file_catalog:
            key, extension = os.path.splitext(entry['relative_path'])
            if extension == '.txt':
                txt_files.add(key)
            elif extension in ('.yaml', '.yml'):
                yaml_files.add(key)
            basenames.setdefault(key.rsplit('/', 1)[-1], key)
            sources.setdefault(key, []).append({
                'source': source_ids.get(entry['root']), 'root': entry['root'],
                'relative_path': entry['relative_path'], 'ext': extension[1:],
            })
        return {
            'files': sorted(txt_files), 'wildcards': sorted(sources),
            'prompt_files': sorted(txt_files), 'yaml_files': sorted(yaml_files),
            'tags': sorted(loader.umi_tags),
            'entry_names': sorted(str(info['entry_key']) for info in loader.entry_names.values()),
            'sources': sources, 'basenames': basenames,
            'loras': _get_lora_filename_list(),
            'lint_cleaner_enabled': UMI_SETTINGS.get('lint_cleaner_enabled', False),
        }


def _all_wildcard_details():
    data = get_wildcard_data()
    bundled = {(e['name'], e.get('ext', 'txt')): e for e in _wildcard_text_details()}
    details = []
    local = os.path.normcase(os.path.abspath(_wildcard_root()))
    for name, sources in data['sources'].items():
        for priority, source in enumerate(sources):
            is_local = os.path.normcase(os.path.abspath(source['root'])) == local
            detail = dict(bundled.get((name, source['ext']), {}) if is_local else {})
            detail.update(name=name, **source, lines=detail.get('lines'),
                          readonly=not is_local or source['ext'] == 'csv',
                          alternatives=len(sources), priority=priority)
            details.append(detail)
    return details


def _target_lora_path(filename):
    return folder_paths.get_full_path("loras", filename)


def _get_lora_filename_list(force=False):
    if force:
        try:
            folder_paths.filename_list_cache.pop("loras", None)
        except Exception:
            pass

    try:
        names = set(folder_paths.get_filename_list("loras"))
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed loading LoRAs from folder_paths: {e}")
        names = set()

    if not force and names:
        return sorted(name.replace("\\", "/") for name in names)

    try:
        lora_exts = folder_paths.folder_names_and_paths.get("loras", ([], set()))[1]
        for root in folder_paths.get_folder_paths("loras"):
            if not os.path.isdir(root):
                continue
            for dirpath, _, filenames in os.walk(root):
                for filename in filenames:
                    if os.path.splitext(filename)[1].lower() not in lora_exts:
                        continue
                    names.add(os.path.relpath(os.path.join(dirpath, filename), root))
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed fallback LoRA scan: {e}")

    return sorted(name.replace("\\", "/") for name in names)


def _lora_companion_paths(full_path):
    base, _ = os.path.splitext(full_path)
    candidates = [
        full_path,
        f"{base}.civitai.info",
        f"{base}.json",
    ]
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidates.append(f"{base}.preview{ext}")
        candidates.append(f"{base}{ext}")
    return candidates


def _resolved_lora_roots():
    """Realpath-resolved LoRA model roots; deletions must stay inside these."""
    try:
        candidates = folder_paths.get_folder_paths("loras") or []
    except Exception:
        candidates = []
    roots = []
    for root in candidates:
        try:
            if root and os.path.isdir(root):
                roots.append(os.path.realpath(root))
        except OSError:
            continue
    return roots


def _real_path_inside_any(path, roots):
    """Return the symlink-resolved path if it lies inside one of the resolved
    roots, else None. Resolving first means a symlinked directory inside a
    root cannot redirect operations outside it."""
    try:
        real = os.path.realpath(path)
    except OSError:
        return None
    real_cmp = os.path.normcase(real)
    for root in roots:
        root_cmp = os.path.normcase(root)
        try:
            if os.path.commonpath([real_cmp, root_cmp]) == root_cmp:
                return real
        except ValueError:
            continue
    return None


def _delete_lora_files_sync(lora_name):
    """Delete a LoRA file and its companion files. Returns (payload, status)."""
    full_path = _target_lora_path(lora_name)
    if not full_path or not os.path.exists(full_path):
        return {"success": False, "error": "LoRA not found"}, 404
    roots = _resolved_lora_roots()
    real_full = _real_path_inside_any(full_path, roots)
    if real_full is None or not os.path.isfile(real_full):
        return {"success": False, "error": "LoRA path is not a file inside the allowed LoRA folders"}, 400
    deleted = []
    lora_dir = os.path.dirname(full_path)
    for candidate in _lora_companion_paths(full_path):
        if not os.path.isfile(candidate):
            continue
        if _real_path_inside_any(candidate, roots) is None:
            continue
        os.remove(candidate)
        deleted.append(os.path.relpath(candidate, lora_dir).replace("\\", "/"))
    target_key = _lora_key(lora_name).lower()
    with _LORA_OVERRIDES_LOCK:
        overrides = _load_lora_overrides()
        next_overrides = {
            key: value for key, value in overrides.items()
            if _lora_key(key).lower() != target_key
        }
        if len(next_overrides) != len(overrides):
            _save_lora_overrides(next_overrides)
    with _CIVITAI_CACHE_LOCK:
        cache = _load_civitai_cache()
        next_cache = {
            key: value for key, value in cache.items()
            if _lora_key(key).lower() != target_key
        }
        if len(next_cache) != len(cache):
            _save_civitai_cache(next_cache)
    return {"success": True, "deleted": deleted}, 200


def _lora_overrides_path():
    return os.path.join(BASE_DIR, "lora_overrides.json")


def _load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception as e:
        umi_debug_print(f"[UmiAI] Failed loading {path}: {e}")
        return default


def _save_json_file(path, data):
    _atomic_write_json(path, data, indent=2)


def _load_lora_overrides():
    return _load_json_file(_lora_overrides_path(), {})


def _save_lora_overrides(data):
    _save_json_file(_lora_overrides_path(), data)


def _load_civitai_cache():
    return _load_json_file(os.path.join(BASE_DIR, "civitai_cache.json"), {})


def _save_civitai_cache(data):
    _save_json_file(os.path.join(BASE_DIR, "civitai_cache.json"), data)


def _merge_civitai_cache_entries(entries):
    """Merge freshly fetched entries into the on-disk Civitai cache under a
    lock, re-reading the file first so concurrent single/batch fetches cannot
    clobber each other's results with a stale snapshot."""
    if not entries:
        return
    with _CIVITAI_CACHE_LOCK:
        cache = _load_civitai_cache()
        cache.update(entries)
        _save_civitai_cache(cache)


def _to_civitai_red_url(value):
    if not isinstance(value, str):
        return value
    return value.replace(CIVITAI_LEGACY_BASE, CIVITAI_SITE_BASE).replace("http://civitai.com", CIVITAI_SITE_BASE)


def _normalize_civitai_entry(entry):
    if not isinstance(entry, dict):
        return {}
    normalized = dict(entry)
    for key in ("url", "model_url", "creator_url"):
        if key in normalized:
            normalized[key] = _to_civitai_red_url(normalized[key])
    if not normalized.get("url") and normalized.get("id"):
        normalized["url"] = f"{CIVITAI_SITE_BASE}/models/{normalized.get('id')}"
    return normalized


def _lora_key(name):
    return os.path.splitext(str(name or "").replace("/", "\\").strip())[0]


def _lora_basename(key):
    """Path-style-independent basename for cache keys from any OS."""
    return str(key or "").replace("\\", "/").rsplit("/", 1)[-1]


def _find_lora_cache_entry(cache, name):
    key = _lora_key(name).lower()
    base = _lora_basename(key)
    # A basename fallback is useful for caches created before folders were
    # recorded, but it must never shadow an exact path match.
    exact = _find_exact_lora_cache_entry(cache, name)
    if exact:
        return exact
    for cache_key, value in cache.items():
        normalized = _lora_key(cache_key).lower()
        if _lora_basename(normalized) == base:
            return _normalize_civitai_entry(value)
    return {}


def _find_exact_lora_cache_entry(cache, name):
    key = _lora_key(name).lower()
    for cache_key, value in cache.items():
        normalized = _lora_key(cache_key).lower()
        if normalized == key:
            return _normalize_civitai_entry(value)
    return {}


def _build_civitai_cache_index(cache):
    """One-pass index over the Civitai cache so a listing request does not
    rescan the whole cache per LoRA. Exact relative paths take priority over
    the first legacy basename match."""
    exact = {}
    by_base = {}
    for position, (cache_key, value) in enumerate(cache.items()):
        normalized = _lora_key(cache_key).lower()
        if normalized not in exact:
            exact[normalized] = (position, value)
        base = _lora_basename(normalized)
        if base not in by_base:
            by_base[base] = (position, value)
    return exact, by_base


def _find_lora_cache_entry_indexed(index, name):
    exact, by_base = index
    key = _lora_key(name).lower()
    base = _lora_basename(key)
    match = exact.get(key) or by_base.get(base)
    return _normalize_civitai_entry(match[1]) if match is not None else {}


def _sha256_file(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _cached_lora_sha256(cache, lora_name, full_path):
    """Return (sha256, size, mtime) for a LoRA file, reusing the hash stored
    in the cache entry for this exact key when the file's size and mtime are
    unchanged. Avoids re-reading multi-GB files on repeat Civitai fetches."""
    stat = os.stat(full_path)
    cached = cache.get(lora_name)
    if isinstance(cached, dict):
        sha = cached.get("sha256")
        if sha and cached.get("hash_size") == stat.st_size and cached.get("hash_mtime") == stat.st_mtime:
            return sha, stat.st_size, stat.st_mtime
    return _sha256_file(full_path), stat.st_size, stat.st_mtime


def _civitai_tags(model):
    tags = model.get("tags") if isinstance(model, dict) else []
    if not isinstance(tags, list):
        return []
    clean = []
    for tag in tags:
        if isinstance(tag, dict):
            value = tag.get("name")
        else:
            value = tag
        value = str(value or "").strip()
        if value and value not in clean:
            clean.append(value)
    return clean


def _civitai_creator_name(model):
    if not isinstance(model, dict):
        return ""
    creator = model.get("creator")
    if isinstance(creator, dict):
        return str(creator.get("username") or creator.get("name") or "").strip()
    return str(creator or "").strip()


def _civitai_preview_url(version):
    images = version.get("images") if isinstance(version, dict) else []
    if not isinstance(images, list):
        return ""
    for image in images:
        if not isinstance(image, dict):
            continue
        url = image.get("url")
        if url:
            return str(url)
    return ""


def _preview_prompt_text(meta, *keys):
    if not isinstance(meta, dict):
        return ""
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _civitai_preview_prompts_from_images(images):
    if not isinstance(images, list):
        return []
    prompts = []
    for idx, image in enumerate(images):
        if not isinstance(image, dict):
            continue
        meta = image.get("meta") if isinstance(image.get("meta"), dict) else {}
        resources = image.get("resources") if isinstance(image.get("resources"), list) else []
        entry = {
            "index": idx + 1,
            "url": str(image.get("url") or ""),
            "prompt": _preview_prompt_text(meta, "prompt", "Prompt"),
            "negative_prompt": _preview_prompt_text(meta, "negativePrompt", "negative_prompt", "Negative prompt", "Negative Prompt"),
            "model": _preview_prompt_text(meta, "Model", "model", "checkpoint"),
            "sampler": _preview_prompt_text(meta, "sampler", "Sampler"),
            "scheduler": _preview_prompt_text(meta, "scheduler", "Schedule type", "Schedule Type"),
            "steps": meta.get("steps") or meta.get("Steps") or "",
            "cfg_scale": meta.get("cfgScale") or meta.get("cfg_scale") or meta.get("CFG scale") or "",
            "seed": meta.get("seed") or meta.get("Seed") or "",
            "size": _preview_prompt_text(meta, "Size", "size"),
            "resources": [
                {
                    "name": str(resource.get("name") or ""),
                    "type": str(resource.get("type") or ""),
                    "weight": resource.get("weight", ""),
                }
                for resource in resources
                if isinstance(resource, dict) and (resource.get("name") or resource.get("type"))
            ],
        }
        if any(entry.get(key) for key in ("prompt", "negative_prompt", "model", "sampler", "scheduler", "steps", "cfg_scale", "seed", "size", "resources")):
            prompts.append(entry)
    return prompts


def _civitai_preview_prompts(version):
    if not isinstance(version, dict):
        return []
    return _civitai_preview_prompts_from_images(version.get("images"))


def _civitai_nsfw_label(version, model):
    value = None
    if isinstance(model, dict):
        value = model.get("nsfw")
    if value is None and isinstance(version, dict):
        value = version.get("nsfw") or version.get("nsfwLevel")
    if value in (None, False, 0, "0", ""):
        return "None"
    if value is True:
        return "Yes"
    return str(value)


def _civitai_cache_entry_from_version(version):
    if not isinstance(version, dict):
        return {}
    model = version.get("model") if isinstance(version.get("model"), dict) else {}
    model_id = version.get("modelId") or model.get("id")
    version_id = version.get("id")
    trained_words = version.get("trainedWords") or version.get("triggerWords") or []
    if not isinstance(trained_words, list):
        trained_words = []
    entry = {
        "id": model_id,
        "model_version_id": version_id,
        "name": model.get("name") or version.get("modelName") or version.get("name") or "",
        "version_name": version.get("name") or "",
        "description": model.get("description") or version.get("description") or "",
        "tags": _civitai_tags(model),
        "creator": _civitai_creator_name(model),
        "url": f"{CIVITAI_SITE_BASE}/models/{model_id}" if model_id else "",
        "trigger_words": [str(word).strip() for word in trained_words if str(word).strip()],
        "base_model": version.get("baseModel") or version.get("base_model") or "",
        "preview_url": _civitai_preview_url(version),
        "preview_prompts": _civitai_preview_prompts(version),
        "nsfw": _civitai_nsfw_label(version, model),
    }
    return _normalize_civitai_entry({k: v for k, v in entry.items() if v not in (None, "", [])})


def _civitai_info_sidecar_from_entry(entry, version):
    data = dict(version) if isinstance(version, dict) else {}
    if entry:
        data.setdefault("modelId", entry.get("id"))
        data.setdefault("modelVersionId", entry.get("model_version_id"))
        data.setdefault("modelName", entry.get("name"))
        data.setdefault("name", entry.get("version_name") or entry.get("name"))
        data.setdefault("baseModel", entry.get("base_model"))
        data.setdefault("trainedWords", entry.get("trigger_words", []))
        data.setdefault("description", entry.get("description", ""))
        data.setdefault("preview_url", entry.get("preview_url", ""))
        data.setdefault("url", entry.get("url", ""))
    return data


def _fetch_civitai_version_by_hash(file_hash, api_token=None):
    import requests

    headers = {
        "Accept": "application/json",
        "User-Agent": "UmiAI-ComfyUI/1.0",
    }
    api_token = str(api_token or "").strip() or os.environ.get("CIVITAI_API_TOKEN") or os.environ.get("CIVITAI_API_KEY")
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    errors = []
    for base_url in (CIVITAI_SITE_BASE, CIVITAI_LEGACY_BASE):
        url = f"{base_url}/api/v1/model-versions/by-hash/{file_hash}"
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 404:
                errors.append(f"Not found on {base_url}")
                continue
            if response.status_code in (401, 403):
                errors.append(f"{base_url} returned HTTP {response.status_code}; set CIVITAI_API_TOKEN if this model needs account access")
                continue
            if response.status_code != 200:
                errors.append(f"{base_url} returned HTTP {response.status_code}")
                continue
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                errors.append(f"{base_url}: {payload.get('error')}")
                continue
            return payload, base_url
        except Exception as e:
            errors.append(f"{base_url}: {e}")
    raise RuntimeError("; ".join(errors) or "CivitAI lookup failed")


def _write_lora_metadata_files(full_path, entry, version, mode):
    base, _ = os.path.splitext(full_path)
    if mode == "update_missing":
        civitai_path = f"{base}.civitai.info"
        json_path = f"{base}.json"
        if not os.path.exists(civitai_path):
            _save_json_file(civitai_path, _civitai_info_sidecar_from_entry(entry, version))
        if not os.path.exists(json_path):
            _save_json_file(json_path, entry)
        return
    if mode in {"replace_civitai_info", "replace_json_and_civitai", "replace_all"}:
        _save_json_file(f"{base}.civitai.info", _civitai_info_sidecar_from_entry(entry, version))
    if mode in {"replace_json_info", "replace_json_and_civitai", "replace_all"}:
        _save_json_file(f"{base}.json", entry)


def _lora_preview_paths(full_path):
    base, _ = os.path.splitext(full_path)
    paths = []
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        paths.extend((f"{base}.preview{ext}", f"{base}{ext}"))
    return paths


def _validated_preview_bytes(data):
    if not data:
        raise ValueError("Preview image is empty")
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Preview image exceeds the 25 MB limit")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            image_format = str(image.format or "").upper()
            image.verify()
    except Exception as e:
        raise ValueError(f"Invalid preview image: {e}") from e
    extensions = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
    if image_format not in extensions:
        raise ValueError("Preview must be a PNG, JPEG, or WebP image")
    return extensions[image_format]


def _write_lora_preview(full_path, data, replace=True):
    ext = _validated_preview_bytes(data)
    base, _ = os.path.splitext(full_path)
    destination = f"{base}.preview{ext}"
    temp_path = f"{destination}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
        if replace:
            for candidate in _lora_preview_paths(full_path):
                if candidate != destination and os.path.isfile(candidate):
                    os.remove(candidate)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return destination


def _download_lora_preview(full_path, url, replace=True):
    if not str(url or "").lower().startswith(("https://", "http://")):
        raise ValueError("CivitAI did not provide a preview URL")
    import requests
    response = requests.get(
        url,
        headers={"Accept": "image/*", "User-Agent": "UmiAI-ComfyUI/1.0"},
        stream=True,
        timeout=30,
    )
    response.raise_for_status()
    content_length = _safe_int(response.headers.get("Content-Length"), 0, minimum=0)
    if content_length > 25 * 1024 * 1024:
        raise ValueError("Preview image exceeds the 25 MB limit")
    data = bytearray()
    for chunk in response.iter_content(64 * 1024):
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > 25 * 1024 * 1024:
            raise ValueError("Preview image exceeds the 25 MB limit")
    return _write_lora_preview(full_path, bytes(data), replace=replace)


def _update_lora_preview_from_entry(full_path, entry, mode):
    has_preview = any(os.path.isfile(path) for path in _lora_preview_paths(full_path))
    should_replace = mode in {"replace_previews", "replace_all"}
    should_fill = mode == "update_missing" and not has_preview
    if not should_replace and not should_fill:
        return False, ""
    try:
        _download_lora_preview(full_path, entry.get("preview_url"), replace=should_replace)
        return True, ""
    except Exception as e:
        return False, str(e)


def _fetch_and_cache_lora_civitai(lora_name, cache, mode="update_missing", api_token=None):
    full_path = _target_lora_path(lora_name)
    if not full_path or not os.path.exists(full_path):
        return {"success": False, "error": "LoRA not found", "lora_name": lora_name}
    real_full = _real_path_inside_any(full_path, _resolved_lora_roots())
    if real_full is None or not os.path.isfile(real_full):
        return {"success": False, "error": "LoRA is outside the allowed LoRA folders", "lora_name": lora_name}
    full_path = real_full

    # Mutation must never trust an ambiguous legacy basename match: doing so
    # can write another folder's metadata beside this LoRA.
    existing = _find_exact_lora_cache_entry(cache, lora_name)
    if existing and mode == "update_missing":
        _write_lora_metadata_files(full_path, existing, existing, mode)
        preview_updated, preview_error = _update_lora_preview_from_entry(full_path, existing, mode)
        result = {
            "success": True,
            "cached": True,
            "updated": preview_updated,
            "preview_updated": preview_updated,
            "entry": existing,
        }
        if preview_error:
            result["warning"] = f"Metadata updated, but preview download failed: {preview_error}"
        return result

    try:
        file_hash, file_size, file_mtime = _cached_lora_sha256(cache, lora_name, full_path)
        version, source = _fetch_civitai_version_by_hash(file_hash, api_token=api_token)
    except Exception as e:
        return {"success": False, "error": str(e), "lora_name": lora_name}

    entry = _civitai_cache_entry_from_version(version)
    if not entry:
        return {"success": False, "error": "CivitAI response did not include model info", "lora_name": lora_name}

    entry["sha256"] = file_hash
    entry["hash_size"] = file_size
    entry["hash_mtime"] = file_mtime
    cache[lora_name] = entry
    _write_lora_metadata_files(full_path, entry, version, mode)
    preview_updated, preview_error = _update_lora_preview_from_entry(full_path, entry, mode)
    result = {
        "success": True,
        "cached": False,
        "updated": True,
        "preview_updated": preview_updated,
        "source": source,
        "entry": entry,
    }
    if preview_error:
        result["warning"] = f"Metadata updated, but preview download failed: {preview_error}"
    return result


@lru_cache(maxsize=256)
def _cached_lora_sidecar_json(path, mtime_ns, ctime_ns, size):
    # Stat fields form the freshness key. Failed parses are never cached.
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_lora_sidecar_json(full_path, suffix):
    base, _ = os.path.splitext(full_path)
    path = f"{base}{suffix}"
    try:
        stat = os.stat(path)
        # Avoid retaining unusually large metadata files in memory.
        if stat.st_size > 256 * 1024:
            return _load_json_file(path, {})
        value = _cached_lora_sidecar_json(path, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        return copy.deepcopy(value) if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_lora_metadata_tags(full_path):
    tags = []
    try:
        from safetensors import safe_open
        with safe_open(full_path, framework="pt", device="cpu") as f:
            metadata = f.metadata() or {}
        raw = metadata.get("ss_tag_frequency") or metadata.get("tag_frequency")
        if raw:
            data = json.loads(raw) if isinstance(raw, str) else raw
            counts = Counter()
            if isinstance(data, dict):
                for value in data.values():
                    if isinstance(value, dict):
                        for tag, count in value.items():
                            try:
                                counts[str(tag)] += int(count)
                            except Exception:
                                counts[str(tag)] += 1
            tags = [{"tag": tag, "count": count} for tag, count in counts.most_common()]
    except Exception as e:
        umi_debug_print(f"[UmiAI] Could not read LoRA internal tags: {e}")
    return tags


def _collect_loras_sync(force=False):
    """Blocking LoRA collection (filename listing, stat, preview probing,
    sidecar JSON reads, cache/override merging); called via asyncio.to_thread
    so the listing does not stall the aiohttp event loop."""
    loras = []
    base_models = set()
    if force:
        _cached_lora_sidecar_json.cache_clear()
    overrides = _load_lora_overrides()
    civitai_index = _build_civitai_cache_index(_load_civitai_cache())
    for name in _get_lora_filename_list(force=force):
        full_path = _target_lora_path(name)
        if not full_path:
            continue
        base, _ = os.path.splitext(full_path)
        rel_folder = os.path.dirname(name).replace("\\", "/") or "(root)"
        try:
            stat = os.stat(full_path)
            file_size = stat.st_size
            file_mtime = stat.st_mtime
        except Exception:
            file_size = 0
            file_mtime = 0

        local_preview = None
        preview_mtime = 0
        for ext in [".preview.png", ".preview.jpg", ".preview.jpeg", ".preview.webp", ".png", ".jpg", ".jpeg", ".webp"]:
            preview_candidate = f"{base}{ext}"
            if os.path.exists(preview_candidate):
                local_preview = name.rsplit(".", 1)[0] + ext
                try:
                    preview_mtime = os.path.getmtime(preview_candidate)
                except OSError:
                    preview_mtime = 0
                break

        override = overrides.get(name) or overrides.get(_lora_key(name)) or {}
        civitai = _find_lora_cache_entry_indexed(civitai_index, name)
        info = _read_lora_sidecar_json(full_path, ".civitai.info")
        local_json = _read_lora_sidecar_json(full_path, ".json")
        civitai_info_tags = []
        for source in (info, civitai):
            words = source.get("trainedWords") or source.get("trigger_words") or source.get("triggerWords") or []
            if isinstance(words, list):
                civitai_info_tags.extend(str(word) for word in words if str(word).strip())
        base_model = override.get("base_model") or civitai.get("base_model") or info.get("baseModel") or info.get("base_model") or ""
        preview_prompts = civitai.get("preview_prompts")
        if not isinstance(preview_prompts, list):
            preview_prompts = _civitai_preview_prompts_from_images(info.get("images"))
        if base_model:
            base_models.add(str(base_model))

        loras.append({
            "name": name,
            "filename": name,
            "folder": rel_folder,
            "size": file_size,
            "mtime": file_mtime,
            "civitai": civitai,
            "override": override,
            "local": local_json,
            "local_preview": local_preview,
            "preview_mtime": preview_mtime,
            "civitai_info_tags": sorted(set(civitai_info_tags)),
            "preview_prompts": preview_prompts,
            "base_model": str(base_model),
            "tags": civitai.get("tags", []) if isinstance(civitai.get("tags", []), list) else [],
        })
    return {"loras": loras, "base_models": sorted(base_models)}


@_UI_ROUTES.get("/umiapp/loras")
async def get_loras(request):
    force = str(request.query.get("force", "")).lower() in {"1", "true", "yes"}
    try:
        payload = await asyncio.to_thread(_collect_loras_sync, force)
    except Exception as e:
        print(f"[UmiAI] /umiapp/loras failed: {e}")
        traceback.print_exc()
        return web.json_response({
            "success": False,
            "error": f"LoRA listing failed on the server ({type(e).__name__}). Check the ComfyUI log for details.",
            "loras": [],
            "base_models": [],
        }, status=500)
    return web.json_response(payload)


@_UI_ROUTES.post("/umiapp/loras/internal_tags")
async def get_lora_internal_tags(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name") or data.get("filename")
        full_path = _target_lora_path(lora_name)
        if not full_path or not os.path.exists(full_path):
            return web.json_response({"success": False, "error": "LoRA not found", "tag_pairs": []}, status=404)
        return web.json_response({"success": True, "tag_pairs": _read_lora_metadata_tags(full_path)})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "tag_pairs": []}, status=500)


@_UI_ROUTES.post("/umiapp/loras/overrides/save")
async def save_lora_override(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name")
        override = data.get("override") or {}
        if not lora_name or not isinstance(override, dict):
            return web.json_response({"success": False, "error": "Invalid override"}, status=400)
        if "activation_text" in override and "activation_tags" not in override:
            override["activation_tags"] = [part.strip() for part in str(override.get("activation_text") or "").split(",") if part.strip()]
        with _LORA_OVERRIDES_LOCK:
            overrides = _load_lora_overrides()
            overrides[lora_name] = override
            _save_lora_overrides(overrides)
        return web.json_response({"success": True, "override": override})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.post("/umiapp/loras/upload_preview")
async def upload_lora_preview(request):
    try:
        reader = await request.multipart()
        lora_name = ""
        image_bytes = bytearray()
        too_large = False
        async for part in reader:
            if part.name == "lora_name":
                lora_name = (await part.text()).strip()
            elif part.name == "image":
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    image_bytes.extend(chunk)
                    if len(image_bytes) > 25 * 1024 * 1024:
                        too_large = True
                        break
        if too_large:
            return web.json_response({"success": False, "error": "Preview image exceeds the 25 MB limit"}, status=413)
        full_path = _target_lora_path(lora_name)
        if not full_path or not os.path.exists(full_path) or not image_bytes:
            return web.json_response({"success": False, "error": "Missing LoRA or image"}, status=400)
        real_full = _real_path_inside_any(full_path, _resolved_lora_roots())
        if real_full is None or not os.path.isfile(real_full):
            return web.json_response({"success": False, "error": "LoRA is outside the allowed LoRA folders"}, status=400)
        full_path = real_full
        try:
            preview_path = await asyncio.to_thread(_write_lora_preview, full_path, bytes(image_bytes), True)
        except ValueError as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)
        with _LORA_OVERRIDES_LOCK:
            overrides = _load_lora_overrides()
            override = overrides.get(lora_name, {})
            if isinstance(override, dict) and override.pop("preview_url", None) is not None:
                overrides[lora_name] = override
                _save_lora_overrides(overrides)
        return web.json_response({"success": True, "preview": os.path.basename(preview_path)})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.post("/umiapp/loras/preview/replace_url")
async def replace_lora_preview_url(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name")
        url = _to_civitai_red_url(str(data.get("url") or "").strip())
        if not lora_name or not re.match(r'^https?://', url, flags=re.IGNORECASE):
            return web.json_response({"success": False, "error": "Invalid LoRA or URL"}, status=400)
        with _LORA_OVERRIDES_LOCK:
            overrides = _load_lora_overrides()
            override = overrides.get(lora_name, {})
            if not isinstance(override, dict):
                override = {}
            override["preview_url"] = url
            overrides[lora_name] = override
            _save_lora_overrides(overrides)
        return web.json_response({"success": True, "override": override})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.post("/umiapp/loras/manage/open")
async def open_lora_folder(request):
    try:
        data = await request.json()
        lora_name = data.get("filename") or data.get("lora_name")
        full_path = _target_lora_path(lora_name)
        if not full_path or not os.path.exists(full_path):
            return web.json_response({"success": False, "error": "LoRA not found"}, status=404)
        folder = os.path.dirname(full_path)
        if os.name == "nt":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.post("/umiapp/loras/manage/delete")
async def delete_lora_files(request):
    try:
        data = await request.json()
        lora_name = data.get("filename") or data.get("lora_name")
        payload, status = await asyncio.to_thread(_delete_lora_files_sync, lora_name)
        return web.json_response(payload, status=status)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.post("/umiapp/loras/civitai/single")
async def fetch_lora_civitai_single(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name")
        mode = data.get("mode") or "replace_civitai_info"
        api_token = data.get("api_token")
        if not lora_name:
            return web.json_response({"success": False, "error": "Missing LoRA name"}, status=400)
        cache = _load_civitai_cache()
        # Hashing the LoRA file and the network fetch are blocking; keep them
        # off the aiohttp event loop so the ComfyUI UI stays responsive.
        result = await asyncio.to_thread(
            _fetch_and_cache_lora_civitai, lora_name, cache, mode=mode, api_token=api_token
        )
        if result.get("success") and result.get("updated") and result.get("entry"):
            await asyncio.to_thread(_merge_civitai_cache_entries, {lora_name: result.get("entry")})
        status = 200 if result.get("success") else 502
        return web.json_response(result, status=status)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.post("/umiapp/loras/civitai/batch")
async def fetch_lora_civitai_batch(request):
    try:
        data = await request.json()
        mode = data.get("mode") or "update_missing"
        requested_loras = data.get("loras")
        api_token = data.get("api_token")
        cache = _load_civitai_cache()
        names = requested_loras if isinstance(requested_loras, list) and requested_loras else _get_lora_filename_list()
        if not _CIVITAI_BATCH_GUARD.acquire(blocking=False):
            return web.json_response({
                "success": False,
                "error": "A Civitai batch fetch is already running.",
                "count": 0,
            }, status=409)
        try:
            count = 0
            cached = 0
            errors = []
            updated_entries = {}
            for name in names:
                # Per-file hashing + fetch is blocking; run off the event loop.
                result = await asyncio.to_thread(
                    _fetch_and_cache_lora_civitai, str(name), cache, mode=mode, api_token=api_token
                )
                if result.get("success"):
                    count += 1
                    if result.get("cached"):
                        cached += 1
                    elif result.get("entry"):
                        updated_entries[str(name)] = result.get("entry")
                else:
                    errors.append({
                        "lora_name": name,
                        "error": result.get("error") or "Unknown error",
                    })
            if updated_entries:
                await asyncio.to_thread(_merge_civitai_cache_entries, updated_entries)
        finally:
            _CIVITAI_BATCH_GUARD.release()
        return web.json_response({
            "success": True,
            "count": count,
            "cached": cached,
            "updated": max(0, count - cached),
            "errors": errors[:100],
            "error_count": len(errors),
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "count": 0}, status=500)


@PromptServer.instance.routes.get("/umiapp/run_inspector/latest")
async def get_latest_run_inspector(request):
    if not UMI_SETTINGS.get("persist_run_inspector", False):
        return web.json_response(
            {
                "success": False,
                "disabled": True,
                "error": "Run Inspector persistence is disabled in Umi settings.",
            },
            status=404,
        )
    cache_path = os.path.join(BASE_DIR, "cache", "run_inspector_latest.json")
    if not os.path.exists(cache_path):
        return web.json_response({"success": False, "error": "No Umi run has been cached yet."}, status=404)
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return web.json_response({"success": True, **data})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@PromptServer.instance.routes.get("/umiapp/wildcards")
async def fetch_wildcards(request):
    return web.json_response(await asyncio.to_thread(get_wildcard_data))


@PromptServer.instance.routes.get("/umiapp/globals")
async def fetch_globals(request):
    variables = {}
    for root in _wildcard_roots():
        globals_path = os.path.join(root, "globals.yaml")
        if not os.path.exists(globals_path):
            continue
        try:
            with open(globals_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                for key, value in data.items():
                    var_name = key if str(key).startswith("$") else f"${key}"
                    variables.setdefault(var_name, str(value))
        except Exception as e:
            umi_debug_print(f"[UmiAI] Error loading globals.yaml: {e}")
    return web.json_response({"variables": variables, "count": len(variables)})


@PromptServer.instance.routes.get("/umiapp/preview")
async def preview_content(request):
    path = request.query.get("path")
    if path:
        if not UI_TOOLS_ENABLED:
            return web.Response(status=404, text="Preview not found")
        for root in folder_paths.get_folder_paths("loras"):
            full_path = _safe_join(root, path)
            if _is_allowed_lora_preview_file(full_path):
                return web.FileResponse(full_path)
        return web.Response(status=404, text="Preview not found")

    filename = request.query.get("file", "")
    normalized = filename.replace("\\", "/").strip("/")
    if not normalized:
        return web.json_response({"error": "No file specified"}, status=400)

    wildcard_root = _wildcard_root()
    for ext in ("txt", "yaml", "yml", "csv"):
        file_path = _safe_join(wildcard_root, f"{normalized}.{ext}")
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return web.json_response({"filename": filename, "type": ext, "content": content, "count": len(content.splitlines())})
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

    return web.json_response({"error": "File not found"}, status=404)


@PromptServer.instance.routes.post("/umiapp/refresh")
async def refresh_wildcards(request):
    data = await asyncio.to_thread(_refresh_wildcards_sync)
    return web.json_response({"status": "success", "count": len(data.get("files", [])) + len(data.get("tags", [])), **data})


def _refresh_wildcards_sync():
    with PROMPT_CACHE_LOCK:
        GLOBAL_CACHE_LITE.clear()
        GLOBAL_INDEX_LITE["built"] = False
        GLOBAL_INDEX_LITE["files"] = set()
        GLOBAL_INDEX_LITE["entries"] = {}
        GLOBAL_INDEX_LITE["tags"] = set()
        GLOBAL_INDEX_LITE["entry_names"] = {}
        FILE_MTIME_CACHE_LITE.clear()
        data = get_wildcard_data()
        return data


@PromptServer.instance.routes.get("/umiapp/settings")
async def get_settings(request):
    return web.json_response({"settings": UMI_SETTINGS})


@PromptServer.instance.routes.post("/umiapp/settings/update")
async def update_settings(request):
    try:
        data = await request.json()
        allowed = set(load_umi_settings().keys())
        current_settings = dict(UMI_SETTINGS)
        current_settings.update({k: v for k, v in data.get("settings", {}).items() if k in allowed})
        try:
            validate_processing_settings(current_settings)
        except ValueError as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=400)

        settings_path = os.path.join(BASE_DIR, "umi_settings.json")
        _atomic_write_json(settings_path, current_settings, indent=4)

        UMI_SETTINGS.clear()
        UMI_SETTINGS.update(load_umi_settings())
        return web.json_response({"status": "success", "settings": UMI_SETTINGS})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


def _preview_roll_sync(payload):
    """Expand a prompt the way the node would, without touching the graph.

    dry_run short-circuits LoRA loading, so no model or clip is needed and
    nothing is cached or mutated. The node's own process() is used rather than a
    reimplementation, so a preview cannot drift from a real run.
    """
    text = str(payload.get("text") or "")
    if not text.strip():
        return {"success": False, "error": "Nothing to preview: the prompt is empty."}, 400

    kwargs = {
        "text": text,
        "seed": _safe_int(payload.get("seed"), 0, minimum=0),
        "dry_run": True,
        "model": None,
        "clip": None,
    }
    # Pass through the node settings that change the expansion, when supplied.
    for key in ("prompt_profile", "prompt_preset", "preset_placement",
                "section_order", "input_negative", "anima_prompt_mode",
                "anima_artist_mode", "bypass_phrases", "lora_tags_behavior",
                "lora_cache_limit", "width", "height"):
        if payload.get(key) is not None:
            kwargs[key] = payload[key]

    try:
        result = UmiAIWildcardNodeLite().process(**kwargs)
    except Exception as exc:
        umi_debug_print(f"[UmiAI] Roll preview failed: {exc}")
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}, 500

    # RETURN_NAMES: model, clip, text, negative_text, width, height, lora_info,
    #               input_text, input_negative, bypass_matches, explain_json, ...
    try:
        explain = json.loads(result[10]) if result[10] else {}
    except Exception:
        explain = {}

    trace = explain.get("wildcard_trace") or []
    return {
        "success": True,
        "prompt": result[2],
        # This is the resolved prompt immediately before LoRA extraction.  It
        # intentionally still contains <lora:...> so the Pin button can reuse
        # the roll without silently dropping model patches.
        "frozen_prompt": explain.get("processed_prompt_before_lora") or result[2],
        "negative": result[3],
        "width": result[4],
        "height": result[5],
        "picks": len(trace),
        "reused": sum(1 for item in trace if item.get("mode") == "cached"),
        "warnings": explain.get("warnings") or [],
        "trace": trace,
    }, 200


@PromptServer.instance.routes.post("/umiapp/preview-roll")
async def preview_roll(request):
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Malformed request body."}, status=400)

    body, status = await asyncio.to_thread(_preview_roll_sync, payload)
    return web.json_response(body, status=status)


def _prompt_history_path():
    return os.path.join(BASE_DIR, "prompt_history.json")


@PromptServer.instance.routes.get("/umiapp/prompt-history")
async def get_prompt_history(request):
    """Stored prompt history, newest first.

    Persistence is opt-in (persist_prompt_history). When it is off this still
    returns 200 with an empty list and persist=False, so the panel can show its
    in-session history and offer the toggle instead of reporting an error.
    """
    persist = bool(UMI_SETTINGS.get("persist_prompt_history", False))
    entries = []
    if persist:
        try:
            path = _prompt_history_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    entries = list(reversed(data))
        except Exception as e:
            return web.json_response(
                {"success": False, "persist": persist, "entries": [], "error": str(e)},
                status=500,
            )
    return web.json_response({"success": True, "persist": persist, "entries": entries})


@PromptServer.instance.routes.post("/umiapp/prompt-history/clear")
async def clear_prompt_history(request):
    try:
        path = _prompt_history_path()
        if os.path.exists(path):
            _atomic_write_json(path, [], indent=2)
        return web.json_response({"success": True, "entries": []})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@PromptServer.instance.routes.post("/umiapp/settings/reset")
async def reset_settings(request):
    defaults = dict(DEFAULT_UMI_SETTINGS)
    try:
        settings_path = os.path.join(BASE_DIR, "umi_settings.json")
        _atomic_write_json(settings_path, defaults, indent=4)
        UMI_SETTINGS.clear()
        UMI_SETTINGS.update(load_umi_settings())
        return web.json_response({"status": "success", "settings": UMI_SETTINGS})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


def _collect_autocomplete_tags(query, limit):
    """Blocking CSV scan for autocomplete; called via asyncio.to_thread."""
    tags = []
    tag_dir = os.path.join(BASE_DIR, "autocomplete-tags")
    if not query or not os.path.isdir(tag_dir):
        return tags
    pattern = re.compile(re.escape(query).replace("\\ ", "[_ ]"), re.IGNORECASE)
    for csv_path in glob.glob(os.path.join(tag_dir, "*.csv")):
        try:
            with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.split(",", 3)
                    tag = parts[0].strip()
                    if tag and pattern.search(tag):
                        count = _safe_int(parts[2].strip() if len(parts) > 2 else 0, 0, minimum=0)
                        category = _safe_int(parts[1].strip() if len(parts) > 1 else 0, 0, minimum=0)
                        tags.append({
                            "tag": tag,
                            "value": tag.replace("_", " "),
                            "count": count,
                            "category": category,
                        })
                        if len(tags) >= limit:
                            return tags
        except Exception:
            continue
    return tags


@PromptServer.instance.routes.get("/umiapp/autocomplete/tags")
async def get_autocomplete_tags(request):
    if not UMI_SETTINGS.get("enable_tag_autocomplete", True):
        return web.json_response({"tags": [], "count": 0, "total": 0, "disabled": True})

    query = (request.query.get("query", "") or "").strip().lower()
    limit = _safe_int(request.query.get("limit"), 50, minimum=1, maximum=200)
    tags = await asyncio.to_thread(_collect_autocomplete_tags, query, limit)
    return web.json_response({"tags": tags, "count": len(tags), "total": len(tags)})


@_UI_ROUTES.get("/umiapp/danbooru/search")
async def danbooru_search(request):
    query = _normalize_danbooru_search_tags(request.query.get("tags", ""))
    rating = (request.query.get("rating", "") or "").strip()
    page = _safe_int(request.query.get("page", 1), 1, minimum=1)
    limit = _safe_int(request.query.get("limit", 24), 24, minimum=1, maximum=100)

    tags = query
    rating_map = {
        "general": "g",
        "sensitive": "s",
        "questionable": "q",
        "explicit": "e",
    }
    rating_value = rating_map.get(rating, rating)
    if rating_value and rating_value != "any" and f"rating:{rating_value}" not in tags:
        tags = f"{tags} rating:{rating_value}".strip()

    try:
        headers = {
            "Accept": "application/json",
            "User-Agent": "UmiAI-ComfyUI/1.0",
        }
        auth = None
        danbooru_login = os.environ.get("DANBOORU_LOGIN")
        danbooru_api_key = os.environ.get("DANBOORU_API_KEY")
        if danbooru_login and danbooru_api_key:
            auth = (danbooru_login, danbooru_api_key)
        tags = _limit_danbooru_public_query(tags, bool(auth))
        # Synchronous HTTP client; run off the event loop.
        response = await asyncio.to_thread(
            _danbooru_get_posts, {"tags": tags, "limit": limit, "page": page}, headers, auth
        )
        if response.status_code != 200:
            error = f"Danbooru returned HTTP {response.status_code}"
            if _is_cloudflare_challenge(response):
                error += "; Cloudflare blocked the backend request. Install curl_cffi or try again later."
            return web.json_response({
                "success": False,
                "error": error,
                "posts": [],
            }, status=502)
        try:
            posts = response.json()
        except Exception:
            return web.json_response({
                "success": False,
                "error": "Danbooru returned a non-JSON response",
                "posts": [],
            }, status=502)
        if not isinstance(posts, list):
            posts = []
        payload_posts = [_danbooru_post_payload(post) for post in posts if isinstance(post, dict)]
        umi_debug_print(f"[UmiAI] Danbooru search query='{tags}' status={response.status_code} posts={len(payload_posts)}")
        return web.json_response({
            "success": True,
            "query": tags,
            "page": page,
            "limit": limit,
            "count": len(payload_posts),
            "posts": payload_posts,
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "posts": []}, status=500)


@_UI_ROUTES.get("/umiapp/danbooru/image")
async def danbooru_image(request):
    url = request.query.get("url", "")
    if not _is_allowed_danbooru_image_url(url):
        return web.Response(status=400, text="Invalid Danbooru image URL")
    try:
        # Synchronous HTTP client; run off the event loop.
        response = await asyncio.to_thread(_danbooru_get_image, url)
        if response.status_code != 200:
            return web.Response(status=502, text=f"Danbooru image returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type") or "application/octet-stream"
        return web.Response(
            body=response.content,
            content_type=content_type.split(";", 1)[0],
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        return web.Response(status=502, text=str(e))


def _series_import_manifest_root():
    return os.path.join(BASE_DIR, "cache", "series_imports")


@_UI_ROUTES.get("/umiapp/series-import/search")
async def series_import_search(request):
    query = (request.query.get("query", "") or "").strip()
    media_type = (request.query.get("type", "ANIME") or "ANIME").upper()
    page = _safe_int(request.query.get("page"), 1, minimum=1, maximum=1000)
    if not query:
        return web.json_response({"success": True, "items": [], "page_info": {"current_page": 1, "has_next_page": False}})
    try:
        result = await asyncio.to_thread(series_importer.search_anilist_media, query, media_type, page)
        return web.json_response({"success": True, **result})
    except Exception as e:
        umi_debug_print(f"[UmiAI] AniList series search failed: {e}")
        return web.json_response({"success": False, "error": str(e), "items": []}, status=502)


@_UI_ROUTES.get("/umiapp/series-import/characters")
async def series_import_characters(request):
    media_id = _safe_int(request.query.get("media_id"), 0, minimum=0)
    character_limit = _safe_int(request.query.get("limit"), 250, minimum=0, maximum=2000)
    if not media_id:
        return web.json_response({"success": False, "error": "A valid AniList media ID is required"}, status=400)
    try:
        media, characters = await asyncio.to_thread(
            series_importer.fetch_anilist_characters, media_id, character_limit
        )
        result = await asyncio.to_thread(
            series_importer.enrich_characters,
            media,
            characters,
            os.path.join(BASE_DIR, "autocomplete-tags"),
        )
        return web.json_response({"success": True, **result})
    except Exception as e:
        umi_debug_print(f"[UmiAI] Series character import failed for AniList {media_id}: {e}")
        return web.json_response({"success": False, "error": str(e), "characters": []}, status=502)


@_UI_ROUTES.post("/umiapp/series-import/variants")
async def series_import_variants(request):
    try:
        data = await request.json()
        tags = data.get("tags") if isinstance(data, dict) else []
        if not isinstance(tags, list):
            return web.json_response({"success": False, "error": "tags must be a list"}, status=400)
        tags = list(dict.fromkeys(str(tag or "").strip() for tag in tags if str(tag or "").strip()))[:100]
        index = await asyncio.to_thread(series_importer.load_tag_index, os.path.join(BASE_DIR, "autocomplete-tags"))
        results = {}
        errors = {}
        online_disabled_error = None
        for position, tag in enumerate(tags):
            local = series_importer.discover_local_variants(tag, index)
            if online_disabled_error:
                online = []
                errors[tag] = online_disabled_error
            else:
                try:
                    online = await asyncio.to_thread(
                        series_importer.discover_online_variants,
                        tag,
                        index,
                        100,
                        0.10 if position else 0.0,
                    )
                except Exception as e:
                    online = []
                    errors[tag] = str(e)
                    if "403" in str(e) or "cloudflare" in str(e).lower():
                        online_disabled_error = str(e)
            merged = {}
            for variant in [*local, *online]:
                current = merged.get(variant["tag"])
                if current is None or variant.get("verified"):
                    merged[variant["tag"]] = variant
            results[tag] = sorted(merged.values(), key=lambda item: (-item.get("post_count", 0), item["tag"]))
        return web.json_response({"success": True, "variants": results, "errors": errors})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "variants": {}}, status=500)


@_UI_ROUTES.post("/umiapp/series-import/write")
async def series_import_write(request):
    try:
        data = await request.json()
        if not isinstance(data, dict):
            return web.json_response({"success": False, "error": "Invalid request body"}, status=400)
        characters = data.get("characters")
        if not isinstance(characters, list) or len(characters) > 1000:
            return web.json_response({"success": False, "error": "characters must be a list of at most 1000 entries"}, status=400)
        result = await asyncio.to_thread(
            series_importer.write_wildcard_import,
            data,
            _wildcard_root(),
            _series_import_manifest_root(),
        )
        return web.json_response(result)
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        umi_debug_print(f"[UmiAI] Series wildcard write failed: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


@_UI_ROUTES.get("/umiapp/series-import/manifests")
async def series_import_manifests(request):
    manifest_id = (request.query.get("id", "") or "").strip()
    try:
        if manifest_id:
            manifest = await asyncio.to_thread(series_importer.read_manifest, _series_import_manifest_root(), manifest_id)
            if manifest is None:
                return web.json_response({"success": False, "error": "Import manifest not found"}, status=404)
            return web.json_response({"success": True, "manifest": manifest})
        items = await asyncio.to_thread(series_importer.list_manifests, _series_import_manifest_root())
        return web.json_response({"success": True, "items": items})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "items": []}, status=500)


def _wildcard_text_details():
    """Per-file metadata for the wildcard browser and health report.

    Blank lines and comments are excluded from the count, because what matters
    is how many candidates a wildcard actually offers -- a file of 40 lines that
    are all comments offers none.
    """
    root = _wildcard_root()
    details = []
    if not os.path.isdir(root):
        return details
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            lowered = filename.lower()
            ext = next((e for e in WILDCARD_EXTENSIONS if lowered.endswith("." + e)), None)
            if ext is None:
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root).replace("\\", "/")
            entry = {
                "name": rel[: -(len(ext) + 1)],
                "ext": ext,
                "lines": 0,
                "blank": 0,
                "comments": 0,
                "bytes": 0,
            }
            try:
                stat = os.stat(path)
                entry["bytes"] = stat.st_size
                entry["mtime"] = stat.st_mtime
                if ext == "txt":
                    with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                        for raw in handle:
                            line = raw.strip()
                            if not line:
                                entry["blank"] += 1
                            elif line.startswith("#"):
                                entry["comments"] += 1
                            else:
                                entry["lines"] += 1
                else:
                    # For YAML the candidates are the named entries.
                    count, problem = _count_yaml_entries(path)
                    if problem:
                        entry["error"] = problem
                        entry["lines"] = None
                    else:
                        entry["lines"] = count
            except Exception as exc:
                entry["error"] = str(exc)
            details.append(entry)
    return sorted(details, key=lambda item: (item["name"].lower(), item.get("ext", "")))


def _wildcard_health_sync():
    """Structural problems across the wildcard collection.

    Only things that can be determined from the files themselves are reported.
    "Unused file" is deliberately absent: knowing it would mean scanning every
    workflow and saved prompt, and a wrong answer there invites deleting
    something that is used.
    """
    details = _wildcard_text_details()
    findings = []

    empty, single, unreadable, big = [], [], [], []
    dupes_within = []
    line_owners = {}

    root = _wildcard_root()
    for entry in details:
        name = entry["name"]
        ext = entry.get("ext", "txt")
        label = name if ext == "txt" else f"{name}.{ext}"
        if entry.get("error"):
            unreadable.append({"name": label, "note": entry["error"]})
            continue
        if entry["lines"] == 0:
            empty.append({"name": label, "note": "no candidate lines"})
            continue
        if entry["lines"] == 1:
            single.append({"name": label, "note": "one candidate, so it always resolves the same"})
        if entry["lines"] > 5000:
            big.append({"name": label, "note": f"{entry['lines']} candidates"})

        # The duplicate checks below compare candidate lines. A YAML file's
        # candidates are entries spread across many lines, so running them
        # over one would report noise rather than duplicates.
        if ext != "txt":
            continue

        path = _safe_join(root, f"{name}.txt")
        if not path or not os.path.exists(path):
            continue
        seen = {}
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                for number, raw in enumerate(handle, 1):
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    key = line.lower()
                    if key in seen:
                        seen[key] += 1
                    else:
                        seen[key] = 1
                    line_owners.setdefault(key, set()).add(name)
        except Exception:
            continue

        repeated = sorted((text, count) for text, count in seen.items() if count > 1)
        if repeated:
            shown = ", ".join(f"{text!r} x{count}" for text, count in repeated[:3])
            more = "" if len(repeated) <= 3 else f" (+{len(repeated) - 3} more)"
            dupes_within.append({
                "name": name,
                "note": f"{len(repeated)} repeated line(s): {shown}{more}",
            })

    shared = [
        {"name": ", ".join(sorted(owners)), "note": f"{text!r} appears in {len(owners)} files"}
        for text, owners in line_owners.items() if len(owners) > 2
    ]
    shared.sort(key=lambda item: item["note"])

    def group(key, title, severity, items, why):
        if items:
            findings.append({
                "key": key, "title": title, "severity": severity,
                "why": why, "items": items[:60], "total": len(items),
            })

    group("unreadable", "Files that could not be read", "error", unreadable,
          "These never resolve; a prompt referencing one gets [WILDCARD_NOT_FOUND].")
    group("empty", "Files with no candidates", "error", empty,
          "Only blank lines or comments, so referencing one produces nothing.")
    group("single", "Files with one candidate", "warn", single,
          "A wildcard with one line always resolves the same and could be plain text.")
    group("dupes-within", "Repeated lines inside a file", "warn", dupes_within,
          "Duplicates weight the roll toward that value, usually unintentionally.")
    group("shared", "Lines shared across three or more files", "info", shared,
          "Often fine, but can mean a file was copied rather than referenced.")
    group("large", "Very large files", "info", big,
          "Large files are read on every expansion; worth knowing about.")

    counts = {"error": 0, "warn": 0, "info": 0}
    for finding in findings:
        counts[finding["severity"]] += finding["total"]

    return {
        "success": True,
        "files": len(details),
        "candidates": sum(entry["lines"] for entry in details),
        "counts": counts,
        "findings": findings,
    }


@PromptServer.instance.routes.get("/umiapp/wildcards/health")
async def wildcard_health(request):
    try:
        return web.json_response(await asyncio.to_thread(_wildcard_health_sync))
    except Exception as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)


@PromptServer.instance.routes.get("/umiapp/wildcards/text/list")
async def list_text_wildcards(request):
    # `files` keeps its original flat shape: the Danbooru and LoRA browsers
    # both read it. `details` is additive.
    payload = {"success": True, "files": _list_wildcard_text_files()}
    if request.query.get("details") == "1":
        payload["details"] = await asyncio.to_thread(
            _all_wildcard_details if request.query.get("all") == "1" else _wildcard_text_details)
        payload["root"] = _wildcard_root()
    return web.json_response(payload)


@PromptServer.instance.routes.get("/umiapp/wildcards/text/read")
async def read_text_wildcard(request):
    name = request.query.get("name", "")
    ext = _wildcard_ext(request.query.get("ext"))
    source = request.query.get("source")
    if source:
        root = _wildcard_sources().get(source)
        ext = request.query.get("ext", "txt")
        if root is None or ext not in ('txt', 'yaml', 'yml', 'csv'):
            return web.json_response({"success": False, "error": "Unknown wildcard source or format"}, status=400)
        path = _safe_join(root, f"{name}.{ext}")
    else:
        path = _wildcard_file_path(name, ext)
    if not path:
        return web.json_response({"success": False, "error": "Invalid wildcard name"}, status=400)
    if not os.path.exists(path):
        return web.json_response({"success": True, "name": _normalize_wildcard_name(name), "ext": ext, "content": "", "exists": False, "version": None})
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.json_response({"success": True, "name": _normalize_wildcard_name(name), "ext": ext, "content": content, "exists": True,
                                  "version": _content_version(content)})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@PromptServer.instance.routes.post("/umiapp/wildcards/text/write")
async def write_text_wildcard(request):
    try:
        data = await request.json()
        name = data.get("name", "")
        if data.get('source'):
            return web.json_response({"success": False, "error": "Source browsing is read-only; edit external files in their source folder."}, status=400)
        mode = data.get("mode", "append")
        ext = _wildcard_ext(data.get("ext"))
        content = str(data.get("content", "") or "")
        tags = data.get("tags")
        if tags is not None:
            content = _format_tag_line(tags)
        path = _wildcard_file_path(name, ext)
        if not path:
            return web.json_response({"success": False, "error": "Invalid wildcard name"}, status=400)
        if _is_yaml_ext(ext):
            # A YAML file is a mapping, so appending a line to it produces a
            # file that no longer parses and silently stops matching anything.
            if mode != "overwrite":
                return web.json_response(
                    {"success": False,
                     "error": "A YAML wildcard can only be saved whole, not appended to."},
                    status=400)
            problem = _validate_yaml_text(content)
            if problem:
                return web.json_response(
                    {"success": False, "error": problem, "invalid_yaml": True}, status=400)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        existing = ""
        exists = os.path.exists(path)
        if exists:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        # expected_version is the version the editor read (null: the file must
        # not exist yet). Without it an overwrite replaces whatever is there.
        # No await runs between this check and the replace below.
        if mode == "overwrite" and "expected_version" in data:
            current_version = _content_version(existing) if exists else None
            if data["expected_version"] != current_version:
                if data["expected_version"] is None:
                    error = "A file with this name already exists."
                elif exists:
                    error = "This file changed on disk since it was opened."
                else:
                    error = "This file was deleted since it was opened."
                return web.json_response({
                    "success": False, "conflict": True, "exists": exists,
                    "version": current_version, "error": error,
                }, status=409)
        if mode == "overwrite":
            next_content = content.rstrip() + ("\n" if content.strip() else "")
        elif mode == "append":
            line = content.strip()
            next_content = existing
            if line:
                if next_content and not next_content.endswith("\n"):
                    next_content += "\n"
                if line not in {entry.strip() for entry in next_content.splitlines()}:
                    next_content += line + "\n"
        else:
            return web.json_response({"success": False, "error": "Unsupported write mode"}, status=400)
        # Stage beside the destination so a failed write cannot truncate a
        # working wildcard, and readers see either complete version.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                    dir=os.path.dirname(path), prefix=".umi-wildcard-",
                    suffix=".tmp", delete=False) as f:
                temp_path = f.name
                f.write(next_content)
            os.replace(temp_path, path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        return web.json_response({
            "success": True,
            "name": _normalize_wildcard_name(name),
            "content": next_content,
            "version": _content_version(next_content),
            "path": os.path.relpath(path, _wildcard_root()).replace("\\", "/"),
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


def _scan_images_sync(query):
    """Blocking image scan body; called via asyncio.to_thread."""
    output_root = _image_output_root()
    recursive = query.get("recursive", "1") != "0"
    quick = query.get("quick", "0") == "1"
    limit = _safe_int(query.get("limit"), 30, minimum=1, maximum=200)
    offset = _safe_int(query.get("offset"), 0, minimum=0)
    sort_mode = query.get("sort", "newest")
    annotations = _load_image_annotations().get("items", {})
    scan_cache = _load_image_scan_cache()
    cache_items = scan_cache.setdefault("items", {})
    cache_changed = False
    seen_paths = set()
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}

    all_items = []
    walker = os.walk(output_root) if recursive else [(output_root, [], os.listdir(output_root) if os.path.isdir(output_root) else [])]
    for root, _, files in walker:
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in image_exts:
                continue
            path = os.path.join(root, filename)
            if not _is_path_inside(path, output_root):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            relative_path = os.path.relpath(path, output_root).replace("\\", "/")
            seen_paths.add(relative_path)
            metadata, derived, changed, metadata_complete = _cached_image_metadata(cache_items, relative_path, stat, path, quick)
            cache_changed = cache_changed or changed
            item_annotations = annotations.get(relative_path) or annotations.get(filename) or {}
            if not isinstance(item_annotations, dict):
                item_annotations = {}
            item_annotations.setdefault("tags", [])
            item_annotations.setdefault("favorite", False)
            folder = os.path.dirname(relative_path).replace("\\", "/") or "(root)"
            item = {
                "filename": filename,
                "relative_path": relative_path,
                "folder": folder,
                "url": _image_url(relative_path),
                "thumbnail_url": "/umiapp/images/thumbnail?" + urllib.parse.urlencode({
                    "relative_path": relative_path, "v": f"{stat.st_mtime_ns}-{stat.st_ctime_ns}-{stat.st_size}"}),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "metadata": metadata,
                "derived": derived,
                "metadata_complete": metadata_complete,
                "annotations": item_annotations,
            }
            all_items.append(item)

    stale_paths = [path for path in cache_items if path not in seen_paths
                   and (recursive or "/" not in path)]
    for path in stale_paths:
        cache_items.pop(path, None)
        cache_changed = True
    if cache_changed:
        _save_image_scan_cache(scan_cache)

    items = [item for item in all_items if _image_matches_query(item, query)]

    def _sort_number(item, key, *, metadata=False):
        source = item.get("metadata", {}) if metadata else item.get("derived", {})
        value = _coerce_number(source.get(key))
        # Unknown values belong at the end of descending numeric sorts.
        return float("-inf") if value is None else value

    def _resolution_pixels(item):
        metadata = item.get("metadata", {})
        width = _coerce_number(metadata.get("width"))
        height = _coerce_number(metadata.get("height"))
        if width is None or height is None:
            return float("-inf")
        return width * height

    if sort_mode == "oldest":
        items.sort(key=lambda item: item.get("mtime", 0))
    elif sort_mode == "name":
        items.sort(key=lambda item: item.get("relative_path", "").lower())
    elif sort_mode == "size":
        items.sort(key=lambda item: item.get("size", 0), reverse=True)
    elif sort_mode == "resolution":
        items.sort(key=_resolution_pixels, reverse=True)
    elif sort_mode in {"steps", "cfg", "seed"}:
        items.sort(key=lambda item: _sort_number(item, sort_mode), reverse=True)
    else:
        items.sort(key=lambda item: item.get("mtime", 0), reverse=True)

    # Facets are disjunctive: when Model A is selected, keep Model B visible so
    # the user can add it as an OR filter.  Counting only the already-filtered
    # result made every disjoint option disappear after the first click.
    def _facet_source(*excluded_params):
        facet_query = dict(query)
        for param in excluded_params:
            facet_query.pop(param, None)
        return [item for item in all_items if _image_matches_query(item, facet_query)]

    folder_counts = Counter(item.get("folder", "") for item in _facet_source("folder"))
    model_counts = Counter(model for item in _facet_source("models") for model in item.get("derived", {}).get("models", []))
    lora_counts = Counter(lora for item in _facet_source("loras") for lora in item.get("derived", {}).get("loras", []))
    sampler_counts = Counter(item.get("derived", {}).get("sampler", "") for item in _facet_source("samplers"))
    tag_counts = Counter(tag for item in _facet_source("tags") for tag in item.get("annotations", {}).get("tags", []))

    return {
        "images": items[offset:offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "cache": {"items": len(cache_items), "updated": cache_changed},
        "facets": {
            "folders": _facet_items(folder_counts),
            "models": _facet_items(model_counts),
            "loras": _facet_items(lora_counts),
            "samplers": _facet_items(sampler_counts),
            "tags": _facet_items(tag_counts),
        },
    }


@_UI_ROUTES.get("/umiapp/images/scan")
async def scan_images(request):
    # The scan walks the output folder and reads image metadata; keep that
    # blocking work off the aiohttp event loop.
    query = dict(request.query)
    try:
        # Only share identical requests that are currently running. Completed
        # results are not retained, so Refresh and later requests stay fresh.
        key = (asyncio.get_running_loop(), tuple(sorted(query.items())))
        task = _IMAGE_SCAN_TASKS.get(key)
        if task is None or task.done():
            task = asyncio.create_task(asyncio.to_thread(_scan_images_sync, query))
            _IMAGE_SCAN_TASKS[key] = task
            def finished(done):
                if _IMAGE_SCAN_TASKS.get(key) is done:
                    _IMAGE_SCAN_TASKS.pop(key, None)
                if not done.cancelled():
                    done.exception()  # Retrieve failures even if all callers left.
            task.add_done_callback(finished)
        payload = await asyncio.shield(task)
    except Exception as e:
        # Full details (which may include local paths) go to the server log;
        # the response carries only a concise, path-free summary.
        print(f"[UmiAI] /umiapp/images/scan failed: {e}")
        traceback.print_exc()
        return web.json_response({
            "success": False,
            "error": f"Image scan failed on the server ({type(e).__name__}). Check the ComfyUI log for details.",
            "images": [],
            "total": 0,
            "facets": {},
            "limit": _safe_int(query.get("limit"), 30, minimum=1, maximum=200),
            "offset": _safe_int(query.get("offset"), 0, minimum=0),
        }, status=500)
    return web.json_response(payload)


@_UI_ROUTES.post("/umiapp/images/annotations/update")
async def update_image_annotations(request):
    try:
        data = await request.json()
        relative_path = str(data.get("relative_path", "")).replace("\\", "/").strip("/")
        if not relative_path:
            return web.json_response({"success": False, "error": "Missing relative_path"}, status=400)

        output_root = _image_output_root()
        target = _safe_join(output_root, relative_path)
        if not target:
            return web.json_response({"success": False, "error": "Invalid image path"}, status=400)

        with _IMAGE_ANNOTATIONS_LOCK:
            annotations = _load_image_annotations()
            items = annotations.setdefault("items", {})
            item = items.get(relative_path, {})
            if not isinstance(item, dict):
                item = {}

            if "favorite" in data:
                item["favorite"] = bool(data.get("favorite"))
            if "tags" in data:
                tags = data.get("tags") or []
                if not isinstance(tags, list):
                    tags = []
                item["tags"] = sorted({str(tag).strip() for tag in tags if str(tag).strip()})

            item.setdefault("tags", [])
            item.setdefault("favorite", False)
            items[relative_path] = item
            _save_image_annotations(annotations)
        return web.json_response({"success": True, "item": item})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


@PromptServer.instance.routes.get("/umiapp/modules")
async def umi_module_status(request):
    """Report the core and optional overlay state for support/debugging."""
    return web.json_response(
        {
            "core": "loaded",
            "version": __version__,
            "core_api_version": CORE_API_VERSION,
            "optional": dict(OPTIONAL_MODULE_STATUS),
            "ui_tools_enabled": UI_TOOLS_ENABLED,
            "node_count": len(NODE_CLASS_MAPPINGS),
            "nodes": sorted(NODE_CLASS_MAPPINGS),
        }
    )


class _UmiAIWildcardNodeLiteCompat(UmiAIWildcardNodeLite):
    """Alias so workflows saved with the old 'UmiAIWildcardNodeLite' class name
    keep loading. DEPRECATED hides it from the node menu on newer frontends."""
    DEPRECATED = True


CORE_NODE_CLASS_MAPPINGS = {
    "UmiAIWildcardNode": UmiAIWildcardNodeLite,
    "UmiAIWildcardNodeLite": _UmiAIWildcardNodeLiteCompat,
    "UmiSaveImage": UmiSaveImage,
    "UmiTextBypass": UmiTextBypass,
    "UmiPromptPreset": UmiPromptPreset,
    "UmiPromptProfile": UmiPromptProfile,
    "UmiPromptInspector": UmiPromptInspector,
    "UmiPromptSyntaxLint": UmiPromptSyntaxLint,
    "UmiBypassModelSwitch": UmiBypassModelSwitch,
}

CORE_NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiAIWildcardNode": "UmiAI Wildcard Processor",
    "UmiAIWildcardNodeLite": "UmiAI Wildcard Processor",
    "UmiSaveImage": "Umi Save Image (with metadata)",
    "UmiTextBypass": "Umi Bypass",
    "UmiPromptPreset": "Umi Prompt Preset",
    "UmiPromptProfile": "Umi Prompt Profile",
    "UmiPromptInspector": "Umi Prompt Inspector",
    "UmiPromptSyntaxLint": "Umi Prompt Syntax Lint",
    "UmiBypassModelSwitch": "Umi Bypass Model Switch",
}

NODE_CLASS_MAPPINGS = dict(CORE_NODE_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS = dict(CORE_NODE_DISPLAY_NAME_MAPPINGS)

# Optional features are overlay modules. A core-only installation simply does
# not contain these files; dropping one of the optional archives over the core
# folder makes its nodes available after the next ComfyUI restart.
OPTIONAL_NODE_MODULES = (
    "optional_krea",
    "optional_anima_edit",
    "optional_klein_edit",
    "optional_memory",
    "optional_ui_tools",
)
OPTIONAL_MODULE_STATUS = {}


def _load_optional_node_module(module_name):
    overlay_manifest, manifest_error = _read_overlay_manifest(module_name)
    if manifest_error:
        OPTIONAL_MODULE_STATUS[module_name] = manifest_error
        if manifest_error != "not installed":
            logging.warning("[UmiAI] Optional module %s: %s", module_name, manifest_error)
        return
    bundle_version = str(overlay_manifest["bundle_version"])

    try:
        module = importlib.import_module(f".{module_name}", __package__)
    except ModuleNotFoundError as exc:
        # Absence of the overlay itself is normal. A missing dependency inside
        # an installed overlay is different and should be visible to the user.
        if str(exc.name or "").rsplit(".", 1)[-1] == module_name:
            OPTIONAL_MODULE_STATUS[module_name] = "not installed"
            return
        OPTIONAL_MODULE_STATUS[module_name] = f"error: {exc}"
        logging.warning("[UmiAI] Optional module %s could not load: %s", module_name, exc)
        return
    except Exception as exc:
        OPTIONAL_MODULE_STATUS[module_name] = f"error: {exc}"
        logging.warning("[UmiAI] Optional module %s could not load: %s", module_name, exc)
        return

    class_mappings = getattr(module, "NODE_CLASS_MAPPINGS", {})
    display_mappings = getattr(module, "NODE_DISPLAY_NAME_MAPPINGS", {})
    duplicates = sorted(set(NODE_CLASS_MAPPINGS).intersection(class_mappings))
    if duplicates:
        OPTIONAL_MODULE_STATUS[module_name] = f"error: duplicate nodes {', '.join(duplicates)}"
        logging.warning(
            "[UmiAI] Optional module %s was skipped because it duplicates: %s",
            module_name,
            ", ".join(duplicates),
        )
        return
    NODE_CLASS_MAPPINGS.update(class_mappings)
    NODE_DISPLAY_NAME_MAPPINGS.update(display_mappings)
    OPTIONAL_MODULE_STATUS[module_name] = (
        f"loaded bundle {bundle_version} ({len(class_mappings)} nodes)"
    )


for _optional_module_name in OPTIONAL_NODE_MODULES:
    _load_optional_node_module(_optional_module_name)

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "OPTIONAL_MODULE_STATUS",
    "CORE_API_VERSION",
    "__version__",
    "WEB_DIRECTORY",
]
