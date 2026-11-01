from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from wild_rift_skin_version.site_builder import build_site
from wild_rift_skin_version.sources import PROJECT_ROOT
from wild_rift_skin_version import workflow_policy


class SiteBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wild-rift-build-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        (self.root / "site").mkdir()
        (self.root / "site/index.html").write_text("<!doctype html><title>Test</title>", encoding="utf-8")
        for name in ("skins.json", "skin_spotlights.json"):
            shutil.copyfile(PROJECT_ROOT / "data" / name, self.root / "data" / name)

    def test_offline_build_attaches_videos_without_modifying_snapshot(self):
        before = (self.root / "data/skins.json").read_bytes()
        with redirect_stdout(io.StringIO()):
            built = build_site(self.root)
        self.assertEqual((self.root / "data/skins.json").read_bytes(), before)
        self.assertEqual((self.root / "dist/index.html").read_bytes(), (self.root / "site/index.html").read_bytes())
        saved = json.loads(before)
        delivered = json.loads((self.root / "dist/data/skins.json").read_text(encoding="utf-8"))
        self.assertEqual(built, delivered)
        self.assertEqual(built["dataUpdatedAt"], saved["dataUpdatedAt"])
        self.assertTrue(any(s.get("spotlight") for s in built["skins"]))

    def test_completion_timestamp_only_advances(self):
        for completed, expected in [
            ("2020-01-01T00:00:00Z", None),
            ("2099-01-01T00:00:00Z", "2099-01-01T00:00:00Z"),
        ]:
            with self.subTest(completed=completed), redirect_stdout(io.StringIO()):
                built = build_site(self.root, completed)
            saved = json.loads((self.root / "data/skins.json").read_text(encoding="utf-8"))
            self.assertEqual(built["dataUpdatedAt"], expected or saved["dataUpdatedAt"])
        with self.assertRaises(ValueError):
            build_site(self.root, "not-a-date")

    def test_manual_deployment_keeps_previous_sync_timestamp(self):
        output = self.root / "outputs"
        timestamp = "2026-10-31T22:01:50Z"
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch", "REFRESH_DATA": "false", "GITHUB_OUTPUT": str(output)}), \
             patch.object(workflow_policy, "latest_successful_sync", return_value=timestamp), \
             patch("sys.argv", ["workflow_policy"]), redirect_stdout(io.StringIO()):
            workflow_policy.main()
        self.assertEqual(output.read_text(encoding="utf-8").splitlines(), ["update=false", f"data_updated_at={timestamp}"])
