import base64
import logging
import os
import tempfile
import time

logger = logging.getLogger(__name__)

# Import T-one as shown in the official example
try:
    from tone import StreamingCTCPipeline, read_audio
except ImportError:
    logger.error(
        "Failed to import T-one. Please ensure it's installed from GitHub: "
        "pip install git+https://github.com/voicekit-team/T-one.git"
    )
    raise ImportError(
        "T-one package not found. Install with: "
        "pip install git+https://github.com/voicekit-team/T-one.git"
    )


class STT:
    """Speech-to-Text component using T-one (T-Tech streaming ASR for Russian)"""
    
    def __init__(self):
        self.pipeline = None
        self._initialized = False
    
    def initialize(self):
        """Initialize STT model (called on startup)"""
        if self._initialized:
            return
        
        logger.info("STT: Loading T-one model from local...")
        try:
            local_dir = "./tone_models"
            self.pipeline = StreamingCTCPipeline.from_local(local_dir)
            # self.pipeline = StreamingCTCPipeline.from_hugging_face()
            self._initialized = True
            logger.info("STT: T-one model loaded successfully")
        except Exception as e:
            logger.error(f"STT: Failed to load model: {str(e)}")
            raise
    
    async def transcribe(self, audio_data: str) -> str:
        """
        Transcribe audio from base64 encoded audio data
        """
        if not self._initialized:
            raise RuntimeError("STT model not initialized. Call initialize() first.")
        
        overall_start = time.time()
        logger.info(f"STT: Starting transcription (audio_data length: {len(audio_data)})")
        
        temp_file_path = None
        try:
            # Decode base64 audio
            decode_start = time.time()
            audio_bytes = base64.b64decode(audio_data)
            decode_time = time.time() - decode_start
            logger.info(f"STT: Decoded base64 audio (decoded length: {len(audio_bytes)} bytes, decode time: {decode_time:.3f}s)")
            
            # Save to temporary file
            file_write_start = time.time()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            file_write_time = time.time() - file_write_start
            logger.info(f"STT: Saved audio to temporary file: {temp_file_path} (file write time: {file_write_time:.3f}s)")
            
            # Read audio using T-one's read_audio function (as shown in official example)
            read_start = time.time()
            logger.info(f"STT: Reading audio file: {temp_file_path}")
            audio = read_audio(temp_file_path)
            read_time = time.time() - read_start
            logger.info(f"STT: Audio read completed (read time: {read_time:.3f}s)")
            
            # Transcribe using T-one offline mode
            transcribe_start = time.time()
            logger.info("STT: Transcribing audio with T-one...")
            phrases = self.pipeline.forward_offline(audio)
            transcribe_time = time.time() - transcribe_start
            
            # Extract text from phrases and combine
            extract_start = time.time()
            # T-one returns a list of TextPhrase objects with text, start_time, end_time
            # Combine all phrase texts into a single transcription
            transcription_parts = [phrase.text for phrase in phrases]
            transcription = " ".join(transcription_parts).strip()
            extract_time = time.time() - extract_start
            
            overall_time = time.time() - overall_start
            logger.info(
                f"STT: Transcription result: '{transcription}' - "
                f"Base64 decode: {decode_time:.3f}s, "
                f"File write: {file_write_time:.3f}s, "
                f"Audio read: {read_time:.3f}s, "
                f"T-one model: {transcribe_time:.3f}s, "
                f"Text extract: {extract_time:.3f}s, "
                f"Total: {overall_time:.3f}s"
            )
            return transcription
        
        except Exception as e:
            overall_time = time.time() - overall_start
            logger.error(f"STT: Error during transcription (failed after {overall_time:.3f}s): {str(e)}", exc_info=True)
            raise
        
        finally:
            # Clean up temporary file
            cleanup_start = time.time()
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    cleanup_time = time.time() - cleanup_start
                    logger.debug(f"STT: Cleaned up temp file (cleanup time: {cleanup_time:.3f}s)")
                except Exception as cleanup_error:
                    logger.warning(f"STT: Error cleaning up temp file: {cleanup_error}")

