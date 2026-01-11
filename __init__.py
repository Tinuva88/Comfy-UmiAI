from .nodes import (UmiAIWildcardNode, UmiSaveImage, UmiPoseGenerator, UmiEmotionGenerator, 
                    UmiEmotionStudio, UmiCharacterCreator as UmiCharacterCreator2, 
                    UmiSpriteGenerator as UmiSpriteGenerator2, UmiDatasetGenerator as UmiDatasetGenerator2,
                    UmiPositionControl as UmiPositionControl2, UmiVisualCameraControl as UmiVisualCameraControl2)
from .nodes_lite import UmiAIWildcardNodeLite
from .nodes_character import UmiCharacterManager, UmiCharacterBatch, UmiSpriteExport, UmiCharacterInfo
from .nodes_camera import UmiCameraControl, UmiVisualCameraControl, UmiCameraAngleSelector
from .nodes_power import UmiPoseLibrary, UmiExpressionMixer, UmiSceneComposer, UmiLoraAnimator, UmiPromptTemplate
from .nodes_dataset import UmiDatasetExport, UmiCaptionGenerator
from .nodes_caption import UmiAutoCaption, UmiCaptionEnhancer
from .nodes_qwen_detailer import UmiQWENDetailer, UmiBBoxExtractor
from .nodes_qwen_encoder import UmiQWENEncoder
from .nodes_model_manager import UmiModelManager, UmiModelSelector
from .nodes_sheet_tools import (
    VNCCSSheetManager,
    VNCCSSheetExtractor,
    VNCCSChromaKey,
    VNCCS_ColorFix,
    VNCCS_Resize,
    VNCCS_MaskExtractor,
    VNCCS_RMBG2,
    VNCCS_QuadSplitter,
)
from .nodes_sheet_crop import CharacterSheetCropper
from server import PromptServer
from aiohttp import web
import os
import importlib.util
import glob
import yaml
import folder_paths # New Import for LoRA scanning

# 1. Setup the API Route
def get_wildcard_data():
    wildcards_path = os.path.join(os.path.dirname(__file__), "wildcards")
    txt_files = []      # For __ autocomplete (txt files only)
    yaml_files = []     # YAML file names
    tags = set()        # Tags from YAML files for <[ autocomplete
    basenames = {}      # Maps basename -> full path for quick lookup
    
    if os.path.exists(wildcards_path):
        # 1. Scan TXT files (for __ wildcards)
        for filepath in glob.glob(os.path.join(wildcards_path, '**', '*.txt'), recursive=True):
            rel_path = os.path.relpath(filepath, wildcards_path)
            tag_name = os.path.splitext(rel_path)[0].replace(os.sep, '/')
            txt_files.append(tag_name)
            
            # Add basename mapping (filename without extension)
            basename = os.path.splitext(os.path.basename(filepath))[0]
            if basename not in basenames:
                basenames[basename] = tag_name
        
        # 2. Scan YAML files (for tags)
        for filepath in glob.glob(os.path.join(wildcards_path, '**', '*.yaml'), recursive=True):
            rel_path = os.path.relpath(filepath, wildcards_path)
            tag_name = os.path.splitext(rel_path)[0].replace(os.sep, '/')
            yaml_files.append(tag_name)
            
            # Add basename mapping
            basename = os.path.splitext(os.path.basename(filepath))[0]
            if basename not in basenames:
                basenames[basename] = tag_name
            
            # Parse YAML for Tags
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        for entry in data.values():
                            if isinstance(entry, dict) and 'Tags' in entry:
                                for t in entry['Tags']:
                                    tags.add(str(t).strip())
            except Exception as e:
                print(f"[UmiAI] Error parsing YAML {filepath}: {e}")

    # Return separated data
    return {
        "files": sorted(txt_files),           # Legacy/combined (for backwards compat)
        "wildcards": sorted(txt_files),       # TXT files only (for __ autocomplete)
        "yaml_files": sorted(yaml_files),     # YAML file names
        "tags": sorted(list(tags)),           # Tags from YAML (for <[ autocomplete)
        "basenames": basenames,               # Basename -> full path mapping
        "loras": folder_paths.get_filename_list("loras")
    }

