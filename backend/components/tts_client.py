import httpx
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://tts_service:8002")


class TTSClient:
    """HTTP client for TTS service"""
    
    def __init__(self, service_url: str = None):
        self.service_url = service_url or TTS_SERVICE_URL
        # Set longer timeout for TTS generation (connect, read, write, pool)
        # TTS can take a while, especially for longer texts
        timeout = httpx.Timeout(300.0, connect=10.0)  # 5 minutes total, 10s connect
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def synthesize(self, text: str, language: str = "ru", speaker: str = "aidar") -> str:
        """
        Synthesize text to speech using TTS service
        
        Args:
            text: Text to synthesize
            language: Language code (default: "ru" for Russian)
            speaker: Speaker voice ('aidar', 'baya', 'kseniya', 'xenia', 'eugene')
        """
        try:
            logger.info(f"TTSClient: Sending synthesis request to {self.service_url}/synthesize (speaker: {speaker})")
            payload = {
                "text": text,
                "language": language,
                "speaker": speaker
            }
            
            response = await self.client.post(
                f"{self.service_url}/synthesize",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            audio_base64 = result.get("audio", "")
            logger.info(f"TTSClient: Received synthesized audio (length: {len(audio_base64)})")
            return audio_base64
        except httpx.HTTPError as e:
            logger.error(f"TTSClient: HTTP error during synthesis: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"TTSClient: Error during synthesis: {str(e)}", exc_info=True)
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

