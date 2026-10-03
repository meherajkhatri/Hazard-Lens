import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas import IncidentAlert
from app.storage import SupabaseStore


@pytest.mark.parametrize("key", ["sb_secret_test", "legacy-jwt"])
def test_supabase_crud_contract(key):
    now = datetime.now(timezone.utc)
    record = IncidentAlert(incident_id=uuid4(), camera_id="camera-1", zone_id="Zone 1",
        event_type="fall", pose_confidence=.9, severity="high", description="Possible fall",
        location="Zone 1", detected_at=now, received_at=now)
    rows = {}
    def handler(request):
        assert request.headers["apikey"] == key
        if key.startswith("sb_secret_"):
            assert "authorization" not in request.headers
        else:
            assert request.headers["authorization"] == "Bearer legacy-jwt"
        assert request.url.path == "/rest/v1/incidents"
        if request.method == "POST":
            assert "resolution=ignore-duplicates" in request.headers["prefer"]
            data = json.loads(request.content)
            if data["incident_id"] in rows:
                return httpx.Response(201, json=[])
            rows[data["incident_id"]] = data
            return httpx.Response(201, json=[data])
        if request.method == "PATCH":
            rows[str(record.incident_id)].update(json.loads(request.content))
        if "zone_id" in request.url.params:
            assert request.url.params["zone_id"] == "eq.Zone 1"
            assert request.url.params.get_list("detected_at") == [f"gte.{now.isoformat()}", f"lte.{now.isoformat()}"]
        return httpx.Response(200, json=list(rows.values()))
    async def run():
        settings = Settings(supabase_url="https://example.supabase.co", supabase_key=key)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            store = SupabaseStore(settings, client)
            assert await store.insert(record)
            assert not await store.insert(record)
            assert (await store.get(record.incident_id)).incident_id == record.incident_id
            assert len(await store.list(zone_id="Zone 1", since=now, until=now)) == 1
            assert (await store.update(record.incident_id, {"status": "resolved"})).status == "resolved"
    asyncio.run(run())


def test_storage_outage_is_not_success():
    settings = Settings(storage="supabase", supabase_url="https://example.supabase.co", supabase_key="sb_secret_test")
    with TestClient(create_app(settings, transport=httpx.MockTransport(lambda _: httpx.Response(503)))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/ready").status_code == 503
        assert client.get("/api/v1/incidents").json() == {"detail": "Incident storage unavailable"}
