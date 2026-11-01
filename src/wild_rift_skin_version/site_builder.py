"""Build the static site from the saved Wild Rift snapshot."""
from datetime import datetime
import json
import os
import shutil

from .sources import PROJECT_ROOT, assert_catalog
from .spotlights import attach_spotlights, load_catalog
from .updater import _write_bytes_atomic


def build_site(root=PROJECT_ROOT, completed_sync=None):
    data = json.loads((root / "data/skins.json").read_text(encoding="utf-8"))
    assert_catalog(data)
    attach_spotlights(data["skins"], load_catalog(root / "data/skin_spotlights.json"))
    if completed_sync:
        completed = datetime.fromisoformat(completed_sync.replace("Z", "+00:00"))
        saved = data.get("dataUpdatedAt")
        if not saved or completed > datetime.fromisoformat(saved.replace("Z", "+00:00")):
            data["dataUpdatedAt"] = completed_sync
    output = root / "dist"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "site", output, dirs_exist_ok=True)
    _write_bytes_atomic(output / "data/skins.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print(f"Built dist/: {data['totalSkins']} skins, {len(data['versions'])} patch groups.")
    return data


def main():
    build_site(completed_sync=os.environ.get("WR_DATA_UPDATED_AT"))


if __name__ == "__main__":
    main()
