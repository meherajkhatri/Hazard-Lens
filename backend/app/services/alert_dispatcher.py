import httpx

from app.schemas import SMSAlert


class AlertDispatcher:
    def __init__(self, settings, client):
        self.settings = settings
        self.client = client

    async def send_sms_alert(self, alert: SMSAlert) -> dict[str, str]:
        if self.settings.sms_mode == "dry_run":
            return {"status": "dry_run", "recipient": alert.recipient}
        try:
            response = await self.client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_sid}/Messages.json",
                auth=(self.settings.twilio_sid, self.settings.twilio_token),
                data={"From": self.settings.twilio_from, "To": alert.recipient, "Body": alert.message},
            )
        except httpx.RequestError:
            # A timeout can occur after Twilio accepts a message. Do not retry blindly.
            return {"status": "unknown", "recipient": alert.recipient, "error": "provider_connection_error"}
        if response.is_error:
            result = {"status": "failed", "recipient": alert.recipient, "error": "provider_rejected_request"}
            try:
                provider_code = response.json().get("code")
                if isinstance(provider_code, (int, str)):
                    result["provider_code"] = str(provider_code)
            except (ValueError, AttributeError, TypeError):
                pass
            return result
        try:
            data = response.json()
            return {"status": str(data["status"]), "recipient": alert.recipient, "sid": str(data["sid"])}
        except (ValueError, KeyError, TypeError):
            return {"status": "unknown", "recipient": alert.recipient, "error": "invalid_provider_response"}

    async def dispatch(self, incident):
        if not self.settings.sms_recipients:
            return "not_configured", []
        results = []
        for recipient in self.settings.sms_recipients:
            results.append(await self.send_sms_alert(SMSAlert(recipient=recipient,
                message=f"CALL_HELP: possible {incident.event_type} in {incident.zone_id}, camera {incident.camera_id}, at {incident.detected_at.isoformat()}. Incident {incident.incident_id}. Check the dashboard.")))
        statuses = {row["status"] for row in results}
        return (next(iter(statuses)) if len(statuses) == 1 else "partial"), results
