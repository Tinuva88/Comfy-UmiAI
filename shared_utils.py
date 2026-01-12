"""
Shared utility functions used by both Full and Lite Umi nodes.
This module contains common functions to avoid code duplication.
"""

import os
import json
import random
import re
import yaml
import csv
import fnmatch
import hashlib
from datetime import datetime
import folder_paths

# ==============================================================================
# CONSTANTS
# ==============================================================================
ALL_KEY = 'all_files_index'

# ==============================================================================
# GLOBAL CACHES (shared between Full and Lite)
# ==============================================================================
GLOBAL_CACHE = {}
GLOBAL_INDEX = {'built': False, 'files': set(), 'entries': {}, 'tags': set()}
FILE_MTIME_CACHE = {}
ALIAS_CACHE = {}


def _normalize_aliases(data):
    wildcards = {}
    loras = {}

    if not isinstance(data, dict):
        return {'wildcards': wildcards, 'loras': loras}

    if 'wildcards' in data or 'loras' in data:
        wild_map = data.get('wildcards', {})
        lora_map = data.get('loras', {})
    else:
        wild_map = data
        lora_map = {}

    if isinstance(wild_map, dict):
        for k, v in wild_map.items():
            if isinstance(v, str):
                wildcards[str(k).strip().lower()] = v.strip()

    if isinstance(lora_map, dict):
        for k, v in lora_map.items():
            if isinstance(v, str):
                loras[str(k).strip().lower()] = v.strip()

    return {'wildcards': wildcards, 'loras': loras}


def load_aliases_from_paths(paths):
    combined = {'wildcards': {}, 'loras': {}}
    for path in paths:
        alias_path = os.path.join(path, 'aliases.yaml')
        if not os.path.exists(alias_path):
            continue
        try:
            mtime = os.path.getmtime(alias_path)
        except OSError:
            continue

        cached = ALIAS_CACHE.get(alias_path)
        if cached and cached.get('mtime') == mtime:
            data = cached.get('data', {})
        else:
            try:
                with open(alias_path, 'r', encoding='utf-8') as f:
                    raw = yaml.safe_load(f) or {}
            except Exception:
                raw = {}
            data = _normalize_aliases(raw)
            ALIAS_CACHE[alias_path] = {'mtime': mtime, 'data': data}

        combined['wildcards'].update(data.get('wildcards', {}))
        combined['loras'].update(data.get('loras', {}))

    return combined


def resolve_lora_alias(name, wildcard_paths):
    if not name:
        return name
    aliases = load_aliases_from_paths(wildcard_paths)
    return aliases.get('loras', {}).get(str(name).strip().lower(), name)


def escape_unweighted_colons(prompt):
    """
    Escapes colons that are NOT part of SD weight syntax (token:weight) inside parentheses.
    This prevents tags like 'reverse:1999' from being misinterpreted as weights by SD.

    Examples:
    - 'reverse:1999' -> 'reverse\\:1999' (escaped)
    - '(red:1.2)' -> '(red:1.2)' (unchanged - valid weight)
    - 'vertin_(reverse:1999)' -> 'vertin_(reverse\\:1999)' (escaped - not a weight)
    """
    if not prompt or ':' not in prompt:
        return prompt

    result = []
    i = 0

    while i < len(prompt):
        char = prompt[i]

        if char == ':':
            # Look back and forward to determine if this is SD weight syntax
            # SD weight syntax: (token:number) where opening paren is immediately before token

            # Look ahead: check if followed by a number
            j = i + 1
            while j < len(prompt) and prompt[j] in ' \t':
                j += 1

            has_number = False
            if j < len(prompt):
                if prompt[j] == '-':
                    j += 1
                has_digit = False
                has_decimal = False
                while j < len(prompt) and (prompt[j].isdigit() or (prompt[j] == '.' and not has_decimal)):
                    if prompt[j].isdigit():
                        has_digit = True
                    if prompt[j] == '.':
                        has_decimal = True
                    j += 1
                if has_digit:
                    has_number = True

            # Look back: check if we're in a weight context (opening paren before token)
            # For SD weights like (red:1.2), the pattern is: , (token:num) or start (token:num)
            # NOT like tag_(sub:123) where underscore precedes the paren
            is_weight_context = False
            if has_number and j < len(prompt) and prompt[j] == ')':
                # Find the matching opening paren
                k = i - 1
                # Skip back through the token
                while k >= 0 and prompt[k] not in '(,\n':
                    k -= 1
                # Check if we hit an opening paren (not preceded by underscore/alphanumeric)
                if k >= 0 and prompt[k] == '(':
                    # Check what's before the opening paren
                    if k == 0:
                        is_weight_context = True
                    elif k > 0 and prompt[k-1] in ', \t\n':
                        is_weight_context = True
                    # If preceded by underscore or alphanumeric, it's part of a tag name
                    elif k > 0 and (prompt[k-1].isalnum() or prompt[k-1] == '_'):
                        is_weight_context = False

            if is_weight_context:
                # Valid SD weight syntax - keep colon
                result.append(char)
            else:
                # Not a weight - escape it
                result.append('\\:')
            i += 1
        else:
            result.append(char)
            i += 1

    return ''.join(result)


def parse_wildcard_weight(line):
    """
    Parse a wildcard file line to extract value and tags.
    
    Format: "text::tag1,tag2" or just "text"
    Weight parsing via colon has been removed to avoid conflicts with entries like "show:1988"
    
    Returns:
        dict: {'value': str, 'weight': float, 'tags': list}
    """
    value = line
    weight = 1.0  # Weight is always 1.0 now (feature removed)
    tags = []

    # Check for tags (using :: separator only - unambiguous)
    if '::' in line:
        parts = line.split('::', 1)
        value = parts[0].strip()
        remainder = parts[1].strip()
        # Parse tags from remainder
        tags = [t.strip() for t in remainder.split(',') if t.strip()]

    return {
        'value': value,
        'weight': weight,
        'tags': tags
    }


def get_all_wildcard_paths():
    """
    Get all wildcard search paths.
    Returns list of directories to search for wildcard files.
    """
    paths = set()

    # Internal wildcards path (in the extension directory)
    internal_path = os.path.join(os.path.dirname(__file__), "wildcards")
    if os.path.exists(internal_path):
        paths.add(internal_path)

    # Root wildcards path
    root_wildcards = os.path.join(folder_paths.base_path, "wildcards")
    if os.path.exists(root_wildcards):
        paths.add(root_wildcards)

    # Models wildcards path
    models_wildcards = os.path.join(folder_paths.models_dir, "wildcards")
    if os.path.exists(models_wildcards):
        paths.add(models_wildcards)

    # Extension-registered wildcard paths
    try:
        ext_paths = folder_paths.get_folder_paths("wildcards")
        if ext_paths:
            for p in ext_paths:
                if os.path.exists(p):
                    paths.add(p)
    except:
        pass

    return list(paths)


