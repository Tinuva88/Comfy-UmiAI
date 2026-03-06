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
    escape_unweighted_colons, parse_wildcard_weight, log_prompt_to_history, expand_prompt_files,
    LogicEvaluator, DynamicPromptReplacer, VariableReplacer, NegativePromptGenerator,
    ConditionalReplacer, TagLoaderBase, TagSelectorBase, LoRAHandlerBase, TagReplacerBase,
    CharacterReplacer, resolve_lora_alias, strip_prompt_comments
)

# Import UMI_SETTINGS from main nodes for syncing toggle
from .nodes import UMI_SETTINGS, umi_debug_print

# ==============================================================================
# GLOBAL TEXT CACHE FOR BYPASS NODE
# Stores the last generated text from each wildcard processor node
WILDCARD_TEXT_CACHE = {}

# ==============================================================================
# GLOBAL CACHE & SETUP (LITE VERSION - ISOLATED FROM FULL NODE)
# ==============================================================================
GLOBAL_CACHE_LITE = {}
GLOBAL_INDEX_LITE = {'built': False, 'files': set(), 'entries': {}, 'tags': set(), 'entry_names': {}}

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

def _get_execution_blocker_class():
    """Try to resolve ComfyUI's ExecutionBlocker without hard dependency."""
    try:
        from comfy.execution import ExecutionBlocker
        return ExecutionBlocker
    except Exception:
        pass
    try:
        from comfy.utils import ExecutionBlocker
        return ExecutionBlocker
    except Exception:
        return None

# Note: escape_unweighted_colons and log_prompt_to_history are imported from shared_utils
# Keeping lite-specific get_all_wildcard_paths() since it only searches internal wildcards

