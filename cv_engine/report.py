"""Summarise the camera event logs for a shift report or the AI Safety Coach.

    python -m cv_engine.report                       # all days in cv_engine/logs
    python -m cv_engine.report --since 2026-10-04    # from a date (YYYY-MM-DD)
    python -m cv_engine.report --json                # machine-readable, e.g. for the Coach
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from cv_engine.config import EngineConfig
from cv_engine.eventlog import DEFAULT_LOG_DIR, read_events


def _ts(event: dict) -> datetime:
    return datetime.fromisoformat(event["time"].replace("Z", "+00:00"))


def summarize(events: list[dict]) -> dict:
    falls = [e for e in events if e["event"] == "fall"]
    outcomes = {e["event_id"]: e for e in events if e["event"] == "post_fall"}  # latest outcome wins

    zones: dict[str, dict] = defaultdict(lambda: {"falls": 0, "by_detection": Counter(), "outcomes": Counter(),
                                                  "cameras": set()})
    for fall in falls:
        z = zones[fall["zone_id"]]
        z["falls"] += 1
        z["by_detection"][fall.get("detection", "seen_drop")] += 1
        z["cameras"].add(fall["camera_id"])
        outcome = outcomes.get(fall.get("event_id"), {}).get("outcome")
        z["outcomes"][outcome or "no_follow_up"] += 1

    # Vision-impaired time per camera: pair each "impaired" with the next "ok".
    impaired_s: Counter = Counter()
    impaired_count: Counter = Counter()
    open_since: dict[str, datetime] = {}
    for e in events:
        if e["event"] != "vision":
            continue
        cam = e["camera_id"]
        if e["status"] == "impaired" and cam not in open_since:
            open_since[cam] = _ts(e)
            impaired_count[f"{cam}:{e.get('reason')}"] += 1
        elif e["status"] == "ok" and cam in open_since:
            impaired_s[cam] += (_ts(e) - open_since.pop(cam)).total_seconds()

    urgent = [{"time": f["time"], "zone_id": f["zone_id"], "camera_id": f["camera_id"],
               "seconds_down": outcomes[f["event_id"]].get("seconds_down")}
              for f in falls if outcomes.get(f.get("event_id"), {}).get("outcome") == "unresponsive"]

    return {
        "period": {"from": events[0]["time"], "to": events[-1]["time"]} if events else None,
        "total_falls": len(falls),
        "falls_by_hour": dict(sorted(Counter(_ts(f).strftime("%H:00") for f in falls).items())),
        "zones": {zone: {"falls": z["falls"], "by_detection": dict(z["by_detection"]),
                         "outcomes": dict(z["outcomes"]), "cameras": sorted(z["cameras"])}
                  for zone, z in sorted(zones.items())},
        "unresponsive": urgent,
        "vision_impaired": {"episodes": dict(impaired_count), "seconds_by_camera": dict(impaired_s),
                            "still_impaired": sorted(open_since)},
        "camera_disconnects": dict(Counter(e["camera_id"] for e in events
                                           if e["event"] == "camera" and e["status"] == "lost")),
    }


def format_report(s: dict) -> str:
    if not s["period"]:
        return "No events logged yet."
    lines = [f"Safety report {s['period']['from']} to {s['period']['to']}",
             f"Falls: {s['total_falls']}"]
    for zone, z in s["zones"].items():
        detection = ", ".join(f"{k} {v}" for k, v in z["by_detection"].items())
        outcomes = ", ".join(f"{k} {v}" for k, v in z["outcomes"].items())
        lines.append(f"  {zone}: {z['falls']} falls ({detection}); outcomes: {outcomes}; "
                     f"cameras: {', '.join(z['cameras'])}")
    if s["unresponsive"]:
        lines.append("Unresponsive after a fall (possible medical emergency):")
        lines += [f"  {u['time']}  {u['zone_id']}  {u['camera_id']}  down {u['seconds_down']}s"
                  for u in s["unresponsive"]]
    if s["falls_by_hour"]:
        lines.append("Falls by hour (UTC): " + ", ".join(f"{h} {n}" for h, n in s["falls_by_hour"].items()))
    v = s["vision_impaired"]
    if v["episodes"]:
        lines.append("Camera vision impaired: " + ", ".join(f"{k} x{n}" for k, n in v["episodes"].items()))
    if s["camera_disconnects"]:
        lines.append("Camera disconnects: " + ", ".join(f"{k} x{n}" for k, n in s["camera_disconnects"].items()))
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log-dir", type=Path, help="default: LOG_DIR or cv_engine/logs")
    parser.add_argument("--since", help="first day, YYYY-MM-DD")
    parser.add_argument("--until", help="last day, YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    cfg = EngineConfig()
    log_dir = args.log_dir or (Path(cfg.LOG_DIR) if cfg.LOG_DIR else DEFAULT_LOG_DIR)
    summary = summarize(read_events(log_dir, args.since, args.until))
    print(json.dumps(summary, indent=2) if args.json else format_report(summary))


if __name__ == "__main__":
    main()
