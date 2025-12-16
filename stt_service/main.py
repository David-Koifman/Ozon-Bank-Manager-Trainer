from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import asyncio
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

from components.stt import STT

app = FastAPI(title="STT Service")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize STT component
stt = STT()


class TranscribeRequest(BaseModel):
    audio: str  # base64 encoded audio


class TranscribeResponse(BaseModel):
    transcription: str


# Streaming request/response models
class StartStreamRequest(BaseModel):
    session_id: str


class ProcessChunkRequest(BaseModel):
    session_id: str
    audio_chunk: str  # base64 encoded audio chunk


class ProcessChunkResponse(BaseModel):
    partial_transcription: str
    is_final: bool = False


class FinalizeStreamRequest(BaseModel):
    session_id: str


class FinalizeStreamResponse(BaseModel):
    final_transcription: str


class ResetStreamRequest(BaseModel):
    session_id: str


@app.on_event("startup")
async def load_model():
    """Load STT model on startup"""
    logger.info("STT Service: Starting model loading...")
    try:
        stt.initialize()
        logger.info("STT Service: Model loaded successfully!")
    except Exception as e:
        logger.error(f"STT Service: Error loading model: {str(e)}", exc_info=True)
        raise


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """Transcribe audio to text"""
    endpoint_start = time.time()
    try:
        logger.info(f"STT Service: Received transcription request (audio length: {len(request.audio)})")
        transcription = await stt.transcribe(request.audio)
        endpoint_time = time.time() - endpoint_start
        logger.info(
            f"STT Service: Transcription completed: {transcription[:100]}... "
            f"(endpoint total time: {endpoint_time:.3f}s)"
        )
        return TranscribeResponse(transcription=transcription)
    except Exception as e:
        endpoint_time = time.time() - endpoint_start
        logger.error(
            f"STT Service: Error during transcription (failed after {endpoint_time:.3f}s): {str(e)}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "stt",
        "model_loaded": stt._initialized if hasattr(stt, '_initialized') else False
    }


@app.get("/")
async def root():
    return {"service": "STT Service", "status": "running"}


# Streaming endpoints
@app.post("/stream/start")
async def start_stream(request: StartStreamRequest):
    """Start a new streaming STT session"""
    try:
        stt.start_stream(request.session_id)
        logger.info(f"STT Service: Started streaming session {request.session_id}")
        return {"status": "started", "session_id": request.session_id}
    except Exception as e:
        logger.error(f"STT Service: Error starting stream {request.session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start stream: {str(e)}")


@app.post("/stream/chunk", response_model=ProcessChunkResponse)
async def process_chunk(request: ProcessChunkRequest):
    """Process an audio chunk and return partial transcription"""
    endpoint_start = time.time()
    try:
        logger.debug(
            f"STT Service: Processing chunk for session {request.session_id} "
            f"(audio length: {len(request.audio_chunk)})"
        )
        partial_transcription = await stt.process_chunk(request.session_id, request.audio_chunk)
        endpoint_time = time.time() - endpoint_start
        
        logger.debug(
            f"STT Service: Chunk processed for session {request.session_id}, "
            f"partial: '{partial_transcription[:50]}...' "
            f"(time: {endpoint_time:.3f}s)"
        )
        
        return ProcessChunkResponse(
            partial_transcription=partial_transcription,
            is_final=False
        )
    except Exception as e:
        endpoint_time = time.time() - endpoint_start
        logger.error(
            f"STT Service: Error processing chunk for session {request.session_id} "
            f"(failed after {endpoint_time:.3f}s): {str(e)}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to process chunk: {str(e)}")


@app.post("/stream/finalize", response_model=FinalizeStreamResponse)
async def finalize_stream(request: FinalizeStreamRequest):
    """Finalize a streaming session and return complete transcription"""
    endpoint_start = time.time()
    try:
        logger.info(f"STT Service: Finalizing stream for session {request.session_id}")
        final_transcription = await stt.finalize_stream(request.session_id)
        endpoint_time = time.time() - endpoint_start
        
        logger.info(
            f"STT Service: Stream finalized for session {request.session_id}, "
            f"final: '{final_transcription[:100]}...' "
            f"(time: {endpoint_time:.3f}s)"
        )
        
        return FinalizeStreamResponse(final_transcription=final_transcription)
    except Exception as e:
        endpoint_time = time.time() - endpoint_start
        logger.error(
            f"STT Service: Error finalizing stream {request.session_id} "
            f"(failed after {endpoint_time:.3f}s): {str(e)}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to finalize stream: {str(e)}")


@app.post("/stream/reset")
async def reset_stream(request: ResetStreamRequest):
    """Reset/cleanup a streaming session"""
    try:
        stt.reset_stream(request.session_id)
        logger.info(f"STT Service: Reset stream {request.session_id}")
        return {"status": "reset", "session_id": request.session_id}
    except Exception as e:
        logger.error(f"STT Service: Error resetting stream {request.session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset stream: {str(e)}")

