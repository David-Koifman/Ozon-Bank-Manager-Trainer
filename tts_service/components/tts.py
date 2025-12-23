import base64
import logging
import os
import io

import numpy as np
import soundfile as sf
import torch
from torch.cpu import is_available

logger = logging.getLogger(__name__)

# Silero TTS configuration
MODEL_URL = 'https://models.silero.ai/models/tts/ru/v4_ru.pt'
MODEL_FILE = 'model.pt'
SAMPLE_RATE = 48000
DEFAULT_SPEAKER = 'aidar'  # Options: 'aidar', 'baya', 'kseniya', 'xenia', 'eugene'


class TTSComponent:
    """Text-to-Speech component using Silero TTS"""
    
    def __init__(self):
        self.model = None
        self.device = None
        self._initialized = False
    
    def initialize(self):
        """Initialize TTS model (called on startup)"""
        if self._initialized:
            return
        
        logger.info("TTS: Initializing Silero TTS model...")
        try:
            if torch.cuda.is_available():
                self.device = 'cuda'
            elif torch.backends.mps.is_available():
                self.device = 'mps'
            else:
                self.device = 'cpu'
            # Set device (GPU if available, else CPU)
            logger.info(f"TTS: Using device: {self.device}")
            
            # Download model if not exists
            if not os.path.isfile(MODEL_FILE):
                logger.info("TTS: Downloading Silero model... This may take a moment.")
                torch.hub.download_url_to_file(MODEL_URL, MODEL_FILE)
                logger.info("TTS: Model downloaded successfully")
            
            # Load model
            logger.info("TTS: Loading model...")
            self.model = torch.package.PackageImporter(MODEL_FILE).load_pickle("tts_models", "model")
            self.model.to(self.device)
            self._initialized = True
            
            logger.info("TTS: Model loaded successfully")
        except Exception as e:
            logger.error(f"TTS: Failed to load model: {str(e)}", exc_info=True)
            raise
    
    async def synthesize(self, text: str, language: str = "ru", speaker: str = DEFAULT_SPEAKER) -> str:
        """
        Synthesize text to speech and return base64 encoded WAV audio (in-memory, no temp files).
        
        Args:
            text: Text to synthesize
            language: Language code (default: "ru" for Russian)
            speaker: Speaker voice ('aidar', 'baya', 'kseniya', 'xenia', 'eugene')
        """
        if not self._initialized:
            raise RuntimeError("TTS model not initialized. Call initialize() first.")

        logger.info(f"TTS: Starting synthesis (text length: {len(text)}, speaker: {speaker})")
        logger.info(f"TTS: Text: {text}")

        try:
            # Generate audio using Silero
            audio = self.model.apply_tts(
                text=text,
                speaker=speaker,
                sample_rate=SAMPLE_RATE
            )

            # Ensure numpy array
            audio_np = np.asarray(audio, dtype=np.float32)
            if audio_np.ndim > 1:
                # Convert multi-channel to mono
                logger.info(f"TTS: Converting multi-channel audio to mono")
                audio_np = np.mean(audio_np, axis=-1).astype(np.float32)

            # Write WAV to in-memory buffer
            buffer = io.BytesIO()
            sf.write(buffer, audio_np, SAMPLE_RATE, format="WAV")
            audio_bytes: bytes = buffer.getvalue()

            # Encode to base64
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            logger.info(
                f"TTS: Generated in-memory audio (base64 length: {len(audio_base64)}, raw size: {len(audio_bytes)} bytes)"
            )
            return audio_base64

        except Exception as e:
            logger.error(f"TTS: Error during synthesis: {str(e)}", exc_info=True)
            raise

