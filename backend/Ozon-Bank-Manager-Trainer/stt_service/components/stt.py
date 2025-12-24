import base64
import logging
import os
import tempfile
import whisper

logger = logging.getLogger(__name__)

MODEL_SIZE = "base"  # Options: 'tiny', 'base', 'small', 'medium', 'large'


class STT:
    """Speech-to-Text component using OpenAI Whisper"""
    
    def __init__(self):
        self.model = None
        self._initialized = False
    
    def initialize(self):
        """Initialize STT model (called on startup)"""
        if self._initialized:
            return
        
        logger.info(f"STT: Loading Whisper model '{MODEL_SIZE}' (this may take a minute)...")
        try:
            self.model = whisper.load_model(MODEL_SIZE)
            self._initialized = True
            logger.info("STT: Model loaded successfully")
        except Exception as e:
            logger.error(f"STT: Failed to load model: {str(e)}")
            raise
    
    async def transcribe(self, audio_data: str) -> str:
        """
        Transcribe audio from base64 encoded audio data
        """
        if not self._initialized:
            raise RuntimeError("STT model not initialized. Call initialize() first.")
        
        logger.info(f"STT: Starting transcription (audio_data length: {len(audio_data)})")
        
        temp_file_path = None
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_data)
            logger.info(f"STT: Decoded base64 audio (decoded length: {len(audio_bytes)} bytes)")
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            logger.info(f"STT: Saved audio to temporary file: {temp_file_path}")
            
            # Transcribe using Whisper
            logger.info(f"STT: Transcribing audio file: {temp_file_path}")
            result = self.model.transcribe(temp_file_path)
            
            # Extract text from result
            transcription = result['text']
            
            logger.info(f"STT: Transcription result: '{transcription}'")
            return transcription
        
        except Exception as e:
            logger.error(f"STT: Error during transcription: {str(e)}", exc_info=True)
            raise
        
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass

