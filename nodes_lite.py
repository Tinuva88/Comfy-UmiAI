import os
import random
import re
import yaml
import glob
import json
import csv
import fnmatch
import gc
from collections import Counter, OrderedDict
import folder_paths
import comfy.sd
import comfy.utils
import torch
from safetensors import safe_open
from datetime import datetime

# Import shared utilities
from .shared_utils import (
    escape_unweighted_colons, parse_wildcard_weight, log_prompt_to_history,
    LogicEvaluator, DynamicPromptReplacer, VariableReplacer, NegativePromptGenerator,
    ConditionalReplacer, TagLoaderBase, TagSelectorBase, LoRAHandlerBase, TagReplacerBase
)

# ==============================================================================
# GLOBAL CACHE & SETUP (LITE VERSION - ISOLATED FROM FULL NODE)
# ==============================================================================
GLOBAL_CACHE_LITE = {}
GLOBAL_INDEX_LITE = {'built': False, 'files': set(), 'entries': {}, 'tags': set()}

# Fix 12: File modification time cache to skip rescanning unchanged files
FILE_MTIME_CACHE_LITE = {}

# LRU CACHE (ISOLATED FROM FULL NODE)
LORA_MEMORY_CACHE_LITE = OrderedDict()

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def get_all_wildcard_paths():
    """Get all wildcard paths - same as Full node for consistency"""
    # Import the shared function
    from .shared_utils import get_all_wildcard_paths as shared_get_paths
    return shared_get_paths()

# Note: escape_unweighted_colons and log_prompt_to_history are imported from shared_utils
# Keeping lite-specific get_all_wildcard_paths() since it only searches internal wildcards

