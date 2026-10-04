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
    alert_provider: str = "none"
    brevo_smtp_login: str = ""
    brevo_smtp_key: str = ""
    brevo_from_email: str = ""
    brevo_from_name: str = "Hazard Lens"
    brevo_recipients: list[str] = field(default_factory=list)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    min_confidence: float = 0.7
    alert_min_confidence: float = 0.9
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
            alert_provider=os.getenv("ALERT_PROVIDER", "none"),
            brevo_smtp_login=os.getenv("BREVO_SMTP_LOGIN", ""),
            brevo_smtp_key=os.getenv("BREVO_SMTP_KEY", ""),
            brevo_from_email=os.getenv("BREVO_FROM_EMAIL", ""),
            brevo_from_name=os.getenv("BREVO_FROM_NAME", "Hazard Lens"),
            brevo_recipients=csv("BREVO_RECIPIENTS"),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.7")),
            alert_min_confidence=float(os.getenv("ALERT_MIN_CONFIDENCE", "0.9")),
            cooldown_seconds=int(os.getenv("ALERT_COOLDOWN_SECONDS", "30")),
        )

    def validate(self):
        if self.storage not in {"sqlite", "supabase"}:
            raise ValueError("STORAGE_BACKEND must be sqlite or supabase")
        if self.storage == "supabase" and not (self.supabase_url.startswith("https://") and self.supabase_key):
            raise ValueError("Configure SUPABASE_URL (HTTPS) and SUPABASE_SECRET_KEY in backend/.env. For offline development only, explicitly set STORAGE_BACKEND=sqlite and ALERT_PROVIDER=none.")
        if self.alert_provider not in {"none", "brevo_email"}:
            raise ValueError("ALERT_PROVIDER must be none or brevo_email")
        if self.alert_provider == "brevo_email" and not all([self.api_key, self.brevo_smtp_login,
            self.brevo_smtp_key, self.brevo_from_email, self.brevo_recipients]):
            raise ValueError("Brevo email requires API_KEY, SMTP credentials, sender, and recipients")
        if not self.ollama_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_URL must be an HTTP(S) URL")
        if not self.ollama_model.strip():
            raise ValueError("OLLAMA_MODEL must not be empty")
        if not 0 <= self.min_confidence <= 1 or not 0 <= self.alert_min_confidence <= 1 or self.cooldown_seconds < 0:
            raise ValueError("Invalid confidence threshold or cooldown")
        for address in self.brevo_recipients + ([self.brevo_from_email] if self.brevo_from_email else []):
            if "@" not in address or address.startswith("@") or address.endswith("@"):
                raise ValueError("Brevo sender and recipients must be email addresses")