# ==============================================================================
# TAG LOADER (Lite Version - No Danbooru)
# ==============================================================================
class TagLoader(TagLoaderBase):
    def __init__(self, wildcard_paths, options):
        super().__init__(wildcard_paths, options)
        self.use_folder_paths = options.get('use_folder_paths', False)
        self.build_index()

    def build_index(self):
        # Check if cache was built with a different use_folder_paths setting
        cached_setting = GLOBAL_INDEX_LITE.get('use_folder_paths', None)
        full_rebuild = False

        if GLOBAL_INDEX_LITE['built'] and cached_setting == self.use_folder_paths:
            # Cache exists and setting matches, but we still need to scan YAML files
            # for potential modifications (scan_yaml_for_tags handles mtime checking)
            self.files_index = GLOBAL_INDEX_LITE['files']
            self.umi_tags = GLOBAL_INDEX_LITE['tags']
            self.entry_names = GLOBAL_INDEX_LITE.get('entry_names', {})
            # Rescan YAML files to check for modifications
            for wildcard_path in self.wildcard_paths:
                if not os.path.exists(wildcard_path):
                    continue
                for root, dirs, files in os.walk(wildcard_path):
                    for file in files:
                        if file.endswith(('.yaml', '.yml')):
                            full_path = os.path.join(root, file)
                            self.scan_yaml_for_tags(full_path)
            return

        # Rebuild if setting changed or first build
        if GLOBAL_INDEX_LITE['built'] and cached_setting != self.use_folder_paths:
            umi_debug_print(f"[UmiAI Lite] Rebuilding index: use_folder_paths changed from {cached_setting} to {self.use_folder_paths}")
            GLOBAL_INDEX_LITE['built'] = False  # Force rebuild
            full_rebuild = True

        # Reset for fresh build
        self.files_index = set()
        self.umi_tags = set()
        self.entry_names = {}
        if full_rebuild:
            GLOBAL_INDEX_LITE['entries'] = {}
            GLOBAL_INDEX_LITE['entry_names'] = {}
            # Clear YAML mtime cache on full rebuild
            yaml_keys = [k for k in FILE_MTIME_CACHE_LITE.keys() if k.startswith('yaml_tags_')]
            for k in yaml_keys:
                del FILE_MTIME_CACHE_LITE[k]

        for wildcard_path in self.wildcard_paths:
            if not os.path.exists(wildcard_path):
                continue

            for root, dirs, files in os.walk(wildcard_path):
                for file in files:
                    if file.endswith(('.txt', '.yaml', '.yml', '.csv')):
                        # Toggle between filename-only and full path modes
                        full_path = os.path.join(root, file)
                        if self.use_folder_paths:
                            # Full path mode: __Series/A Centaur's Life__
                            rel_path = os.path.relpath(full_path, wildcard_path)
                            key = os.path.splitext(rel_path)[0].replace(os.sep, '/')
                        else:
                            # Filename only mode: __A Centaur's Life__
                            key = os.path.splitext(file)[0]

                        self.files_index.add(key)

                        if file.endswith(('.yaml', '.yml')):
                            self.scan_yaml_for_tags(full_path)

        GLOBAL_INDEX_LITE['built'] = True
        GLOBAL_INDEX_LITE['files'] = self.files_index
        GLOBAL_INDEX_LITE['tags'] = self.umi_tags
        GLOBAL_INDEX_LITE['entry_names'] = self.entry_names
        GLOBAL_INDEX_LITE['use_folder_paths'] = self.use_folder_paths

    def scan_yaml_for_tags(self, file_path):
        try:
            # Track modification time for this YAML file
            current_mtime = os.path.getmtime(file_path)
            yaml_cache_key = f"yaml_tags_{file_path}"

            # Check if we've already scanned this file with the same mtime
            if yaml_cache_key in FILE_MTIME_CACHE_LITE:
                cached_mtime = FILE_MTIME_CACHE_LITE[yaml_cache_key].get('mtime', 0)
                if current_mtime == cached_mtime:
                    # File hasn't changed, skip re-scanning
                    return
                else:
                    # File changed, remove old entries from index
                    if self.verbose:
                        umi_debug_print(f"[UmiAI Lite] YAML file '{os.path.basename(file_path)}' modified, rescanning tags...")
                    # Remove old entries for this file from the global index
                    for tag_list in GLOBAL_INDEX_LITE['entries'].values():
                        tag_list[:] = [e for e in tag_list if e['file'] != file_path]

            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                umi_debug_print(f"[UmiAI Lite DEBUG] Skipping {os.path.basename(file_path)}: not a dict")
                return

            tags_found = []
            entry_names_found = []
            for entry_key, entry_data in data.items():
                if not isinstance(entry_data, dict):
                    continue

                # Track entry name for direct lookup in <[EntryName]> syntax
                entry_key_str = str(entry_key).strip()
                entry_key_lower = entry_key_str.lower()
                if entry_key_str and entry_key_lower not in GLOBAL_INDEX_LITE['entry_names']:
                    self.entry_names[entry_key_lower] = {
                        'file': file_path,
                        'entry_key': entry_key,
                        'data': entry_data
                    }
                    GLOBAL_INDEX_LITE['entry_names'][entry_key_lower] = {
                        'file': file_path,
                        'entry_key': entry_key,
                        'data': entry_data
                    }
                    entry_names_found.append(entry_key_str)

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

            # Cache the modification time so we don't rescan unchanged files
            FILE_MTIME_CACHE_LITE[yaml_cache_key] = {
                'path': file_path,
                'mtime': current_mtime
            }

            if tags_found:
                umi_debug_print(f"[UmiAI Lite DEBUG] Scanned {os.path.basename(file_path)}: found tags {tags_found[:10]}")
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
                    full_path = os.path.join(root, file)
                    
                    # Support both path-based and filename-only matching
                    name_without_ext = os.path.splitext(file)[0]
                    
                    # Path-based match: relative path from wildcard folder
                    rel_path = os.path.relpath(full_path, wildcard_path)
                    path_key = os.path.splitext(rel_path)[0].replace(os.sep, '/')
                    
                    # Match against either filename-only or full path
                    if name_without_ext.lower() == file_key_lower or path_key.lower() == file_key_lower:
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
        key = self.resolve_wildcard_alias(file_key.strip())
        if key.lower().endswith('.txt'):
            key = key[:-4]
        file_key_lower = key.lower()
        for wildcard_path in self.wildcard_paths:
            for root, dirs, files in os.walk(wildcard_path):
                for file in files:
                    name_without_ext = os.path.splitext(file)[0]
                    if name_without_ext.lower() == file_key_lower and file.endswith('.txt'):
                        full_path = os.path.join(root, file)
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                content = f.read().strip()
                            return strip_prompt_comments(content)
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
            raw_lines = f.read().splitlines()
        lines = []
        def strip_double_slash_comments(line):
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
            return "".join(out).strip()

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                continue
            if '//' in line:
                line = strip_double_slash_comments(line)
                if not line:
                    continue
            if '#' in line:
                line = line.split('#')[0].strip()
            if line:
                lines.append(line)

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

    def _weighted_sample(self, entries, count, rng=None):
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
            rand_val = (rng or self.random).random() * available_total
            cumsum = 0

            for idx, i in enumerate(available_indices):
                cumsum += weights[i]
                if rand_val <= cumsum:
                    selected.append(entries[i])
                    available_indices.pop(idx)
                    break

        return selected

    def select(self, tag_key, count=1, logic_filter=None, sequential=False):
        self.init_debug_context()
        self.init_trace_context()
        scope_override = None
        if tag_key.startswith('@') and ':' in tag_key:
            scope_override, tag_key = tag_key[1:].split(':', 1)
            scope_override = scope_override.strip()
            tag_key = tag_key.strip()
        rng = self.get_rng(scope_override or tag_key)
        tag_key = self.tag_loader.resolve_wildcard_alias(tag_key)
        entries = self.tag_loader.load_from_file(tag_key)

        if not entries:
            # Fix 11: Better error messages - provide helpful feedback for missing wildcards
            error_msg = f"[WILDCARD_NOT_FOUND: {tag_key}]"
            print(f"[UmiAI Lite] WARNING: Wildcard file '{tag_key}' not found or is empty.")
            if self.is_failfast_enabled():
                return f"<<ERROR_WILDCARD_NOT_FOUND:{tag_key}>>"
            return error_msg

        if tag_key in self.seeded_values and not logic_filter and not sequential:
            return self.seeded_values[tag_key]

        # Phase 6: Sequential selection - use seed to pick same index
        if sequential and entries:
            if self.rng_streams_enabled:
                idx = self.get_scoped_index(scope_override or tag_key, len(entries))
            else:
                idx = self.seed % len(entries)
            selected_entry = entries[idx]
            result = selected_entry['value']
            self.seeded_values[tag_key] = result
            if self.is_debug_enabled():
                self.variables['debug_last_type'] = "wildcard"
                self.variables['debug_last_source'] = tag_key
                self.variables['debug_last_pick'] = str(result)
            self.set_trace_info({
                "trace_last_type": "wildcard",
                "trace_last_source": tag_key,
                "trace_last_pick": str(result),
            })
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
                if self.is_failfast_enabled():
                    return f"<<ERROR_NO_MATCHES:{logic_filter} in {tag_key}>>"
                return error_msg

            entries = filtered_entries

        # Fix 13: Weighted selection - use weights if present
        has_weights = any(entry.get('weight', 1.0) != 1.0 for entry in entries)

        if has_weights:
            # Weighted random selection
            selected_entries = self._weighted_sample(entries, min(count, len(entries)), rng=rng)
        else:
            # Normal random selection
            selected_entries = rng.sample(entries, min(count, len(entries)))

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
                    var_name = str(column_name).strip()
                    if var_name and var_name not in self.variables:
                        self.variables[var_name] = column_value
                    if var_name and UMI_SETTINGS.get('csv_namespace', True):
                        namespaced = f"csv_{var_name}"
                        if namespaced not in self.variables:
                            self.variables[namespaced] = column_value
                if self.is_debug_enabled():
                    self.variables['debug_last_type'] = "csv"
                    self.variables['debug_last_source'] = tag_key
                    if 'id' in csv_row:
                        self.variables['debug_row_id'] = str(csv_row.get('id'))
                self.set_trace_info({
                    "trace_last_type": "csv",
                    "trace_last_source": tag_key,
                    "trace_row_id": str(csv_row.get('id')) if 'id' in csv_row else "",
                })

        result = ", ".join(result_parts)
        if self.is_debug_enabled():
            self.variables['debug_last_type'] = self.variables.get('debug_last_type', "wildcard")
            self.variables['debug_last_source'] = tag_key
            self.variables['debug_last_pick'] = result
            self.variables['debug_last_count'] = str(len(selected_entries))
        self.set_trace_info({
            "trace_last_type": self.variables.get('debug_last_type', "wildcard"),
            "trace_last_source": tag_key,
            "trace_last_pick": result,
        })
        self.seeded_values[tag_key] = result
        return result

    def select_by_tags(self, logic_expression):
        cache_key = f"logic_{logic_expression}"
        if cache_key in self.seeded_values:
            return self.seeded_values[cache_key]

        evaluator = LogicEvaluator(logic_expression, self.variables)
        rng = self.get_rng(logic_expression)

        # Debug logging - VERBOSE
        total_tags = len(GLOBAL_INDEX_LITE['entries'])
        umi_debug_print(f"[UmiAI Lite DEBUG] select_by_tags('{logic_expression}'): {total_tags} tags indexed, GLOBAL_INDEX_LITE['built']={GLOBAL_INDEX_LITE['built']}")
        umi_debug_print(f"[UmiAI Lite DEBUG] GLOBAL_INDEX_LITE id: {id(GLOBAL_INDEX_LITE)}, entries id: {id(GLOBAL_INDEX_LITE['entries'])}")
        if total_tags > 0:
            umi_debug_print(f"[UmiAI Lite DEBUG] Available tags: {list(GLOBAL_INDEX_LITE['entries'].keys())[:20]}")
        else:
            umi_debug_print(f"[UmiAI Lite DEBUG] WARNING: entries dict is EMPTY! umi_tags has {len(GLOBAL_INDEX_LITE.get('tags', set()))} items")
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
                    umi_debug_print(f"[UmiAI Lite DEBUG] Checking entry '{entry_info.get('entry_key', 'unknown')}': tag_dict={tag_dict}, expression='{logic_expression}', result={result}")
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
                            'entry_key': entry_info.get('entry_key'),
                            'tags': entry_tags,
                            'description': entry_data.get('Description', [''])[0] if isinstance(entry_data.get('Description'), list) else entry_data.get('Description', ''),
                        })

        if not matching_entries:
            # Fix 11: Better error messages - show which logic expression failed to match
            error_msg = f"[NO_MATCHES: {logic_expression}]"
            umi_debug_print(f"[UmiAI Lite DEBUG] Loop complete: checked {total_entries_checked} entries, found {len(matching_entries)} matches for '{logic_expression}'")
            print(f"[UmiAI Lite] WARNING: No YAML entries matched logic expression '{logic_expression}'.")
            sys.stdout.flush()
            if self.is_failfast_enabled():
                error_msg = f"<<ERROR_NO_MATCHES:{logic_expression}>>"
            self.seeded_values[cache_key] = error_msg
            return error_msg

        selected = rng.choice(matching_entries)

        if selected.get('prefix'):
            self.prefixes.append(selected['prefix'])
        if selected.get('suffix'):
            self.suffixes.append(selected['suffix'])
        if selected.get('neg_prefix'):
            self.neg_prefixes.append(selected['neg_prefix'])
        if selected.get('neg_suffix'):
            self.neg_suffixes.append(selected['neg_suffix'])

        self.set_trace_info({
            "trace_yaml_entry": str(selected.get('entry_key') or ""),
            "trace_last_type": "yaml",
            "trace_last_source": logic_expression,
            "trace_last_pick": str(selected.get('value', '')),
        })
        if UMI_SETTINGS.get('yaml_namespace', True):
            if selected.get('entry_key'):
                self.variables['yaml_title'] = str(selected.get('entry_key'))
            tags = selected.get('tags') or []
            if tags:
                self.variables['yaml_tags'] = ", ".join(str(t) for t in tags)
            description = selected.get('description')
            if description:
                self.variables['yaml_description'] = str(description)

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

            scope_key = tag_key
            if tag_key.startswith('@') and ':' in tag_key:
                scope_key = tag_key[1:].split(':', 1)[0].strip()
            rng = self.tag_selector.get_rng(scope_key)
            count = rng.randint(min_val, max_val)
            return self.tag_selector.select(tag_key, count)

        text = re.sub(pattern, range_replacer, text)

        pattern_logic = r'__\[([^\]]+)\]__'

        def logic_replacer(match):
            logic_expr = match.group(1)
            return self.tag_selector.select_by_tags(logic_expr)

        text = re.sub(pattern_logic, logic_replacer, text)

        pattern_angle = r'<\[([^\]]+)\]>'

        def angle_replacer(match):
            expression = match.group(1)
            expression_lower = expression.lower()
            
            # Check if expression is a direct entry name (Option A: make strings work)
            if expression_lower in GLOBAL_INDEX_LITE['entry_names']:
                entry_info = GLOBAL_INDEX_LITE['entry_names'][expression_lower]
                entry_data = entry_info['data']
                prompts = entry_data.get('Prompts', [])
                
                # Convert prompts to list if it's a string
                if isinstance(prompts, str):
                    prompts = [prompts]
                
                if prompts:
                    rng = self.tag_selector.get_rng(expression)
                    selected_prompt = rng.choice(prompts)
                    umi_debug_print(f"[UmiAI Lite DEBUG] <[{expression}]> matched entry name, selected prompt: {selected_prompt[:50]}")
                    return selected_prompt
                else:
                    umi_debug_print(f"[UmiAI Lite DEBUG] <[{expression}]> matched entry name but has no Prompts")
                    return f"[NO_PROMPTS: {expression}]"
            
            # Fallback to logic-based filtering if not a direct entry name
            umi_debug_print(f"[UmiAI Lite DEBUG] <[{expression}]> not a direct entry name, treating as logic filter")
            return self.tag_selector.select_by_tags(expression)

        text = re.sub(pattern_angle, angle_replacer, text)

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
            if tag_key.startswith('@') and ':' not in tag_key:
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




