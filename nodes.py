import os
import random
import re
import yaml
import glob
import json
import csv
import requests
import fnmatch
from collections import Counter
import folder_paths
import comfy.sd
import comfy.utils
import torch 
from safetensors import safe_open 

# API Imports
import server
from aiohttp import web

# ==============================================================================
# GLOBAL CACHE
# ==============================================================================
GLOBAL_CACHE = {}
# Persist the card index across generations
GLOBAL_INDEX = {'built': False, 'files': set(), 'entries': {}} 

# ==============================================================================
# OPTIONAL IMPORTS (LLM & Downloader)
# ==============================================================================
try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

try:
    from huggingface_hub import hf_hub_download
    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False

# ==============================================================================
# CONSTANTS & HELPER FUNCTIONS
# ==============================================================================

DOWNLOADABLE_MODELS = {
    "Download: Qwen2.5-1.5B (Fast, Low RAM)": {
        "repo_id": "bartowski/Qwen2.5-Coder-1.5B-Instruct-abliterated-GGUF",
        "filename": "Qwen2.5-Coder-1.5B-Instruct-abliterated-Q4_K_M.gguf"
    },
    "Download: Dolphin-Llama3.1-8B (Smart, Uncensored)": {
        "repo_id": "bartowski/dolphin-2.9.4-llama3.1-8b-GGUF",
        "filename": "dolphin-2.9.4-llama3.1-8b-Q4_K_M.gguf"
    }
}

ALL_KEY = 'all_files_index'

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
        if '#' in line:
            line = line.split('#')[0].strip()
        lines.append(line)
    return lines

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

def process_wildcard_range(tag, lines):
    if not lines:
        return ""
    if tag.startswith('#'):
        return None
    
    if "$$" not in tag:
        selected = random.choice(lines)
        if '#' in selected:
            selected = selected.split('#')[0].strip()
        return selected
        
    range_str, tag_name = tag.split("$$", 1)
    try:
        low, high = parse_wildcard_range(range_str, len(lines))
        num_items = random.randint(low, high)
        if num_items == 0:
            return ""
            
        selected = random.sample(lines, min(num_items, len(lines)))
        selected = [line.split('#')[0].strip() if '#' in line else line for line in selected]
        return ", ".join(selected)
    except Exception as e:
        print(f"Error processing wildcard range: {e}")
        selected = random.choice(lines)
        if '#' in selected:
            selected = selected.split('#')[0].strip()
        return selected

def get_all_wildcard_paths():
    """
    Returns a list of all valid wildcard directory paths.
    Checks:
    1. Internal UmiAI/wildcards
    2. ComfyUI/wildcards (Root)
    3. ComfyUI/models/wildcards
    """
    paths = set()
    
    # 1. Internal Umi Folder
    internal_path = os.path.join(os.path.dirname(__file__), "wildcards")
    if os.path.exists(internal_path):
        paths.add(internal_path)
    
    # 2. ComfyUI/wildcards (Root)
    root_wildcards = os.path.join(folder_paths.base_path, "wildcards")
    if os.path.exists(root_wildcards):
        paths.add(root_wildcards)

    # 3. ComfyUI/models/wildcards
    models_wildcards = os.path.join(folder_paths.models_dir, "wildcards")
    if os.path.exists(models_wildcards):
        paths.add(models_wildcards)

    # 4. Check for 'wildcards' type in folder_paths (external extensions)
    try:
        ext_paths = folder_paths.get_folder_paths("wildcards")
        if ext_paths:
            for p in ext_paths:
                if os.path.exists(p):
                    paths.add(p)
    except:
        pass
    
    return list(paths)

# ==============================================================================
# CORE CLASSES
# ==============================================================================

