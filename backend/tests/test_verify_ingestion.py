from app.config import Settings
from app.verify_ingestion import verify
import pytest


@pytest.mark.parametrize("provider", ["twilio", "brevo_email"])
def test_ingestion_probe_forces_dry_run_and_checks_persistence(tmp_path, monkeypatch, provider):
    # Even a live SMS setting must not allow this verifier to send a real message.
    def forbid_email(*args, **kwargs):
        raise AssertionError("Verification must never contact SMTP")
    monkeypatch.setattr("app.services.alert_dispatcher.smtplib.SMTP", forbid_email)
    settings = Settings(sqlite_path=str(tmp_path / "probe.sqlite3"), sms_mode="twilio",
        alert_provider=provider, brevo_smtp_login="test", brevo_smtp_key="test",
        brevo_from_email="alerts@example.com", brevo_recipients=["team@example.com"])
    result = verify(settings)
    assert result["status"] == "passed"
    assert result["sms_mode"] == "dry_run"
    assert result["checks"] == ["storage_ready", "fall_ingestion", "sms_dry_run_recorded",
        "retry_deduplicated", "conflicting_retry_rejected", "persisted_readback",
        "acknowledged", "resolved", "persisted_after_restart"]
