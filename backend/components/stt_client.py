import httpx
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", "http://stt_service:8001")


class STTClient:
    """HTTP client for STT service"""
    
    def __init__(self, service_url: str = None):
        self.service_url = service_url or STT_SERVICE_URL
        
        timeout = httpx.Timeout(300.0, connect=10.0)
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def transcribe(self, audio_data: str) -> str:
        """
        Transcribe audio using STT service
        """
        overall_start = time.time()
        try:
            # Prepare request
            prepare_start = time.time()
            logger.info(f"STTClient: Sending transcription request to {self.service_url}/transcribe")
            prepare_time = time.time() - prepare_start
            
            # Send HTTP request and wait for response
            request_start = time.time()
            response = await self.client.post(
                f"{self.service_url}/transcribe",
                json={"audio": audio_data}
            )
            request_time = time.time() - request_start
            
            # Check response status
            status_start = time.time()
            response.raise_for_status()
            status_time = time.time() - status_start
            
            # Parse JSON response
            parse_start = time.time()
            result = response.json()
            transcription = result.get("transcription", "")
            parse_time = time.time() - parse_start
            
            overall_time = time.time() - overall_start
            logger.info(
                f"STTClient: Received transcription: {transcription[:100]}... - "
                f"Prepare: {prepare_time:.3f}s, "
                f"HTTP request: {request_time:.3f}s, "
                f"Status check: {status_time:.3f}s, "
                f"JSON parse: {parse_time:.3f}s, "
                f"Total: {overall_time:.3f}s"
            )
            return transcription
        except httpx.HTTPError as e:
            overall_time = time.time() - overall_start
            logger.error(f"STTClient: HTTP error during transcription (failed after {overall_time:.3f}s): {str(e)}")
            raise
        except Exception as e:
            overall_time = time.time() - overall_start
            logger.error(f"STTClient: Error during transcription (failed after {overall_time:.3f}s): {str(e)}", exc_info=True)
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

