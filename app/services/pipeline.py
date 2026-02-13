from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models import JobResponse, StageResult
from app.services.placeholders import DemucsPlaceholderClient, WhisperXPlaceholderClient
from app.services.storage import LocalStorage


class PipelineService:
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.demucs = DemucsPlaceholderClient()
        self.whisperx = WhisperXPlaceholderClient()

    def process(self, filename: str, content: bytes, language: str | None = None) -> JobResponse:
        job_id = self.storage.create_job_dir()
        created_at = datetime.now(timezone.utc)
        input_sha256 = self.storage.sha256_bytes(content)
        upload_path = self.storage.save_upload(job_id, filename, content)

        stages: list[StageResult] = []

        demucs_params = {"version": "v1-placeholder"}
        demucs_key = self.storage.cache_key("demucs", input_sha256, demucs_params)
        demucs_cached = self.storage.cache_get(demucs_key)
        if demucs_cached:
            demucs_payload = demucs_cached["payload"]
            demucs_hit = True
        else:
            demucs_payload = self.demucs.separate(upload_path)
            self.storage.cache_set(demucs_key, demucs_payload)
            demucs_hit = False
        stages.append(StageResult(stage="demucs", cache_hit=demucs_hit, payload=demucs_payload))

        vocals_ref = next((s for s in demucs_payload.get("stems", []) if s.get("name") == "vocals"), {})

        whisperx_params = {"version": "v1-placeholder", "language": language}
        whisperx_key = self.storage.cache_key("whisperx", input_sha256, whisperx_params)
        whisperx_cached = self.storage.cache_get(whisperx_key)
        if whisperx_cached:
            whisperx_payload = whisperx_cached["payload"]
            whisperx_hit = True
        else:
            whisperx_payload = self.whisperx.transcribe(vocals_ref, language=language)
            self.storage.cache_set(whisperx_key, whisperx_payload)
            whisperx_hit = False
        stages.append(StageResult(stage="whisperx", cache_hit=whisperx_hit, payload=whisperx_payload))

        self.storage.save_job_artifact_json(job_id, "demucs.json", demucs_payload)
        self.storage.save_job_artifact_json(job_id, "whisperx.json", whisperx_payload)

        job = JobResponse(
            job_id=job_id,
            status="completed",
            created_at=created_at,
            input_file=Path(filename).name,
            input_sha256=input_sha256,
            language=language,
            stages=stages,
            output_artifacts=self.storage.list_artifacts(job_id),
            error=None,
        )
        self.storage.save_job(job)
        return job
