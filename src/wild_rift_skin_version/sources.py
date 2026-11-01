"""Parse public source data without evaluating remote Lua or JavaScript."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import json
import re
import unicodedata
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WIKI = "https://wiki.leagueoflegends.com/en-us/"
OFFICIAL = "https://wildrift.leagueoflegends.com"
CN_HEROES = "https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js"
CN_SKINS = "https://game.gtimg.cn/images/lgamem/act/lrlib/js/skins/skins.js"


def key(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).lower())


def parse_lua(source):
    pos = 0

    def fail(message):
        raise ValueError(f"Lua data at {pos}: {message}")

    def skip():
        nonlocal pos
        while pos < len(source):
            if source[pos].isspace():
                pos += 1
            elif source.startswith("--[[", pos):
                end = source.find("]]", pos + 4)
                if end < 0:
                    fail("unclosed comment")
                pos = end + 2
            elif source.startswith("--", pos):
                end = source.find("\n", pos)
                pos = len(source) if end < 0 else end + 1
            else:
                break

    def expect(token):
        nonlocal pos
        skip()
        if not source.startswith(token, pos):
            fail(f"expected {token}")
        pos += len(token)

    def string():
        nonlocal pos
        quote = source[pos]
        pos += 1
        text = []
        while pos < len(source):
            ch = source[pos]
            pos += 1
            if ch == quote:
                return "".join(text)
            if ch == "\\":
                if pos >= len(source):
                    fail("unclosed string")
                ch = source[pos]
                pos += 1
                ch = {"n": "\n", "r": "\r", "t": "\t"}.get(ch, ch)
            text.append(ch)
        fail("unclosed string")

    def value():
        nonlocal pos
        skip()
        if pos >= len(source):
            fail("missing value")
        if source[pos] in "\"'":
            return string()
        if source[pos] == "{":
            pos += 1
            result, index = {}, 1
            while True:
                skip()
                if pos >= len(source):
                    fail("unclosed table")
                if source[pos] == "}":
                    pos += 1
                    return result
                if source[pos] == "[":
                    pos += 1
                    field = value()
                    expect("]")
                    expect("=")
                else:
                    field, index = index, index + 1
                result[str(field)] = value()
                skip()
                if pos < len(source) and source[pos] in ",;":
                    pos += 1
                elif pos >= len(source) or source[pos] != "}":
                    fail("expected comma or table end")
        match = re.match(r"-?\d+(?:\.\d+)?|true\b|false\b|nil\b", source[pos:])
        if not match:
            fail("unsupported expression")
        token = match[0]
        pos += len(token)
        if token in ("true", "false", "nil"):
            return {"true": True, "false": False, "nil": None}[token]
        return float(token) if "." in token else int(token)

    expect("return")
    result = value()
    skip()
    if pos != len(source):
        fail("trailing expression")
    return result


def next_page(html):
    match = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html, re.I)
    if not match:
        raise ValueError("Official page is missing its structured data")
    page = json.loads(match[1]).get("props", {}).get("pageProps", {}).get("page")
    if not isinstance(page, dict) or not isinstance(page.get("blades"), list):
        raise ValueError("Official page schema changed")
    return page


def safe_image(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and (
            parsed.hostname in ("cmsassets.rgpub.io", "game.gtimg.cn")
            or (parsed.hostname == "wiki.leagueoflegends.com" and parsed.path.startswith("/en-us/images/"))
        )
    except ValueError:
        return False


def official_skins(page):
    carousel = next((b for b in page["blades"] if b.get("type") == "landingMediaCarousel"), {})
    groups = carousel.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError(f"Skin carousel missing: {page.get('url')}")
    result = []
    for group in groups[1:]:
        image = group.get("content", {}).get("media", {}).get("url")
        if not group.get("label") or not safe_image(image):
            raise ValueError(f"Invalid official skin: {page.get('url')}")
        result.append({"name": group["label"], "image": image, "source": page.get("url")})
    return result


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def patch_date(content):
    match = re.search(r"^\|\s*Release\s*=\s*(.+)$", content, re.I | re.M)
    if not match:
        return None
    value = re.sub(r"\{\{NumberSup\|(\d+)\}\}", r"\1", match[1], flags=re.I)
    value = re.sub(r"<[^>]+>", "", value).strip()
    if iso_date(value):
        return value
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", value)
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    if match:
        month = next((i for i, name in enumerate(months, 1) if match[1].lower() in (name, name[:3])), None)
        if month:
            return iso_date(f"{match[3]}-{month:02}-{int(match[2]):02}")
    return None


def patch_skins(content):
    section = re.search(r"^==\s*New Cosmetics\s*==\s*$([\s\S]*?)(?=^==[^=]|\Z)", content, re.I | re.M)
    if not section:
        return []
    records, parents, returning_section = [], {}, False
    returning = re.compile(r"\b(?:return(?:ing|s|ed)?|re[- ]?releas(?:e|ed|ing)|available again)\b", re.I)
    for raw in section[1].splitlines():
        line = raw.strip()
        bullet = re.match(r"^(\*+)\s*(.*)$", line)
        if not bullet:
            if re.match(r"^={3,}", line) or re.search(r"\breleased\b|following.*skins?.*(?:added|released)", line, re.I) or returning.search(line):
                returning_section = bool(returning.search(line))
                parents.clear()
            continue
        depth = len(bullet[1])
        parents = {level: flag for level, flag in parents.items() if level < depth}
        annotation = re.sub(r"\{\{\s*WRskin\|[^{}]+\}\}", "", bullet[2], flags=re.I)
        excluded = returning_section or any(parents.values()) or bool(returning.search(annotation) or re.search(r"\bchromas?\b", annotation, re.I))
        parents[depth] = excluded
        if excluded or not re.match(r"^\{\{\s*WRskin\|", bullet[2], re.I):
            continue
        for match in re.finditer(r"\{\{\s*WRskin\|([^|{}]+)\|([^|{}]+)(?:\|[^{}]*)?\}\}", line, re.I):
            if key(match[2]) != "original":
                records.append({"champion": match[1].strip(), "skin": match[2].strip()})
    return records


def patch_key(value):
    match = re.fullmatch(r"(\d+)\.(\d+)([a-z]*)", value, re.I)
    return (int(match[1]), int(match[2]), match[3]) if match else (0, 0, str(value))


def _base_poster(hero):
    match = re.search(r"/([^/]+)_0\.[a-z]+$", (hero or {}).get("poster", ""), re.I)
    return match[1] if match else None


def chinese_index(heroes, skins):
    owners = {}

    def claim(prefix, identity):
        if prefix:
            name, owner = key(prefix), str(identity)
            owners[name] = owner if name not in owners or owners[name] == owner else None

    for identity, hero in heroes.items():
        claim(_base_poster(hero), identity)
    for entry in skins.values():
        if str(entry["heroId"]) in heroes:
            match = re.search(r"/([^/]+)_\d+\.[a-z]+$", entry.get("poster", ""), re.I)
            claim(match[1] if match else None, entry["heroId"])
    result = {}
    for entry in skins.values():
        hero = heroes.get(str(entry["heroId"]))
        match = re.search(r"/([^/]+)_(\d+)\.[a-z]+$", entry.get("poster", ""), re.I)
        if not hero or not match or re.match(r"^HeroTitle_\d+$", entry["name"]):
            continue
        if owners.get(key(match[1])) != str(entry["heroId"]):
            continue
        identity = f"{entry['heroId']}:{int(match[2])}"
        if identity in result:
            raise ValueError(f"Ambiguous Chinese skin mapping: {identity}")
        result[identity] = {**entry, "heroName": hero["name"]}
    return result


def chinese_hero_ids(catalog, heroes):
    claimed = {str(champion.get("id")) for champion in catalog.values()}
    posters = {}
    for identity, hero in heroes.items():
        base = _base_poster(hero)
        if base and identity not in claimed:
            name = key(base)
            posters[name] = None if name in posters else identity
    return {
        name: str(champion["id"]) if str(champion.get("id")) in heroes else posters.get(key(name))
        for name, champion in catalog.items()
    }


def assert_catalog(payload, previous=None):
    if payload.get("game") != "wild-rift" or payload.get("region") != "international" or not isinstance(payload.get("skins"), list) or not payload["skins"]:
        raise ValueError("Invalid or empty Wild Rift catalog")
    ids, names = set(), set()
    for skin in payload["skins"]:
        identity = skin["id"]
        if not identity.startswith("wr:") or identity in ids:
            raise ValueError(f"Invalid/duplicate ID: {identity}")
        ids.add(identity)
        for name in [skin["name"], *skin.get("aliases", [])]:
            names.add(f"{key(skin['champion'])}:{key(name)}")
        if not skin.get("name") or not skin.get("champion") or not skin.get("nameZh"):
            raise ValueError(f"Missing name: {identity}")
        if skin.get("image") and not safe_image(skin["image"]):
            raise ValueError(f"Unexpected image host: {identity}")
        if skin.get("releaseDate") and not iso_date(skin["releaseDate"]):
            raise ValueError(f"Invalid release date: {identity}")
        if skin["version"] not in ("unverified", "upcoming", "regional") and not (skin.get("patchEvidence") or {}).get("url"):
            raise ValueError(f"Patch without evidence: {identity}")
        if skin.get("status") == "regional" and (skin.get("regionAvailability") != "cn-only" or skin["version"] != "regional" or skin.get("releaseDate") is not None):
            raise ValueError(f"Invalid regional record: {identity}")
    # Upcoming identities can change or be withdrawn before release.
    removed = [s for s in (previous or {}).get("skins", []) if s.get("status") != "upcoming" and s["id"] not in ids and f"{key(s['champion'])}:{key(s['name'])}" not in names]
    if removed:
        raise ValueError(f"Refusing to remove {len(removed)} existing skins: " + ", ".join(s["name"] for s in removed[:5]))
