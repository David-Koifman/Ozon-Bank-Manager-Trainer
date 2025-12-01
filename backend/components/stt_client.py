import httpx
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", "http://stt_service:8001")


class STTClient:
    """HTTP client for STT service"""
    
    def __init__(self, service_url: str = None):
        self.service_url = service_url or STT_SERVICE_URL
        self.client = httpx.AsyncClient(timeout=60.0)  # Longer timeout for model inference
    
    async def transcribe(self, audio_data: str) -> str:
        """
        Transcribe audio using STT service
        """
        try:
            logger.info(f"STTClient: Sending transcription request to {self.service_url}/transcribe")
            response = await self.client.post(
                f"{self.service_url}/transcribe",
                json={"audio": audio_data}
            )
            response.raise_for_status()
            result = response.json()
            transcription = result.get("transcription", "")
            logger.info(f"STTClient: Received transcription: {transcription[:100]}...")
            return transcription
        except httpx.HTTPError as e:
            logger.error(f"STTClient: HTTP error during transcription: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"STTClient: Error during transcription: {str(e)}", exc_info=True)
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

