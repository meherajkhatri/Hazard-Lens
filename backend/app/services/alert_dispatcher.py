import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import certifi

from app.schemas import EmailAlert


class AlertDispatcher:
    def __init__(self, settings, client, smtp_factory=None):
        self.settings = settings
        self.client = client
        self.smtp_factory = smtp_factory or smtplib.SMTP

    def _send_email(self, alert: EmailAlert) -> dict[str, str]:
        """
        Send one email through Brevo SMTP.
        """

        message = EmailMessage()

        message["From"] = formataddr(
            (
                self.settings.brevo_from_name,
                self.settings.brevo_from_email,
            )
        )

        message["To"] = alert.recipient
        message["Subject"] = alert.subject
        message.set_content(alert.message)

        server = None

        try:
            print("Connecting to Brevo SMTP...")

            server = self.smtp_factory(
                "smtp-relay.brevo.com",
                587,
                timeout=10,
            )

            # Identify ourselves to SMTP server
            server.ehlo()

            # Create secure TLS connection
            tls_context = ssl.create_default_context(
                cafile=certifi.where()
            )

            print("Starting TLS...")
            server.starttls(context=tls_context)

            # EHLO again after TLS
            server.ehlo()

            print(
                "Logging into Brevo SMTP with:",
                self.settings.brevo_smtp_login,
            )

            # IMPORTANT:
            # brevo_smtp_key must be an SMTP key,
            # NOT your normal Brevo password.
            server.login(
                self.settings.brevo_smtp_login,
                self.settings.brevo_smtp_key,
            )

            print(
                f"Sending email from "
                f"{self.settings.brevo_from_email} "
                f"to {alert.recipient}"
            )

            server.send_message(message)

            print("EMAIL SENT SUCCESSFULLY")

            return {
                "status": "queued",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
            }

        except smtplib.SMTPAuthenticationError as exc:
            print("SMTP AUTHENTICATION ERROR:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"authentication_failed: {exc}",
            }

        except smtplib.SMTPRecipientsRefused as exc:
            print("SMTP RECIPIENT REFUSED:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"recipient_refused: {exc}",
            }

        except smtplib.SMTPSenderRefused as exc:
            print("SMTP SENDER REFUSED:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"sender_refused: {exc}",
            }

        except smtplib.SMTPConnectError as exc:
            print("SMTP CONNECTION ERROR:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"connection_failed: {exc}",
            }

        except smtplib.SMTPException as exc:
            print("SMTP ERROR:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"smtp_error: {exc}",
            }

        except OSError as exc:
            print("NETWORK / OS ERROR:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"network_error: {exc}",
            }

        except Exception as exc:
            print("UNEXPECTED EMAIL ERROR:", repr(exc))

            return {
                "status": "failed",
                "recipient": alert.recipient,
                "channel": "email",
                "provider": "brevo",
                "error": f"unexpected_error: {exc}",
            }

        finally:
            if server:
                try:
                    server.quit()
                except (OSError, smtplib.SMTPException):
                    pass

    async def send_email_alert(
        self,
        alert: EmailAlert,
    ) -> dict[str, str]:

        return await asyncio.to_thread(
            self._send_email,
            alert,
        )

    async def _send_all(
        self,
        message,
        subject="Hazard Lens safety alert",
    ):
        """
        Send an alert to every configured Brevo recipient.
        """

        if self.settings.alert_provider != "brevo_email":
            print(
                "Email alerts are disabled. "
                f"Current provider: {self.settings.alert_provider}"
            )

            return "not_configured", []

        results = []

        for recipient in self.settings.brevo_recipients:
            result = await self.send_email_alert(
                EmailAlert(
                    recipient=recipient,
                    subject=subject,
                    message=message,
                )
            )

            results.append(result)

        if not results:
            return "not_configured", []

        statuses = {
            row["status"]
            for row in results
        }

        status = (
            next(iter(statuses))
            if len(statuses) == 1
            else "partial"
        )

        return status, results

    async def dispatch(self, incident):
        """
        Initial safety alert.
        """

        message = (
            f"Hazard Lens: possible {incident.event_type} "
            f"in {incident.zone_id}, "
            f"camera {incident.camera_id}, "
            f"at {incident.detected_at.isoformat()}. "
            f"Incident {incident.incident_id}. "
            f"Check the dashboard."
        )

        subject = (
            f"Hazard Lens: possible "
            f"{incident.event_type} "
            f"in {incident.zone_id}"
        )

        return await self._send_all(
            message,
            subject=subject,
        )

    async def escalate(
        self,
        incident,
        assessment,
    ):
        """
        Follow-up alert after a fall.

        unresponsive:
            send urgent alert

        recovered:
            send recovery/update alert
        """

        if assessment.outcome == "unresponsive":

            message = (
                f"Hazard Lens URGENT: worker down "
                f"{assessment.seconds_down:.0f}s "
                f"with NO MOVEMENT in "
                f"{incident.zone_id} "
                f"(camera {assessment.camera_id}). "
                f"Possible medical emergency. "
                f"Incident {incident.incident_id}."
            )

            subject = (
                "Hazard Lens URGENT: "
                "worker unresponsive"
            )

        else:

            message = (
                f"Hazard Lens update: worker in "
                f"{incident.zone_id} "
                f"got back up after "
                f"{assessment.seconds_down:.0f}s. "
                f"Incident {incident.incident_id} "
                f"still needs a check."
            )

            subject = (
                "Hazard Lens update: "
                "worker recovered"
            )

        return await self._send_all(
            message,
            subject=subject,
        )