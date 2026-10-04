import pytest

from app.config import Settings
from app.verify_ingestion import verify


@pytest.mark.parametrize("provider", ["none", "brevo_email"])
def test_ingestion_probe_checks_persistence_without_external_alerts(tmp_path, monkeypatch, provider):
    def forbid_email(*args, **kwargs):
        raise AssertionError("Verification must never contact SMTP")
    monkeypatch.setattr("app.services.alert_dispatcher.smtplib.SMTP", forbid_email)
    settings = Settings(sqlite_path=str(tmp_path / "probe.sqlite3"),
        alert_provider=provider, brevo_smtp_login="test", brevo_smtp_key="test",
        brevo_from_email="alerts@example.com", brevo_recipients=["team@example.com"])
    result = verify(settings)
    assert result["status"] == "passed"
    assert result["alert_provider"] == "none"
    assert result["checks"] == ["storage_ready", "fall_ingestion", "alert_status_recorded",
        "retry_deduplicated", "conflicting_retry_rejected", "persisted_readback",
        "acknowledged", "resolved", "persisted_after_restart"]
