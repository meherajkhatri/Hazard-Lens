"""Event logs for the AI Coach and reports: writing, reading, engine recording, summaries."""

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from cv_engine.eventlog import EventLog, read_events
from cv_engine.report import format_report, main, summarize

DAY1 = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc).timestamp()
DAY2 = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc).timestamp()


def test_one_file_per_camera_per_day_and_date_filters(tmp_path):
    cam1, cam2 = EventLog(tmp_path, "zone-1-cam-1", "Zone 1"), EventLog(tmp_path, "zone-1-cam-2", "Zone 1")
    cam1.write("fall", DAY1, track_id=1)
    cam2.write("fall", DAY1 + 5, track_id=2)
    cam1.write("fall", DAY2, track_id=3)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "zone-1-cam-1-2026-10-04.events.jsonl", "zone-1-cam-1-2026-10-05.events.jsonl",
        "zone-1-cam-2-2026-10-04.events.jsonl"]
    assert [e["track_id"] for e in read_events(tmp_path)] == [1, 2, 3]
    assert [e["track_id"] for e in read_events(tmp_path, since="2026-10-05")] == [3]
    assert [e["track_id"] for e in read_events(tmp_path, until="2026-10-04")] == [1, 2]


def test_damaged_lines_are_skipped(tmp_path):
    log = EventLog(tmp_path, "cam", "Zone 1")
    log.write("fall", DAY1, track_id=1)
    with log.path_for(DAY1).open("a") as f:
        f.write('{"event": "fall", "tru\n')
    assert len(read_events(tmp_path)) == 1


def test_every_line_is_standalone_json_with_camera_and_zone(tmp_path):
    EventLog(tmp_path, "zone-1-cam-1", "Zone 1").write("vision", DAY1, status="impaired", reason="glare")
    [line] = next(tmp_path.iterdir()).read_text().splitlines()
    assert json.loads(line) == {"event": "vision", "time": "2026-10-04T09:00:00.000Z", "camera_id": "zone-1-cam-1",
                                "zone_id": "Zone 1", "status": "impaired", "reason": "glare"}


def test_engine_records_fall_post_fall_and_vision(tmp_path):
    from cv_engine.tests.test_run import FPS, falling_person, make_engine

    engine, emitter, _, clock = make_engine(falling_person)
    engine.event_log = EventLog(tmp_path, engine.cfg.CAMERA_ID, engine.cfg.ZONE_ID)
    rng = np.random.default_rng(0)
    scene = np.dstack([np.kron(rng.integers(40, 220, (12, 16)), np.ones((40, 40)))] * 3).astype(np.uint8)
    for i in range(16 * FPS):
        clock["t"] = i / FPS
        frame = np.full_like(scene, 255) if 13 * FPS <= i < 15 * FPS else scene  # flashlight at 13-15s
        engine.process(frame, clock["t"])
    for i in range(16 * FPS, 19 * FPS):
        clock["t"] = i / FPS
        engine.process(scene, clock["t"])

    events = read_events(tmp_path)
    kinds = [e["event"] for e in events]
    assert kinds.count("fall") == 1 and kinds.count("post_fall") == 1
    fall = next(e for e in events if e["event"] == "fall")
    post = next(e for e in events if e["event"] == "post_fall")
    assert post["event_id"] == fall["event_id"] == next(p for p in emitter.sent if p["event_type"] == "fall")["event_id"]
    assert fall["detection"] == "seen_drop" and post["outcome"] == "unresponsive"
    vision = [(e["status"], e["reason"]) for e in events if e["event"] == "vision"]
    assert vision == [("impaired", "glare"), ("ok", None)]


def test_a_failing_disk_never_stops_detection(tmp_path, caplog):
    from cv_engine.tests.test_run import FPS, falling_person, make_engine

    class BrokenLog:
        def write(self, *args, **kwargs):
            raise OSError("disk full")

    engine, emitter, _, clock = make_engine(falling_person)
    engine.event_log = BrokenLog()
    for i in range(4 * FPS):
        clock["t"] = i / FPS
        engine.process(np.zeros((480, 640, 3), np.uint8), clock["t"])
    assert any(p["event_type"] == "fall" for p in emitter.sent)
    assert "could not write event log" in caplog.text


