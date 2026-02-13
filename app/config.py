from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    max_upload_mb: int

    @staticmethod
    def from_env() -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
        max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "250"))
        return Settings(data_dir=data_dir, max_upload_mb=max_upload_mb)


settings = Settings.from_env()
