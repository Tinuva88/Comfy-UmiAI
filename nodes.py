import os
import random
import re
import yaml
import glob
import json
import csv
import requests
import fnmatch
import gc 
import sys
import subprocess
from collections import Counter, OrderedDict
import folder_paths
import comfy.sd
import comfy.utils
import torch 
from safetensors import safe_open 

# New imports for Vision support
import base64
import io
import numpy as np
from PIL import Image

# API Imports
import server
from aiohttp import web

import importlib
import sys

# Import shared utilities
from . import shared_utils
importlib.reload(shared_utils)

from .shared_utils import (
    escape_unweighted_colons, parse_wildcard_weight, get_all_wildcard_paths, log_prompt_to_history,
    LogicEvaluator, DynamicPromptReplacer, VariableReplacer, NegativePromptGenerator,
    ConditionalReplacer, TagLoaderBase, TagSelectorBase, LoRAHandlerBase, TagReplacerBase,
    CharacterReplacer, resolve_lora_alias
)

# ==============================================================================
# GLOBAL CACHE & SETUP
# ==============================================================================
GLOBAL_CACHE = {}
GLOBAL_INDEX = {'built': False, 'files': set(), 'entries': {}, 'tags': set()}

# Fix 12: File modification time cache to skip rescanning unchanged files
FILE_MTIME_CACHE = {}

# LRU CACHE
LORA_MEMORY_CACHE = OrderedDict()

# REGISTER LLM FOLDER
folder_paths.add_model_folder_path("llm", os.path.join(folder_paths.models_dir, "llm"))

# ==============================================================================
# OPTIONAL IMPORTS (LLM & Downloader)
# ==============================================================================
LLAMA_CPP_AVAILABLE = False
try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    pass

HF_HUB_AVAILABLE = False
try:
    from huggingface_hub import hf_hub_download
    HF_HUB_AVAILABLE = True
except ImportError:
    pass

# ==============================================================================
# AUTO-UPDATE LOGIC
# ==============================================================================
def perform_library_update():
    print("\n[UmiAI] STARTING AUTO-UPDATE OF LLAMA-CPP-PYTHON...")
    
    # 1. Detect CUDA Version to choose right wheel
    cuda_ver = ""
    try:
        raw_ver = torch.version.cuda
        if raw_ver:
            cuda_ver = raw_ver.replace(".", "")
            print(f"[UmiAI] Detected CUDA Version: {raw_ver}")
    except:
        pass

    # 2. Select URL based on CUDA (Defaulting to cu124 for modern ComfyUI)
    # Most ComfyUI portables are on 12.1 or 12.4
    extra_url = "https://abetlen.github.io/llama-cpp-python/whl/cu124"
    
    if "121" in cuda_ver:
        extra_url = "https://abetlen.github.io/llama-cpp-python/whl/cu121"
    elif "118" in cuda_ver or "117" in cuda_ver:
        extra_url = "https://abetlen.github.io/llama-cpp-python/whl/cu117"
    elif not cuda_ver:
        # Fallback for CPU only
        extra_url = "https://abetlen.github.io/llama-cpp-python/whl/cpu"

    print(f"[UmiAI] Target Wheel URL: {extra_url}")

    # 3. Construct Pip Command
    cmd = [
        sys.executable, "-m", "pip", "install", 
        "llama-cpp-python", 
        "--upgrade", "--force-reinstall", "--no-cache-dir", 
        "--extra-index-url", extra_url
    ]

    try:
        subprocess.check_call(cmd)
        print("\n[UmiAI] UPDATE SUCCESSFUL!")
        print("[UmiAI] =====================================================")
        print("[UmiAI] YOU MUST RESTART COMFYUI NOW FOR CHANGES TO TAKE EFFECT.")
        print("[UmiAI] =====================================================\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[UmiAI] UPDATE FAILED: {e}")
        return False

# ==============================================================================
# CUSTOM HANDLER FOR JOYCAPTION
# ==============================================================================
if LLAMA_CPP_AVAILABLE:
    class JoyCaptionChatHandler(Llava15ChatHandler):
        def __init__(self, clip_model_path, verbose=False):
            super().__init__(clip_model_path=clip_model_path, verbose=verbose)

        def _format_prompt(self, messages, **kwargs):
            # Strict Llama 3 Template for JoyCaption
            prompt = ""
            for message in messages:
                role = message["role"]
                content = message["content"]
                
                # JoyCaption (Alpha 2) works best without a system prompt interfering
                if role == "system":
                    continue 
                
                elif role == "user":
                    prompt += f"<|start_header_id|>user<|end_header_id|>\n\n"
                    
                    has_image = False
                    text_content = ""
                    
                    if isinstance(content, list):
                        for item in content:
                            if item["type"] == "text":
                                text_content += item["text"]
                            elif item["type"] == "image_url":
                                has_image = True
                    else:
                        text_content += str(content)
                    
                    prompt += text_content
                    # JoyCaption expects the image token at the END of the user message
                    if has_image:
                        prompt += "\n<image>"
                        
                    prompt += "<|eot_id|>"
                
                elif role == "assistant":
                    prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>"
            
            prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"
            return prompt

# ==============================================================================
# CONSTANTS & HELPER FUNCTIONS
# ==============================================================================

DOWNLOADABLE_MODELS = {
    "Download: JoyCaption-Alpha-2 (Best Accuracy - Requires Update)": {
        "repo_id": "bartowski/JoyCaption-Alpha-Two-Llama3-GGUF",
        "filename": "JoyCaption-Alpha-Two-Llama3-Q4_K_M.gguf",
        "mmproj": "JoyCaption-Alpha-Two-Llama3-mmproj-f16.gguf" 
    },
    "Download: Llava-v1.5-7b (Standard Vision - Stable)": {
        "repo_id": "cjpais/llava-1.5-7b-gguf",
        "filename": "llava-v1.5-7b-Q4_K.gguf",
        "mmproj": "llava-v1.5-7b-mmproj-Q4_0.gguf" 
    },
    "Download: Qwen2.5-1.5B (Text Refiner - Smart & Fast)": {
        "repo_id": "bartowski/Qwen2.5-Coder-1.5B-Instruct-abliterated-GGUF",
        "filename": "Qwen2.5-Coder-1.5B-Instruct-abliterated-Q4_K_M.gguf"
    },
    "Download: Dolphin-Llama3.1-8B (Text Refiner - Creative)": {
        "repo_id": "bartowski/dolphin-2.9.4-llama3.1-8b-GGUF",
        "filename": "dolphin-2.9.4-llama3.1-8b-Q4_K_M.gguf"
    },
    "Download: Wingless Imp 8B (Llama-3 - Creative RP)": {
        "repo_id": "mradermacher/Wingless_Imp_8B-GGUF",
        "filename": "Wingless_Imp_8B.Q4_K_M.gguf"
    }
}

ALL_KEY = 'all_files_index'

def load_umi_settings():
    """Load user settings from umi_settings.json"""
    settings_path = os.path.join(os.path.dirname(__file__), "umi_settings.json")
    defaults = {
        'use_folder_paths': False,  # False = __MyFile__, True = __Series/MyFile__
        'csv_namespace': True,  # Add $csv_ prefixed variables for CSV columns
        'yaml_namespace': True,  # Add $yaml_ prefixed variables for YAML entries
        'rng_streams': False,  # Use deterministic RNG streams per scope/tag
    }
    
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
                defaults.update({k: v for k, v in user_settings.items() if not k.startswith('_')})
        except Exception as e:
            print(f"[UmiAI] Warning: Could not load umi_settings.json: {e}")
    
    return defaults

# Cache settings at startup
UMI_SETTINGS = load_umi_settings()

def is_valid_image(image_input):
    """Safe check for image tensor availability."""
    if image_input is None:
        return False
    if isinstance(image_input, torch.Tensor):
        return True
    return False

def parse_tag(tag):
    if tag is None:
        return ""
    tag = tag.replace("__", "").replace('<', '').replace('>', '').strip()
    if tag.startswith('#'):
        return tag
    return tag

def read_file_lines(file):
    f_lines = file.read().splitlines()
    lines = []
    for line in f_lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        if '//' in line:
            line = re.sub(r'(?<!:)//[^,\n]*', '', line).strip()
            if not line:
                continue
        if '#' in line:
            line = line.split('#')[0].strip()

        # Parse using shared utility function
        parsed = parse_wildcard_weight(line)
        lines.append(parsed)

    return lines

def append_trace_summary(prompt, variables):
    summary = variables.get('trace_summary')
    if not summary or str(summary).strip() in ("0", "false", "False"):
        return prompt

    def _level(val):
        if val is None:
            return 1
        if isinstance(val, (int, float)):
            return max(0, int(val))
        s = str(val).strip()
        if s.isdigit():
            return int(s)
        if s.lower() in ("true", "yes", "on"):
            return 1
        return 0

    level = _level(variables.get('trace'))
    parts = [
        "TRACE",
        f"seed={variables.get('trace_seed', '')}",
        f"run={variables.get('trace_run_id', '')}",
    ]
    if variables.get('trace_last_type'):
        parts.append(f"type={variables.get('trace_last_type')}")
    if variables.get('trace_last_source'):
        parts.append(f"src={variables.get('trace_last_source')}")
    if variables.get('trace_last_pick'):
        parts.append(f"pick={variables.get('trace_last_pick')}")
    if level >= 2:
        if variables.get('trace_row_id'):
            parts.append(f"row_id={variables.get('trace_row_id')}")
        if variables.get('trace_row_index'):
            parts.append(f"row={variables.get('trace_row_index')}")
        if variables.get('trace_yaml_entry'):
            parts.append(f"yaml={variables.get('trace_yaml_entry')}")
        if variables.get('trace_last_roll') and variables.get('trace_last_total_weight'):
            parts.append(f"roll={variables.get('trace_last_roll')}/{variables.get('trace_last_total_weight')}")
        if variables.get('trace_last_condition'):
            parts.append(f"cond={variables.get('trace_last_condition')}")
        if variables.get('trace_last_branch'):
            parts.append(f"branch={variables.get('trace_last_branch')}")
        if variables.get('trace_last_var') and variables.get('trace_last_var_source'):
            parts.append(f"var={variables.get('trace_last_var')}:{variables.get('trace_last_var_source')}")

    trace_line = "<<{}>>".format(" | ".join(p for p in parts if p))
    return f"{trace_line}\n{prompt}"

def append_debug_summary(prompt, variables):
    summary = variables.get('debug_summary')
    if not summary or str(summary).strip() in ("0", "false", "False"):
        return prompt

    def _level(val):
        if val is None:
            return 1
        if isinstance(val, (int, float)):
            return max(0, int(val))
        s = str(val).strip()
        if s.isdigit():
            return int(s)
        if s.lower() in ("true", "yes", "on"):
            return 1
        return 0

    level = _level(variables.get('debug'))
    parts = [
        "DBG",
        f"seed={variables.get('debug_seed', '')}",
        f"run={variables.get('debug_run_id', '')}",
    ]
    if variables.get('debug_last_type'):
        parts.append(f"type={variables.get('debug_last_type')}")
    if variables.get('debug_last_source'):
        parts.append(f"src={variables.get('debug_last_source')}")
    if variables.get('debug_last_pick'):
        parts.append(f"pick={variables.get('debug_last_pick')}")
    if level >= 2:
        if variables.get('debug_last_count'):
            parts.append(f"count={variables.get('debug_last_count')}")
        if variables.get('debug_row_id'):
            parts.append(f"row_id={variables.get('debug_row_id')}")
        if variables.get('debug_row_index'):
            parts.append(f"row={variables.get('debug_row_index')}")
        if variables.get('debug_yaml_entry'):
            parts.append(f"yaml={variables.get('debug_yaml_entry')}")
        if variables.get('debug_last_roll') and variables.get('debug_last_total_weight'):
            parts.append(f"roll={variables.get('debug_last_roll')}/{variables.get('debug_last_total_weight')}")

    dbg_line = "<<{}>>".format(" | ".join(p for p in parts if p))
    return f"{dbg_line}\n{prompt}"

def parse_wildcard_range(range_str, num_variants):
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

def process_wildcard_range(tag, lines, rng):
    if not lines:
        return ""
    if tag.startswith('#'):
        return None
    
    if "$$" not in tag:
        selected = rng.choice(lines)
        if '#' in selected:
            selected = selected.split('#')[0].strip()
        return selected
        
    range_str, tag_name = tag.split("$$", 1)
    try:
        low, high = parse_wildcard_range(range_str, len(lines))
        num_items = rng.randint(low, high)
        if num_items == 0:
            return ""
            
        selected = rng.sample(lines, min(num_items, len(lines)))
        selected = [line.split('#')[0].strip() if '#' in line else line for line in selected]
        return ", ".join(selected)
    except Exception as e:
        print(f"Error processing wildcard range: {e}")
        selected = rng.choice(lines)
        if '#' in selected:
            selected = selected.split('#')[0].strip()
        return selected

# ==============================================================================
# CORE CLASSES
# ==============================================================================