def log_prompt_to_history(prompt, negative="", seed=None):
    """
    Log a prompt to history file for tracking generations.

    Args:
        prompt (str): The positive prompt
        negative (str): The negative prompt
        seed (int): The seed used for generation
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        history_file = os.path.join(current_dir, "prompt_history.json")

        # Load existing history
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                history = []

        # Add new entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "negative": negative,
            "seed": seed
        }
        history.append(entry)

        # Keep only last 100 entries
        history = history[-100:]

        # Save updated history
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[UmiAI] Warning: Could not log prompt to history: {e}")


def parse_tag(tag):
    """Parse and clean a wildcard tag"""
    if tag is None:
        return ""
    tag = tag.replace("__", "").replace('<', '').replace('>', '').strip()
    if tag.startswith('#'):
        return tag
    return tag


def read_file_lines(file):
    """Read and parse lines from a wildcard text file"""
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


def parse_wildcard_range(range_str, num_variants):
    """Parse range syntax like '2-5' or '3'"""
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
    """Process wildcard range selection like '2-5$$tag'"""
    if not lines:
        return ""
    if tag.startswith('#'):
        return None

    if "$$" not in tag:
        selected = rng.choice(lines)
        if isinstance(selected, dict):
            selected = selected.get('value', '')
        if '#' in str(selected):
            selected = str(selected).split('#')[0].strip()
        return selected

    range_str, tag_name = tag.split("$$", 1)
    try:
        low, high = parse_wildcard_range(range_str, len(lines))
        num_items = rng.randint(low, high)
        if num_items == 0:
            return ""

        selected = rng.sample(lines, min(num_items, len(lines)))
        result = []
        for item in selected:
            if isinstance(item, dict):
                val = item.get('value', '')
            else:
                val = str(item)
            if '#' in val:
                val = val.split('#')[0].strip()
            result.append(val)
        return ", ".join(result)
    except Exception as e:
        print(f"Error processing wildcard range: {e}")
        selected = rng.choice(lines)
        if isinstance(selected, dict):
            selected = selected.get('value', '')
        if '#' in str(selected):
            selected = str(selected).split('#')[0].strip()
        return selected


# ==============================================================================
# LOGIC EVALUATOR
# ==============================================================================
class LogicEvaluator:
    """
    Evaluates boolean logic expressions against a context dictionary.
    Supports: AND, OR, NOT, XOR, NAND, NOR operators (word and symbolic forms)
    Also supports variable comparisons ($var==value) and boolean checks ($var)
    """
    def __init__(self, expression, variables=None):
        self.expression = self._normalize_expression(expression.strip())
        self.variables = variables or {}

    def _strip_line_comments(self, expr):
        if not expr:
            return expr

        result = []
        i = 0
        in_quote = False
        quote_char = ""
        while i < len(expr):
            char = expr[i]
            if in_quote:
                result.append(char)
                if char == quote_char:
                    in_quote = False
                    quote_char = ""
                i += 1
                continue

            if char in ('"', "'"):
                in_quote = True
                quote_char = char
                result.append(char)
                i += 1
                continue

            if char == '/' and i + 1 < len(expr) and expr[i + 1] == '/':
                prev_char = expr[i - 1] if i > 0 else ""
                if prev_char != ':':
                    # Skip until newline
                    i += 2
                    while i < len(expr) and expr[i] != '\n':
                        i += 1
                    continue

            result.append(char)
            i += 1

        return "".join(result)

    def _normalize_expression(self, expr):
        if not expr:
            return expr

        expr = self._strip_line_comments(expr)

        # Normalize single '=' to '==' outside of quotes.
        result = []
        in_quote = False
        quote_char = ""
        i = 0
        while i < len(expr):
            char = expr[i]
            if char in ('"', "'"):
                if in_quote and char == quote_char:
                    in_quote = False
                    quote_char = ""
                elif not in_quote:
                    in_quote = True
                    quote_char = char
                result.append(char)
                i += 1
                continue

            if not in_quote and char == '=':
                prev_char = expr[i - 1] if i > 0 else ""
                next_char = expr[i + 1] if i + 1 < len(expr) else ""
                if prev_char not in ('!', '=') and next_char != '=':
                    result.append('==')
                else:
                    result.append(char)
                i += 1
                continue

            result.append(char)
            i += 1

        normalized = "".join(result)
        # Remove spaces around comparison operators for tokenization stability
        normalized = re.sub(r'\s*(==|!=)\s*', r'\1', normalized)
        return normalized

    def _strip_quotes(self, value):
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            return value[1:-1]
        return value

    def evaluate(self, context):
        tokens = self.tokenize(self.expression)
        postfix = self.to_postfix(tokens)
        return self.evaluate_postfix(postfix, context)

    def tokenize(self, expr):
        tokens = []
        current = ""
        i = 0
        in_quote = False
        quote_char = ""
        
        def is_word_boundary(pos):
            """Check if position is at a word boundary (start, end, space, or paren)"""
            if pos < 0 or pos >= len(expr):
                return True
            return expr[pos] in ' \t\n()'
        
        while i < len(expr):
            char = expr[i]

            if in_quote:
                current += char
                if char == quote_char:
                    in_quote = False
                    quote_char = ""
                i += 1
                continue

            if char in ('"', "'"):
                in_quote = True
                quote_char = char
                current += char
                i += 1
                continue

            if char in '()':
                if current.strip():
                    tokens.append(current.strip())
                    current = ""
                tokens.append(char)
                i += 1
            elif char.isspace():
                if current.strip():
                    tokens.append(current.strip())
                    current = ""
                i += 1
            else:
                # Check for symbolic operators first (these don't need word boundaries)
                if expr[i:i+2] == '&&':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('AND')
                    i += 2
                elif expr[i:i+2] == '||':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('OR')
                    i += 2
                elif char == '!':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NOT')
                    i += 1
                elif char == '^':
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('XOR')
                    i += 1
                # Word operators - must be standalone words (preceded and followed by word boundary)
                elif (expr[i:i+4].upper() == 'NAND' and 
                      is_word_boundary(i-1) and is_word_boundary(i+4)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NAND')
                    i += 4
                elif (expr[i:i+3].upper() == 'AND' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('AND')
                    i += 3
                elif (expr[i:i+3].upper() == 'NOT' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NOT')
                    i += 3
                elif (expr[i:i+3].upper() == 'XOR' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('XOR')
                    i += 3
                elif (expr[i:i+3].upper() == 'NOR' and 
                      is_word_boundary(i-1) and is_word_boundary(i+3)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('NOR')
                    i += 3
                elif (expr[i:i+2].upper() == 'OR' and 
                      is_word_boundary(i-1) and is_word_boundary(i+2)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('OR')
                    i += 2
                elif (expr[i:i+2].upper() == 'IN' and 
                      is_word_boundary(i-1) and is_word_boundary(i+2)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('IN')
                    i += 2
                elif (expr[i:i+8].upper() == 'CONTAINS' and 
                      is_word_boundary(i-1) and is_word_boundary(i+8)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('CONTAINS')
                    i += 8
                elif (expr[i:i+7].upper() == 'MATCHES' and 
                      is_word_boundary(i-1) and is_word_boundary(i+7)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('MATCHES')
                    i += 7
                elif (expr[i:i+10].upper() == 'STARTSWITH' and 
                      is_word_boundary(i-1) and is_word_boundary(i+10)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('STARTSWITH')
                    i += 10
                elif (expr[i:i+8].upper() == 'ENDSWITH' and 
                      is_word_boundary(i-1) and is_word_boundary(i+8)):
                    if current.strip():
                        tokens.append(current.strip())
                        current = ""
                    tokens.append('ENDSWITH')
                    i += 8
                else:
                    current += char
                    i += 1

        if current.strip():
            tokens.append(current.strip())

        return tokens

    def to_postfix(self, tokens):
        precedence = {
            'NOT': 3, 'AND': 2, 'NAND': 2, 'XOR': 1, 'OR': 1, 'NOR': 1,
            'IN': 4, 'CONTAINS': 4, 'MATCHES': 4, 'STARTSWITH': 4, 'ENDSWITH': 4
        }
        output = []
        stack = []

        for token in tokens:
            if token in precedence:
                while (stack and stack[-1] != '(' and
                       stack[-1] in precedence and
                       precedence[stack[-1]] >= precedence[token]):
                    output.append(stack.pop())
                stack.append(token)
            elif token == '(':
                stack.append(token)
            elif token == ')':
                while stack and stack[-1] != '(':
                    output.append(stack.pop())
                if stack:
                    stack.pop()
            else:
                output.append(token)

        while stack:
            output.append(stack.pop())

        return output

    def evaluate_postfix(self, postfix, context):
        stack = []

        context_text = None
        if isinstance(context, str):
            context_text = context.lower()

        def _coerce_bool(operand):
            if isinstance(operand, dict):
                kind = operand.get('kind')
                if kind == 'var':
                    val = self.variables.get(operand.get('name', ''), False)
                    return bool(val) and str(val).lower() not in ['false', '0', 'no', '']
                if kind == 'quoted':
                    return bool(operand.get('value', ''))
                if kind == 'bare':
                    token_lower = operand.get('value', '').lower()
                    if context_text is not None:
                        if re.search(r'\s', token_lower):
                            return token_lower in context_text
                        return re.search(r'\b' + re.escape(token_lower) + r'\b', context_text) is not None
                    return token_lower in context
                if kind == 'bool':
                    return bool(operand.get('value'))
            return bool(operand)

        def _coerce_str(operand):
            if isinstance(operand, dict):
                kind = operand.get('kind')
                if kind == 'var':
                    return str(self.variables.get(operand.get('name', ''), ''))
                if kind == 'quoted':
                    return str(operand.get('value', ''))
                if kind == 'bare':
                    return str(operand.get('value', ''))
                if kind == 'bool':
                    return str(bool(operand.get('value')))
            return str(operand)

        for token in postfix:
            if token == 'AND':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(a and b)
            elif token == 'OR':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(a or b)
            elif token == 'NOT':
                if len(stack) < 1:
                    return False
                a = _coerce_bool(stack.pop())
                stack.append(not a)
            elif token == 'XOR':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(a != b)
            elif token == 'NAND':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(not (a and b))
            elif token == 'NOR':
                if len(stack) < 2:
                    return False
                b = _coerce_bool(stack.pop())
                a = _coerce_bool(stack.pop())
                stack.append(not (a or b))
            elif token == 'IN':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                if ',' in right or '|' in right:
                    parts = [p.strip() for p in re.split(r'[,\|]', right) if p.strip()]
                    stack.append(left in parts)
                else:
                    stack.append(left in right)
            elif token == 'CONTAINS':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                stack.append(right in left)
            elif token == 'MATCHES':
                if len(stack) < 2:
                    return False
                pattern = _coerce_str(stack.pop())
                target = _coerce_str(stack.pop())
                try:
                    stack.append(re.search(pattern, target, re.IGNORECASE) is not None)
                except re.error:
                    stack.append(False)
            elif token == 'STARTSWITH':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                stack.append(left.startswith(right))
            elif token == 'ENDSWITH':
                if len(stack) < 2:
                    return False
                right = _coerce_str(stack.pop()).lower()
                left = _coerce_str(stack.pop()).lower()
                stack.append(left.endswith(right))
            else:
                # Variable comparison support ($var==value, $var!=value, $var=value)
                if '!=' in token:
                    parts = token.split('!=', 1)
                    left = parts[0].strip()
                    right = self._strip_quotes(parts[1].strip())

                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value != right.lower())
                    else:
                        stack.append(self._strip_quotes(left).lower() != right.lower())
                elif '==' in token:
                    parts = token.split('==', 1)
                    left = parts[0].strip()
                    right = self._strip_quotes(parts[1].strip())

                    # Check if left side is a variable
                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value == right.lower())
                    else:
                        # Regular comparison
                        stack.append(self._strip_quotes(left).lower() == right.lower())
                elif '=' in token:
                    parts = token.split('=', 1)
                    left = parts[0].strip()
                    right = self._strip_quotes(parts[1].strip())

                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value == right.lower())
                    else:
                        stack.append(self._strip_quotes(left).lower() == right.lower())
                elif token.startswith('$'):
                    stack.append({'kind': 'var', 'name': token[1:]})
                elif token.startswith(("'", '"')) and token.endswith(("'", '"')) and len(token) >= 2:
                    stack.append({'kind': 'quoted', 'value': self._strip_quotes(token)})
                else:
                    stack.append({'kind': 'bare', 'value': token})

        if not stack:
            return False
        return _coerce_bool(stack[0])


# ==============================================================================
# DYNAMIC PROMPT REPLACER
# ==============================================================================
class DynamicPromptReplacer:
    """
    Handles dynamic prompt syntax like {option1|option2|option3}
    Supports: random choice, percentage chance, range selection, sequential mode
    """
    def __init__(self, seed):
        self.re_combinations = re.compile(r"\{([^{}]*)\}")
        self.seed = seed
        self.rng = random.Random(seed)

    def replace_combinations(self, match):
        if not match:
            return ""
        content = match.group(1)
        
        # Sequential mode: ~{opt1|opt2|opt3} picks based on seed
        if content.startswith('~'):
            content = content[1:]
            if '$$' not in content:
                variants = [s.strip() for s in content.split("|")]
                if not variants:
                    return ""
                return variants[self.seed % len(variants)]

        # Enhanced percentage support with new algorithm:
        # {Red|Blue|Yellow|Green} - Equal 25% each (no percentages)
        # {15%Red|15%Blue|15%Yellow|10%Green} - Total 55%, 45% blank chance
        # {35%Red|35%Blue|35%Yellow|35%Green} - Total 140%, normalized to ~25% each
        # {115%Red|25%Blue|Yellow|Green} - Total 140%, Y/G get 0%
        # {75%Red|Blue|Yellow|Green} - 75% R, remaining 25% split among B/Y/G (8.33% each)
        if '%' in content and '$$' not in content:
            parts = content.split('|')
            options = []
            total_explicit_pct = 0
            unassigned_count = 0
            has_percentage = False
            
            for part in parts:
                part = part.strip()
                if '%' in part:
                    # Parse percentage: "25%Red" -> (25, "Red")
                    pct_split = part.split('%', 1)
                    try:
                        pct = float(pct_split[0])
                        text = pct_split[1].strip() if len(pct_split) > 1 else ""
                        options.append({'pct': pct, 'text': text, 'has_pct': True})
                        total_explicit_pct += pct
                        has_percentage = True
                    except ValueError:
                        # Not a valid percentage, treat as regular option
                        options.append({'pct': None, 'text': part, 'has_pct': False})
                        unassigned_count += 1
                else:
                    # No percentage specified
                    options.append({'pct': None, 'text': part, 'has_pct': False})
                    unassigned_count += 1
            
            if has_percentage:
                # Calculate the effective max and distribute unassigned options
                # Rule: Unassigned options get 0% if sum >= 100%, else split remaining
                
                if total_explicit_pct >= 100:
                    # No room for unassigned options - they get 0%
                    for opt in options:
                        if opt['pct'] is None:
                            opt['pct'] = 0
                else:
                    # Distribute remaining (100 - sum) equally among unassigned
                    remaining = 100 - total_explicit_pct
                    share = remaining / unassigned_count if unassigned_count > 0 else 0
                    for opt in options:
                        if opt['pct'] is None:
                            opt['pct'] = share
                
                # Recalculate total after distribution
                total_pct = sum(opt['pct'] for opt in options)
                
                # Normalize if total > 100
                if total_pct > 100:
                    scale = 100 / total_pct
                    for opt in options:
                        opt['pct'] *= scale
                    total_pct = 100
                
                # Roll and pick
                roll = self.rng.random() * 100
                cumulative = 0
                
                for opt in options:
                    cumulative += opt['pct']
                    if roll < cumulative:
                        return opt['text']
                
                # If we're here and total < 100, roll landed in "blank" zone
                # If total == 100, return last option as fallback
                if total_pct >= 100 and options:
                    return options[-1]['text']
                return ""

        # Range selection: {2-3$$opt1|opt2|opt3|opt4} picks 2-3 random options
        if '$$' in content:
            range_str, variants_str = content.split('$$', 1)
            variants = [s.strip() for s in variants_str.split("|")]
            low, high = parse_wildcard_range(range_str, len(variants))
            count = self.rng.randint(low, high)
            if count <= 0:
                return ""
            selected = self.rng.sample(variants, min(count, len(variants)))
            return ", ".join(selected)

        # Standard random choice
        variants = [s.strip() for s in content.split("|")]
        if not variants:
            return ""
        return self.rng.choice(variants)

    def replace(self, template):
        if not template:
            return ""
        # Replace nested choice blocks iteratively
        prev = None
        while prev != template:
            prev = template
            template = self.re_combinations.sub(self.replace_combinations, template)
        return template


# ==============================================================================
# VARIABLE REPLACER
# ==============================================================================
class VariableReplacer:
    """
    Handles variable assignment ($var = value) and usage ($var)
    Supports: nested variable resolution, string methods (.upper, .lower, .clean, etc.)
    """
    def __init__(self):
        # Updated regex to support multiple assignments per line using ';' as separator
        # Matches $var=val until ';' or end of line/string
        # greedy match up to the separator to handle spaces correctly
        self.assign_regex = re.compile(r'\$([a-zA-Z0-9_]+)\s*=\s*([^;]+?)(?:\s*;|(?=\n)|$)', re.MULTILINE)
        self.use_regex = re.compile(r'\$([a-zA-Z0-9_]+)((?:\.[a-zA-Z_]+)*)')
        self.default_regex = re.compile(r'\$\{([a-zA-Z0-9_]+)\|([^}]*)\}')
        self.coalesce_regex = re.compile(r'coalesce\(([^)]+)\)', re.IGNORECASE)
        self.variables = {}
        self.variable_sources = {}

    def load_globals(self, globals_dict):
        self.variables.update(globals_dict)

    def find_matching_bracket(self, text, start):
        """Find the matching closing bracket for the one at text[start]."""
        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
            i += 1
        return i - 1 if depth == 0 else -1

    def store_variables(self, text, tag_replacer, dynamic_replacer):
        # 1. Mask conditional blocks (e.g. [if ... ]) to prevent premature variable assignment
        masked_text = text
        blocks = {}
        counter = 0
        if_start = re.compile(r'\[if\s+', re.IGNORECASE)

        while True:
            # Always search from the beginning of current masked_text
            match = if_start.search(masked_text)
            if not match:
                break
            
            # Match start is at "[if"
            bracket_idx = match.start()
            end = self.find_matching_bracket(masked_text, bracket_idx)
            
            if end == -1:
                # Malformed or unmatched check, just break to be safe
                break
                
            # Extract content including brackets
            block_content = masked_text[bracket_idx:end+1]
            token = f"%%UMI_IF_BLOCK_{counter}%%"
            blocks[token] = block_content
            
            # Replace strictly this occurrence
            masked_text = masked_text[:bracket_idx] + token + masked_text[end+1:]
            counter += 1

        def _find_matching(text_value, start, open_char, close_char):
            depth = 1
            i = start + 1
            while i < len(text_value) and depth > 0:
                if text_value[i] == open_char:
                    depth += 1
                elif text_value[i] == close_char:
                    depth -= 1
                i += 1
            return i - 1 if depth == 0 else -1

        def _parse_assignment(text_value, idx):
            if text_value[idx] != '$':
                return None

            j = idx + 1
            while j < len(text_value) and (text_value[j].isalnum() or text_value[j] == '_'):
                j += 1
            if j == idx + 1:
                return None

            var_name = text_value[idx + 1:j]

            k = j
            while k < len(text_value) and text_value[k].isspace():
                k += 1
            if k >= len(text_value) or text_value[k] != '=':
                return None

            k += 1
            while k < len(text_value) and text_value[k].isspace():
                k += 1
            if k >= len(text_value):
                return None

            value_start = k

            if text_value[k] == '{':
                end = _find_matching(text_value, k, '{', '}')
                if end == -1:
                    end = k
                value_end = end + 1
            elif text_value[k] == '[':
                end = _find_matching(text_value, k, '[', ']')
                if end == -1:
                    end = k
                value_end = end + 1
            elif text_value[k] in ("'", '"'):
                quote_char = text_value[k]
                k += 1
                while k < len(text_value):
                    if text_value[k] == quote_char and text_value[k - 1] != '\\':
                        k += 1
                        break
                    k += 1
                value_end = k
            elif text_value[k:k + 2] == '__':
                end = text_value.find('__', k + 2)
                value_end = end + 2 if end != -1 else len(text_value)
            elif text_value[k] == '<':
                end = text_value.find('>', k + 1)
                value_end = end + 1 if end != -1 else len(text_value)
            else:
                k = value_start
                while k < len(text_value) and text_value[k] not in ';\n':
                    k += 1
                value_end = k

            raw_value = text_value[value_start:value_end].strip()

            # Skip a trailing semicolon if present
            value_end = value_end + 1 if value_end < len(text_value) and text_value[value_end] == ';' else value_end

            return var_name, raw_value, value_end

        # 2. Run assignment on MASKED text
        processed_parts = []
        i = 0
        while i < len(masked_text):
            if masked_text[i] != '$':
                processed_parts.append(masked_text[i])
                i += 1
                continue

            parsed = _parse_assignment(masked_text, i)
            if not parsed:
                processed_parts.append(masked_text[i])
                i += 1
                continue

            var_name, raw_value, end_idx = parsed
            resolved_value = raw_value
            for _ in range(10):  # Max iterations to prevent infinite loops
                prev_value = resolved_value
                resolved_value = tag_replacer.replace(resolved_value)
                resolved_value = dynamic_replacer.replace(resolved_value)
                if prev_value == resolved_value:
                    break

            self.variables[var_name] = resolved_value
            self.variable_sources[var_name] = self._infer_source(raw_value)
            self.variables['trace_last_var'] = var_name
            self.variables['trace_last_var_source'] = self.variable_sources[var_name]
            i = end_idx

        processed_text = "".join(processed_parts)
        
        # 3. Restore blocks
        for token, content in blocks.items():
            processed_text = processed_text.replace(token, content)
            
        return processed_text

    def replace_variables(self, text):
        # Nested variable resolution - resolve variables that reference other variables
        max_depth = 10
        resolved_vars = {}

        for var_name, var_value in self.variables.items():
            resolved_value = str(var_value)
            depth = 0

            # Keep resolving until no more $ references or max depth reached
            while '$' in resolved_value and depth < max_depth:
                changed = False
                for other_var_name, other_var_value in self.variables.items():
                    if other_var_name != var_name:
                        pattern = r'\$' + re.escape(other_var_name) + r'(?!\w)'
                        if re.search(pattern, resolved_value):
                            resolved_value = re.sub(pattern, str(other_var_value), resolved_value)
                            changed = True
                if not changed:
                    break
                depth += 1

            resolved_vars[var_name] = resolved_value

        # Temporarily update variables dict with resolved values for method application
        original_vars = self.variables.copy()
        self.variables.update(resolved_vars)

        def _split_fallbacks(value):
            parts = []
            current = ""
            in_quote = False
            quote_char = ""
            for c in value:
                if in_quote:
                    current += c
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    current += c
                    continue
                if c == '|':
                    parts.append(current.strip())
                    current = ""
                else:
                    current += c
            parts.append(current.strip())
            return parts

        def _normalize_literal(val):
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                return val[1:-1]
            return val

        def _get_value_or_literal(token):
            token = token.strip()
            if not token:
                return ""
            if token.startswith('$'):
                return str(self.variables.get(token[1:], ""))
            return _normalize_literal(token)

        def _replace_default(match):
            var_name = match.group(1)
            fallback_raw = match.group(2).strip()

            value = self.variables.get(var_name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                fallbacks = _split_fallbacks(fallback_raw)
                for fb in fallbacks:
                    fb_val = _get_value_or_literal(fb)
                    if fb_val.strip() != "":
                        return fb_val
                return ""
            return str(value)

        def _split_args(value):
            parts = []
            current = ""
            in_quote = False
            quote_char = ""
            depth = 0
            for c in value:
                if in_quote:
                    current += c
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    current += c
                    continue
                if c == '(':
                    depth += 1
                    current += c
                    continue
                if c == ')':
                    depth = max(0, depth - 1)
                    current += c
                    continue
                if c == ',' and depth == 0:
                    parts.append(current.strip())
                    current = ""
                else:
                    current += c
            if current.strip():
                parts.append(current.strip())
            return parts

        def _replace_coalesce(match):
            content = match.group(1)
            args = _split_args(content)
            for arg in args:
                val = _get_value_or_literal(arg)
                if val.strip() != "":
                    return val
            return ""

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

        result = self.default_regex.sub(_replace_default, text)
        result = self.coalesce_regex.sub(_replace_coalesce, result)
        result = self.use_regex.sub(_replace_use, result)
        self.variables = original_vars  # Restore original for next iteration
        return result

    def _infer_source(self, raw_value):
        raw = raw_value.strip()
        if raw.startswith(('{', '[')) and '|' in raw:
            return "choice"
        if raw.startswith('__@') or '__@' in raw:
            return "prompt_file"
        if '__[' in raw or '<[' in raw:
            return "yaml"
        if '__' in raw:
            return "wildcard"
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')):
            return "literal"
        return "literal"


# ==============================================================================
# NEGATIVE PROMPT GENERATOR
# ==============================================================================
class NegativePromptGenerator:
    """
    Collects and manages negative prompt tags from various sources.
    Supports: **tag** syntax, --neg: syntax, list addition, deduplication
    """
    def __init__(self):
        self.negative_list = []  # Preserve order
        self.seen_lower = set()  # Track lowercase versions for deduplication

    def add(self, negative_text):
        """Add a single negative tag"""
        if negative_text:
            tag = negative_text.strip()
            tag_lower = tag.lower()
            if tag and tag_lower not in self.seen_lower:
                self.seen_lower.add(tag_lower)
                self.negative_list.append(tag)

    def add_list(self, tags):
        """Add multiple negative tags"""
        for t in tags:
            self.add(t)

    def strip_negative_tags(self, text):
        """Extract **negatives** from text and add them, return cleaned text"""
        # Handle **negative** syntax
        matches = re.findall(r'\*\*.*?\*\*', text)
        for match in matches:
            tag = match.replace("**", "").strip()
            self.add(tag)
            text = text.replace(match, "")
        
        # Handle --neg: syntax
        neg_pattern = r'--neg:\s*([^,\n]+)'
        neg_matches = re.findall(neg_pattern, text)
        for match in neg_matches:
            self.add(match.strip())
        text = re.sub(neg_pattern, '', text)
        
        return text

    def get_negative_string(self):
        """Return combined negative string, deduplicated"""
        return ", ".join(self.negative_list)


# ==============================================================================
# CONDITIONAL REPLACER
# ==============================================================================
class ConditionalReplacer:
    """
    Handles conditional text: [if condition: true_text | false_text]
    Supports: tag existence, variable checks, logical operators (AND, OR, NOT, XOR, NAND, NOR)
    """
    def __init__(self):
        # Simple pattern to find [if starts - we'll parse brackets manually
        self.if_start = re.compile(r'\[if\s+', re.IGNORECASE)
        self.local_assign_prefix = "$@"

    def _parse_local_assignment(self, text_value, idx):
        if text_value[idx:idx + 2] != self.local_assign_prefix:
            return None

        j = idx + 2
        while j < len(text_value) and (text_value[j].isalnum() or text_value[j] == '_'):
            j += 1
        if j == idx + 2:
            return None

        var_name = text_value[idx + 2:j]

        k = j
        while k < len(text_value) and text_value[k].isspace():
            k += 1
        if k >= len(text_value) or text_value[k] != '=':
            return None

        k += 1
        while k < len(text_value) and text_value[k].isspace():
            k += 1
        if k >= len(text_value):
            return None

        value_start = k

        def _find_matching(text_src, start, open_char, close_char):
            depth = 1
            i = start + 1
            while i < len(text_src) and depth > 0:
                if text_src[i] == open_char:
                    depth += 1
                elif text_src[i] == close_char:
                    depth -= 1
                i += 1
            return i - 1 if depth == 0 else -1

        if text_value[k] == '{':
            end = _find_matching(text_value, k, '{', '}')
            if end == -1:
                end = k
            value_end = end + 1
        elif text_value[k] == '[':
            end = _find_matching(text_value, k, '[', ']')
            if end == -1:
                end = k
            value_end = end + 1
        elif text_value[k] in ("'", '"'):
            quote_char = text_value[k]
            k += 1
            while k < len(text_value):
                if text_value[k] == quote_char and text_value[k - 1] != '\\':
                    k += 1
                    break
                k += 1
            value_end = k
        elif text_value[k:k + 2] == '__':
            end = text_value.find('__', k + 2)
            value_end = end + 2 if end != -1 else len(text_value)
        elif text_value[k] == '<':
            end = text_value.find('>', k + 1)
            value_end = end + 1 if end != -1 else len(text_value)
        else:
            k = value_start
            while k < len(text_value) and text_value[k] not in ';\n':
                k += 1
            value_end = k

        raw_value = text_value[value_start:value_end].strip()
        value_end = value_end + 1 if value_end < len(text_value) and text_value[value_end] == ';' else value_end

        return var_name, raw_value, value_end

    def _apply_local_vars(self, text_value, variables):
        local_vars = {}
        output = []
        i = 0
        while i < len(text_value):
            if text_value[i:i + 2] != self.local_assign_prefix:
                output.append(text_value[i])
                i += 1
                continue

            parsed = self._parse_local_assignment(text_value, i)
            if not parsed:
                output.append(text_value[i])
                i += 1
                continue

            var_name, raw_value, end_idx = parsed
            local_vars[var_name] = raw_value

            if isinstance(variables, dict):
                trace_val = variables.get('trace')
                if str(trace_val).strip().lower() in ("1", "true", "yes", "on"):
                    variables['trace_last_var'] = var_name
                    variables['trace_last_var_source'] = "local"
            i = end_idx

        cleaned = "".join(output)
        for name, value in local_vars.items():
            pattern = r'\$@' + re.escape(name) + r'(?!\w)'
            cleaned = re.sub(pattern, value, cleaned)
        return cleaned

    def find_matching_bracket(self, text, start):
        """Find the closing ] that matches the opening [ at start, accounting for nested brackets."""
        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
            i += 1
        return i - 1 if depth == 0 else -1

    def mask_conditionals(self, text):
        """Mask [if ...] blocks to prevent premature expansion."""
        masked_text = text
        blocks = {}
        counter = 0

        while True:
            match = self.if_start.search(masked_text)
            if not match:
                break
            bracket_idx = match.start()
            end = self.find_matching_bracket(masked_text, bracket_idx)
            if end == -1:
                break

            block_content = masked_text[bracket_idx:end + 1]
            token = f"%%UMI_IF_BLOCK_{counter}%%"
            blocks[token] = block_content
            masked_text = masked_text[:bracket_idx] + token + masked_text[end + 1:]
            counter += 1

        return masked_text, blocks

    def unmask_conditionals(self, text, blocks):
        """Restore masked [if ...] blocks."""
        for token, content in blocks.items():
            text = text.replace(token, content)
        return text

    def parse_conditional(self, text, start):
        """
        Parse a conditional starting at position 'start'.
        Returns (start_pos, end_pos, branches, else_text) or None if invalid.
        """
        # Find the [ position
        bracket_start = text.rfind('[', 0, start + 4)  # [if is 3 chars before content
        if bracket_start == -1:
            return None
        
        # Find matching ]
        end = self.find_matching_bracket(text, bracket_start)
        if end == -1:
            return None
        
        # Extract full content between [if and ]
        inner = text[bracket_start + 1:end]
        
        # Parse: "if condition : true_text | false_text" or "if condition : true_text"
        if_match = re.match(r'if\s+(.+?)\s*:\s*', inner, re.IGNORECASE | re.DOTALL)
        if not if_match:
            return None
        
        condition = if_match.group(1).strip()
        rest = inner[if_match.end():]
        
        def _find_colon(s, start_idx):
            depth_bracket = 0
            depth_brace = 0
            in_quote = False
            quote_char = ""
            i = start_idx
            while i < len(s):
                c = s[i]
                if in_quote:
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    i += 1
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    i += 1
                    continue
                if c == '[':
                    depth_bracket += 1
                elif c == ']':
                    depth_bracket -= 1
                elif c == '{':
                    depth_brace += 1
                elif c == '}':
                    depth_brace -= 1
                elif c == ':' and depth_bracket == 0 and depth_brace == 0:
                    return i
                i += 1
            return -1

        # Find the | or else/elif separators (but not inside nested brackets or braces)
        depth_bracket = 0
        depth_brace = 0
        in_quote = False
        quote_char = ""
        pipe_pos = -1
        else_pos = -1
        has_elif_else = False
        
        for i, c in enumerate(rest):
            if in_quote:
                if c == quote_char:
                    in_quote = False
                    quote_char = ""
                continue
            if c in ("'", '"'):
                in_quote = True
                quote_char = c
                continue
            if c == '[':
                depth_bracket += 1
            elif c == ']':
                depth_bracket -= 1
            elif c == '{':
                depth_brace += 1
            elif c == '}':
                depth_brace -= 1
            elif c == '|' and depth_bracket == 0 and depth_brace == 0:
                pipe_pos = i
            elif depth_bracket == 0 and depth_brace == 0:
                if rest[i:i+5].lower() == 'else:' and (i == 0 or rest[i-1].isspace()):
                    else_pos = i
                    has_elif_else = True
                    break
                if rest[i:i+4].lower() == 'elif' and (i == 0 or rest[i-1].isspace()):
                    has_elif_else = True
                    break
        
        if not has_elif_else:
            if pipe_pos == -1 and else_pos == -1:
                true_text = rest
                false_text = ""
            elif pipe_pos != -1:
                true_text = rest[:pipe_pos]
                false_text = rest[pipe_pos + 1:]
            else:
                true_text = rest[:else_pos]
                false_text = rest[else_pos + 5:]
            branches = [(condition, true_text.strip())]
            return (bracket_start, end + 1, branches, false_text.strip())

        branches = []
        current_cond = condition
        segment_start = 0
        i = 0
        depth_bracket = 0
        depth_brace = 0
        in_quote = False
        quote_char = ""
        while i < len(rest):
            c = rest[i]
            if in_quote:
                if c == quote_char:
                    in_quote = False
                    quote_char = ""
                i += 1
                continue
            if c in ("'", '"'):
                in_quote = True
                quote_char = c
                i += 1
                continue
            if c == '[':
                depth_bracket += 1
                i += 1
                continue
            if c == ']':
                depth_bracket -= 1
                i += 1
                continue
            if c == '{':
                depth_brace += 1
                i += 1
                continue
            if c == '}':
                depth_brace -= 1
                i += 1
                continue

            if depth_bracket == 0 and depth_brace == 0:
                if rest[i:i+5].lower() == 'else:' and (i == 0 or rest[i-1].isspace()):
                    branches.append((current_cond, rest[segment_start:i].strip()))
                    else_text = rest[i+5:].strip()
                    return (bracket_start, end + 1, branches, else_text)
                if rest[i:i+4].lower() == 'elif' and (i == 0 or rest[i-1].isspace()):
                    branches.append((current_cond, rest[segment_start:i].strip()))
                    cond_start = i + 4
                    while cond_start < len(rest) and rest[cond_start].isspace():
                        cond_start += 1
                    colon_pos = _find_colon(rest, cond_start)
                    if colon_pos == -1:
                        return None
                    current_cond = rest[cond_start:colon_pos].strip()
                    segment_start = colon_pos + 1
                    i = segment_start
                    continue
            i += 1

        branches.append((current_cond, rest[segment_start:].strip()))
        return (bracket_start, end + 1, branches, "")

    def evaluate_logic(self, condition, context, variables=None):
        """Evaluate a logical condition against the context."""
        if variables is None: 
            variables = {}
        evaluator = LogicEvaluator(condition, variables)
        return evaluator.evaluate(context)

    def replace(self, prompt, variables=None):
        """Replace conditional tags in the prompt."""
        if variables is None: 
            variables = {}
        
        max_iterations = 100  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            match = self.if_start.search(prompt)
            if not match:
                break
            
            parsed = self.parse_conditional(prompt, match.start())
            if not parsed:
                # Invalid conditional, skip past it
                break
            
            start_pos, end_pos, branches, else_text = parsed
            
            # Clean the context by removing current tag to avoid self-reference
            context = prompt[:start_pos] + prompt[end_pos:]

            replacement = self._apply_local_vars(else_text, variables) if else_text else else_text
            for idx, (cond, text_value) in enumerate(branches):
                if self.evaluate_logic(cond, context, variables):
                    replacement = self._apply_local_vars(text_value, variables)
                    trace_val = variables.get('trace')
                    if str(trace_val).strip().lower() in ("1", "true", "yes", "on"):
                        variables['trace_last_condition'] = cond
                        variables['trace_last_branch'] = str(idx)
                    break
            
            prompt = prompt[:start_pos] + replacement + prompt[end_pos:]
            iteration += 1
        
        return prompt


# ==============================================================================
# TAG LOADER BASE
# ==============================================================================
class TagLoaderBase:
    """
    Base class for TagLoader with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self, wildcard_paths, options):
        if isinstance(wildcard_paths, str):
            self.wildcard_paths = [wildcard_paths]
        else:
            self.wildcard_paths = wildcard_paths
            
        self.options = options
        self.verbose = options.get('verbose', False)
        self.files_index = set()
        self.umi_tags = set()
        self.aliases = load_aliases_from_paths(self.wildcard_paths)

    def resolve_wildcard_alias(self, name):
        if not name:
            return name
        return self.aliases.get('wildcards', {}).get(str(name).strip().lower(), name)

    def resolve_lora_alias(self, name):
        if not name:
            return name
        return self.aliases.get('loras', {}).get(str(name).strip().lower(), name)

    def load_globals(self):
        """Load global variables from globals.yaml files."""
        merged_globals = {}
        for location in self.wildcard_paths:
            global_path = os.path.join(location, 'globals.yaml')
            if os.path.exists(global_path):
                try:
                    with open(global_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            merged_globals.update({str(k): str(v) for k, v in data.items()})
                except yaml.YAMLError as e:
                    print(f"[UmiAI] ERROR: Malformed globals.yaml at {global_path}: {e}")
                except UnicodeDecodeError as e:
                    print(f"[UmiAI] ERROR: Encoding issue in globals.yaml at {global_path}: {e}")
                except Exception as e:
                    print(f"[UmiAI] WARNING: Error loading globals.yaml at {global_path}: {e}")
        return merged_globals

    def load_prompt_file(self, file_key):
        """Load entire .txt file content as a prompt (no parsing)."""
        key = self.resolve_wildcard_alias(file_key.strip())
        if key.lower().endswith('.txt'):
            key = key[:-4]
        for location in self.wildcard_paths:
            file_path = os.path.join(location, f"{key}.txt")
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return f.read().strip()
                except Exception as e:
                    if self.verbose:
                        print(f"[UmiAI] Error reading prompt file {file_path}: {e}")
        return None

    def process_yaml_entry(self, title, entry_data):
        """Process a YAML entry to extract structured data."""
        return {
            'title': title,
            'description': entry_data.get('Description', [None])[0] if isinstance(entry_data.get('Description', []), list) else None,
            'prompts': entry_data.get('Prompts', []),
            'prefixes': entry_data.get('Prefix', []),
            'suffixes': entry_data.get('Suffix', []),
            'tags': [str(x).lower().strip() for x in entry_data.get('Tags', [])]
        }


# ==============================================================================
# TAG SELECTOR BASE
# ==============================================================================
class TagSelectorBase:
    """
    Base class for TagSelector with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self, tag_loader, options):
        self.tag_loader = tag_loader
        self.options = options
        self.verbose = options.get('verbose', False)
        self.seed = options.get('seed', 0)
        self.rng = random.Random(self.seed)
        self.rng_streams_enabled = options.get('rng_streams', False)
        self.rng_streams_cache = {}
        self.variables = {}
        self.seeded_values = {}
        self.scoped_negatives = []

    def is_debug_enabled(self):
        val = self.variables.get('debug')
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    def is_trace_enabled(self):
        val = self.variables.get('trace')
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    def is_failfast_enabled(self):
        val = self.variables.get('fail_fast')
        if val is None:
            val = self.variables.get('failfast')
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    def init_debug_context(self):
        if not self.is_debug_enabled():
            return
        if 'debug_seed' not in self.variables:
            self.variables['debug_seed'] = str(self.seed)
        if 'debug_run_id' not in self.variables:
            run_id = f"{self.seed}-{int(datetime.now().timestamp() * 1000)}"
            self.variables['debug_run_id'] = run_id
        if 'debug_summary' not in self.variables:
            self.variables['debug_summary'] = "1"

    def init_trace_context(self):
        if not self.is_trace_enabled():
            return
        if 'trace_seed' not in self.variables:
            self.variables['trace_seed'] = str(self.seed)
        if 'trace_run_id' not in self.variables:
            run_id = f"{self.seed}-{int(datetime.now().timestamp() * 1000)}"
            self.variables['trace_run_id'] = run_id
        if 'trace_summary' not in self.variables:
            self.variables['trace_summary'] = "1"

    def set_trace_info(self, info):
        if not self.is_trace_enabled():
            return
        for k, v in info.items():
            self.variables[k] = v

    def update_variables(self, variables):
        """Update the variables dictionary."""
        self.variables = variables

    def clear_seeded_values(self):
        """Clear cached seeded values for a fresh run."""
        self.seeded_values = {}
        self.scoped_negatives = []

    def get_rng(self, scope=None):
        if not self.rng_streams_enabled:
            return self.rng

        scope_prefix = str(self.variables.get('rng_scope', '')).strip()
        if scope_prefix and scope:
            scope_key = f"{scope_prefix}:{scope}"
        elif scope_prefix:
            scope_key = scope_prefix
        else:
            scope_key = scope or ""

        if scope_key not in self.rng_streams_cache:
            seed_key = f"{self.seed}:{scope_key}"
            seed_int = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) % (2 ** 32)
            self.rng_streams_cache[scope_key] = random.Random(seed_int)

        return self.rng_streams_cache[scope_key]

    def get_scoped_index(self, scope, count):
        if count <= 0:
            return 0
        scope_key = scope or ""
        seed_key = f"{self.seed}:{scope_key}:index"
        seed_int = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) % (2 ** 32)
        return seed_int % count

    def _weighted_choice(self, items, rng=None):
        """Weighted random selection for lists with weights."""
        has_weights = all(isinstance(item, dict) and 'weight' in item for item in items)

        if not has_weights:
            return (rng or self.rng).choice(items)

        weights = [item.get('weight', 1.0) for item in items]
        total_weight = sum(weights)
        rand_val = (rng or self.rng).random() * total_weight
        cumsum = 0

        for item in items:
            cumsum += item.get('weight', 1.0)
            if rand_val <= cumsum:
                return item

        return items[-1]

    def get_prefixes_and_suffixes(self):
        """Get collected prefixes and suffixes. Override in subclasses."""
        return {
            'prefixes': getattr(self, 'prefixes', []),
            'suffixes': getattr(self, 'suffixes', []),
            'neg_prefixes': getattr(self, 'neg_prefixes', []),
            'neg_suffixes': getattr(self, 'neg_suffixes', [])
        }


# ==============================================================================
# LORA HANDLER BASE
# ==============================================================================
class LoRAHandlerBase:
    """
    Base class for LoRAHandler with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self):
        self.regex = re.compile(r'<lora:([^>]+)>', re.IGNORECASE)
        self.blacklist = {
            "1girl", "1boy", "solo", "monochrome", "greyscale", "comic", "scenery",
            "translated", "commentary_request", "highres", "absurdres", "masterpiece",
            "best quality", "simple background", "white background", "transparent background"
        }

    def apply_qkv_fusion(self, lora_dict):
        """Apply QKV fusion for Z-Image format LoRAs."""
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
                    try:
                        import torch
                        fused_weight = torch.cat([q_weight, k_weight, v_weight], dim=0)
                        fused_dict[new_key] = fused_weight
                    except:
                        fused_dict[key] = q_weight
                else:
                    fused_dict[key] = q_weight
            else:
                fused_dict[key] = lora_dict[key]

        return fused_dict

    def parse_lora_tag(self, lora_tag):
        """Parse a LoRA tag like 'name:strength' or 'name:str1:str2'."""
        parts = lora_tag.split(':')
        if len(parts) >= 2:
            name = parts[0]
            try:
                strength = float(parts[1])
            except ValueError:
                strength = 1.0
            return name, strength
        return lora_tag, 1.0


