from io import BytesIO

from cv_api.app import create_app
from cv_api.config import ApiConfig


class FakeService:
    def health(self):
        return {
            "status": "ok", "model_ready": True, "model": "test",
            "device": "cpu", "emergency_mode": False, "test_mode": True,
            "confirmation_seconds": 1.0, "confidence_threshold": 0.75,
            "last_inference_ms": 1.0, "error": None,
        }

    def detect(self, raw, zone_id=None):
        assert raw == b"jpeg"
        return {
            "success": True, "person_detected": True, "fall_detected": False,
            "confidence": 0.9, "status": "person_detected", "people": [],
            "frame": {"width": 640, "height": 480}, "inference_ms": 1.0,
            "emergency_mode": False,
        }

    def simulated_fall(self, zone_id=None):
        return {
            "success": True, "person_detected": True, "fall_detected": True,
            "confidence": 0.99, "status": "fall_detected", "people": [],
            "frame": {"width": 640, "height": 480}, "inference_ms": 0.0,
            "emergency_mode": False, "simulated": True,
        }


def client():
    app = create_app(ApiConfig(), FakeService())
    app.testing = True
    return app.test_client()


def test_health():
    response = client().get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["model_ready"] is True


def test_detect_requires_frame():
    response = client().post("/api/detect")
    assert response.status_code == 400


def test_detect_accepts_multipart_frame():
    response = client().post(
        "/api/detect",
        data={"frame": (BytesIO(b"jpeg"), "frame.jpg"), "zone_id": "Zone 1"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "person_detected"


def test_safe_fall_simulation():
    response = client().post("/api/test/fall", data={"zone_id": "Zone 1"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["fall_detected"] is True
    assert body["emergency_mode"] is False
