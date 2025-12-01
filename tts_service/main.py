from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

from components.tts import TTSComponent

app = FastAPI(title="TTS Service")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize TTS component
tts = TTSComponent()


class SynthesizeRequest(BaseModel):
    text: str
    language: str = "ru"  # Russian by default
    speaker: str = "aidar"  # Options: 'aidar', 'kseniya', 'baya', 'xenia'


class SynthesizeResponse(BaseModel):
    audio: str  # base64 encoded audio


@app.on_event("startup")
async def load_model():
    """Load TTS model on startup"""
    logger.info("TTS Service: Starting model loading...")
    try:
        tts.initialize()
        logger.info("TTS Service: Model loaded successfully!")
    except Exception as e:
        logger.error(f"TTS Service: Error loading model: {str(e)}", exc_info=True)
        raise


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(request: SynthesizeRequest):
    """Synthesize text to speech"""
    try:
        logger.info(f"TTS Service: Received synthesis request (text length: {len(request.text)}, language: {request.language}, speaker: {request.speaker})")
        audio_base64 = await tts.synthesize(
            text=request.text,
            language=request.language,
            speaker=request.speaker
        )
        logger.info(f"TTS Service: Synthesis completed")
        return SynthesizeResponse(audio=audio_base64)
    except Exception as e:
        logger.error(f"TTS Service: Error during synthesis: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "tts",
        "model_loaded": tts._initialized if hasattr(tts, '_initialized') else False
    }


@app.get("/")
async def root():
    return {"service": "TTS Service", "status": "running"}