# ==============================================================================
# TAG REPLACER BASE
# ==============================================================================
class TagReplacerBase:
    """
    Base class for TagReplacer with common functionality.
    Full and Lite versions should extend this class.
    """
    def __init__(self, tag_selector):
        self.tag_selector = tag_selector
        self.replacement_history = []  # Track replacements for cycle detection
        # Use more flexible patterns that can handle content with brackets
        self.clean_regex = re.compile(r'\[clean:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)
        self.shuffle_regex = re.compile(r'\[shuffle:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)
        self.require_regex = re.compile(r'\[require:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)
        self.forbid_regex = re.compile(r'\[forbid:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)
        self.prefer_regex = re.compile(r'\[prefer:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)
        self.assert_regex = re.compile(r'\[assert:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)
        self.warn_regex = re.compile(r'\[warn:([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', re.IGNORECASE)

    def replace_functions(self, text):
        """Process [shuffle:] and [clean:] tags."""
        def _shuffle(match):
            content = match.group(1)
            items = [x.strip() for x in content.split(',')]
            # Use rng if available (base class), otherwise random
            rng = getattr(self.tag_selector, 'rng', None) or getattr(self.tag_selector, 'random', None)
            if rng:
                rng.shuffle(items)
            else:
                random.shuffle(items)
            return ", ".join(items)

        def _clean(match):
            content = match.group(1)
            # Remove extra whitespace
            content = re.sub(r'\s+', ' ', content)
            # Remove empty commas (,,)
            content = re.sub(r',\s*,+', ',', content)
            # Clean up spaces around commas
            content = content.replace(' ,', ',')
            content = re.sub(r',\s+', ', ', content)
            # Remove leading/trailing commas and spaces
            return content.strip(', ')

        def _require(match):
            content = match.group(1).strip()
            if not content:
                return ""
            var_part = content
            label = None
            if '|' in content:
                var_part, label = [s.strip() for s in content.split('|', 1)]
            var_name = var_part[1:] if var_part.startswith('$') else var_part
            if not var_name:
                return ""

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            value = variables.get(var_name)
            missing = value is None or (isinstance(value, str) and value.strip() == "")
            if missing:
                return f"<<ERROR_MISSING:{label or var_name}>>"
            return ""

        def _split_forbid(content):
            in_quote = False
            quote_char = ""
            for i, c in enumerate(content):
                if in_quote:
                    if c == quote_char:
                        in_quote = False
                        quote_char = ""
                    continue
                if c in ("'", '"'):
                    in_quote = True
                    quote_char = c
                    continue
                if c == '|':
                    prev_c = content[i - 1] if i > 0 else ""
                    next_c = content[i + 1] if i + 1 < len(content) else ""
                    if (prev_c.isspace() or prev_c == "") and (next_c.isspace() or next_c == ""):
                        return content[:i].strip(), content[i + 1:].strip()
            return "", ""

        def _forbid(match):
            content = match.group(1).strip()
            if not content:
                return ""
            condition, neg_text = _split_forbid(content)
            if not condition or not neg_text:
                return ""

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            evaluator = LogicEvaluator(condition, variables)
            if not evaluator.evaluate(text):
                return ""

            parts = [t.strip() for t in neg_text.split(',') if t.strip()]
            return " ".join(f"**{t}**" for t in parts)

        def _prefer(match):
            content = match.group(1).strip()
            if not content:
                return ""
            condition, pos_text = _split_forbid(content)
            if not condition or not pos_text:
                return ""

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            evaluator = LogicEvaluator(condition, variables)
            if not evaluator.evaluate(text):
                return ""

            parts = [t.strip() for t in pos_text.split(',') if t.strip()]
            return ", ".join(parts)

        def _assert(match):
            content = match.group(1).strip()
            if not content:
                return ""
            condition, label = _split_forbid(content)
            if not condition:
                return ""
            if not label:
                label = condition

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            evaluator = LogicEvaluator(condition, variables)
            if evaluator.evaluate(text):
                return ""
            return f"<<ERROR_ASSERT:{label}>>"

        def _warn(match):
            content = match.group(1).strip()
            if not content:
                return ""
            condition, message = _split_forbid(content)
            if not condition:
                return ""
            if not message:
                message = condition

            variables = getattr(self.tag_selector, 'variables', {}) or {}
            trace = variables.get('trace')
            debug = variables.get('debug')
            enabled = str(trace).strip().lower() in ("1", "true", "yes", "on") or str(debug).strip().lower() in ("1", "true", "yes", "on")
            if not enabled:
                return ""
            evaluator = LogicEvaluator(condition, variables)
            if evaluator.evaluate(text):
                return f"<<WARN:{message}>>"
            return ""

        text = self.shuffle_regex.sub(_shuffle, text)
        text = self.clean_regex.sub(_clean, text)
        text = self.require_regex.sub(_require, text)
        text = self.forbid_regex.sub(_forbid, text)
        text = self.prefer_regex.sub(_prefer, text)
        text = self.assert_regex.sub(_assert, text)
        text = self.warn_regex.sub(_warn, text)
        return text

    def get_prompt_file_content(self, filename):
        """Load full file content as a prompt."""
        try:
            file_content = self.tag_selector.tag_loader.load_prompt_file(filename)
            if file_content:
                return file_content
            else:
                return f"[PROMPT_FILE_NOT_FOUND: {filename}]"
        except Exception as e:
            return f"[PROMPT_FILE_ERROR: {filename}: {str(e)}]"


# ==============================================================================
# CHARACTER REPLACER
# ==============================================================================

class CharacterReplacer:
    """
    Replaces @@character:outfit:emotion@@ syntax with expanded character prompts.
    
    Syntax:
        @@elena@@                   - Base character only
        @@elena:casual@@            - Character with outfit
        @@elena:casual:happy@@      - Character with outfit and emotion
    """
    
    # Regex pattern for @@character:outfit:emotion@@
    pattern = re.compile(r'@@([a-zA-Z0-9_-]+)(?::([a-zA-Z0-9_-]+))?(?::([a-zA-Z0-9_-]+))?@@')
    
    # Cache for character data
    _cache = {}
    _mtime_cache = {}
    
    @classmethod
    def get_characters_path(cls):
        """Get the path to the characters folder."""
        # Check in the UmiAI custom node folder
        node_path = os.path.dirname(os.path.abspath(__file__))
        util_chars_path = os.path.join(node_path, "umi_utilities", "characters")
        if os.path.isdir(util_chars_path):
            return util_chars_path
        chars_path = os.path.join(node_path, "characters")
        if os.path.isdir(chars_path):
            return chars_path
        return None
    
    @classmethod
    def list_characters(cls):
        """List all available character names."""
        chars_path = cls.get_characters_path()
        if not chars_path:
            return []
        
        characters = []
        for item in os.listdir(chars_path):
            item_path = os.path.join(chars_path, item)
            profile_path = os.path.join(item_path, "profile.yaml")
            if os.path.isdir(item_path) and os.path.isfile(profile_path):
                characters.append(item)
        
        return characters
    
    @classmethod
    def load_character(cls, name):
        """Load a character profile, using cache if available."""
        chars_path = cls.get_characters_path()
        if not chars_path:
            return None
        
        profile_path = os.path.join(chars_path, name, "profile.yaml")
        if not os.path.isfile(profile_path):
            return None
        
        # Check if cached and still valid
        mtime = os.path.getmtime(profile_path)
        if name in cls._cache and cls._mtime_cache.get(name) == mtime:
            return cls._cache[name]
        
        # Load fresh
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                cls._cache[name] = data
                cls._mtime_cache[name] = mtime
                return data
        except Exception as e:
            print(f"[UmiAI Character] Error loading {name}: {e}")
            return None
    
    @classmethod
    def expand_character(cls, name, outfit=None, emotion=None, include_lora=True):
        """
        Expand a character reference into a full prompt.
        
        Args:
            name: Character folder name (e.g., 'elena')
            outfit: Outfit name (e.g., 'casual')
            emotion: Emotion name (e.g., 'happy')
            include_lora: Whether to include the LoRA tag
            
        Returns:
            Expanded prompt string or original reference if not found
        """
        data = cls.load_character(name)
        if not data:
            return f"@@{name}@@"  # Return original if not found
        
        parts = []
        
        # Add LoRA if available
        if include_lora and data.get('lora'):
            lora_name = data['lora']
            lora_strength = data.get('lora_strength', 1.0)
            parts.append(f"<lora:{lora_name}:{lora_strength}>")
        
        # Add base prompt
        if data.get('base_prompt'):
            parts.append(data['base_prompt'])
        
        # Add outfit if specified
        if outfit and 'outfits' in data:
            outfit_lower = outfit.lower()
            if outfit_lower in data['outfits']:
                outfit_data = data['outfits'][outfit_lower]
                if isinstance(outfit_data, dict):
                    parts.append(outfit_data.get('prompt', ''))
                else:
                    parts.append(str(outfit_data))
        
        # Add emotion if specified
        if emotion and 'emotions' in data:
            emotion_lower = emotion.lower()
            if emotion_lower in data['emotions']:
                emotion_data = data['emotions'][emotion_lower]
                if isinstance(emotion_data, dict):
                    parts.append(emotion_data.get('prompt', ''))
                else:
                    parts.append(str(emotion_data))
        
        return ", ".join(filter(None, parts))
    
    @classmethod
    def get_costume_parts(cls, name, costume_name, part=None):
        """
        Get costume parts from character data (VNCCS-style).
        
        Args:
            name: Character folder name
            costume_name: Costume name (e.g., 'school_uniform')
            part: Specific part (face/head/top/bottom/shoes) or None for all
            
        Returns:
            Prompt string for the costume/part
        """
        data = cls.load_character(name)
        if not data:
            return ""
        
        costumes = data.get('Costumes', data.get('costumes', {}))
        if not costumes:
            return ""
        
        costume_lower = costume_name.lower()
        costume_data = None
        for k, v in costumes.items():
            if k.lower() == costume_lower:
                costume_data = v
                break
        
        if not costume_data:
            return ""
        
        if part:
            # Return specific part
            part_lower = part.lower()
            return str(costume_data.get(part_lower, ""))
        else:
            # Return all parts combined
            valid_parts = ['face', 'head', 'top', 'bottom', 'shoes']
            part_prompts = []
            for p in valid_parts:
                val = costume_data.get(p, "")
                if val:
                    part_prompts.append(str(val))
            return ", ".join(part_prompts)
    
    @classmethod
    def get_emotion(cls, name, emotion_name):
        """
        Get emotion prompt from character data (VNCCS-style).
        
        Args:
            name: Character folder name
            emotion_name: Emotion name (e.g., 'happy')
            
        Returns:
            Emotion prompt string
        """
        data = cls.load_character(name)
        if not data:
            return ""
        
        emotions = data.get('Emotions', data.get('emotions', {}))
        if not emotions:
            return ""
        
        emotion_lower = emotion_name.lower()
        for k, v in emotions.items():
            if k.lower() == emotion_lower:
                if isinstance(v, dict):
                    return str(v.get('prompt', ''))
                return str(v)
        return ""
    
    @classmethod
    def get_info(cls, name, field):
        """
        Get character info field (VNCCS-style).
        
        Args:
            name: Character folder name
            field: Info field (sex/age/race/eyes/hair/face/body/skin_color)
            
        Returns:
            Info field value
        """
        data = cls.load_character(name)
        if not data:
            return ""
        
        info = data.get('Info', data.get('info', {}))
        if not info:
            return ""
        
        field_lower = field.lower()
        return str(info.get(field_lower, ""))
    
    @classmethod
    def replace(cls, text):
        """
        Replace all character patterns in text.
        
        Supports:
            @@character:outfit:emotion@@         - Original syntax
            @@character.costume.name@@           - Full costume
            @@character.costume.name.part@@      - Specific part
            @@character.emotion.name@@           - Emotion
            @@character.info.field@@             - Character info field
        
        Args:
            text: Input text with character references
            
        Returns:
            Text with character references expanded
        """
        # Extended pattern for dot-notation: @@char.category.name(.part)?@@
        dot_pattern = re.compile(r'@@([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9_-]+))?@@')
        
        def _replace_dot(match):
            char_name = match.group(1)
            category = match.group(2).lower()  # costume, emotion, info
            item_name = match.group(3)
            sub_item = match.group(4)  # May be None (for costume parts)
            
            if category == 'costume':
                return cls.get_costume_parts(char_name, item_name, sub_item)
            elif category == 'emotion':
                return cls.get_emotion(char_name, item_name)
            elif category == 'info':
                return cls.get_info(char_name, item_name)
            else:
                return match.group(0)  # Return unchanged
        
        # Original pattern for colon notation: @@char:outfit:emotion@@
        def _replace_colon(match):
            name = match.group(1)
            outfit = match.group(2)  # May be None
            emotion = match.group(3)  # May be None
            return cls.expand_character(name, outfit, emotion)
        
        # Apply dot notation first (more specific)
        text = dot_pattern.sub(_replace_dot, text)
        
        # Then apply colon notation (original behavior)
        text = cls.pattern.sub(_replace_colon, text)
        
        return text
