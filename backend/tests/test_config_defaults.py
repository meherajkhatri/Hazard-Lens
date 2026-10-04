import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def clean_environment(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *args: None)
    for name in ("STORAGE_BACKEND", "ALERT_PROVIDER", "SUPABASE_URL", "SUPABASE_SECRET_KEY",
                 "API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_unconfigured_machine_cannot_silently_start_local(clean_environment):
    settings = Settings.from_env()
    assert settings.storage == "supabase"
    assert settings.alert_provider == "none"
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        with TestClient(create_app(settings)):
            pass


def test_explicit_offline_mode_still_works(clean_environment, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("ALERT_PROVIDER", "none")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "offline.sqlite3"))
    with TestClient(create_app(Settings.from_env())) as client:
        assert client.get("/health").json()["storage"] == "sqlite"
        assert client.get("/api/v1/ready").status_code == 200


def test_database_credentials_alone_do_not_enable_email(clean_environment, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    with TestClient(create_app(Settings.from_env())) as client:
        assert client.get("/health").json()["alert_provider"] == "none"
