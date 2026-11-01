import json
import unittest
from urllib.parse import urlparse

from wild_rift_skin_version.sources import (
    PROJECT_ROOT, assert_catalog, chinese_hero_ids, chinese_index, iso_date,
    next_page, official_skins, parse_lua, patch_date, patch_key, patch_skins,
)


def fixture():
    return {"game": "wild-rift", "region": "international", "skins": [{
        "id": "wr:10038:3", "name": "Foxfire Ahri", "nameZh": "焰尾妖狐 阿狸",
        "champion": "Ahri", "version": "unverified", "releaseDate": "2020-10-07", "image": None,
    }]}


def snapshot():
    return json.loads((PROJECT_ROOT / "data/skins.json").read_text(encoding="utf-8"))


class SourceTests(unittest.TestCase):
    def test_lua_is_parsed_without_execution(self):
        data = parse_lua('-- ignored {\nreturn {["Ahri"]={["skins"]={["Foxfire"]={["id"]=3,["set"]={"Infernal"},["lore"]="text } \\"quote\\"",["newvoice"]=false,["newvoice"]=true}}}} -- end')
        self.assertEqual(data["Ahri"]["skins"]["Foxfire"]["id"], 3)
        self.assertEqual(data["Ahri"]["skins"]["Foxfire"]["lore"], 'text } "quote"')
        self.assertTrue(data["Ahri"]["skins"]["Foxfire"]["newvoice"])
        for source in ('return os.execute("bad")', "return {} another()", "return {", 'return {["x"]="unfinished'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_lua(source)

    def test_only_new_cosmetics_link_patches(self):
        text = "== New Cosmetics ==\nThe following skins have been added:\n* {{WRskin|Ahri|Foxfire}} (990)\n* {{WRskin|Ahri|Original}}\n=== Returning skins ===\n* {{WRskin|Ahri|Arcade}}\n== Changes ==\n* {{WRskin|Ahri|Popstar}}"
        self.assertEqual(patch_skins(text), [{"champion": "Ahri", "skin": "Foxfire"}])
        self.assertEqual(patch_skins("== Bug fixes ==\n* {{WRskin|Ahri|Foxfire}}"), [])

    def test_strict_dates(self):
        cases = {
            "|Release = December {{NumberSup|17}}, 2021": "2021-12-17",
            "|Release = Dec {{NumberSup|27}}, 2023": "2023-12-27",
            "|Release = Decembuary 27, 2023": None, "|Release = Feb 30, 2023": None,
            "|Publish = 2026-09-21": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(patch_date(text), expected)
        self.assertIsNone(iso_date("2026-02-30"))
        self.assertIsNone(iso_date("N/A"))
        self.assertEqual(iso_date("2024-02-29"), "2024-02-29")

    def test_returning_markers_do_not_hide_new_siblings(self):
        text = """== New Cosmetics ==
* {{sbc|Editor's Note:}} Arcane Jinx and Vi are released in this patch.
* {{WRskin|Jinx|Arcane}}
* {{WRskin|Vi|Arcane}}
''Released August 8, 2024:''
* {{WRskin|Lux|Crystal Rose}} (Event, Re-release)
* {{WRskin|Ashe|Crystal Rose}} (Event)
* {{WRskin|Viego|Crystal Rose}} (Event)
== Changes =="""
        self.assertEqual(patch_skins(text), [{"champion": c, "skin": s} for c, s in
                                           [("Jinx", "Arcane"), ("Vi", "Arcane"), ("Ashe", "Crystal Rose"), ("Viego", "Crystal Rose")]])

    def test_nested_forms_and_returning_families(self):
        text = """== New Cosmetics ==
* {{WRskin|Jinx|Supervillain Fantasy}}
** {{WRskin|Jinx|Supervillain Fracture}}
** {{WRskin|Jinx|Supervillain Doombringer}}
* Returning skins:
** {{WRskin|Ahri|Arcade}}
*** {{WRskin|Ahri|Arcade Special}}
* {{WRskin|Riven|Arcade}} Chromas
* {{WRskin|Ashe|High Noon Mythic Chroma}}
=== Returning skins ===
* {{WRskin|Jhin|Supervillain}}
=== New skins ===
* {{WRskin|Viego|Crystal Rose}}
== Changes =="""
        self.assertEqual([s["skin"] for s in patch_skins(text)], [
            "Supervillain Fantasy", "Supervillain Fracture", "Supervillain Doombringer", "High Noon Mythic Chroma", "Crystal Rose",
        ])

    def test_chinese_ids_use_owned_poster_numbers(self):
        heroes = {"10038": {"name": "阿狸", "poster": "https://game.gtimg.cn/Ahri_0.jpg"},
                  "10099": {"name": "拉克丝", "poster": "https://game.gtimg.cn/Lux_0.jpg"}}
        skins = {"one": {"heroId": "10038", "skinId": "1003804", "name": "焰尾妖狐", "poster": "https://game.gtimg.cn/Ahri_3.jpg"},
                 "bad": {"heroId": "10038", "skinId": "000", "name": "Wrong", "poster": "https://game.gtimg.cn/Lux_3.jpg"}}
        self.assertEqual(chinese_index(heroes, skins)["10038:3"]["skinId"], "1003804")
        self.assertEqual(len(chinese_index(heroes, skins)), 1)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            chinese_index(heroes, {**skins, "two": skins["one"]})

    def test_chinese_prefixes_conflicts_and_unclaimed_hero_fallback(self):
        heroes = {"10056": {"name": "嘉文四世", "poster": "https://game.gtimg.cn/JarvanIV_0.jpg"},
                  "10146": {"name": "塔莉垭", "poster": "https://game.gtimg.cn/Taliyah_0.jpg"}}
        skins = {"a": {"heroId": "10056", "skinId": "1005606", "name": "海克斯科技", "poster": "https://game.gtimg.cn/Jarvan_5.jpg"},
                 "b": {"heroId": "10146", "skinId": "1014603", "name": "HeroTitle_1014603", "poster": "https://game.gtimg.cn/Taliyah_2.jpg"}}
        self.assertEqual(chinese_index(heroes, skins)["10056:5"]["skinId"], "1005606")
        self.assertEqual(len(chinese_index(heroes, skins)), 1)
        conflicting = {**skins, "c": {"heroId": "10146", "skinId": "x", "name": "Conflict", "poster": "https://game.gtimg.cn/Jarvan_6.jpg"}}
        self.assertEqual(chinese_index(heroes, conflicting), {})
        self.assertEqual(chinese_hero_ids({"Jarvan IV": {"id": 10056}, "Taliyah": {"id": 101460}, "Missing": {}}, heroes),
                         {"Jarvan IV": "10056", "Taliyah": "10146", "Missing": None})
        self.assertIsNone(chinese_hero_ids({"Taliyah": {"id": 101460}, "Other": {"id": 10146}}, heroes)["Taliyah"])

    def test_official_catalog_excludes_base_and_rejects_bad_hosts(self):
        def group(label, url):
            return {"label": label, "content": {"media": {"url": url}}}
        page = {"url": "https://wildrift.leagueoflegends.com/en-us/champions/ahri/", "blades": [{
            "type": "landingMediaCarousel", "groups": [group("AHRI", "https://cmsassets.rgpub.io/base.jpg"), group("FOXFIRE AHRI", "https://cmsassets.rgpub.io/foxfire.jpg")],
        }]}
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"page": page}}}) + "</script>"
        self.assertEqual(len(official_skins(next_page(html))), 1)
        page["blades"][0]["groups"][1]["content"]["media"]["url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "Invalid official skin"):
            official_skins(page)
        with self.assertRaisesRegex(ValueError, "missing"):
            next_page("<h1>blocked</h1>")

    def test_patch_sorting(self):
        self.assertEqual(sorted(["7.0", "2.6a", "7.1g", "7.1", "6.2k", "7.10"], key=patch_key), ["2.6a", "6.2k", "7.0", "7.1", "7.1g", "7.10"])

    def test_dated_skin_still_requires_evidence(self):
        data = fixture()
        assert_catalog(data)
        data["skins"][0]["version"] = "1.0"
        with self.assertRaisesRegex(ValueError, "Patch without evidence"):
            assert_catalog(data)
        data["skins"][0]["patchEvidence"] = {"url": "https://wiki.leagueoflegends.com/en-us/WR:V1.0"}
        assert_catalog(data)

    def test_identity_changes_and_upstream_evidence_corrections(self):
        previous = fixture()
        previous["skins"].append({**previous["skins"][0], "id": "wr:10038:4", "name": "Arcade Ahri"})
        with self.assertRaisesRegex(ValueError, "Refusing to remove"):
            assert_catalog(fixture(), previous)
        old = fixture()
        old["skins"][0]["patchEvidence"] = {"kind": "wiki", "url": "https://wiki.leagueoflegends.com/en-us/WR:V1.0"}
        assert_catalog(fixture(), old)
        renamed = fixture()
        renamed["skins"][0]["id"] = "wr:10038:30"
        assert_catalog(renamed, old)
        renamed["skins"][0]["name"] = "Foxfire Ahri Renamed"
        with self.assertRaisesRegex(ValueError, "Refusing to remove"):
            assert_catalog(renamed, old)
        renamed["skins"][0]["aliases"] = [old["skins"][0]["name"]]
        assert_catalog(renamed, old)

    def test_upcoming_can_change_but_other_history_stays_protected(self):
        previous = fixture()
        previous["skins"].append({"id": "wr:wiki:ahri:preview", "name": "Preview Ahri", "nameZh": "Preview Ahri",
                                  "champion": "Ahri", "status": "upcoming", "version": "upcoming", "image": None})
        assert_catalog(fixture(), previous)
        renamed = fixture()
        renamed["skins"].append({**previous["skins"][1], "id": "wr:10038:20", "name": "Final Ahri", "nameZh": "Final Ahri", "status": "released", "version": "unverified"})
        assert_catalog(renamed, previous)
        for status in ("released", "listed", "regional"):
            previous["skins"][1]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "Refusing to remove"):
                assert_catalog(renamed, previous)

    def test_snapshot_identities_provenance_and_counts(self):
        payload = snapshot()
        assert_catalog(payload)
        self.assertEqual(payload["totalSkins"], sum(s["status"] not in ("upcoming", "regional") for s in payload["skins"]))
        self.assertEqual(payload["verifiedSkins"] + payload["inferredSkins"] + payload["unverifiedSkins"], payload["totalSkins"])
        for patch in payload["versions"]:
            self.assertEqual(patch["count"], sum(s["version"] == patch["version"] for s in payload["skins"]))
        versions = {v["version"]: v for v in payload["versions"]}
        for skin in payload["skins"]:
            evidence = skin.get("patchEvidence") or {}
            if evidence.get("kind") == "inferred":
                self.assertEqual(skin["version"], evidence["version"])
                self.assertLessEqual(evidence["patchDate"], skin["releaseDate"])
                version = versions[skin["version"]]
                stated = ([version["releaseDate"]] + [d["reported"] for d in payload["diagnostics"]["patchDateDisagreements"] if d["version"] == skin["version"]]
                          if "wiki.leagueoflegends.com" in evidence["url"] else [version["announcementDate"]])
                self.assertIn(evidence["patchDate"], stated, skin["name"])
            self.assertNotEqual(skin["wikiSkinId"], 0)
            self.assertTrue(not skin["releaseDate"] or skin["releaseDate"] >= "2020-01-01")
            self.assertTrue(skin["sourceLinks"])
            self.assertTrue(all(urlparse(s["url"]).hostname in ("wiki.leagueoflegends.com", "wildrift.leagueoflegends.com", "game.gtimg.cn") for s in skin["sourceLinks"]))

    def test_snapshot_chinese_joins_and_independent_variant_art(self):
        skins = snapshot()["skins"]
        by_name = {s["name"]: s for s in skins}
        for name, identity in [("Pool Party Taliyah", "1014602"), ("Hextech Jarvan IV", "1005606"), ("Pool Party Mundo", "1006202")]:
            self.assertEqual(by_name[name]["cnSkinId"], identity)
        self.assertEqual(by_name["HEARTSTEEL K'Sante"]["championZh"], "奎桑提")
        ids = [s["cnSkinId"] for s in skins if s["cnSkinId"]]
        self.assertEqual(len(ids), len(set(ids)))
        image = by_name["Warring Kingdoms Jarvan IV Mythic Chroma"]["image"]
        self.assertRegex(image, r"WarringKingdomsMythicChromaSkin_WR\.jpg")
        self.assertNotEqual(image, by_name["Warring Kingdoms Jarvan IV"]["image"])
        self.assertFalse(any("HeroTitle_" in s["nameZh"] for s in skins))