# ==============================================================================
# TAG LOADER (Lite Version - No Danbooru)
# ==============================================================================
class TagLoader(TagLoaderBase):
    def __init__(self, wildcard_paths, options):
        super().__init__(wildcard_paths, options)
        self.build_index()

    def build_index(self):
        if GLOBAL_INDEX_LITE['built']:
            self.files_index = GLOBAL_INDEX_LITE['files']
            self.umi_tags = GLOBAL_INDEX_LITE['tags']
            return

        for wildcard_path in self.wildcard_paths:
            if not os.path.exists(wildcard_path):
                continue

            for root, dirs, files in os.walk(wildcard_path):
                for file in files:
                    if file.endswith(('.txt', '.yaml', '.yml', '.csv')):
                        name_without_ext = os.path.splitext(file)[0]
                        self.files_index.add(name_without_ext)

                        if file.endswith(('.yaml', '.yml')):
                            full_path = os.path.join(root, file)
                            self.scan_yaml_for_tags(full_path)

        GLOBAL_INDEX_LITE['built'] = True
        GLOBAL_INDEX_LITE['files'] = self.files_index
        GLOBAL_INDEX_LITE['tags'] = self.umi_tags

    def scan_yaml_for_tags(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                print(f"[UmiAI Lite DEBUG] Skipping {os.path.basename(file_path)}: not a dict")
                return

            tags_found = []
            for entry_key, entry_data in data.items():
                if not isinstance(entry_data, dict):
                    continue

                entry_tags = entry_data.get('Tags', [])
                if not isinstance(entry_tags, list):
                    entry_tags = [str(entry_tags)]

                for tag in entry_tags:
                    tag = str(tag).strip()
                    if tag:
                        self.umi_tags.add(tag)
                        tags_found.append(tag)
                        GLOBAL_INDEX_LITE['entries'].setdefault(tag.lower(), []).append({
                            'file': file_path,
                            'entry_key': entry_key,
                            'data': entry_data
                        })

            if tags_found:
                print(f"[UmiAI Lite DEBUG] Scanned {os.path.basename(file_path)}: found tags {tags_found[:10]}")
        except yaml.YAMLError as e:
            print(f"[UmiAI Lite] ERROR: Malformed YAML file '{os.path.basename(file_path)}': {e}")
            print(f"[UmiAI Lite] Skipping file. Please fix YAML syntax and refresh wildcards.")
        except UnicodeDecodeError as e:
            print(f"[UmiAI Lite] ERROR: Encoding issue in '{os.path.basename(file_path)}': {e}")
            print(f"[UmiAI Lite] File must be UTF-8 encoded. Skipping file.")
        except Exception as e:
            print(f"[UmiAI Lite] WARNING: Error scanning YAML '{os.path.basename(file_path)}': {e}")
            print(f"[UmiAI Lite] Skipping file and continuing...")

    def load_globals(self):
        globals_dict = {}
        for wildcard_path in self.wildcard_paths:
            globals_file = os.path.join(wildcard_path, "globals.yaml")
            if os.path.exists(globals_file):
                try:
                    with open(globals_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)

                    if isinstance(data, dict):
                        for k, v in data.items():
                            if k.startswith('$'):
                                globals_dict[k] = v
                except yaml.YAMLError as e:
                    print(f"[UmiAI Lite] ERROR: Malformed globals.yaml: {e}")
                    print(f"[UmiAI Lite] Global variables will not be loaded. Please fix YAML syntax.")
                except UnicodeDecodeError as e:
                    print(f"[UmiAI Lite] ERROR: Encoding issue in globals.yaml: {e}")
                except Exception as e:
                    print(f"[UmiAI Lite] WARNING: Error loading globals.yaml: {e}")
        return globals_dict

    def load_from_file(self, file_key):
        cache_key = f"file_{file_key}"

        # Fix 12: Check modification time before using cached data
        if cache_key in GLOBAL_CACHE_LITE:
            cached_path = FILE_MTIME_CACHE_LITE.get(cache_key, {}).get('path')
            if cached_path and os.path.exists(cached_path):
                current_mtime = os.path.getmtime(cached_path)
                cached_mtime = FILE_MTIME_CACHE_LITE.get(cache_key, {}).get('mtime', 0)
                if current_mtime == cached_mtime:
                    return GLOBAL_CACHE_LITE[cache_key]
                else:
                    # File has been modified, invalidate cache
                    if self.verbose:
                        print(f"[UmiAI Lite] File '{file_key}' modified, reloading...")

        file_key_lower = file_key.lower()
        for wildcard_path in self.wildcard_paths:
            for root, dirs, files in os.walk(wildcard_path):
                for file in files:
                    name_without_ext = os.path.splitext(file)[0]
                    if name_without_ext.lower() == file_key_lower:
                        full_path = os.path.join(root, file)
                        result = self.load_file(full_path)
                        GLOBAL_CACHE_LITE[cache_key] = result
                        # Cache modification time
                        FILE_MTIME_CACHE_LITE[cache_key] = {
                            'path': full_path,
                            'mtime': os.path.getmtime(full_path)
                        }
                        return result

        GLOBAL_CACHE_LITE[cache_key] = []
        return []

    def load_prompt_file(self, file_key):
        """Phase 6: Load entire .txt file content as a prompt (no parsing)"""
        file_key_lower = file_key.lower()
        for wildcard_path in self.wildcard_paths:
            for root, dirs, files in os.walk(wildcard_path):
                for file in files:
                    name_without_ext = os.path.splitext(file)[0]
                    if name_without_ext.lower() == file_key_lower and file.endswith('.txt'):
                        full_path = os.path.join(root, file)
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                content = f.read().strip()
                            return content
                        except Exception as e:
                            if self.verbose:
                                print(f"[UmiAI Lite] Error reading prompt file {full_path}: {e}")
                            return None
        return None

    def load_file(self, file_path):
        try:
            if file_path.endswith('.txt'):
                return self.load_txt_file(file_path)
            elif file_path.endswith(('.yaml', '.yml')):
                return self.load_yaml_file(file_path)
            elif file_path.endswith('.csv'):
                return self.load_csv_file(file_path)
        except Exception as e:
            if self.verbose:
                print(f"[UmiAI Lite] Error loading file {file_path}: {e}")
        return []

    def load_txt_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        # Parse using shared utility function
        entries = []
        for line in lines:
            parsed = parse_wildcard_weight(line)
            entries.append(parsed)

        return entries

    def load_yaml_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                print(f"[UmiAI Lite] WARNING: YAML file '{os.path.basename(file_path)}' does not contain a dictionary. Skipping.")
                return []

            entries = []
            for entry_key, entry_data in data.items():
                if isinstance(entry_data, dict):
                    prompts = entry_data.get('Prompts', [])
                    if isinstance(prompts, str):
                        prompts = [prompts]

                    for prompt in prompts:
                        entries.append({
                            'value': prompt,
                            'prefix': entry_data.get('Prefix', [''])[0] if isinstance(entry_data.get('Prefix'), list) else '',
                            'suffix': entry_data.get('Suffix', [''])[0] if isinstance(entry_data.get('Suffix'), list) else '',
                            'neg_prefix': entry_data.get('Neg_Prefix', [''])[0] if isinstance(entry_data.get('Neg_Prefix'), list) else '',
                            'neg_suffix': entry_data.get('Neg_Suffix', [''])[0] if isinstance(entry_data.get('Neg_Suffix'), list) else '',
                        })

            return entries
        except yaml.YAMLError as e:
            print(f"[UmiAI Lite] ERROR: Malformed YAML file '{os.path.basename(file_path)}': {e}")
            print(f"[UmiAI Lite] Returning empty list. Please fix YAML syntax.")
            return []
        except UnicodeDecodeError as e:
            print(f"[UmiAI Lite] ERROR: Encoding issue in '{os.path.basename(file_path)}': {e}")
            return []
        except Exception as e:
            print(f"[UmiAI Lite] WARNING: Error loading YAML '{os.path.basename(file_path)}': {e}")
            return []

    def load_csv_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        entries = []
        for row in rows:
            merged = ', '.join([f"{k}: {v}" for k, v in row.items() if v])
            entries.append({'value': merged, 'csv_row': row})

        return entries

# ==============================================================================
# TAG SELECTOR (Lite Version)
# ==============================================================================
class TagSelector(TagSelectorBase):
    def __init__(self, tag_loader, options):
        super().__init__(tag_loader, options)
        # Use rng instead of random for consistency with base class
        self.random = self.rng
        
        self.prefixes = []
        self.suffixes = []
        self.neg_prefixes = []
        self.neg_suffixes = []

    def clear_seeded_values(self):
        self.seeded_values.clear()

    def update_variables(self, variables):
        self.variables = variables

    def _weighted_sample(self, entries, count):
        """Fix 13: Weighted random selection based on entry weights"""
        if count >= len(entries):
            return entries

        # Build cumulative weight distribution
        weights = [entry.get('weight', 1.0) for entry in entries]
        total_weight = sum(weights)

        selected = []
        available_indices = list(range(len(entries)))

        for _ in range(count):
            if not available_indices:
                break

            # Calculate weights for remaining entries
            available_weights = [weights[i] for i in available_indices]
            available_total = sum(available_weights)

            # Pick random value in weight range
            rand_val = self.random.random() * available_total
            cumsum = 0

            for idx, i in enumerate(available_indices):
                cumsum += weights[i]
                if rand_val <= cumsum:
                    selected.append(entries[i])
                    available_indices.pop(idx)
                    break

        return selected

    def select(self, tag_key, count=1, logic_filter=None, sequential=False):
        entries = self.tag_loader.load_from_file(tag_key)

        if not entries:
            # Fix 11: Better error messages - provide helpful feedback for missing wildcards
            error_msg = f"[WILDCARD_NOT_FOUND: {tag_key}]"
            print(f"[UmiAI Lite] WARNING: Wildcard file '{tag_key}' not found or is empty.")
            return error_msg

        if tag_key in self.seeded_values and not logic_filter and not sequential:
            return self.seeded_values[tag_key]

        # Phase 6: Sequential selection - use seed to pick same index
        if sequential and entries:
            idx = self.seed % len(entries)
            selected_entry = entries[idx]
            result = selected_entry['value']
            self.seeded_values[tag_key] = result
            return result

        # Phase 5: Filter entries by logic expression if provided
        if logic_filter:
            evaluator = LogicEvaluator(logic_filter, self.variables)
            filtered_entries = []
            for entry in entries:
                # Build tag context from entry tags
                tag_dict = {tag.lower(): True for tag in entry.get('tags', [])}
                if evaluator.evaluate(tag_dict):
                    filtered_entries.append(entry)

            if not filtered_entries:
                error_msg = f"[NO_MATCHES: {logic_filter} in {tag_key}]"
                print(f"[UmiAI Lite] WARNING: No entries in '{tag_key}' matched logic '{logic_filter}'.")
                return error_msg

            entries = filtered_entries

        # Fix 13: Weighted selection - use weights if present
        has_weights = any(entry.get('weight', 1.0) != 1.0 for entry in entries)

        if has_weights:
            # Weighted random selection
            selected_entries = self._weighted_sample(entries, min(count, len(entries)))
        else:
            # Normal random selection
            selected_entries = self.random.sample(entries, min(count, len(entries)))

        result_parts = []
        for entry in selected_entries:
            result_parts.append(entry['value'])

            if entry.get('prefix'):
                self.prefixes.append(entry['prefix'])
            if entry.get('suffix'):
                self.suffixes.append(entry['suffix'])
            if entry.get('neg_prefix'):
                self.neg_prefixes.append(entry['neg_prefix'])
            if entry.get('neg_suffix'):
                self.neg_suffixes.append(entry['neg_suffix'])

            # CSV variable injection: if entry has csv_row, inject columns as variables
            if entry.get('csv_row'):
                csv_row = entry['csv_row']
                for column_name, column_value in csv_row.items():
                    var_name = f"${column_name}"
                    if var_name not in self.variables:
                        self.variables[var_name] = column_value

        result = ", ".join(result_parts)
        self.seeded_values[tag_key] = result
        return result

    def select_by_tags(self, logic_expression):
        cache_key = f"logic_{logic_expression}"
        if cache_key in self.seeded_values:
            return self.seeded_values[cache_key]

        evaluator = LogicEvaluator(logic_expression, self.variables)

        # Debug logging - VERBOSE
        total_tags = len(GLOBAL_INDEX_LITE['entries'])
        print(f"[UmiAI Lite DEBUG] select_by_tags('{logic_expression}'): {total_tags} tags indexed, GLOBAL_INDEX_LITE['built']={GLOBAL_INDEX_LITE['built']}")
        print(f"[UmiAI Lite DEBUG] GLOBAL_INDEX_LITE id: {id(GLOBAL_INDEX_LITE)}, entries id: {id(GLOBAL_INDEX_LITE['entries'])}")
        if total_tags > 0:
            print(f"[UmiAI Lite DEBUG] Available tags: {list(GLOBAL_INDEX_LITE['entries'].keys())[:20]}")
        else:
            print(f"[UmiAI Lite DEBUG] WARNING: entries dict is EMPTY! umi_tags has {len(GLOBAL_INDEX_LITE.get('tags', set()))} items")
        import sys
        sys.stdout.flush()

        matching_entries = []
        debug_count = 0
        total_entries_checked = 0
        for tag_lower, entry_list in GLOBAL_INDEX_LITE['entries'].items():
            total_entries_checked += len(entry_list)
            for entry_info in entry_list:
                entry_data = entry_info['data']
                entry_tags = entry_data.get('Tags', [])

                if not isinstance(entry_tags, list):
                    entry_tags = [str(entry_tags)]

                tag_dict = {str(t).strip().lower(): True for t in entry_tags}

                # Debug: show first few evaluations
                result = evaluator.evaluate(tag_dict)
                if debug_count < 5:
                    print(f"[UmiAI Lite DEBUG] Checking entry '{entry_info.get('entry_key', 'unknown')}': tag_dict={tag_dict}, expression='{logic_expression}', result={result}")
                    debug_count += 1
                    
                if result:
                    prompts = entry_data.get('Prompts', [])
                    if isinstance(prompts, str):
                        prompts = [prompts]

                    for prompt in prompts:
                        matching_entries.append({
                            'value': prompt,
                            'prefix': entry_data.get('Prefix', [''])[0] if isinstance(entry_data.get('Prefix'), list) else '',
                            'suffix': entry_data.get('Suffix', [''])[0] if isinstance(entry_data.get('Suffix'), list) else '',
                            'neg_prefix': entry_data.get('Neg_Prefix', [''])[0] if isinstance(entry_data.get('Neg_Prefix'), list) else '',
                            'neg_suffix': entry_data.get('Neg_Suffix', [''])[0] if isinstance(entry_data.get('Neg_Suffix'), list) else '',
                        })

        if not matching_entries:
            # Fix 11: Better error messages - show which logic expression failed to match
            error_msg = f"[NO_MATCHES: {logic_expression}]"
            print(f"[UmiAI Lite DEBUG] Loop complete: checked {total_entries_checked} entries, found {len(matching_entries)} matches for '{logic_expression}'")
            print(f"[UmiAI Lite] WARNING: No YAML entries matched logic expression '{logic_expression}'.")
            sys.stdout.flush()
            self.seeded_values[cache_key] = error_msg
            return error_msg

        selected = self.random.choice(matching_entries)

        if selected.get('prefix'):
            self.prefixes.append(selected['prefix'])
        if selected.get('suffix'):
            self.suffixes.append(selected['suffix'])
        if selected.get('neg_prefix'):
            self.neg_prefixes.append(selected['neg_prefix'])
        if selected.get('neg_suffix'):
            self.neg_suffixes.append(selected['neg_suffix'])

        result = selected['value']
        self.seeded_values[cache_key] = result
        return result

    def get_prefixes_and_suffixes(self):
        return {
            'prefixes': self.prefixes,
            'suffixes': self.suffixes,
            'neg_prefixes': self.neg_prefixes,
            'neg_suffixes': self.neg_suffixes
        }


# ==============================================================================
# TAG REPLACER
# ==============================================================================
class TagReplacer(TagReplacerBase):
    def __init__(self, tag_selector):
        super().__init__(tag_selector)

    def replace(self, text):
        # Escape mechanism: Replace \__ and \{ with placeholders to preserve literal syntax
        ESCAPED_WILDCARD = "___ESCAPED_WILDCARD___"
        ESCAPED_CHOICE = "___ESCAPED_CHOICE___"

        text = text.replace(r'\__', ESCAPED_WILDCARD)
        text = text.replace(r'\{', ESCAPED_CHOICE)

        pattern = r'__(\d+)-(\d+)\$\$([^_]+)__'

        def range_replacer(match):
            min_val = int(match.group(1))
            max_val = int(match.group(2))
            tag_key = match.group(3)

            count = self.tag_selector.random.randint(min_val, max_val)
            return self.tag_selector.select(tag_key, count)

        text = re.sub(pattern, range_replacer, text)

        pattern_logic = r'__\[([^\]]+)\]__'

        def logic_replacer(match):
            logic_expr = match.group(1)
            return self.tag_selector.select_by_tags(logic_expr)

        text = re.sub(pattern_logic, logic_replacer, text)

        pattern_angle = r'<\[([^\]]+)\]>'
        text = re.sub(pattern_angle, logic_replacer, text)

        # Phase 5: Support __filename[logic]__ syntax for .txt wildcards with logic
        pattern_file_logic = r'__([a-zA-Z0-9_-]+)\[([^\]]+)\]__'

        def file_logic_replacer(match):
            filename = match.group(1)
            logic_expr = match.group(2)
            return self.tag_selector.select(filename, count=1, logic_filter=logic_expr)

        text = re.sub(pattern_file_logic, file_logic_replacer, text)

        # Phase 6: Support __@filename__ syntax to load full file content as prompt
        pattern_prompt_file = r'__@([a-zA-Z0-9_-]+)__'

        def prompt_file_replacer(match):
            filename = match.group(1)
            try:
                file_content = self.tag_selector.tag_loader.load_prompt_file(filename)
                if file_content:
                    return file_content
                else:
                    return f"[PROMPT_FILE_NOT_FOUND: {filename}]"
            except Exception as e:
                return f"[PROMPT_FILE_ERROR: {filename}: {str(e)}]"

        text = re.sub(pattern_prompt_file, prompt_file_replacer, text)

        pattern_simple = r'__([^_]+)__'

        def simple_replacer(match):
            tag_key = match.group(1)
            # Phase 6: Support ~sequential prefix
            sequential = False
            if tag_key.startswith('~'):
                sequential = True
                tag_key = tag_key[1:]
            # Phase 6: Support @prompt file prefix
            if tag_key.startswith('@'):
                try:
                    file_content = self.tag_selector.tag_loader.load_prompt_file(tag_key[1:])
                    if file_content:
                        return file_content
                    else:
                        return f"[PROMPT_FILE_NOT_FOUND: {tag_key[1:]}]"
                except Exception as e:
                    return f"[PROMPT_FILE_ERROR: {tag_key[1:]}: {str(e)}]"
            return self.tag_selector.select(tag_key, sequential=sequential)

        text = re.sub(pattern_simple, simple_replacer, text)

        # Process function tags ([shuffle:], [clean:])
        text = self.replace_functions(text)

        # Restore escaped syntax
        text = text.replace(ESCAPED_WILDCARD, '__')
        text = text.replace(ESCAPED_CHOICE, '{')

        return text




# ==============================================================================
# LORA HANDLER
# ==============================================================================
class LoRAHandler(LoRAHandlerBase):
    def __init__(self):
        super().__init__()
    
    def extract_and_load(self, text, model, clip, lora_behavior, cache_limit):
        lora_pattern = r'<lora:([^:>]+):([0-9.]+)>'
        lora_matches = re.findall(lora_pattern, text)

        lora_info_parts = []

        if not lora_matches:
            return text, model, clip, ""

        for lora_name, strength_str in lora_matches:
            # Input validation: clamp strength to valid range
            try:
                strength = float(strength_str)
                if strength < 0.0 or strength > 5.0:
                    print(f"[UmiAI Lite] WARNING: LoRA strength {strength} for '{lora_name}' is out of range. Clamping to [0.0, 5.0].")
                    strength = max(0.0, min(5.0, strength))
            except ValueError:
                print(f"[UmiAI Lite] ERROR: Invalid LoRA strength '{strength_str}' for '{lora_name}'. Using 1.0 as default.")
                strength = 1.0

            if model is not None and clip is not None:
                model, clip = self.load_lora(model, clip, lora_name, strength, cache_limit)
                lora_info_parts.append(f"{lora_name}:{strength}")

            if lora_behavior == "Disabled":
                text = re.sub(r'<lora:[^>]+>', '', text)
            elif lora_behavior == "Append to Prompt":
                lora_tags = self.extract_lora_tags(lora_name)
                if lora_tags:
                    text = text + ", " + lora_tags
                text = re.sub(r'<lora:[^>]+>', '', text)
            elif lora_behavior == "Prepend to Prompt":
                lora_tags = self.extract_lora_tags(lora_name)
                if lora_tags:
                    text = lora_tags + ", " + text
                text = re.sub(r'<lora:[^>]+>', '', text)

        lora_info = ", ".join(lora_info_parts) if lora_info_parts else ""

        return text, model, clip, lora_info

    def load_lora(self, model, clip, lora_name, strength, cache_limit):
        cache_key = f"{lora_name}_{strength}"

        # Fix memory leak: skip caching entirely when limit is 0
        if cache_limit > 0:
            if cache_key in LORA_MEMORY_CACHE_LITE:
                LORA_MEMORY_CACHE_LITE.move_to_end(cache_key)
                cached = LORA_MEMORY_CACHE_LITE[cache_key]
                return cached['model'], cached['clip']

        lora_path = folder_paths.get_full_path("loras", lora_name)

        if lora_path is None:
            all_loras = folder_paths.get_filename_list("loras")
            for lora_file in all_loras:
                lora_base = os.path.splitext(os.path.basename(lora_file))[0]
                if lora_base.lower() == lora_name.lower():
                    lora_path = folder_paths.get_full_path("loras", lora_file)
                    break

        if lora_path is None:
            print(f"[UmiAI Lite] LoRA not found: {lora_name}")
            return model, clip

        try:
            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

            has_z_image = any('to_k_lora.down.weight' in key for key in lora.keys())

            if has_z_image:
                print(f"[UmiAI Lite] Detected Z-Image format LoRA: {lora_name}. Applying QKV fusion patch...")
                lora = self.apply_qkv_fusion(lora)

            model_patched, clip_patched = comfy.sd.load_lora_for_models(model, clip, lora, strength, strength)

            # Only cache if cache_limit > 0
            if cache_limit > 0:
                LORA_MEMORY_CACHE_LITE[cache_key] = {'model': model_patched, 'clip': clip_patched}
                LORA_MEMORY_CACHE_LITE.move_to_end(cache_key)

                if len(LORA_MEMORY_CACHE_LITE) > cache_limit:
                    oldest_key = next(iter(LORA_MEMORY_CACHE_LITE))
                    del LORA_MEMORY_CACHE_LITE[oldest_key]
                    gc.collect()
                    torch.cuda.empty_cache()

            return model_patched, clip_patched

        except Exception as e:
            print(f"[UmiAI Lite] Error loading LoRA {lora_name}: {e}")
            return model, clip

    def apply_qkv_fusion(self, lora_dict):
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
                    fused_weight = torch.cat([q_weight, k_weight, v_weight], dim=0)
                    fused_dict[new_key] = fused_weight
                else:
                    fused_dict[key] = q_weight
            else:
                fused_dict[key] = lora_dict[key]

        return fused_dict

    def extract_lora_tags(self, lora_name):
        lora_path = folder_paths.get_full_path("loras", lora_name)

        if lora_path is None:
            all_loras = folder_paths.get_filename_list("loras")
            for lora_file in all_loras:
                lora_base = os.path.splitext(os.path.basename(lora_file))[0]
                if lora_base.lower() == lora_name.lower():
                    lora_path = folder_paths.get_full_path("loras", lora_file)
                    break

        if lora_path is None or not lora_path.endswith('.safetensors'):
            return ""

        try:
            with safe_open(lora_path, framework="pt", device="cpu") as f:
                metadata = f.metadata()

            tags_value = metadata.get('ss_tag_frequency', None)
            if not tags_value:
                return ""

            tag_data = json.loads(tags_value)

            all_tags = []
            for dataset_tags in tag_data.values():
                all_tags.extend(dataset_tags.items())

            sorted_tags = sorted(all_tags, key=lambda x: x[1], reverse=True)

            top_tags = [tag for tag, count in sorted_tags[:20]]

            return ", ".join(top_tags)

        except Exception as e:
            return ""

# ==============================================================================
# MAIN NODE CLASS (LITE VERSION)
# ==============================================================================
class UmiAIWildcardNodeLite:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                # Standard Connections
                "model": ("MODEL",),
                "clip": ("CLIP",),

                # Basic Settings
                "lora_tags_behavior": (["Append to Prompt", "Disabled", "Prepend to Prompt"], {"default": "Append to Prompt"}),
                "lora_cache_limit": ("INT", {"default": 5, "min": 0, "max": 50, "step": 1}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "input_negative": ("STRING", {"multiline": True, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "INT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "text", "negative_text", "width", "height", "lora_info", "input_text", "input_negative")
    FUNCTION = "process"
    CATEGORY = "UmiAI"
    COLOR = "#47325e"

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
        text = self.get_val(kwargs, "text", "", str)
        seed = self.get_val(kwargs, "seed", 0, int)

        model = kwargs.get("model", None)
        clip = kwargs.get("clip", None)

        width = self.get_val(kwargs, "width", 1024, int)
        height = self.get_val(kwargs, "height", 1024, int)

        # Fix: Ensure width/height are never 0
        if width <= 0:
            width = 1024
        if height <= 0:
            height = 1024

        lora_tags_behavior = self.get_val(kwargs, "lora_tags_behavior", "Append to Prompt", str)
        lora_cache_limit = self.get_val(kwargs, "lora_cache_limit", 5, int)
        input_negative = self.get_val(kwargs, "input_negative", "", str)

        # ============================================================
        # CORE PROCESSING
        # ============================================================

        # Strip comments
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
            'ignore_paths': True
        }

        all_wildcard_paths = get_all_wildcard_paths()
        tag_loader = TagLoader(all_wildcard_paths, options)

        tag_selector = TagSelector(tag_loader, options)
        neg_gen = NegativePromptGenerator()

        tag_replacer = TagReplacer(tag_selector)
        dynamic_replacer = DynamicPromptReplacer(seed)
        conditional_replacer = ConditionalReplacer()
        variable_replacer = VariableReplacer()
        lora_handler = LoRAHandler()

        # Load globals
        globals_dict = tag_loader.load_globals()
        variable_replacer.load_globals(globals_dict)

        prompt = text
        previous_prompt = ""
        iterations = 0
        prompt_history = []  # Track prompts for cycle detection
        tag_selector.clear_seeded_values()

        # Main processing loop
        while previous_prompt != prompt and iterations < 50:
            # Cycle detection: check if we've seen this exact prompt before
            if prompt in prompt_history:
                print(f"[UmiAI Lite] WARNING: Cycle detected in prompt processing. Breaking loop to prevent infinite recursion.")
                print(f"[UmiAI Lite] Problematic prompt fragment: {prompt[:100]}...")
                break

            prompt_history.append(previous_prompt)
            previous_prompt = prompt

            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)
            prompt = tag_replacer.replace(prompt)
            prompt = dynamic_replacer.replace(prompt)
            iterations += 1

        # Warn if we hit the iteration limit
        if iterations >= 50:
            print(f"[UmiAI Lite] WARNING: Reached maximum processing iterations (50). Possible recursive wildcards or variables.")

        # Apply conditional logic
        prompt = conditional_replacer.replace(prompt, variable_replacer.variables)

        # Add prefixes and suffixes
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

        # Strip negative tags from prompt
        prompt = neg_gen.strip_negative_tags(prompt)

        # Cleanup
        prompt = re.sub(r',\s*,', ',', prompt)
        prompt = re.sub(r'\s+', ' ', prompt).strip().strip(',')

        # Extract and load LoRAs
        prompt, final_model, final_clip, lora_info = lora_handler.extract_and_load(prompt, model, clip, lora_tags_behavior, lora_cache_limit)

        # Generate final negative prompt
        generated_negatives = neg_gen.get_negative_string()
        final_negative = input_negative
        if generated_negatives:
            final_negative = f"{final_negative}, {generated_negatives}" if final_negative else generated_negatives
        if final_negative:
            final_negative = re.sub(r',\s*,', ',', final_negative).strip()

        # Extract settings
        prompt, settings = self.extract_settings(prompt)
        final_width = settings['width'] if settings['width'] > 0 else width
        final_height = settings['height'] if settings['height'] > 0 else height

        # Escape colons that aren't part of weight syntax to prevent SD misinterpretation
        prompt = escape_unweighted_colons(prompt)
        final_negative = escape_unweighted_colons(final_negative)

        # Phase 8: Log prompt to history
        log_prompt_to_history(prompt, final_negative, seed)

        return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info, text, input_negative)

NODE_CLASS_MAPPINGS = {"UmiAIWildcardNodeLite": UmiAIWildcardNodeLite}
NODE_DISPLAY_NAME_MAPPINGS = {"UmiAIWildcardNodeLite": "UmiAI Wildcard Processor (Lite)"}
