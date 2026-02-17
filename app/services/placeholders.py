from __future__ import annotations

import mimetypes
from pathlib import Path

import requests


def _audio_content_type(audio_file: Path) -> str:
    guessed, _ = mimetypes.guess_type(audio_file.name)
    if guessed and guessed.startswith("audio/"):
        return guessed

    ext = audio_file.suffix.lower()
    if ext == ".wav":
        return "audio/wav"
    if ext == ".mp3":
        return "audio/mpeg"
    if ext == ".flac":
        return "audio/flac"
    if ext in {".m4a", ".mp4"}:
        return "audio/mp4"
    if ext == ".ogg":
        return "audio/ogg"
    return "audio/wav"


class DemucsPlaceholderClient:
    def separate(self, audio_file: Path) -> tuple[dict, bytes | None]:
        # Offline placeholder for local development without hosted APIs.
        payload = {
            "provider": "demucs-placeholder",
            "input": str(audio_file),
            "stems": [
                {"name": "vocals", "uri": None},
                {"name": "drums", "uri": None},
                {"name": "bass", "uri": None},
                {"name": "other", "uri": None},
            ],
        }
        return payload, None


class WhisperXPlaceholderClient:
    def transcribe(self, vocals_file: Path, language: str | None = None) -> dict:
        # Offline placeholder for local development without hosted APIs.
        return {
            "provider": "whisperx-placeholder",
            "language": language or "unknown",
            "model": "large-v3",
            "text": "",
            "segments": [],
            "words": [],
            "input": str(vocals_file),
        }


class DemucsHostedClient:
    def __init__(self, url: str, api_key: str, timeout_s: int):
        self.url = url
        self.api_key = api_key
        self.timeout_s = timeout_s

    def separate(self, audio_file: Path) -> tuple[dict, bytes]:
        headers = {"X-API-Key": self.api_key}
        content_type = _audio_content_type(audio_file)
        with audio_file.open("rb") as fh:
            files = {"file": (audio_file.name, fh, content_type)}
            resp = requests.post(self.url, headers=headers, files=files, timeout=self.timeout_s)
        resp.raise_for_status()

        zip_bytes = resp.content
        payload = {
            "provider": "demucs-cloud-run",
            "url": self.url,
            "status_code": resp.status_code,
            "zip_size_bytes": len(zip_bytes),
            "content_type": resp.headers.get("content-type"),
        }
        return payload, zip_bytes


class WhisperXHostedClient:
    def __init__(self, url: str, api_key: str, timeout_s: int):
        self.url = url
        self.api_key = api_key
        self.timeout_s = timeout_s

    def transcribe(self, vocals_file: Path, language: str | None = None) -> dict:
        headers = {"X-API-Key": self.api_key}
        params = {}
        if language:
            params["language"] = language

        content_type = _audio_content_type(vocals_file)
        with vocals_file.open("rb") as fh:
            files = {"file": (vocals_file.name, fh, content_type)}
            resp = requests.post(
                self.url,
                headers=headers,
                params=params,
                files=files,
                timeout=self.timeout_s,
            )
        resp.raise_for_status()

        data = resp.json()
        data["provider"] = "whisperx-cloud-run"
        data["url"] = self.url
        return data
