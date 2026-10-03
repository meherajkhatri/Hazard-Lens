"""Hours 0–3 gate: verify the configured Supabase incident table without sending SMS."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.config import Settings
from app.schemas import IncidentAlert
from app.storage import SupabaseStore


async def verify(settings, *, write_probe=False, transport=None):
    required = {"STORAGE_BACKEND=supabase": settings.storage == "supabase",
        "SUPABASE_URL": bool(settings.supabase_url.startswith("https://")),
        "SUPABASE_SECRET_KEY": bool(settings.supabase_key), "API_KEY": bool(settings.api_key)}
    missing = [name for name, present in required.items() if not present]
    if missing:
        return {"status": "blocked", "missing": missing}
    probe_id = str(uuid4())
    result = {"status": "failed", "checks": []}
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            store = SupabaseStore(settings, client)
            # Explicit columns validate the schema even when the table is empty.
            response = await client.get(store.url, headers=store.headers,
                params={"select": ",".join(IncidentAlert.model_fields), "limit": "1"})
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError("Expected rows")
            for row in rows:
                IncidentAlert.model_validate(row)
            result["checks"].append("table_read_and_columns")
            if not write_probe:
                return {**result, "status": "incomplete", "next": "Run with --write-probe to verify insert, readback, uniqueness, and update"}
            now = datetime.now(timezone.utc)
            probe = IncidentAlert(incident_id=probe_id, camera_id="setup-verification",
                zone_id="Setup Verification", event_type="fall", pose_confidence=1,
                severity="high", description="SIMULATED setup verification; no emergency and no SMS",
                location="Setup Verification", detected_at=now, received_at=now,
                status="resolved", sms_status="not_required", metadata={"simulated": True, "setup_probe": True})
            # A labeled, resolved record is retained as evidence. No deletes or alert dispatch.
            result["probe_id"] = probe_id
            if not await store.insert(probe):
                raise ValueError("Probe was not inserted")
            result["checks"].append("insert")
            stored = await store.get(probe_id)
            if stored is None or stored.model_dump() != probe.model_dump():
                raise ValueError("Readback mismatch")
            result["checks"].append("readback")
            if await store.insert(probe):
                raise ValueError("Duplicate accepted")
            result["checks"].append("unique_incident_id")
            description = "SIMULATED setup verification PASSED; no emergency and no SMS"
            updated = await store.update(probe_id, {"description": description})
            if updated is None or updated.description != description:
                raise ValueError("Update mismatch")
            result["checks"].append("update")
            return {**result, "status": "passed"}
    except httpx.HTTPStatusError as exc:
        return {**result, "error": "supabase_http_error", "http_status": exc.response.status_code}
    except httpx.RequestError:
        return {**result, "error": "supabase_connection_failed"}
    except (ValueError, KeyError, TypeError):
        return {**result, "error": "schema_or_readback_mismatch"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-probe", action="store_true",
        help="Retain one labeled, resolved test incident to verify writes. Never sends SMS.")
    args = parser.parse_args()
    result = asyncio.run(verify(Settings.from_env(), write_probe=args.write_probe))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
