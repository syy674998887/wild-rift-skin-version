"""Extract direct release evidence and infer only unambiguous patch dates."""
from datetime import date, datetime, timedelta
import re
import unicodedata

from .sources import iso_date, key, patch_key

OPEN_BETA_DATE = "2020-10-27"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def plain_text(html):
    text = re.sub(r"<[^>]*>", " ", str(html))
    text = re.sub(r"&#(x[0-9a-f]+|\d+);", lambda m: chr(int(m[1][1:], 16) if m[1].lower().startswith("x") else int(m[1])), text, flags=re.I)
    entities = {"nbsp": " ", "amp": "&", "quot": '"', "apos": "'", "lt": "<", "gt": ">"}
    text = re.sub(r"&(nbsp|amp|quot|apos|lt|gt);", lambda m: entities[m[1]], text)
    return re.sub(r"\s+", " ", text).strip()


def written_date(text, year=None):
    text = plain_text(re.sub(r"\{\{NumberSup\|(\d+)\}\}", r"\1", text, flags=re.I))
    match = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b", text, re.I)
    if match and (match[3] or year):
        return iso_date(f"{match[3] or year}-{MONTHS.index(match[1].lower()) + 1:02}-{int(match[2]):02}")
    return None


def official_patch_version(title):
    match = re.fullmatch(r"Wild Rift Patch(?: Notes)?\s+(\d+\.\d+[a-z]*)(?:\s+[-–—]\s+.+)?\s*", title, re.I)
    return match[1].lower() if match else None


def consistent_patch_date(reported, announced):
    if reported and announced and abs((date.fromisoformat(reported) - date.fromisoformat(announced)).days) > 7:
        return None
    return reported


def release_date(text, published):
    value = written_date(text, published[:4] if published else None)
    if value and not re.search(r"\b20\d{2}\b", text) and published and published[5:7] == "12" and value[5:7] == "01":
        value = str(int(value[:4]) + 1) + value[4:]
    time = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\s*\(?(UTC(?:[+-]\d{1,2})?|GMT[+-]\d{1,2}|PST|PDT)\b", text, re.I)
    if value and time:
        zone = time[4].upper()
        suffix = re.search(r"[+-]\d+$", zone)
        offset = -8 if zone == "PST" else -7 if zone == "PDT" else int(suffix[0]) if suffix else 0
        hour, minute = int(time[1]), int(time[2] or 0)
        if time[3]:
            hour = hour % 12 + (12 if time[3].upper() == "PM" else 0)
        if hour < 24 and minute < 60 and abs(offset) <= 14:
            value = (datetime.fromisoformat(value) + timedelta(hours=hour - offset, minutes=minute)).date().isoformat()
    return value


def mentioned_skins(text, name_index):
    words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text), re.I)
    max_length = max(map(len, name_index), default=0)
    result, start = [], 0
    while start < len(words):
        name, match = "", None
        end = start
        while end < len(words) and len(name) <= max_length:
            name += words[end].lower()
            if name in name_index:
                match = (end, " ".join(words[start:end + 1]))
            end += 1
        if match:
            start, label = match
            result.append(label)
        start += 1
    return result


