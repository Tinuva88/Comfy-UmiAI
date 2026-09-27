"""Series-to-wildcard import helpers used by the Umi Danbooru browser.

The module deliberately keeps the expensive work out of the aiohttp event loop.
It talks to AniList for structured cast data, matches names against C-UMI's
bundled Danbooru autocomplete CSV, and builds safe, refreshable wildcard files.
"""

from __future__ import annotations

import csv
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone


ANILIST_API = "https://graphql.anilist.co"
DANBOORU_BASE = "https://danbooru.donmai.us"
_TAG_INDEX_CACHE = {}
_TAG_INDEX_LOCK = threading.Lock()
_VARIANT_CACHE = {}
_VARIANT_CACHE_LOCK = threading.Lock()
_WRITE_LOCK = threading.Lock()


def _safe_int(value, default=0, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _slug(value, fallback="item"):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or fallback


def _danbooru_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    value = value.replace("’", "'").replace("‘", "'")
    value = re.sub(r"[.·・]", " ", value)
    value = re.sub(r"[^\w:+'()\[\]-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def _tag_tokens(value):
    clean = re.sub(r"[()\[\]:+'-]+", "_", _danbooru_name(value))
    return tuple(token for token in clean.split("_") if token)


def _read_tag_rows(csv_path):
    rows = []
    with open(csv_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
        for parts in csv.reader(handle):
            if not parts or not parts[0].strip():
                continue
            name = parts[0].strip()
            category = _safe_int(parts[1] if len(parts) > 1 else 0)
            count = _safe_int(parts[2] if len(parts) > 2 else 0, minimum=0)
            aliases = tuple(
                alias.strip()
                for alias in (parts[3] if len(parts) > 3 else "").split(",")
                if alias.strip()
            )
            rows.append({
                "tag": name,
                "category": category,
                "post_count": count,
                "aliases": aliases,
            })
    return rows


def find_danbooru_csv(tag_dir):
    if not os.path.isdir(tag_dir):
        return None
    candidates = []
    for filename in os.listdir(tag_dir):
        lower = filename.lower()
        if not lower.endswith(".csv") or not lower.startswith("danbooru_"):
            continue
        if "e621" in lower or "merged" in lower or "cooccurrence" in lower:
            continue
        path = os.path.join(tag_dir, filename)
        candidates.append((os.path.getmtime(path), path))
    return max(candidates, default=(None, None))[1]


def load_tag_index(tag_dir, force=False):
    """Load the local tag database once, retaining counts, aliases and tokens."""
    csv_path = find_danbooru_csv(tag_dir)
    if not csv_path:
        return {
            "source": None,
            "by_name": {},
            "alias_to_names": {},
            "by_category": {},
            "token_index": {},
        }
    signature = (csv_path, os.path.getmtime(csv_path), os.path.getsize(csv_path))
    with _TAG_INDEX_LOCK:
        if not force and signature in _TAG_INDEX_CACHE:
            return _TAG_INDEX_CACHE[signature]

    by_name = {}
    alias_to_names = defaultdict(list)
    by_category = defaultdict(list)
    token_index = defaultdict(set)
    for row in _read_tag_rows(csv_path):
        tag = row["tag"]
        by_name[tag] = row
        by_category[row["category"]].append(row)
        for alias in row["aliases"]:
            alias_to_names[_danbooru_name(alias)].append(tag)
        if row["category"] in (3, 4):
            for token in set(_tag_tokens(tag)):
                if len(token) > 1:
                    token_index[token].add(tag)

    index = {
        "source": csv_path,
        "signature": signature,
        "by_name": by_name,
        "alias_to_names": dict(alias_to_names),
        "by_category": dict(by_category),
        "token_index": dict(token_index),
    }
    with _TAG_INDEX_LOCK:
        _TAG_INDEX_CACHE.clear()
        _TAG_INDEX_CACHE[signature] = index
    return index


def _retry_delay(response, attempt):
    header = response.headers.get("Retry-After") if response is not None else None
    try:
        delay = float(header)
    except (TypeError, ValueError):
        delay = 1.5 * (2 ** attempt)
    return min(20.0, max(0.5, delay))


def _http_post_json(url, payload, timeout=30, retries=4):
    import requests

    response = None
    for attempt in range(_safe_int(retries, 4, 0, 8) + 1):
        response = requests.post(
            url,
            json=payload,
            headers={"Accept": "application/json", "User-Agent": "UmiAI-ComfyUI/1.0"},
            timeout=timeout,
        )
        if response.status_code != 429 or attempt >= retries:
            response.raise_for_status()
            return response.json()
        time.sleep(_retry_delay(response, attempt))
    response.raise_for_status()


def _http_get_json(url, params=None, timeout=25, retries=3):
    try:
        from curl_cffi import requests as http_client
        request_kwargs = {"impersonate": "chrome"}
    except ImportError:
        import requests as http_client
        request_kwargs = {}

    auth = None
    if str(url).startswith(DANBOORU_BASE):
        login = os.environ.get("DANBOORU_LOGIN")
        api_key = os.environ.get("DANBOORU_API_KEY")
        if login and api_key:
            auth = (login, api_key)

    response = None
    for attempt in range(_safe_int(retries, 3, 0, 8) + 1):
        response = http_client.get(
            url,
            params=params or {},
            headers={"Accept": "application/json", "User-Agent": "UmiAI-ComfyUI/1.0"},
            auth=auth,
            timeout=timeout,
            **request_kwargs,
        )
        if response.status_code != 429 or attempt >= retries:
            response.raise_for_status()
            return response.json()
        time.sleep(_retry_delay(response, attempt))
    response.raise_for_status()


def _anilist(query, variables):
    payload = _http_post_json(ANILIST_API, {"query": query, "variables": variables})
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        messages = [str(item.get("message") or "AniList error") for item in errors if isinstance(item, dict)]
        raise RuntimeError("; ".join(messages) or "AniList returned an error")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("AniList returned an invalid response")
    return data


def search_anilist_media(search, media_type="ANIME", page=1, per_page=20):
    search = str(search or "").strip()
    if not search:
        return {"items": [], "page_info": {"current_page": 1, "has_next_page": False}}
    media_type = "MANGA" if str(media_type).upper() == "MANGA" else "ANIME"
    query = """
    query ($search: String!, $type: MediaType!, $page: Int!, $perPage: Int!) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { currentPage hasNextPage total }
        media(search: $search, type: $type, sort: SEARCH_MATCH) {
          id idMal type format status seasonYear episodes chapters siteUrl
          title { romaji english native userPreferred }
          synonyms
          coverImage { medium large }
        }
      }
    }
    """
    data = _anilist(query, {
        "search": search,
        "type": media_type,
        "page": _safe_int(page, 1, 1, 1000),
        "perPage": _safe_int(per_page, 20, 1, 50),
    })
    page_data = data.get("Page") or {}
    items = []
    for media in page_data.get("media") or []:
        if not isinstance(media, dict):
            continue
        title = media.get("title") or {}
        items.append({
            "id": media.get("id"),
            "mal_id": media.get("idMal"),
            "type": media.get("type"),
            "format": media.get("format"),
            "status": media.get("status"),
            "year": media.get("seasonYear"),
            "episodes": media.get("episodes"),
            "chapters": media.get("chapters"),
            "title": title.get("userPreferred") or title.get("romaji") or title.get("english") or "Untitled",
            "titles": [value for value in (
                title.get("userPreferred"), title.get("romaji"), title.get("english"), title.get("native"),
                *(media.get("synonyms") or []),
            ) if value],
            "cover": (media.get("coverImage") or {}).get("medium") or "",
            "cover_large": (media.get("coverImage") or {}).get("large") or "",
            "site_url": media.get("siteUrl") or "",
        })
    info = page_data.get("pageInfo") or {}
    return {
        "items": items,
        "page_info": {
            "current_page": info.get("currentPage") or 1,
            "has_next_page": bool(info.get("hasNextPage")),
            "total": info.get("total") or len(items),
        },
    }


def fetch_anilist_characters(media_id, max_characters=250, pages_per_request=4):
    """Fetch a popularity-sorted cast with several connection pages per query.

    AniList caps character connections at 25 items. GraphQL aliases let us fetch
    multiple pages in one HTTP request, which is materially faster and much less
    likely to hit the public API's shared rate limit on large franchises.
    ``max_characters=0`` requests the entire cast.
    """
    max_characters = _safe_int(max_characters, 250, minimum=0, maximum=2000)
    pages_per_request = _safe_int(pages_per_request, 4, minimum=1, maximum=8)
    connection_fragment = """
      pageInfo { currentPage hasNextPage total }
      edges {
        role
        node {
          id gender age favourites siteUrl
          name { full native alternative }
          image { medium large }
        }
      }
    """
    start_page = 1
    media_out = None
    characters = []
    seen = set()
    total_characters = None
    while True:
        if max_characters:
            remaining_pages = max(1, (max_characters - len(characters) + 24) // 25)
            chunk_size = min(pages_per_request, remaining_pages)
        else:
            chunk_size = pages_per_request
        aliases = "\n".join(
            f"c{page}: characters(page: {page}, perPage: 25, sort: [FAVOURITES_DESC]) {{ {connection_fragment} }}"
            for page in range(start_page, start_page + chunk_size)
        )
        query = f"""
        query ($id: Int!) {{
          Media(id: $id) {{
            id idMal type format seasonYear siteUrl
            title {{ romaji english native userPreferred }}
            synonyms
            coverImage {{ medium large }}
            {aliases}
          }}
        }}
        """
        data = _anilist(query, {"id": _safe_int(media_id)})
        media = data.get("Media")
        if not isinstance(media, dict):
            raise RuntimeError("AniList media was not found")
        if media_out is None:
            title = media.get("title") or {}
            media_out = {
                "id": media.get("id"),
                "mal_id": media.get("idMal"),
                "type": media.get("type"),
                "format": media.get("format"),
                "year": media.get("seasonYear"),
                "title": title.get("userPreferred") or title.get("romaji") or title.get("english") or "Untitled",
                "titles": [value for value in (
                    title.get("userPreferred"), title.get("romaji"), title.get("english"), title.get("native"),
                    *(media.get("synonyms") or []),
                ) if value],
                "cover": (media.get("coverImage") or {}).get("medium") or "",
                "cover_large": (media.get("coverImage") or {}).get("large") or "",
                "site_url": media.get("siteUrl") or "",
            }
        reached_end = False
        for page in range(start_page, start_page + chunk_size):
            connection = media.get(f"c{page}") or {}
            page_info = connection.get("pageInfo") or {}
            if total_characters is None:
                total_characters = _safe_int(page_info.get("total"), 0, minimum=0)
            for edge in connection.get("edges") or []:
                node = edge.get("node") if isinstance(edge, dict) else None
                if not isinstance(node, dict) or node.get("id") in seen:
                    continue
                seen.add(node.get("id"))
                name = node.get("name") or {}
                alternatives = [value for value in (name.get("alternative") or []) if value]
                characters.append({
                    "source_id": node.get("id"),
                    "name": name.get("full") or name.get("native") or "Unnamed character",
                    "native_name": name.get("native") or "",
                    "alternative_names": alternatives,
                    "gender": node.get("gender") or "Unknown",
                    "age": node.get("age") or "",
                    "favourites": _safe_int(node.get("favourites"), 0, minimum=0),
                    "role": str(edge.get("role") or "BACKGROUND").upper(),
                    "image": (node.get("image") or {}).get("medium") or "",
                    "image_large": (node.get("image") or {}).get("large") or "",
                    "site_url": node.get("siteUrl") or "",
                })
                if max_characters and len(characters) >= max_characters:
                    break
            if max_characters and len(characters) >= max_characters:
                reached_end = True
                break
            if not page_info.get("hasNextPage"):
                reached_end = True
                break
        if reached_end:
            break
        start_page += chunk_size
        if start_page > 80:
            raise RuntimeError("AniList returned too many character pages")
    role_order = {"MAIN": 0, "SUPPORTING": 1, "BACKGROUND": 2}
    characters.sort(key=lambda item: (role_order.get(item["role"], 3), -item["favourites"], item["name"].lower()))
    media_out["character_total"] = total_characters or len(characters)
    media_out["characters_truncated"] = bool(total_characters and len(characters) < total_characters)
    return media_out, characters


def _name_forms(character):
    raw_names = [character.get("name"), character.get("native_name")]
    raw_names.extend(character.get("alternative_names") or [])
    forms = []
    for raw in raw_names:
        clean = _danbooru_name(raw)
        if not clean:
            continue
        forms.append(clean)
        tokens = [token for token in clean.split("_") if token]
        if len(tokens) >= 2:
            forms.append("_".join(reversed(tokens)))
    return list(dict.fromkeys(forms))


def _primary_name_forms(character):
    primary = dict(character)
    primary["alternative_names"] = []
    return _name_forms(primary)


def _series_forms(media):
    return list(dict.fromkeys(_danbooru_name(value) for value in media.get("titles") or [media.get("title")] if value))


def _candidate_pool(index, forms):
    token_sets = []
    for form in forms:
        tokens = [token for token in _tag_tokens(form) if len(token) > 1]
        if not tokens:
            continue
        sets = [index["token_index"].get(token, set()) for token in tokens]
        sets = [value for value in sets if value]
        if sets:
            token_sets.append(set.intersection(*sets) if len(sets) > 1 else set(sets[0]))
    pool = set().union(*token_sets) if token_sets else set()
    return pool


def _score_candidate(row, forms, series_forms, primary_forms=None):
    tag = row["tag"]
    aliases = [_danbooru_name(alias) for alias in row.get("aliases") or ()]
    names = [tag, *aliases]
    primary_forms = set(primary_forms if primary_forms is not None else forms)
    best = 0
    reason = "fuzzy"
    for form in forms:
        penalty = 0 if form in primary_forms else 30
        if form == tag:
            best, reason = max((best, reason), (100 - penalty, "exact"), key=lambda value: value[0])
        if form in aliases:
            best, reason = max((best, reason), (96 - penalty, "alias"), key=lambda value: value[0])
        for name in names:
            bare = re.sub(r"(?:_\([^)]*\))+$", "", name)
            if form == bare:
                best, reason = max((best, reason), (90 - penalty, "disambiguated"), key=lambda value: value[0])
            elif name.startswith(form + "_(") or name.startswith(form + "_"):
                best, reason = max((best, reason), (76 - penalty, "name-prefix"), key=lambda value: value[0])
            else:
                wanted = set(_tag_tokens(form))
                actual = set(_tag_tokens(name))
                if wanted and wanted.issubset(actual):
                    overlap = int(72 + 18 * len(wanted) / max(1, len(actual))) - penalty
                    best, reason = max((best, reason), (overlap, "name-overlap"), key=lambda value: value[0])
    series_tokens = set(token for value in series_forms for token in _tag_tokens(value) if len(token) > 1)
    candidate_tokens = set(token for name in names for token in _tag_tokens(name))
    series_overlap = len(series_tokens & candidate_tokens)
    if series_overlap:
        best += min(12, series_overlap * 4)
        reason += "+series"
    return min(best, 100), reason


def match_character(character, media, index, limit=8):
    forms = _name_forms(character)
    primary_forms = _primary_name_forms(character)
    series_forms = _series_forms(media)
    names = set()
    for form in forms:
        row = index["by_name"].get(form)
        if row and row["category"] == 4:
            names.add(row["tag"])
        names.update(name for name in index["alias_to_names"].get(form, []) if index["by_name"].get(name, {}).get("category") == 4)
        for series in series_forms:
            for candidate in (f"{form}_({series})", f"{form}_({series.replace('_series', '')})"):
                row = index["by_name"].get(candidate)
                if row and row["category"] == 4:
                    names.add(row["tag"])
    names.update(name for name in _candidate_pool(index, forms) if index["by_name"].get(name, {}).get("category") == 4)
    ranked = []
    for name in names:
        row = index["by_name"][name]
        score, reason = _score_candidate(row, forms, series_forms, primary_forms)
        if score < 48:
            continue
        ranked.append({
            "tag": name,
            "post_count": row["post_count"],
            "aliases": list(row.get("aliases") or ()),
            "score": score,
            "reason": reason,
        })
    ranked.sort(key=lambda item: (-item["score"], -item["post_count"], item["tag"]))
    ranked = ranked[:_safe_int(limit, 8, 1, 25)]
    selected = ranked[0] if ranked and ranked[0]["score"] >= 75 else None
    return {
        "selected_tag": selected["tag"] if selected else "",
        "post_count": selected["post_count"] if selected else 0,
        "confidence": selected["reason"] if selected else ("review" if ranked else "unmatched"),
        "confidence_score": selected["score"] if selected else (ranked[0]["score"] if ranked else 0),
        "candidates": ranked,
    }


def match_copyright(media, index, limit=8):
    pseudo = {
        "name": media.get("title"),
        "native_name": "",
        "alternative_names": media.get("titles") or [],
    }
    forms = _name_forms(pseudo)
    names = set()
    for form in forms:
        row = index["by_name"].get(form)
        if row and row["category"] == 3:
            names.add(row["tag"])
        names.update(name for name in index["alias_to_names"].get(form, []) if index["by_name"].get(name, {}).get("category") == 3)
    names.update(name for name in _candidate_pool(index, forms) if index["by_name"].get(name, {}).get("category") == 3)
    ranked = []
    for name in names:
        row = index["by_name"][name]
        score, reason = _score_candidate(row, forms, forms)
        if score >= 48:
            ranked.append({"tag": name, "post_count": row["post_count"], "score": score, "reason": reason})
    ranked.sort(key=lambda item: (-item["score"], -item["post_count"], item["tag"]))
    ranked = ranked[:_safe_int(limit, 8, 1, 25)]
    selected = ranked[0] if ranked and ranked[0]["score"] >= 70 else None
    return {
        "selected_tag": selected["tag"] if selected else "",
        "confidence": selected["reason"] if selected else ("review" if ranked else "unmatched"),
        "candidates": ranked,
    }


def _identity_stems(row):
    stems = set()
    for value in (row["tag"], *(row.get("aliases") or ())):
        clean = _danbooru_name(value)
        stems.add(re.sub(r"(?:_\([^)]*\))+$", "", clean))
    return {stem for stem in stems if len(stem) >= 4}


def discover_local_variants(base_tag, index, limit=40):
    base = index["by_name"].get(base_tag)
    if not base or base.get("category") != 4:
        return []
    stems = _identity_stems(base)
    base_parentheticals = set(re.findall(r"\(([^)]*)\)", base_tag))
    candidates = set()
    for stem in stems:
        first = next((token for token in _tag_tokens(stem) if len(token) > 2), None)
        if first:
            candidates.update(index["token_index"].get(first, set()))
    variants = []
    for tag in candidates:
        if tag == base_tag:
            continue
        row = index["by_name"].get(tag)
        if not row or row.get("category") != 4:
            continue
        candidate_names = [row["tag"], *(row.get("aliases") or ())]
        identity_match = any(
            any(name == stem or name.startswith(stem + "_") or name.startswith(stem + "_(") for stem in stems)
            for name in candidate_names
        )
        if not identity_match:
            continue
        candidate_parentheticals = set(value for name in candidate_names for value in re.findall(r"\(([^)]*)\)", name))
        if base_parentheticals and not base_parentheticals.intersection(candidate_parentheticals):
            continue
        variants.append({
            "tag": tag,
            "post_count": row["post_count"],
            "source": "local-name",
            "verified": False,
            "include": True,
        })
    variants.sort(key=lambda item: (-item["post_count"], item["tag"]))
    return variants[:_safe_int(limit, 40, 1, 200)]


def discover_online_variants(base_tag, index, limit=100, delay=0.0):
    """Return active character-tag implications pointing at ``base_tag``."""
    cache_key = (base_tag, index.get("signature"))
    with _VARIANT_CACHE_LOCK:
        if cache_key in _VARIANT_CACHE:
            return [dict(item) for item in _VARIANT_CACHE[cache_key]]
    if delay:
        time.sleep(max(0.0, float(delay)))
    data = _http_get_json(
        f"{DANBOORU_BASE}/tag_implications.json",
        params={
            "search[consequent_name]": base_tag,
            "search[status]": "active",
            "limit": _safe_int(limit, 100, 1, 1000),
            "only": "antecedent_name,consequent_name,status",
        },
    )
    variants = []
    for item in data if isinstance(data, list) else []:
        tag = str(item.get("antecedent_name") or "").strip() if isinstance(item, dict) else ""
        row = index["by_name"].get(tag)
        if not tag or tag == base_tag or not row or row.get("category") != 4:
            continue
        variants.append({
            "tag": tag,
            "post_count": row["post_count"],
            "source": "danbooru-implication",
            "verified": True,
            "include": True,
        })
    variants.sort(key=lambda item: (-item["post_count"], item["tag"]))
    with _VARIANT_CACHE_LOCK:
        _VARIANT_CACHE[cache_key] = [dict(item) for item in variants]
    return variants


def enrich_characters(media, characters, tag_dir):
    index = load_tag_index(tag_dir)
    copyright_match = match_copyright(media, index)
    enriched = []
    for character in characters:
        item = dict(character)
        item.update(match_character(item, media, index))
        item["variants"] = discover_local_variants(item["selected_tag"], index) if item["selected_tag"] else []
        item["include"] = bool(item["selected_tag"])
        enriched.append(item)
    return {
        "media": media,
        "characters": enriched,
        "copyright_match": copyright_match,
        "tag_database": {
            "source": os.path.basename(index.get("source") or ""),
            "character_count": len(index.get("by_category", {}).get(4, [])),
            "copyright_count": len(index.get("by_category", {}).get(3, [])),
        },
    }


def character_is_eligible(character, filters):
    gender = str(filters.get("gender") or "all").lower()
    actual_gender = str(character.get("gender") or "Unknown").lower()
    if gender != "all" and gender != actual_gender:
        return False
    role = str(filters.get("role") or "all").upper()
    if role != "ALL" and role != str(character.get("role") or "").upper():
        return False
    if _safe_int(character.get("post_count"), 0) < _safe_int(filters.get("minimum_posts"), 0, minimum=0):
        return False
    if _safe_int(character.get("favourites"), 0) < _safe_int(filters.get("minimum_favourites"), 0, minimum=0):
        return False
    return bool(character.get("selected_tag"))


def _metadata_tags(character, variant=False):
    count = _safe_int(character.get("post_count"), 0, minimum=0)
    buckets = [value for value in (100, 500, 1000, 5000, 10000, 50000) if count >= value]
    tags = [
        _slug(character.get("gender") or "unknown"),
        _slug(character.get("role") or "background"),
    ]
    tags.extend(f"danbooru_{value}_plus" for value in buckets)
    if variant:
        tags.append("variant")
    return list(dict.fromkeys(tag for tag in tags if tag))


def _output_line(character, media, copyright_tag, output_format="danbooru", include_copyright=True, variant=None):
    base_tag = str(character.get("selected_tag") or "").strip()
    if output_format == "natural":
        if variant:
            name = str(variant.get("tag") or "").replace("_", " ")
        else:
            name = str(character.get("name") or base_tag.replace("_", " "))
        value = f"{name} from {media.get('title')}" if include_copyright and media.get("title") else name
    else:
        parts = []
        if variant and variant.get("tag"):
            parts.append(str(variant["tag"]).strip())
        if base_tag and base_tag not in parts:
            parts.append(base_tag)
        if include_copyright and copyright_tag and copyright_tag not in parts:
            parts.append(copyright_tag)
        value = ", ".join(parts)
    if output_format == "metadata":
        metadata_character = dict(character)
        if variant:
            metadata_character["post_count"] = variant.get("post_count", 0)
        tags = _metadata_tags(metadata_character, variant=bool(variant))
        if tags:
            value += "::" + ",".join(tags)
    return value.strip()


def prepare_wildcard_files(payload):
    """Build relative wildcard file contents without touching the filesystem."""
    target = str(payload.get("name") or "").replace("\\", "/").strip().strip("/")
    if not target:
        raise ValueError("A wildcard name is required")
    media = payload.get("media") if isinstance(payload.get("media"), dict) else {}
    copyright_tag = str(payload.get("copyright_tag") or "").strip()
    output_format = str(payload.get("output_format") or "danbooru").lower()
    if output_format not in {"danbooru", "natural", "metadata"}:
        raise ValueError("Unsupported output format")
    variant_mode = str(payload.get("variant_mode") or "none").lower()
    if variant_mode not in {"none", "flat", "grouped"}:
        raise ValueError("Unsupported variant mode")
    include_copyright = bool(payload.get("include_copyright", True))
    minimum_variant_posts = _safe_int(payload.get("minimum_variant_posts"), 0, minimum=0)
    main_lines = []
    files = {}
    records = []
    for source in payload.get("characters") or []:
        if not isinstance(source, dict) or not source.get("include", True) or not source.get("selected_tag"):
            continue
        character = dict(source)
        base_line = _output_line(character, media, copyright_tag, output_format, include_copyright)
        variants = []
        seen_variants = set()
        for variant in character.get("variants") or []:
            if not isinstance(variant, dict) or not variant.get("include", True):
                continue
            tag = str(variant.get("tag") or "").strip()
            if not tag or tag == character["selected_tag"] or tag in seen_variants:
                continue
            if _safe_int(variant.get("post_count"), 0) < minimum_variant_posts:
                continue
            seen_variants.add(tag)
            variants.append(dict(variant))
        if variant_mode == "flat":
            main_lines.append(base_line)
            main_lines.extend(
                _output_line(character, media, copyright_tag, output_format, include_copyright, variant)
                for variant in variants
            )
        elif variant_mode == "grouped" and variants:
            child_name = f"{target}/variants/{_slug(character['selected_tag'], 'character')}"
            child_lines = [base_line]
            child_lines.extend(
                _output_line(character, media, copyright_tag, output_format, include_copyright, variant)
                for variant in variants
            )
            files[child_name] = child_lines
            reference = f"__{child_name}__"
            if output_format == "metadata":
                tags = _metadata_tags(character)
                if tags:
                    reference += "::" + ",".join(tags)
            main_lines.append(reference)
        else:
            main_lines.append(base_line)
        record = dict(character)
        record["variants"] = variants
        records.append(record)
    files[target] = main_lines
    return {
        "target": target,
        "files": files,
        "characters": records,
        "line_count": sum(len(lines) for lines in files.values()),
    }


def _atomic_write_text(path, content):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".tmp.", dir=directory, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _safe_wildcard_path(root, name):
    normalized = str(name or "").replace("\\", "/").strip().strip("/")
    normalized = re.sub(r"[^A-Za-z0-9_./ -]+", "_", normalized).strip(" .")
    if not normalized:
        return None, None
    root = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root, normalized + ".txt"))
    try:
        inside = os.path.commonpath([root, path]) == root
    except (OSError, ValueError):
        inside = False
    return (normalized, path) if inside else (None, None)


def _write_wildcard_import_unlocked(payload, wildcard_root, manifest_root):
    prepared = prepare_wildcard_files(payload)
    mode = str(payload.get("mode") or "overwrite").lower()
    if mode not in {"append", "overwrite"}:
        raise ValueError("Unsupported write mode")
    written = []
    for name, lines in prepared["files"].items():
        normalized, path = _safe_wildcard_path(wildcard_root, name)
        if not path:
            raise ValueError(f"Invalid wildcard name: {name}")
        next_lines = [str(line).strip() for line in lines if str(line).strip()]
        if mode == "append" and os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as handle:
                existing = [line.strip() for line in handle.read().splitlines() if line.strip()]
            next_lines = list(dict.fromkeys([*existing, *next_lines]))
        else:
            next_lines = list(dict.fromkeys(next_lines))
        _atomic_write_text(path, "\n".join(next_lines) + ("\n" if next_lines else ""))
        written.append({"name": normalized, "path": os.path.relpath(path, wildcard_root).replace("\\", "/"), "lines": len(next_lines)})

    media = payload.get("media") if isinstance(payload.get("media"), dict) else {}
    manifest = {
        "version": 1,
        "source": "anilist",
        "media": media,
        "wildcard": prepared["target"],
        "copyright_tag": str(payload.get("copyright_tag") or ""),
        "filters": payload.get("filters") if isinstance(payload.get("filters"), dict) else {},
        "options": {
            "mode": mode,
            "output_format": str(payload.get("output_format") or "danbooru"),
            "include_copyright": bool(payload.get("include_copyright", True)),
            "variant_mode": str(payload.get("variant_mode") or "none"),
            "minimum_variant_posts": _safe_int(payload.get("minimum_variant_posts"), 0, minimum=0),
        },
        "characters": prepared["characters"],
        "written_files": written,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(manifest_root, exist_ok=True)
    manifest_id = f"anilist-{_safe_int(media.get('id'), 0)}-{_slug(prepared['target'])}"
    manifest_path = os.path.abspath(os.path.join(manifest_root, manifest_id + ".json"))
    manifest_root_abs = os.path.abspath(manifest_root)
    if os.path.commonpath([manifest_root_abs, manifest_path]) != manifest_root_abs:
        raise ValueError("Invalid manifest path")
    _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {
        "success": True,
        "manifest_id": manifest_id,
        "manifest": manifest,
        "written_files": written,
        "character_count": len(prepared["characters"]),
        "line_count": prepared["line_count"],
    }


def write_wildcard_import(payload, wildcard_root, manifest_root):
    """Serialize multi-file imports so concurrent requests cannot interleave."""
    with _WRITE_LOCK:
        return _write_wildcard_import_unlocked(payload, wildcard_root, manifest_root)


def list_manifests(manifest_root):
    items = []
    if not os.path.isdir(manifest_root):
        return items
    for filename in os.listdir(manifest_root):
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(manifest_root, filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            media = data.get("media") if isinstance(data, dict) else {}
            items.append({
                "id": filename[:-5],
                "media_id": media.get("id"),
                "title": media.get("title") or "Untitled",
                "wildcard": data.get("wildcard") or "",
                "updated_at": data.get("updated_at") or "",
                "character_count": len(data.get("characters") or []),
            })
        except Exception:
            continue
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items


def read_manifest(manifest_root, manifest_id):
    raw_id = str(manifest_id or "")
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "", raw_id)
    if not safe_id or safe_id != raw_id:
        return None
    root = os.path.abspath(manifest_root)
    path = os.path.abspath(os.path.join(root, safe_id + ".json"))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None