class TagLoader:
    def __init__(self, wildcard_paths, options):
        # Allow passing a single string or a list
        if isinstance(wildcard_paths, str):
            self.wildcard_locations = [wildcard_paths]
        else:
            self.wildcard_locations = wildcard_paths

        self.loaded_tags = {}
        self.yaml_entries = {}
        self.files_index = set() 
        self.index_built = False
        self.ignore_paths = options.get('ignore_paths', True)
        self.verbose = options.get('verbose', False)
        
        # Mappings
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
                    # Rel path must be relative to the *current* root location being scanned
                    rel_path = os.path.relpath(full_path, location)
                    
                    # Normalize slashes for consistency across OS
                    key = os.path.splitext(rel_path)[0].replace(os.sep, '/')
                    
                    name_lower = file.lower()
                    if name_lower.endswith('.txt'):
                        self.txt_lookup[key.lower()] = full_path
                    elif name_lower.endswith('.yaml'):
                        self.yaml_lookup[key.lower()] = full_path
                    elif name_lower.endswith('.csv'):
                        self.csv_lookup[key.lower()] = full_path

    def build_index(self):
        # OPTIMIZATION: Check if we already did this work globally
        if GLOBAL_INDEX['built']:
            self.files_index = GLOBAL_INDEX['files']
            self.yaml_entries = GLOBAL_INDEX['entries']
            self.index_built = True
            return

        if self.index_built:
            return

        new_index = set()
        new_entries = {}
        
        # 1. Add Files (TXT/CSV)
        for key in self.txt_lookup.keys():
            new_index.add(key)
        for key in self.csv_lookup.keys():
            new_index.add(key)

        # 2. Add YAML Keys
        for file_key, full_path in self.yaml_lookup.items():
            if file_key == 'globals':
                continue
            try:
                with open(full_path, encoding="utf8") as f:
                    data = yaml.safe_load(f)
                    
                    # Fix: Immediate population of entries for Umi format
                    if self.is_umi_format(data):
                         for k, v in data.items():
                             new_index.add(k)
                             # Store card data
                             if isinstance(v, dict):
                                 processed = self.process_yaml_entry(k, v)
                                 if processed['tags']:
                                     new_entries[k.lower()] = processed
                    else:
                        flat_data = self.flatten_hierarchical_yaml(data)
                        for k in flat_data.keys():
                            combined = f"{file_key}/{k}"
                            new_index.add(combined)
            except Exception as e:
                pass

        # Save to Instance
        self.files_index = new_index
        self.yaml_entries = new_entries
        self.index_built = True
        
        # Save to Global Cache (Persist for next run)
        GLOBAL_INDEX['files'] = new_index
        GLOBAL_INDEX['entries'] = new_entries
        GLOBAL_INDEX['built'] = True

    def load_globals(self):
        """Loads globals.yaml from ALL detected paths and merges them."""
        merged_globals = {}
        
        for location in self.wildcard_locations:
            global_path = os.path.join(location, 'globals.yaml')
            if os.path.exists(global_path):
                try:
                    with open(global_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            # Update dictionary (later paths overwrite earlier ones)
                            merged_globals.update({str(k): str(v) for k, v in data.items()})
                except Exception as e:
                    print(f"[UmiAI] Error loading globals.yaml at {global_path}: {e}")
                    
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
    
    def flatten_hierarchical_yaml(self, data, prefix=""):
        results = {}
        if isinstance(data, dict):
            for k, v in data.items():
                clean_key = str(k).strip()
                new_prefix = f"{prefix}/{clean_key}" if prefix else clean_key
                results.update(self.flatten_hierarchical_yaml(v, new_prefix))
        elif isinstance(data, list):
            clean_list = [str(x) for x in data if x is not None]
            results[prefix] = clean_list
        elif data is not None:
            results[prefix] = [str(data)]
        return results

    def is_umi_format(self, data):
        """
        Determines if the YAML file follows the Umi 'Card' structure.
        Criteria: The data is a dictionary, and at least one of its values 
        is a dictionary containing a 'Prompts' key (case-insensitive).
        """
        if not isinstance(data, dict):
            return False
        
        # We iterate through the top-level keys (Card Titles)
        for key, value in data.items():
            if isinstance(value, dict):
                # Check keys case-insensitively for 'prompts'
                keys_lower = {k.lower() for k in value.keys()}
                if 'prompts' in keys_lower:
                    return True
        return False

    def load_tags(self, requested_tag, verbose=False):
        # Fix: Handle Global Index Request for Tag Aggregation
        if requested_tag == ALL_KEY:
            self.build_index() # Ensure we have data
            return self.yaml_entries

        if requested_tag in GLOBAL_CACHE:
            return GLOBAL_CACHE[requested_tag]
        
        lower_tag = requested_tag.lower()
        
        # 1. Try TXT files
        if lower_tag in self.txt_lookup:
            with open(self.txt_lookup[lower_tag], encoding="utf8") as f:
                lines = read_file_lines(f)
                GLOBAL_CACHE[requested_tag] = lines
                return lines
        
        # 2. Try CSV files
        if lower_tag in self.csv_lookup:
            with open(self.csv_lookup[lower_tag], 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                GLOBAL_CACHE[requested_tag] = rows
                return rows

        # 3. YAML Handling (Branching Path)
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
                    
                    # SYSTEM 1: Umi "Card" System
                    if self.is_umi_format(data):
                        # Populate global index if not already (mostly handled by build_index now)
                        for title, entry in data.items():
                            if isinstance(entry, dict):
                                processed = self.process_yaml_entry(title, entry)
                                if processed['tags']:
                                    self.yaml_entries[title.lower()] = processed

                        # Return specific card if requested
                        if key_suffix:
                             for k, v in data.items():
                                 if k.lower() == key_suffix:
                                     processed = self.process_yaml_entry(k, v)
                                     GLOBAL_CACHE[requested_tag] = processed['prompts']
                                     return processed['prompts']
                        return []

                    # SYSTEM 2: Standard "Folder" System (Hierarchical)
                    else:
                        flat_data = self.flatten_hierarchical_yaml(data)
                        if key_suffix:
                            # Exact path match (case-insensitive)
                            for k, v in flat_data.items():
                                if k.lower() == key_suffix:
                                    GLOBAL_CACHE[requested_tag] = v
                                    return v
                            return []
                        else:
                            # Return all leaves if root file selected
                            all_values = []
                            for v in flat_data.values():
                                all_values.extend(v)
                            return all_values

                except Exception as e:
                    if verbose: print(f'Error parsing YAML {found_file}: {e}')

        return []

    def get_glob_matches(self, pattern):
        self.build_index()
        return fnmatch.filter(self.files_index, pattern)

    def get_entry_details(self, title):
        # Fallback if entry is not in dict but index is built
        if title and title.lower() in self.yaml_entries:
            return self.yaml_entries[title.lower()]
        return self.yaml_entries.get(title)

class TagSelector:
    def __init__(self, tag_loader, options):
        self.tag_loader = tag_loader
        self.previously_selected_tags = {}
        self.used_values = {}
        self.selected_options = options.get('selected_options', {})
        self.verbose = options.get('verbose', False)
        self.global_seed = options.get('seed', 0)
        self.seeded_values = {}
        self.processing_stack = set()
        self.resolved_seeds = {}
        self.selected_entries = {}
        self.scoped_negatives = []
        self.variables = {} 

    def update_variables(self, variables):
        self.variables = variables

    def clear_seeded_values(self):
        self.seeded_values = {}
        self.resolved_seeds = {}
        self.processing_stack.clear()
        self.selected_entries.clear()
        self.scoped_negatives = []

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

    def get_tag_choice(self, parsed_tag, tags):
        if isinstance(tags, list) and len(tags) > 0 and isinstance(tags[0], dict):
            row = random.choice(tags)
            vars_out = []
            for k, v in row.items():
                vars_out.append(f"${k.strip()}={v.strip()}")
            return " ".join(vars_out)

        if not isinstance(tags, list):
            return ""
        
        seed_match = re.match(r'#([0-9|]+)\$\$(.*)', parsed_tag)
        if seed_match:
            seed_options = seed_match.group(1).split('|')
            chosen_seed = random.choice(seed_options)
            
            if chosen_seed in self.seeded_values:
                selected = self.seeded_values[chosen_seed]
                return self.resolve_wildcard_recursively(selected, chosen_seed)
            
            unused = [t for t in tags if t not in self.used_values]
            selected = random.choice(unused) if unused else random.choice(tags)
            
            self.seeded_values[chosen_seed] = selected
            self.used_values[selected] = True
            return self.resolve_wildcard_recursively(selected, chosen_seed)

        selected = None
        if len(tags) == 1:
            selected = tags[0]
        else:
            unused = [t for t in tags if t not in self.used_values]
            selected = random.choice(unused) if unused else random.choice(tags)

        if selected:
            self.used_values[selected] = True
            entry_details = self.tag_loader.get_entry_details(selected)
            if entry_details:
                self.selected_entries[parsed_tag] = entry_details
                if entry_details['prompts']:
                    selected = random.choice(entry_details['prompts'])
            if isinstance(selected, str) and '#' in selected:
                selected = selected.split('#')[0].strip()
            selected = self.process_scoped_negative(selected)

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

    def get_tag_group_choice(self, parsed_tag, groups, tags):
        if not isinstance(tags, dict):
            return ""
        
        resolved_groups = []
        for g in groups:
            clean_g = g.strip()
            # Fix: Resolve variables inside tags (e.g. <[$char]> -> <[rin]>)
            if clean_g.startswith('$') and clean_g[1:] in self.variables:
                val = self.variables[clean_g[1:]]
                resolved_groups.append(val)
            else:
                resolved_groups.append(clean_g)

        neg_groups = {x.replace('--', '').strip().lower() for x in resolved_groups if x.startswith('--')}
        pos_groups = {x.strip().lower() for x in resolved_groups if not x.startswith('--') and '|' not in x}
        any_groups = [{y.strip() for y in x.lower().split('|')} for x in resolved_groups if '|' in x]

        candidates = []
        
        # Fix: Better Dictionary Handling for Umi Cards
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
            
            selected_title = random.choice(candidates)
            if seed_id and seed_id in self.seeded_values:
                selected_title = self.seeded_values[seed_id]
            elif seed_id:
                self.seeded_values[seed_id] = selected_title
                
            entry_details = self.tag_loader.get_entry_details(selected_title)
            if entry_details:
                self.selected_entries[parsed_tag] = entry_details
                if entry_details['prompts']:
                    return self.resolve_wildcard_recursively(random.choice(entry_details['prompts']), seed_id)
            return self.resolve_wildcard_recursively(selected_title, seed_id)
        return ""

    def select(self, tag, groups=None):
        self.previously_selected_tags.setdefault(tag, 0)
        if self.previously_selected_tags.get(tag) > 500:
            return f"LOOP_ERROR({tag})"
        
        self.previously_selected_tags[tag] += 1
        parsed_tag = parse_tag(tag)
        
        # --- GLOB MATCHING ---
        if '*' in parsed_tag or '?' in parsed_tag:
            matches = self.tag_loader.get_glob_matches(parsed_tag)
            if matches:
                random.shuffle(matches)
                for selected_key in matches:
                    result = self.select(selected_key, groups)
                    if result and str(result).strip():
                        return result
            return ""

        sequential = False
        if parsed_tag.startswith('~'):
            sequential = True
            parsed_tag = parsed_tag[1:]

        if '$$' in parsed_tag and not parsed_tag.startswith('#'):
            range_part, file_part = parsed_tag.split('$$', 1)
            if any(c.isdigit() for c in range_part) or '-' in range_part:
                tags = self.tag_loader.load_tags(file_part, self.verbose)
                if isinstance(tags, list):
                    return process_wildcard_range(parsed_tag, tags)

        if parsed_tag.startswith('#'):
            tags = self.tag_loader.load_tags(parsed_tag.split('$$')[1], self.verbose)
            if isinstance(tags, list):
                return self.get_tag_choice(parsed_tag, tags)

        tags = self.tag_loader.load_tags(parsed_tag, self.verbose)
        
        if sequential and isinstance(tags, list) and tags:
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
            return self.resolve_wildcard_recursively(selected, self.global_seed)

        if groups:
            return self.get_tag_group_choice(parsed_tag, groups, tags)
        if tags:
            return self.get_tag_choice(parsed_tag, tags)
        
        return None 

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

class TagReplacer:
    def __init__(self, tag_selector):
        self.tag_selector = tag_selector
        self.wildcard_regex = re.compile(r'(__|<)(.*?)(__|>)')
        self.opts_regexp = re.compile(r'(?<=\[)(.*?)(?=\])')
        self.clean_regex = re.compile(r'\[clean:(.*?)\]', re.IGNORECASE)
        self.shuffle_regex = re.compile(r'\[shuffle:(.*?)\]', re.IGNORECASE)

    def replace_wildcard(self, matches):
        if not matches or len(matches.groups()) != 3:
            return ""
        match = matches.group(2)
        if not match:
            return ""
        
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

    def replace_functions(self, prompt):
        def _shuffle(match):
            content = match.group(1)
            items = [x.strip() for x in content.split(',')]
            random.shuffle(items)
            return ", ".join(items)
        
        def _clean(match):
            content = match.group(1)
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r',\s*,', ',', content)
            content = content.replace(' ,', ',')
            return content.strip(', ')

        p = self.shuffle_regex.sub(_shuffle, prompt)
        p = self.clean_regex.sub(_clean, p)
        return p

    def replace(self, prompt):
        p = self.wildcard_regex.sub(self.replace_wildcard, prompt)
        count = 0
        while p != prompt and count < 10:
            prompt = p
            p = self.wildcard_regex.sub(self.replace_wildcard, prompt)
            count += 1
        p = self.replace_functions(p)
        return p

class DynamicPromptReplacer:
    def __init__(self, seed):
        self.re_combinations = re.compile(r"\{([^{}]*)\}")
        self.seed = seed

    def replace_combinations(self, match):
        if not match:
            return ""
        content = match.group(1)
        
        if content.startswith('~'):
            content = content[1:]
            if '$$' in content: 
                 pass 
            else:
                variants = [s.strip() for s in content.split("|")]
                if not variants:
                    return ""
                return variants[self.seed % len(variants)]

        if '%' in content and '$$' not in content:
            parts = content.split('%', 1)
            try:
                chance = float(parts[0])
                options = parts[1].split('|')
                if random.random() * 100 < chance:
                    return options[0]
                elif len(options) > 1:
                    return random.choice(options[1:])
                else:
                    return ""
            except ValueError:
                pass 

        if '$$' in content:
            range_str, variants_str = content.split('$$', 1)
            variants = [s.strip() for s in variants_str.split("|")]
            low, high = parse_wildcard_range(range_str, len(variants))
            count = random.randint(low, high)
            if count <= 0:
                return ""
            selected = random.sample(variants, min(count, len(variants)))
            return ", ".join(selected)

        variants = [s.strip() for s in content.split("|")]
        if not variants:
            return ""
        return random.choice(variants)

    def replace(self, template):
        if not template:
            return ""
        return self.re_combinations.sub(self.replace_combinations, template)

class ConditionalReplacer:
    def __init__(self):
        self.regex = re.compile(
            r'\[if\s+([^:|\]]+?)\s*:\s*((?:(?!\[if).)*?)(?:\s*\|\s*((?:(?!\[if).)*?))?\]', 
            re.IGNORECASE | re.DOTALL
        )

    def replace(self, prompt):
        while True:
            match = self.regex.search(prompt)
            if not match:
                break
            
            full_tag = match.group(0)
            trigger_word = match.group(1).strip()
            true_text = match.group(2)
            false_text = match.group(3) if match.group(3) else ""

            if trigger_word.lower() in prompt.replace(full_tag, "").lower():
                replacement = true_text
            else:
                replacement = false_text
            
            prompt = prompt.replace(full_tag, replacement, 1)
        return prompt

class VariableReplacer:
    def __init__(self):
        self.assign_regex = re.compile(r'\$([a-zA-Z0-9_]+)\s*=\s*((?:\{.*?\})|(?:[^\s]+))', re.DOTALL)
        self.use_regex = re.compile(r'\$([a-zA-Z0-9_]+)((?:\.[a-zA-Z_]+)*)')
        self.variables = {}

    def load_globals(self, globals_dict):
        self.variables.update(globals_dict)

    def store_variables(self, text, tag_replacer, dynamic_replacer):
        def _replace_assign(match):
            var_name = match.group(1)
            raw_value = match.group(2)
            
            resolved_value = raw_value
            for _ in range(10): 
                prev_value = resolved_value
                resolved_value = tag_replacer.replace(resolved_value)
                resolved_value = dynamic_replacer.replace(resolved_value)
                if prev_value == resolved_value:
                    break
            
            self.variables[var_name] = resolved_value
            return "" 
        return self.assign_regex.sub(_replace_assign, text)

    def replace_variables(self, text):
        def _replace_use(match):
            var_name = match.group(1)
            methods_str = match.group(2) 
            
            value = self.variables.get(var_name)
            if value is None:
                return match.group(0)
            
            if methods_str:
                methods = methods_str.split('.')[1:]
                for method in methods:
                    if method == 'clean':
                        value = value.replace('_', ' ').replace('-', ' ')
                    elif method == 'upper':
                        value = value.upper()
                    elif method == 'lower':
                        value = value.lower()
                    elif method == 'title':
                        value = value.title()
                    elif method == 'capitalize':
                        value = value.capitalize()
                        
            return value
            
        return self.use_regex.sub(_replace_use, text)

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
        self.regex = re.compile(r'<lora:([^>:]+)(?::([0-9.]+))?>', re.IGNORECASE)
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

    def extract_and_load(self, text, model, clip, behavior):
        matches = self.regex.findall(text)
        clean_text = self.regex.sub("", text)
        lora_info_output = []
        extracted_tags_str = ""

        if model is None or clip is None:
            return clean_text, model, clip, ""

        for match in matches:
            name = match[0].strip()
            strength = float(match[1]) if match[1] else 1.0
            
            lora_path = folder_paths.get_full_path("loras", name)
            if not lora_path:
                lora_path = folder_paths.get_full_path("loras", f"{name}.safetensors")
            
            if lora_path:
                tags = self.get_lora_tags(lora_path)
                info_block = f"[LORA: {name}]\n"
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
                    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
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
        self.negative_tag = set()

    def strip_negative_tags(self, text):
        matches = re.findall(r'\*\*.*?\*\*', text)
        for match in matches:
            self.negative_tag.add(match.replace("**", ""))
            text = text.replace(match, "")
        return text

    def add_list(self, tags):
        for t in tags:
            self.negative_tag.add(t.strip())

    def get_negative_string(self):
        return ", ".join([t for t in self.negative_tag if t.strip()])

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
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_tags_behavior": (["Append to Prompt", "Disabled", "Prepend to Prompt"],),
                "llm_prompt_enhancer": (["No", "Yes"],),
                "llm_model": (llm_options,),
                "llm_temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "llm_max_tokens": ("INT", {"default": 400, "min": 100, "max": 4096}),
                "custom_system_prompt": ("STRING", {"multiline": True, "default": "", "placeholder": "Leave empty to use the default 'Creative Writer' persona..."}),
                "input_negative": ("STRING", {"multiline": True, "forceInput": True}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "danbooru_threshold": ("FLOAT", {"default": 0.75, "min": 0.1, "max": 1.0, "step": 0.05}),
                "danbooru_max_tags": ("INT", {"default": 15, "min": 1, "max": 50}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("model", "clip", "text", "negative_text", "width", "height", "lora_info")
    FUNCTION = "process"
    CATEGORY = "UmiAI"
    COLOR = "#322947"

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
            return None
        target_folder = os.path.join(folder_paths.models_dir, "llm")
        if not os.path.exists(target_folder):
            os.makedirs(target_folder, exist_ok=True)

        if model_choice in DOWNLOADABLE_MODELS:
            if not HF_HUB_AVAILABLE:
                return None
            model_info = DOWNLOADABLE_MODELS[model_choice]
            repo_id = model_info["repo_id"]
            filename = model_info["filename"]
            local_file_path = os.path.join(target_folder, filename)
            if os.path.exists(local_file_path):
                return local_file_path
            try:
                return hf_hub_download(repo_id=repo_id, filename=filename, local_dir=target_folder, local_dir_use_symlinks=False)
            except Exception:
                return None
        else:
            path = folder_paths.get_full_path("llm", model_choice)
            if not path:
                path = os.path.join(target_folder, model_choice)
            return path

    def run_llm_naturalizer(self, text, model_choice, temperature, max_tokens, custom_prompt):
        if not LLAMA_CPP_AVAILABLE:
            return text
        model_path = self.ensure_model_exists(model_choice)
        if not model_path:
            return text

        try:
            llm = Llama(model_path=model_path, n_ctx=4096, n_gpu_layers=0, verbose=False)
            default_system_prompt = "You are an AI image prompt assistant. Rewrite the following tags into detailed natural language."
            final_system_prompt = custom_prompt.strip() if custom_prompt.strip() else default_system_prompt
            user_input = f"Write a detailed visual description based on these tags: {text}"

            if "dolphin" in model_path.lower():
                prompt = f"<|im_start|>system\n{final_system_prompt}<|im_end|>\n<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
                output = llm.create_completion(prompt, stop=["<|im_end|>"], temperature=temperature, max_tokens=max_tokens)
                return output['choices'][0]['text'].strip()
            else:
                output = llm.create_chat_completion(
                    messages=[{"role": "system", "content": final_system_prompt}, {"role": "user", "content": user_input}],
                    temperature=temperature, max_tokens=max_tokens
                )
                return output['choices'][0]['message']['content'].strip()
        except Exception:
            return text

    # --- SAFETY HELPER ---
    def get_val(self, kwargs, key, default, value_type=None):
        val = kwargs.get(key, default)
        
        # Type enforcement
        if value_type and not isinstance(val, value_type):
            try:
                if value_type == int:
                    return int(val)
                if value_type == float:
                    return float(val)
                if value_type == str:
                    return str(val)
            except:
                return default
        
        return val

    def process(self, **kwargs):
        # 1. EXTRACT INPUTS SAFELY (CRASH PROOFING)
        text = self.get_val(kwargs, "text", "", str)
        seed = self.get_val(kwargs, "seed", 0, int)
        
        # Objects (Model/CLIP) - Handle None explicitly (standard Comfy behavior)
        model = kwargs.get("model", None)
        clip = kwargs.get("clip", None)

        # Settings with defaults
        width = self.get_val(kwargs, "width", 1024, int)
        height = self.get_val(kwargs, "height", 1024, int)
        lora_tags_behavior = self.get_val(kwargs, "lora_tags_behavior", "Append to Prompt", str)
        input_negative = self.get_val(kwargs, "input_negative", "", str)

        # LLM Settings
        llm_prompt_enhancer = self.get_val(kwargs, "llm_prompt_enhancer", "No", str)
        llm_model = self.get_val(kwargs, "llm_model", "None", str)
        llm_temperature = self.get_val(kwargs, "llm_temperature", 0.7, float)
        llm_max_tokens = self.get_val(kwargs, "llm_max_tokens", 400, int)
        custom_system_prompt = self.get_val(kwargs, "custom_system_prompt", "", str)

        # Danbooru Settings
        danbooru_threshold = self.get_val(kwargs, "danbooru_threshold", 0.75, float)
        danbooru_max_tags = self.get_val(kwargs, "danbooru_max_tags", 15, int)

        # ============================================================
        # CORE PROCESSING
        # ============================================================
        
        # Strip comments
        protected_text = text.replace('__#', '___UMI_HASH_PROTECT___').replace('<#', '<___UMI_HASH_PROTECT___')
        clean_lines = []
        for line in protected_text.splitlines():
            if '//' in line:
                line = line.split('//')[0]
            if '#' in line:
                line = line.split('#')[0]
            line = line.strip()
            if line:
                clean_lines.append(line)
        
        text = "\n".join(clean_lines)
        text = text.replace('___UMI_HASH_PROTECT___', '#').replace('<___UMI_HASH_PROTECT___', '<#')

        random.seed(seed)
        
        options = {
            'verbose': False, 
            'seed': seed,
            'ignore_paths': True
        }

        # Fix: Get all paths instead of just the internal one
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

        globals_dict = tag_loader.load_globals()
        variable_replacer.load_globals(globals_dict)

        prompt = text
        previous_prompt = ""
        iterations = 0
        tag_selector.clear_seeded_values()

        while previous_prompt != prompt and iterations < 50:
            previous_prompt = prompt
            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)
            prompt = tag_replacer.replace(prompt)
            prompt = dynamic_replacer.replace(prompt)
            prompt = danbooru_replacer.replace(prompt, danbooru_threshold, danbooru_max_tags)
            iterations += 1
            
        prompt = conditional_replacer.replace(prompt)
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

        if llm_prompt_enhancer == "Yes" and llm_model != "None":
            lora_regex = re.compile(r'<lora:[^>]+>')
            lora_tags = lora_regex.findall(prompt)
            clean_for_llm = lora_regex.sub("", prompt).strip()
            naturalized_text = self.run_llm_naturalizer(clean_for_llm, llm_model, llm_temperature, llm_max_tokens, custom_system_prompt)
            prompt = naturalized_text + " " + " ".join(lora_tags)

        prompt, final_model, final_clip, lora_info = lora_handler.extract_and_load(prompt, model, clip, lora_tags_behavior)

        generated_negatives = neg_gen.get_negative_string()
        final_negative = input_negative
        if generated_negatives:
            final_negative = f"{final_negative}, {generated_negatives}" if final_negative else generated_negatives
        if final_negative:
            final_negative = re.sub(r',\s*,', ',', final_negative).strip()

        prompt, settings = self.extract_settings(prompt)
        final_width = settings['width'] if settings['width'] > 0 else width
        final_height = settings['height'] if settings['height'] > 0 else height

        return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info)

NODE_CLASS_MAPPINGS = {"UmiAIWildcardNode": UmiAIWildcardNode}
NODE_DISPLAY_NAME_MAPPINGS = {"UmiAIWildcardNode": "UmiAI Wildcard Processor"}

# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@server.PromptServer.instance.routes.get("/umiapp/wildcards")
async def get_wildcards(request):
    all_paths = get_all_wildcard_paths()
    options = {'ignore_paths': True, 'verbose': False}
    loader = TagLoader(all_paths, options)
    loader.build_index()
    
    # 1. Get Wildcards
    wildcards = sorted(list(loader.files_index))
    
    # 2. Get LoRAs
    loras = folder_paths.get_filename_list("loras")
    loras = sorted(loras) if loras else []

    return web.json_response({
        "wildcards": wildcards,
        "loras": loras
    })

@server.PromptServer.instance.routes.post("/umiapp/refresh")
async def refresh_wildcards(request):
    """Refreshes the global cache and returns the new list."""
    GLOBAL_CACHE.clear()
    
    # Fix: Nuke the Index Cache so it rebuilds next time
    GLOBAL_INDEX['built'] = False 
    GLOBAL_INDEX['files'] = set()
    GLOBAL_INDEX['entries'] = {}
    
    all_paths = get_all_wildcard_paths()
    options = {'ignore_paths': True, 'verbose': False}
    loader = TagLoader(all_paths, options)
    loader.build_index() # Rebuild immediately
    
    wildcards = sorted(list(loader.files_index))
    loras = folder_paths.get_filename_list("loras")
    loras = sorted(loras) if loras else []
    
    return web.json_response({
        "status": "success", 
        "count": len(wildcards),
        "wildcards": wildcards,
        "loras": loras
    })