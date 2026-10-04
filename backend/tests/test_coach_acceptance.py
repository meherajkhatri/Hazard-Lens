import json

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.verify_coach import verify


def ollama_response(answer):
    return httpx.Response(200, json={
        "model": "qwen2.5:3b",
        "done": True,
        "message": {"role": "assistant", "content": answer},
    })


def test_coach_verifier_grounds_answers_and_disables_sms(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "coach.sqlite3"),
        api_key="test",
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:3b",
        alert_provider="none",
    )

    def provider(request):
        assert request.url.host == "127.0.0.1"
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:3b"
        context = json.loads(body["messages"][-1]["content"])
        rows = context["incidents"]
        if rows:
            assert len(rows) == 1
            assert rows[0]["simulated"] is True
            assert rows[0]["status"] == "resolved"
            answer = "One simulated fall: " + rows[0]["incident_id"]
        else:
            answer = "No records were supplied for this zone."
        return ollama_response(answer)

    result = verify(settings, transport=httpx.MockTransport(provider))
    assert result["status"] == "passed", result
    assert len(result["checks"]) == 7
    assert len(result["answers"]) == 2


def test_coach_retries_a_transient_ollama_failure(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "coach.sqlite3"),
        api_key="test",
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:3b",
    )
    calls = 0

    def provider(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return ollama_response("Recovered.")

    with TestClient(
        create_app(settings, transport=httpx.MockTransport(provider)),
        headers={"X-API-Key": "test"},
    ) as client:
        response = client.post("/api/v1/coach/chat", json={"question": "Summarize"})

    assert response.status_code == 200
    assert response.json()["mode"] == "ollama"
    assert calls == 2


def test_coach_falls_back_if_ollama_is_unavailable(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "coach.sqlite3"),
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:3b",
    )

    def provider(_):
        raise httpx.ConnectError("offline")

    with TestClient(
        create_app(settings, transport=httpx.MockTransport(provider))
    ) as client:
        response = client.post("/api/v1/coach/chat", json={"question": "Summarize"})

    assert response.status_code == 503
    assert "Ollama is not reachable" in response.json()["detail"]


def test_empty_ollama_answer_falls_back(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "coach.sqlite3"),
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:3b",
    )
    with TestClient(
        create_app(
            settings,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={"message": {"role": "assistant", "content": ""}},
                )
            ),
        )
    ) as client:
        response = client.post("/api/v1/coach/chat", json={"question": "Summarize"})

    assert response.status_code == 502
    assert "invalid or empty" in response.json()["detail"]
