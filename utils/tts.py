from __future__ import annotations
"""TTS adapters and orchestration for JP/EN audio synthesis."""

from dataclasses import dataclass
import base64
import hashlib
import io
import json
from tempfile import NamedTemporaryFile
import subprocess
import wave
import numpy as np
from typing import TYPE_CHECKING

from app.config import (
    ESPEAK_BIN, ESPEAK_EN_VOICE, TTS_TIMEOUT_MS,
    TTS_JP_HALF_TONE_DEFAULT, TTS_JP_SPEED_DEFAULT,
)
from utils.process_data import sep_mora_get_audio_mapping
from utils.storage import get_file_from_minio_as_stream, storage_object_exists, upload_file_to_minio

if TYPE_CHECKING:
    from utils.db import DBHandling
    import redis.asyncio as aioredis

try:
    import pyopenjtalk
except Exception:
    pyopenjtalk = None


@dataclass
class TTSAudio:
    """Unified TTS output payload across all engines."""

    wav_bytes: bytes
    sample_rate: int
    engine: str
    source: str = "generated"
    object_name: str = ""


class TTSAdapterError(RuntimeError):
    """Raised when a TTS engine cannot synthesize audio."""


def _pcm_to_wav_bytes(pcm_input, sample_rate: int) -> bytes:
    """Convert mono PCM (float/int) into WAV bytes as int16."""
    pcm = np.asarray(pcm_input)
    if pcm.ndim != 1:
        pcm = pcm.reshape(-1)

    if np.issubdtype(pcm.dtype, np.floating):
        # pyopenjtalk may return float64; support both [-1, 1] and int-like float ranges.
        max_abs = float(np.max(np.abs(pcm))) if pcm.size else 0.0
        if max_abs <= 1.0:
            pcm = pcm * 32767.0

    pcm = np.clip(pcm, -32768, 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


class JPAdapterPyOpenJTalk:
    """Japanese synthesis adapter implemented with pyopenjtalk-plus."""

    engine_name = "pyopenjtalk-plus"

    def __init__(self, speed_default: float = TTS_JP_SPEED_DEFAULT, half_tone_default: float = TTS_JP_HALF_TONE_DEFAULT):
        """Configure default JP synthesis voice controls."""
        self.speed_default = speed_default
        self.half_tone_default = half_tone_default

    def synthesize(self, text: str, speed: float = None, half_tone: float = None) -> TTSAudio:
        """Synthesize Japanese text into WAV bytes."""
        if pyopenjtalk is None:
            raise TTSAdapterError("pyopenjtalk is not available")

        speed = self.speed_default if speed is None else float(speed)
        half_tone = self.half_tone_default if half_tone is None else float(half_tone)

        try:
            pcm, sample_rate = pyopenjtalk.tts(text, speed=speed, half_tone=half_tone)
        except Exception as exc:
            raise TTSAdapterError(f"JP synthesis failed: {exc}") from exc

        wav_bytes = _pcm_to_wav_bytes(pcm, int(sample_rate))
        return TTSAudio(wav_bytes=wav_bytes, sample_rate=int(sample_rate), engine=self.engine_name)


class ENAdapterESpeakCLI:
    """eSpeak NG is a separated model installed on this machine,
    use subprocess to call it."""
    engine_name = "espeak-ng"

    def __init__(self, command: str = ESPEAK_BIN, voice: str = ESPEAK_EN_VOICE, timeout_ms: int = TTS_TIMEOUT_MS):
        """Configure command, voice, and timeout for eSpeak synthesis."""
        self.command = command
        self.voice = voice
        self.timeout_sec = max(1, int(timeout_ms)) / 1000

    def synthesize(self, text: str) -> TTSAudio:
        """Synthesize English text by invoking eSpeak NG executable."""
        with NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            cmd = [self.command, "-v", self.voice, "-w", tmp.name, text]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                )
            except FileNotFoundError as exc:
                raise TTSAdapterError(f"eSpeak command not found: {self.command}") from exc
            except subprocess.TimeoutExpired as exc:
                raise TTSAdapterError("eSpeak synthesis timeout") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or str(exc)).strip()
                raise TTSAdapterError(f"eSpeak synthesis failed: {detail}") from exc

            tmp.seek(0)
            wav_bytes = tmp.read()

        return TTSAudio(wav_bytes=wav_bytes, sample_rate=22050, engine=self.engine_name)


