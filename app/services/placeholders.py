from __future__ import annotations

from pathlib import Path


class DemucsPlaceholderClient:
    def separate(self, audio_file: Path) -> dict:
        # Placeholder contract for future hosted Demucs API call.
        return {
            "provider": "demucs-placeholder",
            "input": str(audio_file),
            "stems": [
                {"name": "vocals", "uri": None},
                {"name": "drums", "uri": None},
                {"name": "bass", "uri": None},
                {"name": "other", "uri": None},
            ],
        }


class WhisperXPlaceholderClient:
    def transcribe(self, vocals_reference: dict, language: str | None = None) -> dict:
        # Placeholder contract for future hosted WhisperX API call.
        return {
            "provider": "whisperx-placeholder",
            "language": language or "unknown",
            "model": "large-v3",
            "text": "",
            "segments": [],
            "words": [],
            "input": vocals_reference,
        }
