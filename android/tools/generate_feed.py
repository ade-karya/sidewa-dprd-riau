#!/usr/bin/env python3
"""Generate `android/app/src/main/assets/feed.json` and `config.json` (camelCase keys for Gson)."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "android" / "app" / "src" / "main" / "assets"

config = {
    "supabase_url": "https://fbbczlzmtbpycbeatuly.supabase.co",
    "anon_key": json.loads((ASSETS / "config.json").read_text())["anon_key"],
    "app_name": "DewanKu",
}


def rpc(fn: str, body: dict) -> object:
    req = urllib.request.Request(
        config["supabase_url"] + "/rest/v1/rpc/" + fn,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "apikey": config["anon_key"],
            "authorization": "Bearer " + config["anon_key"],
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def convert(v: object) -> object:
    if isinstance(v, dict):
        return {camel(k): convert(x) for k, x in v.items()}
    if isinstance(v, list):
        return [convert(x) for x in v]
    return v


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    activities = rpc("android_activities", {})
    feed: dict[str, object] = {
        "stats": convert(rpc("android_stats", {})),
        "commissions": convert(rpc("android_commissions", {})),
        "activities": convert(activities),
        "activityDetails": [convert(rpc("android_activity", {"p_id": a["id"]})) for a in activities],
        "members": convert(rpc("android_members", {})),
    }
    members = rpc("android_members", {})
    feed["memberDetails"] = [convert(rpc("android_member", {"p_id": m["id"]})) for m in members]
    releases = rpc("android_press_releases", {})
    feed["pressReleases"] = convert(releases)
    feed["pressReleaseDetails"] = [convert(rpc("android_press_release", {"p_id": r["id"]})) for r in releases]
    feed["faces"] = convert(rpc("android_faces", {}))
    feed["generated_at"] = datetime.now(timezone.utc).isoformat()
    (ASSETS / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ASSETS / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {ASSETS/'feed.json'} ({(ASSETS/'feed.json').stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
