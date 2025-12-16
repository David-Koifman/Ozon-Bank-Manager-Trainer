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
    
    async def start_stream(self, session_id: str):
        """
        Start a new streaming STT session
        
        Args:
            session_id: Unique session identifier
        """
        try:
            logger.debug(f"STTClient: Starting stream for session {session_id}")
            response = await self.client.post(
                f"{self.service_url}/stream/start",
                json={"session_id": session_id}
            )
            response.raise_for_status()
            logger.debug(f"STTClient: Stream started for session {session_id}")
        except httpx.HTTPError as e:
            logger.error(f"STTClient: HTTP error starting stream {session_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"STTClient: Error starting stream {session_id}: {str(e)}", exc_info=True)
            raise
    
    async def process_chunk(self, session_id: str, audio_chunk_base64: str) -> str:
        """
        Process an audio chunk and return partial transcription
        
        Args:
            session_id: Session identifier
            audio_chunk_base64: Base64 encoded audio chunk
            
        Returns:
            Partial transcription text
        """
        try:
            logger.debug(
                f"STTClient: Processing chunk for session {session_id} "
                f"(audio length: {len(audio_chunk_base64)})"
            )
            response = await self.client.post(
                f"{self.service_url}/stream/chunk",
                json={
                    "session_id": session_id,
                    "audio_chunk": audio_chunk_base64
                }
            )
            response.raise_for_status()
            result = response.json()
            partial_transcription = result.get("partial_transcription", "")
            
            logger.debug(
                f"STTClient: Received partial transcription for session {session_id}: "
                f"'{partial_transcription[:50]}...'"
            )
            return partial_transcription
        except httpx.HTTPError as e:
            logger.error(f"STTClient: HTTP error processing chunk for session {session_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"STTClient: Error processing chunk for session {session_id}: {str(e)}", exc_info=True)
            raise
    
    async def finalize_stream(self, session_id: str) -> str:
        """
        Finalize a streaming session and return complete transcription
        
        Args:
            session_id: Session identifier
            
        Returns:
            Final transcription text
        """
        try:
            logger.info(f"STTClient: Finalizing stream for session {session_id}")
            response = await self.client.post(
                f"{self.service_url}/stream/finalize",
                json={"session_id": session_id}
            )
            response.raise_for_status()
            result = response.json()
            final_transcription = result.get("final_transcription", "")
            
            logger.info(
                f"STTClient: Received final transcription for session {session_id}: "
                f"'{final_transcription[:100]}...'"
            )
            return final_transcription
        except httpx.HTTPError as e:
            logger.error(f"STTClient: HTTP error finalizing stream {session_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"STTClient: Error finalizing stream {session_id}: {str(e)}", exc_info=True)
            raise
    
    async def reset_stream(self, session_id: str):
        """
        Reset/cleanup a streaming session
        
        Args:
            session_id: Session identifier
        """
        try:
            logger.debug(f"STTClient: Resetting stream for session {session_id}")
            response = await self.client.post(
                f"{self.service_url}/stream/reset",
                json={"session_id": session_id}
            )
            response.raise_for_status()
            logger.debug(f"STTClient: Stream reset for session {session_id}")
        except httpx.HTTPError as e:
            logger.warning(f"STTClient: HTTP error resetting stream {session_id}: {str(e)}")
            # Don't raise - reset is best effort cleanup
        except Exception as e:
            logger.warning(f"STTClient: Error resetting stream {session_id}: {str(e)}")
            # Don't raise - reset is best effort cleanup
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

