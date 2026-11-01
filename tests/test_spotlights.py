import unittest
from wild_rift_skin_version import spotlights as s


def video(number, title):
    return {"id": f"{number:011d}", "title": title}


class SpotlightTests(unittest.TestCase):
    def test_only_complete_wild_rift_titles_match(self):
        self.assertEqual(s.parse_title("Frostblade Irelia Wild Rift Skin Spotlight"), ("Frostblade Irelia", False))
        for title in ("Frostblade Irelia Skin Spotlight - League of Legends", "Irelia Skins Wild Rift", "Frostblade Irelia Wild Rift Skin Spotlight Comparison"):
            self.assertIsNone(s.parse_title(title))

    def test_newest_exact_video_does_not_leak_to_special_editions(self):
        skins = [{"name": name} for name in ("K/DA Kai’Sa", "K/DA Kai’Sa Special Edition", "No Video")]
        data = s.catalog([video(1, "K/DA Kai'Sa Wild Rift Skin Spotlight"), video(2, "K/DA Kai'Sa Wild Rift Skin Spotlight")])
        s.attach_spotlights(skins, data)
        self.assertEqual(skins[0]["spotlight"]["videoId"], "00000000001")
        self.assertNotIn("spotlight", skins[1])
        self.assertNotIn("spotlight", skins[2])

    def test_duplicate_names_channels_and_invalid_ids(self):
        skins = [{"name": "New Ahri"}, {"name": "New Ahri"}]
        s.attach_spotlights(skins, s.catalog([video(1, "New Ahri Wild Rift Skin Spotlight")]))
        self.assertTrue(all("spotlight" not in skin for skin in skins))
        with self.assertRaisesRegex(ValueError, "channel"):
            s.attach_spotlights(skins, {"channelId": "other", "videos": []})
        with self.assertRaisesRegex(ValueError, "video ID"):
            s.catalog([{"id": "https://example.com", "title": "New Ahri Wild Rift Skin Spotlight"}])

    def test_feed_merge_preserves_history_decodes_entities_and_is_idempotent(self):
        old = s.catalog([video(1, "Old Ahri Wild Rift Skin Spotlight")])
        xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
        <yt:channelId>{s.CHANNEL_ID}</yt:channelId><entry><yt:channelId>{s.CHANNEL_ID}</yt:channelId>
        <yt:videoId>00000000002</yt:videoId><title>New Nunu &amp; Willump Wild Rift Skin Spotlight</title></entry></feed>'''
        merged = s.merge_feed(old, xml)
        self.assertEqual(len(merged["videos"]), 2)
        self.assertEqual(merged["videos"][0]["title"], "New Nunu & Willump Wild Rift Skin Spotlight")
        self.assertEqual(s.merge_feed(merged, xml), merged)
        self.assertEqual(s.merge_feed(merged, xml.replace(f"<yt:channelId>{s.CHANNEL_ID}</yt:channelId>", f"<yt:channelId>{s.CHANNEL_ID[2:]}</yt:channelId>", 1)), merged)
        with self.assertRaisesRegex(ValueError, "channel"):
            s.merge_feed(old, xml.replace(s.CHANNEL_ID, "wrong-channel"))
        self.assertEqual(len(old["videos"]), 1)
