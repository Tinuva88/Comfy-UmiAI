import os
import re
import yaml
import hashlib
import json
import logging
import csv
import gc
import threading
from collections import OrderedDict
import folder_paths
import comfy.sd
import comfy.utils
import torch
from safetensors import safe_open
from datetime import datetime

# Import shared utilities
from .shared_utils import (
    _atomic_write_json, _dedupe_keep_order, _split_prompt_tags,
    parse_wildcard_weight, log_prompt_to_history, expand_prompt_files,
    get_all_wildcard_paths, scan_wildcard_files,
    LogicEvaluator, DynamicPromptReplacer, VariableReplacer, NegativePromptGenerator,
    ConditionalReplacer, TagLoaderBase, TagSelectorBase, LoRAHandlerBase, TagReplacerBase,
    CharacterReplacer, resolve_lora_alias, strip_prompt_comments,
    apply_prompt_sections, build_prompt_diff, apply_prompt_preset, expand_prompt_presets,
    list_prompt_presets, lint_prompt_profile, list_prompt_profiles, apply_named_prompt_profile,
    lint_prompt_join_boundaries, lint_prompt_syntax
)
from .prompt_parser import find_lora_spans, find_settings_spans, find_wildcard_spans, parse_angle_yaml_specs, parse_key_value_csv, parse_lora_specs, parse_wildcard_specs, remove_spans

# Import lean shared settings/debug helpers.
from .nodes_core import UMI_SETTINGS, umi_debug_print
from .prompt_extensions import get_anima_extension

