"""Emitter tests. Payloads are validated against the backend's own schema, and
delivery is tested against the real FastAPI app (skipped if fastapi is missing)."""

import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests

from cv_engine.detector.types import FallEvent
from cv_engine.transport.emitter import TelemetryEmitter, event_id, fall_payload, heartbeat_payload

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
CAMERA_ID, ZONE_ID = "zone-1-cam-1", "Zone 1"

EVENT = FallEvent(
    track_id=3,
    timestamp=1791062047.412,  # 2026-10-03T21:14:07.412Z
    drop_started_at=1791062046.200,
    pose_confidence=0.8123,
    torso_angle_deg=82.44,
    bbox_aspect=1.4712,
    drop_velocity=0.9234,
    keypoint_conf=0.88,
    bbox=(10.0, 20.0, 300.0, 220.0),
)


def _backend_schemas():
    pytest.importorskip("fastapi")
    sys.path.insert(0, str(BACKEND_DIR))
    from app import schemas

    return schemas


def test_fall_payload_matches_plan_contract():
    p = fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=EVENT.timestamp + 0.04, snapshot_base_url="http://10.0.0.5:8001/")
    assert p["camera_id"] == CAMERA_ID
    assert p["timestamp"] == "2026-10-03T21:14:07.412Z"
    assert p["event_type"] == "fall"
    assert p["pose_confidence"] == 0.812
    m = p["metadata"]
    assert m["event_id"] == "zone-1-cam-1-3-1791062047412" == event_id(CAMERA_ID, EVENT)
    assert m["zone_id"] == ZONE_ID and m["track_id"] == 3
    assert m["latency_ms"] == 1252
    assert m["trigger"] == "auto"
    assert m["snapshot_url"] == "http://10.0.0.5:8001/snapshot/zone-1-cam-1-3-1791062047412.jpg"


def test_manual_event_is_labelled_manual():
    from dataclasses import replace

    p = fall_payload(replace(EVENT, manual=True), CAMERA_ID, ZONE_ID, sent_at=EVENT.timestamp)
    assert p["metadata"]["trigger"] == "manual"


def test_metadata_is_flat_and_has_no_nulls():
    for p in (
        fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=EVENT.timestamp),
        heartbeat_payload(CAMERA_ID, ZONE_ID, now=EVENT.timestamp, fps=28.37, people_detected=2),
    ):
        assert all(isinstance(v, (str, int, float, bool)) for v in p["metadata"].values())
    assert "snapshot_url" not in fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=EVENT.timestamp)["metadata"]


def test_payloads_validate_against_backend_schema():
    schemas = _backend_schemas()
    fall = schemas.TelemetryEvent(**fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=EVENT.timestamp))
    beat = schemas.TelemetryEvent(**heartbeat_payload(CAMERA_ID, ZONE_ID, EVENT.timestamp, 28.0, 1))
    assert fall.event_type == "fall" and beat.pose_confidence == 0.0


@pytest.fixture
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_backend(port: int):
    _backend_schemas()
    import uvicorn
    from app.main import active_incidents, app

    active_incidents.clear()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "backend did not start"
    return server, thread


def _wait_for(condition, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_send_does_not_block_when_backend_is_down(free_port):
    emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
    start = time.perf_counter()
    for _ in range(20):
        emitter.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
    assert time.perf_counter() - start < 0.05
    assert _wait_for(lambda: emitter.pending_falls == 20)


def test_fall_reaches_real_backend_and_becomes_incident(free_port):
    server, thread = _start_backend(free_port)
    base = f"http://127.0.0.1:{free_port}"
    try:
        emitter = TelemetryEmitter(base)
        emitter.send(heartbeat_payload(CAMERA_ID, ZONE_ID, time.time(), 28.0, 1))
        emitter.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
        assert _wait_for(lambda: emitter.delivered == 2)
        incidents = requests.get(f"{base}/api/v1/incidents", timeout=2).json()
        assert len(incidents) == 1  # heartbeat is not an incident
        assert incidents[0]["description"] == "Detected fall"
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_falls_queued_during_outage_are_delivered_on_recovery(free_port):
    emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
    emitter.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
    assert _wait_for(lambda: emitter.pending_falls == 1)

    server, thread = _start_backend(free_port)
    try:
        assert _wait_for(lambda: emitter.pending_falls == 0, timeout=10)
        incidents = requests.get(f"http://127.0.0.1:{free_port}/api/v1/incidents", timeout=2).json()
        assert len(incidents) == 1
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)
