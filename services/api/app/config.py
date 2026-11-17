from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    root: Path
    runtime: Path
    models: Path
    device: str = "auto"
    deepseek_key: str = ""
    deepseek_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    cors: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    max_upload: int = 8 * 1024 * 1024

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            root=ROOT,
            runtime=ROOT / os.getenv("AGRIVISION_RUNTIME_DIR", "runtime"),
            models=ROOT / os.getenv("AGRIVISION_MODEL_DIR", "artifacts/models"),
            device=os.getenv("AGRIVISION_DEVICE", "auto"),
            deepseek_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            cors=tuple(os.getenv("AGRIVISION_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")),
        )
