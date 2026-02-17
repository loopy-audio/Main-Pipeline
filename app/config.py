from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    max_upload_mb: int
    use_hosted_apis: bool
    api_key: str | None
    whisperx_url: str
    demucs_url: str
    request_timeout_s: int
    enable_gemini: bool
    gemini_api_key: str | None
    gemini_model: str
    gemini_chunk_size: int

    @staticmethod
    def from_env() -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
        max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "250"))
        use_hosted_apis = os.getenv("USE_HOSTED_APIS", "true").lower() == "true"
        api_key = os.getenv("API_KEY")
        whisperx_url = os.getenv(
            "WHISPERX_URL",
            "https://whisperx-ooz43fzexa-ue.a.run.app/transcribe",
        )
        demucs_url = os.getenv(
            "DEMUCS_URL",
            "https://demucs-ooz43fzexa-ue.a.run.app/separate",
        )
        request_timeout_s = int(os.getenv("REQUEST_TIMEOUT_S", "1800"))
        enable_gemini = os.getenv("ENABLE_GEMINI", "true").lower() == "true"
        gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        gemini_chunk_size = int(os.getenv("GEMINI_CHUNK_SIZE", "180"))
        return Settings(
            data_dir=data_dir,
            max_upload_mb=max_upload_mb,
            use_hosted_apis=use_hosted_apis,
            api_key=api_key,
            whisperx_url=whisperx_url,
            demucs_url=demucs_url,
            request_timeout_s=request_timeout_s,
            enable_gemini=enable_gemini,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            gemini_chunk_size=gemini_chunk_size,
        )


settings = Settings.from_env()
