import os
import uuid
import logging
import asyncio
from typing import List, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

from components.orchestrator import Orchestrator
from components.session_manager import SessionManager
from components.context import Context
from components.stt_client import STTClient
from components.llm import LLM
from components.tts_client import TTSClient
from components.database import Database
from llm_judge.judge import LLMJudge

# Load .env (ищет вверх по дереву)
load_dotenv(find_dotenv())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Operator Voice Trainer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()
session_manager = SessionManager()
context = Context()
stt = STTClient()
llm = LLM()
tts = TTSClient()
database = Database()

_JUDGE: LLMJudge | None = None
JUDGE_TIMEOUT_SEC = float(os.getenv("JUDGE_TIMEOUT_SEC", "45"))


def get_judge() -> LLMJudge:
    global _JUDGE
    if _JUDGE is None:
        _JUDGE = LLMJudge()
    return _JUDGE


@app.on_event("startup")
async def startup():
    logger.info("Starting services...")
    try:
        logger.info("Initializing database...")
        await database.initialize()
        logger.info("Backend services initialized successfully!")
    except Exception as e:
        logger.error(f"Error initializing services: {str(e)}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown():
    await database.close()
    await stt.close()
    await tts.close()


class StartTrainingRequest(BaseModel):
    scenario: str = "default"
    speaker: str = "aidar"
    behavior_archetype: str = "novice"
    difficulty_level: str = "1"


class AudioInputRequest(BaseModel):
    audio: str
    session_id: str


class EndTrainingRequest(BaseModel):
    session_id: str


class TranscriptReplica(BaseModel):
    role: Literal["manager", "client"]
    text: str


class JudgeEvaluateRequest(BaseModel):
    session_id: str
    transcript: List[TranscriptReplica]


@app.post("/api/start-training")
async def start_training(request: StartTrainingRequest):
    try:
        session_id = str(uuid.uuid4())
        logger.info("Starting training session %s with scenario '%s'", session_id, request.scenario)

        message = {
            "action": "start_training",
            "scenario": request.scenario,
            "speaker": request.speaker,
            "behavior_archetype": request.behavior_archetype,
            "difficulty_level": request.difficulty_level,
        }

        response = await orchestrator.process(
            message=message,
            session_id=session_id,
            session_manager=session_manager,
            context=context,
            stt=stt,
            llm=llm,
            tts=tts,
            database=database,
        )

        if isinstance(response, dict) and "session_id" not in response:
            response["session_id"] = session_id

        return response

    except Exception as e:
        logger.error("Error starting training session: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error starting training session: {str(e)}")


@app.post("/api/audio-input")
async def audio_input(request: AudioInputRequest):
    try:
        if not request.audio:
            raise HTTPException(status_code=400, detail="Audio data is required")
        if not request.session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")

        import base64
        try:
            decoded = base64.b64decode(request.audio, validate=True)
            if len(decoded) == 0:
                raise HTTPException(status_code=400, detail="Audio data is empty")
            logger.info("Received audio input for session %s (decoded size: %s bytes)", request.session_id, len(decoded))
        except Exception as e:
            logger.error("Invalid base64 audio data: %s", str(e))
            raise HTTPException(status_code=400, detail=f"Invalid audio format: {str(e)}")

        message = {"action": "audio_input", "audio": request.audio, "session_id": request.session_id}

        response = await orchestrator.process(
            message=message,
            session_id=request.session_id,
            session_manager=session_manager,
            context=context,
            stt=stt,
            llm=llm,
            tts=tts,
            database=database,
        )

        if not isinstance(response, dict):
            logger.error("Invalid response type from orchestrator: %s", type(response))
            raise HTTPException(status_code=500, detail="Invalid response from orchestrator")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing audio input: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")


@app.post("/api/end-training")
async def end_training(request: EndTrainingRequest):
    logger.info("Ending training session %s", request.session_id)

    message = {"action": "end_training", "session_id": request.session_id}

    response = await orchestrator.process(
        message=message,
        session_id=request.session_id,
        session_manager=session_manager,
        context=context,
        stt=stt,
        llm=llm,
        tts=tts,
        database=database,
    )

    return response


@app.post("/api/judge/evaluate")
async def judge_evaluate(request: JudgeEvaluateRequest):
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} not found")

    llm_scenario_id = session.get("llm_scenario_id") or "novice_ip_no_account_easy"

    transcript = [r.model_dump() for r in request.transcript]

    try:
        judge = get_judge()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Judge backend not configured: {e}")

    try:
        # evaluate() синхронный — уводим в отдельный поток + ставим таймаут
        result = await asyncio.wait_for(
            asyncio.to_thread(judge.evaluate, transcript, llm_scenario_id),
            timeout=JUDGE_TIMEOUT_SEC,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Judge timeout after {JUDGE_TIMEOUT_SEC}s")
    except Exception as e:
        logger.error("Judge evaluate failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Judge evaluate failed: {e}")


@app.get("/")
async def root():
    return {"message": "Operator Voice Trainer Backend", "status": "running"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "stt": {"service_url": getattr(stt, "service_url", None), "type": "http_client"},
        "tts": {"service_url": getattr(tts, "service_url", None), "type": "http_client"},
        "llm": {"api_key_set": bool(getattr(llm, "api_key", None))},
        "database": {"initialized": getattr(database, "_initialized", False)},
        "judge": {
            "backend": os.getenv("JUDGE_BACKEND") or ("openrouter" if os.getenv("OPENROUTER_API_KEY") else "mock"),
            "timeout_sec": JUDGE_TIMEOUT_SEC,
        },
    }

