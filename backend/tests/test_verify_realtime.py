from app.config import Settings
from app.verify_realtime import verify


def test_real_network_camera_dashboard_and_coach(tmp_path):
    result = verify(Settings(sqlite_path=str(tmp_path / "realtime.sqlite3"), api_key="realtime-test-key"))
    assert result["status"] == "passed", result
    assert len(result["checks"]) == 10
    assert result["broadcast_latency_ms"] >= 0
    assert result["transport"] == "real_uvicorn_http_and_websockets"
