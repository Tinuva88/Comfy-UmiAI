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
    Parse a wildcard file line to extract value, weight, and tags.

    Format: "text::tag1,tag2:weight" or "text:weight" or "text::tags" or just "text"

    Returns:
        dict: {'value': str, 'weight': float, 'tags': list}
    """
    value = line
    weight = 1.0
    tags = []

    # Check for tags (using :: separator)
    if '::' in line:
        parts = line.split('::', 1)
        value = parts[0].strip()
        remainder = parts[1].strip()

        # Check if remainder has weight at the end
        weight_parts = remainder.rsplit(':', 1)
        if len(weight_parts) == 2 and weight_parts[1].strip().replace('.', '', 1).isdigit():
            # Has tags and weight: "text::tag1,tag2:weight"
            tags = [t.strip() for t in weight_parts[0].split(',') if t.strip()]
            weight = float(weight_parts[1].strip())
        else:
            # Just tags: "text::tag1,tag2"
            tags = [t.strip() for t in remainder.split(',') if t.strip()]
    elif ':' in line:
        parts = line.rsplit(':', 1)
        # Only treat as weight if:
        # 1. The part after colon is a valid number
        # 2. The part before colon doesn't end with a closing paren (not a tag like "char_(name:1999)")
        if (len(parts) == 2 and
            parts[1].strip().replace('.', '', 1).isdigit() and
            not parts[0].rstrip().endswith(')')):
            # This is a weighted entry
            value = parts[0].strip()
            weight = float(parts[1].strip())

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
        self.expression = expression.strip()
        self.variables = variables or {}

    def evaluate(self, context):
        tokens = self.tokenize(self.expression)
        postfix = self.to_postfix(tokens)
        return self.evaluate_postfix(postfix, context)

    def tokenize(self, expr):
        tokens = []
        current = ""
        i = 0
        
        def is_word_boundary(pos):
            """Check if position is at a word boundary (start, end, space, or paren)"""
            if pos < 0 or pos >= len(expr):
                return True
            return expr[pos] in ' \t\n()'
        
        while i < len(expr):
            char = expr[i]

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
                else:
                    current += char
                    i += 1

        if current.strip():
            tokens.append(current.strip())

        return tokens

    def to_postfix(self, tokens):
        precedence = {'NOT': 3, 'AND': 2, 'NAND': 2, 'XOR': 1, 'OR': 1, 'NOR': 1}
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

        for token in postfix:
            if token == 'AND':
                if len(stack) < 2:
                    return False
                b = stack.pop()
                a = stack.pop()
                stack.append(a and b)
            elif token == 'OR':
                if len(stack) < 2:
                    return False
                b = stack.pop()
                a = stack.pop()
                stack.append(a or b)
            elif token == 'NOT':
                if len(stack) < 1:
                    return False
                a = stack.pop()
                stack.append(not a)
            elif token == 'XOR':
                if len(stack) < 2:
                    return False
                b = stack.pop()
                a = stack.pop()
                stack.append(a != b)
            elif token == 'NAND':
                if len(stack) < 2:
                    return False
                b = stack.pop()
                a = stack.pop()
                stack.append(not (a and b))
            elif token == 'NOR':
                if len(stack) < 2:
                    return False
                b = stack.pop()
                a = stack.pop()
                stack.append(not (a or b))
            else:
                # Variable comparison support ($var==value)
                if '==' in token:
                    parts = token.split('==', 1)
                    left = parts[0].strip()
                    right = parts[1].strip()

                    # Check if left side is a variable
                    if left.startswith('$'):
                        var_name = left[1:]
                        var_value = str(self.variables.get(var_name, "")).lower()
                        stack.append(var_value == right.lower())
                    else:
                        # Regular comparison
                        stack.append(left.lower() == right.lower())
                elif token.startswith('$'):
                    # Boolean variable check ($var means "is var truthy")
                    var_name = token[1:]
                    val = self.variables.get(var_name, False)
                    is_true = bool(val) and str(val).lower() not in ['false', '0', 'no', '']
                    stack.append(is_true)
                else:
                    # Tag existence check
                    token_lower = token.lower()
                    stack.append(token_lower in context)

        return stack[0] if stack else False


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

        # Enhanced percentage support: {25%Red|75%Blue} or {50%yes|no}
        # Supports multiple percentages per option
        if '%' in content and '$$' not in content:
            parts = content.split('|')
            options = []
            total_pct = 0
            has_percentage = False
            
            for part in parts:
                part = part.strip()
                if '%' in part:
                    # Parse percentage: "25%Red" -> (25, "Red")
                    pct_split = part.split('%', 1)
                    try:
                        pct = float(pct_split[0])
                        text = pct_split[1].strip() if len(pct_split) > 1 else ""
                        options.append((pct, text))
                        total_pct += pct
                        has_percentage = True
                    except ValueError:
                        # Not a valid percentage, treat as regular option
                        options.append((None, part))
                else:
                    # No percentage, will get equal share of remaining
                    options.append((None, part))
            
            if has_percentage:
                # Calculate probabilities
                # If total < 100%, remaining = chance of empty result
                # If total > 100%, normalize all to sum to 100%
                
                roll = self.rng.random() * 100
                
                if total_pct > 100:
                    # Normalize: scale all percentages proportionally
                    scale = 100 / total_pct
                    cumulative = 0
                    for pct, text in options:
                        if pct is not None:
                            cumulative += pct * scale
                            if roll < cumulative:
                                return text
                    # Fallback to last option
                    return options[-1][1] if options else ""
                else:
                    # total <= 100%: remaining = empty chance
                    cumulative = 0
                    for pct, text in options:
                        if pct is not None:
                            cumulative += pct
                            if roll < cumulative:
                                return text
                    # Roll landed in the "empty" zone (remaining percentage)
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
        self.assign_regex = re.compile(r'^\$([a-zA-Z0-9_]+)\s*=\s*(.*?)$', re.MULTILINE)
        self.use_regex = re.compile(r'\$([a-zA-Z0-9_]+)((?:\.[a-zA-Z_]+)*)')
        self.variables = {}

    def load_globals(self, globals_dict):
        self.variables.update(globals_dict)

    def store_variables(self, text, tag_replacer, dynamic_replacer):
        def _replace_assign(match):
            var_name = match.group(1)
            raw_value = match.group(2).strip()
            
            resolved_value = raw_value
            for _ in range(10):  # Max iterations to prevent infinite loops
                prev_value = resolved_value
                resolved_value = tag_replacer.replace(resolved_value)
                resolved_value = dynamic_replacer.replace(resolved_value)
                if prev_value == resolved_value:
                    break
            
            self.variables[var_name] = resolved_value
            return ""  # Remove the assignment line from output
        return self.assign_regex.sub(_replace_assign, text)

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

        result = self.use_regex.sub(_replace_use, text)
        self.variables = original_vars  # Restore original for next iteration
        return result


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
        self.regex = re.compile(
            r'\[if\s+([^:|\]]+?)\s*:\s*((?:(?!\[if).)*?)(?:\s*\|\s*((?:(?!\[if).)*?))?\]', 
            re.IGNORECASE | re.DOTALL
        )

    def evaluate_logic(self, condition, context, variables=None):
        """Evaluate a logical condition against the context."""
        if variables is None: 
            variables = {}

        ops = {'AND': 'and', 'OR': 'or', 'NOT': 'not', 'XOR': '!=', 'NAND': 'nand', 'NOR': 'nor'}
        tokens = re.split(r'(\(|\)|\bNAND\b|\bNOR\b|\bAND\b|\bOR\b|\bNOT\b|\bXOR\b|&&|\|\||!|\^)', condition, flags=re.IGNORECASE)
        expression = []
        
        for token in tokens:
            token = token.strip()
            if not token: 
                continue

            # Handle symbolic operators
            if token == '&&':
                expression.append('and')
            elif token == '||':
                expression.append('or')
            elif token == '!':
                expression.append('not')
            elif token == '^':
                expression.append('!=')
            elif token in ('(', ')'):
                expression.append(token)
            else:
                upper_token = token.upper()
                if upper_token in ops:
                    if upper_token == 'NAND':
                        expression.append('nand')
                    elif upper_token == 'NOR':
                        expression.append('nor')
                    else:
                        expression.append(ops[upper_token])
                elif '=' in token:
                    left, right = token.split('=', 1)
                    left = left.strip()
                    right = right.strip()
                    
                    if left.startswith('$'):
                        var_name = left[1:]
                        left_val = str(variables.get(var_name, "")).lower()
                    else:
                        left_val = left.lower()
                    
                    expression.append(str(left_val == right.lower()))
                
                elif token.startswith('$'):
                    var_name = token[1:]
                    val = variables.get(var_name, False)
                    is_true = bool(val) and str(val).lower() not in ['false', '0', 'no']
                    expression.append(str(is_true))
                    
                else:
                    # Use regex word boundaries to prevent partial matching
                    pattern = r'\b' + re.escape(token.lower()) + r'\b'
                    exists = re.search(pattern, context.lower()) is not None
                    expression.append(str(exists))
        
        try:
            # Post-process to handle NAND and NOR
            processed_expr = []
            i = 0
            while i < len(expression):
                if expression[i] == 'nand' and i + 2 < len(expression):
                    a = processed_expr.pop() if processed_expr else 'False'
                    b = expression[i + 1] if i + 1 < len(expression) else 'False'
                    processed_expr.append(f'not ({a} and {b})')
                    i += 2
                elif expression[i] == 'nor' and i + 2 < len(expression):
                    a = processed_expr.pop() if processed_expr else 'False'
                    b = expression[i + 1] if i + 1 < len(expression) else 'False'
                    processed_expr.append(f'not ({a} or {b})')
                    i += 2
                else:
                    processed_expr.append(expression[i])
                    i += 1

            return eval(" ".join(processed_expr), {"__builtins__": None}, {})
        except:
            return False

    def replace(self, prompt, variables=None):
        """Replace conditional tags in the prompt."""
        if variables is None: 
            variables = {}
        
        while True:
            match = self.regex.search(prompt)
            if not match: 
                break
            
            full_tag = match.group(0)
            condition = match.group(1).strip()
            true_text = match.group(2)
            false_text = match.group(3) if match.group(3) else ""
            
            # Clean the context by removing ALL conditional tags
            context = self.regex.sub("", prompt)

            if self.evaluate_logic(condition, context, variables):
                replacement = true_text
            else:
                replacement = false_text
            
            prompt = prompt.replace(full_tag, replacement, 1)
        
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
        for location in self.wildcard_paths:
            file_path = os.path.join(location, f"{file_key}.txt")
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
        self.variables = {}
        self.seeded_values = {}
        self.scoped_negatives = []

    def update_variables(self, variables):
        """Update the variables dictionary."""
        self.variables = variables

    def clear_seeded_values(self):
        """Clear cached seeded values for a fresh run."""
        self.seeded_values = {}
        self.scoped_negatives = []

    def _weighted_choice(self, items):
        """Weighted random selection for lists with weights."""
        has_weights = all(isinstance(item, dict) and 'weight' in item for item in items)

        if not has_weights:
            return self.rng.choice(items)

        weights = [item.get('weight', 1.0) for item in items]
        total_weight = sum(weights)
        rand_val = self.rng.random() * total_weight
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
        self.clean_regex = re.compile(r'\[clean:(.*?)\]', re.IGNORECASE)
        self.shuffle_regex = re.compile(r'\[shuffle:(.*?)\]', re.IGNORECASE)

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
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r',\s*,', ',', content)
            content = content.replace(' ,', ',')
            return content.strip(', ')

        text = self.shuffle_regex.sub(_shuffle, text)
        text = self.clean_regex.sub(_clean, text)
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
