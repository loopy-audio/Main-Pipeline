# Spatial Audio Pipeline API (Placeholder Integrations)

This service is the orchestration layer for your spatial audio pipeline.

Current scope:
- Accept audio uploads
- Persist local job files/artifacts
- Cache stage responses locally by input hash
- Run **placeholder** Demucs/WhisperX stages (no external calls yet)

## Endpoints
- `GET /healthz`
- `POST /jobs` (multipart: `file`, optional `language`)
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/artifact/{name}`

## Local run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## Example
```bash
curl -X POST "http://localhost:8080/jobs" \
  -F "file=@/path/to/song.wav" \
  -F "language=en"
```

## Local data layout
By default data is stored in `./data` (set `DATA_DIR` to override):
- `data/jobs/<job_id>/job.json`
- `data/jobs/<job_id>/demucs.json`
- `data/jobs/<job_id>/whisperx.json`
- `data/cache/responses/*.json`

## Env vars
- `DATA_DIR` (default: `./data`)
- `MAX_UPLOAD_MB` (default: `250`)

## Next integration step
Replace `DemucsPlaceholderClient` and `WhisperXPlaceholderClient` in `app/services/placeholders.py`
with HTTP clients to your hosted APIs while preserving cache keys/contracts.
