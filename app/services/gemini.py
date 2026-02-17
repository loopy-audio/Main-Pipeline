from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from typing import Any

import requests


class GeminiLyricsClient:
    def __init__(self, api_key: str | None, model: str, timeout_s: int, chunk_size: int):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.chunk_size = max(20, chunk_size)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9_\-]*\\n", "", cleaned)
            cleaned = re.sub(r"\\n```$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def words_digest(words: list[dict[str, Any]]) -> str:
        blob = json.dumps(words, separators=(",", ":"), ensure_ascii=False)
        return sha256(blob.encode("utf-8")).hexdigest()

    def _deterministic_positions(self, words: list[dict[str, Any]], base_index: int) -> list[dict[str, Any]]:
        n = max(1, len(words))
        out: list[dict[str, Any]] = []
        for i, word_item in enumerate(words):
            frac = i / max(1, n - 1)
            angle = 2.0 * math.pi * frac
            x = round(math.cos(angle), 4)
            y = round(0.15 * math.sin(angle * 2.0), 4)
            z = round(math.sin(angle), 4)
            out.append(
                {
                    "index": base_index + i,
                    "word": word_item.get("word", ""),
                    "start": word_item.get("start"),
                    "end": word_item.get("end"),
                    "score": word_item.get("score"),
                    "position": {"x": x, "y": y, "z": z},
                    "confidence": 0.45,
                    "method": "deterministic-fallback",
                }
            )
        return out

    def _predict_chunk_with_gemini(
        self,
        words: list[dict[str, Any]],
        base_index: int,
        language: str | None,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured")

        compact_words = []
        for i, w in enumerate(words):
            compact_words.append(
                {
                    "index": base_index + i,
                    "word": w.get("word", ""),
                    "start": w.get("start"),
                    "end": w.get("end"),
                    "score": w.get("score"),
                }
            )

        prompt = {
            "task": "Predict 3D spatial position per lyric word for immersive audio.",
            "rules": [
                "Return valid JSON only.",
                "Include one output object for every input index.",
                "x,y,z must be floats in range [-1,1].",
                "confidence must be float in [0,1].",
                "Preserve the same index values.",
            ],
            "language": language,
            "input_words": compact_words,
            "output_schema": {
                "positions": [
                    {
                        "index": 0,
                        "x": 0.0,
                        "y": 0.0,
                        "z": 0.0,
                        "confidence": 0.8,
                    }
                ]
            },
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        body = {
            "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        resp = requests.post(url, params=params, json=body, timeout=self.timeout_s)
        resp.raise_for_status()

        payload = resp.json()
        text = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not text:
            raise ValueError("Gemini returned empty content")

        parsed = json.loads(self._strip_code_fences(text))
        rows = parsed.get("positions", []) if isinstance(parsed, dict) else []
        if not isinstance(rows, list) or not rows:
            raise ValueError("Gemini response missing positions list")

        by_index: dict[int, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            idx = row.get("index")
            if not isinstance(idx, int):
                continue
            x = self._clamp(float(row.get("x", 0.0)), -1.0, 1.0)
            y = self._clamp(float(row.get("y", 0.0)), -1.0, 1.0)
            z = self._clamp(float(row.get("z", 0.0)), -1.0, 1.0)
            confidence = self._clamp(float(row.get("confidence", 0.5)), 0.0, 1.0)
            by_index[idx] = {
                "index": idx,
                "position": {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)},
                "confidence": round(confidence, 4),
                "method": "gemini",
            }

        merged: list[dict[str, Any]] = []
        for i, original in enumerate(words):
            idx = base_index + i
            base = by_index.get(idx)
            if not base:
                # If Gemini misses any index, fill deterministically for that word.
                base = self._deterministic_positions([original], idx)[0]
            merged.append(
                {
                    "index": idx,
                    "word": original.get("word", ""),
                    "start": original.get("start"),
                    "end": original.get("end"),
                    "score": original.get("score"),
                    "position": base["position"],
                    "confidence": base.get("confidence", 0.5),
                    "method": base.get("method", "gemini"),
                }
            )
        return merged

    def predict_word_positions(self, words: list[dict[str, Any]], language: str | None = None) -> dict[str, Any]:
        if not words:
            return {
                "provider": "gemini-lyrics",
                "model": self.model,
                "language": language,
                "word_count": 0,
                "positions": [],
                "fallback_chunks": 0,
            }

        positions: list[dict[str, Any]] = []
        fallback_chunks = 0

        for start in range(0, len(words), self.chunk_size):
            chunk = words[start : start + self.chunk_size]
            try:
                chunk_positions = self._predict_chunk_with_gemini(chunk, start, language)
            except Exception:
                fallback_chunks += 1
                chunk_positions = self._deterministic_positions(chunk, start)
            positions.extend(chunk_positions)

        return {
            "provider": "gemini-lyrics",
            "model": self.model,
            "language": language,
            "word_count": len(words),
            "positions": positions,
            "fallback_chunks": fallback_chunks,
            "chunk_size": self.chunk_size,
        }
