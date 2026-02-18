from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from typing import Any

import requests


class GeminiLyricsClient:
    def __init__(self, api_key: str | None, model: str, timeout_s: int, chunk_size: int, context_words: int):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.chunk_size = max(12, chunk_size)
        self.context_words = max(0, context_words)

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

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_time(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _normalize_azimuth_pi(self, value: float) -> float:
        return value % 2.0

    def _normalize_elevation_pi(self, value: float) -> float:
        return self._clamp(value, 0.0, 1.0)

    @staticmethod
    def _pi_to_radians(value_pi: float) -> float:
        return value_pi * math.pi

    def _pi_triplet_to_rad(self, position_pi: dict[str, Any]) -> dict[str, float]:
        azimuth_pi = self._normalize_azimuth_pi(self._coerce_float(position_pi.get("azimuth_pi"), 0.0))
        elevation_pi = self._normalize_elevation_pi(self._coerce_float(position_pi.get("elevation_pi"), 0.5))
        distance = self._clamp(self._coerce_float(position_pi.get("distance"), 1.0), 0.25, 3.0)
        return {
            "azimuth": round(self._pi_to_radians(azimuth_pi), 6),
            "elevation": round(self._pi_to_radians(elevation_pi), 6),
            "distance": round(distance, 6),
        }

    @staticmethod
    def _rad_to_xyz(position_rad: dict[str, Any]) -> dict[str, float]:
        azimuth = float(position_rad.get("azimuth", 0.0))
        elevation = float(position_rad.get("elevation", math.pi / 2.0))
        distance = float(position_rad.get("distance", 1.0))

        horizontal = distance * math.sin(elevation)
        y = distance * math.cos(elevation)
        x = horizontal * math.cos(azimuth)
        z = horizontal * math.sin(azimuth)
        return {
            "x": round(x, 4),
            "y": round(y, 4),
            "z": round(z, 4),
        }

    def _deterministic_pi_position(self, index: int, total_words: int) -> dict[str, float]:
        frac = index / max(1, total_words - 1)
        azimuth_pi = self._normalize_azimuth_pi(2.0 * frac)
        elevation_pi = self._normalize_elevation_pi(0.5 + 0.18 * math.sin(2.0 * math.pi * frac))
        distance = self._clamp(1.0 + 0.2 * math.sin(4.0 * math.pi * frac), 0.45, 2.5)
        return {
            "azimuth_pi": round(azimuth_pi, 4),
            "elevation_pi": round(elevation_pi, 4),
            "distance": round(distance, 4),
        }

    def _build_word_row(
        self,
        word_item: dict[str, Any],
        index: int,
        position_pi: dict[str, Any],
        confidence: float,
        method: str,
    ) -> dict[str, Any]:
        normalized_pi = {
            "azimuth_pi": round(self._normalize_azimuth_pi(self._coerce_float(position_pi.get("azimuth_pi"), 0.0)), 4),
            "elevation_pi": round(
                self._normalize_elevation_pi(self._coerce_float(position_pi.get("elevation_pi"), 0.5)), 4
            ),
            "distance": round(self._clamp(self._coerce_float(position_pi.get("distance"), 1.0), 0.25, 3.0), 4),
        }
        position_rad = self._pi_triplet_to_rad(normalized_pi)
        position_xyz = self._rad_to_xyz(position_rad)

        return {
            "index": index,
            "word": word_item.get("word", ""),
            "start": word_item.get("start"),
            "end": word_item.get("end"),
            "score": word_item.get("score"),
            "position_pi": normalized_pi,
            "position_rad": position_rad,
            "position_xyz": position_xyz,
            "confidence": round(self._clamp(confidence, 0.0, 1.0), 4),
            "method": method,
        }

    def _build_ambisonic_effects(self, positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        effects: list[dict[str, Any]] = []
        prev_end = 0.0

        for i, row in enumerate(positions):
            start_t = self._coerce_time(row.get("start"), prev_end)
            end_t = self._coerce_time(row.get("end"), start_t + 0.08)
            if end_t <= start_t:
                end_t = start_t + 0.05

            current_pi = row.get("position_pi", {"azimuth_pi": 0.0, "elevation_pi": 0.5, "distance": 1.0})
            current_rad = row.get("position_rad", self._pi_triplet_to_rad(current_pi))

            if i + 1 < len(positions):
                next_row = positions[i + 1]
                next_pi = next_row.get("position_pi", current_pi)
                next_rad = next_row.get("position_rad", self._pi_triplet_to_rad(next_pi))
            else:
                next_pi = current_pi
                next_rad = current_rad

            effects.append(
                {
                    "time_range": [round(start_t, 6), round(end_t, 6)],
                    "effect": {
                        "type": "move",
                        "start": [current_rad["azimuth"], current_rad["elevation"], current_rad["distance"]],
                        "end": [next_rad["azimuth"], next_rad["elevation"], next_rad["distance"]],
                    },
                    "effect_pi": {
                        "type": "move",
                        "start_pi": [
                            current_pi["azimuth_pi"],
                            current_pi["elevation_pi"],
                            current_pi["distance"],
                        ],
                        "end_pi": [
                            next_pi["azimuth_pi"],
                            next_pi["elevation_pi"],
                            next_pi["distance"],
                        ],
                    },
                    "meta": {
                        "index": row.get("index"),
                        "word": row.get("word", ""),
                        "confidence": row.get("confidence", 0.5),
                        "method": row.get("method", "gemini"),
                    },
                }
            )
            prev_end = end_t

        return effects

    def _predict_chunk_with_gemini(
        self,
        target_words: list[dict[str, Any]],
        base_index: int,
        total_words: int,
        language: str | None,
        context_before: list[dict[str, Any]],
        context_after: list[dict[str, Any]],
        previous_anchor_pi: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured")

        compact_target = []
        for i, w in enumerate(target_words):
            compact_target.append(
                {
                    "index": base_index + i,
                    "word": w.get("word", ""),
                    "start": w.get("start"),
                    "end": w.get("end"),
                    "score": w.get("score"),
                }
            )

        compact_before = []
        before_start_idx = base_index - len(context_before)
        for i, w in enumerate(context_before):
            compact_before.append(
                {
                    "index": before_start_idx + i,
                    "word": w.get("word", ""),
                    "start": w.get("start"),
                    "end": w.get("end"),
                }
            )

        compact_after = []
        after_start_idx = base_index + len(target_words)
        for i, w in enumerate(context_after):
            compact_after.append(
                {
                    "index": after_start_idx + i,
                    "word": w.get("word", ""),
                    "start": w.get("start"),
                    "end": w.get("end"),
                }
            )

        prompt = {
            "task": "Predict ambisonic lyric positions in PI units for target words only.",
            "rules": [
                "Return valid JSON only.",
                "Return one position object per TARGET index and no extra indices.",
                "Use PI units for angles: azimuth_pi in [0,2), elevation_pi in [0,1].",
                "distance must be in [0.25,3.0].",
                "confidence must be in [0,1].",
                "Use context_before/context_after only for continuity.",
            ],
            "language": language,
            "chunk_strategy": {
                "target_size": len(compact_target),
                "context_before_size": len(compact_before),
                "context_after_size": len(compact_after),
                "total_words": total_words,
            },
            "previous_anchor_pi": previous_anchor_pi,
            "context_before": compact_before,
            "target_words": compact_target,
            "context_after": compact_after,
            "output_schema": {
                "positions": [
                    {
                        "index": 0,
                        "azimuth_pi": 0.5,
                        "elevation_pi": 0.5,
                        "distance": 1.0,
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
                "temperature": 0.15,
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
            by_index[idx] = {
                "azimuth_pi": self._normalize_azimuth_pi(self._coerce_float(row.get("azimuth_pi"), 0.0)),
                "elevation_pi": self._normalize_elevation_pi(self._coerce_float(row.get("elevation_pi"), 0.5)),
                "distance": self._clamp(self._coerce_float(row.get("distance"), 1.0), 0.25, 3.0),
                "confidence": self._clamp(self._coerce_float(row.get("confidence"), 0.5), 0.0, 1.0),
            }

        merged: list[dict[str, Any]] = []
        for i, original in enumerate(target_words):
            idx = base_index + i
            base = by_index.get(idx)
            if not base:
                pi_position = self._deterministic_pi_position(idx, total_words)
                merged.append(
                    self._build_word_row(
                        word_item=original,
                        index=idx,
                        position_pi=pi_position,
                        confidence=0.45,
                        method="deterministic-fallback",
                    )
                )
                continue

            merged.append(
                self._build_word_row(
                    word_item=original,
                    index=idx,
                    position_pi={
                        "azimuth_pi": base["azimuth_pi"],
                        "elevation_pi": base["elevation_pi"],
                        "distance": base["distance"],
                    },
                    confidence=base["confidence"],
                    method="gemini",
                )
            )

        return merged

    def _build_fallback_chunk(
        self,
        words: list[dict[str, Any]],
        base_index: int,
        total_words: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for i, word_item in enumerate(words):
            idx = base_index + i
            pi_position = self._deterministic_pi_position(idx, total_words)
            rows.append(
                self._build_word_row(
                    word_item=word_item,
                    index=idx,
                    position_pi=pi_position,
                    confidence=0.45,
                    method="deterministic-fallback",
                )
            )
        return rows

    def predict_word_positions(self, words: list[dict[str, Any]], language: str | None = None) -> dict[str, Any]:
        if not words:
            return {
                "provider": "gemini-lyrics",
                "model": self.model,
                "language": language,
                "word_count": 0,
                "positions": [],
                "ambisonic_effects": [],
                "fallback_chunks": 0,
                "chunk_size": self.chunk_size,
                "context_words": self.context_words,
            }

        positions: list[dict[str, Any]] = []
        fallback_chunks = 0
        total_words = len(words)

        for start in range(0, total_words, self.chunk_size):
            end = min(start + self.chunk_size, total_words)
            chunk = words[start:end]
            ctx_start = max(0, start - self.context_words)
            ctx_end = min(total_words, end + self.context_words)
            context_before = words[ctx_start:start]
            context_after = words[end:ctx_end]
            previous_anchor_pi = [
                {
                    "index": row["index"],
                    "azimuth_pi": row["position_pi"]["azimuth_pi"],
                    "elevation_pi": row["position_pi"]["elevation_pi"],
                    "distance": row["position_pi"]["distance"],
                }
                for row in positions[-4:]
            ]

            try:
                chunk_positions = self._predict_chunk_with_gemini(
                    target_words=chunk,
                    base_index=start,
                    total_words=total_words,
                    language=language,
                    context_before=context_before,
                    context_after=context_after,
                    previous_anchor_pi=previous_anchor_pi,
                )
            except Exception:
                fallback_chunks += 1
                chunk_positions = self._build_fallback_chunk(chunk, start, total_words)

            positions.extend(chunk_positions)

        ambisonic_effects = self._build_ambisonic_effects(positions)

        return {
            "provider": "gemini-lyrics",
            "model": self.model,
            "language": language,
            "word_count": len(words),
            "positions": positions,
            "ambisonic_effects": ambisonic_effects,
            "ambisonic_format": {
                "api": "Speaker.add_effect((start_time, end_time), effect)",
                "effect_schema": {
                    "type": "move",
                    "start": [0.0, 1.570796, 1.0],
                    "end": [1.57, 1.57, 1.0],
                },
                "angle_units": {
                    "pi_fields": ["position_pi.azimuth_pi", "position_pi.elevation_pi"],
                    "radian_fields": ["position_rad.azimuth", "position_rad.elevation", "effect.start/end[0:2]"],
                },
                "distance_units": "relative",
            },
            "fallback_chunks": fallback_chunks,
            "chunk_size": self.chunk_size,
            "context_words": self.context_words,
        }
