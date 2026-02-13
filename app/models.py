from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["completed", "failed"]


class StageResult(BaseModel):
    stage: str
    cache_hit: bool
    payload: dict[str, Any]


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    input_file: str
    input_sha256: str
    language: str | None = None
    stages: list[StageResult] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
