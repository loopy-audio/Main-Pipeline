from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import JobResponse


class LocalStorage:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.uploads_dir = base_dir / "uploads"
        self.jobs_dir = base_dir / "jobs"
        self.cache_dir = base_dir / "cache"
        self.cache_responses_dir = self.cache_dir / "responses"
        self.cache_stems_dir = self.cache_dir / "stems"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.cache_responses_dir.mkdir(parents=True, exist_ok=True)
        self.cache_stems_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def cache_key(stage: str, input_sha256: str, params: dict[str, Any]) -> str:
        params_blob = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(params_blob.encode("utf-8")).hexdigest()
        return f"{stage}-{input_sha256}-{digest}"

    def create_job_dir(self) -> str:
        job_id = str(uuid4())
        (self.jobs_dir / job_id).mkdir(parents=True, exist_ok=False)
        return job_id

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def save_upload(self, job_id: str, filename: str, content: bytes) -> Path:
        safe_name = Path(filename).name
        dst = self.job_dir(job_id) / safe_name
        dst.write_bytes(content)
        return dst

    def save_job(self, job: JobResponse) -> Path:
        path = self.job_dir(job.job_id) / "job.json"
        path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_job(self, job_id: str) -> JobResponse:
        path = self.job_dir(job_id) / "job.json"
        raw = path.read_text(encoding="utf-8")
        return JobResponse.model_validate_json(raw)

    def save_job_artifact_json(self, job_id: str, name: str, payload: dict[str, Any]) -> Path:
        dst = self.job_dir(job_id) / name
        dst.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return dst

    def save_job_artifact_bytes(self, job_id: str, name: str, payload: bytes) -> Path:
        dst = self.job_dir(job_id) / Path(name).name
        dst.write_bytes(payload)
        return dst

    def cache_get(self, key: str) -> dict[str, Any] | None:
        path = self.cache_responses_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def cache_set(self, key: str, payload: dict[str, Any]) -> Path:
        path = self.cache_responses_dir / f"{key}.json"
        envelope = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        return path

    def stems_cache_dir(self, key: str) -> Path:
        path = self.cache_stems_dir / key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_stems_zip_set(self, key: str, payload: bytes) -> Path:
        path = self.stems_cache_dir(key) / "stems.zip"
        path.write_bytes(payload)
        return path

    def cache_stems_zip_get(self, key: str) -> Path | None:
        path = self.cache_stems_dir / key / "stems.zip"
        if not path.exists():
            return None
        return path

    def cache_stems_vocals_get(self, key: str) -> Path | None:
        dir_path = self.cache_stems_dir / key
        if not dir_path.exists():
            return None
        for item in sorted(dir_path.iterdir()):
            if item.is_file() and item.stem.lower() == "vocals":
                return item
        return None

    def cache_stems_vocals_set(self, key: str, source: Path) -> Path:
        ext = source.suffix or ".wav"
        dst = self.stems_cache_dir(key) / f"vocals{ext}"
        shutil.copyfile(source, dst)
        return dst

    def copy_to_job_artifact(self, job_id: str, source: Path, artifact_name: str | None = None) -> Path:
        safe_name = Path(artifact_name).name if artifact_name else source.name
        dst = self.job_dir(job_id) / safe_name
        shutil.copyfile(source, dst)
        return dst

    def list_artifacts(self, job_id: str) -> list[str]:
        files = []
        for item in sorted(self.job_dir(job_id).iterdir()):
            if item.is_file() and item.name != "job.json":
                files.append(item.name)
        return files
