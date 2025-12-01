from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from typing import Dict, Optional
import uuid
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

from components.orchestrator import Orchestrator
from components.session_manager import SessionManager
from components.context import Context
from components.stt_client import STTClient
from components.llm import LLM
from components.tts_client import TTSClient
from components.database import Database

app = FastAPI(title="Operator Voice Trainer")

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components (STT and TTS are now separate services)
orchestrator = Orchestrator()
session_manager = SessionManager()
context = Context()
stt = STTClient()
llm = LLM()
tts = TTSClient()
database = Database()


@app.on_event("startup")
async def startup():
    """Initialize services on startup"""
    logger.info("Starting services...")
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        await database.initialize()
        
        # STT and TTS are now separate services, no need to initialize them here
        logger.info("Backend services initialized successfully!")
    except Exception as e:
        logger.error(f"Error initializing services: {str(e)}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    await database.close()
    await stt.close()
    await tts.close()


# Request/Response models
class StartTrainingRequest(BaseModel):
    scenario: str = "default"


class AudioInputRequest(BaseModel):
    audio: str  # base64 encoded audio
    session_id: str


class EndTrainingRequest(BaseModel):
    session_id: str


@app.post("/api/start-training")
async def start_training(request: StartTrainingRequest):
    """Start a new training session"""
    try:
        session_id = str(uuid.uuid4())
        logger.info(f"Starting training session {session_id} with scenario '{request.scenario}'")
        
        message = {
            "action": "start_training",
            "scenario": request.scenario
        }
        
        response = await orchestrator.process(
            message=message,
            session_id=session_id,
            session_manager=session_manager,
            context=context,
            stt=stt,
            llm=llm,
            tts=tts,
            database=database
        )
        
        # Ensure session_id is in response (orchestrator should include it, but ensure it's there)
        if isinstance(response, dict) and "session_id" not in response:
            response["session_id"] = session_id
        
        return response
    except Exception as e:
        logger.error(f"Error starting training session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error starting training session: {str(e)}")


@app.post("/api/audio-input")
async def audio_input(request: AudioInputRequest):
    """Process audio input and return echo response"""
    try:
        # Validate input
        if not request.audio:
            raise HTTPException(status_code=400, detail="Audio data is required")
        
        if not request.session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # Validate base64 format
        try:
            import base64
            # Try to decode to validate it's valid base64
            decoded = base64.b64decode(request.audio, validate=True)
            if len(decoded) == 0:
                raise HTTPException(status_code=400, detail="Audio data is empty")
            logger.info(f"Received audio input for session {request.session_id} (decoded size: {len(decoded)} bytes)")
        except Exception as e:
            logger.error(f"Invalid base64 audio data: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid audio format: {str(e)}")
        
        message = {
            "action": "audio_input",
            "audio": request.audio,
            "session_id": request.session_id
        }
        
        response = await orchestrator.process(
            message=message,
            session_id=request.session_id,
            session_manager=session_manager,
            context=context,
            stt=stt,
            llm=llm,
            tts=tts,
            database=database
        )
        
        # Validate response structure
        if not isinstance(response, dict):
            logger.error(f"Invalid response type from orchestrator: {type(response)}")
            raise HTTPException(status_code=500, detail="Invalid response from orchestrator")
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing audio input: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")


@app.post("/api/end-training")
async def end_training(request: EndTrainingRequest):
    """End a training session"""
    logger.info(f"Ending training session {request.session_id}")
    
    message = {
        "action": "end_training",
        "session_id": request.session_id
    }
    
    response = await orchestrator.process(
        message=message,
        session_id=request.session_id,
        session_manager=session_manager,
        context=context,
        stt=stt,
        llm=llm,
        tts=tts,
        database=database
    )
    
    return response


@app.get("/")
async def root():
    return {"message": "Operator Voice Trainer Backend", "status": "running"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "stt": {
            "service_url": stt.service_url,
            "type": "http_client"
        },
        "tts": {
            "service_url": tts.service_url,
            "type": "http_client"
        },
        "llm": {
            "api_key_set": bool(llm.api_key)
        },
        "database": {
            "initialized": database._initialized if hasattr(database, '_initialized') else False
        }
    }