EVENTS = [
    {"event": "fall", "time": "2026-10-04T09:00:00.000Z", "camera_id": "zone-1-cam-1", "zone_id": "Zone 1",
     "event_id": "a", "detection": "seen_drop"},
    {"event": "post_fall", "time": "2026-10-04T09:00:11.000Z", "camera_id": "zone-1-cam-1", "zone_id": "Zone 1",
     "event_id": "a", "outcome": "unresponsive", "seconds_down": 10.0},
    {"event": "post_fall", "time": "2026-10-04T09:00:40.000Z", "camera_id": "zone-1-cam-1", "zone_id": "Zone 1",
     "event_id": "a", "outcome": "recovered", "seconds_down": 39.0},
    {"event": "fall", "time": "2026-10-04T14:10:00.000Z", "camera_id": "zone-1-cam-2", "zone_id": "Zone 1",
     "event_id": "b", "detection": "found_down"},
    {"event": "fall", "time": "2026-10-04T14:20:00.000Z", "camera_id": "corridor-cam-1",
     "zone_id": "Forklift Corridor", "event_id": "c", "detection": "unseen_drop"},
    {"event": "post_fall", "time": "2026-10-04T14:20:12.000Z", "camera_id": "corridor-cam-1",
     "zone_id": "Forklift Corridor", "event_id": "c", "outcome": "unresponsive", "seconds_down": 10.5},
    {"event": "vision", "time": "2026-10-04T10:00:00.000Z", "camera_id": "zone-1-cam-1", "zone_id": "Zone 1",
     "status": "impaired", "reason": "glare"},
    {"event": "vision", "time": "2026-10-04T10:00:30.000Z", "camera_id": "zone-1-cam-1", "zone_id": "Zone 1",
     "status": "ok", "reason": None},
    {"event": "camera", "time": "2026-10-04T11:00:00.000Z", "camera_id": "zone-1-cam-2", "zone_id": "Zone 1",
     "status": "lost"},
]


def test_summary_counts_falls_outcomes_vision_and_disconnects():
    s = summarize(sorted(EVENTS, key=lambda e: e["time"]))
    assert s["total_falls"] == 3
    assert s["zones"]["Zone 1"] == {"falls": 2, "by_detection": {"seen_drop": 1, "found_down": 1},
                                    "outcomes": {"recovered": 1, "no_follow_up": 1},
                                    "cameras": ["zone-1-cam-1", "zone-1-cam-2"]}
    assert [u["zone_id"] for u in s["unresponsive"]] == ["Forklift Corridor"]  # 'a' later recovered
    assert s["falls_by_hour"] == {"09:00": 1, "14:00": 2}
    assert s["vision_impaired"]["seconds_by_camera"] == {"zone-1-cam-1": 30.0}
    assert s["camera_disconnects"] == {"zone-1-cam-2": 1}
    text = format_report(s)
    assert "Falls: 3" in text and "Forklift Corridor" in text and "zone-1-cam-1:glare x1" in text


def test_report_command_text_and_json(tmp_path, capsys):
    for e in EVENTS:
        ts = datetime.fromisoformat(e["time"].replace("Z", "+00:00")).timestamp()
        fields = {k: v for k, v in e.items() if k not in ("event", "time", "camera_id", "zone_id")}
        EventLog(tmp_path, e["camera_id"], e["zone_id"]).write(e["event"], ts, **fields)
    main(["--log-dir", str(tmp_path)])
    assert "Falls: 3" in capsys.readouterr().out
    main(["--log-dir", str(tmp_path), "--json"])
    assert json.loads(capsys.readouterr().out)["total_falls"] == 3
    main(["--log-dir", str(tmp_path), "--since", "2026-10-05"])
    assert "No events logged yet." in capsys.readouterr().out
