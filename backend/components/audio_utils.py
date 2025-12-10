"""
Audio utility functions for converting between formats.
"""
import wave
import io
import logging

logger = logging.getLogger(__name__)


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    """
    Convert raw PCM audio bytes to WAV format.
    
    Args:
        pcm_bytes: Raw PCM audio bytes (16-bit signed integers)
        sample_rate: Audio sample rate (default: 16000 Hz)
        channels: Number of audio channels (default: 1 for mono)
        sample_width: Sample width in bytes (default: 2 for 16-bit)
        
    Returns:
        WAV file bytes
    """
    # Create in-memory WAV file
    wav_buffer = io.BytesIO()
    
    with wave.open(wav_buffer, 'wb') as wav_file:
        # Set WAV parameters
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        
        # Write PCM data
        wav_file.writeframes(pcm_bytes)
    
    # Get WAV file bytes
    wav_bytes = wav_buffer.getvalue()
    wav_buffer.close()
    
    logger.debug(
        f"Converted PCM to WAV: {len(pcm_bytes)} bytes PCM -> {len(wav_bytes)} bytes WAV "
        f"(sample_rate={sample_rate}, channels={channels}, sample_width={sample_width})"
    )
    
    return wav_bytes