class TagLoader(TagLoaderBase):
    def __init__(self, wildcard_paths, options):
        super().__init__(wildcard_paths, options)
        # Full version uses wildcard_locations (alias for wildcard_paths)
        self.wildcard_locations = self.wildcard_paths

        self.loaded_tags = {}
        self.yaml_entries = {}
        self.index_built = False
        # Toggle: False = filename only (__MyFile__), True = include folder paths (__Series/MyFile__)
        self.use_folder_paths = options.get('use_folder_paths', False)
        
        self.txt_lookup = {}
        self.yaml_lookup = {}
        self.csv_lookup = {}
        
        self.refresh_maps()

    def refresh_maps(self):
        self.txt_lookup = {}
        self.yaml_lookup = {}
        self.csv_lookup = {}
        
        for location in self.wildcard_locations:
            if not os.path.exists(location):
                continue
                
            for root, dirs, files in os.walk(location):
                for file in files:
                    full_path = os.path.join(root, file)
                    
                    # Toggle between filename-only and full path modes
                    if self.use_folder_paths:
                        # Full path mode: __Series/A Centaur's Life__
                        rel_path = os.path.relpath(full_path, location)
                        key = os.path.splitext(rel_path)[0].replace(os.sep, '/')
                    else:
                        # Filename only mode: __A Centaur's Life__
                        key = os.path.splitext(file)[0]
                    
                    name_lower = file.lower()
                    key_lower = key.lower()
                    
                    if name_lower.endswith('.txt'):
                        # Handle conflicts by keeping first found
                        if key_lower not in self.txt_lookup:
                            self.txt_lookup[key_lower] = full_path
                    elif name_lower.endswith('.yaml'):
                        if key_lower not in self.yaml_lookup:
                            self.yaml_lookup[key_lower] = full_path
                    elif name_lower.endswith('.csv'):
                        if key_lower not in self.csv_lookup:
                            self.csv_lookup[key_lower] = full_path

    def load_prompt_file(self, file_key):
        """Phase 6: Load entire .txt file content as a prompt (no parsing)"""
        key = file_key.strip()
        if key.lower().endswith('.txt'):
            key = key[:-4]
        key_lower = key.lower()
        lookup_keys = [key_lower]
        if '/' in key_lower:
            lookup_keys.append(key_lower.split('/')[-1])

        for lookup_key in lookup_keys:
            if lookup_key in self.txt_lookup:
                full_path = self.txt_lookup[lookup_key]
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    return content
                except Exception as e:
                    if self.verbose:
                        print(f"[UmiAI] Error reading prompt file {full_path}: {e}")
                    return None
        return None

    def build_index(self):
        # Check if cache was built with a different use_folder_paths setting
        cached_setting = GLOBAL_INDEX.get('use_folder_paths', None)
        if GLOBAL_INDEX['built'] and cached_setting == self.use_folder_paths:
            self.files_index = GLOBAL_INDEX['files']
            self.yaml_entries = GLOBAL_INDEX['entries']
            self.umi_tags = GLOBAL_INDEX.get('tags', set())
            self.index_built = True
            return
        
        # Rebuild if setting changed
        if GLOBAL_INDEX['built'] and cached_setting != self.use_folder_paths:
            print(f"[UmiAI] Rebuilding index: use_folder_paths changed from {cached_setting} to {self.use_folder_paths}")
            # Need to rebuild lookup maps with new setting and reset cache
            self.refresh_maps()
            GLOBAL_INDEX['built'] = False  # Force rebuild
            self.index_built = False

        if self.index_built:
            return

        new_index = set()
        new_entries = {}
        new_tags = set()
        
        for key in self.txt_lookup.keys():
            new_index.add(key)
        for key in self.csv_lookup.keys():
            new_index.add(key)

        for file_key, full_path in self.yaml_lookup.items():
            if file_key == 'globals':
                continue
            try:
                with open(full_path, encoding="utf8") as f:
                    data = yaml.safe_load(f)

                    # Phase 7: Unified YAML format - always process entries with tags
                    if isinstance(data, dict):
                        for k, v in data.items():
                            new_index.add(k)
                            if isinstance(v, dict):
                                processed = self.process_yaml_entry(k, v)
                                if processed['tags']:
                                    new_entries[k.lower()] = processed
                                    for t in processed['tags']:
                                        new_tags.add(t)
            except Exception as e:
                pass

        self.files_index = new_index
        self.yaml_entries = new_entries
        self.umi_tags = new_tags
        self.index_built = True
        
        GLOBAL_INDEX['files'] = new_index
        GLOBAL_INDEX['entries'] = new_entries
        GLOBAL_INDEX['tags'] = new_tags
        GLOBAL_INDEX['built'] = True
        GLOBAL_INDEX['use_folder_paths'] = self.use_folder_paths

    def load_globals(self):
        merged_globals = {}
        for location in self.wildcard_locations:
            global_path = os.path.join(location, 'globals.yaml')
            if os.path.exists(global_path):
                try:
                    with open(global_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            merged_globals.update({str(k): str(v) for k, v in data.items()})
                except yaml.YAMLError as e:
                    print(f"[UmiAI] ERROR: Malformed globals.yaml at {global_path}: {e}")
                    print(f"[UmiAI] Global variables from this file will not be loaded. Please fix YAML syntax.")
                except UnicodeDecodeError as e:
                    print(f"[UmiAI] ERROR: Encoding issue in globals.yaml at {global_path}: {e}")
                    print(f"[UmiAI] File must be UTF-8 encoded.")
                except Exception as e:
                    print(f"[UmiAI] WARNING: Error loading globals.yaml at {global_path}: {e}")
        return merged_globals

    def process_yaml_entry(self, title, entry_data):
        return {
            'title': title,
            'description': entry_data.get('Description', [None])[0] if isinstance(entry_data.get('Description', []), list) else None,
            'prompts': entry_data.get('Prompts', []),
            'prefixes': entry_data.get('Prefix', []),
            'suffixes': entry_data.get('Suffix', []),
            'tags': [x.lower().strip() for x in entry_data.get('Tags', [])]
        }
    
    # Phase 7: Removed is_umi_format() and flatten_hierarchical_yaml()
    # Now using unified YAML format with tag-based selection

    def load_tags(self, requested_tag, verbose=False):
        if requested_tag == ALL_KEY:
            self.build_index()
            if verbose:
                print(f"[UmiAI] load_tags(ALL_KEY) returning {len(self.yaml_entries)} YAML entries")
            return self.yaml_entries

        # Fix 12: Check modification time before using cached data
        if requested_tag in GLOBAL_CACHE:
            cached_path = FILE_MTIME_CACHE.get(requested_tag, {}).get('path')
            if cached_path and os.path.exists(cached_path):
                current_mtime = os.path.getmtime(cached_path)
                cached_mtime = FILE_MTIME_CACHE.get(requested_tag, {}).get('mtime', 0)
                if current_mtime == cached_mtime:
                    return GLOBAL_CACHE[requested_tag]
                else:
                    # File has been modified, invalidate cache
                    if verbose:
                        print(f"[UmiAI] File '{requested_tag}' modified, reloading...")

        lower_tag = requested_tag.lower()

        if lower_tag in self.txt_lookup:
            file_path = self.txt_lookup[lower_tag]
            with open(file_path, encoding="utf8") as f:
                lines = read_file_lines(f)
                GLOBAL_CACHE[requested_tag] = lines
                FILE_MTIME_CACHE[requested_tag] = {
                    'path': file_path,
                    'mtime': os.path.getmtime(file_path)
                }
                return lines

        if lower_tag in self.csv_lookup:
            file_path = self.csv_lookup[lower_tag]
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                GLOBAL_CACHE[requested_tag] = rows
                FILE_MTIME_CACHE[requested_tag] = {
                    'path': file_path,
                    'mtime': os.path.getmtime(file_path)
                }
                return rows

        parts = lower_tag.split('/')
        found_file = None
        key_suffix = ""

        if lower_tag in self.yaml_lookup:
            found_file = self.yaml_lookup[lower_tag]
        else:
            for i in range(len(parts) - 1, 0, -1):
                potential_file = "/".join(parts[:i])
                potential_key = "/".join(parts[i:])
                if potential_file in self.yaml_lookup:
                    found_file = self.yaml_lookup[potential_file]
                    key_suffix = potential_key
                    break
        
        if found_file:
            with open(found_file, encoding="utf8") as file:
                try:
                    data = yaml.safe_load(file)

                    # Phase 7: Unified YAML format - always process entries with tags
                    if isinstance(data, dict):
                        for title, entry in data.items():
                            if isinstance(entry, dict):
                                processed = self.process_yaml_entry(title, entry)
                                # Store in yaml_entries index if it has tags
                                if processed['tags']:
                                    self.yaml_entries[title.lower()] = processed

                        # If a specific key was requested (key_suffix), return its prompts
                        if key_suffix:
                            for k, v in data.items():
                                if k.lower() == key_suffix:
                                    processed = self.process_yaml_entry(k, v)
                                    GLOBAL_CACHE[requested_tag] = processed['prompts']
                                    FILE_MTIME_CACHE[requested_tag] = {
                                        'path': found_file,
                                        'mtime': os.path.getmtime(found_file)
                                    }
                                    return processed['prompts']
                            return []

                        # No specific key - return all prompts from all entries
                        all_prompts = []
                        for entry in data.values():
                            if isinstance(entry, dict):
                                processed = self.process_yaml_entry('', entry)
                                all_prompts.extend(processed['prompts'])
                        return all_prompts

                except Exception as e:
                    if verbose: print(f'Error parsing YAML {found_file}: {e}')

        return []

    def get_glob_matches(self, pattern):
        self.build_index()
        return fnmatch.filter(self.files_index, pattern)

    def get_entry_details(self, title):
        if title and title.lower() in self.yaml_entries:
            return self.yaml_entries[title.lower()]
        return self.yaml_entries.get(title)

class TagSelector(TagSelectorBase):
    def __init__(self, tag_loader, options):
        super().__init__(tag_loader, options)
        self.previously_selected_tags = {}
        self.used_values = {}
        self.selected_options = options.get('selected_options', {})
        self.global_seed = self.seed
        
        self.processing_stack = set()
        self.resolved_seeds = {}
        self.selected_entries = {} 

    def _set_yaml_vars(self, title, entry_details):
        if not UMI_SETTINGS.get('yaml_namespace', True):
            return
        if title:
            self.variables['yaml_title'] = str(title)
        tags = entry_details.get('tags', [])
        if tags:
            self.variables['yaml_tags'] = ", ".join(str(t) for t in tags)
        description = entry_details.get('description')
        if description:
            self.variables['yaml_description'] = str(description)
        prefixes = entry_details.get('prefixes', [])
        if prefixes:
            self.variables['yaml_prefixes'] = ", ".join(str(p) for p in prefixes)
        suffixes = entry_details.get('suffixes', [])
        if suffixes:
            self.variables['yaml_suffixes'] = ", ".join(str(s) for s in suffixes)

    def update_variables(self, variables):
        self.variables = variables

    def clear_seeded_values(self):
        self.seeded_values = {}
        self.resolved_seeds = {}
        self.processing_stack.clear()
        self.selected_entries.clear()
        self.scoped_negatives = []

    def _weighted_choice(self, items, rng=None):
        """Fix 13: Weighted random selection for lists with weights"""
        # Check if items have weights
        has_weights = all(isinstance(item, dict) and 'weight' in item for item in items)

        if not has_weights:
            # Fall back to normal choice for strings or unweighted dicts
            return (rng or self.rng).choice(items)

        # Weighted selection
        weights = [item.get('weight', 1.0) for item in items]
        total_weight = sum(weights)
        rand_val = (rng or self.rng).random() * total_weight
        cumsum = 0

        if self.is_debug_enabled():
            self.variables['debug_last_roll'] = f"{rand_val:.6f}"
            self.variables['debug_last_total_weight'] = f"{total_weight:.6f}"
        self.set_trace_info({
            "trace_last_roll": f"{rand_val:.6f}",
            "trace_last_total_weight": f"{total_weight:.6f}",
        })

        for item in items:
            cumsum += item.get('weight', 1.0)
            if rand_val <= cumsum:
                return item

        return items[-1]  # Fallback

    def process_scoped_negative(self, text):
        if not isinstance(text, str):
            return text
        if "--neg:" in text:
            parts = text.split("--neg:", 1)
            positive = parts[0].strip()
            negative = parts[1].strip()
            if negative:
                self.scoped_negatives.append(negative)
            return positive
        return text

    def get_tag_choice(self, parsed_tag, tags, logic_filter=None, rng=None):
        rng = rng or self.get_rng(parsed_tag)
        if isinstance(tags, list) and len(tags) > 0 and isinstance(tags[0], dict):
            # Check if it's a CSV file (has non-tag/weight keys)
            first_entry = tags[0]
            if not ('value' in first_entry or 'weight' in first_entry or 'tags' in first_entry):
                # This is CSV data
                row_index = rng.randrange(len(tags))
                row = tags[row_index]
                # CSV variable injection: directly inject columns into variables dict
                if self.is_debug_enabled():
                    self.variables['debug_last_type'] = "csv"
                    self.variables['debug_last_source'] = parsed_tag
                    self.variables['debug_row_index'] = str(row_index)
                    self.variables['debug_last_pick'] = str(row_index)
                    if isinstance(row, dict) and 'id' in row:
                        self.variables['debug_row_id'] = str(row.get('id'))
                self.set_trace_info({
                    "trace_last_type": "csv",
                    "trace_last_source": parsed_tag,
                    "trace_row_index": str(row_index),
                    "trace_last_pick": str(row_index),
                    "trace_row_id": str(row.get('id')) if isinstance(row, dict) and 'id' in row else "",
                })
                for k, v in row.items():
                    var_name = k.strip()
                    if var_name and var_name not in self.variables:
                        self.variables[var_name] = v.strip()
                    if var_name and UMI_SETTINGS.get('csv_namespace', True):
                        namespaced = f"csv_{var_name}"
                        if namespaced not in self.variables:
                            self.variables[namespaced] = v.strip()
                # Also return the old format for backwards compatibility
                vars_out = []
                for k, v in row.items():
                    vars_out.append(f"${k.strip()}={v.strip()}")
                return " ".join(vars_out)

        if not isinstance(tags, list):
            return ""

        # Phase 5: Filter entries by logic expression if provided
        if logic_filter:
            from .nodes_lite import LogicEvaluator  # Import shared evaluator
            evaluator = LogicEvaluator(logic_filter, self.variables)
            filtered_tags = []
            for tag in tags:
                if isinstance(tag, dict):
                    # Build tag context from entry tags
                    tag_dict = {t.lower(): True for t in tag.get('tags', [])}
                    if evaluator.evaluate(tag_dict):
                        filtered_tags.append(tag)
                else:
                    # String tag - can't filter
                    filtered_tags.append(tag)

            if not filtered_tags:
                if self.verbose:
                    print(f"[UmiAI] WARNING: No entries in '{parsed_tag}' matched logic '{logic_filter}'.")
                if self.is_failfast_enabled():
                    return f"<<ERROR_NO_MATCHES:{logic_filter} in {parsed_tag}>>"
                return f"[NO_MATCHES: {logic_filter} in {parsed_tag}]"

            tags = filtered_tags
        
        seed_match = re.match(r'#([0-9|]+)\$\$(.*)', parsed_tag)
        if seed_match:
            seed_options = seed_match.group(1).split('|')
            chosen_seed = rng.choice(seed_options)
            
            if chosen_seed in self.seeded_values:
                selected = self.seeded_values[chosen_seed]
                return self.resolve_wildcard_recursively(selected, chosen_seed)
            
            unused = [t for t in tags if t not in self.used_values]
            # Fix 13: Use weighted choice if tags have weights
            selected = self._weighted_choice(unused, rng=rng) if unused else self._weighted_choice(tags, rng=rng)

            self.seeded_values[chosen_seed] = selected
            self.used_values[selected] = True
            return self.resolve_wildcard_recursively(selected, chosen_seed)

        selected = None
        if len(tags) == 1:
            selected = tags[0]
        else:
            unused = [t for t in tags if t not in self.used_values]
            # Fix 13: Use weighted choice if tags have weights
            selected = self._weighted_choice(unused, rng=rng) if unused else self._weighted_choice(tags, rng=rng)

        if selected:
            # Fix 13: Extract value if selected is a weighted dict
            if isinstance(selected, dict) and 'value' in selected:
                selected_key = selected['value']
            else:
                selected_key = selected

            self.used_values[selected_key] = True
            entry_title = selected_key
            entry_details = self.tag_loader.get_entry_details(selected_key)
            if entry_details:
                self.selected_entries[parsed_tag] = entry_details
                self._set_yaml_vars(entry_title, entry_details)
                if self.is_debug_enabled():
                    self.variables['debug_yaml_entry'] = str(entry_title)
                self.set_trace_info({
                    "trace_yaml_entry": str(entry_title),
                    "trace_last_type": "yaml",
                    "trace_last_source": parsed_tag,
                })
                if entry_details['prompts']:
                    selected_key = rng.choice(entry_details['prompts'])
            if isinstance(selected_key, str) and '#' in selected_key:
                selected_key = selected_key.split('#')[0].strip()
            selected_key = self.process_scoped_negative(selected_key)
            if self.is_debug_enabled():
                self.variables['debug_last_type'] = "wildcard"
                self.variables['debug_last_source'] = parsed_tag
                self.variables['debug_last_pick'] = str(selected_key)
            self.set_trace_info({
                "trace_last_type": "wildcard",
                "trace_last_source": parsed_tag,
                "trace_last_pick": str(selected_key),
            })

            return selected_key

        return selected

    def resolve_wildcard_recursively(self, value, seed_id=None):
        if value.startswith('__') and value.endswith('__'):
            nested_tag = value[2:-2]
            nested_seed = f"{seed_id}_{nested_tag}" if seed_id else None
            
            if nested_tag in self.processing_stack:
                return value
            self.processing_stack.add(nested_tag)
            
            if nested_seed and nested_seed in self.resolved_seeds:
                resolved = self.resolved_seeds[nested_seed]
            else:
                resolved = self.select(nested_tag)
                if nested_seed:
                    self.resolved_seeds[nested_seed] = resolved
            
            self.processing_stack.remove(nested_tag)
            return resolved
        return value

    def get_tag_group_choice(self, parsed_tag, groups, tags, rng=None):
        if not isinstance(tags, dict):
            return ""
        rng = rng or self.get_rng(parsed_tag)
        rng = self.get_rng(parsed_tag)

        resolved_groups = []
        for g in groups:
            clean_g = g.strip()
            if clean_g.startswith('$') and clean_g[1:] in self.variables:
                val = self.variables[clean_g[1:]]
                resolved_groups.append(val)
            else:
                resolved_groups.append(clean_g)

        neg_groups = {x.replace('--', '').strip().lower() for x in resolved_groups if x.startswith('--')}
        pos_groups = {x.strip().lower() for x in resolved_groups if not x.startswith('--') and '|' not in x}
        any_groups = [{y.strip() for y in x.lower().split('|')} for x in resolved_groups if '|' in x]

        candidates = []
        for title, entry_data in tags.items():
            if isinstance(entry_data, dict):
                tag_set = set(entry_data.get('tags', []))
            elif isinstance(entry_data, (list, set)):
                tag_set = set(entry_data)
            else:
                continue

            if not pos_groups.issubset(tag_set):
                continue
            if not neg_groups.isdisjoint(tag_set):
                continue
            if any_groups:
                if not all(not group.isdisjoint(tag_set) for group in any_groups):
                    continue
            candidates.append(title)

        if candidates:
            seed_match = re.match(r'#([0-9|]+)\$\$(.*)', parsed_tag)
            seed_id = seed_match.group(1) if seed_match else None
            
            selected_title = rng.choice(candidates)
            if seed_id and seed_id in self.seeded_values:
                selected_title = self.seeded_values[seed_id]
            elif seed_id:
                self.seeded_values[seed_id] = selected_title
                
            entry_details = self.tag_loader.get_entry_details(selected_title)
            if entry_details:
                self.selected_entries[parsed_tag] = entry_details
                self._set_yaml_vars(selected_title, entry_details)
                if self.is_debug_enabled():
                    self.variables['debug_yaml_entry'] = str(selected_title)
                self.set_trace_info({
                    "trace_yaml_entry": str(selected_title),
                    "trace_last_type": "yaml",
                    "trace_last_source": parsed_tag,
                })
                if entry_details['prompts']:
                    chosen_prompt = rng.choice(entry_details['prompts'])
                    if self.is_debug_enabled():
                        self.variables['debug_last_type'] = "yaml"
                        self.variables['debug_last_source'] = parsed_tag
                        self.variables['debug_last_pick'] = str(chosen_prompt)
                    self.set_trace_info({
                        "trace_last_type": "yaml",
                        "trace_last_source": parsed_tag,
                        "trace_last_pick": str(chosen_prompt),
                    })
                    return self.resolve_wildcard_recursively(chosen_prompt, seed_id)
            if self.is_debug_enabled():
                self.variables['debug_last_type'] = "yaml"
                self.variables['debug_last_source'] = parsed_tag
                self.variables['debug_last_pick'] = str(selected_title)
            self.set_trace_info({
                "trace_last_type": "yaml",
                "trace_last_source": parsed_tag,
                "trace_last_pick": str(selected_title),
            })
            return self.resolve_wildcard_recursively(selected_title, seed_id)

        # Fix 11: Better error messages - show which logic expression failed to match
        logic_expr = " ".join(str(g) for g in groups)
        if self.verbose:
            print(f"[UmiAI] WARNING: No YAML entries matched tag logic '{logic_expr}' in '{parsed_tag}'.")
        return f"[NO_MATCHES: {logic_expr}]"

    def select(self, tag, groups=None):
        self.previously_selected_tags.setdefault(tag, 0)
        if self.previously_selected_tags.get(tag) > 500:
            return f"LOOP_ERROR({tag})"
        
        self.previously_selected_tags[tag] += 1
        parsed_tag = parse_tag(tag)
        self.init_debug_context()
        self.init_trace_context()
        scope_override = None
        if parsed_tag.startswith('@') and ':' in parsed_tag:
            scope_override, parsed_tag = parsed_tag[1:].split(':', 1)
            scope_override = scope_override.strip()
            parsed_tag = parsed_tag.strip()
        rng = self.get_rng(scope_override or parsed_tag)
        
        if '*' in parsed_tag or '?' in parsed_tag:
            matches = self.tag_loader.get_glob_matches(parsed_tag)
            if matches:
                rng.shuffle(matches)
                for selected_key in matches:
                    result = self.select(selected_key, groups)
                    if result and str(result).strip():
                        return result
            # Fix 11: Better error messages - indicate glob pattern found no matches
            if self.verbose:
                print(f"[UmiAI] WARNING: Glob pattern '{parsed_tag}' matched no wildcard files.")
            if self.is_failfast_enabled():
                return f"<<ERROR_GLOB_NO_MATCHES:{parsed_tag}>>"
            return f"[GLOB_NO_MATCHES: {parsed_tag}]"

        sequential = False
        if parsed_tag.startswith('~'):
            sequential = True
            parsed_tag = parsed_tag[1:]

        if parsed_tag.startswith('@'):
            filename = parsed_tag[1:].strip()
            file_content = self.tag_loader.load_prompt_file(filename)
            if file_content:
                if self.is_debug_enabled():
                    self.variables['debug_last_type'] = "prompt_file"
                    self.variables['debug_last_source'] = parsed_tag
                    self.variables['debug_last_pick'] = filename
                self.set_trace_info({
                    "trace_last_type": "prompt_file",
                    "trace_last_source": parsed_tag,
                    "trace_last_pick": filename,
                })
                return file_content
            return f"[PROMPT_FILE_NOT_FOUND: {filename}]"

        if not parsed_tag.startswith('#') and '*' not in parsed_tag and '?' not in parsed_tag:
            parsed_tag = self.tag_loader.resolve_wildcard_alias(parsed_tag)

        if '$$' in parsed_tag and not parsed_tag.startswith('#'):
            range_part, file_part = parsed_tag.split('$$', 1)
            if any(c.isdigit() for c in range_part) or '-' in range_part:
                if '*' not in file_part and '?' not in file_part:
                    file_part = self.tag_loader.resolve_wildcard_alias(file_part)
                tags = self.tag_loader.load_tags(file_part, self.verbose)
                if isinstance(tags, list):
                    return process_wildcard_range(parsed_tag, tags, rng)

        if parsed_tag.startswith('#'):
            # Tag-based selection: #tag or #seed$$tag
            if '$$' in parsed_tag:
                # Has seed: #seed$$tag
                tags = self.tag_loader.load_tags(parsed_tag.split('$$')[1], self.verbose)
            else:
                # Just tag: #tag - load all YAML entries for tag filtering
                tag_name = parsed_tag[1:]  # Remove the # prefix
                tags = self.tag_loader.load_tags(ALL_KEY, self.verbose)

                if self.verbose:
                    print(f"[UmiAI] Tag search for '{tag_name}': found {len(tags) if isinstance(tags, dict) else 0} YAML entries")
                    if isinstance(tags, dict):
                        matching = [title for title, entry in tags.items() if tag_name.lower() in [t.lower() for t in entry.get('tags', [])]]
                        print(f"[UmiAI] Entries with tag '{tag_name}': {matching}")

                # Filter by tag and convert to format expected by get_tag_group_choice
                if isinstance(tags, dict):
                    return self.get_tag_group_choice(parsed_tag, [tag_name], tags, rng=rng)
            if isinstance(tags, list):
                return self.get_tag_choice(parsed_tag, tags, rng=rng)

        tags = self.tag_loader.load_tags(parsed_tag, self.verbose)
        
        if sequential and isinstance(tags, list) and tags:
            if self.rng_streams_enabled:
                idx = self.get_scoped_index(scope_override or parsed_tag, len(tags))
            else:
                idx = self.global_seed % len(tags)
            selected = tags[idx]
            if isinstance(selected, dict):
                 vars_out = []
                 for k, v in selected.items():
                     vars_out.append(f"${k.strip()}={v.strip()}")
                 return " ".join(vars_out)
            if '#' in selected:
                selected = selected.split('#')[0].strip()
            selected = self.process_scoped_negative(selected)
            if self.is_debug_enabled():
                self.variables['debug_last_type'] = "wildcard"
                self.variables['debug_last_source'] = parsed_tag
                self.variables['debug_last_pick'] = str(selected)
            self.set_trace_info({
                "trace_last_type": "wildcard",
                "trace_last_source": parsed_tag,
                "trace_last_pick": str(selected),
            })
            return self.resolve_wildcard_recursively(selected, self.global_seed)

        if groups:
            return self.get_tag_group_choice(parsed_tag, groups, tags, rng=rng)
        if tags:
            return self.get_tag_choice(parsed_tag, tags, rng=rng)

        # Fix 11: Better error messages - provide helpful feedback for missing wildcards
        if self.verbose:
            print(f"[UmiAI] WARNING: Wildcard '{parsed_tag}' not found or is empty.")
        if self.is_failfast_enabled():
            return f"<<ERROR_WILDCARD_NOT_FOUND:{parsed_tag}>>"
        return f"[WILDCARD_NOT_FOUND: {parsed_tag}]" 

    def get_prefixes_and_suffixes(self):
        prefixes, suffixes, neg_p, neg_s = [], [], [], []
        for entry in self.selected_entries.values():
            for p in entry.get('prefixes', []):
                if not p:
                    continue
                p_str = str(p)
                if '**' in p_str:
                    neg_p.append(p_str.replace('**', '').strip())
                else:
                    prefixes.append(p_str)
            for s in entry.get('suffixes', []):
                if not s:
                    continue
                s_str = str(s)
                if '**' in s_str:
                    neg_s.append(s_str.replace('**', '').strip())
                else:
                    suffixes.append(s_str)
        return {'prefixes': prefixes, 'suffixes': suffixes, 'neg_prefixes': neg_p, 'neg_suffixes': neg_s}

# ==============================================================================
# VISION & LLM REPLACERS
# ==============================================================================
class VisionReplacer:
    def __init__(self, node_instance, vision_model, refiner_model, vision_temp, refiner_temp, llm_tokens, image_input):
        self.node = node_instance
        self.vision_model = vision_model
        self.refiner_model = refiner_model
        self.vision_temp = vision_temp
        self.refiner_temp = refiner_temp
        self.llm_tokens = llm_tokens
        self.image_input = image_input
        self.regex = re.compile(r'\[VISION(?::\s*(.*?))?\]', re.IGNORECASE)

    def replace(self, prompt):
        def _process_vision_tag(match):
            print("[UmiAI] Found Vision Tag. Processing...")
            
            if self.vision_model == "None":
                return "[VISION_ERROR: No Vision Model Selected]"
            
            # SAFE CHECK: prevents ambiguous tensor error
            if not is_valid_image(self.image_input):
                return "[VISION_ERROR: No Image Connected]"

            custom_instruction = match.group(1)
            if not custom_instruction:
                custom_instruction = ""

            result = self.node.run_llm_naturalizer(
                text="", 
                model_choice=self.vision_model,
                refiner_choice=self.refiner_model,
                vision_temperature=self.vision_temp,
                refiner_temperature=self.refiner_temp,
                max_tokens=self.llm_tokens,
                custom_prompt=custom_instruction,
                image_input=self.image_input
            )
            
            if not result:
                return "[VISION_ERROR: Empty Output from LLM]"
            
            if result.startswith("[Error:") or result.startswith("[VISION_ERROR:"):
                return result
                
            return result

        if self.regex.search(prompt):
            return self.regex.sub(_process_vision_tag, prompt)
        return prompt

class LLMReplacer:
    def __init__(self, node_instance, refiner_model, refiner_temp, llm_tokens, custom_prompt):
        self.node = node_instance
        self.refiner_model = refiner_model
        self.refiner_temp = refiner_temp
        self.llm_tokens = llm_tokens
        # UPDATED DEFAULT PROMPT
        self.custom_prompt = custom_prompt if custom_prompt else "You are an AI image prompt assistant. Rewrite the following into detailed natural language."
        # Matches [LLM: your text here]
        self.regex = re.compile(r'\[LLM:\s*(.*?)\]', re.IGNORECASE | re.DOTALL)

    def replace(self, prompt):
        def _process_llm_tag(match):
            content = match.group(1).strip()
            if not content: 
                return ""
            
            print(f"[UmiAI] Found LLM Tag. Processing: {content[:20]}...")
            
            if self.refiner_model == "None":
                return "[LLM_ERROR: No Refiner Model Selected]"

            # We reuse the existing naturalizer but force it into text-only mode
            result = self.node.run_llm_naturalizer(
                text=content, 
                model_choice="None", # Skip Vision Stage
                refiner_choice=self.refiner_model,
                vision_temperature=0.0,
                refiner_temperature=self.refiner_temp,
                max_tokens=self.llm_tokens,
                custom_prompt=self.custom_prompt,
                image_input=None
            )
            
            if not result:
                return "[LLM_ERROR: Empty Output]"
                
            return result

        if self.regex.search(prompt):
            return self.regex.sub(_process_llm_tag, prompt)
        return prompt

class TagReplacer(TagReplacerBase):
    def __init__(self, tag_selector):
        super().__init__(tag_selector)
        self.wildcard_regex = re.compile(r'(__|<)(.*?)(__|>)')
        self.opts_regexp = re.compile(r'(?<=\[)(.*?)(?=\])')

    def replace_wildcard(self, matches):
        if not matches or len(matches.groups()) != 3:
            return ""
        match = matches.group(2)
        if not match:
            return ""

        # Phase 6: Support @filename to load full prompt file
        if match.startswith('@') and ':' not in match:
            filename = match[1:]
            return self.get_prompt_file_content(filename)

        if ':' in match:
            scope, opts = match.split(':', 1)
            global_opts = self.opts_regexp.findall(opts)
            if global_opts:
                 selected = self.tag_selector.select(scope, global_opts)
            else:
                 selected = self.tag_selector.select(scope)
        else:
            global_opts = self.opts_regexp.findall(match)
            if global_opts:
                selected = self.tag_selector.select(ALL_KEY, global_opts)
            else:
                selected = self.tag_selector.select(match)
        
        if selected is not None:
            if isinstance(selected, str) and '#' in selected:
                selected = selected.split('#')[0].strip()
            return str(selected) 
            
        return matches.group(0)

    def replace(self, prompt):
        # Escape mechanism: Replace \__ and \< with placeholders to preserve literal syntax
        ESCAPED_WILDCARD = "___ESCAPED_WILDCARD___"
        ESCAPED_ANGLE = "___ESCAPED_ANGLE___"

        prompt = prompt.replace(r'\__', ESCAPED_WILDCARD)
        prompt = prompt.replace(r'\<', ESCAPED_ANGLE)

        # Reset cycle detection for new replacement session
        self.replacement_history = []

        p = self.wildcard_regex.sub(self.replace_wildcard, prompt)
        count = 0
        max_iterations = 10

        while p != prompt and count < max_iterations:
            # Cycle detection: check if we've seen this exact prompt before
            if p in self.replacement_history:
                print(f"[UmiAI] WARNING: Cycle detected in wildcard replacement. Breaking loop to prevent infinite recursion.")
                print(f"[UmiAI] Problematic prompt fragment: {p[:100]}...")
                break

            self.replacement_history.append(prompt)
            prompt = p
            p = self.wildcard_regex.sub(self.replace_wildcard, prompt)
            count += 1

        # Warn if we hit the iteration limit
        if count >= max_iterations:
            print(f"[UmiAI] WARNING: Reached maximum wildcard replacement iterations ({max_iterations}). Possible nested wildcards.")

        p = self.replace_functions(p)

        # Restore escaped syntax
        p = p.replace(ESCAPED_WILDCARD, '__')
        p = p.replace(ESCAPED_ANGLE, '<')

        return p

# ==============================================================================
# DANBOORU & LORA
# ==============================================================================

class DanbooruReplacer:
    def __init__(self, options):
        self.cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        self.blacklist = {
            "1girl", "1boy", "solo", "monochrome", "greyscale", "comic", 
            "translated", "commentary_request", "highres", "absurdres", 
            "looking_at_viewer", "smile", "open_mouth", "standing", "simple_background",
            "white_background", "transparent_background"
        }
        self.pattern = re.compile(r"(?:<)?char:([^>,\n]+)(?:>)?")

    def get_character_tags(self, character_name, threshold):
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '', character_name)
        cache_path = os.path.join(self.cache_dir, f"{safe_name}.json")
        
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        url = "https://danbooru.donmai.us/posts.json"
        params = {
            "tags": f"{character_name} solo", 
            "limit": 20,
            "only": "tag_string_character,tag_string_general"
        }
        headers = {"User-Agent": "ComfyUI-UmiAI/1.0"}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code != 200:
                return []
            posts = response.json()
            if not posts:
                return []

        except Exception:
            return []

        tag_counts = Counter()
        total_posts = len(posts)
        
        for post in posts:
            tags = post.get('tag_string_general', '').split() + post.get('tag_string_character', '').split()
            tags = [t for t in tags if t != character_name]
            tag_counts.update(tags)

        consensus_tags = []
        for tag, count in tag_counts.most_common():
            frequency = count / total_posts
            if frequency >= threshold and tag not in self.blacklist:
                clean_tag = tag.replace('_', ' ')
                consensus_tags.append(clean_tag)

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(consensus_tags, f)
        return consensus_tags

    def replace(self, text, threshold, max_tags):
        def _replace_match(match):
            raw_name = match.group(1).strip()
            api_name = raw_name.replace(" ", "_")
            tags = self.get_character_tags(api_name, threshold)
            if not tags:
                return raw_name 
            selected_tags = tags[:max_tags]
            description = ", ".join(selected_tags)
            return f"{raw_name}, {description}"

        return self.pattern.sub(_replace_match, text)

