import io
import logging
import soundfile as sf
import requests
import numpy as np
from src.engine.stt_base import BaseSTTEngine
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.STT_Cloud")

class CloudSTTEngine(BaseSTTEngine):
    def __init__(self):
        pass

    def load_model(self, model_name: str = "whisper-large-v3-turbo", language: str = "tr"):
        pass  # Cloud APIs load model remotely on server

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if len(audio) == 0:
            return ""

        # Convert numpy float32 audio to WAV in-memory bytes
        buffer = io.BytesIO()
        sf.write(buffer, audio, sample_rate, format='WAV', subtype='PCM_16')
        buffer.seek(0)
        buffer.name = "audio.wav"

        provider = config_manager.get("ai_cleanup_provider", "groq")
        api_key_groq = config_manager.get("api_key_groq", "")
        api_key_openai = config_manager.get("api_key_openai", "")

        # Try Groq API first if key exists
        if api_key_groq:
            try:
                headers = {"Authorization": f"Bearer {api_key_groq}"}
                files = {"file": ("audio.wav", buffer, "audio/wav")}
                data = {
                    "model": "whisper-large-v3-turbo",
                    "language": language if language != "auto" else "tr",
                    "response_format": "json"
                }
                resp = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data, timeout=10)
                if resp.status_code == 200:
                    text = resp.json().get("text", "").strip()
                    logger.info(f"Groq Cloud Transcribed: {text}")
                    return text
                else:
                    logger.warning(f"Groq API error {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Groq API exception: {e}")

        # Try OpenAI API if key exists
        if api_key_openai:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key_openai)
                buffer.seek(0)
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=buffer,
                    language=language if language != "auto" else "tr"
                )
                logger.info(f"OpenAI Cloud Transcribed: {transcript.text}")
                return transcript.text.strip()
            except Exception as e:
                logger.error(f"OpenAI API exception: {e}")

        logger.error("No valid Cloud API key found or Cloud request failed.")
        return ""