class TTSService:
    """Language router over TTS adapters with one unified return type."""

    def __init__(self):
        """Initialize language-specific adapters."""
        self.jp_adapter = JPAdapterPyOpenJTalk()
        self.en_adapter = ENAdapterESpeakCLI()
        self.redis_ttl_sec = 60 * 60 * 24

    @staticmethod
    def _cache_object_name(text: str, lang: str, engine: str, voice_options: dict | None = None) -> str:
        """Return object name for MinIO/S3 caching of generated audio."""
        options_str = ""
        if voice_options:
            options_str = json.dumps(voice_options, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        key = f"v1:{engine}:{lang}:{text}:{options_str}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()
        return f"audio/tts/{lang}/{engine}/{digest}.wav"

    @staticmethod
    def _redis_cache_key(object_name: str) -> str:
        """Return Redis key for an object-storage audio cache path."""
        return f"cache:tts:{object_name}"

    @staticmethod
    def _encode_redis_audio(wav_bytes: bytes) -> str:
        """Encode WAV bytes for Redis clients configured with decode_responses=True."""
        return base64.b64encode(wav_bytes).decode("ascii")

    @staticmethod
    def _decode_redis_audio(value) -> bytes | None:
        """Decode Redis audio value back to WAV bytes."""
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="strict")
        if not isinstance(value, str) or value == "":
            return None
        try:
            return base64.b64decode(value, validate=True)
        except Exception:
            return None

    async def _cache_get(self, object_name: str, redis: "aioredis.Redis" = None) -> tuple[bytes | None, str | None]:
        """Get cached audio bytes using Redis-first, then MinIO fallback."""
        if redis is not None:
            try:
                val = await redis.get(self._redis_cache_key(object_name))
                cached_wav = self._decode_redis_audio(val)
                if cached_wav is not None:
                    return cached_wav, "redis"
            except Exception:
                pass

        try:
            if storage_object_exists(object_name):
                wav_bytes = get_file_from_minio_as_stream(object_name).read()
                if redis is not None and wav_bytes:
                    try:
                        await redis.setex(
                            self._redis_cache_key(object_name),
                            self.redis_ttl_sec,
                            self._encode_redis_audio(wav_bytes),
                        )
                    except Exception:
                        pass
                return wav_bytes, "minio"
        except Exception:
            return None, None
        return None, None

    async def _cache_set(self, object_name: str, wav_bytes: bytes, redis: "aioredis.Redis" = None) -> None:
        """Write-through audio cache to both Redis and MinIO, best-effort
        (no Redis-MinIO atomic all or nothing)."""
        if redis is not None:
            try:
                await redis.setex(
                    self._redis_cache_key(object_name),
                    self.redis_ttl_sec,
                    self._encode_redis_audio(wav_bytes),
                )
            except Exception:
                pass

        try:
            if not storage_object_exists(object_name):
                upload_file_to_minio(io.BytesIO(wav_bytes), object_name)
        except Exception:
            # Cache write failures should not fail synthesis requests.
            pass

    async def _jp_to_statica_mapping(self, kana_text: str, db: "DBHandling" = None) -> list[str]:
        """Resolve StaticA mapping for JP text.

        Strategy:
        1. Try DB first (exact spelling/word lookup) and use stored audio_mapping
        (produced when insert file/string, will have for individual words).
        2. Fall back to mora separation mapping when DB has no usable result (if input phrase/sentence).
        """
        if db is not None:
            try:
                candidates = await db.query_search_word(kana_text, limit=5)
                for item in candidates:
                    if item.get("spelling") == kana_text or item.get("word") == kana_text:
                        mapping = item.get("audio_mapping") or []
                        if mapping:
                            return mapping
            except Exception:
                # Non-blocking: fallback to derived mapping below.
                pass

        return await sep_mora_get_audio_mapping(kana_text)

    async def build_statica_fallback(self, text: str, lang: str, reason: str, db: "DBHandling" = None) -> dict | None:
        """Return fallback payload for clients that can play existing StaticA mapping.
        Only works for `lang`='jp'."""
        if lang != "jp":
            return None

        audio_mapping = await self._jp_to_statica_mapping(text, db)
        if not audio_mapping:
            return None

        return {
            "source": "statica",
            "engine": "StaticA",
            "reason": reason,
            "lang": lang,
            "text": text,
            "audio_mapping": audio_mapping,
        }

    async def synthesize(self, text: str, lang: str, redis: "aioredis.Redis" = None, voice_options: dict | None = None) -> TTSAudio:
        """Synthesize `text` in `lang` with Redis->MinIO->generate cache flow."""
        voice_options = voice_options or {}
        if lang == "jp":
            adapter = self.jp_adapter
        elif lang == "en":
            adapter = self.en_adapter
        else:
            raise TTSAdapterError(f"Unsupported TTS language: {lang}")

        object_name = self._cache_object_name(text, lang, adapter.engine_name, voice_options)
        cached_wav, cache_source = await self._cache_get(object_name, redis)
        if cached_wav is not None:
            return TTSAudio(
                wav_bytes=cached_wav,
                sample_rate=0,
                engine=adapter.engine_name,
                source=cache_source or "cache",
                object_name=object_name,
            )

        if lang == "jp":
            result = adapter.synthesize(
                text,
                speed=voice_options.get("speed"),
                half_tone=voice_options.get("half_tone"),
            )
        else:
            result = adapter.synthesize(text)
        result.object_name = object_name
        result.source = "generated"
        await self._cache_set(object_name, result.wav_bytes, redis)
        return result

    async def get_cached_for_request(self, text: str, lang: str, engine: str,
                                     redis: "aioredis.Redis" = None,
                                     voice_options: dict | None = None) -> TTSAudio | None:
        """Return cached TTSAudio for an exact request key, without generating."""
        object_name = self._cache_object_name(text, lang, engine, voice_options or {})
        cached_wav, cache_source = await self._cache_get(object_name, redis)
        if cached_wav is None:
            return None
        return TTSAudio(
            wav_bytes=cached_wav,
            sample_rate=0,
            engine=engine,
            source=cache_source or "cache",
            object_name=object_name,
        )

    async def get_cached_by_object_name(self, object_name: str, redis: "aioredis.Redis" = None) -> tuple[bytes | None, str | None]:
        """Return cached audio bytes by cache object name, without synthesis."""
        return await self._cache_get(object_name, redis)
