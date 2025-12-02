import os
import random
import re
import yaml
import glob
import json
import requests
from collections import Counter
import folder_paths
import comfy.sd
import comfy.utils
import torch # Required for Z-Image Matrix Math

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

ALL_KEY = 'all yaml files'

def get_index(items, item):
    try:
        return items.index(item)
    except Exception:
        return None

def parse_tag(tag):
    tag = tag.replace("__", "").replace('<', '').replace('>', '').strip()
    if tag.startswith('#'):
        return tag
    return tag

def read_file_lines(file):
    f_lines = file.read().splitlines()
    lines = []
    for line in f_lines:
        line = line.strip()
        if not line: continue
        if line.startswith('#'): continue
        if '#' in line:
            line = line.split('#')[0].strip()
        lines.append(line)
    return lines

def parse_wildcard_range(range_str, num_variants):
    if range_str is None: return 1, 1
    
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
    if not lines: return ""
    if tag.startswith('#'): return "" # Fixed: Return empty string instead of None
    
    if "$$" not in tag:
        selected = random.choice(lines)
        if '#' in selected: selected = selected.split('#')[0].strip()
        return selected
        
    range_str, tag_name = tag.split("$$", 1)
    try:
        low, high = parse_wildcard_range(range_str, len(lines))
        num_items = random.randint(low, high)
        if num_items == 0: return ""
            
        selected = random.sample(lines, min(num_items, len(lines)))
        selected = [line.split('#')[0].strip() if '#' in line else line for line in selected]
        return ", ".join(selected)
    except Exception as e:
        print(f"Error processing wildcard range: {e}")
        selected = random.choice(lines)
        if '#' in selected: selected = selected.split('#')[0].strip()
        return selected

# ==============================================================================
# CORE CLASSES
# ==============================================================================

