import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from app.schemas import EmailAlert, SMSAlert


class AlertDispatcher:
    def __init__(self, settings, client, smtp_factory=None):
        self.settings = settings
        self.client = client
        self.smtp_factory = smtp_factory or smtplib.SMTP

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

    def _send_email(self, alert: EmailAlert) -> dict[str, str]:
        message = EmailMessage()
        message["From"] = formataddr((self.settings.brevo_from_name, self.settings.brevo_from_email))
        message["To"] = alert.recipient
        message["Subject"] = alert.subject
        message.set_content(alert.message)
        server = None
        try:
            server = self.smtp_factory("smtp-relay.brevo.com", 587, timeout=10)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(self.settings.brevo_smtp_login, self.settings.brevo_smtp_key)
            server.send_message(message)
            return {"status": "queued", "recipient": alert.recipient, "channel": "email", "provider": "brevo"}
        except (OSError, smtplib.SMTPException):
            return {"status": "failed", "recipient": alert.recipient, "channel": "email",
                "provider": "brevo", "error": "provider_rejected_request"}
        finally:
            if server:
                try:
                    server.quit()
                except (OSError, smtplib.SMTPException):
                    pass

    async def send_email_alert(self, alert: EmailAlert) -> dict[str, str]:
        return await asyncio.to_thread(self._send_email, alert)

    async def dispatch(self, incident):
        if self.settings.alert_provider == "brevo_email":
            results = []
            for recipient in self.settings.brevo_recipients:
                results.append(await self.send_email_alert(EmailAlert(recipient=recipient,
                    subject=f"CALL_HELP: possible {incident.event_type} in {incident.zone_id}",
                    message=(f"CALL_HELP alert\n\nPossible {incident.event_type} detected in {incident.zone_id}.\n"
                        f"Camera: {incident.camera_id}\nDetected: {incident.detected_at.isoformat()}\n"
                        f"Incident: {incident.incident_id}\n\nCheck the dashboard immediately."))))
            statuses = {row["status"] for row in results}
            return (next(iter(statuses)) if len(statuses) == 1 else "partial"), results
        if not self.settings.sms_recipients:
            return "not_configured", []
        results = []
        for recipient in self.settings.sms_recipients:
            results.append(await self.send_sms_alert(SMSAlert(recipient=recipient,
                message=f"CALL_HELP: possible {incident.event_type} in {incident.zone_id}, camera {incident.camera_id}, at {incident.detected_at.isoformat()}. Incident {incident.incident_id}. Check the dashboard.")))
        statuses = {row["status"] for row in results}
        return (next(iter(statuses)) if len(statuses) == 1 else "partial"), results
