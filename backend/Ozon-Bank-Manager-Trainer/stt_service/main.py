from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import asyncio

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
    try:
        logger.info(f"STT Service: Received transcription request (audio length: {len(request.audio)})")
        transcription = await stt.transcribe(request.audio)
        logger.info(f"STT Service: Transcription completed: {transcription[:100]}...")
        return TranscribeResponse(transcription=transcription)
    except Exception as e:
        logger.error(f"STT Service: Error during transcription: {str(e)}", exc_info=True)
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

