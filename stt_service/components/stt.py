import base64
import logging
import os
import tempfile
import time
import numpy as np
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field

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


@dataclass
class StreamingState:
    """State for a streaming STT session"""
    pipeline_state: Optional[Any] = None  # T-one pipeline state (None initially)
    all_phrases: List[Any] = field(default_factory=list)  # Accumulated phrases from all chunks
    audio_buffer: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int32))  # Buffer for audio samples (int32 for T-one)
    partial_text: str = ""  # Current partial transcription
    finalized: bool = False
    created_at: float = field(default_factory=time.time)


class STT:
    """Speech-to-Text component using T-one (T-Tech streaming ASR for Russian)"""
    
    def __init__(self):
        self.pipeline = None
        self._initialized = False
        self.streams: Dict[str, StreamingState] = {}  # Per-session streaming state
    
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
            # Get required chunk size from pipeline
            self.required_chunk_size = self.pipeline.CHUNK_SIZE
            logger.info(f"STT: T-one model loaded successfully (required chunk size: {self.required_chunk_size} samples)")
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
    
    def start_stream(self, session_id: str):
        """
        Initialize a new streaming session.
        
        Args:
            session_id: Unique session identifier
        """
        if session_id in self.streams:
            logger.warning(f"STT: Stream {session_id} already exists, resetting...")
            self.reset_stream(session_id)
        
        # Initialize with None state (as per T-one example)
        self.streams[session_id] = StreamingState(pipeline_state=None)
        logger.info(f"STT: Started streaming session {session_id}")
    
    async def process_chunk(self, session_id: str, audio_chunk_base64: str) -> str:
        """
        Process an audio chunk and return partial transcription using T-one streaming API.
        Buffers chunks until required size (2400 samples) is reached.
        
        Args:
            session_id: Session identifier
            audio_chunk_base64: Base64 encoded audio chunk (WAV format)
            
        Returns:
            Partial transcription text
        """
        if not self._initialized:
            raise RuntimeError("STT model not initialized. Call initialize() first.")
        
        if session_id not in self.streams:
            logger.warning(f"STT: Stream {session_id} not found, creating new stream...")
            self.start_stream(session_id)
        
        stream_state = self.streams[session_id]
        
        if stream_state.finalized:
            logger.warning(f"STT: Stream {session_id} already finalized, resetting...")
            self.reset_stream(session_id)
            self.start_stream(session_id)
            stream_state = self.streams[session_id]
        
        try:
            # Decode base64 audio chunk
            audio_bytes = base64.b64decode(audio_chunk_base64)
            
            # Save to temporary file and read with T-one's read_audio
            temp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                    temp_file.write(audio_bytes)
                    temp_file_path = temp_file.name
                
                # Read audio chunk using T-one's read_audio function
                # read_audio returns float32 normalized audio [-1, 1]
                audio_chunk_float = read_audio(temp_file_path)

                logger.info(f"audio_chunk_float.max(): {audio_chunk_float.max()}")
                logger.info(f"audio_chunk_float.max(): {audio_chunk_float.min()}")
                
                # Convert float32 [-1, 1] to int32 [-32768, 32767] for T-one pipeline
                # T-one's forward() expects int32 dtype
                # audio_chunk = (audio_chunk_float * 32768.0).clip(-32768, 32767).astype(np.int32)
                audio_chunk = audio_chunk_float.astype(np.int32)
                
                # Add to buffer
                stream_state.audio_buffer = np.concatenate([stream_state.audio_buffer, audio_chunk])
                
                # Process chunks when we have enough samples
                # T-one requires exactly CHUNK_SIZE samples per forward() call
                processed_any = False
                total_new_phrases = 0
                logger.info(f"len(stream_state.audio_buffer): {len(stream_state.audio_buffer)}")
                while len(stream_state.audio_buffer) >= self.required_chunk_size:
                    # Extract exactly required_chunk_size samples
                    chunk_to_process = stream_state.audio_buffer[:self.required_chunk_size]
                    stream_state.audio_buffer = stream_state.audio_buffer[self.required_chunk_size:]
                    
                    # Process chunk with T-one streaming API: forward(audio_chunk, state)
                    # Returns: (new_phrases, updated_state)
                    new_phrases, updated_state = self.pipeline.forward(
                        chunk_to_process, 
                        stream_state.pipeline_state
                    )
                    
                    # Update pipeline state
                    stream_state.pipeline_state = updated_state
                    
                    # Accumulate new phrases
                    stream_state.all_phrases.extend(new_phrases)
                    total_new_phrases += len(new_phrases)
                    processed_any = True
                
                # Extract text from all accumulated phrases
                transcription_parts = [phrase.text for phrase in stream_state.all_phrases]
                partial_transcription = " ".join(transcription_parts).strip()
                
                # Log partial transcription if it changed
                if processed_any and partial_transcription != stream_state.partial_text:
                    logger.info(
                        f"STT: Partial transcription for session {session_id}: "
                        f"'{partial_transcription}' "
                        f"(new phrases: {total_new_phrases}, "
                        f"total phrases: {len(stream_state.all_phrases)}, "
                        f"buffer: {len(stream_state.audio_buffer)}/{self.required_chunk_size} samples)"
                    )
                elif processed_any:
                    logger.debug(
                        f"STT: Processed chunk for session {session_id}, "
                        f"new phrases: {total_new_phrases}, "
                        f"buffer remaining: {len(stream_state.audio_buffer)} samples"
                    )
                else:
                    logger.debug(
                        f"STT: Buffering chunk for session {session_id}, "
                        f"buffer size: {len(stream_state.audio_buffer)}/{self.required_chunk_size} samples"
                    )
                
                stream_state.partial_text = partial_transcription
                
                return partial_transcription
                
            finally:
                # Clean up temporary file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except Exception as e:
                        logger.warning(f"STT: Error cleaning up temp file: {e}")
        
        except Exception as e:
            logger.error(f"STT: Error processing chunk for session {session_id}: {e}", exc_info=True)
            raise
    
    async def finalize_stream(self, session_id: str) -> str:
        """
        Finalize a streaming session and return complete transcription using T-one finalize API.
        Processes any remaining buffered audio before finalizing.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Final transcription text
        """
        if not self._initialized:
            raise RuntimeError("STT model not initialized. Call initialize() first.")
        
        if session_id not in self.streams:
            logger.warning(f"STT: Stream {session_id} not found")
            return ""
        
        stream_state = self.streams[session_id]
        
        if stream_state.finalized:
            logger.warning(f"STT: Stream {session_id} already finalized")
            return stream_state.partial_text
        
        try:
            # Process any remaining buffered audio
            # Pad with zeros if needed to reach required chunk size
            if len(stream_state.audio_buffer) > 0:
                remaining_samples = len(stream_state.audio_buffer)
                if remaining_samples < self.required_chunk_size:
                    # Pad with zeros to reach required size (int32 zeros)
                    padding_size = self.required_chunk_size - remaining_samples
                    padding = np.zeros(padding_size, dtype=np.int32)
                    stream_state.audio_buffer = np.concatenate([stream_state.audio_buffer, padding])
                    logger.debug(
                        f"STT: Padded remaining buffer for session {session_id}: "
                        f"{remaining_samples} -> {len(stream_state.audio_buffer)} samples"
                    )
                
                # Process remaining buffer
                if len(stream_state.audio_buffer) >= self.required_chunk_size:
                    chunk_to_process = stream_state.audio_buffer[:self.required_chunk_size]
                    new_phrases, updated_state = self.pipeline.forward(
                        chunk_to_process,
                        stream_state.pipeline_state
                    )
                    stream_state.pipeline_state = updated_state
                    stream_state.all_phrases.extend(new_phrases)
                    
                    # Log updated partial transcription
                    transcription_parts = [phrase.text for phrase in stream_state.all_phrases]
                    partial_transcription = " ".join(transcription_parts).strip()
                    logger.info(
                        f"STT: Processed remaining buffer for session {session_id}, "
                        f"new phrases: {len(new_phrases)}, "
                        f"partial transcription: '{partial_transcription}'"
                    )
            
            # Finalize the pipeline and get remaining phrases
            # pipeline.finalize(state) returns: (new_phrases, _)
            if stream_state.pipeline_state is not None:
                final_phrases, _ = self.pipeline.finalize(stream_state.pipeline_state)
                
                # Add final phrases to accumulated phrases
                stream_state.all_phrases.extend(final_phrases)
                
                # Extract final text from all phrases
                transcription_parts = [phrase.text for phrase in stream_state.all_phrases]
                final_transcription = " ".join(transcription_parts).strip()
                
                stream_state.partial_text = final_transcription
                stream_state.finalized = True
                
                logger.info(
                    f"STT: Finalized stream {session_id}, "
                    f"final phrases: {len(final_phrases)}, "
                    f"total phrases: {len(stream_state.all_phrases)}, "
                    f"final transcription: '{final_transcription[:100]}...'"
                )
                
                return final_transcription
            else:
                # No state means no chunks were processed, return empty
                logger.warning(f"STT: No pipeline state for session {session_id} (no chunks processed)")
                stream_state.finalized = True
                return stream_state.partial_text if stream_state.partial_text else ""
        
        except Exception as e:
            logger.error(f"STT: Error finalizing stream {session_id}: {e}", exc_info=True)
            raise
    
    def reset_stream(self, session_id: str):
        """
        Reset/cleanup a streaming session.
        
        Args:
            session_id: Session identifier
        """
        if session_id in self.streams:
            del self.streams[session_id]
            logger.info(f"STT: Reset stream {session_id}")
        else:
            logger.debug(f"STT: Stream {session_id} not found for reset")

