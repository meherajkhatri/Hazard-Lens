"""Emitter tests. Payloads are validated against the backend's own schema, and
delivery is tested against the real FastAPI app (skipped if fastapi is missing)."""

import socket
import sys
import threading
import time
from pathlib import Path

from uuid import UUID

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


def test_fall_payload_matches_backend_contract():
    p = fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=EVENT.timestamp + 0.04, snapshot_base_url="http://10.0.0.5:8001/")
    eid = event_id(CAMERA_ID, EVENT)
    assert str(UUID(eid)) == eid == p["event_id"]
    assert p["camera_id"] == CAMERA_ID and p["zone_id"] == ZONE_ID
    assert p["timestamp"] == "2026-10-03T21:14:07.412Z"
    assert p["event_type"] == "fall"
    assert p["pose_confidence"] == 0.812
    m = p["metadata"]
    assert m["track_id"] == 3
    assert m["latency_ms"] == 1252
    assert m["trigger"] == "auto"
    assert m["snapshot_url"] == f"http://10.0.0.5:8001/snapshot/{eid}.jpg"


def test_event_id_is_stable_for_retries_and_unique_per_fall():
    from dataclasses import replace

    assert event_id(CAMERA_ID, EVENT) == event_id(CAMERA_ID, EVENT)
    assert event_id(CAMERA_ID, EVENT) != event_id(CAMERA_ID, replace(EVENT, track_id=4))
    assert event_id(CAMERA_ID, EVENT) != event_id("zone-2-cam-1", EVENT)


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
    snapshot = "http://10.0.0.5:8001"
    fall = schemas.TelemetryEvent(**fall_payload(EVENT, CAMERA_ID, ZONE_ID, EVENT.timestamp, snapshot))
    beat = schemas.TelemetryEvent(**heartbeat_payload(CAMERA_ID, ZONE_ID, EVENT.timestamp, 28.0, 1))
    assert fall.event_type == "fall" and fall.zone_id == ZONE_ID
    assert beat.event_type == "normal" and beat.pose_confidence == 0.0


@pytest.fixture
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_backend(port: int, tmp_path: Path, api_key: str = ""):
    _backend_schemas()
    import uvicorn
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(sqlite_path=str(tmp_path / "incidents.sqlite3"), api_key=api_key))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "backend did not start"
    return server, thread


def _incidents(port: int, api_key: str = "") -> list:
    headers = {"X-API-Key": api_key} if api_key else {}
    return requests.get(f"http://127.0.0.1:{port}/api/v1/incidents", headers=headers, timeout=2).json()


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


def test_fall_reaches_real_backend_and_becomes_incident(free_port, tmp_path):
    server, thread = _start_backend(free_port, tmp_path)
    try:
        emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
        emitter.send(heartbeat_payload(CAMERA_ID, ZONE_ID, time.time(), 28.0, 1))
        emitter.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
        assert _wait_for(lambda: emitter.delivered == 2)
        incidents = _incidents(free_port)
        assert len(incidents) == 1  # heartbeat is acknowledged but not stored
        assert incidents[0]["incident_id"] == event_id(CAMERA_ID, EVENT)
        assert incidents[0]["zone_id"] == ZONE_ID and incidents[0]["event_type"] == "fall"
        assert emitter.rejected == 0
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_resent_fall_is_a_duplicate_not_a_second_incident(free_port, tmp_path):
    server, thread = _start_backend(free_port, tmp_path)
    try:
        emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
        payload = fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time())
        emitter.send(payload)
        emitter.send(payload)
        assert _wait_for(lambda: emitter.delivered == 2)
        assert len(_incidents(free_port)) == 1 and emitter.rejected == 0
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_api_key_is_sent_and_a_wrong_key_is_counted_as_rejected(free_port, tmp_path):
    server, thread = _start_backend(free_port, tmp_path, api_key="team-secret")
    try:
        good = TelemetryEmitter(f"http://127.0.0.1:{free_port}", api_key="team-secret")
        good.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
        assert _wait_for(lambda: good.delivered == 1) and good.rejected == 0

        bad = TelemetryEmitter(f"http://127.0.0.1:{free_port}", api_key="wrong")
        from dataclasses import replace
        bad.send(fall_payload(replace(EVENT, track_id=9), CAMERA_ID, ZONE_ID, sent_at=time.time()))
        assert _wait_for(lambda: bad.rejected == 1) and bad.pending_falls == 0
        assert len(_incidents(free_port, "team-secret")) == 1
        good.close(), bad.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_fall_ignored_by_backend_is_counted_as_rejected(free_port, tmp_path):
    from dataclasses import replace

    server, thread = _start_backend(free_port, tmp_path)
    try:
        emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
        emitter.send(fall_payload(replace(EVENT, pose_confidence=0.5), CAMERA_ID, ZONE_ID, sent_at=time.time()))
        assert _wait_for(lambda: emitter.rejected == 1)
        assert _incidents(free_port) == []
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_falls_queued_during_outage_are_delivered_on_recovery(free_port, tmp_path):
    emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
    emitter.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
    assert _wait_for(lambda: emitter.pending_falls == 1)

    server, thread = _start_backend(free_port, tmp_path)
    try:
        assert _wait_for(lambda: emitter.pending_falls == 0, timeout=10)
        assert len(_incidents(free_port)) == 1
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_assessment_waits_for_its_fall_and_tolerates_missing_endpoint(free_port, tmp_path, caplog):
    """Dev 2's backend has no assessment endpoint yet: warn once, keep going."""
    from cv_engine.detector.types import Assessment, PostFallAssessment
    from cv_engine.transport.emitter import assessment_payload

    server, thread = _start_backend(free_port, tmp_path)
    try:
        emitter = TelemetryEmitter(f"http://127.0.0.1:{free_port}")
        a = PostFallAssessment(EVENT, Assessment.UNRESPONSIVE, EVENT.timestamp + 10, 10.0, 0.004)
        emitter.send(fall_payload(EVENT, CAMERA_ID, ZONE_ID, sent_at=time.time()))
        emitter.send_assessment(event_id(CAMERA_ID, EVENT), assessment_payload(a, CAMERA_ID, ZONE_ID))
        emitter.send_assessment(event_id(CAMERA_ID, EVENT), assessment_payload(a, CAMERA_ID, ZONE_ID))
        emitter.send(heartbeat_payload(CAMERA_ID, ZONE_ID, time.time(), 20.0, 1))
        assert _wait_for(lambda: emitter.delivered == 2)  # fall + heartbeat still go through
        assert emitter.rejected == 0 and emitter.assessments_delivered == 0
        assert caplog.text.count("no /api/v1/incidents/{incident_id}/assessment endpoint") == 1
        emitter.close()
    finally:
        server.should_exit = True
        thread.join(5)


def test_assessment_payload_shape():
    from cv_engine.detector.types import Assessment, PostFallAssessment
    from cv_engine.transport.emitter import assessment_payload

    body = assessment_payload(PostFallAssessment(EVENT, Assessment.MOVING, EVENT.timestamp + 10, 10.04, 0.0712),
                              CAMERA_ID, ZONE_ID)
    assert body == {"outcome": "moving", "seconds_down": 10.0, "motion": 0.071,
                    "observed_at": "2026-10-03T21:14:17.412Z", "camera_id": CAMERA_ID, "zone_id": ZONE_ID}
