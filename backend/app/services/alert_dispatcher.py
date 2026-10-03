from app.schemas import SMSAlert


class AlertDispatcher:
    """Stub dispatcher for integrating real SMS providers later."""

    async def send_sms_alert(self, alert: SMSAlert) -> dict[str, str]:
        return {
            "status": "queued",
            "recipient": alert.recipient,
            "message": alert.message,
        }
