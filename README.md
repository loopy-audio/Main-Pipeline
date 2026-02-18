# Spatial Audio Pipeline API

Short operator guide: `/Users/columbus/Development/IDPRO/main_pipeline/docs/PIPELINE_QUICKSTART.md`

This service orchestrates your hosted audio services:
- Demucs API (`/separate`) for stems
- WhisperX API (`/transcribe`) for transcript + timestamps
- Gemini API for per-word 3D position prediction

It also stores local artifacts and caches API responses on disk for faster re-runs.

## Endpoints
- `GET /health`
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

## Data layout
Default root is `./data` (override with `DATA_DIR`):
- `data/jobs/<job_id>/job.json`
- `data/jobs/<job_id>/stems.zip` (when live Demucs runs)
- `data/jobs/<job_id>/vocals.*` (extracted from zip)
- `data/jobs/<job_id>/demucs.json`
- `data/jobs/<job_id>/whisperx.json`
- `data/jobs/<job_id>/gemini_positions.json`
- `data/cache/responses/*.json`
- `data/cache/stems/<cache_key>/stems.zip`
- `data/cache/stems/<cache_key>/vocals.*`

## Environment variables
- `DATA_DIR` (default: `./data`)
- `MAX_UPLOAD_MB` (default: `250`)
- `USE_HOSTED_APIS` (`true` or `false`, default: `true`)
- `API_KEY` (required when `USE_HOSTED_APIS=true`)
- `DEMUCS_URL` (default: hosted Cloud Run `/separate`)
- `WHISPERX_URL` (default: hosted Cloud Run `/transcribe`)
- `REQUEST_TIMEOUT_S` (default: `1800`)
- `ENABLE_GEMINI` (`true` or `false`, default: `true`)
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`, optional; fallback positions are used if absent)
- `GEMINI_MODEL` (default: `gemini-1.5-flash`)
- `GEMINI_CHUNK_SIZE` (default: `60`)
- `GEMINI_CONTEXT_WORDS` (default: `12`)

## Behavior notes
- Demucs output is cached under `data/cache/stems` and reused by input hash.
- WhisperX JSON is cached by input hash + language.
- Gemini word-position JSON is cached by input hash + transcript words hash + model.
- `gemini_positions.json` includes `ambisonic_effects` entries that map directly to `Speaker.add_effect`.
- Gemini predicts angles in PI units (`position_pi`) and also provides radians (`position_rad`) for rendering.
- If hosted APIs are disabled, placeholder clients are used.
- Vocals extraction is resilient to `vocals` or `voice` stem naming in ZIP content.
