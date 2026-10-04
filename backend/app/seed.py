"""Seed demo history directly without dispatching alerts."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.config import Settings
from app.schemas import IncidentAlert
from app.storage import SQLiteStore, SupabaseStore


async def seed(settings=None):
    settings = settings or Settings.from_env()
    settings.validate()
    async with httpx.AsyncClient(timeout=10) as client:
        store = SQLiteStore(settings.sqlite_path) if settings.storage == "sqlite" else SupabaseStore(settings, client)
        now = datetime.now(timezone.utc)
        inserted = 0
        for index in range(18):
            zone = ["Zone 1", "Zone 2", "Forklift Corridor"][index % 3]
            kind = ["fall", "ppe_violation", "collision_risk"][(index // 3) % 3]
            timestamp = now - timedelta(hours=index * 4 + 1)
            inserted += await store.insert(IncidentAlert(
                incident_id=uuid5(NAMESPACE_URL, f"call-help-demo-{index}"), camera_id=f"demo-camera-{index % 3 + 1}",
                zone_id=zone, event_type=kind, pose_confidence=0.91,
                severity="medium" if kind == "ppe_violation" else "high",
                description=f"Simulated {kind.replace('_', ' ')}", location=zone,
                detected_at=timestamp, received_at=timestamp, status="resolved",
                alert_status="not_configured", metadata={"simulated": True} ))
        return inserted


if __name__ == "__main__":
    print(f"Inserted {asyncio.run(seed())} simulated incidents; no alerts sent.")
