import pytest

pytest.importorskip("requests")
pytest.importorskip("numpy")

from app.config import Settings
from app.verify_cv_integration import exercise_cv
from app.verify_realtime import verify


def test_actual_dev1_emitter_to_backend_dashboard(tmp_path):
    result = verify(Settings(sqlite_path=str(tmp_path / "cv.sqlite3")), exercise_fn=exercise_cv)
    assert result["status"] == "passed", result
    assert len(result["checks"]) == 9
    assert result["transport"] == "dev1_rest_emitter_to_backend_websocket"
