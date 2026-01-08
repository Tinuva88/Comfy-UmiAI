from .nodes import UmiAIWildcardNode, UmiSaveImage
from .nodes_lite import UmiAIWildcardNodeLite
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
                                # Strip weights and tags for preview
                                if '::' in line:
                                    line = line.split('::')[0]
                                elif ':' in line:
                                    parts = line.rsplit(':', 1)
                                    if len(parts) == 2 and parts[1].replace('.', '').isdigit():
                                        line = parts[0]
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
                        if '::' in line:
                            line = line.split('::')[0]
                        elif ':' in line:
                            parts = line.rsplit(':', 1)
                            if len(parts) == 2 and parts[1].replace('.', '').isdigit():
                                line = parts[0]
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

# 2. Mappings
NODE_CLASS_MAPPINGS = {
    "UmiAIWildcardNode": UmiAIWildcardNode,
    "UmiAIWildcardNodeLite": UmiAIWildcardNodeLite,
    "UmiSaveImage": UmiSaveImage
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiAIWildcardNode": "UmiAI Wildcard Processor",
    "UmiAIWildcardNodeLite": "UmiAI Wildcard Processor (Lite)",
    "UmiSaveImage": "Umi Save Image (with metadata)"
}

# 3. Expose the web directory
WEB_DIRECTORY = "./js"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']