# ==============================================================================
def _write_run_inspector_cache(payload):
    try:
        cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "run_inspector_latest.json")
        _atomic_write_json(cache_path, payload, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        umi_debug_print(f"[UmiAI Lite] Failed to write run inspector cache: {e}")

# ==============================================================================
# GLOBAL CACHE & SETUP (LITE VERSION - ISOLATED FROM FULL NODE)
# ==============================================================================
GLOBAL_CACHE_LITE = {}
GLOBAL_INDEX_LITE = {'built': False, 'files': set(), 'entries': {}, 'tags': set(), 'entry_names': {}, 'signature': None}

# Fix 12: File modification time cache to skip rescanning unchanged files
FILE_MTIME_CACHE_LITE = {}

# LRU CACHE (ISOLATED FROM FULL NODE)
LORA_MEMORY_CACHE_LITE = OrderedDict()
PROMPT_CACHE_LOCK = threading.RLock()
# Iteration limits alone cannot stop a wildcard that doubles on each pass.
MAX_EXPANDED_PROMPT_CHARS = 1_000_000


def _check_prompt_size(text):
    limit = _processing_limit('max_expanded_prompt_chars', MAX_EXPANDED_PROMPT_CHARS, 1000, 10_000_000)
    if len(text) > limit:
        raise ValueError(
            f"Wildcard expansion exceeded {limit:,} characters. Check for recursive "
            "wildcard files or reduce repeated sampling counts."
        )


def _processing_limit(name, default, minimum, maximum):
    try:
        value = int(UMI_SETTINGS.get(name, default))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(minimum, min(maximum, value))

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def _get_execution_blocker_class():
    """Try to resolve ComfyUI's ExecutionBlocker without hard dependency."""
    try:
        # Current ComfyUI location.
        from comfy_execution.graph import ExecutionBlocker
        return ExecutionBlocker
    except Exception:
        pass
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

# ==============================================================================
# TAG LOADER (Lite Version - No Danbooru)
# ==============================================================================
def yaml_field(entry_data, name, default=None):
    """Look a YAML entry field up without regard to key case.

    YAML itself is case-sensitive, so an entry written with "tags:" and
    "prompts:" used to match nothing at all and say nothing about why. The
    documented spelling is still Tags/Prompts; this only stops a reasonable
    variation from failing silently.
    """
    if not isinstance(entry_data, dict):
        return default
    if name in entry_data:
        return entry_data[name]
    target = str(name).strip().lower()
    for key, value in entry_data.items():
        if str(key).strip().lower() == target:
            return value
    return default


def yaml_text_list(entry_data, name):
    """A YAML entry field as a list of non-empty strings.

    Accepts a scalar or a list. Two of the three code paths that read Prefix
    and Suffix required a list and dropped a plain string on the floor, so the
    same file behaved differently depending on how it was selected.
    """
    value = yaml_field(entry_data, name)
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for item in items:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def yaml_joined(entry_data, name):
    """Every item of a field, joined. Only the first used to be read."""
    return ", ".join(yaml_text_list(entry_data, name))


class TagLoader(TagLoaderBase):
    def __init__(self, wildcard_paths, options):
        super().__init__(wildcard_paths, options)
        self.use_folder_paths = options.get('use_folder_paths', False)
        self.build_index()

    def build_index(self):
        # Check if cache was built with a different use_folder_paths setting
        cached_setting = GLOBAL_INDEX_LITE.get('use_folder_paths', None)
        current_signature = scan_wildcard_files(self.wildcard_paths)
        cached_signature = GLOBAL_INDEX_LITE.get('signature')
        self.file_catalog = []
        self.catalog_keys = {}
        for item in current_signature:
            if len(item) != 4:
                continue
            root, relative, mtime_ns, size = item
            record = dict(root=root, relative_path=relative,
                          path=os.path.join(root, relative), mtime_ns=mtime_ns, size=size)
            self.file_catalog.append(record)
            key = os.path.splitext(relative)[0].lower()
            for alias in {key, key.rsplit('/', 1)[-1]}:
                self.catalog_keys.setdefault(alias, []).append(record)

        if GLOBAL_INDEX_LITE['built'] and cached_setting == self.use_folder_paths and cached_signature == current_signature:
            # Reuse the index only when every supported file is unchanged.
            self.files_index = GLOBAL_INDEX_LITE['files']
            self.umi_tags = GLOBAL_INDEX_LITE['tags']
            self.entry_names = GLOBAL_INDEX_LITE.get('entry_names', {})
            # The signature already includes every supported file's size and
            # nanosecond mtime. A second tree walk cannot add freshness here.
            return

        # Rebuild if setting changed or first build
        if GLOBAL_INDEX_LITE['built'] and (cached_setting != self.use_folder_paths or cached_signature != current_signature):
            if cached_setting != self.use_folder_paths:
                umi_debug_print(f"[UmiAI Lite] Rebuilding index: use_folder_paths changed from {cached_setting} to {self.use_folder_paths}")
            else:
                umi_debug_print("[UmiAI Lite] Rebuilding index: wildcard files changed")
            GLOBAL_INDEX_LITE['built'] = False  # Force rebuild

        # Reset for fresh build
        self.files_index = set()
        self.umi_tags = set()
        self.entry_names = {}
        GLOBAL_INDEX_LITE['entries'] = {}
        GLOBAL_INDEX_LITE['entry_names'] = {}
        # Rebuild lookup metadata but retain parsed files with unchanged stats.
        live_paths = {entry['path'] for entry in self.file_catalog}
        for key, info in list(FILE_MTIME_CACHE_LITE.items()):
            if key.startswith('yaml_tags_') or info.get('path') not in live_paths:
                FILE_MTIME_CACHE_LITE.pop(key, None)
                GLOBAL_CACHE_LITE.pop(key, None)

        for entry in self.file_catalog:
            relative = entry['relative_path']
            key = os.path.splitext(relative if self.use_folder_paths else relative.rsplit('/', 1)[-1])[0]
            self.files_index.add(key)
            if relative.endswith(('.yaml', '.yml')):
                self.scan_yaml_for_tags(entry['path'])

        GLOBAL_INDEX_LITE['built'] = True
        GLOBAL_INDEX_LITE['files'] = self.files_index
        GLOBAL_INDEX_LITE['tags'] = self.umi_tags
        GLOBAL_INDEX_LITE['entry_names'] = self.entry_names
        GLOBAL_INDEX_LITE['use_folder_paths'] = self.use_folder_paths
        GLOBAL_INDEX_LITE['signature'] = current_signature

    def _read_yaml(self, file_path):
        stat = os.stat(file_path)
        key = f"yaml_data_{file_path}"
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = FILE_MTIME_CACHE_LITE.get(key)
        if cached and cached.get('stat') == signature:
            return cached['data']
        with open(file_path, 'r', encoding='utf-8-sig') as handle:
            data = yaml.safe_load(handle)
        FILE_MTIME_CACHE_LITE[key] = {'path': file_path, 'stat': signature, 'data': data}
        return data

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

            data = self._read_yaml(file_path)

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

                entry_tags = yaml_text_list(entry_data, 'Tags')

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
            logging.error(f"[UmiAI Lite] Malformed YAML file '{os.path.basename(file_path)}', skipped. Fix the syntax and refresh wildcards: {e}")
        except UnicodeDecodeError as e:
            logging.error(f"[UmiAI Lite] '{os.path.basename(file_path)}' is not UTF-8, skipped: {e}")
        except Exception as e:
            logging.warning(f"[UmiAI Lite] Could not scan YAML '{os.path.basename(file_path)}', skipped: {e}")

    # load_globals is inherited from TagLoaderBase.

    def load_from_file(self, file_key):
        file_key = file_key.replace("\\", "/")
        cache_key = f"file_{file_key}"
        self.last_loaded_file_info = None
        candidates = self.catalog_keys.get(file_key.lower(), [])
        signature = tuple((e['path'], e['mtime_ns'], e['size']) for e in candidates)
        cached_info = FILE_MTIME_CACHE_LITE.get(cache_key, {})
        if cache_key in GLOBAL_CACHE_LITE and cached_info.get('candidates') == signature:
            self.last_loaded_file_info = dict(cached_info, cache_hit=True)
            return GLOBAL_CACHE_LITE[cache_key]

        empty_info = None
        for entry in candidates:
            self.last_load_error = None
            result = self.load_file(entry['path'])
            info = dict(entry, mtime=entry['mtime_ns'] / 1e9, candidates=signature)
            if not result:
                info['empty_match'] = True
                if self.last_load_error:
                    info['error'] = self.last_load_error
                if empty_info is None:
                    empty_info = info
                continue
            GLOBAL_CACHE_LITE[cache_key] = result
            FILE_MTIME_CACHE_LITE[cache_key] = info
            self.last_loaded_file_info = dict(info, cache_hit=False)
            return result

        info = empty_info or {'missing': True, 'candidates': signature}
        GLOBAL_CACHE_LITE[cache_key] = []
        FILE_MTIME_CACHE_LITE[cache_key] = info
        self.last_loaded_file_info = dict(info, cache_hit=False)
        return []

    def load_prompt_file(self, file_key):
        key = self.resolve_wildcard_alias(file_key.strip()).replace("\\", "/")
        if key.lower().endswith('.txt'):
            key = key[:-4]
        if os.path.isabs(key) or '..' in key.split('/'):
            return None
        for entry in self.catalog_keys.get(key.lower(), []):
            if not entry['relative_path'].endswith('.txt'):
                continue
            try:
                with open(entry['path'], 'r', encoding='utf-8-sig') as handle:
                    return strip_prompt_comments(handle.read().strip())
            except (OSError, UnicodeError) as exc:
                raise ValueError(f'Prompt file "{key}" could not be read: {exc}') from exc
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
            self.last_load_error = str(e)
            logging.warning(f"[UmiAI Lite] Wildcard file '{file_path}' could not be read: {e}")
        return []

    def load_txt_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8-sig') as f:
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
            # Inline comments need a space before '#' so entries containing a
            # bare '#' (e.g. "deep#blue") survive. Matches strip_prompt_comments.
            if ' #' in line:
                line = line.split(' #')[0].strip()
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
            data = self._read_yaml(file_path)

            if not isinstance(data, dict):
                logging.warning(f"[UmiAI Lite] YAML file '{os.path.basename(file_path)}' does not contain a dictionary. Skipping.")
                return []

            entries = []
            for entry_key, entry_data in data.items():
                if isinstance(entry_data, dict):
                    prompts = yaml_text_list(entry_data, 'Prompts')
                    # Tags were dropped here, so __file[tag]__ filtered against
                    # an empty tag list and could never match -- a documented
                    # form that always reported no matches.
                    entry_tags = yaml_text_list(entry_data, 'Tags')

                    for prompt in prompts:
                        entries.append({
                            'value': prompt,
                            'tags': entry_tags,
                            'entry_key': entry_key,
                            'description': yaml_joined(entry_data, 'Description'),
                            'prefix': yaml_joined(entry_data, 'Prefix'),
                            'suffix': yaml_joined(entry_data, 'Suffix'),
                            'neg_prefix': yaml_joined(entry_data, 'Neg_Prefix'),
                            'neg_suffix': yaml_joined(entry_data, 'Neg_Suffix'),
                        })

            return entries
        except yaml.YAMLError as e:
            self.last_load_error = str(e)
            logging.error(f"[UmiAI Lite] Malformed YAML file '{os.path.basename(file_path)}'; fix the syntax: {e}")
            return []
        except UnicodeDecodeError as e:
            self.last_load_error = str(e)
            logging.error(f"[UmiAI Lite] Encoding issue in '{os.path.basename(file_path)}': {e}")
            return []
        except Exception as e:
            self.last_load_error = str(e)
            logging.warning(f"[UmiAI Lite] Error loading YAML '{os.path.basename(file_path)}': {e}")
            return []

    def load_csv_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8-sig') as f:
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
        self.wildcard_trace = []
        self.diagnostics = []

    def clear_seeded_values(self):
        self.seeded_values.clear()
        self.scoped_negatives = []
        self.wildcard_trace = []
        self.diagnostics = []

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

    def _entry_index(self, entries, entry):
        try:
            return entries.index(entry)
        except ValueError:
            return None

    def _trace_file_info(self):
        info = getattr(self.tag_loader, "last_loaded_file_info", None) or {}
        return {
            "path": info.get("path"),
            "root": info.get("root"),
            "relative_path": info.get("relative_path"),
            "cache_hit": bool(info.get("cache_hit")),
        }

    def _record_wildcard_trace(self, **kwargs):
        record = {
            "seed": self.seed,
            "rng_streams": self.rng_streams_enabled,
            **self._trace_file_info(),
            "type": "wildcard",
            **kwargs,
        }
        self.wildcard_trace.append(record)

    def select(self, tag_key, count=1, logic_filter=None, sequential=False):
        self.init_debug_context()
        self.init_trace_context()
        scope_override = None
        if tag_key.startswith('@') and ':' in tag_key:
            scope_override, tag_key = tag_key[1:].split(':', 1)
            scope_override = scope_override.strip()
            tag_key = tag_key.strip()
        if scope_override is None:
            scope_override = getattr(self, 'assignment_scope', None)
        rng = self.get_rng(scope_override or tag_key)
        tag_key = self.tag_loader.resolve_wildcard_alias(tag_key)
        # Cache identity must include the scope and the requested count, or
        # sibling variables collide and __x__/__2$$x__ swap values.
        if scope_override is None and count == 1:
            cache_key = tag_key
        else:
            cache_key = ''.join((tag_key, scope_override or '', str(count)))
        entries = self.tag_loader.load_from_file(tag_key)

        if not entries:
            # Fix 11: Better error messages - provide helpful feedback for missing wildcards
            error_msg = f"[WILDCARD_NOT_FOUND: {tag_key}]"
            info = getattr(self.tag_loader, 'last_loaded_file_info', None) or {}
            if info.get('error'):
                reason = f'Wildcard "{tag_key}" could not be read: {info["error"]}'
            elif info.get('empty_match'):
                reason = f'Wildcard "{tag_key}" contains no usable candidates (check blank/comment lines or YAML Prompts).'
            else:
                reason = f'Wildcard "{tag_key}" could not be found in the configured wildcard folders.'
            if reason not in self.diagnostics:
                self.diagnostics.append(reason)
            logging.warning(f"[UmiAI Lite] {reason}")
            self._record_wildcard_trace(
                wildcard=tag_key,
                scope=scope_override,
                mode="missing",
                count=0,
                values=[],
                result=error_msg,
                error=error_msg,
                diagnostic=reason,
            )
            if self.is_failfast_enabled():
                return f"<<ERROR_WILDCARD_NOT_FOUND:{tag_key}>>"
            return error_msg

        if cache_key in self.seeded_values and not logic_filter and not sequential:
            self._record_wildcard_trace(
                wildcard=tag_key,
                scope=scope_override,
                mode="cached",
                count=1,
                values=[self.seeded_values[cache_key]],
                result=self.seeded_values[cache_key],
            )
            return self.seeded_values[cache_key]

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
                logging.warning(f"[UmiAI Lite] No entries in '{tag_key}' matched logic '{logic_filter}'.")
                if self.is_failfast_enabled():
                    return f"<<ERROR_NO_MATCHES:{logic_filter} in {tag_key}>>"
                self._record_wildcard_trace(
                    wildcard=tag_key,
                    scope=scope_override,
                    mode="logic",
                    logic_filter=logic_filter,
                    count=0,
                    values=[],
                    result=error_msg,
                    error=error_msg,
                )
                return error_msg

            entries = filtered_entries

        # A scope-qualified request avoids values this file already handed to
        # another scope, so sibling variables differ where the pool allows.
        # When the pool cannot cover the request it recycles.
        if scope_override is not None and not logic_filter and not sequential:
            emitted = getattr(self, 'emitted_values', None)
            if emitted is None:
                emitted = self.emitted_values = {}
            seen = emitted.setdefault(tag_key, set())
            fresh = [e for e in entries if e['value'] not in seen]
            if len(fresh) >= count:
                entries = fresh
            elif fresh or seen:
                seen.clear()

        # Fix 13: Weighted selection - use weights if present
        has_weights = any(entry.get('weight', 1.0) != 1.0 for entry in entries)

        if sequential:
            # Apply filters first, then walk the eligible pool by seed.
            # Use the shared metadata path for YAML decorations and CSV columns.
            idx = self.seed % len(entries)
            take = max(0, min(count, len(entries)))
            selected_entries = [entries[(idx + offset) % len(entries)] for offset in range(take)]
            mode = "sequential"
        elif has_weights:
            # Weighted random selection
            selected_entries = self._weighted_sample(entries, min(count, len(entries)), rng=rng)
            mode = "weighted"
        else:
            # Normal random selection
            selected_entries = rng.sample(entries, min(count, len(entries)))
            mode = "random"

        result_parts = []
        selected_indices = []
        selected_tags = []
        selected_weights = []
        for entry in selected_entries:
            result_parts.append(entry['value'])
            selected_indices.append(self._entry_index(entries, entry))
            selected_tags.append(entry.get('tags', []))
            selected_weights.append(entry.get('weight', 1.0))

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
        if not logic_filter and not sequential:
            self.seeded_values[cache_key] = result
        if scope_override is not None and not logic_filter and not sequential:
            self.emitted_values.setdefault(tag_key, set()).update(result_parts)
        self._record_wildcard_trace(
            wildcard=tag_key,
            scope=scope_override,
            mode="sequential" if sequential else ("logic" if logic_filter else mode),
            logic_filter=logic_filter,
            count=len(selected_entries),
            available_count=len(entries),
            selected_indices=selected_indices,
            values=result_parts,
            tags=selected_tags,
            weights=selected_weights,
            result=result,
        )
        return result

    def select_by_tags(self, logic_expression):
        cache_key = f"logic_{logic_expression}"
        if cache_key in self.seeded_values:
            self._record_wildcard_trace(
                type="yaml",
                wildcard=logic_expression,
                mode="cached",
                count=1,
                values=[self.seeded_values[cache_key]],
                result=self.seeded_values[cache_key],
            )
            return self.seeded_values[cache_key]

        evaluator = LogicEvaluator(logic_expression, self.variables)
        rng = self.get_rng(logic_expression)

        # Debug logging - VERBOSE
        debug_enabled = UMI_SETTINGS.get('enable_debug_output', False)
        total_tags = len(GLOBAL_INDEX_LITE['entries'])
        if debug_enabled:
            umi_debug_print(f"[UmiAI Lite DEBUG] select_by_tags('{logic_expression}'): {total_tags} tags indexed, GLOBAL_INDEX_LITE['built']={GLOBAL_INDEX_LITE['built']}")
            umi_debug_print(f"[UmiAI Lite DEBUG] GLOBAL_INDEX_LITE id: {id(GLOBAL_INDEX_LITE)}, entries id: {id(GLOBAL_INDEX_LITE['entries'])}")
            if total_tags > 0:
                umi_debug_print(f"[UmiAI Lite DEBUG] Available tags: {list(GLOBAL_INDEX_LITE['entries'].keys())[:20]}")
            else:
                umi_debug_print(f"[UmiAI Lite DEBUG] WARNING: entries dict is EMPTY! umi_tags has {len(GLOBAL_INDEX_LITE.get('tags', set()))} items")

        matching_entries = []
        seen_matches = set()
        debug_count = 0
        total_entries_checked = 0
        for tag_lower, entry_list in GLOBAL_INDEX_LITE['entries'].items():
            total_entries_checked += len(entry_list)
            for entry_info in entry_list:
                entry_data = entry_info['data']
                entry_tags = yaml_text_list(entry_data, 'Tags')
                tag_dict = {t.lower(): True for t in entry_tags}

                # Debug: show first few evaluations
                result = evaluator.evaluate(tag_dict)
                if debug_enabled and debug_count < 5:
                    umi_debug_print(f"[UmiAI Lite DEBUG] Checking entry '{entry_info.get('entry_key', 'unknown')}': tag_dict={tag_dict}, expression='{logic_expression}', result={result}")
                    debug_count += 1
                    
                if result:
                    prompts = yaml_text_list(entry_data, 'Prompts')

                    for prompt in prompts:
                        dedupe_key = (
                            entry_info.get('file'),
                            str(entry_info.get('entry_key')),
                            str(prompt),
                        )
                        if dedupe_key in seen_matches:
                            continue
                        seen_matches.add(dedupe_key)
                        matching_entries.append({
                            'value': prompt,
                            'prefix': yaml_joined(entry_data, 'Prefix'),
                            'suffix': yaml_joined(entry_data, 'Suffix'),
                            'neg_prefix': yaml_joined(entry_data, 'Neg_Prefix'),
                            'neg_suffix': yaml_joined(entry_data, 'Neg_Suffix'),
                            'entry_key': entry_info.get('entry_key'),
                            'tags': entry_tags,
                            'description': yaml_joined(entry_data, 'Description'),
                        })

        if not matching_entries:
            # Fix 11: Better error messages - show which logic expression failed to match
            error_msg = f"[NO_MATCHES: {logic_expression}]"
            umi_debug_print(f"[UmiAI Lite DEBUG] Loop complete: checked {total_entries_checked} entries, found {len(matching_entries)} matches for '{logic_expression}'")
            logging.warning(f"[UmiAI Lite] No YAML entries matched logic expression '{logic_expression}'.")
            if self.is_failfast_enabled():
                error_msg = f"<<ERROR_NO_MATCHES:{logic_expression}>>"
            self.seeded_values[cache_key] = error_msg
            self._record_wildcard_trace(
                type="yaml",
                wildcard=logic_expression,
                mode="no_matches",
                count=0,
                values=[],
                result=error_msg,
                error=error_msg,
                available_count=0,
            )
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
        self._record_wildcard_trace(
            type="yaml",
            wildcard=logic_expression,
            mode="logic_tags",
            count=1,
            available_count=len(matching_entries),
            selected_indices=[self._entry_index(matching_entries, selected)],
            entry_key=selected.get('entry_key'),
            values=[result],
            tags=[selected.get('tags', [])],
            result=result,
        )
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
        ESCAPED_WILDCARD = "\u0000UMI_ESC_WILDCARD\u0000"
        ESCAPED_CHOICE = "\u0000UMI_ESC_CHOICE\u0000"

        text = text.replace(r'\__', ESCAPED_WILDCARD)
        text = text.replace(r'\{', ESCAPED_CHOICE)

        def _is_error_result(result):
            return (
                result.startswith("[WILDCARD_NOT_FOUND:")
                or result.startswith("[NO_MATCHES:")
                or result.startswith("[PROMPT_FILE_NOT_FOUND:")
                or result.startswith("[PROMPT_FILE_ERROR:")
                or result.startswith("<<ERROR_")
            )

        def _resolve_wildcard_spec(spec):
            try:
                if spec.kind == "yaml_logic":
                    result = self.tag_selector.select_by_tags(spec.logic)
                elif spec.kind == "file_logic":
                    result = self.tag_selector.select(spec.key, count=1, logic_filter=spec.logic, sequential=spec.sequential)
                elif spec.kind == "range":
                    scope_key = spec.key
                    if scope_key.startswith('@') and ':' in scope_key:
                        scope_key = scope_key[1:].split(':', 1)[0].strip()
                    rng = self.tag_selector.get_rng(scope_key)
                    count = rng.randint(spec.count_min, spec.count_max)
                    result = self.tag_selector.select(spec.key, count, sequential=spec.sequential)
                elif spec.kind == "prompt_file":
                    file_content = self.tag_selector.tag_loader.load_prompt_file(spec.key)
                    result = file_content if file_content else f"[PROMPT_FILE_NOT_FOUND: {spec.key}]"
                else:
                    result = self.tag_selector.select(spec.key, sequential=spec.sequential)
            except Exception as e:
                result = f"[PROMPT_FILE_ERROR: {spec.key}: {str(e)}]" if spec.kind == "prompt_file" else f"<<ERROR_WILDCARD:{spec.key}:{str(e)}>>"

            if spec.fallback and _is_error_result(result):
                return spec.fallback
            return result

        wildcard_specs = parse_wildcard_specs(text)
        if wildcard_specs:
            parts = []
            cursor = 0
            for spec in wildcard_specs:
                if spec.span.start < cursor:
                    continue
                parts.append(text[cursor:spec.span.start])
                parts.append(_resolve_wildcard_spec(spec))
                cursor = spec.span.end
            parts.append(text[cursor:])
            text = "".join(parts)

        def _resolve_angle_yaml_spec(spec):
            expression = spec.key
            expression_lower = expression.lower()
            
            # Check if expression is a direct entry name (Option A: make strings work)
            if expression_lower in GLOBAL_INDEX_LITE['entry_names']:
                entry_info = GLOBAL_INDEX_LITE['entry_names'][expression_lower]
                entry_data = entry_info['data']
                prompts = yaml_text_list(entry_data, 'Prompts')

                if prompts:
                    rng = self.tag_selector.get_rng(expression)
                    selected_prompt = rng.choice(prompts)
                    for field, sink in (
                        ('Prefix', self.tag_selector.prefixes),
                        ('Suffix', self.tag_selector.suffixes),
                        ('Neg_Prefix', self.tag_selector.neg_prefixes),
                        ('Neg_Suffix', self.tag_selector.neg_suffixes),
                    ):
                        text = yaml_joined(entry_data, field)
                        if text:
                            sink.append(text)
                    umi_debug_print(f"[UmiAI Lite DEBUG] <[{expression}]> matched entry name, selected prompt: {selected_prompt[:50]}")
                    return selected_prompt
                else:
                    umi_debug_print(f"[UmiAI Lite DEBUG] <[{expression}]> matched entry name but has no Prompts")
                    return f"[NO_PROMPTS: {expression}]"
            
            # Fallback to logic-based filtering if not a direct entry name
            umi_debug_print(f"[UmiAI Lite DEBUG] <[{expression}]> not a direct entry name, treating as logic filter")
            return self.tag_selector.select_by_tags(expression)

        angle_yaml_specs = parse_angle_yaml_specs(text)
        if angle_yaml_specs:
            parts = []
            cursor = 0
            for spec in angle_yaml_specs:
                if spec.span.start < cursor:
                    continue
                parts.append(text[cursor:spec.span.start])
                parts.append(_resolve_angle_yaml_spec(spec))
                cursor = spec.span.end
            parts.append(text[cursor:])
            text = "".join(parts)

        # If a user accidentally writes "__wildcard____ text", the valid wildcard
        # resolves first and leaves "__ text"; do not let that malformed opener
        # consume everything until the next wildcard on a later pass.
        #
        # Only lines whose delimiters are genuinely unbalanced are touched. The
        # same pattern matches the *closing* "__" of a valid wildcard, so
        # collapsing unconditionally corrupted anything a nested expansion
        # revealed: a wildcard file containing "__a__ tail" became "__a tail"
        # and then resolved to nothing at all.
        def _collapse_dangling(line):
            if line.count("__") % 2 == 0:
                return line
            return re.sub(r'__\s+(?=[A-Za-z0-9])', ' ', line)

        text = "\n".join(_collapse_dangling(line) for line in text.split("\n"))

        # Process function tags ([shuffle:], [clean:])
        text = self.replace_functions(text)

        # Keep escaped syntax escaped across multi-pass prompt expansion. The
        # node restores the literal characters after expansion is complete.
        text = text.replace(ESCAPED_WILDCARD, r'\__')
        text = text.replace(ESCAPED_CHOICE, r'\{')

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
        self.load_trace = []

    def _resolve_lora_path(self, lora_name):
        lora_path = folder_paths.get_full_path("loras", lora_name)

        if lora_path is None:
            all_loras = folder_paths.get_filename_list("loras")
            for lora_file in all_loras:
                lora_base = os.path.splitext(os.path.basename(lora_file))[0]
                if lora_base.lower() == lora_name.lower():
                    lora_path = folder_paths.get_full_path("loras", lora_file)
                    break

        return lora_path

    def _lora_weights_cache_key(self, lora_path):
        try:
            stat = os.stat(lora_path)
            return f"weights_v2|{lora_path}|{stat.st_mtime_ns}|{stat.st_size}"
        except OSError:
            return f"weights_v2|{lora_path}"

    def _load_lora_weights(self, lora_path, cache_limit):
        with PROMPT_CACHE_LOCK:
            return self._load_lora_weights_locked(lora_path, cache_limit)

    def _load_lora_weights_locked(self, lora_path, cache_limit):
        cache_key = self._lora_weights_cache_key(lora_path)

        if cache_limit > 0 and cache_key in LORA_MEMORY_CACHE_LITE:
            LORA_MEMORY_CACHE_LITE.move_to_end(cache_key)
            return LORA_MEMORY_CACHE_LITE[cache_key], True

        lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

        if cache_limit > 0:
            LORA_MEMORY_CACHE_LITE[cache_key] = lora
            LORA_MEMORY_CACHE_LITE.move_to_end(cache_key)

            while len(LORA_MEMORY_CACHE_LITE) > cache_limit:
                oldest_key = next(iter(LORA_MEMORY_CACHE_LITE))
                del LORA_MEMORY_CACHE_LITE[oldest_key]
                gc.collect()
                torch.cuda.empty_cache()

        return lora, False

    def _load_json_file(self, path):
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
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
                        with open(sidecar, 'r', encoding='utf-8-sig') as f:
                            data = json.load(f)
                            # Look for common tag keys
                            tags = data.get("activation text") or data.get("trainedWords") or data.get("tags")
                            if tags:
                                return tags if isinstance(tags, str) else ", ".join(tags)
                    except: continue
            return None

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
                            return [], "safetensors"
                except:
                    pass
            return [], "none"
    
    def extract_and_load(self, text, model, clip, lora_behavior, cache_limit):
        self.load_trace = []
        lora_specs = parse_lora_specs(text)

        lora_info_parts = []
        appended_tags = []
        prepended_tags = []

        if not lora_specs:
            return text, model, clip, ""

        for spec in lora_specs:
            lora_name = spec.name
            tag_options = spec.options or {}

            # Input validation: clamp strength to valid range
            strength = spec.strength
            if strength < -5.0 or strength > 5.0:
                logging.warning(f"[UmiAI Lite] LoRA strength {strength} for '{lora_name}' is out of range. Clamping to [-5.0, 5.0].")
                strength = max(-5.0, min(5.0, strength))

            lora_name = resolve_lora_alias(lora_name, get_all_wildcard_paths())

            trigger_behavior = tag_options.get("triggers") or tag_options.get("trigger") or tag_options.get("tags")
            effective_behavior = lora_behavior
            if trigger_behavior in ("off", "none", "false", "0", "disabled", "disable"):
                effective_behavior = "Disabled"
            elif trigger_behavior in ("append", "on", "true", "1"):
                effective_behavior = "Append to Prompt"
            elif trigger_behavior == "prepend":
                effective_behavior = "Prepend to Prompt"

            if model is not None and clip is not None:
                model, clip = self.load_lora(model, clip, lora_name, strength, cache_limit)
                if self.load_trace:
                    self.load_trace[-1]["trigger_behavior"] = trigger_behavior or ""
                    self.load_trace[-1]["effective_trigger_behavior"] = effective_behavior
            else:
                self.load_trace.append({
                    "lora": lora_name,
                    "strength": strength,
                    "applied": False,
                    "weights_cache_hit": False,
                    "path": self._resolve_lora_path(lora_name) or "",
                    "status": "detected_only",
                    "trigger_behavior": trigger_behavior or "",
                    "effective_trigger_behavior": effective_behavior,
                })
            lora_info_parts.append(f"{lora_name}:{strength}")

            if effective_behavior == "Append to Prompt":
                lora_tags = self.extract_lora_tags(lora_name)
                if lora_tags:
                    appended_tags.append(lora_tags)
            elif effective_behavior == "Prepend to Prompt":
                lora_tags = self.extract_lora_tags(lora_name)
                if lora_tags:
                    prepended_tags.append(lora_tags)

        text = remove_spans(text, [spec.span for spec in lora_specs])
        if prepended_tags:
            text = ", ".join(prepended_tags) + ", " + text
        if appended_tags:
            text = text + ", " + ", ".join(appended_tags)

        lora_info = ", ".join(lora_info_parts) if lora_info_parts else ""

        return text, model, clip, lora_info

    def load_lora(self, model, clip, lora_name, strength, cache_limit):
        trace_item = {
            "lora": lora_name,
            "strength": strength,
            "applied": False,
            "weights_cache_hit": False,
        }
        lora_path = self._resolve_lora_path(lora_name)
        trace_item["path"] = lora_path or ""

        if lora_path is None:
            logging.warning(f"[UmiAI Lite] LoRA not found: {lora_name}")
            trace_item["status"] = "not_found"
            self.load_trace.append(trace_item)
            return model, clip

        try:
            lora, weights_cache_hit = self._load_lora_weights(lora_path, cache_limit)
            trace_item["weights_cache_hit"] = weights_cache_hit

            has_z_image = any('to_k_lora.down.weight' in key for key in lora.keys())

            if has_z_image:
                logging.info(f"[UmiAI Lite] Detected Z-Image format LoRA: {lora_name}. Applying QKV fusion patch...")
                lora = self.apply_qkv_fusion(lora)

            model_patched, clip_patched = comfy.sd.load_lora_for_models(model, clip, lora, strength, strength)
            trace_item["status"] = "applied"
            trace_item["applied"] = True
            self.load_trace.append(trace_item)

            return model_patched, clip_patched

        except Exception as e:
            logging.error(f"[UmiAI Lite] Error loading LoRA {lora_name}: {e}")
            trace_item["status"] = "error"
            trace_item["error"] = str(e)
            self.load_trace.append(trace_item)
            return model, clip

    # apply_qkv_fusion is inherited from LoRAHandlerBase.

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

def _exact_int(value):
    """int() first: going through float rounds seeds above 2**53, so
    neighbouring seeds collapse onto the same roll."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(float(value))


# ==============================================================================
# MAIN NODE CLASS (LITE VERSION)
# ==============================================================================
class UmiAIWildcardNodeLite:
    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False, "tooltip": "Prompt using UmiAI syntax: __wildcards__, {a|b} choices, $variables, [if ...] conditionals, [neg: ...] negatives, <lora:...> tags. See SYNTAX.md."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "tooltip": "Same seed, template, wildcard files and settings reproduce the same expansion. Use the seed control's increment/randomize mode for new rolls; __~name__ cycles by seed."}),
            },
            "optional": {
                # Standard Connections
                "model": ("MODEL", {"tooltip": "Connect to load inline <lora:...> tags into the model."}),
                "clip": ("CLIP", {"tooltip": "Connect together with model to load inline <lora:...> tags."}),

                # Basic Settings
                "lora_tags_behavior": (["Append to Prompt", "Disabled", "Prepend to Prompt"], {"default": "Append to Prompt", "tooltip": "Where to inject LoRA trigger/activation tags into the prompt."}),
                "lora_cache_limit": ("INT", {"default": 5, "min": 0, "max": 50, "step": 1, "tooltip": "How many loaded LoRA weight sets to keep cached in RAM. 0 disables caching."}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192, "tooltip": "Default width output. Overridden by @@width=...@@ in the prompt."}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192, "tooltip": "Default height output. Overridden by @@height=...@@ in the prompt."}),
                "input_negative": ("STRING", {"multiline": True, "forceInput": True, "tooltip": "Optional incoming negative prompt. Wildcards/variables are expanded; extracted negatives are appended to it."}),
            }
        }

        # Add bypass phrases for conditional bypass nodes
        inputs["optional"]["bypass_phrase"] = ("STRING", {"default": "", "multiline": False, "hidden": True})
        inputs["optional"]["bypass_phrases"] = ("STRING", {"default": "", "multiline": False, "placeholder": "simple, test, auto", "tooltip": "Comma-separated phrases matched as whole words, ignoring case, against the processed prompt. Results come out of bypass_matches for Umi Bypass nodes."})

        inputs["optional"]["prompt_profile"] = (list_prompt_profiles(), {"default": "None", "tooltip": "Model-family defaults and lint rules from prompt_profiles.yaml."})
        inputs["optional"]["prompt_preset"] = (["none"] + list_prompt_presets(), {"default": "none", "tooltip": "Named prompt fragment from prompt_presets.yaml applied to this prompt."})
        inputs["optional"]["preset_placement"] = (["append", "prepend", "replace"], {"default": "append", "tooltip": "How the selected preset combines with the prompt text."})
        inputs["optional"]["section_order"] = ("STRING", {"default": "", "multiline": False, "placeholder": "quality, character, style, scene", "tooltip": "Comma-separated order for [section:name] blocks in the prompt."})
        inputs["optional"]["dry_run"] = ("BOOLEAN", {"default": False, "tooltip": "Expand the prompt and report LoRA info without actually loading LoRAs."})
        if get_anima_extension() is not None:
            inputs["optional"]["anima_prompt_mode"] = (
                ["off", "ordered tags", "cohesive prompt"],
                {
                    "default": "off",
                    "tooltip": (
                        "After wildcard expansion, optionally order Anima tags or compose "
                        "the resolved fragments into deterministic visual sentences."
                    ),
                },
            )
            inputs["optional"]["anima_artist_mode"] = (
                ["keep in prompt", "split for artist mixer"],
                {
                    "default": "keep in prompt",
                    "tooltip": (
                        "Split @artist fragments into the artist_chain output for "
                        "Anima Artist Mixer, preventing artist interference in the base prompt."
                    ),
                },
            )


        # Pin carriers for the frozen-reuse path. These MUST stay last.
        # ComfyUI serialises widget values as a positional array, so adding an
        # input anywhere above shifts every later value in every saved
        # workflow. That is exactly how dry_run's False once arrived as
        # _frozen_text and anima_artist_mode's string arrived as _frozen_seed.
        inputs["optional"]["_frozen_text"] = ("STRING", {"default": "", "multiline": True, "tooltip": "Set by the node's Pin button. When present, this exact expansion is reused instead of rolling."})
        inputs["optional"]["_frozen_negative"] = ("STRING", {"default": "", "multiline": True, "tooltip": "Negative half of a pinned roll."})
        # Deliberately STRING, not INT: a workflow saved against an older or
        # mis-ordered definition can carry anything in this slot, and a strict
        # type makes the frontend refuse to queue the graph at all. Accepting
        # anything and coercing server-side turns a hard block into a no-op.
        inputs["optional"]["_frozen_seed"] = ("STRING", {"default": "", "multiline": False, "tooltip": "Seed captured with a pinned roll. Empty means nothing is pinned."})

        return inputs

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "INT", "INT", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "text", "negative_text", "width", "height", "lora_info", "input_text", "input_negative", "bypass_matches", "explain_json", "prompt_diff", "artist_chain")
    FUNCTION = "process"
    CATEGORY = "UmiAI"
    COLOR = "#47325e"

    @classmethod
    def IS_CHANGED(cls, text, seed, **kwargs):
        watched = {
            "text": text,
            "seed": seed,
            "width": kwargs.get("width"),
            "height": kwargs.get("height"),
            "input_negative": kwargs.get("input_negative"),
            "lora_tags_behavior": kwargs.get("lora_tags_behavior"),
            "lora_cache_limit": kwargs.get("lora_cache_limit"),
            "bypass_phrase": kwargs.get("bypass_phrase"),
            "bypass_phrases": kwargs.get("bypass_phrases"),
            "prompt_profile": kwargs.get("prompt_profile"),
            "prompt_preset": kwargs.get("prompt_preset"),
            "preset_placement": kwargs.get("preset_placement"),
            "section_order": kwargs.get("section_order"),
            "dry_run": kwargs.get("dry_run"),
            "anima_prompt_mode": kwargs.get("anima_prompt_mode"),
            "anima_artist_mode": kwargs.get("anima_artist_mode"),
            "settings": {k: UMI_SETTINGS.get(k) for k in sorted(UMI_SETTINGS)},
        }
        watched["wildcards"] = scan_wildcard_files(get_all_wildcard_paths())
        # ComfyUI keeps this value per node; the file listing alone can be
        # hundreds of KiB for a large collection.
        return hashlib.sha256(json.dumps(watched, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

    def extract_settings(self, text):
        settings = {'width': -1, 'height': -1}
        spans = find_settings_spans(text)
        for span in spans:
            for key, val in parse_key_value_csv(span.content).items():
                try:
                    if key == 'width':
                        settings['width'] = int(val)
                    if key == 'height':
                        settings['height'] = int(val)
                except ValueError:
                    pass
        text = remove_spans(text, spans)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\s+([,])', r'\1', text)
        return text.strip(), settings

    def _clamp_dimension(self, value):
        """Hold @@width=...@@ to the same 64-8192 range the widgets enforce.

        An out-of-range value used to pass straight through to the sampler,
        where 99999 is not a slow generation but an allocation failure.
        """
        try:
            value = int(value)
        except (TypeError, ValueError):
            return 1024
        return max(64, min(8192, value))

    def _match_bypass(self, prompt, bypass_phrase="", bypass_phrases=""):
        # Matched without regard to case. "SIMPLE portrait" not matching the
        # phrase "simple" reads as the feature being broken, and a prompt's
        # capitalisation is usually incidental. Whole words only, so "cat"
        # does not match "category".
        haystack = str(prompt or "")

        def found(phrase):
            return re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', haystack, re.IGNORECASE) is not None

        bypass_matched = bool(bypass_phrase) and found(str(bypass_phrase))
        bypass_list = []
        if bypass_phrases:
            phrases = [p.strip() for p in str(bypass_phrases).split(",") if p.strip()]
            bypass_list = [found(phrase) for phrase in phrases]
        return bypass_matched, bypass_list, json.dumps(bypass_list)

    def get_val(self, kwargs, key, default, value_type=None):
        val = kwargs.get(key, default)

        if val is None:
            return default

        if value_type:
            try:
                if value_type == int:
                    return _exact_int(val)
                if value_type == float:
                    return float(val)
                if value_type == str:
                    return str(val)
            except (TypeError, ValueError, OverflowError):
                return default

        return val

    def clean_prompt(self, text):
        """Clean prompt: remove extra commas/spaces, fix BREAK formatting.
        
        - Removes multiple consecutive commas
        - Removes extra spaces
        - Removes commas before and after BREAK
        - Ensures one space before and after BREAK
        """
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

    def format_prompt(self, text, auto_clean=None):
        if auto_clean is None:
            auto_clean = UMI_SETTINGS.get('auto_clean', True)
        def format_segment(segment):
            if auto_clean:
                return self.clean_prompt(segment)
            return re.sub(r'\s+', ' ', re.sub(r',\s*,', ',', segment)).strip().strip(',')
        if UMI_SETTINGS.get('preserve_newlines', False):
            return '\n'.join(format_segment(line) for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n')).strip()
        return format_segment(text)

    def _expand_prompt_core(self, text, tag_loader, options, seed, error_lint=False,
                            auto_clean=True, base_variables=None):
        tag_selector = TagSelector(tag_loader, options)
        neg_gen = NegativePromptGenerator()
        tag_replacer = TagReplacer(tag_selector)
        dynamic_replacer = DynamicPromptReplacer(seed)
        conditional_replacer = ConditionalReplacer()
        variable_replacer = VariableReplacer()

        globals_dict = tag_loader.load_globals()
        variable_replacer.load_globals(globals_dict)
        if base_variables:
            variable_replacer.variables.update(base_variables)
        tag_selector.update_variables(variable_replacer.variables)

        if error_lint:
            variable_replacer.variables['fail_fast'] = '1'
            variable_replacer.variables['failfast'] = '1'
            tag_selector.variables['fail_fast'] = '1'
            tag_selector.variables['failfast'] = '1'

        prompt, iterations, core_warnings = self._expand_loop(
            text, tag_loader, tag_selector, tag_replacer, dynamic_replacer,
            conditional_replacer, variable_replacer,
        )

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

        prompt = neg_gen.strip_negative_tags(prompt, variable_replacer.variables)

        prompt = self.format_prompt(prompt, auto_clean)

        if tag_selector.is_trace_enabled():
            prompt = append_trace_summary(prompt, variable_replacer.variables)
        if tag_selector.is_debug_enabled():
            prompt = append_debug_summary(prompt, variable_replacer.variables)


        return {
            "prompt": prompt,
            "iterations": iterations,
            "warnings": list(dict.fromkeys(core_warnings + tag_selector.diagnostics)),
            "negative_generator": neg_gen,
            "tag_selector": tag_selector,
            "variable_replacer": variable_replacer,
        }

    def _expand_loop(self, prompt, tag_loader, tag_selector, tag_replacer, dynamic_replacer,
                     conditional_replacer, variable_replacer):
        """Expand until the text stops changing. Returns (prompt, iterations, warnings)."""
        warnings = []
        previous_prompt = ""
        iterations = 0
        prompt_history = []
        tag_selector.clear_seeded_values()
        conditional_replacer.set_value_replacers(tag_replacer, dynamic_replacer)

        iteration_limit = _processing_limit('max_expansion_iterations', 50, 1, 200)
        while previous_prompt != prompt and iterations < iteration_limit:
            _check_prompt_size(prompt)
            if prompt in prompt_history:
                warnings.append(
                    f"Cycle detected during prompt expansion; stopped early near: {prompt[:80]}"
                )
                logging.warning(f"[UmiAI Lite] Cycle detected in prompt expansion; stopped near: {prompt[:100]}")
                break

            prompt_history.append(prompt)
            previous_prompt = prompt
            prompt = expand_prompt_files(prompt, tag_loader)
            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)

            masked_prompt, if_blocks = conditional_replacer.mask_conditionals(prompt)
            masked_prompt = CharacterReplacer.replace(masked_prompt)
            masked_prompt = tag_replacer.replace(masked_prompt)
            masked_prompt = dynamic_replacer.replace(masked_prompt)

            prompt = conditional_replacer.unmask_conditionals(masked_prompt, if_blocks)
            prompt = conditional_replacer.replace(prompt, variable_replacer.variables)
            # $@name worked only inside a conditional branch; at top level the
            # assignment was left in the prompt as literal text. Applied after
            # conditionals so a branch that was not taken cannot leak its
            # locals out.
            prompt = conditional_replacer.apply_local_vars(prompt, variable_replacer.variables)
            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            tag_selector.update_variables(variable_replacer.variables)
            prompt = variable_replacer.replace_variables(prompt)
            iterations += 1
            _check_prompt_size(prompt)

        if iterations >= iteration_limit and previous_prompt != prompt:
            warnings.append(
                f"Reached maximum prompt expansion iterations ({iteration_limit}); possible recursive wildcards or variables."
            )

        # A wildcard file that refers to itself is a fixed point, not a cycle:
        # the text stops changing, so the loop exits normally and the history
        # check above never fires. The raw "__name__" then goes to the model
        # verbatim with nothing said about it. Anything left at this point is
        # unresolved, whatever the reason, so report it. A lone "__" (as in
        # ^__^ or a LoRA file name) is not wildcard syntax.
        checked = remove_spans(prompt, find_lora_spans(prompt))
        unresolved = [span for span in find_wildcard_spans(checked) if not checked[:span.start].endswith("\\")]
        if unresolved:
            at = unresolved[0].start
            warnings.append(
                "Prompt still contains unresolved wildcard syntax after expansion "
                "(a wildcard file may refer to itself, or the file may be missing). "
                "Near: " + checked[at:at + 80]
            )

        prompt = conditional_replacer.replace(prompt, variable_replacer.variables)
        prompt = prompt.replace(r'\__', '__').replace(r'\{', '{')
        return prompt, iterations, warnings

    def _process_negative_input(self, negative_text, tag_loader, options, seed, base_variables, warnings):
        """Expand wildcards/variables in the negative input without affecting positive prompt state."""
        negative_text = strip_prompt_comments(negative_text or "")
        if not negative_text.strip():
            return ""

        neg_selector = TagSelector(tag_loader, options)
        variable_replacer = VariableReplacer()
        variable_replacer.variables.update(base_variables or {})
        neg_selector.update_variables(variable_replacer.variables)

        prompt, _, loop_warnings = self._expand_loop(
            negative_text, tag_loader, neg_selector, TagReplacer(neg_selector),
            DynamicPromptReplacer(seed), ConditionalReplacer(), variable_replacer,
        )
        warnings.extend(f"Negative prompt: {message}" for message in loop_warnings + neg_selector.diagnostics)
        return self.format_prompt(prompt)

    def process(self, **kwargs):
        # HTTP wildcard refreshes can run independently of Comfy's execution
        # queue. Hold one re-entrant lock for the complete expansion so a
        # refresh can never clear an index while this node is reading it.
        with PROMPT_CACHE_LOCK:
            return self._process_locked(**kwargs)

    def _process_locked(self, **kwargs):
        # Check for frozen text from auto-requeue (bypass wildcard processing)
        # Coerced rather than trusted: a positionally misaligned workflow can
        # deliver a bool here and a string in the seed, and a crash mid-graph is
        # a far worse outcome than ignoring an unusable pin.
        frozen_text = kwargs.get("_frozen_text", None)
        if not isinstance(frozen_text, str) or not frozen_text.strip():
            frozen_text = None
        frozen_negative = kwargs.get("_frozen_negative", None)
        if not isinstance(frozen_negative, str):
            frozen_negative = None
        frozen_seed = kwargs.get("_frozen_seed", None)
        if isinstance(frozen_seed, str) and not frozen_seed.strip():
            frozen_seed = None
        if frozen_seed is not None:
            try:
                frozen_seed = _exact_int(frozen_seed)
            except (TypeError, ValueError, OverflowError):
                frozen_seed = None

        if frozen_text:
            umi_debug_print("[UmiAI Lite] Using frozen prompt (skipping wildcard expansion)")

            # Get basic parameters
            model = kwargs.get("model", None)
            clip = kwargs.get("clip", None)
            width = self.get_val(kwargs, "width", 1024, int)
            height = self.get_val(kwargs, "height", 1024, int)
            lora_tags_behavior = self.get_val(kwargs, "lora_tags_behavior", "Append to Prompt", str)
            lora_cache_limit = self.get_val(kwargs, "lora_cache_limit", 5, int)
            bypass_phrase = kwargs.get("bypass_phrase", "")
            bypass_phrases = kwargs.get("bypass_phrases", "")
            anima_extension = get_anima_extension()
            anima_artist_mode = self.get_val(kwargs, "anima_artist_mode", "keep in prompt", str)

            # Use frozen values
            prompt = frozen_text
            final_negative = frozen_negative if frozen_negative else ""
            seed = frozen_seed if (frozen_seed is not None and frozen_seed >= 0) else self.get_val(kwargs, "seed", 0, int)
            artist_chain = ""
            if anima_extension is not None:
                prompt, artist_chain = anima_extension.split_artist_chain(
                    prompt,
                    remove=anima_artist_mode.lower().startswith("split"),
                )

            # Matched before LoRA extraction, as an unpinned run does, so pinning
            # a roll cannot flip a downstream bypass.
            bypass_matched, bypass_list, bypass_matches = self._match_bypass(prompt, bypass_phrase, bypass_phrases)

            # Still need to extract LoRAs from the frozen prompt
            lora_handler = LoRAHandler()
            prompt_before_lora = prompt
            prompt, final_model, final_clip, lora_info = lora_handler.extract_and_load(
                prompt, model, clip, lora_tags_behavior, lora_cache_limit
            )

            # Extract settings
            prompt, settings = self.extract_settings(prompt)
            final_width = self._clamp_dimension(settings['width'] if settings['width'] > 0 else width)
            final_height = self._clamp_dimension(settings['height'] if settings['height'] > 0 else height)
            prompt = self.format_prompt(prompt)

            prompt_diff = json.dumps(build_prompt_diff(frozen_text, prompt), indent=2, ensure_ascii=False)
            explain = {
                "schema_version": "umi.run_explain.v1",
                "dry_run": False,
                "frozen": True,
                "seed": seed,
                "input_prompt": frozen_text,
                "processed_prompt_before_lora": prompt_before_lora,
                "final_prompt": prompt,
                "phases": {
                    "input": frozen_text,
                    "before_lora": prompt_before_lora,
                    "after_lora": prompt,
                    "final": prompt,
                },
                "negative_prompt": final_negative,
                "warnings": [],
                "artist_chain": artist_chain,
                "lora_info": lora_info,
                "lora_load_trace": list(getattr(lora_handler, "load_trace", [])),
                "bypass_matches": bypass_list,
                "settings": {
                    "width": final_width,
                    "height": final_height,
                    "auto_clean": UMI_SETTINGS.get('auto_clean', True),
                },
            }
            explain_json = json.dumps(explain, indent=2, ensure_ascii=False, default=str)

            if UMI_SETTINGS.get("persist_prompt_history", False):
                log_prompt_to_history(prompt, final_negative, seed)
            if UMI_SETTINGS.get("persist_run_inspector", False):
                try:
                    _write_run_inspector_cache({
                        "explain": explain,
                        "prompt_diff": json.loads(prompt_diff),
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    })
                except Exception:
                    pass

            # Return immediately with frozen values
            umi_debug_print(f"[UmiAI Lite] Returning frozen prompt (bypass_matched={bypass_matched})")
            return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info, frozen_text, frozen_negative or "", bypass_matches, explain_json, prompt_diff, artist_chain)

        text = self.get_val(kwargs, "text", "", str)
        seed = self.get_val(kwargs, "seed", 0, int)
        original_text = text

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
        auto_clean = UMI_SETTINGS.get('auto_clean', True)
        error_lint = UMI_SETTINGS.get('error_lint', False)
        use_folder_paths = UMI_SETTINGS.get('use_folder_paths', False)
        input_negative = self.get_val(kwargs, "input_negative", "", str)
        original_negative = input_negative
        prompt_profile = self.get_val(kwargs, "prompt_profile", "None", str)
        prompt_preset = self.get_val(kwargs, "prompt_preset", "none", str)
        preset_placement = self.get_val(kwargs, "preset_placement", "append", str)
        section_order = self.get_val(kwargs, "section_order", "", str)
        dry_run = bool(kwargs.get("dry_run", False))
        anima_prompt_mode = self.get_val(
            kwargs, "anima_prompt_mode", "off", str
        )
        anima_artist_mode = self.get_val(
            kwargs, "anima_artist_mode", "keep in prompt", str
        )

        umi_debug_print(f"[UmiAI Lite] Processing with: auto_clean={auto_clean}, error_lint={error_lint}")

        # ============================================================
        # CORE PROCESSING
        # ============================================================

        preset_warnings = []
        phases = {"input": original_text}
        text = expand_prompt_presets(text)
        text, input_negative, preset_warnings = apply_prompt_preset(text, input_negative, prompt_preset, preset_placement)
        phases["after_presets"] = text

        # Recompose named sections before normal wildcard processing.
        text, section_info = apply_prompt_sections(text, section_order)
        phases["after_sections"] = text

        boundary_warnings = lint_prompt_join_boundaries(text)
        # Strip comments: // toggles comment mode until newline or another //
        text = strip_prompt_comments(text)
        phases["after_comments"] = text

        options = {
            'verbose': False,
            'seed': seed,
            'use_folder_paths': use_folder_paths,
            'rng_streams': UMI_SETTINGS.get('rng_streams', False),
        }

        all_wildcard_paths = get_all_wildcard_paths()
        tag_loader = TagLoader(all_wildcard_paths, options)

        lora_handler = LoRAHandler()

        expanded = self._expand_prompt_core(
            text,
            tag_loader,
            options,
            seed,
            error_lint=error_lint,
            auto_clean=auto_clean,
        )
        prompt = expanded["prompt"]
        phases["after_core_expansion"] = prompt
        iterations = expanded["iterations"]
        neg_gen = expanded["negative_generator"]
        tag_selector = expanded["tag_selector"]
        variable_replacer = expanded["variable_replacer"]

        negative_warnings = []
        input_negative = self._process_negative_input(
            input_negative,
            tag_loader,
            options,
            seed,
            variable_replacer.variables,
            warnings=negative_warnings,
        )

        if prompt_profile != "None":
            # Profile warnings are computed once below via lint_prompt_profile,
            # after negatives and LoRA info are final.
            prompt, input_negative, _, prompt_profile = apply_named_prompt_profile(prompt_profile, prompt, input_negative)
        phases["after_profile"] = prompt

        anima_extension = get_anima_extension()
        artist_chain = ""
        anima_composition = {}
        if anima_extension is not None:
            prompt, artist_chain, anima_composition = anima_extension.compose_wildcard_prompt(
                prompt,
                wildcard_trace=getattr(tag_selector, "wildcard_trace", []),
                mode=anima_prompt_mode,
                artist_mode=anima_artist_mode,
            )
        phases["after_anima_composition"] = prompt

        # Calculate bypass_matched for conditional bypass nodes before LoRA extraction
        bypass_phrase = kwargs.get("bypass_phrase", "")
        bypass_phrases = kwargs.get("bypass_phrases", "")
        bypass_matched, bypass_list, bypass_matches = self._match_bypass(prompt, bypass_phrase, bypass_phrases)

        prompt_before_lora = prompt
        phases["before_lora"] = prompt_before_lora
        if dry_run:
            # Detect LoRAs and apply their trigger-tag behaviour exactly as a
            # real run would, but pass no model/clip so weights are never read
            # or applied.  The old regex-only removal made Preview Roll drift
            # from execution and meant a pinned preview lost every LoRA tag.
            prompt, _, _, detected_loras = lora_handler.extract_and_load(
                prompt, None, None, lora_tags_behavior, lora_cache_limit
            )
            final_model, final_clip = model, clip
            lora_info = f"DRY_RUN: {detected_loras}" if detected_loras else "DRY_RUN"
            prompt = self.format_prompt(prompt, auto_clean)
        else:
            prompt, final_model, final_clip, lora_info = lora_handler.extract_and_load(prompt, model, clip, lora_tags_behavior, lora_cache_limit)
            prompt = self.format_prompt(prompt, auto_clean)
        phases["after_lora"] = prompt

        # Generated terms already in the incoming negative (typed or from a
        # profile) are dropped; the incoming text itself is kept verbatim.
        existing_negatives = {term.lower() for term in _split_prompt_tags(input_negative)}
        generated_negatives = ", ".join(
            term for term in _dedupe_keep_order(_split_prompt_tags(neg_gen.get_negative_string()))
            if term.lower() not in existing_negatives
        )
        final_negative = input_negative
        if generated_negatives:
            final_negative = f"{final_negative}, {generated_negatives}" if final_negative else generated_negatives
        if final_negative:
            final_negative = re.sub(r',\s*,', ',', final_negative).strip()

        profile_warnings = lint_prompt_profile(prompt_profile, prompt, final_negative, lora_info)
        expansion_warnings = expanded.get("warnings", [])
        all_warnings = list(dict.fromkeys(boundary_warnings + preset_warnings + profile_warnings + expansion_warnings + negative_warnings))

        # Extract settings
        prompt, settings = self.extract_settings(prompt)
        prompt = self.format_prompt(prompt, auto_clean)
        final_width = self._clamp_dimension(settings['width'] if settings['width'] > 0 else width)
        final_height = self._clamp_dimension(settings['height'] if settings['height'] > 0 else height)
        phases["final"] = prompt

        if UMI_SETTINGS.get("persist_prompt_history", False):
            log_prompt_to_history(prompt, final_negative, seed)

        if bypass_phrase:
            umi_debug_print(f"[Wildcard] Bypass phrase '{bypass_phrase}' {'FOUND' if bypass_matched else 'NOT FOUND'} in prompt")

        prompt_diff = json.dumps(build_prompt_diff(original_text, prompt), indent=2, ensure_ascii=False)
        explain = {
            "schema_version": "umi.run_explain.v1",
            "dry_run": dry_run,
            "profile": prompt_profile,
            "seed": seed,
            "iterations": iterations,
            "input_prompt": original_text,
            "section_order": section_info.get("order", []),
            "sections": section_info.get("sections", {}),
            "processed_prompt_before_lora": prompt_before_lora,
            "final_prompt": prompt,
            "phases": phases,
            "negative_prompt": final_negative,
            "lora_info": lora_info,
            "lora_load_trace": list(getattr(lora_handler, "load_trace", [])),
            "bypass_matches": bypass_list,
            "variables": dict(variable_replacer.variables),
            "wildcard_resolutions": dict(tag_selector.seeded_values),
            "wildcard_trace": list(getattr(tag_selector, "wildcard_trace", [])),
            "anima_composition": anima_composition,
            "artist_chain": artist_chain,
            "warnings": all_warnings,
            "prompt_preset": prompt_preset,
            "settings": {"width": final_width, "height": final_height, "auto_clean": auto_clean},
        }
        explain_json = json.dumps(explain, indent=2, ensure_ascii=False, default=str)
        if UMI_SETTINGS.get("persist_run_inspector", False):
            try:
                _write_run_inspector_cache({
                    "explain": explain,
                    "prompt_diff": json.loads(prompt_diff),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                })
            except Exception:
                pass

        return (final_model, final_clip, prompt, final_negative, final_width, final_height, lora_info, original_text, original_negative, bypass_matches, explain_json, prompt_diff, artist_chain)


# ==============================================================================
# PROMPT PROFILE HELPER NODE
# ==============================================================================
class UmiPromptProfile:
    @classmethod
    def INPUT_TYPES(s):
        optional = {
            "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
        }
        if get_anima_extension() is not None:
            optional["style_preset"] = ([
                "none", "anime illustration", "clean lineart", "painterly",
                "official art", "flat color", "high detail"
            ], {"default": "none"})
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "profile": (list_prompt_profiles(), {"default": "None"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative_prompt", "warnings", "profile")
    FUNCTION = "run"
    CATEGORY = "UmiAI/prompt"
    COLOR = "#47325e"

    def run(self, prompt, profile="None", negative_prompt="", style_preset="none"):
        prompt, negative_prompt, warnings, resolved_profile = apply_named_prompt_profile(
            profile, prompt, negative_prompt, style_preset=style_preset
        )
        return (prompt, negative_prompt, "\n".join(warnings), resolved_profile)


# ==============================================================================
# PROMPT INSPECTOR NODE
# ==============================================================================
class UmiPromptInspector:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_prompt": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "processed_prompt": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "profile": (list_prompt_profiles(), {"default": "None"}),
            },
            "optional": {
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "lora_info": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("diff_json", "lint_warnings", "sections_json")
    FUNCTION = "run"
    CATEGORY = "UmiAI/prompt"
    COLOR = "#47325e"

    def run(self, input_prompt, processed_prompt, profile="None", negative_prompt="", lora_info=""):
        diff = build_prompt_diff(input_prompt, processed_prompt)
        warnings = lint_prompt_profile(profile, processed_prompt, negative_prompt, lora_info)
        sections = apply_prompt_sections(input_prompt, "")[1]
        return (
            json.dumps(diff, indent=2, ensure_ascii=False),
            "\n".join(warnings),
            json.dumps(sections, indent=2, ensure_ascii=False),
        )


# ==============================================================================
# PROMPT SYNTAX LINT NODE
# ==============================================================================
class UmiPromptSyntaxLint:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": False}),
            },
            "optional": {
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "profile": (list_prompt_profiles(), {"default": "None"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("errors", "warnings", "report_json")
    FUNCTION = "run"
    CATEGORY = "UmiAI/prompt"
    COLOR = "#47325e"

    def run(self, prompt, negative_prompt="", profile="None"):
        report = lint_prompt_syntax(
            prompt, negative_prompt, profile, wildcard_paths=get_all_wildcard_paths()
        )
        return (
            "\n".join(report.get("errors", [])),
            "\n".join(report.get("warnings", []) + report.get("notes", [])),
            json.dumps(report, indent=2, ensure_ascii=False),
        )


# ==============================================================================
# PROMPT PRESET HELPER NODE
# ==============================================================================
class UmiPromptPreset:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "preset": (list_prompt_presets(), {"default": list_prompt_presets()[0]}),
                "placement": (["append", "prepend", "replace"], {"default": "append"}),
            },
            "optional": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative_prompt", "notes")
    FUNCTION = "run"
    CATEGORY = "UmiAI/prompt"
    COLOR = "#47325e"

    def run(self, preset, placement="append", prompt="", negative_prompt=""):
        prompt, negative_prompt, notes = apply_prompt_preset(prompt, negative_prompt, preset, placement)
        return (prompt, negative_prompt, "\n".join(notes))


# ==============================================================================
# ANIMA PROMPT HELPER NODE
# ==============================================================================
class UmiAnimaPromptHelper:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "mode": (["profile", "order_only", "natural_language"], {"default": "profile"}),
                "style_preset": ([
                    "none", "anime illustration", "clean lineart", "painterly",
                    "official art", "flat color", "high detail"
                ], {"default": "none"}),
                "add_default_negative": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative_prompt", "warnings")
    FUNCTION = "run"
    CATEGORY = "UmiAI/prompt"
    COLOR = "#47325e"

    def run(self, prompt, mode="profile", style_preset="none", add_default_negative=True, negative_prompt=""):
        anima_extension = get_anima_extension()
        if anima_extension is None:
            raise RuntimeError("The C-UMI Anima/edit overlay is not installed")
        if mode == "natural_language":
            expanded = anima_extension.expand_natural_language(prompt)
            processed_prompt, processed_negative, warnings = anima_extension.apply_profile(
                expanded,
                negative_prompt,
                mode="profile" if add_default_negative else "prefix",
                style_preset=style_preset,
            )
        elif mode == "order_only":
            processed_prompt = anima_extension.order_prompt(prompt, style_preset=style_preset, add_prefix=False)
            processed_negative = negative_prompt or ""
            _, profile_negative, warnings = anima_extension.apply_profile(
                processed_prompt,
                processed_negative,
                mode="negative" if add_default_negative else "order",
                style_preset="none",
            )
            if add_default_negative:
                processed_negative = profile_negative
        else:
            processed_prompt, processed_negative, warnings = anima_extension.apply_profile(
                prompt,
                negative_prompt,
                mode="profile" if add_default_negative else "prefix",
                style_preset=style_preset,
            )

        return (processed_prompt, processed_negative, "\n".join(warnings))


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
                "matched": ("BOOLEAN", {"default": True}),
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
            matched=True, image=None, latent=None, conditioning=None, model=None, clip=None, string=None):

        effective_matched = bool(matched)
        if matched_list:
            try:
                parsed = matched_list
                if isinstance(matched_list, str):
                    parsed = json.loads(matched_list)
                if isinstance(parsed, list):
                    effective_matched = False
                    if 0 <= int(match_index) < len(parsed):
                        effective_matched = bool(parsed[int(match_index)])
            except Exception:
                pass


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
            umi_debug_print(f"[UmiTextBypass] Sent precheck signal: matched={effective_matched}")
        except Exception as e:
            logging.warning(f"[UmiTextBypass] Failed to send precheck: {e}")

        # Send matched status to frontend immediately
        try:
            from server import PromptServer
            PromptServer.instance.send_sync(
                "umi_bypass_signal",
                {"matched": effective_matched, "backend_controls": backend_controls, "needs_restart": needs_restart},
            )
            umi_debug_print(f"[UmiTextBypass] Sent bypass signal: matched={effective_matched}, backend_controls={backend_controls}")
        except Exception as e:
            logging.warning(f"[UmiTextBypass] Failed to send signal: {e}")

        # If ExecutionBlocker is available, stop downstream execution immediately
        if not effective_matched and blocker_cls is not None:
            try:
                # ComfyUI's ExecutionBlocker takes a message; None blocks silently.
                blocker = blocker_cls(None)
            except TypeError:
                blocker = blocker_cls()
            umi_debug_print("[UmiTextBypass] Blocking downstream execution via ExecutionBlocker")
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
        umi_debug_print(f"[UmiTextBypass] {status} - passing through {passthrough_type}")
        if blocker_cls is None:
            umi_debug_print("[UmiTextBypass] Note: ExecutionBlocker unavailable - frontend bypass may be used")
        return (out_image, out_latent, out_conditioning, out_model, out_clip, out_string)


class UmiBypassModelSwitch:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "matched_list": ("STRING", {"default": "", "multiline": False, "forceInput": True}),
                "match_index": ("INT", {"default": 0, "min": 0, "max": 1024, "step": 1}),
            },
            "optional": {
                "base_model": ("MODEL", {"lazy": True}),
                "reference_model": ("MODEL", {"lazy": True}),
            },
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "run"
    CATEGORY = "UmiAI"

    @staticmethod
    def _is_matched(matched_list=None, match_index=0):
        if not matched_list:
            return False
        try:
            parsed = json.loads(matched_list) if isinstance(matched_list, str) else matched_list
            if isinstance(parsed, list) and 0 <= int(match_index) < len(parsed):
                return bool(parsed[int(match_index)])
        except Exception:
            pass
        return False

    def check_lazy_status(self, matched_list=None, match_index=0, base_model=None, reference_model=None):
        if self._is_matched(matched_list, match_index):
            return ["reference_model"] if reference_model is None else []
        return ["base_model"] if base_model is None else []

    def run(self, matched_list=None, match_index=0, base_model=None, reference_model=None):
        if self._is_matched(matched_list, match_index):
            return (reference_model,)
        return (base_model,)

# Node registration lives in the package __init__.py (CORE_NODE_CLASS_MAPPINGS).
