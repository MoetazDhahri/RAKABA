"""
ElevenLabs voice I/O for the RAKABA voice assistant: speech-to-text (Scribe)
and text-to-speech (multilingual), used as a thin layer in front of the
existing handlers.chat_client/chat_admin logic - never replacing it. Every
voice turn still goes through escalation classification and client-safe
data filtering exactly as a text turn does; ElevenLabs only handles audio
in and out.

Language handling: both directions auto-detect from content rather than
requiring the caller to pick a language up front - verified empirically
(see pipeline3/README.md) that this works well for French, English and
Modern Standard Arabic, and reasonably for Tunisian Derja WRITTEN IN ARABIC
SCRIPT (correctly detected as Arabic, minor dialectal-word substitutions in
transcription - e.g. "متاعك" came back as "بتاعك", same meaning). Derja
written in Latin transliteration ("Arabizi", how it's actually typed day to
day) does NOT work - it was misdetected as Esperanto and the transcription
was unusable gibberish. There is no dedicated "Tunisian" language/voice code
in ElevenLabs' API; "Tunisian support" in practice means "works if the text
is in Arabic script," not a distinct dialect model.
"""

from __future__ import annotations

import io
import os

from elevenlabs.client import ElevenLabs

STT_MODEL = "scribe_v1"
TTS_MODEL = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
DEFAULT_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")  # "Sarah"
OUTPUT_FORMAT = "mp3_44100_128"

_client = None


class VoiceAPIError(Exception):
    pass


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise VoiceAPIError(
                "ELEVENLABS_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = ElevenLabs(api_key=api_key)
    return _client


def transcribe(audio_bytes: bytes) -> str:
    """Speech-to-text via ElevenLabs Scribe. Language is auto-detected."""
    try:
        client = _get_client()
        result = client.speech_to_text.convert(
            file=io.BytesIO(audio_bytes),
            model_id=STT_MODEL,
        )
    except VoiceAPIError:
        raise
    except Exception as exc:
        raise VoiceAPIError(f"ElevenLabs speech-to-text failed: {exc}") from exc

    return result.text or ""


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """Text-to-speech via ElevenLabs' multilingual model. Language is
    auto-detected from the text itself - no language_code needed. Returns
    MP3 bytes."""
    try:
        client = _get_client()
        chunks = client.text_to_speech.convert(
            voice_id=voice_id or DEFAULT_VOICE_ID,
            text=text,
            model_id=TTS_MODEL,
            output_format=OUTPUT_FORMAT,
        )
    except VoiceAPIError:
        raise
    except Exception as exc:
        raise VoiceAPIError(f"ElevenLabs text-to-speech failed: {exc}") from exc

    return b"".join(chunks)