# ==============================================================================
# LORA HANDLER
# ==============================================================================
class LoRAHandler(LoRAHandlerBase):
    def __init__(self):
        super().__init__()
        self._cache_dir = os.path.dirname(__file__)

    def _load_json_file(self, path):
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _get_override_tags(self, lora_path):
            """Lite Version: Check for local .json or .civitai.info sidecars."""
            if not lora_path: return None
            base = os.path.splitext(lora_path)[0]
            
            # Check .json (Standard) then .civitai.info (Civitai Helper)
            for ext in [".json", ".civitai.info"]:
                sidecar = base + ext
                if os.path.exists(sidecar):
                    try:
                        with open(sidecar, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # Look for common tag keys
                            tags = data.get("activation text") or data.get("trainedWords") or data.get("tags")
                            if tags:
                                return tags if isinstance(tags, str) else ", ".join(tags)
                    except: continue
            return None

    def _get_civitai_info_tags(self, lora_path):
        civitai_info_path = os.path.splitext(lora_path)[0] + ".civitai.info"
        civitai_info = self._load_json_file(civitai_info_path) or {}
        activation_text = civitai_info.get("activation text", "")
        if not activation_text:
            return []
        return [t.strip() for t in activation_text.split(",") if t.strip()]

    def _get_civitai_cache_tags(self, lora_path):
            """Deprecated global cache lookup. Now redirects to local sidecar logic."""
            return self._get_override_tags(lora_path)

    def get_activation_tags(self, lora_name, lora_path, max_tags=5):
            """Lite Version: Prioritize local sidecar files."""
            override_tags = self._get_override_tags(lora_path)
            if override_tags:
                tags = [t.strip() for t in override_tags.split(',') if t.strip()]
                return tags[:max_tags], "local_info"

            if lora_path and lora_path.endswith(".safetensors"):
                try:
                    with safe_open(lora_path, framework="pt", device="cpu") as f:
                        metadata = f.metadata()
                        if metadata and "ss_tag_frequency" in metadata:
                            return ["(Metadata tags found)"], "safetensors"
                except:
                    pass
            return [], "none"
    
    def extract_and_load(self, text, model, clip, lora_behavior, cache_limit):
        lora_pattern = r'<lora:([^:>]+):([-+]?[0-9.]+)>'
        lora_matches = re.findall(lora_pattern, text)

        lora_info_parts = []

        if not lora_matches:
            return text, model, clip, ""

        for lora_name, strength_str in lora_matches:
            # Input validation: clamp strength to valid range
            try:
                strength = float(strength_str)
            except ValueError:
                print(f"[UmiAI Lite] ERROR: Invalid LoRA strength '{strength_str}' for '{lora_name}'. Using 1.0 as default.")
                strength = 1.0

            lora_name = resolve_lora_alias(lora_name, get_all_wildcard_paths())

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

        activation_tags, tag_source = self.get_activation_tags(lora_name, lora_path, max_tags=20)
        if activation_tags:
            return ", ".join(activation_tags)

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
        # Check settings for conditional features
        enable_llm = UMI_SETTINGS.get('enable_llm_features', False)
        enable_danbooru = UMI_SETTINGS.get('enable_danbooru_features', False)

        # Build LLM options if enabled
        llm_options = ["None"]
        if enable_llm:
            from .nodes import DOWNLOADABLE_MODELS
            llm_files = folder_paths.get_filename_list("llm") if "llm" in folder_paths.folder_names_and_paths else []
            if not llm_files:
                llm_path = os.path.join(folder_paths.models_dir, "llm")
                if os.path.exists(llm_path):
                    llm_files = [f for f in os.listdir(llm_path) if f.endswith('.gguf')]
            download_options = list(DOWNLOADABLE_MODELS.keys())
            llm_options = ["None"] + download_options + llm_files

        inputs = {
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

        # Add LLM/Vision features if enabled
        if enable_llm:
            inputs["optional"]["image"] = ("IMAGE",)
            inputs["optional"]["update_llama_cpp"] = ("BOOLEAN", {"default": False, "label_on": "UPDATE & RESTART", "label_off": "Update Disabled"})
            inputs["optional"]["vision_model"] = (llm_options, {"default": "None"})
            inputs["optional"]["refiner_model"] = (llm_options, {"default": "None"})
            inputs["optional"]["vision_temperature"] = ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.01})
            inputs["optional"]["refiner_temperature"] = ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01})
            inputs["optional"]["max_tokens"] = ("INT", {"default": 800, "min": 100, "max": 4096})
            inputs["optional"]["custom_system_prompt"] = ("STRING", {"multiline": True, "default": "", "placeholder": "Default: You are an AI image prompt assistant. Rewrite the following into detailed natural language."})

        # Add Danbooru features if enabled
        if enable_danbooru:
            inputs["optional"]["danbooru_threshold"] = ("FLOAT", {"default": 0.70, "min": 0.1, "max": 1.0, "step": 0.05})
            inputs["optional"]["danbooru_max_tags"] = ("INT", {"default": 15, "min": 1, "max": 50})

        # Add bypass phrases for conditional bypass nodes
        inputs["optional"]["bypass_phrase"] = ("STRING", {"default": "", "multiline": False, "hidden": True})
        inputs["optional"]["bypass_phrases"] = ("STRING", {"default": "", "multiline": False, "placeholder": "simple, test, auto"})

        return inputs

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "INT", "INT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "text", "negative_text", "width", "height", "lora_info", "input_text", "input_negative", "bypass_matches")
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

    def clean_prompt(self, text):
        """Clean prompt: remove extra commas/spaces, fix BREAK formatting.
        
        - Removes multiple consecutive commas
        - Removes extra spaces
        - Removes commas before and after BREAK
        - Ensures one space before and after BREAK
        """
        import re

        if not text:
            return ""

        def _clean_segment(segment):
            segment = re.sub(r'\s+', ' ', segment)
            segment = re.sub(r'(?:\s*,\s*)+', ', ', segment)
            segment = segment.strip(' ,')
            segment = re.sub(r'\s+', ' ', segment).strip()
            return segment

        parts = re.split(r'\s*[,\.]*\s*\bBREAK\b\s*[,\.]*\s*', text, flags=re.IGNORECASE)
        cleaned_parts = [p for p in (_clean_segment(part) for part in parts) if p]

        if not cleaned_parts:
            return ""

        return " BREAK ".join(cleaned_parts)

    def preview_bypass_matched(
        self,
        text,
        seed,
        bypass_phrase,
        bypass_phrases,
        input_negative="",
        width=1024,
        height=1024,
        image_input=None,
        vision_model="None",
        refiner_model="None",
        vision_temperature=0.6,
        refiner_temperature=0.7,
        max_tokens=800,
        custom_system_prompt="",
        danbooru_threshold=0.70,
        danbooru_max_tags=15,
    ):
        """Compute bypass_matched using the same prompt expansion logic without loading LoRAs."""
        auto_clean = UMI_SETTINGS.get('auto_clean', True)
        error_lint = UMI_SETTINGS.get('error_lint', False)
        use_folder_paths = UMI_SETTINGS.get('use_folder_paths', False)

        # Strip comments: // toggles comment mode until newline or another //
        text = strip_prompt_comments(text)

        options = {
            'verbose': False,
            'seed': seed,
            'use_folder_paths': use_folder_paths,
            'rng_streams': UMI_SETTINGS.get('rng_streams', False),
        }

        all_wildcard_paths = get_all_wildcard_paths()
        tag_loader = TagLoader(all_wildcard_paths, options)

        tag_selector = TagSelector(tag_loader, options)
        neg_gen = NegativePromptGenerator()

        tag_replacer = TagReplacer(tag_selector)
        dynamic_replacer = DynamicPromptReplacer(seed)
        conditional_replacer = ConditionalReplacer()
        variable_replacer = VariableReplacer()

        # Initialize optional replacers based on settings
        if UMI_SETTINGS.get('enable_llm_features', False):
            from .nodes import VisionReplacer, LLMReplacer
            vision_replacer = VisionReplacer(self, vision_model, refiner_model, vision_temperature, refiner_temperature, max_tokens, image_input)
            llm_replacer = LLMReplacer(self, refiner_model, refiner_temperature, max_tokens, custom_system_prompt)
        else:
            vision_replacer = None
            llm_replacer = None

        if UMI_SETTINGS.get('enable_danbooru_features', False):
            from .nodes import DanbooruReplacer
            danbooru_replacer = DanbooruReplacer(options)
        else:
            danbooru_replacer = None

        # Load globals
        globals_dict = tag_loader.load_globals()
        variable_replacer.load_globals(globals_dict)

        # Inject error_lint setting as failfast variable in both variable_replacer and tag_selector
        if error_lint:
            variable_replacer.variables['fail_fast'] = '1'
            variable_replacer.variables['failfast'] = '1'
            tag_selector.variables['fail_fast'] = '1'
            tag_selector.variables['failfast'] = '1'

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

            prompt_history.append(prompt)
            previous_prompt = prompt

            # Pre-expand prompt files so variables apply in the same pass
            prompt = expand_prompt_files(prompt, tag_loader)

            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)

            masked_prompt, if_blocks = conditional_replacer.mask_conditionals(prompt)

            # Process Vision and LLM tags if enabled (skip conditional blocks)
            if vision_replacer:
                masked_prompt = vision_replacer.replace(masked_prompt)
            if llm_replacer:
                masked_prompt = llm_replacer.replace(masked_prompt)

            masked_prompt = CharacterReplacer.replace(masked_prompt)  # @@character:outfit:emotion@@
            masked_prompt = tag_replacer.replace(masked_prompt)
            masked_prompt = dynamic_replacer.replace(masked_prompt)

            # Process Danbooru tags if enabled
            if danbooru_replacer:
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
            umi_debug_print(f"[UmiAI Lite] WARNING: Reached maximum processing iterations (50). Possible recursive wildcards or variables.")

        # Apply conditional logic (in case any remain after loop)
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

        # Cleanup (enhanced with BREAK handling if auto_clean enabled)
        if auto_clean:
            prompt = self.clean_prompt(prompt)
        else:
            prompt = re.sub(r',\s*,', ',', prompt)
            prompt = re.sub(r'\s+', ' ', prompt).strip().strip(',')

        if tag_selector.is_trace_enabled():
            prompt = append_trace_summary(prompt, variable_replacer.variables)
        if tag_selector.is_debug_enabled():
            prompt = append_debug_summary(prompt, variable_replacer.variables)

        bypass_matched = bool(bypass_phrase) and bypass_phrase in prompt
        bypass_list = []
        if bypass_phrases:
            phrases = [p.strip() for p in bypass_phrases.split(",") if p.strip()]
            bypass_list = [phrase in prompt for phrase in phrases]
        return bypass_matched, prompt, bypass_list

    def process(self, **kwargs):
        # Check if auto-update was requested (LLM feature)
        if UMI_SETTINGS.get('enable_llm_features', False):
            do_update = kwargs.get("update_llama_cpp", False)
            if do_update:
                from .nodes import perform_library_update
                success = perform_library_update()
                if success:
                    raise Exception("Auto-Update Complete! Please Restart ComfyUI now.")
                else:
                    raise Exception("Auto-Update Failed! Check console for errors.")

        # Check for frozen text from auto-requeue (bypass wildcard processing)
        frozen_text = kwargs.get("_frozen_text", None)
        frozen_negative = kwargs.get("_frozen_negative", None)
        frozen_seed = kwargs.get("_frozen_seed", None)

        if frozen_text:
            print(f"[UmiAI Lite] Using FROZEN prompt from auto-requeue (skipping wildcard processing)")
            print(f"[UmiAI Lite] Frozen text: {frozen_text[:100]}...")

            # Get basic parameters
            model = kwargs.get("model", None)
            clip = kwargs.get("clip", None)
            width = self.get_val(kwargs, "width", 1024, int)
            height = self.get_val(kwargs, "height", 1024, int)
            lora_tags_behavior = self.get_val(kwargs, "lora_tags_behavior", "Append to Prompt", str)
            lora_cache_limit = self.get_val(kwargs, "lora_cache_limit", 5, int)
            bypass_phrase = kwargs.get("bypass_phrase", "")
            bypass_phrases = kwargs.get("bypass_phrases", "")

            # Use frozen values
            prompt = frozen_text
            final_negative = frozen_negative if frozen_negative else ""
            seed = frozen_seed if frozen_seed is not None else self.get_val(kwargs, "seed", 0, int)

            # Still need to extract LoRAs from the frozen prompt
            lora_handler = LoRAHandler()
            prompt, final_model, final_clip, lora_info = lora_handler.extract_and_load(
                prompt, model, clip, lora_tags_behavior, lora_cache_limit
            )

            # Calculate bypass_matched and bypass_matches
            bypass_matched = bool(bypass_phrase) and bypass_phrase in prompt
            bypass_list = []
            if bypass_phrases:
                phrases = [p.strip() for p in bypass_phrases.split(",") if p.strip()]
                bypass_list = [phrase in prompt for phrase in phrases]
            bypass_matches = json.dumps(bypass_list)

            # Extract settings
            prompt, settings = self.extract_settings(prompt)
            final_width = settings['width'] if settings['width'] > 0 else width
            final_height = settings['height'] if settings['height'] > 0 else height

            # Log to history
            log_prompt_to_history(prompt, final_negative, seed)

            # Return immediately with frozen values
            print(f"[UmiAI Lite] Returning frozen prompt (bypass_matched={bypass_matched})")
            return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info, frozen_text, frozen_negative, bypass_matches)

        text = self.get_val(kwargs, "text", "", str)
        seed = self.get_val(kwargs, "seed", 0, int)

        model = kwargs.get("model", None)
        clip = kwargs.get("clip", None)
        image_input = kwargs.get("image", None) if UMI_SETTINGS.get('enable_llm_features', False) else None

        width = self.get_val(kwargs, "width", 1024, int)
        height = self.get_val(kwargs, "height", 1024, int)

        # Fix: Ensure width/height are never 0
        if width <= 0:
            width = 1024
        if height <= 0:
            height = 1024

        lora_tags_behavior = self.get_val(kwargs, "lora_tags_behavior", "Append to Prompt", str)
        lora_cache_limit = self.get_val(kwargs, "lora_cache_limit", 5, int)
        auto_clean = UMI_SETTINGS.get('auto_clean', True)
        error_lint = UMI_SETTINGS.get('error_lint', False)
        use_folder_paths = UMI_SETTINGS.get('use_folder_paths', False)
        input_negative = self.get_val(kwargs, "input_negative", "", str)

        # Debug: Show what settings are being read
        if UMI_SETTINGS.get('enable_debug_output', False):
            from .nodes import umi_debug_print
            umi_debug_print(f"[UmiAI Lite] Processing with: auto_clean={auto_clean}, error_lint={error_lint}")

        # LLM/Vision parameters (if enabled)
        if UMI_SETTINGS.get('enable_llm_features', False):
            vision_model = self.get_val(kwargs, "vision_model", "None", str)
            refiner_model = self.get_val(kwargs, "refiner_model", "None", str)
            vision_temperature = self.get_val(kwargs, "vision_temperature", 0.6, float)
            refiner_temperature = self.get_val(kwargs, "refiner_temperature", 0.7, float)
            max_tokens = self.get_val(kwargs, "max_tokens", 800, int)
            custom_system_prompt = self.get_val(kwargs, "custom_system_prompt", "", str)
        else:
            vision_model = refiner_model = "None"
            vision_temperature = refiner_temperature = 0.7
            max_tokens = 800
            custom_system_prompt = ""

        # Danbooru parameters (if enabled)
        if UMI_SETTINGS.get('enable_danbooru_features', False):
            danbooru_threshold = self.get_val(kwargs, "danbooru_threshold", 0.70, float)
            danbooru_max_tags = self.get_val(kwargs, "danbooru_max_tags", 15, int)
        else:
            danbooru_threshold = 0.70
            danbooru_max_tags = 15

        # ============================================================
        # CORE PROCESSING
        # ============================================================

        # Strip comments: // toggles comment mode until newline or another //
        text = strip_prompt_comments(text)

        options = {
            'verbose': False,
            'seed': seed,
            'use_folder_paths': use_folder_paths,
            'rng_streams': UMI_SETTINGS.get('rng_streams', False),
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

        # Initialize optional replacers based on settings
        if UMI_SETTINGS.get('enable_llm_features', False):
            from .nodes import VisionReplacer, LLMReplacer
            vision_replacer = VisionReplacer(self, vision_model, refiner_model, vision_temperature, refiner_temperature, max_tokens, image_input)
            llm_replacer = LLMReplacer(self, refiner_model, refiner_temperature, max_tokens, custom_system_prompt)
        else:
            vision_replacer = None
            llm_replacer = None

        if UMI_SETTINGS.get('enable_danbooru_features', False):
            from .nodes import DanbooruReplacer
            danbooru_replacer = DanbooruReplacer(options)
        else:
            danbooru_replacer = None

        # Load globals
        globals_dict = tag_loader.load_globals()
        variable_replacer.load_globals(globals_dict)

        # Inject error_lint setting as failfast variable in both variable_replacer and tag_selector
        if error_lint:
            variable_replacer.variables['fail_fast'] = '1'
            variable_replacer.variables['failfast'] = '1'
            tag_selector.variables['fail_fast'] = '1'
            tag_selector.variables['failfast'] = '1'

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

            prompt_history.append(prompt)
            previous_prompt = prompt

            # Pre-expand prompt files so variables apply in the same pass
            prompt = expand_prompt_files(prompt, tag_loader)

            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)

            masked_prompt, if_blocks = conditional_replacer.mask_conditionals(prompt)

            # Process Vision and LLM tags if enabled (skip conditional blocks)
            if vision_replacer:
                masked_prompt = vision_replacer.replace(masked_prompt)
            if llm_replacer:
                masked_prompt = llm_replacer.replace(masked_prompt)

            masked_prompt = CharacterReplacer.replace(masked_prompt)  # @@character:outfit:emotion@@
            masked_prompt = tag_replacer.replace(masked_prompt)
            masked_prompt = dynamic_replacer.replace(masked_prompt)

            # Process Danbooru tags if enabled
            if danbooru_replacer:
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
            umi_debug_print(f"[UmiAI Lite] WARNING: Reached maximum processing iterations (50). Possible recursive wildcards or variables.")

        # Apply conditional logic (in case any remain after loop)
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

        # Cleanup (enhanced with BREAK handling if auto_clean enabled)
        if auto_clean:
            prompt = self.clean_prompt(prompt)
        else:
            prompt = re.sub(r',\s*,', ',', prompt)
            prompt = re.sub(r'\s+', ' ', prompt).strip().strip(',')

        if tag_selector.is_trace_enabled():
            prompt = append_trace_summary(prompt, variable_replacer.variables)
        if tag_selector.is_debug_enabled():
            prompt = append_debug_summary(prompt, variable_replacer.variables)

        # Calculate bypass_matched for conditional bypass nodes before LoRA extraction
        bypass_phrase = kwargs.get("bypass_phrase", "")
        bypass_phrases = kwargs.get("bypass_phrases", "")
        bypass_matched = bool(bypass_phrase) and bypass_phrase in prompt
        bypass_list = []
        if bypass_phrases:
            phrases = [p.strip() for p in bypass_phrases.split(",") if p.strip()]
            bypass_list = [phrase in prompt for phrase in phrases]
        bypass_matches = json.dumps(bypass_list)

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

        # Phase 8: Log prompt to history
        log_prompt_to_history(prompt, final_negative, seed)

        if UMI_SETTINGS.get('enable_debug_output', False):
            if bypass_phrase:
                umi_debug_print(f"[Wildcard] Bypass phrase '{bypass_phrase}' {'FOUND' if bypass_matched else 'NOT FOUND'} in prompt")

        return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info, text, input_negative, bypass_matches)