class LoRAHandler:
    def __init__(self):
        self.regex = re.compile(r'<lora:([^>]+)>', re.IGNORECASE)
        self.blacklist = {
            "1girl", "1boy", "solo", "monochrome", "greyscale", "comic", "scenery",
            "translated", "commentary_request", "highres", "absurdres", "masterpiece",
            "best quality", "simple background", "white background", "transparent background"
        }

    def patch_zimage_lora(self, lora):
        new_lora = {}
        qkv_groups = {}
        for k, v in lora.items():
            new_k = k
            if ".attention.to_out.0." in new_k:
                new_k = new_k.replace(".attention.to_out.0.", ".attention.out.")
                new_lora[new_k] = v
                continue

            if ".attention.to_" in new_k:
                parts = new_k.split(".attention.to_")
                base_prefix = parts[0] + ".attention" 
                remainder = parts[1] 
                qkv_type = remainder[0] 
                suffix = remainder[2:] 
                
                if base_prefix not in qkv_groups:
                    qkv_groups[base_prefix] = {'q': {}, 'k': {}, 'v': {}}
                
                qkv_groups[base_prefix][qkv_type][suffix] = v
                continue
            new_lora[new_k] = v

        for base_key, group in qkv_groups.items():
            ak_a = "lora_A.weight"
            if ak_a in group['q'] and ak_a in group['k'] and ak_a in group['v']:
                q_a = group['q'][ak_a]
                k_a = group['k'][ak_a]
                v_a = group['v'][ak_a]
                fused_A = torch.cat([q_a, k_a, v_a], dim=0)
                new_lora[f"{base_key}.qkv.lora_A.weight"] = fused_A

            ak_b = "lora_B.weight"
            if ak_b in group['q'] and ak_b in group['k'] and ak_b in group['v']:
                q_b = group['q'][ak_b]
                k_b = group['k'][ak_b]
                v_b = group['v'][ak_b]
                out_dim, rank = q_b.shape
                fused_B = torch.zeros((out_dim * 3, rank * 3), dtype=q_b.dtype, device=q_b.device)
                fused_B[0:out_dim, 0:rank] = q_b
                fused_B[out_dim:2*out_dim, rank:2*rank] = k_b
                fused_B[2*out_dim:3*out_dim, 2*rank:3*rank] = v_b
                new_lora[f"{base_key}.qkv.lora_B.weight"] = fused_B

            ak_alpha = "lora_alpha"
            if ak_alpha in group['q']:
                new_lora[f"{base_key}.qkv.lora_alpha"] = group['q'][ak_alpha]

        return new_lora

    def get_lora_hash(self, lora_path):
        """Get SHA256 hash of LoRA file for CivitAI lookup"""
        try:
            import hashlib
            sha256 = hashlib.sha256()
            with open(lora_path, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            return sha256.hexdigest().upper()[:10]  # CivitAI uses first 10 chars
        except Exception as e:
            print(f"[Umi LoRA Browser] Error hashing {lora_path}: {e}")
            return None

    def get_lora_tags(self, lora_path, max_tags=10):
        try:
            with safe_open(lora_path, framework="pt", device="cpu") as f:
                metadata = f.metadata()
            if not metadata:
                return None
            if "ss_tag_frequency" in metadata:
                try:
                    freqs = json.loads(metadata["ss_tag_frequency"])
                    merged = Counter()
                    for dir_freq in freqs.values():
                        merged.update(dir_freq)
                    filtered_tags = []
                    for t, c in merged.most_common():
                        clean_t = t.strip()
                        if clean_t in self.blacklist:
                            continue
                        if " " in clean_t and clean_t.replace(" ", "_") in self.blacklist:
                            continue
                        filtered_tags.append(clean_t)
                        if len(filtered_tags) >= max_tags:
                            break
                    return filtered_tags
                except Exception:
                    pass
            return None
        except Exception:
            return None

    def load_lora_cached(self, lora_path, limit):
        # Fix memory leak: skip caching entirely when limit is 0
        if limit == 0:
            return comfy.utils.load_torch_file(lora_path, safe_load=True)

        if lora_path in LORA_MEMORY_CACHE:
            data = LORA_MEMORY_CACHE.pop(lora_path)
            LORA_MEMORY_CACHE[lora_path] = data
            return data

        lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

        LORA_MEMORY_CACHE[lora_path] = lora
        while len(LORA_MEMORY_CACHE) > limit:
            LORA_MEMORY_CACHE.popitem(last=False)

        return lora

    def extract_and_load(self, text, model, clip, behavior, cache_limit, max_tags=5):
        matches = self.regex.findall(text)
        clean_text = self.regex.sub("", text)
        lora_info_output = []
        extracted_tags_str = ""

        if model is None or clip is None:
            return clean_text, model, clip, ""

        for content in matches:
            content = content.strip()

            if ':' in content:
                parts = content.rsplit(':', 1)
                name = parts[0].strip()
                try:
                    strength = float(parts[1].strip())
                    # Input validation: clamp strength to valid range
                    if strength < 0.0 or strength > 5.0:
                        print(f"[UmiAI] WARNING: LoRA strength {strength} for '{name}' is out of range. Clamping to [0.0, 5.0].")
                        strength = max(0.0, min(5.0, strength))
                except ValueError as e:
                    print(f"[UmiAI] ERROR: Invalid LoRA strength '{parts[1].strip()}' for '{name}'. Using 1.0 as default.")
                    name = content
                    strength = 1.0
            else:
                name = content
                strength = 1.0

            name = resolve_lora_alias(name, get_all_wildcard_paths())

            lora_path = folder_paths.get_full_path("loras", name)
            if not lora_path:
                lora_path = folder_paths.get_full_path("loras", f"{name}.safetensors")

            if lora_path:
                tags = self.get_lora_tags(lora_path, max_tags=max_tags)
                info_block = f"[LORA: {name} (Str: {strength})]\n"
                if tags:
                    info_block += f"Common Tags: {', '.join(tags)}"
                else:
                    info_block += "Common Tags: (No Metadata Found)"
                lora_info_output.append(info_block)

                if behavior == "Append to Prompt" and tags:
                     extracted_tags_str += ", " + ", ".join(tags)
                elif behavior == "Prepend to Prompt" and tags:
                     extracted_tags_str = ", ".join(tags) + ", " + extracted_tags_str

                try:
                    lora = self.load_lora_cached(lora_path, cache_limit)
                    
                    is_zimage = any(".attention.to_q." in k for k in lora.keys())
                    if is_zimage:
                        lora = self.patch_zimage_lora(lora)
                    model, clip = comfy.sd.load_lora_for_models(model, clip, lora, strength, strength)
                except Exception as e:
                    print(f"[UmiAI] Failed to load LoRA {name}: {e}")
                    lora_info_output.append(f"Error loading: {e}")
            else:
                 print(f"[UmiAI] LoRA not found: {name}")
                 lora_info_output.append(f"[LORA: {name}] - NOT FOUND")
        
        if behavior == "Append to Prompt":
            clean_text = clean_text + extracted_tags_str
        elif behavior == "Prepend to Prompt":
            clean_text = extracted_tags_str + ", " + clean_text

        return clean_text, model, clip, "\n\n".join(lora_info_output)

class NegativePromptGenerator:
    def __init__(self):
        self.negative_list = []  # Changed from set to list to preserve order
        self.seen_lower = set()  # Track lowercase versions for deduplication

    def strip_negative_tags(self, text):
        matches = re.findall(r'\*\*.*?\*\*', text)
        for match in matches:
            tag = match.replace("**", "").strip()
            tag_lower = tag.lower()
            if tag and tag_lower not in self.seen_lower:
                self.seen_lower.add(tag_lower)
                self.negative_list.append(tag)
            text = text.replace(match, "")
        return text

    def add_list(self, tags):
        for t in tags:
            tag = t.strip()
            tag_lower = tag.lower()
            if tag and tag_lower not in self.seen_lower:
                self.seen_lower.add(tag_lower)
                self.negative_list.append(tag)

    def get_negative_string(self):
        return ", ".join(self.negative_list)

# ==============================================================================
# NODE DEFINITION
# ==============================================================================

class UmiAIWildcardNode:
    def __init__(self):
        self.loaded = False
        self.llm_path = os.path.join(folder_paths.models_dir, "llm")
        if not os.path.exists(self.llm_path):
            os.makedirs(self.llm_path, exist_ok=True)

    @classmethod
    def INPUT_TYPES(s):
        llm_files = folder_paths.get_filename_list("llm") if "llm" in folder_paths.folder_names_and_paths else []
        if not llm_files:
             llm_path = os.path.join(folder_paths.models_dir, "llm")
             if os.path.exists(llm_path):
                 llm_files = [f for f in os.listdir(llm_path) if f.endswith('.gguf')]
        
        download_options = list(DOWNLOADABLE_MODELS.keys())
        llm_options = ["None"] + download_options + llm_files

        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                # Standard Connections
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "image": ("IMAGE",), 

                # Basic Settings
                "lora_tags_behavior": (["Append to Prompt", "Disabled", "Prepend to Prompt"], {"default": "Append to Prompt"}),
                "lora_max_tags": ("INT", {"default": 5, "min": 0, "max": 20, "step": 1}),
                "lora_cache_limit": ("INT", {"default": 5, "min": 0, "max": 50, "step": 1}),
                "use_folder_paths": ("BOOLEAN", {"default": False, "tooltip": "Show folder paths in wildcards: __Series/MyFile__ vs __MyFile__"}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                
                # --- AUTO UPDATER (BUTTON) ---
                "update_llama_cpp": ("BOOLEAN", {"default": True, "label_on": "UPDATE & RESTART", "label_off": "Update Disabled"}),

                # --- VISIBLE LLM SETTINGS ---
                "vision_model": (llm_options, {"default": "None"}),
                "refiner_model": (llm_options, {"default": "None"}),
                
                # SEPARATE TEMPERATURE CONTROLS
                "vision_temperature": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.01}),
                "refiner_temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "max_tokens": ("INT", {"default": 800, "min": 100, "max": 4096}),
                
                "custom_system_prompt": ("STRING", {"multiline": True, "default": "", "placeholder": "Default: You are an AI image prompt assistant. Rewrite the following into detailed natural language."}),
                "input_negative": ("STRING", {"multiline": True, "forceInput": True}),

                # Danbooru Settings
                "danbooru_threshold": ("FLOAT", {"default": 0.70, "min": 0.1, "max": 1.0, "step": 0.05}),
                "danbooru_max_tags": ("INT", {"default": 15, "min": 1, "max": 50}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "INT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "text", "negative_text", "width", "height", "lora_info", "input_text", "input_negative")
    FUNCTION = "process"
    CATEGORY = "UmiAI"
    COLOR = "#322947"
    
    @classmethod
    def IS_CHANGED(cls, text, seed, **kwargs):
        return f"{seed}_{text}"

    def extract_settings(self, text):
        settings_regex = re.compile(r'@@(.*?)@@')
        matches = settings_regex.findall(text)
        settings = {'width': -1, 'height': -1}
        for match in matches:
            text = text.replace(f"@@{match}@@", "")
            pairs = match.split(',')
            for pair in pairs:
                if '=' in pair:
                    key, val = pair.split('=', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    try:
                        if key == 'width': settings['width'] = int(val)
                        if key == 'height': settings['height'] = int(val)
                    except ValueError: pass
        return text, settings

    def ensure_model_exists(self, model_choice):
        if model_choice == "None":
            return None, None
        
        target_folder = os.path.join(folder_paths.models_dir, "llm")
        if not os.path.exists(target_folder):
            os.makedirs(target_folder, exist_ok=True)

        # 1. Download Mode
        if model_choice in DOWNLOADABLE_MODELS:
            if not HF_HUB_AVAILABLE:
                return None, None
            
            model_info = DOWNLOADABLE_MODELS[model_choice]
            repo_id = model_info["repo_id"]
            filename = model_info["filename"]
            
            # Download Main Model
            local_file_path = os.path.join(target_folder, filename)
            if not os.path.exists(local_file_path):
                try:
                    print(f"[UmiAI] Downloading {filename}...")
                    local_file_path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=target_folder, local_dir_use_symlinks=False)
                except Exception as e:
                    print(f"[UmiAI] Download failed: {e}")
                    return None, None

            # Download Projector/Adapter (Vision) if required
            mmproj_path = None
            if "mmproj" in model_info:
                mmproj_file = model_info["mmproj"]
                mmproj_local = os.path.join(target_folder, mmproj_file)
                if os.path.exists(mmproj_local):
                    mmproj_path = mmproj_local
                else:
                    try:
                        print(f"[UmiAI] Downloading Vision Adapter {mmproj_file}...")
                        mmproj_path = hf_hub_download(repo_id=repo_id, filename=mmproj_file, local_dir=target_folder, local_dir_use_symlinks=False)
                    except Exception:
                        pass
            
            return local_file_path, mmproj_path
        
        # 2. Local File Mode (Auto-Detect Adapter)
        else:
            # Check for exact path
            path = folder_paths.get_full_path("llm", model_choice)
            if not path:
                # Fallback: check simply inside models/llm/
                potential = os.path.join(target_folder, model_choice)
                if os.path.exists(potential):
                    path = potential
            
            if not path:
                return None, None
            
            # --- AGGRESSIVE ADAPTER SEARCH ---
            mmproj_path = None
            
            # Strategy A: Check exact name pairs
            base = os.path.splitext(path)[0]
            candidates = [
                base + "-mmproj.gguf", 
                base + ".mmproj.gguf", 
                base + "-vision.gguf",
                base.replace("Q4_K_M", "mmproj-f16"),
                base.replace("Q6_K", "mmproj-f16"),
                base.replace("Q4_K", "mmproj-Q4_0"), # Common for Llava
            ]
            for c in candidates:
                if os.path.exists(c):
                    mmproj_path = c
                    break
            
            # Strategy B: Scan folder for ANY 'mmproj' file
            # If not found, scan directory for matching mmproj
            if not mmproj_path:
                folder = os.path.dirname(path)
                # Filter for JoyCaption specific or generic
                is_joy = "joycaption" in model_choice.lower()
                is_llava = "llava" in model_choice.lower()
                
                for f in os.listdir(folder):
                    if "mmproj" in f.lower() and f.endswith(".gguf"):
                        if is_joy and "joycaption" in f.lower():
                            mmproj_path = os.path.join(folder, f)
                            break
                        if is_llava and "llava" in f.lower():
                             mmproj_path = os.path.join(folder, f)
                             break

            return path, mmproj_path

    def run_llm_naturalizer(self, text, model_choice, refiner_choice, vision_temperature, refiner_temperature, max_tokens, custom_prompt, image_input=None):
        if not LLAMA_CPP_AVAILABLE:
            return "[Error: llama_cpp_python not installed]"
        
        # --- STAGE 1: VISION (Only if Image Input is present) ---
        raw_vision_output = ""
        
        if is_valid_image(image_input) and model_choice != "None":
            # GC
            gc.collect()
            torch.cuda.empty_cache()

            model_path, mmproj_path = self.ensure_model_exists(model_choice)
            if not model_path:
                return f"[Error: Model '{model_choice}' not found]"

            # Hallucination Guard
            if is_valid_image(image_input) and not mmproj_path:
                return "[VISION_ERROR: Model Loaded but Vision Adapter (.mmproj) Not Found.]"

            print(f"[UmiAI] Vision Adapter Loaded: {mmproj_path}")

            llm = None
            try:
                chat_handler = None
                if mmproj_path:
                    # USE CUSTOM HANDLER FOR JOYCAPTION (LLAMA 3)
                    if "joycaption" in str(model_choice).lower():
                        chat_handler = JoyCaptionChatHandler(clip_model_path=mmproj_path)
                    else:
                        chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
                
                # Initialize Llama 
                llm = Llama(
                    model_path=model_path, 
                    chat_handler=chat_handler,
                    n_ctx=4096, 
                    n_gpu_layers=-1, 
                    verbose=True 
                )
                
                messages = []
                user_content = []
                
                # Convert Tensor (Batch, H, W, C) -> PIL -> Base64
                i = 255. * image_input[0].cpu().numpy()
                img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
                
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}
                })
                
                # GENERIC PROMPT FOR VISION (Just get the data)
                user_content.append({"type": "text", "text": "Describe this image in extreme detail."})
                messages.append({"role": "user", "content": user_content})

                output = llm.create_chat_completion(
                    messages=messages,
                    temperature=vision_temperature, 
                    max_tokens=max_tokens
                )
                
                raw_vision_output = output['choices'][0]['message']['content'].strip()
                
                if len(raw_vision_output) > 20 and raw_vision_output[:10] == "1: 1: 1: 1":
                    return "[VISION_ERROR: Projector Mismatch. Please use Auto-Update to install compatible llama-cpp-python.]"
                    
            except Exception as e:
                print(f"[UmiAI] LLM/Vision Error: {e}")
                return f"[Error: {str(e)}]"
            
            finally:
                if llm:
                    del llm
                gc.collect()
                torch.cuda.empty_cache()

        # --- STAGE 2: REFINEMENT (Only if Refiner Model is selected) ---
        if refiner_choice != "None":
            # IMPORTANT: If Vision Failed (raw_vision_output is empty), we must abort.
            if not raw_vision_output and not text:
                 return "[VISION_ERROR: Vision Model failed to generate text. Check console for details.]"
            
            # If no vision output but we have text (Global Override Mode), use text
            if not raw_vision_output:
                 raw_vision_output = text

            # GC Again before loading second model
            gc.collect()
            torch.cuda.empty_cache()
            
            refiner_path, _ = self.ensure_model_exists(refiner_choice)
            if not refiner_path:
                return raw_vision_output # Fallback to raw output if refiner fails

            print(f"[UmiAI] Loading Refiner: {refiner_path}")
            
            refiner_llm = None
            try:
                # Initialize Text-Only Model
                refiner_llm = Llama(
                    model_path=refiner_path, 
                    n_ctx=4096, 
                    n_gpu_layers=-1, 
                    verbose=True 
                )
                
                instruction = custom_prompt if custom_prompt else "You are an AI image prompt assistant. Rewrite the following into detailed natural language."
                
                # =========================================================================
                # 3. MANUAL PROMPT CONSTRUCTION FOR DOLPHIN/LLAMA 3 (NUCLEAR OPTION)
                #    We detect if it's Dolphin/Llama and use raw completion instead of chat.
                #    This is the only 100% reliable way to stop the "Parroting" loop.
                # =========================================================================
                
                is_dolphin_or_llama = "dolphin" in refiner_choice.lower() or "llama" in refiner_choice.lower() or "imp" in refiner_choice.lower()
                
                if is_dolphin_or_llama:
                    print("[UmiAI] Detected Dolphin/Llama-3 model. Using Manual Prompt Construction.")
                    
                    # Manually constructed Llama-3 prompt string
                    prompt_string = (
                        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                        f"{instruction}<|eot_id|>"
                        "<|start_header_id|>user<|end_header_id|>\n\n"
                        f"{raw_vision_output}<|eot_id|>"
                        "<|start_header_id|>assistant<|end_header_id|>\n\n"
                    )
                    
                    # Use create_completion (Raw) instead of chat completion
                    output = refiner_llm.create_completion(
                        prompt=prompt_string,
                        temperature=refiner_temperature,
                        max_tokens=max_tokens,
                        stop=["<|eot_id|>", "<|end_of_text|>", "</s>"]
                    )
                    return output['choices'][0]['text'].strip()

                else:
                    # FALLBACK FOR QWEN / OTHER MODELS (Chat Completion works fine usually)
                    messages = [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": raw_vision_output}
                    ]
                    
                    output = refiner_llm.create_chat_completion(
                        messages=messages,
                        temperature=refiner_temperature,
                        max_tokens=max_tokens
                    )
                    return output['choices'][0]['message']['content'].strip()

            except Exception as e:
                print(f"[UmiAI] Refiner Error: {e}")
                return raw_vision_output # Fallback
            
            finally:
                if refiner_llm:
                    del refiner_llm
                gc.collect()
                torch.cuda.empty_cache()

        # If no refiner, return raw vision output
        return raw_vision_output

    # --- SAFETY HELPER ---
    def get_val(self, kwargs, key, default, value_type=None):
        val = kwargs.get(key, default)
        
        if val is None:
            return default

        if value_type:
            try:
                if value_type == int:
                    return int(float(val)) 
                if value_type == float:
                    return float(val)
                if value_type == str:
                    if isinstance(val, (int, float)):
                        return str(val) 
                    return str(val)
            except:
                return default
        
        return val

    def process(self, **kwargs):
        # 1. AUTO-UPDATE CHECK (BUTTON LOGIC)
        do_update = kwargs.get("update_llama_cpp", False)
        if do_update:
            success = perform_library_update()
            if success:
                raise Exception("Auto-Update Complete! Please Restart ComfyUI now.")
            else:
                raise Exception("Auto-Update Failed! Check console for errors.")

        import numpy as np 

        text = self.get_val(kwargs, "text", "", str)
        seed = self.get_val(kwargs, "seed", 0, int)
        
        model = kwargs.get("model", None)
        clip = kwargs.get("clip", None)
        image_input = kwargs.get("image", None)

        width = self.get_val(kwargs, "width", 1024, int)
        height = self.get_val(kwargs, "height", 1024, int)
        lora_tags_behavior = self.get_val(kwargs, "lora_tags_behavior", "Append to Prompt", str)
        lora_max_tags = self.get_val(kwargs, "lora_max_tags", 5, int)
        lora_cache_limit = self.get_val(kwargs, "lora_cache_limit", 5, int)
        use_folder_paths = kwargs.get("use_folder_paths", False)
        input_negative = self.get_val(kwargs, "input_negative", "", str)

        # RENAMED INPUTS
        vision_model = self.get_val(kwargs, "vision_model", "None", str)
        refiner_model = self.get_val(kwargs, "refiner_model", "None", str)

        vision_temperature = self.get_val(kwargs, "vision_temperature", 0.2, float)
        refiner_temperature = self.get_val(kwargs, "refiner_temperature", 0.7, float)
        max_tokens = self.get_val(kwargs, "max_tokens", 400, int)
        custom_system_prompt = self.get_val(kwargs, "custom_system_prompt", "", str)

        danbooru_threshold = self.get_val(kwargs, "danbooru_threshold", 0.70, float)
        danbooru_max_tags = self.get_val(kwargs, "danbooru_max_tags", 15, int)

        # ============================================================
        # CORE PROCESSING
        # ============================================================
        
        protected_text = text.replace('__#', '___UMI_HASH_PROTECT___').replace('<#', '<___UMI_HASH_PROTECT___')
        clean_lines = []
        for line in protected_text.splitlines():
            if '//' in line:
                line = line.split('//')[0]
            if '#' in line and not line.strip().startswith("#"):
                 if ' #' in line:
                    line = line.split(' #')[0]
            
            line = line.strip()
            if line:
                clean_lines.append(line)
        
        text = "\n".join(clean_lines)
        text = text.replace('___UMI_HASH_PROTECT___', '#').replace('<___UMI_HASH_PROTECT___', '<#')

        options = {
            'verbose': False, 
            'seed': seed,
            'use_folder_paths': use_folder_paths,
            'rng_streams': UMI_SETTINGS.get('rng_streams', False),
        }
        
        # Sync node toggle to global settings so autocomplete uses same setting
        if UMI_SETTINGS.get('use_folder_paths', False) != use_folder_paths:
            UMI_SETTINGS['use_folder_paths'] = use_folder_paths
            print(f"[UmiAI] Updated global use_folder_paths to: {use_folder_paths}")

        all_wildcard_paths = get_all_wildcard_paths()
        tag_loader = TagLoader(all_wildcard_paths, options)
        
        tag_selector = TagSelector(tag_loader, options)
        neg_gen = NegativePromptGenerator()
        
        tag_replacer = TagReplacer(tag_selector)
        dynamic_replacer = DynamicPromptReplacer(seed)
        conditional_replacer = ConditionalReplacer()
        variable_replacer = VariableReplacer()
        danbooru_replacer = DanbooruReplacer(options)
        lora_handler = LoRAHandler()
        
        # Initialize VisionReplacer
        vision_replacer = VisionReplacer(self, vision_model, refiner_model, vision_temperature, refiner_temperature, max_tokens, image_input)
        
        # Initialize LLMReplacer
        llm_replacer = LLMReplacer(self, refiner_model, refiner_temperature, max_tokens, custom_system_prompt)

        globals_dict = tag_loader.load_globals()
        variable_replacer.load_globals(globals_dict)

        prompt = text
        previous_prompt = ""
        iterations = 0
        prompt_history = []  # Track prompts for cycle detection
        tag_selector.clear_seeded_values()

        while previous_prompt != prompt and iterations < 50:
            # Cycle detection: check if we've seen this exact prompt before
            if prompt in prompt_history:
                print(f"[UmiAI] WARNING: Cycle detected in prompt processing. Breaking loop to prevent infinite recursion.")
                print(f"[UmiAI] Problematic prompt fragment: {prompt[:100]}...")
                break

            prompt_history.append(prompt)
            previous_prompt = prompt

            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)

            masked_prompt, if_blocks = conditional_replacer.mask_conditionals(prompt)

            # Process Vision and LLM tags (skip conditional blocks)
            masked_prompt = vision_replacer.replace(masked_prompt)
            masked_prompt = llm_replacer.replace(masked_prompt)

            masked_prompt = tag_replacer.replace(masked_prompt)
            masked_prompt = dynamic_replacer.replace(masked_prompt)
            masked_prompt = danbooru_replacer.replace(masked_prompt, danbooru_threshold, danbooru_max_tags)

            prompt = conditional_replacer.unmask_conditionals(masked_prompt, if_blocks)
            prompt = conditional_replacer.replace(prompt, variable_replacer.variables)

            # Capture assignments revealed by conditionals in the same iteration
            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)

            iterations += 1

        # Warn if we hit the iteration limit
        if iterations >= 50:
            print(f"[UmiAI] WARNING: Reached maximum processing iterations (50). Possible recursive wildcards or variables.")


        
        additions = tag_selector.get_prefixes_and_suffixes()
        if additions['prefixes']:
            prompt = ", ".join(additions['prefixes']) + ", " + prompt
        if additions['suffixes']:
            prompt = prompt + ", " + ", ".join(additions['suffixes'])

        if additions['neg_prefixes']:
            neg_gen.add_list(additions['neg_prefixes'])
        if additions['neg_suffixes']:
            neg_gen.add_list(additions['neg_suffixes'])
        if tag_selector.scoped_negatives:
            neg_gen.add_list(tag_selector.scoped_negatives)

        prompt = neg_gen.strip_negative_tags(prompt)
        prompt = re.sub(r',\s*,', ',', prompt)
        prompt = re.sub(r'\s+', ' ', prompt).strip().strip(',')

        if tag_selector.is_trace_enabled():
            prompt = append_trace_summary(prompt, variable_replacer.variables)
        if tag_selector.is_debug_enabled():
            prompt = append_debug_summary(prompt, variable_replacer.variables)

        prompt, final_model, final_clip, lora_info = lora_handler.extract_and_load(prompt, model, clip, lora_tags_behavior, lora_cache_limit, lora_max_tags)

        generated_negatives = neg_gen.get_negative_string()
        final_negative = input_negative
        if generated_negatives:
            final_negative = f"{final_negative}, {generated_negatives}" if final_negative else generated_negatives
        if final_negative:
            final_negative = re.sub(r',\s*,', ',', final_negative).strip()

        prompt, settings = self.extract_settings(prompt)
        final_width = settings['width'] if settings['width'] > 0 else width
        final_height = settings['height'] if settings['height'] > 0 else height

        # Phase 8: Log prompt to history
        log_prompt_to_history(prompt, final_negative, seed)

        return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info, text, input_negative)

