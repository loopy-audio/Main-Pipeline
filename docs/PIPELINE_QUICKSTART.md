# Spatial Pipeline Quickstart

## 1) Set env
Create `.env` with:

```bash
API_KEY=...                         # Demucs + WhisperX
USE_HOSTED_APIS=true
DEMUCS_URL=https://demucs-.../separate
WHISPERX_URL=https://whisperx-.../transcribe
ENABLE_GEMINI=true
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-flash-latest
```

## 2) Start API
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
set -a; source .env; set +a
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## 3) Run one song
```bash
curl -X POST "http://localhost:8080/jobs" \
  -F "file=@song.mp3;type=audio/mpeg" \
  -F "language=en"
```

## 4) Check output files
For returned `job_id`:

- `data/jobs/<job_id>/demucs.json`
- `data/jobs/<job_id>/stems.zip`
- `data/jobs/<job_id>/vocals.mp3`
- `data/jobs/<job_id>/whisperx.json`
- `data/jobs/<job_id>/gemini_positions.json`

## 5) Check cache reuse
Run the same file again and confirm stage cache hits in job response:

- `demucs: true`
- `whisperx: true`
- `gemini_lyrics: true`

Cache locations:

- `data/cache/stems/<key>/stems.zip`
- `data/cache/stems/<key>/vocals.*`
- `data/cache/responses/*.json`
