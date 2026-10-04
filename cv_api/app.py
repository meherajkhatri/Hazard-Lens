import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

from cv_api.config import ApiConfig
from cv_api.detection_service import DetectionService


def create_app(config: ApiConfig | None = None, service: DetectionService | None = None) -> Flask:
    config = config or ApiConfig()
    config.validate()
    app = Flask(__name__)
    CORS(app, origins=list(config.cors_origins))
    detector = service or DetectionService(config)

    @app.get("/api/health")
    def health():
        body = detector.health()
        return jsonify(body), 200 if body["model_ready"] else 503

    @app.post("/api/detect")
    def detect():
        uploaded = request.files.get("frame")
        if uploaded is None:
            return jsonify({"success": False, "error": "Missing multipart field 'frame'"}), 400
        try:
            result = detector.detect(uploaded.read(), request.form.get("zone_id"))
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"success": False, "error": str(exc)}), 503

    @app.post("/api/test/fall")
    def test_fall():
        try:
            return jsonify(detector.simulated_fall(request.form.get("zone_id")))
        except PermissionError as exc:
            return jsonify({"success": False, "error": str(exc)}), 403

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = ApiConfig()
    create_app(settings).run(host=settings.host, port=settings.port, threaded=True)
