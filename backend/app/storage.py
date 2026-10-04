import asyncio
import json
import sqlite3
from pathlib import Path

from app.schemas import IncidentAlert


class SQLiteStore:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS incidents (incident_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            rows = db.execute("SELECT incident_id, payload FROM incidents").fetchall()
            for incident_id, payload in rows:
                data = json.loads(payload)
                changed = False
                if "sms_status" in data:
                    data["alert_status"] = data.pop("sms_status")
                    changed = True
                if "sms_results" in data:
                    data["alert_results"] = data.pop("sms_results")
                    changed = True
                if "alert_status" not in data:
                    data["alert_status"] = "not_configured"
                    changed = True
                if "alert_results" not in data:
                    data["alert_results"] = []
                    changed = True
                if changed:
                    db.execute("UPDATE incidents SET payload = ? WHERE incident_id = ?",
                               (json.dumps(data), incident_id))

    def _execute(self, sql, params=(), *, fetch=False):
        with sqlite3.connect(self.path, timeout=10) as db:
            cursor = db.execute(sql, params)
            return cursor.fetchall() if fetch else cursor.rowcount

    async def insert(self, incident):
        return bool(await asyncio.to_thread(self._execute,
            "INSERT OR IGNORE INTO incidents VALUES (?, ?)",
            (str(incident.incident_id), incident.model_dump_json())))

    async def get(self, incident_id):
        rows = await asyncio.to_thread(self._execute, "SELECT payload FROM incidents WHERE incident_id = ?", (str(incident_id),), fetch=True)
        return IncidentAlert.model_validate_json(rows[0][0]) if rows else None

    async def list(self, *, zone_id=None, status=None, since=None, until=None, limit=100, offset=0, camera_id=None, event_type=None, alert_history=False):
        # JSON columns keep the local schema equivalent to the Supabase record.
        clauses, params = [], []
        for field, value in [("zone_id", zone_id), ("status", status), ("camera_id", camera_id), ("event_type", event_type)]:
            if value is not None:
                clauses.append(f"json_extract(payload, '$.{field}') = ?")
                params.append(value)
        for op, value in [(">=", since), ("<=", until)]:
            if value is not None:
                clauses.append(f"julianday(json_extract(payload, '$.detected_at')) {op} julianday(?)")
                params.append(value.isoformat())
        sql = "SELECT payload FROM incidents"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        order_field = "received_at" if alert_history else "detected_at"
        sql += f" ORDER BY julianday(json_extract(payload, '$.{order_field}')) DESC, incident_id DESC LIMIT ? OFFSET ?"
        rows = await asyncio.to_thread(self._execute, sql, (*params, limit, offset), fetch=True)
        return [IncidentAlert.model_validate_json(row[0]) for row in rows]

    async def update(self, incident_id, fields):
        # Patch only specified fields so an acknowledgement cannot overwrite alert results.
        await asyncio.to_thread(self._execute,
            "UPDATE incidents SET payload = json_patch(payload, ?) WHERE incident_id = ?",
            (json.dumps(fields), str(incident_id)))
        return await self.get(incident_id)


class SupabaseStore:
    def __init__(self, settings, client):
        self.client = client
        self.url = settings.supabase_url + "/rest/v1/incidents"
        self.headers = {"apikey": settings.supabase_key}
        # New sb_secret keys use apikey only; legacy service_role JWTs also use Bearer.
        if not settings.supabase_key.startswith("sb_secret_"):
            self.headers["Authorization"] = "Bearer " + settings.supabase_key

    async def insert(self, incident):
        response = await self.client.post(self.url, params={"on_conflict": "incident_id"},
            headers={**self.headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
            json=incident.model_dump(mode="json"))
        response.raise_for_status()
        return bool(response.json())

    async def get(self, incident_id):
        response = await self.client.get(self.url, headers=self.headers,
            params={"incident_id": f"eq.{incident_id}", "limit": "1"})
        response.raise_for_status()
        rows = response.json()
        return IncidentAlert.model_validate(rows[0]) if rows else None

    async def list(self, *, zone_id=None, status=None, since=None, until=None, limit=100, offset=0, camera_id=None, event_type=None, alert_history=False):
        order_field = "received_at" if alert_history else "detected_at"
        params = [("order", f"{order_field}.desc,incident_id.desc"), ("limit", str(limit)), ("offset", str(offset))]
        for field, value in [("zone_id", zone_id), ("status", status), ("camera_id", camera_id), ("event_type", event_type)]:
            if value is not None:
                params.append((field, f"eq.{value}"))
        for op, value in [("gte", since), ("lte", until)]:
            if value is not None:
                params.append(("detected_at", f"{op}.{value.isoformat()}"))
        response = await self.client.get(self.url, headers=self.headers, params=params)
        response.raise_for_status()
        return [IncidentAlert.model_validate(row) for row in response.json()]

    async def update(self, incident_id, fields):
        response = await self.client.patch(self.url, params={"incident_id": f"eq.{incident_id}"},
            headers={**self.headers, "Prefer": "return=representation"}, json=fields)
        response.raise_for_status()
        rows = response.json()
        return IncidentAlert.model_validate(rows[0]) if rows else None
