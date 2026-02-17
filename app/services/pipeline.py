from __future__ import annotations

import copy
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import JobResponse, StageResult
from app.services.gemini import GeminiLyricsClient
from app.services.placeholders import (
    DemucsHostedClient,
    DemucsPlaceholderClient,
    WhisperXHostedClient,
    WhisperXPlaceholderClient,
)
from app.services.storage import LocalStorage


class PipelineService:
    def __init__(self, storage: LocalStorage):
        self.storage = storage

        if settings.use_hosted_apis:
            if not settings.api_key:
                raise ValueError("API_KEY must be set when USE_HOSTED_APIS=true")
            self.demucs = DemucsHostedClient(settings.demucs_url, settings.api_key, settings.request_timeout_s)
            self.whisperx = WhisperXHostedClient(settings.whisperx_url, settings.api_key, settings.request_timeout_s)
        else:
            self.demucs = DemucsPlaceholderClient()
            self.whisperx = WhisperXPlaceholderClient()
            self.gemini = GeminiLyricsClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_s=settings.request_timeout_s,
            chunk_size=settings.gemini_chunk_size,
        )

    def _save_job(
        self,
        job_id: str,
        created_at: datetime,
        filename: str,
        input_sha256: str,
        language: str | None,
        stages: list[StageResult],
        error: str | None,
    ) -> JobResponse:
        status = "failed" if error else "completed"
        job = JobResponse(
            job_id=job_id,
            status=status,
            created_at=created_at,
            input_file=Path(filename).name,
            input_sha256=input_sha256,
            language=language,
            stages=stages,
            output_artifacts=self.storage.list_artifacts(job_id),
            error=error,
        )
        self.storage.save_job(job)
        return job

    def _extract_vocals_from_zip(self, zip_path: Path, target_dir: Path) -> tuple[Path, list[str]]:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [name for name in zf.namelist() if not name.endswith("/")]
            vocals_name = next((n for n in names if "vocals" in n.lower()), None)
            if not vocals_name:
                vocals_name = next((n for n in names if "voice" in n.lower()), None)
            if not vocals_name:
                raise ValueError("No vocals stem found in Demucs ZIP output")
            data = zf.read(vocals_name)
            ext = Path(vocals_name).suffix or ".wav"
            out = target_dir / f"vocals{ext}"
            out.write_bytes(data)
            return out, names

    def _run_demucs_stage(
        self,
        job_id: str,
        input_sha256: str,
        upload_path: Path,
    ) -> tuple[dict[str, Any], bool, Path]:
        demucs_params = {
            "version": "v2-live" if settings.use_hosted_apis else "v1-placeholder",
            "url": settings.demucs_url if settings.use_hosted_apis else "placeholder",
        }
        demucs_key = self.storage.cache_key("demucs", input_sha256, demucs_params)
        demucs_cached = self.storage.cache_get(demucs_key)
        demucs_zip_cached_path = self.storage.cache_stems_zip_get(demucs_key)
        demucs_vocals_cached_path = self.storage.cache_stems_vocals_get(demucs_key)

        if demucs_cached and demucs_zip_cached_path:
            demucs_payload = copy.deepcopy(demucs_cached["payload"])
            demucs_hit = True
        else:
            demucs_payload, demucs_zip_bytes = self.demucs.separate(upload_path)
            self.storage.cache_set(demucs_key, demucs_payload)
            if demucs_zip_bytes is not None:
                demucs_zip_cached_path = self.storage.cache_stems_zip_set(demucs_key, demucs_zip_bytes)
            demucs_hit = False

        vocals_file = upload_path
        if demucs_zip_cached_path:
            stems_zip_path = self.storage.copy_to_job_artifact(job_id, demucs_zip_cached_path, "stems.zip")
            if demucs_vocals_cached_path:
                vocals_file = self.storage.copy_to_job_artifact(job_id, demucs_vocals_cached_path)
                with zipfile.ZipFile(stems_zip_path, "r") as zf:
                    zip_members = [name for name in zf.namelist() if not name.endswith("/")]
            else:
                vocals_file, zip_members = self._extract_vocals_from_zip(stems_zip_path, self.storage.job_dir(job_id))
                self.storage.cache_stems_vocals_set(demucs_key, vocals_file)
            demucs_payload["zip_members"] = zip_members
            demucs_payload["vocals_file"] = vocals_file.name

        self.storage.save_job_artifact_json(job_id, "demucs.json", demucs_payload)
        return demucs_payload, demucs_hit, vocals_file

    def _run_whisperx_stage(
        self,
        job_id: str,
        input_sha256: str,
        vocals_file: Path,
        language: str | None,
    ) -> tuple[dict[str, Any], bool]:
        whisperx_params = {
            "version": "v2-live" if settings.use_hosted_apis else "v1-placeholder",
            "url": settings.whisperx_url if settings.use_hosted_apis else "placeholder",
            "language": language,
        }
        whisperx_key = self.storage.cache_key("whisperx", input_sha256, whisperx_params)
        whisperx_cached = self.storage.cache_get(whisperx_key)
        if whisperx_cached:
            whisperx_payload = whisperx_cached["payload"]
            whisperx_hit = True
        else:
            whisperx_payload = self.whisperx.transcribe(vocals_file, language=language)
            self.storage.cache_set(whisperx_key, whisperx_payload)
            whisperx_hit = False

        self.storage.save_job_artifact_json(job_id, "whisperx.json", whisperx_payload)
        return whisperx_payload, whisperx_hit

    def _run_gemini_stage(
        self,
        job_id: str,
        input_sha256: str,
        whisperx_payload: dict[str, Any],
        language: str | None,
    ) -> tuple[dict[str, Any], bool]:
        words = whisperx_payload.get("words", [])
        words_sha = GeminiLyricsClient.words_digest(words)
        gemini_params = {
            "version": "v1-gemini-lyrics",
            "model": settings.gemini_model,
            "language": language,
            "words_sha256": words_sha,
        }
        gemini_key = self.storage.cache_key("gemini_positions", input_sha256, gemini_params)
        gemini_cached = self.storage.cache_get(gemini_key)
        if gemini_cached:
            gemini_payload = gemini_cached["payload"]
            gemini_hit = True
        else:
            gemini_payload = self.gemini.predict_word_positions(words=words, language=language)
            self.storage.cache_set(gemini_key, gemini_payload)
            gemini_hit = False

        self.storage.save_job_artifact_json(job_id, "gemini_positions.json", gemini_payload)
        return gemini_payload, gemini_hit

    def process(self, filename: str, content: bytes, language: str | None = None) -> JobResponse:
        job_id = self.storage.create_job_dir()
        created_at = datetime.now(timezone.utc)
        input_sha256 = self.storage.sha256_bytes(content)
        upload_path = self.storage.save_upload(job_id, filename, content)

        stages: list[StageResult] = []

        try:
            demucs_payload, demucs_hit, vocals_file = self._run_demucs_stage(job_id, input_sha256, upload_path)
            stages.append(StageResult(stage="demucs", cache_hit=demucs_hit, payload=demucs_payload))

            whisperx_payload, whisperx_hit = self._run_whisperx_stage(job_id, input_sha256, vocals_file, language)
            stages.append(StageResult(stage="whisperx", cache_hit=whisperx_hit, payload=whisperx_payload))

            if settings.enable_gemini:
                gemini_payload, gemini_hit = self._run_gemini_stage(job_id, input_sha256, whisperx_payload, language)
                stages.append(StageResult(stage="gemini_lyrics", cache_hit=gemini_hit, payload=gemini_payload))
            return self._save_job(
                job_id=job_id,
                created_at=created_at,
                filename=filename,
                input_sha256=input_sha256,
                language=language,
                stages=stages,
                error=None,
            )

        except Exception as exc:
            return self._save_job(
                job_id=job_id,
                created_at=created_at,
                filename=filename,
                input_sha256=input_sha256,
                language=language,
                stages=stages,
                error=str(exc),
            )
