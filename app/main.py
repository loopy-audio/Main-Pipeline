from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.models import JobResponse
from app.services.pipeline import PipelineService
from app.services.storage import LocalStorage

app = FastAPI(title="Spatial Audio Pipeline", version="0.1.0")
storage = LocalStorage(settings.data_dir)
pipeline = PipelineService(storage)


@app.get("/health")
def healthz() -> dict:
    return {"ok": True}


@app.post("/jobs", response_model=JobResponse)
async def create_job(file: UploadFile = File(...), language: str | None = Form(default=None)) -> JobResponse:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds MAX_UPLOAD_MB={settings.max_upload_mb}.")

    return pipeline.process(filename=file.filename or "upload.bin", content=raw, language=language)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    try:
        return storage.load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/jobs/{job_id}/artifact/{name}")
def get_artifact(job_id: str, name: str):
    safe_name = Path(name).name
    path = storage.job_dir(job_id) / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path)
