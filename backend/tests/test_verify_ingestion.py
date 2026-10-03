from app.config import Settings
from app.verify_ingestion import verify


def test_ingestion_probe_forces_dry_run_and_checks_persistence(tmp_path):
    # Even a live SMS setting must not allow this verifier to send a real message.
    settings = Settings(sqlite_path=str(tmp_path / "probe.sqlite3"), sms_mode="twilio")
    result = verify(settings)
    assert result["status"] == "passed"
    assert result["sms_mode"] == "dry_run"
    assert result["checks"] == ["storage_ready", "fall_ingestion", "sms_dry_run_recorded",
        "retry_deduplicated", "conflicting_retry_rejected", "persisted_readback",
        "acknowledged", "resolved", "persisted_after_restart"]
