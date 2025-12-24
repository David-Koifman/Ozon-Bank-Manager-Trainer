from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from typing import Dict, Optional, Set
import uuid
import logging
import base64

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG to see all messages
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
from components.vad_detector import VADDetector
from components.audio_utils import pcm_to_wav
from components.judge_client import JudgeClient

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
judge_client = JudgeClient()

# Track active WebSocket connections
active_websocket_connections: Set[WebSocket] = set()


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
    await judge_client.close()


# Request/Response models
class StartTrainingRequest(BaseModel):
    scenario: str = "default"
    speaker: str = "aidar"  # Options: 'aidar', 'baya', 'kseniya', 'xenia', 'eugene'
    behavior_archetype: str = "novice"  # Options: 'novice', 'silent', 'expert', 'complainer'
    difficulty_level: str = "1"  # Options: '1', '2', '3', '4'


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
            "scenario": request.scenario,
            "speaker": request.speaker,
            "behavior_archetype": request.behavior_archetype,
            "difficulty_level": request.difficulty_level
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


@app.post("/api/end-training")
async def end_training(request: EndTrainingRequest):
    """End a training session and judge it"""
    logger.info(f"Ending training session {request.session_id}")
    
    # Get session info before ending (to get parameters)
    session_info = session_manager.get_session(request.session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} not found")
    
    # Extract session parameters
    behavior_archetype = session_info.get("behavior_archetype", "novice")
    scenario = session_info.get("scenario", "free")
    difficulty_level = session_info.get("difficulty_level", "1")
    
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
    
    # Call judge service after ending session
    judgment = None
    try:
        judgment = await judge_client.judge_session(
            session_id=request.session_id,
            behavior_archetype=behavior_archetype,
            scenario=scenario,
            difficulty_level=difficulty_level
        )
        if judgment:
            response["judgment"] = judgment
            logger.info(f"Successfully judged session {request.session_id}")
        else:
            logger.warning(f"Judge service returned no judgment for session {request.session_id}")
    except Exception as e:
        logger.error(f"Error calling judge service: {str(e)}", exc_info=True)
        # Don't fail the end-training request if judge fails
        response["judgment_error"] = str(e)
    
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
        },
        "websocket_connections": len(active_websocket_connections)
    }


