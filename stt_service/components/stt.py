import asyncio
import base64
import logging
import os
import tempfile
import torch
import torchaudio
import soundfile as sf
from transformers import WhisperProcessor, WhisperForConditionalGeneration

logger = logging.getLogger(__name__)

STT_MODEL_NAME = "Val123val/ru_whisper_small"  # Small Russian Whisper model


class STT:
    """Speech-to-Text component using Whisper"""
    
    def __init__(self):
        self.processor = None
        self.model = None
        self._initialized = False
    
    def initialize(self):
        """Initialize STT model (called on startup)"""
        if self._initialized:
            return
        
        logger.info(f"STT: Loading model: {STT_MODEL_NAME}")
        try:
            self.processor = WhisperProcessor.from_pretrained(STT_MODEL_NAME)
            self.model = WhisperForConditionalGeneration.from_pretrained(STT_MODEL_NAME)
            self.model.eval()
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
            
            audio_format = "wav"
            file_suffix = ".wav"
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            logger.info(f"STT: Saved audio to temporary file: {temp_file_path}")
            
            # Load audio file using soundfile (more reliable for WAV files)
            try:
                # Use soundfile to load audio (works better with WAV files)
                # soundfile returns shape: (samples,) for mono or (samples, channels) for stereo
                audio_array, sample_rate = sf.read(temp_file_path, always_2d=False)
                # Convert to torch tensor
                waveform = torch.from_numpy(audio_array).float()
                
                # Handle shape correctly:
                # soundfile returns:
                # - Mono: (samples,) -> need (1, samples)
                # - Stereo: (samples, channels) -> need (channels, samples) -> then to mono (1, samples)
                logger.info(f"STT: Raw audio array shape: {audio_array.shape}, dtype: {audio_array.dtype}")
                
                if waveform.dim() == 1:
                    # Mono audio: add channel dimension
                    waveform = waveform.unsqueeze(0)
                    logger.info(f"STT: Mono audio detected, added channel dimension")
                elif waveform.dim() == 2:
                    # Stereo audio: shape is (samples, channels)
                    # Check which dimension is channels (should be the smaller one, typically 2)
                    if waveform.shape[1] <= waveform.shape[0] and waveform.shape[1] <= 2:
                        # Standard case: (samples, channels)
                        waveform = waveform.transpose(0, 1)  # (channels, samples)
                        logger.info(f"STT: Stereo audio detected, transposed to (channels, samples)")
                    else:
                        # Unusual case: might already be (channels, samples) or something else
                        logger.warning(f"STT: Unusual stereo shape: {waveform.shape}, assuming (samples, channels)")
                        if waveform.shape[0] < waveform.shape[1]:
                            waveform = waveform.transpose(0, 1)
                    
                    # Convert stereo to mono by averaging channels
                    if waveform.shape[0] > 1:
                        waveform = torch.mean(waveform, dim=0, keepdim=True)  # (1, samples)
                        logger.info(f"STT: Converted stereo to mono")
                else:
                    raise ValueError(f"Unexpected audio shape: {waveform.shape}, dimensions: {waveform.dim()}")
                
                # Validate final shape
                if waveform.shape[0] != 1:
                    raise ValueError(f"Expected mono audio (1 channel), got {waveform.shape[0]} channels")
                if waveform.shape[1] < 100:  # At least 100 samples (very short audio)
                    raise ValueError(f"Audio too short: {waveform.shape[1]} samples. Expected at least 100 samples.")
                
                logger.info(f"STT: Final audio shape: {waveform.shape}, sample_rate: {sample_rate}Hz, duration: {waveform.shape[1]/sample_rate:.2f}s")
            except Exception as e:
                logger.error(f"STT: Error loading audio file: {str(e)}")
                # Fallback to torchaudio if soundfile fails
                try:
                    logger.info("STT: Trying torchaudio as fallback...")
                    waveform, sample_rate = torchaudio.load(temp_file_path)
                except Exception as e2:
                    logger.error(f"STT: Fallback also failed: {str(e2)}")
                    raise ValueError(f"Error loading audio file: {str(e)} (fallback: {str(e2)})")
            
            # Resample to 16kHz if necessary (Whisper expects 16kHz)
            if sample_rate != 16000:
                logger.info(f"STT: Resampling from {sample_rate}Hz to 16000Hz")
                resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=16000)
                waveform = resampler(waveform)
            
            # Process with Whisper processor
            input_features = self.processor(
                waveform.squeeze().numpy(),
                sampling_rate=16000,
                return_tensors="pt"
            ).input_features
            
            # Generate transcription
            with torch.no_grad():
                predicted_ids = self.model.generate(input_features)
                transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
            
            logger.info(f"STT: Transcription result: {transcription[:100]}...")
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

