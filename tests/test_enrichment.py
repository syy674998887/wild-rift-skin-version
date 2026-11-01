from datetime import datetime, timezone
import json
import unittest

from wild_rift_skin_version.metadata import skin_metadata, wiki_files
from wild_rift_skin_version.patches import (
    choose_patch, consistent_patch_date, infer_patch, official_patch_skins,
    official_patch_version, patch_timeline, written_date,
)
from wild_rift_skin_version.sources import PROJECT_ROOT, key
from wild_rift_skin_version.workflow_policy import (
    completed_sync_time, latest_successful_sync, update_policy,
)


def page(body, published="2022-06-07"):
    return {"displayedPublishDate": published, "blades": [{"richText": {"body": body}}]}


def names(*labels):
    return {key(label): label for label in labels}


def snapshot():
    return json.loads((PROJECT_ROOT / "data/skins.json").read_text(encoding="utf-8"))


class EnrichmentTests(unittest.TestCase):
    def test_exact_release_labels_exclude_incidental_returning_and_chroma(self):
        source = page(
            "<h2>CHANGES</h2><p>AstroNautilus fixed.</p>"
            "<h2>SKINS</h2><table><tr><td><p>AstroNautilus</p><p>Releasing June 21 @ 00:01 UTC</p></td></tr></table>"
            "<ul><li>Cosmic Queen Ashe</li><li>Arcade Ahri chroma</li></ul>"
            "<h3>Returning skins</h3><ul><li>Arcane Jinx</li></ul>"
            "<h2>ACCESSORIES</h2><ul><li>Queen Ashe</li></ul>"
        )
        self.assertEqual(official_patch_skins(source, names("AstroNautilus", "Queen Ashe", "Arcade Ahri", "Arcane Jinx")), [
            {"id": "AstroNautilus", "releaseDate": "2022-06-21", "section": "SKINS", "excerpt": "AstroNautilus"},
        ])

    def test_invalid_early_date_does_not_discard_direct_evidence(self):
        evidence = {"version": "3.2b", "date": "2022-06-07", "url": "https://example.test/release"}
        self.assertEqual(choose_patch([evidence], "2012-09-04"), evidence)
        self.assertIsNone(choose_patch([evidence], "2020-10-07"))
        self.assertIsNone(choose_patch([], "2022-06-21"))
        self.assertIsNone(choose_patch([{**evidence, "scope": "announcement"}], "2022-06-21"))
        self.assertEqual(written_date("Released June 21, 2022 (00:01 UTC)"), "2022-06-21")

    def test_patch_title_variants_exclude_previews(self):
        for title, expected in [
            ("Wild Rift Patch 5.1d", "5.1d"), ("Wild Rift patch Notes 5.2a", "5.2a"),
            ("Wild Rift Patch Notes 6.2b - Main & Adventure Modes", "6.2b"),
            ("Wild Rift Patch Preview 7.3", None),
        ]:
            with self.subTest(title=title):
                self.assertEqual(official_patch_version(title), expected)

    def test_chromas_keep_names_and_source_images_under_local_ids(self):
        files = wiki_files("Ahri", "Arcade", {"Pink": {}})
        images = {files["chromas"]["Pink"]: {
            "url": "https://wiki.leagueoflegends.com/en-us/images/Ahri_Arcade_%28Pink%29_WR.png?v1",
            "descriptionurl": "https://wiki.leagueoflegends.com/en-us/File:Ahri_Arcade_(Pink)_WR.png",
        }}
        meta = skin_metadata({"availability": "Legacy", "chromas": {"Pink": {}}},
                             {"quality": "SKIN_QUALITY_EPIC"}, "wr:10038:4", files, images)
        self.assertEqual(meta["chromas"][0]["id"], "wr:10038:4:chroma:pink")
        self.assertEqual(meta["chromas"][0]["nameZh"], "粉色")
        self.assertTrue(meta["chromas"][0]["image"])
        self.assertTrue(meta["legacy"])
        self.assertEqual(meta["rarityRegion"], "cn")
        self.assertEqual(skin_metadata({"availability": "Rare"}, None, "wr:1:1", wiki_files("A", "B"), {})["chromaCoverage"], "not-documented")

    def test_two_tone_chromas_keep_source_filename_and_color_labels(self):
        files = wiki_files("Rammus", "Sweeper", {"White/Light Blue": {}, "Weapon Augment": {}})
        self.assertEqual(files["chromas"]["White/Light Blue"], "File:Rammus Sweeper (WhiteLight Blue) WR.png")
        two_tone, named = skin_metadata({"chromas": {"White/Light Blue": {}, "Weapon Augment": {}}}, None, "wr:10034:1", files, {})["chromas"]
        self.assertEqual(two_tone["nameZh"], "白色/浅蓝")
        self.assertEqual(len(two_tone["colors"]), 2)
        self.assertEqual(named["nameZh"], "Weapon Augment")
        self.assertEqual(named["colors"], [])

    def test_china_exclusives_never_become_confirmed_global_releases(self):
        def metadata(distribution):
            return skin_metadata({"distribution": distribution}, None, "wr:10079:16", wiki_files("Ashe", "Elf Forest"), {})
        self.assertEqual(metadata("Unknown (China Exclusive)")["regionAvailability"], "cn-only")
        self.assertEqual(metadata("China version and Global version")["regionAvailability"], "unspecified")
        data = snapshot()
        regional = [s for s in data["skins"] if s["status"] == "regional"]
        self.assertEqual(data["regionalSkins"], len(regional))
        for skin in data["skins"]:
            if skin["regionAvailability"] == "cn-only":
                self.assertEqual(skin["status"], "regional")
        for skin in regional:
            self.assertEqual(skin["version"], "regional")
            self.assertIsNone(skin["releaseDate"])
            self.assertEqual(skin["regionAvailability"], "cn-only")
            self.assertEqual(skin["verificationReason"], "region-unconfirmed")
        self.assertEqual(data["totalSkins"] + sum(g["count"] for g in data["upcoming"]) + len(regional), len(data["skins"]))

    def test_update_policy_respects_twenty_hours_and_manual_opt_out(self):
        now = datetime(2026, 9, 27, 12, 34, tzinfo=timezone.utc)
        self.assertFalse(update_policy("push", None, now))
        self.assertTrue(update_policy("schedule", None, now))
        self.assertFalse(update_policy("schedule", "2026-09-26T17:00:00Z", now))
        self.assertTrue(update_policy("schedule", "2026-09-26T16:34:00Z", now))
        self.assertTrue(update_policy("workflow_dispatch", "2026-09-27T12:00:00Z", now))
        self.assertFalse(update_policy("workflow_dispatch", None, now, False))

    def test_history_uses_successful_sync_completion(self):
        timestamp = "2026-09-26T12:40:00Z"
        def fetcher(route):
            if "workflows/" in route:
                return {"workflow_runs": [
                    {"id": 3, "event": "push", "conclusion": "success"},
                    {"id": 2, "event": "schedule", "conclusion": "success"},
                    {"id": 1, "event": "schedule", "conclusion": "success"},
                ]}
            return {"jobs": [{"steps": [{"name": "Update skin data", "conclusion": "success" if "/1/" in route else "skipped", "completed_at": timestamp}]}]}
        self.assertEqual(latest_successful_sync(fetcher), timestamp)
        self.assertIsNone(completed_sync_time(fetcher, 2))

    def test_delivered_enrichment_and_reports_remain_consistent(self):
        data = snapshot()
        report = json.loads((PROJECT_ROOT / "data/verification_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["total"], data["unverifiedSkins"])
        self.assertEqual(report["total"], sum(report["byReason"].values()))
        self.assertEqual(report["inferredTotal"], data["inferredSkins"])
        by_id = {s["id"]: s for s in data["skins"]}
        by_name = {s["name"]: s for s in data["skins"]}
        for entry in report["inferred"]:
            self.assertEqual(by_id[entry["id"]]["patchEvidence"]["kind"], "inferred")
        for skin in data["skins"]:
            if skin["rarity"]:
                self.assertEqual(skin["rarityRegion"], "cn")
            if skin["version"] == "unverified":
                self.assertTrue(any(s["id"] == skin["id"] and s["reason"] == skin["verificationReason"] for s in report["skins"]))
            ids = [c["id"] for c in skin["chromas"]]
            self.assertEqual(len(ids), len(set(ids)))
            if skin["availability"] == "Upcoming" and not skin["releaseDate"] and skin["regionAvailability"] != "cn-only":
                self.assertEqual(skin["status"], "upcoming")
        self.assertEqual((by_id["wr:10132:1"]["releaseDate"], by_id["wr:10132:1"]["version"]), ("2022-06-21", "3.2b"))
        self.assertEqual(by_name["Reindeer Smolder"]["releaseDate"], "2026-12-03")
        self.assertEqual((by_name["Glorious Armada Twisted Fate"]["releaseDate"], by_name["Glorious Armada Twisted Fate"]["version"]), ("2023-04-20", "4.1b"))
        self.assertEqual(by_name["Choo-Choo Ornn"]["releaseDate"], "2026-06-06")
        for name in ("Corporate Mundo", "Arcane Jinx"):
            self.assertNotEqual(by_name[name]["version"], "2.6")
        for name in ("Arcane Jinx", "Crystal Rose Ashe", "Supervillain Jinx Fracture", "Neon Daredevil Master Yi: Velocity"):
            self.assertIn(by_name[name]["patchEvidence"]["kind"], ("wiki", "official"))

    def test_release_lists_roll_over_year_and_exclude_returning_siblings(self):
        source = page(
            "<h2>SKINS</h2><p>Releasing December 22 @ 00:01 UTC:</p><ul><li>Winter Lulu</li></ul>"
            "<p>Releasing January 6 @ 00:01 UTC:</p><ul><li>Steel Legion Lux</li></ul>"
            "<h3>Returning skins</h3><p>Releasing January 6:</p><ul><li>Arcane Jinx</li></ul><h2>CHANGES</h2><li>Unrelated Skin</li>",
            "2021-12-17",
        )
        entries = official_patch_skins(source, names("Winter Lulu", "Steel Legion Lux", "Arcane Jinx", "Unrelated Skin"))
        self.assertEqual([(e["id"], e["releaseDate"]) for e in entries], [("Winter Lulu", "2021-12-22"), ("Steel Legion Lux", "2022-01-06")])

    def test_pass_announcements_are_not_release_patch_evidence(self):
        source = page(
            "<h2>Wild Pass</h2><h4>Reindeer Mini Pass</h4><ul><li>Once the Pencil Sharpener Wild Pass wraps up, the Reindeer Mini Pass arrives on December 3, featuring the all-new Reindeer Smolder and Reindeer Smolder (Pink).</li>"
            "<li>Returning on December 3, featuring the new Old Skin.</li></ul>",
            "2026-09-21",
        )
        entries = official_patch_skins(source, names("Reindeer Smolder", "Old Skin", "Smolder"))
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]["id"], entries[0]["releaseDate"], entries[0]["scope"]), ("Reindeer Smolder", "2026-12-03", "announcement"))
        self.assertIsNone(choose_patch([{**e, "version": "7.3"} for e in entries], "2026-12-03"))

    def test_table_dates_do_not_spill_into_other_cells(self):
        source = page("<h2>Skins</h2><table><td>Alpha Skin<p>Releasing June 21</p></td><td><p>Beta Skin</p></td>"
                      "<td><p>Gamma Skin Releasing June 22</p></td><td>Prestige Alpha Skin</td></table>")
        entries = official_patch_skins(source, names("Alpha Skin", "Beta Skin", "Gamma Skin"))
        self.assertEqual([(e["id"], e["releaseDate"]) for e in entries], [("Alpha Skin", "2022-06-21"), ("Beta Skin", None), ("Gamma Skin", "2022-06-22")])

    def test_overlapping_dates_stay_unresolved_and_backwards_dates_are_ignored(self):
        timeline = patch_timeline([
            {"version": "1.1", "dates": ["2021-01-01"]},
            {"version": "1.2", "dates": ["2021-02-01", "2021-02-03"]},
            {"version": "1.3", "dates": ["2020-01-01", "2021-03-01"]},
        ])
        for value, expected in [("2020-12-31", None), ("2021-01-31", "1.1"), ("2021-02-01", None),
                                ("2021-02-02", None), ("2021-02-03", "1.2"), ("2021-03-01", "1.3")]:
            inferred = infer_patch(value, timeline)
            self.assertEqual(inferred["version"] if inferred else None, expected)
        self.assertIsNone(consistent_patch_date("2025-03-18", "2026-03-18"))
        self.assertEqual(consistent_patch_date("2026-03-18", None), "2026-03-18")

    def test_ranked_reward_dates_stay_within_season(self):
        source = page(
            "<h2>RANKED SEASON 9</h2><p>New Ranked skin! Glorious Armada Twisted Fate will be your award.</p>"
            "<p>Glorious Jinx will be returning to the Ranked Store.</p><p>Ranked Season 9 will begin on April 19 7:00 PM PST.</p>"
            "<h3>LEGENDARY QUEUE</h3><p>The queue will begin on April 24 at 00:01 UTC.</p>"
            "<h2>NEW SEASON</h2><p>Earn this season’s ranked skin, Glorious Aigrette Nilah. The season will begin on October 24, 2025, at 08:00 (CST).</p>",
            "2023-04-19",
        )
        entries = official_patch_skins(source, names("Glorious Armada Twisted Fate", "Glorious Jinx", "Glorious Aigrette Nilah"))
        self.assertEqual([(e["id"], e["releaseDate"], e["firstRelease"]) for e in entries],
                         [("Glorious Armada Twisted Fate", "2023-04-20", True), ("Glorious Aigrette Nilah", "2025-10-24", True)])

    def test_event_special_editions_match_complete_names_without_leaking_dates(self):
        source = page(
            "<h2>EVENTS</h2><h3>AURORA’S RUNETERRA ADVENTURE</h3>"
            "<p>Earn a special skin for free, Star Guardian Jinx: Exquisite Edition.</p><p>The adventure will begin on July 24 at 00:01 UTC.</p>"
            "<h3>Another event</h3><p>Earn a special skin for free, Other Skin.</p>"
            "<h3>Return event</h3><p>Earn a special skin returning for free, Old Skin.</p><p>The event begins on July 30.</p>",
            "2025-07-16",
        )
        entries = official_patch_skins(source, names("Star Guardian Jinx", "Star Guardian Jinx Exquisite Edition", "Other Skin", "Old Skin"))
        self.assertEqual([(e["id"], e["releaseDate"], e["scope"]) for e in entries],
                         [("Star Guardian Jinx Exquisite Edition", "2025-07-24", "announcement")])

    def test_pass_prose_keeps_new_variants_and_announcement_scope(self):
        source = page(
            "<h2>NEW WILD PASS</h2><p>The Mini Pass will launch on June 6, 2026 at 00:00 (UTC+0), featuring the new skin Choo-Choo Ornn and its chroma Choo-Choo Ornn (Yellow).</p>"
            "<p>Starting on October 23, 2026, earn Wondertown Vex and Ascended Wondertown Vex.</p>"
            "<p>Comeback skins: Old Skin, starting on October 23.</p>",
            "2026-04-07",
        )
        entries = official_patch_skins(source, names("Choo-Choo Ornn", "Wondertown Vex", "Ascended Wondertown Vex", "Old Skin"))
        self.assertEqual([(e["id"], e["releaseDate"]) for e in entries],
                         [("Choo-Choo Ornn", "2026-06-06"), ("Wondertown Vex", "2026-10-23"), ("Ascended Wondertown Vex", "2026-10-23")])
        self.assertTrue(all(e["scope"] == "announcement" for e in entries))