@app.websocket("/ws/call/{session_id}")
async def websocket_call(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time audio streaming with VAD.
    
    Handles:
    - Receiving audio chunks from client
    - Detecting when user has finished speaking (VAD)
    - Processing complete utterances (STT -> LLM -> TTS)
    - Streaming responses back to client
    """
    await websocket.accept()
    active_websocket_connections.add(websocket)
    
    logger.info(f"WebSocket connection established for session {session_id}")
    
    # Initialize VAD detector using Silero VAD
    # Note: Silero VAD requires minimum 32ms chunks (512 samples at 16kHz)
    vad = VADDetector(
        sample_rate=16000,
        frame_duration_ms=32,  # Must be >= 32ms for Silero VAD
        silence_duration_ms=1500,  # 1.5 seconds of silence = end of speech
        min_speech_duration_ms=500,  # Minimum 500ms of speech
        threshold=0.5  # Silero VAD threshold (0.0-1.0, higher = more conservative)
    )
    
    # Get session info
    session_info = session_manager.get_session(session_id)
    if not session_info:
        await websocket.send_json({
            "type": "error",
            "message": "Session not found. Please start a training session first."
        })
        await websocket.close()
        active_websocket_connections.discard(websocket)
        return
    
    speaker = session_info.get("speaker", "aidar")
    
    # Start STT streaming session
    try:
        await stt.start_stream(session_id)
        logger.info(f"STT streaming session started for {session_id}")
    except Exception as e:
        logger.error(f"Failed to start STT stream for {session_id}: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to start STT stream: {str(e)}"
        })
        await websocket.close()
        active_websocket_connections.discard(websocket)
        return
    
    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "message": "Call started, ready to receive audio",
        "session_id": session_id
    })
    
    try:
        chunk_count = 0
        while True:
            # Receive message from client
            try:
                # Use receive_text() for better error handling
                data = await websocket.receive_text()
                message = json.loads(data)
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON: {e}, data preview: {data[:100] if 'data' in locals() else 'N/A'}")
                continue
            except Exception as e:
                logger.error(f"Error receiving WebSocket message: {e}", exc_info=True)
                break
            
            message_type = message.get("type")
            if message_type != "audio_chunk" or chunk_count % 100 == 0:
                logger.info(f"Received WebSocket message type: {message_type}")
            else:
                logger.debug(f"Received WebSocket message type: {message_type}")
            
            if message_type == "audio_chunk":
                chunk_count += 1
                # Process audio chunk with VAD
                try:
                    audio_chunk_bytes = base64.b64decode(message["data"])
                    if chunk_count % 100 == 0:  # Log every 100 chunks
                        logger.info(f"Received audio chunk #{chunk_count}: {len(audio_chunk_bytes)} bytes")
                    else:
                        logger.debug(f"Received audio chunk #{chunk_count}: {len(audio_chunk_bytes)} bytes")
                except Exception as e:
                    logger.error(f"Error decoding audio chunk: {e}")
                    continue
                
                # Convert PCM chunk to WAV format for STT service
                # We send chunks to STT in real-time for streaming transcription
                wav_chunk = pcm_to_wav(
                    pcm_bytes=audio_chunk_bytes,
                    sample_rate=16000,  # Match VAD sample rate
                    channels=1,  # Mono
                    sample_width=2  # 16-bit
                )
                audio_chunk_base64 = base64.b64encode(wav_chunk).decode('utf-8')
                
                # Send chunk to STT service for streaming transcription
                try:
                    partial_transcription = await stt.process_chunk(session_id, audio_chunk_base64)
                    
                    # Send partial transcription to frontend (for real-time display)
                    if partial_transcription:
                        await websocket.send_json({
                            "type": "partial_transcription",
                            "text": partial_transcription
                        })
                except Exception as e:
                    logger.error(f"Error processing chunk with STT: {e}", exc_info=True)
                    # Continue processing - don't break the connection
                
                # Also process with VAD (for end-of-speech detection)
                speech_segment = vad.process_chunk(audio_chunk_bytes)
                
                # Log VAD state for debugging
                vad_state = vad.get_state()
                if vad_state["speech_started"]:
                    logger.debug(
                        f"VAD state: speech_samples={vad_state['speech_samples']}, "
                        f"silence_samples={vad_state['silence_samples']}, "
                        f"buffer_duration={vad_state['buffer_duration_ms']}ms"
                    )
                
                if speech_segment:
                    # VAD detected end of speech!
                    logger.info(
                        f"Speech ended for session {session_id}, finalizing transcription: "
                        f"{len(speech_segment)} chunks"
                    )
                    
                    # Send status update to client
                    await websocket.send_json({
                        "type": "status",
                        "status": "processing",
                        "message": "Processing your speech..."
                    })
                    
                    # Finalize STT stream and get final transcription
                    try:
                        final_transcription = await stt.finalize_stream(session_id)
                        
                        # Send final transcription to frontend
                        await websocket.send_json({
                            "type": "transcription",
                            "text": final_transcription
                        })
                        
                        # Reset STT stream for next utterance
                        await stt.reset_stream(session_id)
                        await stt.start_stream(session_id)
                        
                        # Process the complete utterance using Orchestrator
                        # Pass transcription directly (skip STT step in orchestrator)
                        await orchestrator.process_streaming(
                            websocket=websocket,
                            session_id=session_id,
                            session_info=session_info,
                            transcription=final_transcription,  # Pass transcription directly
                            speaker=speaker,
                            stt=stt,  # Still pass stt for compatibility, but won't be used
                            llm=llm,
                            tts=tts,
                            context=context,
                            session_manager=session_manager,
                            database=database
                        )
                    except Exception as e:
                        logger.error(f"Error finalizing STT stream: {e}", exc_info=True)
                        # Try to reset stream even if finalization failed
                        try:
                            await stt.reset_stream(session_id)
                            await stt.start_stream(session_id)
                        except:
                            pass
                        
                        # Send error to client
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Error processing speech: {str(e)}"
                        })
            
            elif message_type == "end_call":
                logger.info(f"End call requested for session {session_id}")
                
                # Finalize STT stream if there's any remaining speech
                try:
                    final_transcription = await stt.finalize_stream(session_id)
                    if final_transcription:
                        logger.info("Processing final utterance before ending call")
                        await websocket.send_json({
                            "type": "transcription",
                            "text": final_transcription
                        })
                        await orchestrator.process_streaming(
                            websocket=websocket,
                            session_id=session_id,
                            session_info=session_info,
                            transcription=final_transcription,
                            speaker=speaker,
                            stt=stt,
                            llm=llm,
                            tts=tts,
                            context=context,
                            session_manager=session_manager,
                            database=database
                        )
                except Exception as e:
                    logger.error(f"Error finalizing STT stream on end_call: {e}", exc_info=True)
                
                # Reset STT stream
                try:
                    await stt.reset_stream(session_id)
                except:
                    pass
                
                await websocket.send_json({
                    "type": "call_ended",
                    "message": "Call ended"
                })
                break
            
            elif message_type == "ping":
                # Keep-alive ping
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from session {session_id}")
    except RuntimeError as e:
        # Handle WebSocket connection errors gracefully
        if "WebSocket is not connected" in str(e):
            logger.info(f"WebSocket connection lost for session {session_id}")
        else:
            logger.error(
                f"Runtime error in WebSocket handler for session {session_id}: {e}",
                exc_info=True
            )
    except Exception as e:
        logger.error(
            f"Error in WebSocket handler for session {session_id}: {e}",
            exc_info=True
        )
        try:
            # Only try to send error if WebSocket is still connected
            await websocket.send_json({
                "type": "error",
                "message": f"Error: {str(e)}"
            })
        except (RuntimeError, ConnectionError):
            logger.warning("Could not send error message - WebSocket already disconnected")
        except Exception as send_error:
            logger.warning(f"Error sending error message: {send_error}")
    finally:
        # Cleanup
        active_websocket_connections.discard(websocket)
        
        # Finalize and reset STT stream
        try:
            final_transcription = await stt.finalize_stream(session_id)
            if final_transcription:
                logger.info("Processing final utterance on disconnect")
                try:
                    await websocket.send_json({
                        "type": "transcription",
                        "text": final_transcription
                    })
                    await orchestrator.process_streaming(
                        websocket=websocket,
                        session_id=session_id,
                        session_info=session_info,
                        transcription=final_transcription,
                        speaker=speaker,
                        stt=stt,
                        llm=llm,
                        tts=tts,
                        context=context,
                        session_manager=session_manager,
                        database=database
                    )
                except:
                    pass  # Connection already closed
        except Exception as e:
            logger.warning(f"Error finalizing STT stream on disconnect: {e}")
        
        # Reset STT stream
        try:
            await stt.reset_stream(session_id)
        except:
            pass