def get_optional_dependency_status():
    dependencies = {
        "opencv-python": "cv2",
        "transformers": "transformers",
        "torchvision": "torchvision",
        "transparent-background": "transparent_background"
    }
    installed = []
    missing = []
    for package_name, module_name in dependencies.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
        else:
            installed.append(package_name)
    return {"installed": installed, "missing": missing}

# Register the routes (aligned with nodes.py endpoints)
@PromptServer.instance.routes.get("/umiapp/wildcards")
async def fetch_wildcards(request):
    data = get_wildcard_data()
    return web.json_response(data)

@PromptServer.instance.routes.get("/umiapp/globals")
async def fetch_globals(request):
    """Fetch global variables from globals.yaml for autocomplete."""
    wildcards_path = os.path.join(os.path.dirname(__file__), "wildcards")
    globals_path = os.path.join(wildcards_path, "globals.yaml")
    variables = {}
    
    if os.path.exists(globals_path):
        try:
            with open(globals_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        # Store variable name (with $ prefix) and its value
                        var_name = key if key.startswith('$') else f'${key}'
                        variables[var_name] = str(value)
        except Exception as e:
            print(f"[UmiAI] Error loading globals.yaml: {e}")
    
    # Also check models/wildcards for globals
    models_wildcards = os.path.join(folder_paths.models_dir, "wildcards")
    models_globals = os.path.join(models_wildcards, "globals.yaml")
    
    if os.path.exists(models_globals):
        try:
            with open(models_globals, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        var_name = key if key.startswith('$') else f'${key}'
                        if var_name not in variables:  # Don't override
                            variables[var_name] = str(value)
        except Exception as e:
            print(f"[UmiAI] Error loading models globals.yaml: {e}")
    
    return web.json_response({
        "variables": variables,
        "count": len(variables)
    })

@PromptServer.instance.routes.get("/umiapp/deps")
async def get_dependency_status(request):
    return web.json_response(get_optional_dependency_status())

@PromptServer.instance.routes.get("/umiapp/characters")
async def fetch_characters(request):
    """Fetch available characters and their profiles for autocomplete and external tools."""
    from .nodes_character import CharacterLoader
    
    characters = CharacterLoader.list_characters()
    character_data = {}
    
    for char_name in characters:
        if char_name == "none":
            continue
        data = CharacterLoader.load_character(char_name)
        if data:
            character_data[char_name] = {
                "name": data.get('name', char_name),
                "description": data.get('description', ''),
                "lora": data.get('lora', ''),
                "outfits": list(data.get('outfits', {}).keys()),
                "emotions": list(data.get('emotions', {}).keys()),
                "poses": list(data.get('poses', {}).keys()),
            }
    
    return web.json_response({
        "characters": list(character_data.keys()),
        "profiles": character_data,
        "count": len(character_data)
    })

# VNCCS-style costume API
@PromptServer.instance.routes.get("/umiapp/character/costumes")
async def get_character_costumes(request):
    """List costumes for a character (VNCCS-compatible)."""
    character = request.query.get("character", "")
    if not character:
        return web.json_response([])
    
    chars_path = os.path.join(os.path.dirname(__file__), "characters", character)
    sheets_path = os.path.join(chars_path, "Sheets")
    
    costumes = []
    if os.path.exists(sheets_path):
        for item in os.listdir(sheets_path):
            if os.path.isdir(os.path.join(sheets_path, item)):
                costumes.append(item)
    
    return web.json_response(costumes)

# VNCCS-style character sheet preview
@PromptServer.instance.routes.get("/umiapp/character/preview")
async def get_character_preview(request):
    """Get cropped preview from character sheet (VNCCS-compatible)."""
    import io
    import re
    from PIL import Image
    
    character = request.query.get("character", "")
    if not character:
        return web.Response(status=404, text="No character specified")
    
    chars_path = os.path.join(os.path.dirname(__file__), "characters", character)
    
    # Try to find a sheet image
    sheet_dir = os.path.join(chars_path, "Sheets", "Naked", "neutral")
    if not os.path.exists(sheet_dir):
        # Try any costume
        sheets_base = os.path.join(chars_path, "Sheets")
        if os.path.exists(sheets_base):
            for costume in sorted(os.listdir(sheets_base)):
                path = os.path.join(sheets_base, costume, "neutral")
                if os.path.isdir(path):
                    sheet_dir = path
                    break
    
    if not os.path.exists(sheet_dir):
        return web.Response(status=404, text="Sheet not found")
    
    # Find the best sheet file (highest index)
    pattern = os.path.join(sheet_dir, "sheet_neutral_*.png")
    files = glob.glob(pattern)
    if not files:
        # Try any PNG
        files = glob.glob(os.path.join(sheet_dir, "*.png"))
    
    if not files:
        return web.Response(status=404, text="No sheet images found")
    
    def get_index(f):
        m = re.search(r'(\d+)', os.path.basename(f))
        return int(m.group(1)) if m else 0
    
    files.sort(key=get_index)
    best_file = files[-1]
    
    # Crop: Sheet is 6x2 grid, get last cell (row 1, col 5)
    try:
        img = Image.open(best_file)
        w, h = img.size
        item_w = w // 6
        item_h = h // 2
        
        row, col = 1, 5
        left = col * item_w
        upper = row * item_h
        right = left + item_w
        lower = upper + item_h
        
        crop = img.crop((left, upper, right, lower))
        
        img_byte_arr = io.BytesIO()
        crop.save(img_byte_arr, format='PNG')
        return web.Response(body=img_byte_arr.getvalue(), content_type='image/png')
    except Exception as e:
        return web.Response(status=500, text=str(e))

# VNCCS-style emotions API
@PromptServer.instance.routes.get("/umiapp/emotions")
async def get_emotions(request):
    """Get emotions config data (VNCCS-compatible)."""
    config_path = os.path.join(os.path.dirname(__file__), "emotions-config", "emotions.json")
    
    if not os.path.exists(config_path):
        return web.json_response({"error": "emotions.json not found"}, status=404)
    
    import json
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Emotion image server
@PromptServer.instance.routes.get("/umiapp/emotion/image")
async def get_emotion_image(request):
    """Serve emotion image by safe_name."""
    from urllib.parse import unquote
    
    name = request.query.get("name", "")
    if not name or ".." in name or "/" in name or "\\" in name:
        return web.Response(status=400)
    
    name = unquote(name).strip()
    image_path = os.path.join(os.path.dirname(__file__), "emotions-config", "images", f"{name}.png")
    
    if not os.path.exists(image_path):
        return web.Response(status=404)
    
    return web.FileResponse(image_path)


@PromptServer.instance.routes.get("/umiapp/preview")
async def preview_wildcard(request):
    """Preview the contents of a wildcard file for hover tooltips."""
    filename = request.query.get("file", "")
    if not filename:
        return web.json_response({"error": "No file specified"}, status=400)
    
    wildcards_path = os.path.join(os.path.dirname(__file__), "wildcards")
    entries = []
    
    # Search for the file
    for ext in ['txt', 'yaml', 'yml', 'csv']:
        # Try direct path
        file_path = os.path.join(wildcards_path, f"{filename}.{ext}")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if ext == 'txt':
                        # Read first 15 lines
                        lines = []
                        for i, line in enumerate(f):
                            if i >= 15:
                                lines.append("... (more entries)")
                                break
                            line = line.strip()
                            if line and not line.startswith('#'):
                                # Strip tags (:: separator) for preview
                                if '::' in line:
                                    line = line.split('::')[0]
                                lines.append(line)
                        entries = lines
                    elif ext in ['yaml', 'yml']:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            entries = list(data.keys())[:15]
                            if len(data) > 15:
                                entries.append(f"... (+{len(data) - 15} more)")
                    elif ext == 'csv':
                        import csv as csv_module
                        reader = csv_module.reader(f)
                        for i, row in enumerate(reader):
                            if i >= 15:
                                entries.append("... (more entries)")
                                break
                            if row:
                                entries.append(row[0])
                return web.json_response({
                    "file": filename,
                    "type": ext,
                    "entries": entries,
                    "count": len(entries)
                })
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        
        # Try recursive search
        for root, dirs, files in os.walk(wildcards_path):
            for f in files:
                name_without_ext = os.path.splitext(f)[0]
                rel_path = os.path.relpath(os.path.join(root, f), wildcards_path)
                rel_name = os.path.splitext(rel_path)[0].replace(os.sep, '/')
                if rel_name.lower() == filename.lower() or name_without_ext.lower() == filename.lower():
                    return await preview_wildcard_file(os.path.join(root, f), filename)
    
    return web.json_response({"file": filename, "entries": [], "error": "File not found"})

async def preview_wildcard_file(file_path, filename):
    """Helper to preview a specific wildcard file."""
    entries = []
    ext = os.path.splitext(file_path)[1].lower()[1:]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            if ext == 'txt':
                lines = []
                for i, line in enumerate(f):
                    if i >= 15:
                        lines.append("... (more entries)")
                        break
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Strip tags (:: separator) for preview
                        if '::' in line:
                            line = line.split('::')[0]
                        lines.append(line)
                entries = lines
            elif ext in ['yaml', 'yml']:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    entries = list(data.keys())[:15]
                    if len(data) > 15:
                        entries.append(f"... (+{len(data) - 15} more)")
        return web.json_response({
            "file": filename,
            "type": ext,
            "entries": entries,
            "count": len(entries)
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/umiapp/refresh")
async def refresh_wildcards(request):
    # Trigger a cache clear for BOTH full and lite nodes
    from .nodes import GLOBAL_CACHE, GLOBAL_INDEX, FILE_MTIME_CACHE
    from .nodes_lite import GLOBAL_CACHE_LITE, GLOBAL_INDEX_LITE, FILE_MTIME_CACHE_LITE

    # Clear full node cache (including mtime cache)
    GLOBAL_CACHE.clear()
    GLOBAL_INDEX['built'] = False
    GLOBAL_INDEX['files'] = set()
    GLOBAL_INDEX['entries'] = {}
    GLOBAL_INDEX['tags'] = set()
    FILE_MTIME_CACHE.clear()  # Fix 12: Clear modification time cache on refresh

    # Clear lite node cache (including mtime cache)
    GLOBAL_CACHE_LITE.clear()
    GLOBAL_INDEX_LITE['built'] = False
    GLOBAL_INDEX_LITE['files'] = set()
    GLOBAL_INDEX_LITE['entries'] = {}
    GLOBAL_INDEX_LITE['tags'] = set()
    FILE_MTIME_CACHE_LITE.clear()  # Fix 12: Clear modification time cache on refresh

    # Return fresh data
    data = get_wildcard_data()
    return web.json_response({
        "status": "success",
        "count": len(data.get("files", [])) + len(data.get("tags", [])),
        **data
    })

# ==============================================================================
# MODEL DOWNLOADER API (VNCCS-STYLE REPO SUPPORT)
# ==============================================================================

import json
import asyncio
import threading
import traceback
import requests
import queue
import urllib.parse

try:
    from huggingface_hub import hf_hub_download, hf_hub_url
    HF_HUB_AVAILABLE = True
except Exception:
    HF_HUB_AVAILABLE = False

# Universal download queue to avoid contention
download_queue = queue.Queue()
download_status = {}

def resolve_path(relative_path):
    base = getattr(folder_paths, "base_path", os.getcwd())
    return os.path.abspath(os.path.join(base, relative_path))

def get_installed_version_info():
    registry_path = resolve_path("umi_installed_models.json")
    if os.path.exists(registry_path):
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def update_installed_version(model_name, version):
    registry_path = resolve_path("umi_installed_models.json")
    data = get_installed_version_info()
    data[model_name] = version
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def get_umi_config():
    config_path = resolve_path("umi_user_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_umi_config(new_data):
    config_path = resolve_path("umi_user_config.json")
    data = get_umi_config()
    data.update(new_data)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def _convert_manifest_to_config(manifest):
    version = str(manifest.get("version", "1.0"))
    models = []
    for category in manifest.get("categories", {}).values():
        target_dir = category.get("target_dir", "")
        for model in category.get("models", []):
            filename = model.get("filename", "")
            local_path = os.path.join("models", target_dir, filename).replace("\\", "/")
            files = []
            if model.get("files"):
                for f in model.get("files", []):
                    file_name = f.get("filename") or f.get("name") or ""
                    file_local = f.get("local_path")
                    if not file_local and file_name:
                        file_local = os.path.join("models", target_dir, file_name).replace("\\", "/")
                    files.append({
                        "filename": file_name,
                        "local_path": file_local or "",
                        "url": f.get("url", ""),
                        "hf_repo": f.get("hf_repo", model.get("hf_repo", "")),
                        "hf_path": f.get("hf_path", ""),
                    })
            models.append({
                "name": model.get("name", filename),
                "version": version,
                "local_path": local_path,
                "description": model.get("description", ""),
                "url": model.get("url", ""),
                "hf_repo": model.get("hf_repo", ""),
                "hf_path": model.get("hf_path", ""),
                "files": files
            })
    return {"models": models}


def _fetch_model_config(repo_id):
    if not HF_HUB_AVAILABLE:
        raise RuntimeError("huggingface_hub is not installed.")

    try:
        path = hf_hub_download(repo_id=repo_id, filename="model_updater.json", local_files_only=False)
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        path = hf_hub_download(repo_id=repo_id, filename="models_manifest.json", local_files_only=False)
        with open(path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return _convert_manifest_to_config(manifest)


def worker_loop():
    while True:
        task = download_queue.get()
        if task is None:
            break

        repo_id, model_name, target_model = task

        try:
            file_entries = target_model.get("files") or []
            if not file_entries:
                file_entries = [{
                    "filename": os.path.basename(target_model.get("local_path", "")),
                    "local_path": target_model.get("local_path", ""),
                    "url": target_model.get("url", ""),
                    "hf_repo": target_model.get("hf_repo", ""),
                    "hf_path": target_model.get("hf_path", "")
                }]

            for index, file_entry in enumerate(file_entries):
                file_name = file_entry.get("filename") or os.path.basename(file_entry.get("local_path", "")) or "file"
                download_status[model_name] = {
                    "status": "downloading",
                    "message": f"Downloading {file_name}...",
                    "progress": 0,
                    "file": file_name,
                    "file_index": index + 1,
                    "file_count": len(file_entries)
                }

                url = ""
                headers = {}

                file_repo_id = file_entry.get("hf_repo") or target_model.get("hf_repo") or repo_id
                if file_entry.get("url") or target_model.get("url"):
                    url = file_entry.get("url") or target_model.get("url", "")

                    if "civitai.com/models/" in url and "api/download" not in url:
                        parsed = urllib.parse.urlparse(url)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if "modelVersionId" in qs:
                            ver_id = qs["modelVersionId"][0]
                            url = f"https://civitai.com/api/download/models/{ver_id}"
                            print(f"[UmiAI] Auto-converted Civitai Web Link to API: {url}")

                    if "civitai.com" in url:
                        user_config = get_umi_config()
                        civitai_token = user_config.get("civitai_token", "")
                        if civitai_token:
                            headers = {"Authorization": f"Bearer {civitai_token}"}
                else:
                    if not HF_HUB_AVAILABLE:
                        raise RuntimeError("huggingface_hub is not installed.")

                    filename = file_entry.get("hf_path") or target_model.get("hf_path", "")
                    if filename.startswith(f"{file_repo_id}/"):
                        filename = filename[len(file_repo_id) + 1:]
                    url = hf_hub_url(file_repo_id, filename)
                    token = os.environ.get("HF_TOKEN")
                    if token:
                        headers = {"Authorization": f"Bearer {token}"}

                response = requests.get(url, headers=headers, stream=True, allow_redirects=True)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                temp_dir = os.path.join(folder_paths.base_path, "temp")
                os.makedirs(temp_dir, exist_ok=True)
                sanitized_name = "".join(x for x in model_name if x.isalnum())
                temp_filename = f"umi_{sanitized_name}_{index + 1}.tmp"
                temp_path = os.path.join(temp_dir, temp_filename)

                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                mb_done = downloaded / (1024 * 1024)
                                mb_total = total_size / (1024 * 1024)
                                msg = f"{file_name}: {mb_done:.1f}/{mb_total:.1f} MB"
                                download_status[model_name] = {
                                    "status": "downloading",
                                    "message": msg,
                                    "progress": percent,
                                    "file": file_name,
                                    "file_index": index + 1,
                                    "file_count": len(file_entries)
                                }
                            else:
                                mb_done = downloaded / (1024 * 1024)
                                download_status[model_name] = {
                                    "status": "downloading",
                                    "message": f"{file_name}: {mb_done:.1f} MB",
                                    "progress": 0,
                                    "file": file_name,
                                    "file_index": index + 1,
                                    "file_count": len(file_entries)
                                }

                download_status[model_name]["message"] = f"Installing {file_name}..."
                target_rel_path = file_entry.get("local_path") or target_model.get("local_path", "")
                if not target_rel_path:
                    raise RuntimeError(f"Missing local_path for {model_name}")

                target_abs_path = resolve_path(target_rel_path)
                target_dir = os.path.dirname(target_abs_path)
                os.makedirs(target_dir, exist_ok=True)

                import shutil
                shutil.move(temp_path, target_abs_path)
                print(f"[UmiAI] Installed {model_name} -> {target_abs_path}")

            update_installed_version(model_name, target_model.get("version", ""))
            download_status[model_name] = {"status": "success", "message": "Installed"}

        except Exception as e:
            is_auth_error = False
            if isinstance(e, requests.exceptions.HTTPError):
                if e.response.status_code == 401:
                    is_auth_error = True

            err_msg = str(e)
            status_code = "error"

            if is_auth_error:
                status_code = "auth_required"
                err_msg = "API Key Required"
            elif "404" in err_msg or "EntryNotFoundError" in err_msg:
                err_msg = "File not found (404)"

            download_status[model_name] = {"status": status_code, "message": err_msg}
            print(f"[UmiAI] Download failed for {model_name}: {err_msg}")
        finally:
            download_queue.task_done()

threading.Thread(target=worker_loop, daemon=True).start()

@PromptServer.instance.routes.get("/umiapp/models/status")
async def get_download_status(request):
    return web.json_response(download_status)

@PromptServer.instance.routes.post("/umiapp/models/save_token")
async def save_api_token(request):
    try:
        data = await request.json()
        token = data.get("token", "")
        save_umi_config({"civitai_token": token})
        return web.json_response({"status": "saved"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/umiapp/models/set_active")
async def set_active_version(request):
    try:
        data = await request.json()
        model_name = data.get("model_name")
        version = data.get("version")

        if not model_name or not version:
            return web.json_response({"error": "Missing parameters"}, status=400)

        update_installed_version(model_name, version)
        return web.json_response({"status": "updated", "message": f"Set active version for {model_name} to {version}"})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/umiapp/models/check")
async def check_models(request):
    repo_id = request.rel_url.query.get("repo_id", "")
    if not repo_id:
        return web.json_response({"error": "No repo_id provided"}, status=400)

    if " " in repo_id or repo_id.strip() == "":
        return web.json_response({"error": f"Invalid Repo ID format: '{repo_id}'"}, status=400)

    if not HF_HUB_AVAILABLE:
        return web.json_response({"error": "huggingface_hub is not installed"}, status=500)

    try:
        def fetch_config():
            return _fetch_model_config(repo_id)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        config = await loop.run_in_executor(None, fetch_config)

        active_registry = get_installed_version_info()

        grouped_models = {}
        for model in config.get("models", []):
            name = model["name"]
            grouped_models.setdefault(name, []).append(model)

        models_status = []
        for name, variants in grouped_models.items():
            try:
                from packaging import version
                variants.sort(key=lambda x: version.parse(x["version"]), reverse=True)
            except Exception:
                variants.sort(key=lambda x: str(x["version"]), reverse=True)

            latest = variants[0]
            active_ver = active_registry.get(name, None)

            installed_versions = []
            for v in variants:
                files = v.get("files") or []
                if files:
                    all_found = True
                    for f in files:
                        file_path = f.get("local_path") or ""
                        if not file_path:
                            all_found = False
                            break
                        if not os.path.exists(resolve_path(file_path)):
                            all_found = False
                            break
                    if all_found:
                        installed_versions.append(v["version"])
                else:
                    full_path = resolve_path(v.get("local_path", ""))
                    if os.path.exists(full_path):
                        installed_versions.append(v["version"])

            if active_ver and active_ver not in installed_versions:
                active_ver = None

            if not active_ver and installed_versions:
                for v in variants:
                    if v["version"] in installed_versions:
                        active_ver = v["version"]
                        break

            status = "missing"
            if active_ver:
                status = "installed" if active_ver == latest["version"] else "outdated"
            elif installed_versions:
                status = "outdated"

            models_status.append({
                "name": name,
                "status": status,
                "active_version": active_ver,
                "installed_versions": installed_versions,
                "version": latest["version"],
                "versions": variants,
                "description": latest.get("description", "")
            })

        return web.json_response({"models": models_status})

    except Exception as e:
        err_msg = str(e)
        if "HFValidationError" in err_msg or "Repo id" in err_msg:
            return web.json_response({"error": f"Invalid Repo ID: {repo_id}"}, status=400)
        if "404" in err_msg or "NotFound" in err_msg:
            return web.json_response({"error": "Repository or config not found"}, status=404)

        traceback.print_exc()
        return web.json_response({"error": f"{str(e)}"}, status=500)

@PromptServer.instance.routes.post("/umiapp/models/download")
async def download_model(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    repo_id = data.get("repo_id")
    model_name = data.get("model_name")
    target_version = data.get("version")

    if not repo_id or " " in repo_id:
        return web.json_response({"error": "Invalid Repo ID"}, status=400)

    if not HF_HUB_AVAILABLE:
        return web.json_response({"error": "huggingface_hub is not installed"}, status=500)

    try:
        def fetch_config_sync():
            return _fetch_model_config(repo_id)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        config = await loop.run_in_executor(None, fetch_config_sync)

        target_model = next((m for m in config["models"]
                             if m["name"] == model_name and m["version"] == target_version), None)

        if not target_model:
            target_model = next((m for m in config["models"] if m["name"] == model_name), None)

        if not target_model:
            return web.json_response({"error": f"Model '{model_name}' (v{target_version}) not found in config"}, status=404)

        download_status[model_name] = {"status": "queued", "message": "Queued in backend..."}
        download_queue.put((repo_id, model_name, target_model))

        return web.json_response({"status": "queued", "message": f"Download queued for {model_name}"})

    except Exception as e:
        if "HFValidationError" in str(e):
            return web.json_response({"error": "Invalid Repo ID"}, status=400)
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/umiapp/models/progress")
async def get_download_progress(request):
    download_id = request.query.get("id", "")
    if download_id and download_id in download_status:
        return web.json_response(download_status[download_id])
    return web.json_response(download_status)

# 2. Mappings
CORE_NODE_CLASS_MAPPINGS = {
    "UmiAIWildcardNode": UmiAIWildcardNode,
    "UmiAIWildcardNodeLite": UmiAIWildcardNodeLite,
    "UmiSaveImage": UmiSaveImage,
    "UmiCharacterManager": UmiCharacterManager,
    "UmiCharacterBatch": UmiCharacterBatch,
    "UmiSpriteExport": UmiSpriteExport,
    "UmiCharacterInfo": UmiCharacterInfo,
    "UmiCameraControl": UmiCameraControl,
    "UmiVisualCameraControl": UmiVisualCameraControl,
    "UmiPoseLibrary": UmiPoseLibrary,
    "UmiExpressionMixer": UmiExpressionMixer,
    "UmiSceneComposer": UmiSceneComposer,
    "UmiLoraAnimator": UmiLoraAnimator,
    "UmiPromptTemplate": UmiPromptTemplate,
    "UmiDatasetExport": UmiDatasetExport,
    "UmiCaptionGenerator": UmiCaptionGenerator,
    "UmiAutoCaption": UmiAutoCaption,
    "UmiCaptionEnhancer": UmiCaptionEnhancer,
    "UmiQWENDetailer": UmiQWENDetailer,
    "UmiBBoxExtractor": UmiBBoxExtractor,
    "UmiQWENEncoder": UmiQWENEncoder,
    "UmiPoseGenerator": UmiPoseGenerator,
    "UmiEmotionGenerator": UmiEmotionGenerator,
    "UmiEmotionStudio": UmiEmotionStudio,
    "UmiCharacterDesigner": UmiCharacterCreator2,
    "UmiCameraAngleSelector": UmiCameraAngleSelector,
    "UmiModelManager": UmiModelManager,
    "UmiModelSelector": UmiModelSelector,
}

SHEET_NODE_CLASS_MAPPINGS = {
    "UmiSheetManager": VNCCSSheetManager,
    "UmiSheetExtractor": VNCCSSheetExtractor,
    "UmiChromaKey": VNCCSChromaKey,
    "UmiColorFix": VNCCS_ColorFix,
    "UmiResize": VNCCS_Resize,
    "UmiMaskExtractor": VNCCS_MaskExtractor,
    "UmiRMBG2": VNCCS_RMBG2,
    "UmiQuadSplitter": VNCCS_QuadSplitter,
    "UmiCharacterSheetCropper": CharacterSheetCropper,
}

CORE_NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiAIWildcardNode": "UmiAI Wildcard Processor",
    "UmiAIWildcardNodeLite": "UmiAI Wildcard Processor (Lite)",
    "UmiSaveImage": "Umi Save Image (with metadata)",
    "UmiCharacterManager": "UmiAI Character Manager",
    "UmiCharacterBatch": "UmiAI Character Batch Generator",
    "UmiSpriteExport": "UmiAI Sprite Export",
    "UmiCharacterInfo": "UmiAI Character Info",
    "UmiCameraControl": "UmiAI Camera Control",
    "UmiVisualCameraControl": "UmiAI Visual Camera Control",
    "UmiCameraAngleSelector": "UmiAI 3D Camera Angle Selector",
    "UmiPoseLibrary": "UmiAI Pose Library",
    "UmiExpressionMixer": "UmiAI Expression Mixer",
    "UmiSceneComposer": "UmiAI Scene Composer",
    "UmiLoraAnimator": "UmiAI LoRA Strength Animator",
    "UmiPromptTemplate": "UmiAI Prompt Template",
    "UmiDatasetExport": "UmiAI Dataset Export (LoRA Training)",
    "UmiCaptionGenerator": "UmiAI Caption Generator",
    "UmiAutoCaption": "UmiAI Auto Caption (Wrapper)",
    "UmiCaptionEnhancer": "UmiAI Caption Enhancer",
    "UmiQWENDetailer": "Umi QWEN Detailer",
    "UmiBBoxExtractor": "Umi BBox Extractor",
    "UmiQWENEncoder": "Umi QWEN Encoder",
    "UmiPoseGenerator": "Umi Pose Generator",
    "UmiEmotionGenerator": "Umi Emotion Generator",
    "UmiEmotionStudio": "Umi Emotion Studio",
    "UmiCharacterDesigner": "Umi Character Designer",
    "UmiModelManager": "Umi Model Manager",
    "UmiModelSelector": "Umi Model Selector",
}

SHEET_NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiSheetManager": "Umi Sheet Manager",
    "UmiSheetExtractor": "Umi Sheet Extractor",
    "UmiChromaKey": "Umi Chroma Key",
    "UmiColorFix": "Umi Color Fix",
    "UmiResize": "Umi Resize",
    "UmiMaskExtractor": "Umi Mask Extractor",
    "UmiRMBG2": "Umi RMBG2",
    "UmiQuadSplitter": "Umi Quad Splitter",
    "UmiCharacterSheetCropper": "Umi Character Sheet Cropper",
}

NODE_CLASS_MAPPINGS = {}
NODE_CLASS_MAPPINGS.update(CORE_NODE_CLASS_MAPPINGS)
NODE_CLASS_MAPPINGS.update(SHEET_NODE_CLASS_MAPPINGS)

NODE_DISPLAY_NAME_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS.update(CORE_NODE_DISPLAY_NAME_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(SHEET_NODE_DISPLAY_NAME_MAPPINGS)

# 3. Expose the web directory
WEB_DIRECTORY = "./js"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