# ==============================================================================
# UMI SAVE IMAGE NODE (with embedded metadata)
# ==============================================================================
class UmiSaveImage:
    """Save images with Umi prompt metadata embedded for the Image Browser"""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "Umi"}),
            },
            "optional": {
                "positive_prompt": ("STRING", {"forceInput": True, "multiline": True}),
                "negative_prompt": ("STRING", {"forceInput": True, "multiline": True}),
                "input_prompt": ("STRING", {"forceInput": True, "multiline": True}),  # Original input before wildcards
                "input_negative": ("STRING", {"forceInput": True, "multiline": True}),  # Original negative before wildcards
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "UmiAI"

    def save_images(self, images, filename_prefix="Umi", positive_prompt="", negative_prompt="", input_prompt="", input_negative="", prompt=None, extra_pnginfo=None):
        from PIL import Image, PngImagePlugin
        import numpy as np

        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )

        results = list()

        for (batch_number, image) in enumerate(images):
            # Convert tensor to PIL Image
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            # Prepare PNG metadata
            metadata = PngImagePlugin.PngInfo()

            # Add Umi-specific metadata (processed prompts)
            if positive_prompt:
                metadata.add_text("umi_prompt", positive_prompt)
                print(f"[UmiSaveImage] Saved umi_prompt: {positive_prompt[:100]}...")
            if negative_prompt:
                metadata.add_text("umi_negative", negative_prompt)
                print(f"[UmiSaveImage] Saved umi_negative: {negative_prompt[:100]}...")

            # Add original input prompts (before wildcard processing)
            if input_prompt:
                metadata.add_text("umi_input_prompt", input_prompt)
                print(f"[UmiSaveImage] Saved umi_input_prompt: {input_prompt[:100]}...")
            if input_negative:
                metadata.add_text("umi_input_negative", input_negative)
                print(f"[UmiSaveImage] Saved umi_input_negative: {input_negative[:100]}...")

            # Add standard ComfyUI workflow metadata if available
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for key, value in extra_pnginfo.items():
                    metadata.add_text(key, json.dumps(value))

            # Generate filename
            file = f"{filename}_{counter:05}_.png"
            img.save(
                os.path.join(full_output_folder, file),
                pnginfo=metadata,
                compress_level=self.compress_level
            )

            results.append({
                "filename": file,
                "subfolder": subfolder,
                "type": self.type
            })

            counter += 1

        return { "ui": { "images": results } }