class TagLoader:
    def __init__(self, wildcard_path, options):
        self.files = []
        self.wildcard_location = wildcard_path
        self.loaded_tags = {}
        self.yaml_entries = {}
        self.ignore_paths = options.get('ignore_paths', True)
        self.verbose = options.get('verbose', False)
        
        self.all_txt_files = glob.glob(os.path.join(self.wildcard_location, '**/*.txt'), recursive=True)
        self.all_yaml_files = glob.glob(os.path.join(self.wildcard_location, '**/*.yaml'), recursive=True)
        self.txt_basename_to_path = {os.path.basename(file).lower().split('.')[0]: file for file in self.all_txt_files}
        self.yaml_basename_to_path = {os.path.basename(file).lower().split('.')[0]: file for file in self.all_yaml_files}

    def load_globals(self):
        global_path = os.path.join(self.wildcard_location, 'globals.yaml')
        if os.path.exists(global_path):
            try:
                with open(global_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return {str(k): str(v) for k, v in data.items()}
            except Exception as e:
                print(f"[UmiAI] Error loading globals.yaml: {e}")
        return {}

    def process_yaml_entry(self, title, entry_data):
        return {
            'title': title,
            'description': entry_data.get('Description', [None])[0] if isinstance(entry_data.get('Description', []), list) else None,
            'prompts': entry_data.get('Prompts', []),
            'prefixes': entry_data.get('Prefix', []),
            'suffixes': entry_data.get('Suffix', []),
            'tags': [x.lower().strip() for x in entry_data.get('Tags', [])]
        }

    def load_tags(self, file_path, verbose=False, cache_files=True):
        if cache_files and self.loaded_tags.get(file_path):
            return self.loaded_tags.get(file_path)

        txt_full_file_path = os.path.join(self.wildcard_location, f'{file_path}.txt')
        yaml_full_file_path = os.path.join(self.wildcard_location, f'{file_path}.yaml')
        
        txt_file_match = self.txt_basename_to_path.get(file_path.lower()) or txt_full_file_path
        yaml_file_match = self.yaml_basename_to_path.get(file_path.lower()) or yaml_full_file_path
        
        txt_file_path = txt_file_match if self.ignore_paths else txt_full_file_path
        yaml_file_path = yaml_file_match if self.ignore_paths else yaml_full_file_path

        key = ALL_KEY if file_path == ALL_KEY else (os.path.basename(file_path.lower()) if self.ignore_paths else file_path)

        if self.wildcard_location and os.path.isfile(txt_file_path):
            with open(txt_file_path, encoding="utf8") as file:
                self.files.append(f"{file_path}.txt")
                self.loaded_tags[key] = read_file_lines(file)
                if self.ignore_paths:
                    self.loaded_tags[os.path.basename(file_path.lower())] = self.loaded_tags[key]

        if key is ALL_KEY and self.wildcard_location:
            files = glob.glob(os.path.join(self.wildcard_location, '**/*.yaml'), recursive=True)
            output = {}
            for fp in files:
                if os.path.basename(fp) == 'globals.yaml': continue
                
                with open(fp, encoding="utf8") as file:
                    self.files.append(f"{fp}.yaml")
                    try:
                        data = yaml.safe_load(file)
                        if isinstance(data, dict):
                            for title, entry in data.items():
                                if isinstance(entry, dict):
                                    processed_entry = self.process_yaml_entry(title, entry)
                                    if processed_entry['tags']:
                                        output[title] = set(processed_entry['tags'])
                                        self.yaml_entries[title] = processed_entry
                    except Exception as e:
                        if verbose: print(f'Error parsing YAML {fp}: {e}')
            self.loaded_tags[key] = output

        if self.wildcard_location and os.path.isfile(yaml_file_path):
            with open(yaml_file_path, encoding="utf8") as file:
                self.files.append(f"{file_path}.yaml")
                try:
                    data = yaml.safe_load(file)
                    output = {}
                    for title, entry in data.items():
                        if isinstance(entry, dict):
                            processed_entry = self.process_yaml_entry(title, entry)
                            if processed_entry['tags']:
                                output[title] = set(processed_entry['tags'])
                                self.yaml_entries[title] = processed_entry
                    self.loaded_tags[key] = output
                except Exception as e:
                    if verbose: print(f'Error parsing YAML {yaml_file_path}: {e}')

        return self.loaded_tags.get(key, [])

    def get_entry_details(self, title):
        return self.yaml_entries.get(title)

class TagSelector:
    def __init__(self, tag_loader, options):
        self.tag_loader = tag_loader
        self.previously_selected_tags = {}
        self.used_values = {}
        self.selected_options = options.get('selected_options', {})
        self.verbose = options.get('verbose', False)
        self.cache_files = options.get('cache_files', True)
        self.seeded_values = {}
        self.processing_stack = set()
        self.resolved_seeds = {}
        self.selected_entries = {}

    def clear_seeded_values(self):
        self.seeded_values = {}
        self.resolved_seeds = {}
        self.processing_stack.clear()
        self.selected_entries.clear()

    def get_tag_choice(self, parsed_tag, tags):
        if not isinstance(tags, list): return ""
        
        seed_match = re.match(r'#([0-9|]+)\$\$(.*)', parsed_tag)
        if seed_match:
            seed_options = seed_match.group(1).split('|')
            chosen_seed = random.choice(seed_options)
            
            if chosen_seed in self.seeded_values:
                selected = self.seeded_values[chosen_seed]
                return self.resolve_wildcard_recursively(selected, chosen_seed)
            
            if len(tags) == 1:
                selected = tags[0]
            else:
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

        return selected if selected is not None else ""

    def resolve_wildcard_recursively(self, value, seed_id=None):
        if not value: return ""
        if value.startswith('__') and value.endswith('__'):
            nested_tag = value[2:-2]
            nested_seed = f"{seed_id}_{nested_tag}" if seed_id else None
            
            if nested_tag in self.processing_stack: return value
            self.processing_stack.add(nested_tag)
            
            if nested_seed and nested_seed in self.resolved_seeds:
                resolved = self.resolved_seeds[nested_seed]
            else:
                resolved = self.select(nested_tag)
                if nested_seed: self.resolved_seeds[nested_seed] = resolved
            
            self.processing_stack.remove(nested_tag)
            return resolved
        return value

    def get_tag_group_choice(self, parsed_tag, groups, tags):
        if not isinstance(tags, dict): return ""
        
        neg_groups = {x.replace('--', '').strip().lower() for x in groups if x.startswith('--')}
        pos_groups = {x.strip().lower() for x in groups if not x.startswith('--') and '|' not in x}
        any_groups = [{y.strip() for y in x.lower().split('|')} for x in groups if '|' in x]

        candidates = []
        for title, tag_set in tags.items():
            if not pos_groups.issubset(tag_set): continue
            if not neg_groups.isdisjoint(tag_set): continue
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
        if self.previously_selected_tags.get(tag) > 500: # Loop protection
            return f"LOOP_ERROR({tag})"
        
        self.previously_selected_tags[tag] += 1
        parsed_tag = parse_tag(tag)
        
        if '$$' in parsed_tag and not parsed_tag.startswith('#'):
            range_part, file_part = parsed_tag.split('$$', 1)
            if any(c.isdigit() for c in range_part) or '-' in range_part:
                tags = self.tag_loader.load_tags(file_part, self.verbose, self.cache_files)
                if isinstance(tags, list):
                    return process_wildcard_range(parsed_tag, tags)

        if parsed_tag.startswith('#'):
            tags = self.tag_loader.load_tags(parsed_tag.split('$$')[1], self.verbose, self.cache_files)
            if isinstance(tags, list):
                return self.get_tag_choice(parsed_tag, tags)

        tags = self.tag_loader.load_tags(parsed_tag, self.verbose, self.cache_files)
        if groups: return self.get_tag_group_choice(parsed_tag, groups, tags)
        if tags: return self.get_tag_choice(parsed_tag, tags)
        
        # FIXED: Return empty string instead of None if tag not found
        return "" 

    def get_prefixes_and_suffixes(self):
        prefixes, suffixes, neg_p, neg_s = [], [], [], []
        for entry in self.selected_entries.values():
            for p in entry.get('prefixes', []):
                if not p: continue
                p_str = str(p)
                if '**' in p_str: neg_p.append(p_str.replace('**', '').strip())
                else: prefixes.append(p_str)
            for s in entry.get('suffixes', []):
                if not s: continue
                s_str = str(s)
                if '**' in s_str: neg_s.append(s_str.replace('**', '').strip())
                else: suffixes.append(s_str)
        return {'prefixes': prefixes, 'suffixes': suffixes, 'neg_prefixes': neg_p, 'neg_suffixes': neg_s}

class TagReplacer:
    def __init__(self, tag_selector):
        self.tag_selector = tag_selector
        self.wildcard_regex = re.compile(r'(__|<)(.*?)(__|>)')
        self.opts_regexp = re.compile(r'(?<=\[)(.*?)(?=\])')

    def replace_wildcard(self, matches):
        if not matches or len(matches.groups()) != 3: return ""
        match = matches.group(2)
        if not match: return ""
        
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
            return selected
            
        return matches.group(0)

    def replace(self, prompt):
        p = self.wildcard_regex.sub(self.replace_wildcard, prompt)
        count = 0
        while p != prompt and count < 10:
            prompt = p
            p = self.wildcard_regex.sub(self.replace_wildcard, prompt)
            count += 1
        return p

class DynamicPromptReplacer:
    def __init__(self, seed):
        self.re_combinations = re.compile(r"\{([^{}]*)\}")
        self.seed = seed

    def replace_combinations(self, match):
        if not match: return ""
        content = match.group(1)
        
        if content.startswith('~'):
            content = content[1:]
            if '$$' in content: 
                 pass 
            else:
                variants = [s.strip() for s in content.split("|")]
                if not variants: return ""
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
            if count <= 0: return ""
            selected = random.sample(variants, min(count, len(variants)))
            return ", ".join(selected)

        variants = [s.strip() for s in content.split("|")]
        if not variants: return ""
        return random.choice(variants)

    def replace(self, template):
        if not template: return None
        return self.re_combinations.sub(self.replace_combinations, template)

class ConditionalReplacer:
    def __init__(self):
        # Syntax: [if Trigger : True | False]
        # FIX: Changed (.*?) to ([^\[\]]*?) to strictly match inner-most tags first.
        self.regex = re.compile(r'\[if\s+([^\[\]]+?)\s*:\s*([^\[\]]*?)(?:\s*\|\s*([^\[\]]*?))?\]', re.IGNORECASE | re.DOTALL)

    def replace(self, prompt):
        while True:
            match = self.regex.search(prompt)
            if not match: break
            
            full_tag = match.group(0)
            trigger_word = match.group(1).strip()
            true_text = match.group(2)
            false_text = match.group(3) if match.group(3) else ""

            temp_prompt = prompt.replace(full_tag, "")
            
            if trigger_word.lower() in temp_prompt.lower():
                prompt = prompt.replace(full_tag, true_text, 1)
            else:
                prompt = prompt.replace(full_tag, false_text, 1)
        return prompt

class VariableReplacer:
    def __init__(self):
        self.assign_regex = re.compile(r'\$([a-zA-Z0-9_]+)\s*=\s*((?:\{.*?\})|(?:[^\s]+))', re.DOTALL)
        self.use_regex = re.compile(r'\$([a-zA-Z0-9_]+)((?:\.[a-zA-Z_]+)*)')
        self.variables = {}

    def load_globals(self, globals_dict):
        self.variables.update(globals_dict)

    # NEW: Accepts replacers to force-resolve wildcards immediately
    def store_variables(self, text, tag_replacer, dynamic_replacer):
        def _replace_assign(match):
            var_name = match.group(1)
            raw_value = match.group(2)
            
            # Resolve value immediately (Recursively "bake" the wildcards/choices)
            resolved_value = raw_value
            for _ in range(10): # Depth limit for nesting
                prev_value = resolved_value
                resolved_value = tag_replacer.replace(resolved_value)
                resolved_value = dynamic_replacer.replace(resolved_value)
                if prev_value == resolved_value:
                    break
            
            self.variables[var_name] = resolved_value
            return "" # Strips the definition from the text
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
# DANBOORU CHARACTER EXPANDER
# ==============================================================================

class DanbooruReplacer:
    def __init__(self, options):
        self.cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        self.cache_files = options.get('cache_files', True)
        
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
        
        if self.cache_files and os.path.exists(cache_path):
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
                print(f"[UmiAI] Danbooru Error {response.status_code} for {character_name}")
                return []
            
            posts = response.json()
            if not posts:
                print(f"[UmiAI] No posts found for {character_name}")
                return []

        except Exception as e:
            print(f"[UmiAI] Connection error: {e}")
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

# ==============================================================================
# LORA HANDLER (INTERNAL LOADING WITH Z-IMAGE SUPPORT)
# ==============================================================================

class LoRAHandler:
    def __init__(self):
        # Syntax: <lora:LoraName:Strength> or <lora:LoraName> (defaults to 1.0)
        self.regex = re.compile(r'<lora:([^>:]+)(?::([0-9.]+))?>', re.IGNORECASE)

    def patch_zimage_lora(self, lora):
        """ Applies QKV fusion and key remapping for Z-Image LoRAs """
        new_lora = {}
        qkv_groups = {}
        
        for k, v in lora.items():
            new_k = k
            
            # 1. Output Projection Fix (to_out.0 -> out)
            if ".attention.to_out.0." in new_k:
                new_k = new_k.replace(".attention.to_out.0.", ".attention.out.")
                new_lora[new_k] = v
                continue

            # 2. Handle QKV Separation
            if ".attention.to_" in new_k:
                parts = new_k.split(".attention.to_")
                base_prefix = parts[0] + ".attention" 
                remainder = parts[1] # e.g. q.lora_A.weight
                
                qkv_type = remainder[0] # 'q', 'k', or 'v'
                suffix = remainder[2:] # 'lora_A.weight'
                
                if base_prefix not in qkv_groups:
                    qkv_groups[base_prefix] = {'q': {}, 'k': {}, 'v': {}}
                
                qkv_groups[base_prefix][qkv_type][suffix] = v
                continue

            new_lora[new_k] = v

        # --- FUSE QKV ---
        for base_key, group in qkv_groups.items():
            # Check A weights (Down)
            ak_a = "lora_A.weight"
            if ak_a in group['q'] and ak_a in group['k'] and ak_a in group['v']:
                q_a = group['q'][ak_a]
                k_a = group['k'][ak_a]
                v_a = group['v'][ak_a]
                
                # Stack A vertically: (3*rank, dim_in)
                fused_A = torch.cat([q_a, k_a, v_a], dim=0)
                new_lora[f"{base_key}.qkv.lora_A.weight"] = fused_A

            # Check B weights (Up)
            ak_b = "lora_B.weight"
            if ak_b in group['q'] and ak_b in group['k'] and ak_b in group['v']:
                q_b = group['q'][ak_b]
                k_b = group['k'][ak_b]
                v_b = group['v'][ak_b]
                
                # Block Diagonal B: (3*dim_out, 3*rank)
                out_dim, rank = q_b.shape
                fused_B = torch.zeros((out_dim * 3, rank * 3), dtype=q_b.dtype, device=q_b.device)
                fused_B[0:out_dim, 0:rank] = q_b
                fused_B[out_dim:2*out_dim, rank:2*rank] = k_b
                fused_B[2*out_dim:3*out_dim, 2*rank:3*rank] = v_b
                
                new_lora[f"{base_key}.qkv.lora_B.weight"] = fused_B

            # Handle Alphas
            ak_alpha = "lora_alpha"
            if ak_alpha in group['q']:
                new_lora[f"{base_key}.qkv.lora_alpha"] = group['q'][ak_alpha]

        return new_lora

    def extract_and_load(self, text, model, clip):
        matches = self.regex.findall(text)
        clean_text = self.regex.sub("", text)

        if model is None or clip is None:
            return clean_text, model, clip

        for match in matches:
            name = match[0].strip()
            strength = float(match[1]) if match[1] else 1.0
            
            lora_path = folder_paths.get_full_path("loras", name)
            if not lora_path:
                lora_path = folder_paths.get_full_path("loras", f"{name}.safetensors")
            
            if lora_path:
                try:
                    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                    
                    # AUTO-DETECT Z-IMAGE Format
                    # Heuristic: Check for 'to_q' keys which implies separate QKV
                    is_zimage = any(".attention.to_q." in k for k in lora.keys())
                    
                    if is_zimage:
                        lora = self.patch_zimage_lora(lora)
                    
                    model, clip = comfy.sd.load_lora_for_models(model, clip, lora, strength, strength)
                except Exception as e:
                    print(f"[UmiAI] Failed to load LoRA {name}: {e}")
            else:
                 print(f"[UmiAI] LoRA not found: {name}")

        return clean_text, model, clip

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
        for t in tags: self.negative_tag.add(t.strip())

    def get_negative_string(self):
        return ", ".join([t for t in self.negative_tag if t.strip()])

# ==============================================================================
# COMFYUI NODE DEFINITION
# ==============================================================================

class UmiAIWildcardNode:
    def __init__(self):
        self.loaded = False
        self.wildcards_path = os.path.join(os.path.dirname(__file__), "wildcards")
        if not os.path.exists(self.wildcards_path):
            os.makedirs(self.wildcards_path, exist_ok=True)

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "autorefresh": (["Yes", "No"],),
            },
            "optional": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "input_negative": ("STRING", {"multiline": True, "forceInput": True}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192}),
                "danbooru_threshold": ("FLOAT", {"default": 0.75, "min": 0.1, "max": 1.0, "step": 0.05}),
                "danbooru_max_tags": ("INT", {"default": 15, "min": 1, "max": 50}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("model", "clip", "text", "negative_text", "width", "height")
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
                    except ValueError:
                        pass
        return text, settings

    def process(self, text, seed, autorefresh, width, height, model=None, clip=None, danbooru_threshold=0.75, danbooru_max_tags=15, input_negative=""):
        # ==============================================================================
        # PRE-PROCESSING: Comment Stripping
        # ==============================================================================
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

        # ==============================================================================
        # CORE PROCESSING
        # ==============================================================================
        random.seed(seed)
        options = {'verbose': False, 'cache_files': autorefresh == "No", 'ignore_paths': True}

        tag_loader = TagLoader(self.wildcards_path, options)
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

        # Phase 1: Expansion Loop
        while previous_prompt != prompt and iterations < 50:
            previous_prompt = prompt
            prompt = variable_replacer.store_variables(prompt, tag_replacer, dynamic_replacer)
            prompt = variable_replacer.replace_variables(prompt)
            prompt = tag_replacer.replace(prompt)
            prompt = dynamic_replacer.replace(prompt)
            prompt = danbooru_replacer.replace(prompt, danbooru_threshold, danbooru_max_tags)
            iterations += 1
            
        # Phase 2: Logic & Cleanup
        prompt = conditional_replacer.replace(prompt)
        
        # Phase 3: LoRA Internal Loading
        # We pass the model/clip in, and get the modified versions back
        prompt, final_model, final_clip = lora_handler.extract_and_load(prompt, model, clip)

        additions = tag_selector.get_prefixes_and_suffixes()
        if additions['prefixes']:
            prompt = ", ".join(additions['prefixes']) + ", " + prompt
        if additions['suffixes']:
            prompt = prompt + ", " + ", ".join(additions['suffixes'])

        if additions['neg_prefixes']: neg_gen.add_list(additions['neg_prefixes'])
        if additions['neg_suffixes']: neg_gen.add_list(additions['neg_suffixes'])

        prompt = neg_gen.strip_negative_tags(prompt)
        prompt = re.sub(r',\s*,', ',', prompt)
        prompt = re.sub(r'\s+', ' ', prompt).strip()
        prompt = prompt.strip(',')

        generated_negatives = neg_gen.get_negative_string()
        final_negative = input_negative
        if generated_negatives:
            final_negative = f"{final_negative}, {generated_negatives}" if final_negative else generated_negatives
        
        if final_negative:
            final_negative = re.sub(r',\s*,', ',', final_negative).strip()

        prompt, settings = self.extract_settings(prompt)
        
        final_width = settings['width'] if settings['width'] > 0 else width
        final_height = settings['height'] if settings['height'] > 0 else height

        return (final_model, final_clip, prompt, final_negative, final_width, final_height)