"""
Voice Activity Detection (VAD) with end-of-speech detection using Silero VAD.

This component detects when a user has finished speaking by monitoring
for silence after speech. Only complete utterances are returned for processing.
"""
import numpy as np
import struct
import logging
from typing import Optional, List
import torch

from silero_vad import load_silero_vad


logger = logging.getLogger(__name__)


class VADDetector:
    """
    Voice Activity Detection with end-of-speech detection.
    
    Detects when user has finished speaking based on silence duration.
    Accumulates speech chunks and returns complete utterances when silence
    threshold is exceeded.
    
    Usage:
        vad = VADDetector(sample_rate=16000, silence_duration_ms=1500)
        
        while receiving_audio:
            chunk = receive_audio_chunk()
            speech_segment = vad.process_chunk(chunk)
            
            if speech_segment:
                # User has finished speaking!
                # Process complete utterance
                transcription = await stt.transcribe(speech_segment)
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 32,  # Processing window size (must be >= 32ms for Silero VAD)
        silence_duration_ms: int = 1500,  # 1.5 seconds of silence = end of speech
        min_speech_duration_ms: int = 300,  # Minimum speech duration to consider valid
        threshold: float = 0.5  # Silero VAD threshold (0.0-1.0)
    ):
        """
        Initialize VAD detector using Silero VAD.
        
        Args:
            sample_rate: Audio sample rate (must be 8000 or 16000 for Silero VAD)
            frame_duration_ms: Processing window size in ms (must be >= 32ms for Silero VAD)
                - Silero VAD requires minimum 32ms chunks (512 samples at 16kHz)
            silence_duration_ms: How long silence before considering speech ended
                - Too short: May cut off user mid-sentence
                - Too long: High latency
                - Recommended: 1000-2000ms (1-2 seconds)
            min_speech_duration_ms: Minimum speech duration to be valid
                - Prevents false positives from short noises
                - Recommended: 200-500ms
            threshold: Silero VAD threshold (0.0-1.0)
                - Higher = more conservative (less false positives)
                - Lower = more sensitive (may detect noise as speech)
                - Recommended: 0.5 (balanced)
        """        
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.silence_duration_ms = silence_duration_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.threshold = threshold
        
        # Validate sample rate (Silero VAD supports 8000 and 16000)
        if sample_rate not in [8000, 16000]:
            raise ValueError(
                f"Sample rate must be 8000 or 16000 for Silero VAD, got {sample_rate}"
            )
        
        # Calculate minimum chunk size required by Silero VAD
        # Silero VAD requires: sample_rate / num_samples <= 31.25
        # This means: num_samples >= sample_rate / 31.25
        # For 16kHz: num_samples >= 512 (32ms)
        # For 8kHz: num_samples >= 256 (32ms)
        min_chunk_samples = int(sample_rate / 31.25)
        min_chunk_ms = (min_chunk_samples / sample_rate) * 1000
        
        # Ensure frame_duration_ms meets minimum requirement
        if frame_duration_ms < min_chunk_ms:
            logger.warning(
                f"frame_duration_ms ({frame_duration_ms}ms) is less than Silero VAD minimum "
                f"({min_chunk_ms:.1f}ms). Using {min_chunk_ms:.0f}ms instead."
            )
            self.frame_duration_ms = int(min_chunk_ms)
        
        # Initialize Silero VAD model
        self.model = load_silero_vad()
        self.model.eval()  # Set to evaluation mode
        
        # Calculate frame size in samples and bytes (16-bit PCM = 2 bytes per sample)
        # Ensure we have at least the minimum required samples
        self.frame_size_samples = max(
            int(sample_rate * self.frame_duration_ms / 1000),
            min_chunk_samples
        )
        self.frame_size_bytes = self.frame_size_samples * 2
        
        # State tracking
        self.speech_buffer: List[bytes] = []  # Accumulated speech chunks
        self.silence_samples: int = 0  # Consecutive silence samples
        self.speech_started: bool = False
        self.speech_samples: int = 0  # Total speech samples in current utterance
        self._audio_buffer: np.ndarray = np.array([], dtype=np.float32)  # Buffer for audio samples
        
        # Calculate thresholds in samples
        self.silence_threshold_samples = int(sample_rate * silence_duration_ms / 1000)
        self.min_speech_samples = int(sample_rate * min_speech_duration_ms / 1000)
        
        logger.info(
            f"Silero VAD initialized: sample_rate={sample_rate}Hz, "
            f"frame_duration={frame_duration_ms}ms, "
            f"frame_size={self.frame_size_samples} samples ({self.frame_size_bytes} bytes), "
            f"silence_threshold={silence_duration_ms}ms ({self.silence_threshold_samples} samples), "
            f"min_speech={min_speech_duration_ms}ms ({self.min_speech_samples} samples), "
            f"threshold={threshold}"
        )
    
    def process_chunk(self, audio_chunk: bytes) -> Optional[List[bytes]]:
        """
        Process an audio chunk and detect if speech has ended.
        
        Args:
            audio_chunk: Raw audio bytes (PCM 16-bit)
            
        Returns:
            List of accumulated speech chunks if speech has ended, None otherwise.
            The returned chunks can be concatenated to form the complete utterance.
        """
        # Convert bytes to numpy array (int16 -> float32 normalized to [-1, 1])
        samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Add to audio buffer
        self._audio_buffer = np.concatenate([self._audio_buffer, samples])
        
        # Process in chunks of frame_size_samples for efficiency
        # Silero VAD requires minimum chunk size (32ms = 512 samples at 16kHz)
        min_chunk_samples = self.frame_size_samples
        
        if len(self._audio_buffer) < min_chunk_samples:
            # Not enough samples yet, wait for more
            return None
        
        # Process accumulated audio
        return self._process_audio_buffer()
    
    def _process_audio_buffer(self) -> Optional[List[bytes]]:
        """
        Process accumulated audio buffer using Silero VAD.
        
        Returns:
            Speech segment if speech has ended, None otherwise.
        """
        # Process in chunks of frame_size_samples
        chunk_size = self.frame_size_samples
        
        while len(self._audio_buffer) >= chunk_size:
            # Extract chunk to process
            chunk = self._audio_buffer[:chunk_size]
            self._audio_buffer = self._audio_buffer[chunk_size:]
            
            # Convert to torch tensor (Silero VAD expects torch tensors)
            audio_tensor = torch.from_numpy(chunk).unsqueeze(0)
            
            # Run Silero VAD
            try:
                with torch.no_grad():
                    speech_prob = self.model(audio_tensor, self.sample_rate).item()
            except Exception as e:
                logger.error(f"Silero VAD error: {e}")
                continue
            
            # Determine if this chunk contains speech
            is_speech = speech_prob >= self.threshold
            
            # Convert chunk back to bytes for storage
            chunk_bytes = (chunk * 32768.0).astype(np.int16).tobytes()
            
            if is_speech:
                # Speech detected - accumulate in buffer
                self.speech_buffer.append(chunk_bytes)
                if self.silence_samples > 0:
                    # Was in silence, now speech again - reset silence counter
                    logger.debug(
                        f"Speech resumed after {self.silence_samples} samples "
                        f"({self.silence_samples / self.sample_rate * 1000:.1f}ms) of silence"
                    )
                self.silence_samples = 0
                self.speech_started = True
                self.speech_samples += chunk_size
            else:
                # Silence detected
                if self.speech_started:
                    # We were collecting speech, now we have silence
                    self.silence_samples += chunk_size
                    
                    if self.silence_samples % (self.sample_rate // 10) == 0:  # Log every 100ms
                        logger.debug(
                            f"Silence accumulating: {self.silence_samples}/{self.silence_threshold_samples} samples "
                            f"({self.silence_samples / self.sample_rate * 1000:.1f}ms / "
                            f"{self.silence_threshold_samples / self.sample_rate * 1000:.1f}ms)"
                        )
                    
                    # Check if silence duration exceeds threshold
                    if self.silence_samples >= self.silence_threshold_samples:
                        # Speech has ended!
                        total_speech_samples = sum(len(chunk) // 2 for chunk in self.speech_buffer)
                        
                        if total_speech_samples >= self.min_speech_samples:
                            # Valid speech segment detected
                            speech_segment = self.speech_buffer.copy()
                            speech_duration_ms = total_speech_samples / self.sample_rate * 1000
                            
                            logger.info(
                                f"Speech ended: {len(speech_segment)} chunks "
                                f"({speech_duration_ms:.1f}ms), "
                                f"silence: {self.silence_samples / self.sample_rate * 1000:.1f}ms"
                            )
                            
                            # Reset state for next utterance
                            self._reset()
                            
                            return speech_segment
                        else:
                            # Speech too short, discard (likely noise)
                            logger.debug(
                                f"Speech too short, discarding: "
                                f"{len(self.speech_buffer)} chunks "
                                f"({total_speech_samples / self.sample_rate * 1000:.1f}ms)"
                            )
                            self._reset()
                            return None
                else:
                    # No speech started yet, just silence - ignore
                    pass
        
        return None
    
    def _reset(self):
        """Reset VAD state for next utterance."""
        self.speech_buffer = []
        self.silence_samples = 0
        self.speech_started = False
        self.speech_samples = 0
        self._audio_buffer = np.array([], dtype=np.float32)
    
    def flush(self) -> Optional[List[bytes]]:
        """
        Flush any remaining speech in buffer.
        
        Call this when connection ends or user explicitly stops speaking
        to process the final utterance.
        
        Returns:
            Speech segment if valid speech was in buffer, None otherwise.
        """
        # Process any remaining audio in buffer
        if len(self._audio_buffer) > 0:
            # Pad with zeros to reach minimum chunk size if needed
            min_size = self.frame_size_samples
            if len(self._audio_buffer) < min_size:
                padding = np.zeros(min_size - len(self._audio_buffer), dtype=np.float32)
                self._audio_buffer = np.concatenate([self._audio_buffer, padding])
            
            # Process remaining buffer
            result = self._process_audio_buffer()
            if result:
                return result
        
        # Check if we have valid speech in buffer
        total_speech_samples = sum(len(chunk) // 2 for chunk in self.speech_buffer)
        
        if self.speech_started and total_speech_samples >= self.min_speech_samples:
            speech_segment = self.speech_buffer.copy()
            speech_duration_ms = total_speech_samples / self.sample_rate * 1000
            
            logger.info(
                f"Flushed speech segment: {len(speech_segment)} chunks "
                f"({speech_duration_ms:.1f}ms)"
            )
            
            self._reset()
            return speech_segment
        
        return None
    
    def get_state(self) -> dict:
        """
        Get current VAD state (for debugging/monitoring).
        
        Returns:
            Dictionary with current state information.
        """
        total_speech_samples = sum(len(chunk) // 2 for chunk in self.speech_buffer)
        return {
            "speech_started": self.speech_started,
            "speech_samples": self.speech_samples,
            "silence_samples": self.silence_samples,
            "buffer_size_chunks": len(self.speech_buffer),
            "buffer_duration_ms": total_speech_samples / self.sample_rate * 1000,
            "silence_threshold_samples": self.silence_threshold_samples,
            "min_speech_samples": self.min_speech_samples,
            "audio_buffer_samples": len(self._audio_buffer)
        }

