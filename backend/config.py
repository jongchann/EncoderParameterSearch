from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path = PROJECT_ROOT / "artifacts" / "metadata.sqlite3"
    artifact_root: Path = PROJECT_ROOT / "artifacts"


def get_settings() -> Settings:
    return Settings()