# ==============================================================================
# UMI POSE GENERATOR (Ported from VNCCS)
# ==============================================================================

class UmiPoseGenerator:
    """Pose Generator for creating OpenPose images from JSON pose data.
    
    Creates a 6x2 grid of 12 poses in OpenPose format for ControlNet.
    Compatible with VNCCS 3D pose editor.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        # Import pose utilities
        try:
            from .pose_utils.skeleton_512x1536 import DEFAULT_SKELETON, CANVAS_WIDTH, CANVAS_HEIGHT
            default_skeleton = DEFAULT_SKELETON
            canvas_w = CANVAS_WIDTH
            canvas_h = CANVAS_HEIGHT
        except ImportError:
            default_skeleton = {}
            canvas_w = 512
            canvas_h = 1536
        
        # Create default 12 poses JSON
        default_pose_list = []
        for _ in range(12):
            default_pose_list.append({
                "joints": {name: list(pos) for name, pos in default_skeleton.items()}
            })
        default_pose_json = json.dumps({
            "canvas": {"width": canvas_w, "height": canvas_h},
            "poses": default_pose_list
        }, indent=2)
            
        return {
            "required": {
                "pose_data": ("STRING", {
                    "default": default_pose_json,
                    "multiline": True,
                    "dynamicPrompts": False
                }),
                "line_thickness": ("INT", {
                    "default": 3,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "display": "slider"
                }),
                "safe_zone": ("INT", {
                    "default": 100,
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "display": "slider",
                    "tooltip": "Scale poses toward center (100 = no scaling)"
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("openpose_grid",)
    FUNCTION = "generate"
    CATEGORY = "UmiAI/pose"
    
    def generate(self, pose_data: str, line_thickness: int = 3, safe_zone: int = 100):
        """Generate OpenPose image grid from pose data."""
        import torch
        import numpy as np
        
        try:
            from .pose_utils.skeleton_512x1536 import (
                DEFAULT_SKELETON, CANVAS_WIDTH, CANVAS_HEIGHT, LEGACY_JOINT_ALIASES
            )
            from .pose_utils.pose_renderer import render_openpose, convert_to_comfyui_format
        except ImportError as e:
            print(f"[UmiAI Pose] Error importing pose utilities: {e}")
            # Return black image if imports fail
            black_img = np.zeros((1536*2, 512*6, 3), dtype=np.float32)
            return (torch.from_numpy(black_img).unsqueeze(0),)
        
        print(f"[UmiAI Pose] Generating pose grid (safe_zone: {safe_zone}%)...")
        
        try:
            data = json.loads(pose_data)
        except json.JSONDecodeError as exc:
            print(f"[UmiAI Pose] ERROR: Invalid JSON: {exc}")
            data = {}
        
        # Extract poses list
        poses_data = data.get("poses", [])
        if not isinstance(poses_data, list):
            joints_payload = data.get("joints", {})
            if joints_payload:
                poses_data = [{"joints": joints_payload}]
            else:
                poses_data = []
        
        def _clamp(val, min_val, max_val):
            return max(min_val, min(max_val, val))
        
        def _sanitize_joints(joints_data):
            sanitized = {}
            for raw_name, coords in joints_data.items():
                joint_name = LEGACY_JOINT_ALIASES.get(raw_name, raw_name)
                if joint_name not in DEFAULT_SKELETON:
                    continue
                if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                    continue
                try:
                    x = float(coords[0])
                    y = float(coords[1])
                except (TypeError, ValueError):
                    continue
                x_int = _clamp(int(round(x)), 0, CANVAS_WIDTH - 1)
                y_int = _clamp(int(round(y)), 0, CANVAS_HEIGHT - 1)
                sanitized[joint_name] = (x_int, y_int)
            for joint_name, default_coords in DEFAULT_SKELETON.items():
                sanitized.setdefault(joint_name, default_coords)
            return sanitized
        
        # Ensure we have exactly 12 poses
        poses = []
        for i in range(12):
            if i < len(poses_data) and isinstance(poses_data[i], dict):
                if "joints" in poses_data[i]:
                    joints_payload = poses_data[i]["joints"]
                else:
                    joints_payload = poses_data[i]
                poses.append(_sanitize_joints(joints_payload))
            else:
                poses.append(DEFAULT_SKELETON.copy())
        
        # Apply safe zone scaling
        if safe_zone < 100:
            scale_factor = safe_zone / 100.0
            center_x = CANVAS_WIDTH / 2.0
            center_y = CANVAS_HEIGHT / 2.0
            
            scaled_poses = []
            for pose in poses:
                scaled_pose = {}
                for joint_name, coords in pose.items():
                    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                        x, y = coords[0], coords[1]
                        scaled_x = center_x + (x - center_x) * scale_factor
                        scaled_y = center_y + (y - center_y) * scale_factor
                        scaled_x = _clamp(int(round(scaled_x)), 0, CANVAS_WIDTH - 1)
                        scaled_y = _clamp(int(round(scaled_y)), 0, CANVAS_HEIGHT - 1)
                        scaled_pose[joint_name] = (scaled_x, scaled_y)
                    else:
                        scaled_pose[joint_name] = coords
                scaled_poses.append(scaled_pose)
            poses = scaled_poses
        
        # Grid dimensions (6 columns, 2 rows)
        w, h = CANVAS_WIDTH, CANVAS_HEIGHT
        cols, rows = 6, 2
        grid_w, grid_h = w * cols, h * rows
        
        # Create empty grid
        openpose_grid = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
        
        for idx, joints in enumerate(poses):
            row = idx // cols
            col = idx % cols
            x_offset = col * w
            y_offset = row * h
            
            openpose_img = render_openpose(joints, w, h, line_thickness)
            openpose_grid[y_offset:y_offset+h, x_offset:x_offset+w] = openpose_img
        
        # Convert to ComfyUI format
        openpose_tensor = convert_to_comfyui_format(openpose_grid)
        openpose_tensor = torch.from_numpy(openpose_tensor)
        
        print(f"[UmiAI Pose] Generated grid: {openpose_tensor.shape}")
        
        return (openpose_tensor,)


# ==============================================================================
# UMI EMOTION GENERATOR (Ported from VNCCS)
# ==============================================================================

class UmiEmotionGenerator:
    """Generate emotion prompts from character YAML data.
    
    Reads the Emotions field from character profile and outputs prompts
    for each selected emotion.
    """
    
    # Common emotion list (VNCCS compatible)
    EMOTION_LIST = [
        "neutral", "happy", "sad", "angry", "surprised", "embarrassed",
        "blushing", "crying", "laughing", "scared", "confused", "disgusted",
        "sleepy", "excited", "nervous", "determined", "smug", "shy"
    ]
    
    @classmethod
    def INPUT_TYPES(cls):
        from .shared_utils import CharacterReplacer
        characters = CharacterReplacer.list_characters()
        
        return {
            "required": {
                "character": (characters if characters else ["None"], {}),
                "emotions": ("STRING", {
                    "default": "neutral,happy,sad,angry,surprised",
                    "multiline": True,
                    "tooltip": "Comma-separated list of emotions"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("emotion_prompts", "emotion_names")
    OUTPUT_IS_LIST = (True, True)
    FUNCTION = "generate"
    CATEGORY = "UmiAI/character"
    
    def generate(self, character, emotions):
        from .shared_utils import CharacterReplacer
        
        emotion_list = [e.strip() for e in emotions.split(",") if e.strip()]
        
        prompts = []
        names = []
        
        for emotion in emotion_list:
            prompt = CharacterReplacer.get_emotion(character, emotion)
            if prompt:
                prompts.append(prompt)
                names.append(emotion)
            else:
                # Fallback: use emotion name directly as prompt
                prompts.append(f"({emotion})")
                names.append(emotion)
        
        print(f"[UmiAI Emotion] Generated {len(prompts)} emotion prompts for '{character}'")
        
        return (prompts, names)


# ==============================================================================
# UMI CHARACTER CREATOR (Enhanced VNCCS-style)
# ==============================================================================

# VNCCS-style helper functions
def umi_age_strength(age):
    """Calculate LoRA strength based on age (VNCCS method)."""
    if age < 10:
        return 1.0
    elif age < 18:
        return 0.7
    elif age < 30:
        return 0.3
    elif age < 50:
        return 0.5
    else:
        return 0.8

def umi_ensure_character_structure(char_path, emotions=None, main_dirs=None):
    """Create VNCCS-compatible folder structure for a character."""
    import os
    
    if emotions is None:
        emotions = ["neutral", "happy", "sad", "angry", "surprised", "embarrassed", 
                   "scared", "disgusted", "love", "thinking"]
    
    if main_dirs is None:
        main_dirs = ["Sheets", "Faces", "References"]
    
    # Create main directories
    for dir_name in main_dirs:
        os.makedirs(os.path.join(char_path, dir_name), exist_ok=True)
    
    # Create emotion subdirs in Sheets and Faces
    for main_dir in ["Sheets", "Faces"]:
        for emotion in emotions:
            os.makedirs(os.path.join(char_path, main_dir, "Naked", emotion), exist_ok=True)
    
    return True

def umi_build_face_details(info):
    """Build face details string from character info (VNCCS method)."""
    parts = []
    if info.get("eyes"):
        parts.append(f"({info['eyes']}:1.0)")
    if info.get("hair"):
        parts.append(f"({info['hair']}:1.0)")
    if info.get("face"):
        parts.append(f"({info['face']}:1.0)")
    return ", ".join(parts)

def _resolve_umi_asset_path(*parts):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    util_path = os.path.join(base_dir, "umi_utilities", *parts)
    if os.path.exists(util_path):
        return util_path
    return os.path.join(base_dir, *parts)


class UmiCharacterCreator:
    """Create or update character profiles with VNCCS-compatible structure.
    
    Generates folder structure, config, and outputs for downstream nodes.
    """
    
    EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised", "embarrassed", 
                "scared", "disgusted", "love", "thinking"]
    MAIN_DIRS = ["Sheets", "Faces", "References"]
    
    @classmethod
    def INPUT_TYPES(cls):
        from .shared_utils import CharacterReplacer
        characters = CharacterReplacer.list_characters()
        char_list = characters if characters else ["None"]
        
        return {
            "required": {
                "existing_character": (char_list, {"default": char_list[0]}),
            },
            "optional": {
                "new_character_name": ("STRING", {"default": ""}),
                "background_color": ("STRING", {"default": "green"}),
                "aesthetics": ("STRING", {"default": "masterpiece, best quality", "multiline": True}),
                "sex": (["female", "male"], {"default": "female"}),
                "age": ("INT", {"default": 18, "min": 0, "max": 120}),
                "race": ("STRING", {"default": "human"}),
                "eyes": ("STRING", {"default": "blue eyes"}),
                "hair": ("STRING", {"default": "long black hair"}),
                "face": ("STRING", {"default": "beautiful face"}),
                "body": ("STRING", {"default": "slender"}),
                "skin_color": ("STRING", {"default": "fair skin"}),
                "additional_details": ("STRING", {"default": "", "multiline": True}),
                "negative_prompt": ("STRING", {"default": "bad quality, worst quality", "multiline": True}),
                "lora_prompt": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "STRING", "FLOAT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "seed", "negative_prompt", "age_lora_strength", 
                    "sheets_path", "faces_path", "face_details")
    FUNCTION = "create"
    CATEGORY = "UmiAI/character"
    
    def create(self, existing_character, new_character_name="", background_color="green",
               aesthetics="masterpiece, best quality", sex="female", age=18, race="human",
               eyes="blue eyes", hair="long black hair", face="beautiful face", 
               body="slender", skin_color="fair skin", additional_details="",
               negative_prompt="bad quality, worst quality", lora_prompt="", seed=0):
        import os
        import json
        
        # Determine character name
        character_name = new_character_name.strip() if new_character_name.strip() else existing_character
        if character_name == "None":
            character_name = "NewCharacter"
        
        # Setup paths
        char_root = _resolve_umi_asset_path("characters")
        char_path = os.path.join(char_root, character_name)
        sheets_path = os.path.join(char_path, "Sheets")
        faces_path = os.path.join(char_path, "Faces")
        config_path = os.path.join(char_path, "config.json")
        
        # Create VNCCS-compatible folder structure
        umi_ensure_character_structure(char_path, self.EMOTIONS, self.MAIN_DIRS)
        
        # Build positive prompt
        prompt_parts = [aesthetics, "simple background, expressionless"]
        
        if background_color:
            prompt_parts.append(f"{background_color} background")
        
        # Apply sex
        if sex == "female":
            prompt_parts.append("1girl")
        else:
            prompt_parts.append("1boy")
        
        # Age handling
        if age < 10:
            prompt_parts.append("child")
        elif age < 18:
            prompt_parts.append("teenager")
        elif age > 60:
            prompt_parts.append("elderly")
        
        # Add appearance details
        if race:
            prompt_parts.append(f"({race} race:1.0)")
        if hair:
            prompt_parts.append(f"({hair} hair:1.0)")
        if eyes:
            prompt_parts.append(f"({eyes} eyes:1.0)")
        if face:
            prompt_parts.append(f"({face} face:1.0)")
        if body:
            prompt_parts.append(f"({body} body:1.0)")
        if skin_color:
            prompt_parts.append(f"({skin_color} skin:1.0)")
        if additional_details:
            prompt_parts.append(f"({additional_details})")
        if lora_prompt:
            prompt_parts.append(lora_prompt)
        
        positive_prompt = ", ".join(prompt_parts)
        
        # Calculate age LoRA strength
        age_lora_strength = umi_age_strength(age)
        
        # Build face details for downstream nodes
        info = {"eyes": eyes, "hair": hair, "face": face}
        face_details = umi_build_face_details(info) + ", (expressionless:1.0)"
        
        # Load or create config
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass
        
        # Update config
        config["character_info"] = {
            "name": character_name,
            "background_color": background_color,
            "sex": sex,
            "age": age,
            "race": race,
            "aesthetics": aesthetics,
            "eyes": eyes,
            "hair": hair,
            "face": face,
            "body": body,
            "skin_color": skin_color,
            "additional_details": additional_details,
            "negative_prompt": negative_prompt,
            "lora_prompt": lora_prompt,
            "seed": seed
        }
        
        config["folder_structure"] = {
            "main_directories": self.MAIN_DIRS,
            "emotions": self.EMOTIONS
        }
        
        config["character_path"] = char_path
        config["config_version"] = "2.0"
        
        # Preserve existing costumes
        if "costumes" not in config:
            config["costumes"] = {"Naked": {"description": "Base nude/underwear"}}
        
        # Save config
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"[UmiAI Character] Created/updated '{character_name}'")
        print(f"  Sheets: {sheets_path}")
        print(f"  Faces: {faces_path}")
        print(f"  Age LoRA: {age_lora_strength}")
        
        return (positive_prompt, seed, negative_prompt, age_lora_strength, 
                sheets_path, faces_path, face_details)


# ==============================================================================
# UMI SPRITE GENERATOR (Ported from VNCCS)
# ==============================================================================

class UmiSpriteGenerator:
    """Collect character sprites from the character folder structure.
    
    Scans character's Sheets folder for all costume/emotion combinations.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        from .shared_utils import CharacterReplacer
        characters = CharacterReplacer.list_characters()
        
        return {
            "required": {
                "character": (characters if characters else ["None"], {}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("sprite_paths", "sprite_info")
    OUTPUT_IS_LIST = (True, True)
    FUNCTION = "generate"
    CATEGORY = "UmiAI/character"
    
    def generate(self, character):
        import os
        from .shared_utils import CharacterReplacer
        
        chars_path = CharacterReplacer.get_characters_path()
        if not chars_path:
            return ([], [])
        
        char_path = os.path.join(chars_path, character)
        sheets_dir = os.path.join(char_path, "Sheets")
        
        if not os.path.exists(sheets_dir):
            print(f"[UmiAI Sprite] Sheets folder not found: {sheets_dir}")
            return ([], [])
        
        sprite_paths = []
        sprite_info = []
        
        # Scan costumes
        costumes = [d for d in os.listdir(sheets_dir) 
                   if os.path.isdir(os.path.join(sheets_dir, d))]
        
        for costume in costumes:
            costume_dir = os.path.join(sheets_dir, costume)
            
            # Scan emotions within costume
            emotions = [d for d in os.listdir(costume_dir) 
                       if os.path.isdir(os.path.join(costume_dir, d))]
            
            for emotion in emotions:
                emotion_dir = os.path.join(costume_dir, emotion)
                
                # Find image files
                for f in os.listdir(emotion_dir):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        sprite_path = os.path.join(emotion_dir, f)
                        sprite_paths.append(sprite_path)
                        sprite_info.append(f"{costume}/{emotion}/{f}")
        
        print(f"[UmiAI Sprite] Found {len(sprite_paths)} sprites for '{character}'")
        
        return (sprite_paths, sprite_info)


# ==============================================================================
# UMI DATASET GENERATOR (Ported from VNCCS)
# ==============================================================================

class UmiDatasetGenerator:
    """Create LoRA training dataset from character images.
    
    Copies images to a lora folder and generates caption files.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        from .shared_utils import CharacterReplacer
        characters = CharacterReplacer.list_characters()
        
        return {
            "required": {
                "character": (characters if characters else ["None"], {}),
                "trigger_word": ("STRING", {"default": "mycharacter", "tooltip": "LoRA trigger word"}),
            },
            "optional": {
                "additional_caption": ("STRING", {"default": "", "multiline": True}),
                "include_costume_tags": ("BOOLEAN", {"default": True}),
                "include_emotion_tags": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("dataset_path", "file_count")
    FUNCTION = "generate"
    CATEGORY = "UmiAI/character"
    
    def generate(self, character, trigger_word, additional_caption="",
                 include_costume_tags=True, include_emotion_tags=True):
        import os
        import shutil
        from .shared_utils import CharacterReplacer
        
        chars_path = CharacterReplacer.get_characters_path()
        if not chars_path:
            return ("", 0)
        
        char_path = os.path.join(chars_path, character)
        sheets_dir = os.path.join(char_path, "Sheets")
        lora_dir = os.path.join(char_path, "lora_dataset")
        
        os.makedirs(lora_dir, exist_ok=True)
        
        # Load character data for captions
        char_data = CharacterReplacer.load_character(character) or {}
        
        processed = 0
        
        if not os.path.exists(sheets_dir):
            print(f"[UmiAI Dataset] Sheets folder not found: {sheets_dir}")
            return (lora_dir, 0)
        
        # Scan costumes
        costumes = [d for d in os.listdir(sheets_dir) 
                   if os.path.isdir(os.path.join(sheets_dir, d))]
        
        for costume in costumes:
            costume_dir = os.path.join(sheets_dir, costume)
            emotions = [d for d in os.listdir(costume_dir) 
                       if os.path.isdir(os.path.join(costume_dir, d))]
            
            for emotion in emotions:
                emotion_dir = os.path.join(costume_dir, emotion)
                
                for f in os.listdir(emotion_dir):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        src_path = os.path.join(emotion_dir, f)
                        dst_name = f"{costume}_{emotion}_{f}"
                        dst_path = os.path.join(lora_dir, dst_name)
                        
                        try:
                            shutil.copy2(src_path, dst_path)
                            
                            # Build caption
                            caption_parts = [trigger_word]
                            
                            # Add character info
                            info = char_data.get('Info', char_data.get('info', {}))
                            if info.get('sex'):
                                caption_parts.append(f"1{info['sex'][0]}irl" if info['sex'] == 'female' else f"1{info['sex']}")
                            if info.get('hair'):
                                caption_parts.append(info['hair'])
                            if info.get('eyes'):
                                caption_parts.append(info['eyes'])
                            
                            # Add costume/emotion tags
                            if include_costume_tags:
                                caption_parts.append(costume.replace('_', ' '))
                            if include_emotion_tags:
                                caption_parts.append(emotion.replace('_', ' '))
                            
                            if additional_caption:
                                caption_parts.append(additional_caption.strip())
                            
                            caption_text = ", ".join(caption_parts)
                            
                            # Write caption file
                            caption_path = os.path.splitext(dst_path)[0] + ".txt"
                            with open(caption_path, 'w', encoding='utf-8') as cf:
                                cf.write(caption_text)
                            
                            processed += 1
                        except Exception as e:
                            print(f"[UmiAI Dataset] Error: {e}")
        print(f"[UmiAI Dataset] Created {processed} image/caption pairs in {lora_dir}")
        
        return (lora_dir, processed)


# ==============================================================================
# UMI EMOTION STUDIO (Ported from VNCCS EmotionGeneratorV2)
# ==============================================================================

def load_emotions_config():
    """Load emotions.json from the emotions-config folder."""
    config_path = _resolve_umi_asset_path("emotions-config", "emotions.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[UmiAI] Error loading emotions.json: {e}")
    return {}

class UmiEmotionStudio:
    """Enhanced Emotion Generator with visual emotion picker.
    
    Uses emotions.json config for categorized emotions with descriptions.
    Supports SDXL and QWEN prompt styles.
    """
    
    EMOTIONS_DATA = None
    SAFE_NAME_MAP = None
    
    @classmethod
    def _setup_emotions_data(cls):
        if cls.SAFE_NAME_MAP is not None:
            return
        
        try:
            data = load_emotions_config()
            safe_name_map = {}
            for category, emotion_list in data.items():
                if isinstance(emotion_list, list):
                    for emotion in emotion_list:
                        if isinstance(emotion, dict) and 'safe_name' in emotion:
                            safe_name_map[emotion['safe_name']] = {
                                "key": emotion.get('key', emotion['safe_name']),
                                "description": emotion.get('description', ''),
                                "natural_prompt": emotion.get('natural_prompt', ''),
                                "category": category
                            }
            cls.SAFE_NAME_MAP = safe_name_map
            cls.EMOTIONS_DATA = data
        except Exception as e:
            print(f"[UmiAI Emotion Studio] Error: {e}")
            cls.SAFE_NAME_MAP = {}
            cls.EMOTIONS_DATA = {}
    
    @classmethod
    def INPUT_TYPES(cls):
        cls._setup_emotions_data()
        
        from .shared_utils import CharacterReplacer
        characters = CharacterReplacer.list_characters()
        if not characters:
            characters = ["None"]
        
        # Get emotion list from config
        emotions_list = list(cls.SAFE_NAME_MAP.keys()) if cls.SAFE_NAME_MAP else ["neutral", "happy", "sad", "angry"]
        
        return {
            "required": {
                "prompt_style": (["SDXL Style", "QWEN Style"], {"default": "SDXL Style"}),
                "character": (characters, {}),
                "selected_emotions": ("STRING", {
                    "default": "neutral,happy,sad",
                    "multiline": True,
                    "tooltip": "Comma-separated emotion keys from emotions.json"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("emotion_prompts", "emotion_keys", "face_details")
    OUTPUT_IS_LIST = (True, True, False)
    FUNCTION = "generate"
    CATEGORY = "UmiAI/character"
    
    def generate(self, prompt_style, character, selected_emotions):
        self._setup_emotions_data()
        
        from .shared_utils import CharacterReplacer
        
        emotion_list = [e.strip() for e in selected_emotions.split(",") if e.strip()]
        
        prompts = []
        keys = []
        
        # Load character data for face details
        char_data = CharacterReplacer.load_character(character) or {}
        info = char_data.get('Info', char_data.get('info', {}))
        
        # Build face details
        face_parts = []
        if info.get('eyes'):
            face_parts.append(f"({info['eyes']}:1.0)")
        if info.get('hair'):
            face_parts.append(f"({info['hair']}:1.0)")
        if info.get('face'):
            face_parts.append(f"({info['face']}:1.0)")
        face_details = ", ".join(face_parts)
        
        for emotion_key in emotion_list:
            emotion_data = self.SAFE_NAME_MAP.get(emotion_key, {})
            
            if emotion_data:
                description = emotion_data.get('description', emotion_key)
                natural_prompt = emotion_data.get('natural_prompt', '')
                
                if prompt_style == "QWEN Style":
                    # QWEN format
                    prompt = f"Change emotion: {emotion_key}. SDXL Styled tags: {description}. Emotion description: {natural_prompt}. Face details: {face_details}"
                else:
                    # SDXL format
                    prompt = f"({emotion_key}, {description}), {face_details}"
            else:
                # Fallback for unknown emotions
                if prompt_style == "QWEN Style":
                    prompt = f"Change emotion: {emotion_key}. Face details: {face_details}"
                else:
                    prompt = f"({emotion_key}), {face_details}"
            
            prompts.append(prompt)
            keys.append(emotion_key)
        
        print(f"[UmiAI Emotion Studio] Generated {len(prompts)} emotion prompts for '{character}'")
        
        return (prompts, keys, face_details)


# ==============================================================================
# UMI POSITION/CAMERA CONTROL (Ported from VNCCS)
# ==============================================================================

class UmiPositionControl:
    """Generate camera position prompts for QWEN-style angle control.
    
    Uses azimuth/elevation/distance to create position prompts.
    """
    
    AZIMUTH_MAP = {
        0: "front view",
        45: "front-right quarter view",
        90: "right side view",
        135: "back-right quarter view",
        180: "back view",
        225: "back-left quarter view",
        270: "left side view",
        315: "front-left quarter view"
    }
    
    ELEVATION_MAP = {
        -30: "low-angle shot",
        0: "eye-level shot",
        30: "elevated shot",
        60: "high-angle shot"
    }
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "azimuth": ("INT", {"default": 0, "min": 0, "max": 360, "step": 45, "display": "slider",
                                   "tooltip": "Camera angle: 0=Front, 90=Right, 180=Back"}),
                "elevation": ("INT", {"default": 0, "min": -30, "max": 60, "step": 30, "display": "slider",
                                     "tooltip": "Vertical angle: -30=Low, 0=Eye level, 60=High"}),
                "distance": (["close-up", "medium shot", "wide shot"], {"default": "medium shot"}),
                "include_trigger": ("BOOLEAN", {"default": True, "tooltip": "Include <sks> trigger word"}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "generate"
    CATEGORY = "UmiAI/camera"
    
    def generate(self, azimuth, elevation, distance, include_trigger):
        azimuth = int(azimuth) % 360
        
        # Find closest azimuth
        if azimuth > 337.5:
            closest_azimuth = 0
        else:
            closest_azimuth = min(self.AZIMUTH_MAP.keys(), key=lambda x: abs(x - azimuth))
        az_str = self.AZIMUTH_MAP[closest_azimuth]
        
        # Find closest elevation
        closest_elevation = min(self.ELEVATION_MAP.keys(), key=lambda x: abs(x - elevation))
        el_str = self.ELEVATION_MAP[closest_elevation]
        
        # Build prompt
        parts = []
        if include_trigger:
            parts.append("<sks>")
        parts.append(az_str)
        parts.append(el_str)
        parts.append(distance)
        
        return (" ".join(parts),)


class UmiVisualCameraControl(UmiPositionControl):
    """Visual camera control with interactive canvas widget.
    
    Receives JSON data from the camera widget JS.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "camera_data": ("STRING", {"default": "{}", "hidden": True}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "generate_from_json"
    CATEGORY = "UmiAI/camera"
    
    def generate_from_json(self, camera_data):
        try:
            data = json.loads(camera_data)
        except json.JSONDecodeError:
            data = {"azimuth": 0, "elevation": 0, "distance": "medium shot", "include_trigger": True}
        
        return self.generate(
            data.get("azimuth", 0),
            data.get("elevation", 0),
            data.get("distance", "medium shot"),
            data.get("include_trigger", True)
        )


NODE_CLASS_MAPPINGS = {
    "UmiAIWildcardNode": UmiAIWildcardNode,
    "UmiSaveImage": UmiSaveImage,
    "UmiPoseGenerator": UmiPoseGenerator,
    "UmiEmotionGenerator": UmiEmotionGenerator,
    "UmiCharacterCreator": UmiCharacterCreator,
    "UmiSpriteGenerator": UmiSpriteGenerator,
    "UmiDatasetGenerator": UmiDatasetGenerator,
    "UmiEmotionStudio": UmiEmotionStudio,
    "UmiPositionControl": UmiPositionControl,
    "UmiVisualCameraControl": UmiVisualCameraControl
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiAIWildcardNode": "UmiAI Wildcard Processor",
    "UmiSaveImage": "Umi Save Image (with metadata)",
    "UmiPoseGenerator": "Umi Pose Generator",
    "UmiEmotionGenerator": "Umi Emotion Generator",
    "UmiCharacterCreator": "Umi Character Creator",
    "UmiSpriteGenerator": "Umi Sprite Generator",
    "UmiDatasetGenerator": "Umi Dataset Generator",
    "UmiEmotionStudio": "Umi Emotion Studio",
    "UmiPositionControl": "Umi Position Control",
    "UmiVisualCameraControl": "Umi Visual Camera Control"
}

# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@server.PromptServer.instance.routes.get("/umiapp/wildcards")
async def get_wildcards(request):
    # Respect use_folder_paths setting from UMI_SETTINGS (updated by node toggle)
    use_folder_paths = UMI_SETTINGS.get('use_folder_paths', False)
    print(f"[UmiAI API] /umiapp/wildcards called. UMI_SETTINGS['use_folder_paths'] = {use_folder_paths}")
    
    all_paths = get_all_wildcard_paths()
    options = {'use_folder_paths': use_folder_paths, 'verbose': False}
    loader = TagLoader(all_paths, options)
    loader.build_index()
    
    # Separate txt files from yaml for proper autocomplete
    txt_files = []
    yaml_files = []
    tags = set()
    basenames = {}
    
    for path in all_paths:
        if not os.path.exists(path):
            continue
            
        # Scan TXT files (for __ wildcards)
        for filepath in glob.glob(os.path.join(path, '**', '*.txt'), recursive=True):
            if use_folder_paths:
                # Full path mode: Series/A Centaur's Life
                rel_path = os.path.relpath(filepath, path)
                tag_name = os.path.splitext(rel_path)[0].replace(os.sep, '/')
            else:
                # Filename only mode: A Centaur's Life
                tag_name = os.path.splitext(os.path.basename(filepath))[0]
            
            if tag_name not in txt_files:
                txt_files.append(tag_name)
            
            # Add basename mapping
            basename = os.path.splitext(os.path.basename(filepath))[0]
            if basename not in basenames:
                basenames[basename] = tag_name
        
        # Scan YAML files (for tags)
        for filepath in glob.glob(os.path.join(path, '**', '*.yaml'), recursive=True):
            if use_folder_paths:
                # Full path mode
                rel_path = os.path.relpath(filepath, path)
                tag_name = os.path.splitext(rel_path)[0].replace(os.sep, '/')
            else:
                # Filename only mode
                tag_name = os.path.splitext(os.path.basename(filepath))[0]
            
            if tag_name not in yaml_files:
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
                        for entry_name, entry in data.items():
                            # Add entry names as searchable (for <EntryName>)
                            tags.add(str(entry_name).strip())
                            # Also add Tags field if present
                            if isinstance(entry, dict) and 'Tags' in entry:
                                for t in entry['Tags']:
                                    tags.add(str(t).strip())
            except Exception as e:
                print(f"[UmiAI] Error parsing YAML {filepath}: {e}")
    
    loras = folder_paths.get_filename_list("loras")
    loras = sorted(loras) if loras else []

    return web.json_response({
        "files": sorted(txt_files),
        "wildcards": sorted(txt_files),
        "yaml_files": sorted(yaml_files),
        "tags": sorted(list(tags)),
        "basenames": basenames,
        "loras": loras,
        "use_folder_paths": use_folder_paths,  # Include setting so frontend knows
    })

@server.PromptServer.instance.routes.get("/umiapp/loras")
async def get_loras_metadata(request):
    """Phase 6: Get all LoRAs with metadata for browser panel"""
    loras = folder_paths.get_filename_list("loras")
    if not loras:
        return web.json_response({"loras": []})

    lora_handler = LoRAHandler()
    lora_data = []

    # Load CivitAI cache if exists
    civitai_cache = {}
    cache_path = os.path.join(os.path.dirname(__file__), "civitai_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                civitai_cache = json.load(f)
        except Exception as e:
            print(f"[Umi LoRA Browser] Error loading CivitAI cache: {e}")

    # Load manual overrides if exists
    overrides = {}
    overrides_path = os.path.join(os.path.dirname(__file__), "lora_overrides.json")
    if os.path.exists(overrides_path):
        try:
            with open(overrides_path, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
        except Exception as e:
            print(f"[Umi LoRA Browser] Error loading overrides: {e}")

    for lora_name in sorted(loras):
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path:
            continue

        # Get base name without extension
        base_name = os.path.splitext(lora_name)[0]
        lora_dir = os.path.dirname(lora_path)
        lora_base_path = os.path.splitext(lora_path)[0]

        # Check for local metadata files (JSON, civitai.info, preview images)
        local_metadata = {}
        local_preview = None
        civitai_info_tags = []
        
        # Check for .json file next to the LoRA
        json_path = lora_base_path + ".json"
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    local_metadata = json.load(f)
            except Exception as e:
                print(f"[Umi LoRA Browser] Error loading local JSON for {base_name}: {e}")
        
        # Check for .civitai.info file (SD-CivitAI Helper format)
        # Format: "LoRAName.civitai.info" - contains "activation text" field
        civitai_info_path = lora_base_path + ".civitai.info"
        if os.path.exists(civitai_info_path):
            try:
                with open(civitai_info_path, 'r', encoding='utf-8') as f:
                    civitai_info = json.load(f)
                    # Extract activation text if present
                    activation_text = civitai_info.get("activation text", "")
                    if activation_text:
                        civitai_info_tags = [t.strip() for t in activation_text.split(",") if t.strip()]
                    # Store full civitai info in local_metadata if not already set
                    if not local_metadata:
                        local_metadata = civitai_info
            except Exception as e:
                print(f"[Umi LoRA Browser] Error loading .civitai.info for {base_name}: {e}")
        
        # Check for preview images (common formats)
        for ext in ['.preview.png', '.preview.jpg', '.preview.jpeg', '.preview.webp', 
                    '.png', '.jpg', '.jpeg', '.webp']:
            preview_path = lora_base_path + ext
            if os.path.exists(preview_path):
                local_preview = preview_path
                break

        # Get activation tags from SafeTensors metadata
        tags = lora_handler.get_lora_tags(lora_path, max_tags=10)
        
        # Priority for tags: civitai_info_tags > safetensors tags
        # civitai_info_tags come from .civitai.info "activation text" field
        final_tags = civitai_info_tags if civitai_info_tags else (tags if tags else [])

        # Build lora info with local data priority, then overrides, then CivitAI
        lora_info = {
            "name": base_name,
            "filename": lora_name,
            "tags": final_tags,
            "civitai_info_tags": civitai_info_tags,  # Tags from .civitai.info file
            "safetensor_tags": tags if tags else [],  # Tags from safetensor metadata
            "path": lora_path,
            "civitai": civitai_cache.get(base_name, {}),
            "override": overrides.get(base_name, {}),
            "local": local_metadata,  # Local JSON or .civitai.info data
            "local_preview": local_preview,  # Local preview image path
            "has_local_data": bool(local_metadata or local_preview or civitai_info_tags)
        }

        lora_data.append(lora_info)

    return web.json_response({"loras": lora_data})

@server.PromptServer.instance.routes.get("/umiapp/preview")
async def serve_lora_preview(request):
    """Serve local LoRA preview images"""
    import mimetypes
    
    path = request.query.get("path", "")
    if not path:
        return web.Response(status=400, text="Missing path parameter")
    
    # Security: Only allow serving images from loras folder
    lora_paths = folder_paths.get_folder_paths("loras")
    path_allowed = False
    for lora_base in lora_paths:
        if os.path.commonpath([os.path.abspath(path), os.path.abspath(lora_base)]) == os.path.abspath(lora_base):
            path_allowed = True
            break
    
    if not path_allowed:
        return web.Response(status=403, text="Access denied")
    
    if not os.path.exists(path):
        return web.Response(status=404, text="File not found")
    
    # Determine content type
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type or not mime_type.startswith("image/"):
        return web.Response(status=400, text="Not an image file")
    
    try:
        with open(path, 'rb') as f:
            content = f.read()
        return web.Response(body=content, content_type=mime_type)
    except Exception as e:
        return web.Response(status=500, text=str(e))

@server.PromptServer.instance.routes.post("/umiapp/refresh")
async def refresh_wildcards(request):
    GLOBAL_CACHE.clear()
    
    GLOBAL_INDEX['built'] = False 
    GLOBAL_INDEX['files'] = set()
    GLOBAL_INDEX['entries'] = {}
    GLOBAL_INDEX['tags'] = set()
    
    all_paths = get_all_wildcard_paths()
    options = {'use_folder_paths': UMI_SETTINGS.get('use_folder_paths', False), 'verbose': False}
    loader = TagLoader(all_paths, options)
    loader.build_index() 
    
    combined_list = sorted(list(loader.files_index | loader.umi_tags))
    
    loras = folder_paths.get_filename_list("loras")
    loras = sorted(loras) if loras else []
    
    return web.json_response({
        "status": "success",
        "count": len(combined_list),
        "wildcards": combined_list,
        "loras": loras
    })

@server.PromptServer.instance.routes.post("/umiapp/loras/civitai/batch")
async def fetch_civitai_batch(request):
    """Phase 6: Batch fetch CivitAI metadata for all LoRAs with rate limiting"""
    import aiohttp
    import asyncio

    loras = folder_paths.get_filename_list("loras")
    if not loras:
        return web.json_response({"error": "No LoRAs found"}, status=404)

    # Load existing cache
    cache_path = os.path.join(os.path.dirname(__file__), "civitai_cache.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except:
            pass

    results = {
        "total": len(loras),
        "cached": 0,
        "fetched": 0,
        "failed": 0,
        "skipped": 0
    }

    async def fetch_one(session, lora_name):
        base_name = os.path.splitext(lora_name)[0]

        # Skip if already cached
        if base_name in cache:
            results["cached"] += 1
            return

        try:
            # Rate limiting - wait 1.5 seconds between requests
            await asyncio.sleep(1.5)

            # Get file path and hash
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path:
                results["skipped"] += 1
                return

            lora_handler = LoRAHandler()
            file_hash = lora_handler.get_lora_hash(lora_path)

            # Try hash-based lookup first (exact match!)
            model = None
            if file_hash:
                hash_url = f"https://civitai.com/api/v1/model-versions/by-hash/{file_hash}"
                try:
                    async with session.get(hash_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            version_data = await resp.json()
                            # Fetch the full model data
                            model_id = version_data.get("modelId")
                            if model_id:
                                model_url = f"https://civitai.com/api/v1/models/{model_id}"
                                async with session.get(model_url, timeout=aiohttp.ClientTimeout(total=10)) as model_resp:
                                    if model_resp.status == 200:
                                        model = await model_resp.json()
                                        print(f"[Umi LoRA Browser] Hash match found for '{base_name}'")
                except Exception as e:
                    print(f"[Umi LoRA Browser] Hash lookup failed for '{base_name}': {e}")

            # Fallback to name search if hash lookup failed
            if not model:
                from urllib.parse import quote
                search_url = f"https://civitai.com/api/v1/models?query={quote(base_name)}&types=LORA&limit=5"

                async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        results["skipped"] += 1
                        print(f"[Umi LoRA Browser] Skipped '{base_name}': No CivitAI data found")
                        return

                    search_data = await resp.json()

                    if not search_data.get("items"):
                        results["skipped"] += 1
                        print(f"[Umi LoRA Browser] Skipped '{base_name}': No search results")
                        return

                    # Try to find best match based on name similarity
                    items = search_data["items"]

                    # First try exact match (case insensitive)
                    for item in items:
                        if item.get("name", "").lower() == base_name.lower():
                            model = item
                            print(f"[Umi LoRA Browser] Exact name match for '{base_name}'")
                            break

                    # If no exact match, use first result but validate similarity
                    if not model:
                        candidate = items[0]
                        model_name = candidate.get("name", "").lower()
                        base_words = set(base_name.lower().replace('_', ' ').replace('-', ' ').split())
                        model_words = set(model_name.replace('_', ' ').replace('-', ' ').split())

                        # Calculate word overlap - skip if less than 30% match
                        if base_words and model_words:
                            overlap = len(base_words & model_words) / len(base_words)
                            if overlap < 0.3:  # Less than 30% word match
                                results["skipped"] += 1
                                print(f"[Umi LoRA Browser] Skipped '{base_name}': Poor match (closest: '{candidate.get('name')}', overlap: {overlap:.0%})")
                                return
                            else:
                                model = candidate
                                print(f"[Umi LoRA Browser] Fuzzy match for '{base_name}' -> '{candidate.get('name')}' (overlap: {overlap:.0%})")
                        else:
                            results["skipped"] += 1
                            return

            # If we still don't have a model, skip
            if not model:
                results["skipped"] += 1
                return

            # Extract CivitAI data from the model
            civitai_data = {
                "id": model.get("id"),
                "name": model.get("name"),
                "description": model.get("description", "")[:300],  # Truncate
                "tags": model.get("tags", [])[:15],
                "creator": model.get("creator", {}).get("username", "Unknown"),
                "url": f"https://civitai.com/models/{model.get('id')}",
            }

            if model.get("modelVersions"):
                latest_version = model["modelVersions"][0]
                civitai_data["trigger_words"] = latest_version.get("trainedWords", [])[:15]
                civitai_data["base_model"] = latest_version.get("baseModel", "Unknown")

                if latest_version.get("images"):
                    first_image = latest_version["images"][0]
                    civitai_data["preview_url"] = first_image.get("url")
                    civitai_data["nsfw"] = first_image.get("nsfw", "None")

            cache[base_name] = civitai_data
            results["fetched"] += 1
            print(f"[Umi LoRA Browser] Fetched: {base_name}")

        except asyncio.TimeoutError:
            results["failed"] += 1
            print(f"[Umi LoRA Browser] Timeout: {base_name}")
        except Exception as e:
            results["failed"] += 1
            print(f"[Umi LoRA Browser] Error fetching {base_name}: {e}")

    try:
        async with aiohttp.ClientSession() as session:
            # Process in batches to avoid overwhelming CivitAI
            batch_size = 5
            for i in range(0, len(loras), batch_size):
                batch = loras[i:i+batch_size]
                tasks = [fetch_one(session, lora_name) for lora_name in batch]
                await asyncio.gather(*tasks)

                # Save cache after each batch
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, indent=2, ensure_ascii=False)

        return web.json_response({"success": True, "results": results})

    except Exception as e:
        print(f"[Umi LoRA Browser] Batch fetch error: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.post("/umiapp/loras/civitai/single")
async def fetch_civitai_single(request):
    """Fetch CivitAI metadata for a single LoRA"""
    import aiohttp
    
    try:
        data = await request.json()
        lora_name = data.get("lora_name")
        
        if not lora_name:
            return web.json_response({"error": "lora_name required"}, status=400)
        
        base_name = os.path.splitext(lora_name)[0] if "." in lora_name else lora_name
        
        # Load existing cache
        cache_path = os.path.join(os.path.dirname(__file__), "civitai_cache.json")
        cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
            except:
                pass
        
        # Skip if already cached
        if base_name in cache:
            return web.json_response({"success": True, "cached": True, "data": cache[base_name]})
        
        async with aiohttp.ClientSession() as session:
            # Get file path and hash
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path:
                # Try with .safetensors extension
                lora_path = folder_paths.get_full_path("loras", f"{lora_name}.safetensors")
            
            file_hash = None
            if lora_path:
                lora_handler = LoRAHandler()
                file_hash = lora_handler.get_lora_hash(lora_path)
            
            model = None
            
            # Try hash-based lookup first
            if file_hash:
                hash_url = f"https://civitai.com/api/v1/model-versions/by-hash/{file_hash}"
                try:
                    async with session.get(hash_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            version_data = await resp.json()
                            model_id = version_data.get("modelId")
                            if model_id:
                                model_url = f"https://civitai.com/api/v1/models/{model_id}"
                                async with session.get(model_url, timeout=aiohttp.ClientTimeout(total=10)) as model_resp:
                                    if model_resp.status == 200:
                                        model = await model_resp.json()
                except Exception as e:
                    print(f"[Umi LoRA Browser] Hash lookup failed: {e}")
            
            # Fallback to name search - EXACT MATCH ONLY
            if not model:
                from urllib.parse import quote
                search_url = f"https://civitai.com/api/v1/models?query={quote(base_name)}&types=LORA&limit=5"
                
                async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        search_data = await resp.json()
                        items = search_data.get("items", [])
                        
                        # Only accept exact name match - NO FALLBACK
                        for item in items:
                            if item.get("name", "").lower() == base_name.lower():
                                model = item
                                break
                        
                        # If no exact match, return not found (user can use Edit to add manually)
            
            if not model:
                return web.json_response({"success": False, "error": "No exact match found. Use Edit to add manually."})
            
            # Extract CivitAI data
            civitai_data = {
                "id": model.get("id"),
                "name": model.get("name"),
                "description": model.get("description", "")[:300],
                "tags": model.get("tags", [])[:15],
                "creator": model.get("creator", {}).get("username", "Unknown"),
                "url": f"https://civitai.com/models/{model.get('id')}",
            }
            
            if model.get("modelVersions"):
                latest_version = model["modelVersions"][0]
                civitai_data["trigger_words"] = latest_version.get("trainedWords", [])[:15]
                civitai_data["base_model"] = latest_version.get("baseModel", "Unknown")
                
                if latest_version.get("images"):
                    first_image = latest_version["images"][0]
                    civitai_data["preview_url"] = first_image.get("url")
                    civitai_data["nsfw"] = first_image.get("nsfw", "None")
            
            # Save to cache
            cache[base_name] = civitai_data
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            
            return web.json_response({"success": True, "cached": False, "data": civitai_data})
            
    except Exception as e:
        print(f"[Umi LoRA Browser] Single fetch error: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.get("/umiapp/loras/overrides")
async def get_lora_overrides(request):
    """Get manual overrides for LoRAs (nicknames, custom tags, custom preview)"""
    overrides_path = os.path.join(os.path.dirname(__file__), "lora_overrides.json")

    if os.path.exists(overrides_path):
        try:
            with open(overrides_path, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
            return web.json_response({"overrides": overrides})
        except Exception as e:
            print(f"[Umi LoRA Browser] Error loading overrides: {e}")
            return web.json_response({"overrides": {}})

    return web.json_response({"overrides": {}})

@server.PromptServer.instance.routes.post("/umiapp/loras/overrides/save")
async def save_lora_override(request):
    """Save manual override for a specific LoRA"""
    try:
        data = await request.json()
        lora_name = data.get("lora_name")
        override_data = data.get("override", {})

        if not lora_name:
            return web.json_response({"error": "LoRA name required"}, status=400)

        overrides_path = os.path.join(os.path.dirname(__file__), "lora_overrides.json")

        # Load existing overrides
        overrides = {}
        if os.path.exists(overrides_path):
            try:
                with open(overrides_path, 'r', encoding='utf-8') as f:
                    overrides = json.load(f)
            except:
                pass

        # Update override for this LoRA
        overrides[lora_name] = override_data

        # Save back to file
        with open(overrides_path, 'w', encoding='utf-8') as f:
            json.dump(overrides, f, indent=2, ensure_ascii=False)

        return web.json_response({"success": True})

    except Exception as e:
        print(f"[Umi LoRA Browser] Error saving override: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.get("/umiapp/images/scan")
async def scan_images(request):
    """Phase 6: Scan output directory for images with metadata"""
    import asyncio
    from PIL import Image as PILImage
    from PIL.PngImagePlugin import PngInfo

    # Get output directory
    output_dir = folder_paths.get_output_directory()
    if not os.path.exists(output_dir):
        return web.json_response({"error": "Output directory not found"}, status=404)

    # Get query parameters
    params = request.rel_url.query
    limit = int(params.get("limit", 100))
    offset = int(params.get("offset", 0))
    sort_by = params.get("sort", "newest")  # newest, oldest, name

    images_data = []

    def extract_metadata(image_path):
        """Extract metadata from PNG/JPG"""
        try:
            with PILImage.open(image_path) as img:
                metadata = {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "prompt": None,
                    "negative": None,
                    "workflow": None,
                    "parameters": {}
                }

                # PNG metadata
                if img.format == "PNG":
                    # ComfyUI workflow (in 'prompt' key)
                    if "prompt" in img.info:
                        try:
                            metadata["workflow"] = json.loads(img.info["prompt"])
                        except:
                            pass

                    # A1111 format (in 'parameters' key)
                    if "parameters" in img.info:
                        params_text = img.info["parameters"]
                        metadata["a1111_params"] = params_text

                        # Parse A1111 format
                        lines = params_text.split("\n")
                        if len(lines) > 0:
                            metadata["prompt"] = lines[0]

                        # Look for "Negative prompt:"
                        for i, line in enumerate(lines):
                            if line.startswith("Negative prompt:"):
                                metadata["negative"] = line.replace("Negative prompt:", "").strip()
                                break

                    # Check for custom Umi keys
                    if "umi_prompt" in img.info:
                        metadata["umi_prompt"] = img.info["umi_prompt"]
                    if "umi_negative" in img.info:
                        metadata["umi_negative"] = img.info["umi_negative"]
                    if "umi_input_prompt" in img.info:
                        metadata["umi_input_prompt"] = img.info["umi_input_prompt"]
                    if "umi_input_negative" in img.info:
                        metadata["umi_input_negative"] = img.info["umi_input_negative"]

                    # Set fallback for 'prompt' and 'negative' if not already set
                    if metadata["prompt"] is None and "umi_prompt" in img.info:
                        metadata["prompt"] = img.info["umi_prompt"]
                    if metadata["negative"] is None and "umi_negative" in img.info:
                        metadata["negative"] = img.info["umi_negative"]

                # EXIF data (for JPG)
                if hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    # User Comment tag (0x9286)
                    if 0x9286 in exif:
                        metadata["prompt"] = exif[0x9286]

                return metadata

        except Exception as e:
            print(f"[Umi Image Browser] Error extracting metadata from {image_path}: {e}")
            return None

    # Scan directory
    try:
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        all_images = []

        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if os.path.splitext(file.lower())[1] in image_extensions:
                    full_path = os.path.join(root, file)
                    all_images.append({
                        "path": full_path,
                        "filename": file,
                        "relative_path": os.path.relpath(full_path, output_dir),
                        "mtime": os.path.getmtime(full_path),
                        "size": os.path.getsize(full_path)
                    })

        # Sort images
        if sort_by == "newest":
            all_images.sort(key=lambda x: x["mtime"], reverse=True)
        elif sort_by == "oldest":
            all_images.sort(key=lambda x: x["mtime"])
        elif sort_by == "name":
            all_images.sort(key=lambda x: x["filename"])

        # Paginate
        paginated = all_images[offset:offset+limit]

        # Extract metadata for paginated results
        for img_info in paginated:
            metadata = extract_metadata(img_info["path"])
            if metadata:
                img_info["metadata"] = metadata
            else:
                img_info["metadata"] = {}

            # Create web-accessible URL
            rel_path = img_info["relative_path"].replace("\\", "/")
            img_info["url"] = f"/view?filename={rel_path}&type=output"

            # Remove full path for security
            del img_info["path"]

        return web.json_response({
            "images": paginated,
            "total": len(all_images),
            "offset": offset,
            "limit": limit
        })

    except Exception as e:
        print(f"[Umi Image Browser] Scan error: {e}")
        return web.json_response({"error": str(e)}, status=500)

# Phase 8: Preset Manager Endpoints
@server.PromptServer.instance.routes.get("/umiapp/presets")
async def get_presets(request):
    """Phase 8: Get all saved presets"""
    presets_file = os.path.join(os.path.dirname(__file__), "presets.json")

    if not os.path.exists(presets_file):
        return web.json_response({"presets": []})

    try:
        with open(presets_file, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        return web.json_response({"presets": presets})
    except Exception as e:
        print(f"[Umi Preset Manager] Error loading presets: {e}")
        return web.json_response({"presets": []})

@server.PromptServer.instance.routes.post("/umiapp/presets/save")
async def save_preset(request):
    """Phase 8: Save a new preset"""
    try:
        data = await request.json()
        name = data.get("name")
        description = data.get("description", "")
        preset_data = data.get("data", {})

        if not name:
            return web.json_response({"error": "Preset name is required"}, status=400)

        presets_file = os.path.join(os.path.dirname(__file__), "presets.json")

        # Load existing presets
        presets = []
        if os.path.exists(presets_file):
            with open(presets_file, 'r', encoding='utf-8') as f:
                presets = json.load(f)

        # Check if preset with same name exists
        presets = [p for p in presets if p.get("name") != name]

        # Add new preset
        presets.append({
            "name": name,
            "description": description,
            "data": preset_data,
            "timestamp": datetime.now().isoformat()
        })

        # Save presets
        with open(presets_file, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2, ensure_ascii=False)

        return web.json_response({"success": True})

    except Exception as e:
        print(f"[Umi Preset Manager] Error saving preset: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.post("/umiapp/presets/delete")
async def delete_preset(request):
    """Phase 8: Delete a preset"""
    try:
        data = await request.json()
        name = data.get("name")

        if not name:
            return web.json_response({"error": "Preset name is required"}, status=400)

        presets_file = os.path.join(os.path.dirname(__file__), "presets.json")

        if not os.path.exists(presets_file):
            return web.json_response({"error": "No presets found"}, status=404)

        # Load and filter presets
        with open(presets_file, 'r', encoding='utf-8') as f:
            presets = json.load(f)

        presets = [p for p in presets if p.get("name") != name]

        # Save filtered presets
        with open(presets_file, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2, ensure_ascii=False)

        return web.json_response({"success": True})

    except Exception as e:
        print(f"[Umi Preset Manager] Error deleting preset: {e}")
        return web.json_response({"error": str(e)}, status=500)

# Phase 8: Prompt History Endpoints
@server.PromptServer.instance.routes.get("/umiapp/history")
async def get_history(request):
    """Phase 8: Get prompt history"""
    history_file = os.path.join(os.path.dirname(__file__), "prompt_history.json")

    if not os.path.exists(history_file):
        return web.json_response({"history": []})

    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)

        # Sort by timestamp descending (newest first)
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return web.json_response({"history": history})
    except Exception as e:
        print(f"[Umi History] Error loading history: {e}")
        return web.json_response({"history": []})

@server.PromptServer.instance.routes.post("/umiapp/history/clear")
async def clear_history(request):
    """Phase 8: Clear all prompt history"""
    try:
        history_file = os.path.join(os.path.dirname(__file__), "prompt_history.json")

        if os.path.exists(history_file):
            os.remove(history_file)

        return web.json_response({"success": True})
    except Exception as e:
        print(f"[Umi History] Error clearing history: {e}")
        return web.json_response({"error": str(e)}, status=500)

# Phase 8: YAML Tag Management Endpoints
@server.PromptServer.instance.routes.get("/umiapp/yaml/tags")
async def get_yaml_tags(request):
    """Phase 8: Export all YAML tags with their entries"""
    try:
        all_wildcard_paths = get_all_wildcard_paths()
        tag_loader = TagLoader(all_wildcard_paths, {'use_folder_paths': UMI_SETTINGS.get('use_folder_paths', False), 'verbose': False, 'seed': 0})

        # Build complete index
        tag_loader.build_index()

        # Get all YAML entries with tags
        yaml_entries = tag_loader.yaml_entries

        # Build export data
        export_data = {
            "total_entries": len(yaml_entries),
            "tags": {},
            "entries": []
        }

        # Collect all unique tags
        all_tags = set()
        for entry_name, entry_data in yaml_entries.items():
            tags = entry_data.get('tags', [])
            all_tags.update(tags)

            export_data["entries"].append({
                "name": entry_name,
                "title": entry_data.get('title', entry_name),
                "tags": tags,
                "prompts": entry_data.get('prompts', []),
                "description": entry_data.get('description', '')
            })

        # Build tag index
        for tag in sorted(all_tags):
            export_data["tags"][tag] = {
                "count": sum(1 for e in export_data["entries"] if tag in e["tags"]),
                "entries": [e["name"] for e in export_data["entries"] if tag in e["tags"]]
            }

        return web.json_response(export_data)

    except Exception as e:
        print(f"[Umi YAML Tags] Error exporting tags: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.post("/umiapp/yaml/tags/import")
async def import_yaml_tags(request):
    """Phase 8: Import tags from CSV"""
    try:
        data = await request.json()
        csv_data = data.get("csv_data", "")

        if not csv_data:
            return web.json_response({"error": "No CSV data provided"}, status=400)

        # Parse CSV (format: entry_name,tag1,tag2,tag3...)
        import csv
        from io import StringIO

        reader = csv.reader(StringIO(csv_data))
        updates = []

        for row in reader:
            if len(row) < 2:
                continue

            entry_name = row[0].strip()
            new_tags = [tag.strip() for tag in row[1:] if tag.strip()]

            if entry_name and new_tags:
                updates.append({
                    "entry": entry_name,
                    "tags": new_tags
                })

        # Return update plan (actual file writing would require YAML editing)
        return web.json_response({
            "success": True,
            "updates_planned": len(updates),
            "updates": updates,
            "note": "Tag import parsed successfully. Manual YAML update recommended."
        })

    except Exception as e:
        print(f"[Umi YAML Tags] Error importing tags: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.get("/umiapp/yaml/stats")
async def get_yaml_stats(request):
    """Phase 8: Get YAML statistics"""
    try:
        all_wildcard_paths = get_all_wildcard_paths()
        tag_loader = TagLoader(all_wildcard_paths, {'use_folder_paths': UMI_SETTINGS.get('use_folder_paths', False), 'verbose': False, 'seed': 0})
        tag_loader.build_index()

        yaml_entries = tag_loader.yaml_entries

        # Calculate statistics
        total_entries = len(yaml_entries)
        total_tags = len(set(tag for entry in yaml_entries.values() for tag in entry.get('tags', [])))

        entries_with_tags = sum(1 for entry in yaml_entries.values() if entry.get('tags'))
        entries_without_tags = total_entries - entries_with_tags

        # Most common tags
        tag_counts = {}
        for entry in yaml_entries.values():
            for tag in entry.get('tags', []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]

        stats = {
            "total_entries": total_entries,
            "total_unique_tags": total_tags,
            "entries_with_tags": entries_with_tags,
            "entries_without_tags": entries_without_tags,
            "average_tags_per_entry": round(sum(len(e.get('tags', [])) for e in yaml_entries.values()) / total_entries, 2) if total_entries > 0 else 0,
            "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags]
        }

        return web.json_response(stats)

    except Exception as e:
        print(f"[Umi YAML Stats] Error calculating stats: {e}")
        return web.json_response({"error": str(e)}, status=500)

# Phase 8: File Editor Endpoints
@server.PromptServer.instance.routes.get("/umiapp/files/list")
async def list_files(request):
    """Phase 8: List all wildcard files"""
    try:
        all_paths = get_all_wildcard_paths()
        files = []

        for wildcard_path in all_paths:
            for root, dirs, filenames in os.walk(wildcard_path):
                for filename in filenames:
                    if filename.endswith(('.txt', '.yaml')):
                        full_path = os.path.join(root, filename)
                        files.append(full_path)

        return web.json_response({"files": files})

    except Exception as e:
        print(f"[Umi File Editor] Error listing files: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.post("/umiapp/files/read")
async def read_file(request):
    """Phase 8: Read a file's content"""
    try:
        data = await request.json()
        filepath = data.get("filepath")

        if not filepath or not os.path.exists(filepath):
            return web.json_response({"error": "File not found"}, status=404)

        # Security: ensure file is in wildcard paths
        all_paths = get_all_wildcard_paths()
        is_valid = any(filepath.startswith(path) for path in all_paths)

        if not is_valid:
            return web.json_response({"error": "Access denied"}, status=403)

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        return web.json_response({"success": True, "content": content})

    except Exception as e:
        print(f"[Umi File Editor] Error reading file: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.post("/umiapp/files/write")
async def write_file(request):
    """Phase 8: Write content to a file"""
    try:
        data = await request.json()
        filepath = data.get("filepath")
        content = data.get("content", "")

        if not filepath:
            return web.json_response({"error": "No filepath provided"}, status=400)

        # Security: ensure file is in wildcard paths
        all_paths = get_all_wildcard_paths()
        is_valid = any(filepath.startswith(path) for path in all_paths)

        if not is_valid:
            return web.json_response({"error": "Access denied"}, status=403)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return web.json_response({"success": True})

    except Exception as e:
        print(f"[Umi File Editor] Error writing file: {e}")
        return web.json_response({"error": str(e)}, status=500)

@server.PromptServer.instance.routes.post("/umiapp/files/create")
async def create_file(request):
    """Phase 8: Create a new file"""
    try:
        data = await request.json()
        filename = data.get("filename")

        if not filename:
            return web.json_response({"error": "No filename provided"}, status=400)

        # Get first wildcard path
        all_paths = get_all_wildcard_paths()
        if not all_paths:
            return web.json_response({"error": "No wildcard paths configured"}, status=500)

        wildcard_path = all_paths[0]
        filepath = os.path.join(wildcard_path, filename)

        # Check if file already exists
        if os.path.exists(filepath):
            return web.json_response({"error": "File already exists"}, status=400)

        # Create empty file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("")

        return web.json_response({"success": True, "filepath": filepath})

    except Exception as e:
        print(f"[Umi File Editor] Error creating file: {e}")
        return web.json_response({"error": str(e)}, status=500)
