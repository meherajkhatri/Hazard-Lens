import asyncio
import json

import httpx

from app.config import Settings
from app.verify_setup import verify


def settings():
    return Settings(storage="supabase", supabase_url="https://example.supabase.co",
        supabase_key="sb_secret_test", api_key="test-key")


def test_missing_configuration_blocks_without_network():
    def unexpected(request):
        raise AssertionError("Must not contact any provider")
    result = asyncio.run(verify(Settings(), transport=httpx.MockTransport(unexpected)))
    assert result["status"] == "blocked"
    assert "SUPABASE_SECRET_KEY" in result["missing"]


def test_read_only_is_not_a_pass():
    def handler(request):
        assert request.method == "GET"
        assert "sms_results" in request.url.params["select"]
        return httpx.Response(200, json=[])
    result = asyncio.run(verify(settings(), transport=httpx.MockTransport(handler)))
    assert result["status"] == "incomplete"


def test_write_probe_verifies_each_step_and_retains_resolved_record():
    rows = {}
    def handler(request):
        assert request.url.host == "example.supabase.co"
        if request.method == "POST":
            row = json.loads(request.content)
            if row["incident_id"] in rows:
                return httpx.Response(201, json=[])
            rows[row["incident_id"]] = row
            return httpx.Response(201, json=[row])
        if request.method == "PATCH":
            next(iter(rows.values())).update(json.loads(request.content))
        return httpx.Response(200, json=list(rows.values()))
    result = asyncio.run(verify(settings(), write_probe=True, transport=httpx.MockTransport(handler)))
    assert result["status"] == "passed"
    assert result["checks"] == ["table_read_and_columns", "insert", "readback", "unique_incident_id", "update"]
    row = rows[result["probe_id"]]
    assert row["status"] == "resolved" and row["sms_status"] == "not_required"
    assert row["metadata"]["setup_probe"] is True


def test_schema_failure_does_not_leak_provider_response():
    result = asyncio.run(verify(settings(), write_probe=True,
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="private provider detail"))))
    assert result["status"] == "failed"
    assert result["http_status"] == 401
    assert "private" not in json.dumps(result)