# ==============================================================================
# TEXT BYPASS HELPER NODE
# ==============================================================================
class UmiTextBypass:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "passthrough_type": (["IMAGE", "LATENT", "CONDITIONING", "MODEL", "CLIP", "STRING"], {"default": "IMAGE"}),
            },
            "optional": {
                "matched_list": ("STRING", {"default": "", "multiline": False, "forceInput": True}),
                "match_index": ("INT", {"default": 0, "min": 0, "max": 1024, "step": 1}),
                "image": ("IMAGE",),
                "latent": ("LATENT",),
                "conditioning": ("CONDITIONING",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "string": ("STRING", {"multiline": True, "forceInput": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "LATENT", "CONDITIONING", "MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("image", "latent", "conditioning", "model", "clip", "string")
    FUNCTION = "run"
    CATEGORY = "UmiAI"

    def run(self, passthrough_type, matched_list=None, match_index=0,
            image=None, latent=None, conditioning=None, model=None, clip=None, string=None):

        effective_matched = False
        if matched_list:
            try:
                parsed = matched_list
                if isinstance(matched_list, str):
                    parsed = json.loads(matched_list)
                if isinstance(parsed, list) and 0 <= int(match_index) < len(parsed):
                    effective_matched = bool(parsed[int(match_index)])
            except Exception:
                pass

        print(f"[UmiTextBypass BACKEND] Executing!")
        print(f"[UmiTextBypass BACKEND] matched input: (effective={effective_matched})")
        print(f"[UmiTextBypass BACKEND] passthrough_type: {passthrough_type}")

        blocker_cls = _get_execution_blocker_class()
        backend_controls = blocker_cls is not None

        # Check if we need to trigger a state change and restart
        # This happens BEFORE we continue downstream
        needs_restart = False
        try:
            from server import PromptServer
            # Send a pre-check signal to ask frontend if state needs changing
            PromptServer.instance.send_sync(
                "umi_bypass_precheck",
                {"matched": effective_matched, "check_state": True},
            )
            print(f"[UmiTextBypass BACKEND] Sent precheck signal: matched={effective_matched}")
        except Exception as e:
            print(f"[UmiTextBypass BACKEND] Failed to send precheck: {e}")

        # Send matched status to frontend immediately
        try:
            from server import PromptServer
            PromptServer.instance.send_sync(
                "umi_bypass_signal",
                {"matched": effective_matched, "backend_controls": backend_controls, "needs_restart": needs_restart},
            )
            print(f"[UmiTextBypass BACKEND] Sent bypass signal: matched={effective_matched}, backend_controls={backend_controls}")
        except Exception as e:
            print(f"[UmiTextBypass BACKEND] Failed to send signal: {e}")

        # If ExecutionBlocker is available, stop downstream execution immediately
        if not effective_matched and blocker_cls is not None:
            blocker = blocker_cls()
            print("[UmiTextBypass BACKEND] Blocking downstream execution via ExecutionBlocker")
            return (blocker, blocker, blocker, blocker, blocker, blocker)

        # Always pass through - the matched boolean is informational only
        out_image = None
        out_latent = None
        out_conditioning = None
        out_model = None
        out_clip = None
        out_string = None

        if passthrough_type == "IMAGE":
            out_image = image
        elif passthrough_type == "LATENT":
            out_latent = latent
        elif passthrough_type == "CONDITIONING":
            out_conditioning = conditioning
        elif passthrough_type == "MODEL":
            out_model = model
        elif passthrough_type == "CLIP":
            out_clip = clip
        elif passthrough_type == "STRING":
            out_string = string

        status = "MATCHED" if effective_matched else "NOT MATCHED"
        print(f"[UmiTextBypass BACKEND] {status} - passing through {passthrough_type}")
        if blocker_cls is None:
            print("[UmiTextBypass BACKEND] Note: ExecutionBlocker unavailable - frontend bypass may be used")
        return (out_image, out_latent, out_conditioning, out_model, out_clip, out_string)

NODE_CLASS_MAPPINGS = {
    "UmiAIWildcardNodeLite": UmiAIWildcardNodeLite,
    "UmiAIWildcardNode": UmiAIWildcardNodeLite  # Unified node - both names map to same class
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiAIWildcardNodeLite": "UmiAI Wildcard Processor",
    "UmiAIWildcardNode": "UmiAI Wildcard Processor"  # Same display name for both
}
