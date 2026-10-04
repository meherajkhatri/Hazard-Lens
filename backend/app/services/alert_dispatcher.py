import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.schemas import EmailAlert


class AlertDispatcher:
    def __init__(self, settings, client, smtp_factory=None):
        self.settings = settings
        self.client = client
        self.smtp_factory = smtp_factory or smtplib.SMTP

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

    async def _send_all(self, message, subject="Hazard Lens safety alert"):
        if self.settings.alert_provider == "brevo_email":
            results = []
            for recipient in self.settings.brevo_recipients:
                results.append(await self.send_email_alert(EmailAlert(recipient=recipient,
                    subject=subject, message=message)))
            statuses = {row["status"] for row in results}
            return (next(iter(statuses)) if len(statuses) == 1 else "partial"), results
        return "not_configured", []

    async def dispatch(self, incident):
        return await self._send_all(
            f"Hazard Lens: possible {incident.event_type} in {incident.zone_id}, camera {incident.camera_id}, at {incident.detected_at.isoformat()}. Incident {incident.incident_id}. Check the dashboard.",
            subject=f"Hazard Lens: possible {incident.event_type} in {incident.zone_id}")

    async def escalate(self, incident, assessment):
        """Follow-up for a fall the camera kept watching. Not subject to the cooldown:
        an unresponsive worker must never be silenced by an earlier alert."""
        if assessment.outcome == "unresponsive":
            message = (f"Hazard Lens URGENT: worker down {assessment.seconds_down:.0f}s with NO MOVEMENT in "
                       f"{incident.zone_id} (camera {assessment.camera_id}). Possible medical emergency. "
                       f"Incident {incident.incident_id}.")
        else:
            message = (            f"Hazard Lens update: worker in {incident.zone_id} got back up after "
                       f"{assessment.seconds_down:.0f}s. Incident {incident.incident_id} still needs a check.")
        subject = "Hazard Lens URGENT: worker unresponsive" if assessment.outcome == "unresponsive" else "Hazard Lens update: worker recovered"
        return await self._send_all(message, subject=subject)
