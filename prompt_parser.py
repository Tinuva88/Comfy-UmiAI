"""
Small parser layer for Umi prompt syntax.

This module is intentionally narrow for now: it provides shared token/span
helpers and a parser for negative prompt syntax. The rest of the prompt engine
can migrate here syntax family by syntax family.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpan:
    kind: str
    start: int
    end: int
    content: str
    condition: str = ""


@dataclass(frozen=True)
class LoraSpec:
    span: PromptSpan
    name: str
    strength: float = 1.0
    options: dict = None


@dataclass(frozen=True)
class WildcardSpec:
    span: PromptSpan
    kind: str
    key: str = ""
    fallback: str = ""
    logic: str = ""
    count_min: int = 1
    count_max: int = 1
    sequential: bool = False


@dataclass(frozen=True)
class FunctionSpec:
    span: PromptSpan
    name: str
    content: str = ""


@dataclass(frozen=True)
class ConditionalSpec:
    span: PromptSpan
    branches: tuple
    else_text: str = ""


def split_escaped_csv(text):
    if text is None:
        return []
    parts = []
    current = []
    escape = False
    for ch in str(text):
        if escape:
            current.append(ch)
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == ',':
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(ch)
    if escape:
        current.append('\\')
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def parse_key_value_csv(text):
    values = {}
    for part in split_escaped_csv(text):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            values[key] = value
    return values


def find_settings_spans(text, allowed_keys=None):
    """Return @@key=value@@ settings spans in source order."""
    if not text:
        return []
    allowed = set(allowed_keys or ("width", "height"))
    spans = []
    for match in re.finditer(r'@@(.*?)@@', text, flags=re.DOTALL):
        values = parse_key_value_csv(match.group(1))
        if not values or not any(key in allowed for key in values):
            continue
        spans.append(PromptSpan("settings", match.start(), match.end(), match.group(1).strip()))
    return spans


def parse_settings(text, allowed_keys=None):
    settings = {}
    for span in find_settings_spans(text, allowed_keys=allowed_keys):
        settings.update(parse_key_value_csv(span.content))
    return settings


def _split_option_tokens(text):
    tokens = str(text or "").split()
    option_tokens = []
    while tokens and "=" in tokens[-1]:
        option_tokens.insert(0, tokens.pop())
    return " ".join(tokens).strip(), option_tokens


def parse_lora_content(content):
    spec, option_tokens = _split_option_tokens(content)
    options = {}
    for option in option_tokens:
        key, value = option.split("=", 1)
        options[key.strip().lower()] = value.strip().lower()

    name = spec.strip()
    strength = 1.0
    if ":" in spec:
        candidate_name, candidate_strength = spec.rsplit(":", 1)
        try:
            strength = float(candidate_strength.strip())
            name = candidate_name.strip()
        except ValueError:
            name = spec.strip()
    return name, strength, options


def find_lora_spans(text):
    if not text:
        return []
    spans = []
    for match in re.finditer(r'<lora:([^>]*)>', text, flags=re.IGNORECASE):
        spans.append(PromptSpan("lora", match.start(), match.end(), match.group(1).strip()))
    return spans


def parse_lora_specs(text):
    specs = []
    for span in find_lora_spans(text):
        name, strength, options = parse_lora_content(span.content)
        if not name:
            continue
        specs.append(LoraSpec(span=span, name=name, strength=strength, options=options))
    return specs


def _split_unescaped_once(text, delimiter):
    current = []
    escape = False
    for idx, ch in enumerate(str(text or "")):
        if escape:
            current.append(ch)
            escape = False
            continue
        if ch == '\\':
            current.append(ch)
            escape = True
            continue
        if ch == delimiter:
            return "".join(current), text[idx + 1:]
        current.append(ch)
    return text, None


def _parse_wildcard_content(content, span):
    raw = str(content or "").strip()
    fallback = ""
    body, fallback_part = _split_unescaped_once(raw, "|")
    if fallback_part is not None:
        raw = body.strip()
        fallback = fallback_part.strip()

    if raw.startswith("[") and raw.endswith("]"):
        return WildcardSpec(span=span, kind="yaml_logic", logic=raw[1:-1].strip(), fallback=fallback)

    if raw.startswith("@") and ":" not in raw:
        return WildcardSpec(span=span, kind="prompt_file", key=raw[1:].strip(), fallback=fallback)

    sequential = False
    if raw.startswith("~"):
        sequential = True
        raw = raw[1:].strip()

    range_match = re.match(r'^(\d+)-(\d+)\$\$(.+)$', raw)
    if range_match:
        return WildcardSpec(
            span=span,
            kind="range",
            key=range_match.group(3).strip(),
            fallback=fallback,
            count_min=int(range_match.group(1)),
            count_max=int(range_match.group(2)),
            sequential=sequential,
        )

    logic_match = re.match(r'^(.+?)\[([^\]\r\n]+)\]$', raw)
    if logic_match:
        return WildcardSpec(
            span=span,
            kind="file_logic",
            key=logic_match.group(1).strip(),
            logic=logic_match.group(2).strip(),
            fallback=fallback,
            sequential=sequential,
        )

    return WildcardSpec(span=span, kind="simple", key=raw, fallback=fallback, sequential=sequential)


def find_wildcard_spans(text):
    if not text:
        return []
    spans = []
    for match in re.finditer(r'__([^\r\n]+?)__', text):
        content = match.group(1)
        if not content.strip():
            continue
        spans.append(PromptSpan("wildcard", match.start(), match.end(), content.strip()))
    return spans


def parse_wildcard_specs(text):
    return [_parse_wildcard_content(span.content, span) for span in find_wildcard_spans(text)]


def find_angle_yaml_spans(text):
    if not text:
        return []
    spans = []
    for match in re.finditer(r'<\[([^\]]+)\]>', text):
        content = match.group(1).strip()
        if content:
            spans.append(PromptSpan("angle_yaml", match.start(), match.end(), content))
    return spans


def parse_angle_yaml_specs(text):
    specs = []
    for span in find_angle_yaml_spans(text):
        specs.append(WildcardSpec(span=span, kind="angle_yaml", key=span.content, logic=span.content))
    return specs


def _find_matching_bracket(text, start):
    depth = 0
    quote = ""
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
            continue
        if ch == "[":
            depth += 1
            continue
        if ch == "]":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _parse_function_body(body, allowed):
    body = str(body or "").strip()
    if not body:
        return None

    colon_idx = body.find(":")
    if colon_idx > 0:
        name = body[:colon_idx].strip().lower()
        if re.match(r'^[a-z_][a-z0-9_]*$', name) and (allowed is None or name in allowed):
            return name, body[colon_idx + 1:].strip()

    sample_match = re.match(r'^(sample)\s+(.+)$', body, flags=re.IGNORECASE | re.DOTALL)
    if sample_match:
        name = sample_match.group(1).lower()
        if allowed is None or name in allowed:
            return name, sample_match.group(2).strip()

    return None


def find_function_spans(text, names=None):
    """Return parser-backed bracket function spans in source order."""
    if not text:
        return []
    allowed = {name.lower() for name in names} if names else None
    spans = []
    idx = 0
    while idx < len(text):
        start = text.find("[", idx)
        if start == -1:
            break
        end = _find_matching_bracket(text, start)
        if end == -1:
            break
        parsed = _parse_function_body(text[start + 1:end], allowed)
        if parsed:
            name, content = parsed
            spans.append(PromptSpan(f"function:{name}", start, end + 1, content))
        idx = end + 1
    return spans


def parse_function_specs(text, names=None):
    specs = []
    for span in find_function_spans(text, names=names):
        name = span.kind.split(":", 1)[1] if ":" in span.kind else ""
        specs.append(FunctionSpec(span=span, name=name, content=span.content))
    return specs


def _is_word_at(text, idx, word):
    segment = text[idx:idx + len(word)]
    if segment.lower() != word:
        return False
    before = text[idx - 1] if idx > 0 else ""
    after = text[idx + len(word)] if idx + len(word) < len(text) else ""
    if word.lower() == "else":
        return (not before or before.isspace()) and after == ":"
    return (not before or before.isspace()) and (not after or after.isspace() or after == ":")


def _find_top_level_char(text, target, start=0):
    depth_bracket = 0
    depth_brace = 0
    quote = ""
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
            continue
        if ch == "[":
            depth_bracket += 1
            continue
        if ch == "]":
            depth_bracket -= 1
            continue
        if ch == "{":
            depth_brace += 1
            continue
        if ch == "}":
            depth_brace -= 1
            continue
        if ch == target and depth_bracket == 0 and depth_brace == 0:
            return idx
    return -1


def _find_top_level_keyword(text, word, start=0):
    depth_bracket = 0
    depth_brace = 0
    quote = ""
    escape = False
    idx = start
    while idx < len(text):
        ch = text[idx]
        if escape:
            escape = False
            idx += 1
            continue
        if ch == "\\":
            escape = True
            idx += 1
            continue
        if quote:
            if ch == quote:
                quote = ""
            idx += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            idx += 1
            continue
        if ch == "[":
            depth_bracket += 1
            idx += 1
            continue
        if ch == "]":
            depth_bracket -= 1
            idx += 1
            continue
        if ch == "{":
            depth_brace += 1
            idx += 1
            continue
        if ch == "}":
            depth_brace -= 1
            idx += 1
            continue
        if depth_bracket == 0 and depth_brace == 0 and _is_word_at(text, idx, word):
            return idx
        idx += 1
    return -1


def _parse_conditional_inner(inner, span):
    match = re.match(r'if\s+', inner, flags=re.IGNORECASE)
    if not match:
        return None
    content = inner[match.end():]
    colon = _find_top_level_char(content, ":")
    if colon == -1:
        return None

    condition = content[:colon].strip()
    rest = content[colon + 1:]
    if not condition:
        return None

    elif_pos = _find_top_level_keyword(rest, "elif")
    else_pos = _find_top_level_keyword(rest, "else")
    has_keyword_branches = elif_pos != -1 or else_pos != -1

    if not has_keyword_branches:
        pipe = _find_top_level_char(rest, "|")
        if pipe == -1:
            return ConditionalSpec(span=span, branches=((condition, rest.strip()),), else_text="")
        return ConditionalSpec(
            span=span,
            branches=((condition, rest[:pipe].strip()),),
            else_text=rest[pipe + 1:].strip(),
        )

    branches = []
    current_condition = condition
    segment_start = 0
    idx = 0
    while idx < len(rest):
        next_elif = _find_top_level_keyword(rest, "elif", idx)
        next_else = _find_top_level_keyword(rest, "else", idx)
        positions = [pos for pos in (next_elif, next_else) if pos != -1]
        if not positions:
            branches.append((current_condition, rest[segment_start:].strip()))
            return ConditionalSpec(span=span, branches=tuple(branches), else_text="")

        next_pos = min(positions)
        if next_else == next_pos:
            branches.append((current_condition, rest[segment_start:next_pos].strip()))
            after_else = next_pos + 4
            if after_else < len(rest) and rest[after_else] == ":":
                after_else += 1
            return ConditionalSpec(span=span, branches=tuple(branches), else_text=rest[after_else:].strip())

        branches.append((current_condition, rest[segment_start:next_pos].strip()))
        cond_start = next_pos + 4
        while cond_start < len(rest) and rest[cond_start].isspace():
            cond_start += 1
        colon = _find_top_level_char(rest, ":", cond_start)
        if colon == -1:
            return None
        current_condition = rest[cond_start:colon].strip()
        if not current_condition:
            return None
        segment_start = colon + 1
        idx = segment_start

    branches.append((current_condition, rest[segment_start:].strip()))
    return ConditionalSpec(span=span, branches=tuple(branches), else_text="")


def find_conditional_spans(text):
    if not text:
        return []
    spans = []
    idx = 0
    while idx < len(text):
        start = text.lower().find("[if ", idx)
        if start == -1:
            break
        end = _find_matching_bracket(text, start)
        if end == -1:
            break
        inner = text[start + 1:end]
        spans.append(PromptSpan("conditional", start, end + 1, inner.strip()))
        idx = end + 1
    return spans


def parse_conditional_specs(text):
    specs = []
    for span in find_conditional_spans(text):
        spec = _parse_conditional_inner(span.content, span)
        if spec:
            specs.append(spec)
    return specs


def _parse_cli_negative(text, idx):
    token = "--neg:"
    j = idx + len(token)
    while j < len(text) and text[j] in " \t":
        j += 1
    if j >= len(text):
        return PromptSpan("negative_cli", idx, j, "")
    if text[j] in ("'", '"'):
        quote = text[j]
        j += 1
        buf = []
        while j < len(text):
            ch = text[j]
            if ch == '\\' and j + 1 < len(text):
                buf.append(ch)
                buf.append(text[j + 1])
                j += 2
                continue
            if ch == quote:
                j += 1
                break
            buf.append(ch)
            j += 1
        return PromptSpan("negative_cli", idx, j, "".join(buf).strip())

    buf = []
    while j < len(text) and text[j] != '\n':
        ch = text[j]
        if ch == '\\' and j + 1 < len(text):
            buf.append(ch)
            buf.append(text[j + 1])
            j += 2
            continue
        buf.append(ch)
        j += 1
    return PromptSpan("negative_cli", idx, j, "".join(buf).strip())


def find_negative_spans(text):
    """Return negative syntax spans in source order."""
    if not text:
        return []

    spans = []
    spans.extend(
        PromptSpan("negative_bold", m.start(), m.end(), m.group(1).strip())
        for m in re.finditer(r'\*\*(.*?)\*\*', text, flags=re.DOTALL)
    )
    spans.extend(
        PromptSpan("negative_if_block", m.start(), m.end(), m.group(2).strip(), m.group(1).strip())
        for m in re.finditer(r'\[neg_if:([^\]]+)\]([\s\S]*?)\[/neg_if\]', text, flags=re.IGNORECASE)
    )
    spans.extend(
        PromptSpan("negative_block", m.start(), m.end(), m.group(1).strip())
        for m in re.finditer(r'\[(?:neg|negative)\]([\s\S]*?)\[/\s*(?:neg|negative)\]', text, flags=re.IGNORECASE)
    )
    spans.extend(
        PromptSpan("negative_inline", m.start(), m.end(), m.group(1).strip())
        for m in re.finditer(r'\[(?:neg|negative):([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]', text, flags=re.IGNORECASE)
    )

    i = 0
    while True:
        idx = text.find("--neg:", i)
        if idx == -1:
            break
        span = _parse_cli_negative(text, idx)
        spans.append(span)
        i = max(span.end, idx + 1)

    spans.sort(key=lambda span: (span.start, span.end))
    return spans


def remove_spans(text, spans):
    if not spans:
        return text or ""
    cleaned = []
    cursor = 0
    for span in spans:
        if span.start < cursor:
            continue
        cleaned.append(text[cursor:span.start])
        cursor = span.end
    cleaned.append(text[cursor:])
    return "".join(cleaned)
