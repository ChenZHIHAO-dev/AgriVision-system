from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv, dotenv_values

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    root: Path
    runtime: Path
    models: Path
    device: str = "auto"
    deepseek_key: str = field(default="", repr=False)
    secret_file: Path | None = field(default=None, repr=False)
    deepseek_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    cors: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    max_upload: int = 8 * 1024 * 1024
    allow_experimental_models: bool = False
    admin_password_hash: str = field(default="", repr=False)
    serve_web: bool = True
    build_commit: str = ""
    login_attempts: int = 5
    login_window_seconds: int = 300
    recognition_per_minute: int = 30
    recognition_concurrency: int = 2
    chat_per_hour: int = 30
    chat_per_day: int = 100
    chat_concurrency: int = 2

    def get_deepseek_key(self):
        """Only the application runtime reads the user-owned, git-ignored file."""
        key = self.deepseek_key
        if not key and self.secret_file is not None:
            try:
                key = dotenv_values(self.secret_file, interpolate=False).get("DEEPSEEK_API_KEY") or ""
            except (OSError, UnicodeError):
                return ""
        key = key.strip()
        return key if key and len(key) <= 4096 and not any(c.isspace() for c in key) else ""

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            root=ROOT,
            runtime=ROOT / os.getenv("AGRIVISION_RUNTIME_DIR", "runtime"),
            models=ROOT / os.getenv("AGRIVISION_MODEL_DIR", "artifacts/models"),
            device=os.getenv("AGRIVISION_DEVICE", "auto"),
            deepseek_key=os.getenv("DEEPSEEK_API_KEY", ""),
            secret_file=ROOT / "secrets/deepseek.env",
            deepseek_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            cors=tuple(os.getenv("AGRIVISION_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")),
            allow_experimental_models=os.getenv("AGRIVISION_ALLOW_EXPERIMENTAL_MODELS", "1") == "1",
            admin_password_hash=os.getenv("AGRIVISION_ADMIN_PASSWORD_HASH", ""),
            serve_web=os.getenv("AGRIVISION_SERVE_WEB", "1") == "1",
            build_commit=os.getenv("AGRIVISION_BUILD_COMMIT", ""),
            login_attempts=max(1, int(os.getenv("AGRIVISION_LOGIN_ATTEMPTS", "5"))),
            login_window_seconds=max(1, int(os.getenv("AGRIVISION_LOGIN_WINDOW_SECONDS", "300"))),
            recognition_per_minute=max(1, int(os.getenv("AGRIVISION_RECOGNITION_PER_MINUTE", "30"))),
            recognition_concurrency=max(1, int(os.getenv("AGRIVISION_RECOGNITION_CONCURRENCY", "2"))),
            chat_per_hour=max(1, int(os.getenv("AGRIVISION_CHAT_PER_HOUR", "30"))),
            chat_per_day=max(1, int(os.getenv("AGRIVISION_CHAT_PER_DAY", "100"))),
            chat_concurrency=max(1, int(os.getenv("AGRIVISION_CHAT_CONCURRENCY", "2"))),
        )
