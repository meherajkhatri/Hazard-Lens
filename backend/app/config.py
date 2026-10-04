import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    storage: str = "sqlite"
    sqlite_path: str = "data/call_help.sqlite3"
    api_key: str = ""
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])
    supabase_url: str = ""
    supabase_key: str = ""
    sms_mode: str = "dry_run"
    # "sms" or "whatsapp" (Twilio WhatsApp sandbox: free-form text to numbers that joined it).
    sms_channel: str = "sms"
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = ""
    sms_recipients: list[str] = field(default_factory=list)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    min_confidence: float = 0.7
    cooldown_seconds: int = 30

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        def csv(name, default=""):
            return [part.strip() for part in os.getenv(name, default).split(",") if part.strip()]
        return cls(
            storage=os.getenv("STORAGE_BACKEND", "sqlite"),
            sqlite_path=os.getenv("SQLITE_PATH", "data/call_help.sqlite3"),
            api_key=os.getenv("API_KEY", ""),
            cors_origins=csv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"),
            supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
            supabase_key=os.getenv("SUPABASE_SECRET_KEY", ""),
            sms_mode=os.getenv("SMS_MODE", "dry_run"),
            sms_channel=os.getenv("SMS_CHANNEL", "sms"),
            twilio_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            twilio_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            twilio_from=os.getenv("TWILIO_FROM_NUMBER", ""),
            sms_recipients=csv("SMS_RECIPIENTS"),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.7")),
            cooldown_seconds=int(os.getenv("ALERT_COOLDOWN_SECONDS", "30")),
        )

    def validate(self):
        if self.storage not in {"sqlite", "supabase"}:
            raise ValueError("STORAGE_BACKEND must be sqlite or supabase")
        if self.storage == "supabase" and not (self.supabase_url.startswith("https://") and self.supabase_key):
            raise ValueError("Supabase requires an HTTPS URL and a server secret key")
        if self.sms_channel not in {"sms", "whatsapp"}:
            raise ValueError("SMS_CHANNEL must be sms or whatsapp")
        if self.sms_mode not in {"dry_run", "twilio"}:
            raise ValueError("SMS_MODE must be dry_run or twilio")
        if self.sms_mode == "twilio" and not all([self.api_key, self.twilio_sid, self.twilio_token, self.twilio_from, self.sms_recipients]):
            raise ValueError("Live SMS requires API_KEY, Twilio credentials, sender, and recipients")
        if not self.ollama_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_URL must be an HTTP(S) URL")
        if not self.ollama_model.strip():
            raise ValueError("OLLAMA_MODEL must not be empty")
        if not 0 <= self.min_confidence <= 1 or self.cooldown_seconds < 0:
            raise ValueError("Invalid confidence threshold or cooldown")
        from app.schemas import SMSAlert
        for number in self.sms_recipients + ([self.twilio_from] if self.twilio_from else []):
            SMSAlert(recipient=number, message="validate")
