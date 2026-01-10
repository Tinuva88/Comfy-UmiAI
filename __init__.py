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
from server import PromptServer
from aiohttp import web
import os
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
# MODEL DOWNLOADER API
# ==============================================================================

import json
import asyncio
import aiohttp

# Download progress tracking
_download_progress = {}

def load_model_manifest():
    """Load the model manifest file."""
    manifest_path = os.path.join(os.path.dirname(__file__), "models_manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

@PromptServer.instance.routes.get("/umiapp/models/manifest")
async def get_model_manifest(request):
    """Return the full model manifest."""
    manifest = load_model_manifest()
    if not manifest:
        return web.json_response({"error": "Manifest not found"}, status=404)
    return web.json_response(manifest)

@PromptServer.instance.routes.get("/umiapp/models/status")
async def get_models_status(request):
    """Check which models are installed."""
    manifest = load_model_manifest()
    if not manifest:
        return web.json_response({"error": "Manifest not found"}, status=404)
    
    models_dir = folder_paths.models_dir
    status = {}
    total_required = 0
    installed_required = 0
    
    for cat_id, category in manifest.get("categories", {}).items():
        cat_status = {
            "name": category.get("name", cat_id),
            "models": []
        }
        
        target_dir = os.path.join(models_dir, category.get("target_dir", ""))
        
        for model in category.get("models", []):
            filename = model.get("filename", "")
            model_path = os.path.join(target_dir, filename)
            installed = os.path.exists(model_path)
            
            if model.get("required", False):
                total_required += 1
                if installed:
                    installed_required += 1
            
            cat_status["models"].append({
                "name": model.get("name", filename),
                "filename": filename,
                "installed": installed,
                "required": model.get("required", False),
                "size_mb": model.get("size_mb", 0)
            })
        
        status[cat_id] = cat_status
    
    return web.json_response({
        "status": status,
        "summary": {
            "total_required": total_required,
            "installed_required": installed_required,
            "ready": installed_required >= total_required
        }
    })

@PromptServer.instance.routes.post("/umiapp/models/download")
async def download_model(request):
    """Start downloading a model."""
    global _download_progress
    
    try:
        data = await request.json()
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    category_id = data.get("category")
    model_name = data.get("model")
    
    if not category_id or not model_name:
        return web.json_response({"error": "category and model required"}, status=400)
    
    manifest = load_model_manifest()
    if not manifest:
        return web.json_response({"error": "Manifest not found"}, status=404)
    
    # Find the model
    category = manifest.get("categories", {}).get(category_id)
    if not category:
        return web.json_response({"error": "Category not found"}, status=404)
    
    model = None
    for m in category.get("models", []):
        if m.get("name") == model_name:
            model = m
            break
    
    if not model:
        return web.json_response({"error": "Model not found"}, status=404)
    
    # Prepare download
    models_dir = folder_paths.models_dir
    target_dir = os.path.join(models_dir, category.get("target_dir", ""))
    os.makedirs(target_dir, exist_ok=True)
    
    target_path = os.path.join(target_dir, model.get("filename", ""))
    url = model.get("url", "")
    
    if not url:
        return web.json_response({"error": "No download URL"}, status=400)
    
    # Start async download
    download_id = f"{category_id}_{model_name}"
    _download_progress[download_id] = {
        "status": "starting",
        "progress": 0,
        "total": model.get("size_mb", 0) * 1024 * 1024,
        "downloaded": 0
    }
    
    async def do_download():
        try:
            _download_progress[download_id]["status"] = "downloading"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        _download_progress[download_id]["status"] = "error"
                        _download_progress[download_id]["error"] = f"HTTP {response.status}"
                        return
                    
                    total = int(response.headers.get('content-length', 0))
                    _download_progress[download_id]["total"] = total
                    
                    # Create parent directories if needed
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    
                    with open(target_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                            f.write(chunk)
                            downloaded += len(chunk)
                            _download_progress[download_id]["downloaded"] = downloaded
                            if total > 0:
                                _download_progress[download_id]["progress"] = int(downloaded / total * 100)
            
            _download_progress[download_id]["status"] = "complete"
            _download_progress[download_id]["progress"] = 100
            print(f"[UmiAI] Downloaded: {target_path}")
            
        except Exception as e:
            _download_progress[download_id]["status"] = "error"
            _download_progress[download_id]["error"] = str(e)
            print(f"[UmiAI] Download error: {e}")
    
    asyncio.create_task(do_download())
    
    return web.json_response({
        "download_id": download_id,
        "status": "started",
        "target": target_path
    })

@PromptServer.instance.routes.get("/umiapp/models/progress")
async def get_download_progress(request):
    """Get download progress."""
    download_id = request.query.get("id", "")
    
    if download_id and download_id in _download_progress:
        return web.json_response(_download_progress[download_id])
    
    # Return all progress
    return web.json_response(_download_progress)

@PromptServer.instance.routes.post("/umiapp/models/download-all")
async def download_all_required(request):
    """Download all required models."""
    manifest = load_model_manifest()
    if not manifest:
        return web.json_response({"error": "Manifest not found"}, status=404)
    
    queued = []
    for cat_id, category in manifest.get("categories", {}).items():
        for model in category.get("models", []):
            if model.get("required", False):
                # Check if already installed
                models_dir = folder_paths.models_dir
                target_dir = os.path.join(models_dir, category.get("target_dir", ""))
                target_path = os.path.join(target_dir, model.get("filename", ""))
                
                if not os.path.exists(target_path):
                    queued.append({
                        "category": cat_id,
                        "model": model.get("name")
                    })
    
    return web.json_response({
        "queued": queued,
        "count": len(queued)
    })

# 2. Mappings
NODE_CLASS_MAPPINGS = {
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
    "UmiPoseGenerator": UmiPoseGenerator,
    "UmiEmotionGenerator": UmiEmotionGenerator,
    "UmiEmotionStudio": UmiEmotionStudio,
    "UmiCharacterDesigner": UmiCharacterCreator2,
    "UmiCameraAngleSelector": UmiCameraAngleSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
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
    "UmiPoseGenerator": "Umi Pose Generator",
    "UmiEmotionGenerator": "Umi Emotion Generator",
    "UmiEmotionStudio": "Umi Emotion Studio",
    "UmiCharacterDesigner": "Umi Character Designer",
}

# 3. Expose the web directory
WEB_DIRECTORY = "./js"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']