def official_patch_skins(page, name_index):
    html = "\n".join((blade.get("richText") or {}).get("body", "") for blade in page["blades"])
    headings = list(re.finditer(r"<h([1-6])\b[^>]*>([\s\S]*?)</h\1>", html, re.I))
    result = []
    excluded = re.compile(r"\b(?:return(?:ing|s|ed)?|comeback|re[- ]release|available again|rework(?:ed)?|updated|skin selection|skin chest)\b", re.I)
    releasing = re.compile(r"\b(?:releas(?:ed|ing)|available|arrives?|launch(?:es)?)\b", re.I)
    starts = re.compile(r"\b(?:begin(?:s|ning)?|began|start(?:s|ing)?|kick(?:s|ing)? off|queue up for|launch(?:es|ing)?)\b", re.I)

    def add(label, value, section, scope=None, first_release=False):
        identity = name_index.get(key(re.sub(r"\s*\((?:Legendary|Epic)\)\s*$", "", label, flags=re.I)))
        if identity and not any(entry["id"] == identity for entry in result):
            item = {"id": identity, "releaseDate": value, "section": section, "excerpt": label}
            if scope:
                item["scope"] = scope
            if first_release:
                item["firstRelease"] = True
            result.append(item)

    for index, heading in enumerate(headings):
        title = plain_text(heading[2])
        skins = bool(re.fullmatch(r"(?:new\s+)?skins", title, re.I))
        ranked = bool(re.fullmatch(r"(?:ranked (?:season(?: \d+)?|s\d+)|new season)", title, re.I))
        wild_pass = bool(re.search(r"\b(?:wild|mini) pass\b", title, re.I))
        parent = next((h for h in reversed(headings[:index]) if int(h[1]) < int(heading[1])), None)
        event = bool(re.fullmatch(r"events?", plain_text(parent[2] if parent else ""), re.I))
        if not (skins or ranked or wild_pass or event):
            continue
        end = next((h.start() for h in headings[index + 1:] if int(h[1]) <= int(heading[1])), len(html))
        if (ranked or event) and index + 1 < len(headings):
            end = min(end, headings[index + 1].start())
        section = html[heading.end():end]
        if not skins:
            paragraphs = [plain_text(m[1]) for m in re.finditer(r"<(?:p|li)\b[^>]*>([\s\S]*?)</(?:p|li)>", section, re.I)]
            shared = next((value for text in paragraphs if starts.search(text) and not excluded.search(text)
                           if (value := release_date(text, page.get("displayedPublishDate")))), None) if ranked or event else None
            for text in paragraphs:
                if excluded.search(text) or re.search(r"\branked store\b", text, re.I):
                    continue
                relevant = (re.search(r"\b(?:reward|award|earn|skin)\b", text, re.I) if ranked
                            else re.search(r"\b(?:featuring|feature|starring|earn)\b", text, re.I) if wild_pass
                            else re.search(r"\b(?:earn|obtain|claim|receive)\b", text, re.I) and re.search(r"\b(?:new|special) skin\b", text, re.I))
                if not relevant:
                    continue
                value = shared or (release_date(text, page.get("displayedPublishDate")) if starts.search(text) or releasing.search(text) else None)
                if value:
                    for label in mentioned_skins(text, name_index):
                        add(label, value, title, None if ranked else "announcement", ranked)
            continue
        shared, returning = None, False
        for block in re.finditer(r"<(h[1-6]|p|td|li)\b[^>]*>([\s\S]*?)</\1>", section, re.I):
            tag, body = block[1].lower(), block[2]
            text = plain_text(body)
            if tag.startswith("h"):
                returning = bool(excluded.search(text) or re.search(r"\bchromas?\b", text, re.I))
                shared = None
            if (tag.startswith("h") or tag == "p") and excluded.search(text):
                returning = True
            if (tag.startswith("h") or tag == "p") and releasing.search(text) and not excluded.search(text):
                shared = release_date(text, page.get("displayedPublishDate"))
            if returning or excluded.search(text) or re.search(r"\b(?:chroma|pose)\b", text, re.I):
                continue
            labels = [text] + [plain_text(m[1]) for m in re.finditer(r"<p\b[^>]*>([\s\S]*?)</p>", body, re.I)]
            value = (release_date(text, page.get("displayedPublishDate")) if releasing.search(text) else None) or shared
            for label in labels:
                add(re.split(r"\b(?:Releasing|Available on)\b", label, flags=re.I)[0].strip(), value, title)
    return result


def choose_patch(candidates, release, conflicts=None):
    conflicts = conflicts if conflicts is not None else []
    valid = release if release and release >= "2020-01-01" else None
    for candidate in sorted(candidates, key=lambda c: (c.get("kind") != "wiki", patch_key(c["version"]))):
        if candidate.get("scope") == "announcement":
            conflicts.append(candidate)
            continue
        reference = candidate.get("date") or candidate.get("announcementDate")
        if valid and reference:
            delta = (date.fromisoformat(valid) - date.fromisoformat(reference)).days
            if delta < -14 or delta > 100:
                conflicts.append(candidate)
                continue
        return candidate
    return None


def verification_reason(skin, candidates=()):
    if skin.get("status") == "regional":
        return "region-unconfirmed"
    if skin.get("status") == "upcoming":
        return "upcoming"
    if skin.get("patchEvidence"):
        return None
    if candidates and all(c.get("scope") == "announcement" for c in candidates):
        return "announcement-only"
    if candidates:
        return "date-conflict"
    if not skin.get("releaseDate"):
        return "missing-release-date"
    if skin["releaseDate"] < OPEN_BETA_DATE:
        return "early-history"
    return "missing-patch-record"


def patch_timeline(entries):
    timeline = []
    for entry in sorted(entries, key=lambda e: patch_key(e["version"])):
        valid = sorted(value for value in entry["dates"] if value and (not timeline or value >= timeline[-1]["from"]))
        if valid:
            timeline.append({"version": entry["version"], "from": valid[0], "to": valid[-1]})
    return timeline


def infer_patch(value, timeline):
    for index in range(len(timeline) - 1, -1, -1):
        if timeline[index]["to"] <= value:
            return timeline[index] if all(patch["from"] > value for patch in timeline[index + 1:]) else None
    return None
