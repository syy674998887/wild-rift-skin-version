"""Read successful data-sync runs for Pages timestamps and update scheduling."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Callable
from urllib.request import Request, urlopen



def github_json(path: str) -> dict:
    request = Request(
        f"{os.environ['GITHUB_API_URL']}/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "wild-rift-skin-version",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def completed_sync_time(fetcher: Callable[[str], dict], run_id: int) -> str | None:
    payload = fetcher(f"actions/runs/{run_id}/jobs?filter=latest&per_page=100")
    for job in payload["jobs"]:
        for step in job.get("steps", []):
            if step["name"] == "Update skin data" and step["conclusion"] == "success":
                return step["completed_at"]
    return None


def latest_successful_sync(fetcher: Callable[[str], dict]) -> str | None:
    page = 1
    while True:
        payload = fetcher(
            "actions/workflows/pages.yml/runs"
            f"?branch=main&status=success&per_page=100&page={page}"
        )
        runs = payload["workflow_runs"]
        for run in runs:
            if (
                run["conclusion"] != "success"
                or run["event"] not in {"workflow_dispatch", "schedule"}
            ):
                continue
            completed_at = completed_sync_time(fetcher, run["id"])
            if completed_at:
                return completed_at
        if len(runs) < 100:
            return None
        page += 1


def update_policy(event: str, last_sync: str | None, now: datetime, refresh: bool = True) -> bool:
    if event == "workflow_dispatch":
        return refresh
    if event == "schedule":
        # Under 24 hours: a sync finishes after its own check, so a daily run
        # would otherwise land just short of 24 hours and skip every other day.
        return last_sync is None or (
            now - datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            >= timedelta(hours=20)
        )
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-sync", action="store_true")
    args = parser.parse_args()
    if args.current_sync:
        timestamp = completed_sync_time(github_json, int(os.environ["GITHUB_RUN_ID"]))
        if not timestamp:
            raise RuntimeError("the current run has no completed data-sync step")
        outputs = {"data_updated_at": timestamp}
    else:
        event = os.environ["GITHUB_EVENT_NAME"]
        refresh = os.environ.get("REFRESH_DATA") != "false"
        timestamp = (
            None if event == "workflow_dispatch" and refresh else latest_successful_sync(github_json)
        )
        update = update_policy(event, timestamp, datetime.now(timezone.utc), refresh)
        print(f"Last successful data sync: {timestamp or 'none'}; update={update}")
        outputs = {
            "update": str(update).lower(),
            "data_updated_at": timestamp or "",
        }
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name, value in outputs.items():
            print(f"{name}={value}", file=output)


if __name__ == "__main__":
    main()
