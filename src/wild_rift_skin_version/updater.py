"""Synchronize Wiki, international Riot pages and the official CN catalog."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import cmp_to_key
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlencode, urljoin, urlparse

from .http import fetch_text
from .metadata import skin_metadata, wiki_files
from .patches import (
    OPEN_BETA_DATE, choose_patch, consistent_patch_date, infer_patch,
    official_patch_skins, official_patch_version, patch_timeline, verification_reason,
)
from .sources import (
    CN_HEROES, CN_SKINS, OFFICIAL, PROJECT_ROOT, WIKI, assert_catalog,
    chinese_hero_ids, chinese_index, iso_date, key, next_page, official_skins,
    parse_lua, patch_date, patch_key, patch_skins, safe_image,
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_bytes_atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, payload):
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if not path.exists() or path.read_bytes() != encoded:
        _write_bytes_atomic(path, encoded)


def map_limit(items, function, concurrency=4):
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        return list(executor.map(function, items))


class SourceReader:
    def __init__(self, *, cached=False, root=PROJECT_ROOT, fetcher=fetch_text):
        self.cached, self.root, self.fetcher = cached, root, fetcher
        self.cache = root / ".cache"
        self.oldest_fetch = utc_now()
        self.wiki_lock = threading.Lock()

    def get(self, url):
        filename = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if self.cached:
            entry = json.loads(filename.read_text(encoding="utf-8"))
            if entry["url"] != url:
                raise ValueError("Cache key mismatch")
            self.oldest_fetch = min(self.oldest_fetch, entry["fetchedAt"])
            return entry["body"]
        body = self.fetcher(url)
        fetched_at = utc_now()
        write_json(filename, {"url": url, "fetchedAt": fetched_at, "body": body})
        return body

    def wiki(self, params):
        with self.wiki_lock:
            try:
                body = self.get(WIKI + "api.php?" + urlencode({"action": "query", "format": "json", "formatversion": "2", **params}))
            finally:
                if not self.cached:
                    time.sleep(1)
        response = json.loads(body)
        if response.get("error"):
            raise ValueError(f"Wiki: {response['error']['info']}")
        return response

    def revisions(self, titles):
        response = self.wiki({"prop": "revisions", "rvprop": "ids|timestamp|content", "rvslots": "main", "titles": "|".join(titles)})
        pages = []
        for page in response["query"]["pages"]:
            if page.get("missing"):
                continue
            revision = page["revisions"][0]
            pages.append({
                "title": page["title"], **revision,
                "content": revision["slots"]["main"]["content"],
                "url": WIKI + "index.php?" + urlencode({"title": page["title"], "oldid": revision["revid"]}),
            })
        return pages


def build_snapshot(reader, previous=None, today=None):
    today = today or datetime.now(timezone.utc).date().isoformat()
    print("Fetching Wild Rift catalog and official localization...", flush=True)
    module_pages = reader.revisions(["Module:SkinDataWR/data"])
    champion_html, heroes_text, skins_text = map_limit([OFFICIAL + "/en-us/champions/", CN_HEROES, CN_SKINS], reader.get)
    if len(module_pages) != 1:
        raise ValueError("Missing Wild Rift skin module")
    module = module_pages[0]
    catalog = parse_lua(module["content"])
    translations = json.loads((reader.root / "data/translations.json").read_text(encoding="utf-8"))
    heroes = json.loads(heroes_text)["heroList"]
    cn_skins = json.loads(skins_text)
    chinese = chinese_index(heroes, cn_skins["skinList"])
    cn_hero_ids = chinese_hero_ids(catalog, heroes)
    index = next((b for b in next_page(champion_html)["blades"] if b.get("type") == "characterCardGrid"), {})
    items = index.get("items", [])
    if not items or len(items) != index.get("async", {}).get("metadata", {}).get("totalItems"):
        raise ValueError("Incomplete official champion index; pagination/schema needs review")
    diagnostics = {name: [] for name in ("unmatchedOfficialSkins", "missingArtwork", "patchDateConflicts", "missingWikiIds", "invalidReleaseDates", "patchDateDisagreements")}

    def read_champion(item):
        url = urljoin(OFFICIAL, item["action"]["payload"]["url"])
        if urlparse(url).scheme + "://" + urlparse(url).netloc != OFFICIAL:
            raise ValueError("Unexpected champion page origin")
        return {"name": item["title"], "url": url, "skins": official_skins(next_page(reader.get(url)))}

    print(f"Fetching {len(items)} official champion pages...", flush=True)
    official_pages = map_limit(items, read_champion)
    print("Fetching Wild Rift patch history...", flush=True)
    titles, continuation = [], {}
    while True:
        response = reader.wiki({"list": "allpages", "apnamespace": "3004", "apprefix": "V", "aplimit": "max", **continuation})
        titles.extend(p["title"] for p in response["query"]["allpages"] if re.fullmatch(r"WR:V\d+\.\d+[a-z]*", p["title"]))
        continuation = response.get("continue")
        if not continuation:
            break
    batches = [titles[start:start + 30] for start in range(0, len(titles), 30)]
    patches = [page for batch in map_limit(batches, reader.revisions, 2) for page in batch]
    print("Fetching official patch announcements...", flush=True)
    sitemap = reader.get(OFFICIAL + "/en-us/sitemap_loc.xml")
    urls = [url for url in re.findall(r"<loc>([^<]+)</loc>", sitemap)
            if url.startswith(OFFICIAL + "/en-us/news/") and re.search(r"/wild-rift-(?:patch-notes|patch-\d)", url)]
    if len(urls) < 100:
        raise ValueError("Incomplete official patch sitemap")
    official_patches = [item for item in map_limit(urls, lambda url: {"url": url, "page": next_page(reader.get(url))})
                        if official_patch_version(item["page"]["title"])]
    announcements = {}
    for item in official_patches:
        page = item["page"]
        version = official_patch_version(page["title"])
        announced = iso_date((page.get("displayedPublishDate") or "")[:10])
        if announced and (version not in announcements or announced < announcements[version]):
            announcements[version] = announced
    evidence, patch_dates = {}, {}
    for page in patches:
        version = page["title"].replace("WR:V", "")
        reported = patch_date(page["content"])
        announced = announcements.get(version)
        value = consistent_patch_date(reported, announced)
        if reported and not value:
            diagnostics["patchDateDisagreements"].append({"version": version, "reported": reported, "announcementDate": announced})
        patch_dates[version] = value
        for entry in patch_skins(page["content"]):
            identity = key(entry["champion"]) + ":" + key(entry["skin"])
            evidence.setdefault(identity, []).append({
                "version": version, "date": value, "url": page["url"], "revision": page["revid"],
                "title": page["title"], "kind": "wiki", "announcementDate": announced,
            })
    print("Resolving Wild Rift artwork and chroma images...", flush=True)
    file_titles = []
    for champion, data in catalog.items():
        for name, entry in data.get("skins", {}).items():
            if name == "Original" or entry.get("id") == 0:
                continue
            files = wiki_files(champion, name, entry.get("chromas"))
            file_titles.extend([files[n] for n in ("splash", "loading", "tile", "videoWebm", "videoMp4")] + list(files["chromas"].values()))
    batches = [file_titles[start:start + 40] for start in range(0, len(file_titles), 40)]
    images = {}
    for result in map_limit(batches, lambda batch: reader.wiki({"prop": "imageinfo", "iiprop": "url|size|mime", "titles": "|".join(batch)}), 2):
        for page in result["query"]["pages"]:
            info = page.get("imageinfo") or []
            if info and safe_image(info[0].get("url")):
                images[page["title"]] = info[0]
    records, candidates_by_id, lines, official_names = [], {}, {}, {}
    for page in official_pages:
        for skin in page["skins"]:
            identity = key(page["name"]) + ":" + key(skin["name"])
            if identity in official_names:
                raise ValueError(f"Ambiguous official skin name: {identity}")
            official_names[identity] = {**skin, "champion": page["name"]}
    matched_official = set()
    for champion, data in catalog.items():
        for skin_name, entry in data.get("skins", {}).items():
            if skin_name == "Original" or entry.get("id") == 0:
                continue
            numeric = type(data.get("id")) is int and type(entry.get("id")) is int
            identity = f"wr:{data['id']}:{entry['id']}" if numeric else f"wr:wiki:{key(champion)}:{key(skin_name)}"
            if not numeric:
                diagnostics["missingWikiIds"].append(identity)
            name = entry.get("formatname") or (skin_name if key(skin_name).endswith(key(champion)) else f"{skin_name} {champion}")
            labels = [name, f"{skin_name} {champion}", skin_name]
            official_key = next((key(champion) + ":" + key(label) for label in labels if key(champion) + ":" + key(label) in official_names), None)
            official = official_names.get(official_key)
            if official:
                matched_official.add(official_key)
            official_image = (official or {}).get("image")
            cn_hero_id = cn_hero_ids.get(champion)
            cn = chinese.get(f"{cn_hero_id}:{entry['id']}") if cn_hero_id and type(entry.get("id")) is int else None
            cn_data = cn or {}
            release = iso_date(entry.get("release"))
            displayed = release if release and release >= "2020-01-01" else None
            if release and not displayed:
                diagnostics["invalidReleaseDates"].append({"id": identity, "reported": release})
            candidates = sorted(evidence.get(key(champion) + ":" + key(skin_name), []), key=lambda c: patch_key(c["version"]))
            candidates_by_id[identity] = candidates
            direct = choose_patch(candidates, displayed)
            future = bool((displayed and displayed > today) or (not displayed and entry.get("availability") == "Upcoming"))
            line_ids = [v for v in entry.get("set", {}).values() if isinstance(v, str) and v != "N/A"]
            for line in line_ids:
                lines[line] = {"id": line, "name": line, "nameZh": translations["skinLines"].get(line) or line}
            files = wiki_files(champion, skin_name, entry.get("chromas"))
            wiki_art = {kind: images[files[source]]["url"] for kind, source in (("uncentered", "splash"), ("loading", "loading"), ("tile", "tile")) if files[source] in images}
            video = next((images[files[n]] for n in ("videoWebm", "videoMp4") if images.get(files[n], {}).get("mime") in ("video/webm", "video/mp4")), None)
            image = official_image or wiki_art.get("uncentered") or (cn_data.get("poster") if safe_image(cn_data.get("poster")) else None)
            if not image:
                diagnostics["missingArtwork"].append(identity)
            art = dict(wiki_art)
            if image:
                art["uncentered"] = image
            if wiki_art.get("uncentered") and official_image:
                art["centered"] = wiki_art["uncentered"]
            if not wiki_art.get("loading") and safe_image(cn_data.get("card")):
                art["loading"] = cn_data["card"]
            if video:
                art["videoUncentered"] = video["url"]
            fallback = {}
            if safe_image(cn_data.get("poster")):
                fallback["uncentered"] = cn_data["poster"]
            if safe_image(cn_data.get("card")):
                fallback["loading"] = cn_data["card"]
            links = [{"label": "Wiki", "url": module["url"]}]
            if official:
                links.append({"label": "Wild Rift", "url": official["source"]})
            if cn:
                links.append({"label": "中文名称 / CN", "url": CN_SKINS})
            if wiki_art.get("uncentered"):
                links.append({"label": "Wiki 原画", "url": images[files["splash"]]["descriptionurl"]})
            records.append({
                "id": identity, "name": name, "nameZh": f"{cn['name']} {cn['heroName']}" if cn else name,
                "aliases": [official["name"]] if official else [], "champion": champion,
                "championZh": cn_data.get("heroName") or heroes.get(cn_hero_id, {}).get("name") or champion,
                "championId": data.get("id", f"wiki-{key(champion)}"), "championAlias": key(champion), "skinNumber": entry.get("id"),
                "wikiChampionId": data.get("id"), "wikiSkinId": entry.get("id"), "cnSkinId": cn_data.get("skinId") or None,
                "version": "upcoming" if future else (direct or {}).get("version", "unverified"),
                "plannedVersion": (direct or {}).get("version") if future else None,
                "status": "upcoming" if future else "released" if displayed else "listed", "releaseDate": displayed,
                "reportedReleaseDate": release if release != displayed else None,
                "patchEvidence": direct, "image": image,
                "imageFallback": cn_data["poster"] if official_image and safe_image(cn_data.get("poster")) else None,
                "art": art, "artFallback": fallback, "artPending": not image,
                "artSource": "Wild Rift official" if official_image else "League Wiki (Wild Rift)" if wiki_art.get("uncentered") else "Wild Rift CN official" if image else None,
                **skin_metadata(entry, cn, identity, files, images), "skinLineIds": line_ids,
                "sources": ["wiki"] + (["official"] if official else []) + (["tencent"] if cn else []), "sourceLinks": links,
            })
    for identity, official in official_names.items():
        if identity not in matched_official:
            diagnostics["unmatchedOfficialSkins"].append({"champion": official["champion"], "name": official["name"]})
    names = {}
    for skin in records:
        for name in [skin["name"], *skin["aliases"]]:
            normalized = key(name)
            if normalized in names and names[normalized] != skin["id"]:
                raise ValueError(f"Ambiguous official patch name: {name}")
            names[normalized] = skin["id"]
    by_id = {skin["id"]: skin for skin in records}
    for item in official_patches:
        page, url = item["page"], item["url"]
        version = official_patch_version(page["title"])
        for entry in official_patch_skins(page, names):
            later = sorted((v for v, value in patch_dates.items() if value and patch_key(v) > patch_key(version)), key=patch_key)
            next_date = patch_dates[later[0]] if later else None
            release = entry["releaseDate"] or by_id[entry["id"]]["releaseDate"]
            scope = entry.get("scope") or ("announcement" if release and next_date and release >= next_date else "release")
            candidate = {
                "version": version, "date": patch_dates.get(version), "announcementDate": announcements.get(version),
                "url": url, "title": page["title"], "kind": "official", "scope": scope,
                "section": entry["section"], "excerpt": entry["excerpt"], "listedReleaseDate": entry["releaseDate"],
            }
            if entry.get("firstRelease"):
                candidate["firstRelease"] = True
            candidates_by_id.setdefault(entry["id"], []).append(candidate)
    for skin in records:
        candidates = candidates_by_id.get(skin["id"], [])
        dated = [c for c in candidates if c.get("listedReleaseDate") and choose_patch([{**c, "scope": "release"}], c["listedReleaseDate"])]
        source = min(dated, key=lambda c: c["listedReleaseDate"]) if dated else None
        if source and (source.get("firstRelease") or not skin["releaseDate"] or source["listedReleaseDate"] < skin["releaseDate"] or choose_patch([{**source, "scope": "release"}], skin["releaseDate"])):
            if skin["releaseDate"] != source["listedReleaseDate"]:
                skin["reportedReleaseDate"] = skin["releaseDate"] or skin["reportedReleaseDate"]
            skin["releaseDate"], skin["releaseDateSource"] = source["listedReleaseDate"], source["url"]
            skin["status"] = "upcoming" if skin["releaseDate"] > today else "released"
        conflicts = []
        skin["patchEvidence"] = choose_patch(candidates, skin["releaseDate"], conflicts)
        for candidate in conflicts:
            diagnostics["patchDateConflicts"].append({
                "id": skin["id"], "version": candidate["version"], "releaseDate": skin["releaseDate"],
                "patchDate": candidate.get("date"), "announcementDate": candidate.get("announcementDate"), "url": candidate["url"],
            })
        skin["version"] = "upcoming" if skin["status"] == "upcoming" else (skin["patchEvidence"] or {}).get("version", "unverified")
        skin["plannedVersion"] = (skin["patchEvidence"] or {}).get("version") if skin["status"] == "upcoming" else None
    reported_dates = {entry["version"]: entry["reported"] for entry in diagnostics["patchDateDisagreements"]}
    timeline = patch_timeline([
        {"version": version, "dates": [patch_dates.get(version), announcements.get(version), reported_dates.get(version)]}
        for version in dict.fromkeys([*patch_dates, *announcements])
    ])
    official_sources = {official_patch_version(item["page"]["title"]): {"url": item["url"], "title": item["page"]["title"]} for item in official_patches}
    wiki_sources = {page["title"].replace("WR:V", ""): {"url": page["url"], "title": page["title"], "date": patch_date(page["content"])} for page in patches}
    inferred = []
    for skin in records:
        if skin["patchEvidence"] or skin["status"] != "released" or skin["regionAvailability"] == "cn-only" or skin["releaseDate"] < OPEN_BETA_DATE:
            continue
        reason = verification_reason(skin, candidates_by_id.get(skin["id"], []))
        patch = infer_patch(skin["releaseDate"], timeline) if reason != "date-conflict" else None
        if not patch:
            continue
        source = (wiki_sources if wiki_sources.get(patch["version"], {}).get("date") == patch["to"] else official_sources).get(patch["version"])
        if not source:
            continue
        skin["patchEvidence"] = {"version": patch["version"], "kind": "inferred", "url": source["url"], "title": source["title"], "patchDate": patch["to"]}
        skin["version"] = patch["version"]
        inferred.append({**{field: skin[field] for field in ("id", "name", "nameZh", "releaseDate", "version")}, "patchStart": patch["to"], "reason": reason})
    for skin in records:
        if skin["regionAvailability"] == "cn-only":
            skin["regionalCatalogDate"] = skin["releaseDate"]
            skin["releaseDate"] = None
            skin["catalogVersion"] = skin["plannedVersion"] or (skin["patchEvidence"] or {}).get("version")
            skin["plannedVersion"] = None
            skin["version"], skin["status"] = "regional", "regional"
        skin["verificationReason"] = verification_reason(skin, candidates_by_id.get(skin["id"], []))
    order = lambda value: {"upcoming": 3, "regional": 2, "unverified": 0}.get(value, 1)

    def compare(left, right):
        result = order(right["version"]) - order(left["version"])
        if not result:
            result = (patch_key(right["version"]) > patch_key(left["version"])) - (patch_key(right["version"]) < patch_key(left["version"]))
        if not result:
            result = (left["name"].casefold() > right["name"].casefold()) - (left["name"].casefold() < right["name"].casefold())
        return result

    records.sort(key=cmp_to_key(compare))
    counts = Counter(s["version"] for s in records if s["version"] not in ("upcoming", "regional", "unverified"))
    upcoming_count = sum(s["status"] == "upcoming" for s in records)
    payload = {
        "schemaVersion": 1, "game": "wild-rift", "region": "international",
        "dataUpdatedAt": reader.oldest_fetch if reader.cached else utc_now(),
        "totalSkins": sum(s["status"] not in ("upcoming", "regional") for s in records),
        "totalChampions": len({s["championId"] for s in records}),
        "verifiedSkins": sum(bool(s["patchEvidence"]) and s["patchEvidence"]["kind"] != "inferred" and s["status"] not in ("upcoming", "regional") for s in records),
        "inferredSkins": len(inferred), "unverifiedSkins": sum(s["version"] == "unverified" for s in records),
        "versions": [{"version": version, "count": counts[version], "releaseDate": patch_dates.get(version), "announcementDate": announcements.get(version)}
                     for version in sorted(counts, key=patch_key, reverse=True)],
        "upcoming": [{"version": "upcoming", "count": upcoming_count}] if upcoming_count else [],
        "regionalSkins": sum(s["status"] == "regional" for s in records),
        "skinLines": sorted(lines.values(), key=lambda line: line["name"].casefold()), "skins": records,
        "provenance": {"catalog": {"url": module["url"], "revision": module["revid"], "modifiedAt": module["timestamp"]},
                       "championIndex": OFFICIAL + "/en-us/champions/", "localization": CN_SKINS,
                       "cnFileTime": cn_skins["fileTime"], "patchPages": len(patches), "officialPatchPages": len(official_patches)},
        "diagnostics": diagnostics,
    }
    if previous and {**payload, "dataUpdatedAt": None} == {**previous, "dataUpdatedAt": None}:
        payload["dataUpdatedAt"] = previous["dataUpdatedAt"]
    assert_catalog(payload, previous)
    pending = [{
        **{field: skin[field] for field in ("id", "name", "nameZh", "releaseDate")},
        "reason": skin["verificationReason"], "candidates": candidates_by_id.get(skin["id"], []), "sourceLinks": skin["sourceLinks"],
    } for skin in records if skin["version"] == "unverified"]
    regional = [{
        **{field: skin[field] for field in ("id", "name", "nameZh", "distribution", "sourceLinks")},
        "catalogDate": skin.get("regionalCatalogDate"), "reason": skin["verificationReason"],
    } for skin in records if skin["status"] == "regional"]
    report = {"total": len(pending), "byReason": dict(sorted(Counter(s["reason"] for s in pending).items())),
              "skins": pending, "inferredTotal": len(inferred), "inferred": inferred, "regionalTotal": len(regional), "regional": regional}
    return payload, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached", action="store_true", help="Rebuild from saved responses without network requests")
    args = parser.parse_args()
    target = PROJECT_ROOT / "data/skins.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    payload, report = build_snapshot(SourceReader(cached=args.cached), previous)
    write_json(target, payload)
    write_json(PROJECT_ROOT / "data/verification_report.json", report)
    print(json.dumps({name: payload[name] for name in ("totalSkins", "totalChampions", "verifiedSkins", "inferredSkins", "unverifiedSkins")}, indent=2))


if __name__ == "__main__":
    main()
