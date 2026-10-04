import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.verify_coach import verify


def test_live_verifier_blocks_without_credentials():
    assert verify(Settings())["status"] == "blocked"


def test_coach_verifier_grounds_answers_and_disables_sms(tmp_path):
    settings = Settings(sqlite_path=str(tmp_path / "coach.sqlite3"), api_key="test",
        gemini_key="test", gemini_model="test-model", sms_mode="twilio")
    def provider(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        context = json.loads(body["contents"][0]["parts"][0]["text"])
        rows = context["incidents"]
        if rows:
            assert len(rows) == 1 and rows[0]["simulated"] is True
            assert rows[0]["status"] == "resolved"
            answer = "One simulated fall: " + rows[0]["incident_id"]
        else:
            answer = "No records were supplied for this zone."
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": answer}]}}]})
    result = verify(settings, transport=httpx.MockTransport(provider))
    assert result["status"] == "passed", result
    assert len(result["checks"]) == 7
    assert len(result["answers"]) == 2


def test_coach_retries_a_transient_provider_failure(tmp_path):
    settings = Settings(sqlite_path=str(tmp_path / "coach.sqlite3"), api_key="test", gemini_key="test", gemini_model="test")
    calls = 0
    def provider(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Recovered."}]}}]})
    with TestClient(create_app(settings, transport=httpx.MockTransport(provider)), headers={"X-API-Key": "test"}) as client:
        response = client.post("/api/v1/coach/chat", json={"question": "Summarize"})
    assert response.status_code == 200
    assert calls == 2


@pytest.mark.parametrize("payload", [[], {"candidates": None}, {"candidates": []},
    {"candidates": [{"content": {"parts": None}}]},
    {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "Truncated"}]}}]},
    {"promptFeedback": {"blockReason": "SAFETY"}}])
def test_invalid_or_incomplete_provider_answers_are_not_success(tmp_path, payload):
    settings = Settings(sqlite_path=str(tmp_path / "coach.sqlite3"), api_key="test", gemini_key="test", gemini_model="test")
    with TestClient(create_app(settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))),
        headers={"X-API-Key": "test"}) as client:
        response = client.post("/api/v1/coach/chat", json={"question": "Summarize"})
        assert response.status_code == 502
