"""
FastAPI application for judge service.
Evaluates training sessions using LLM.
"""

import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from .database import Database
from .judge import LLMJudge
from .scenarios import get_scenario_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Judge Service",
    description="Service for evaluating training sessions using LLM",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
database = Database()
judge = None


@app.on_event("startup")
async def startup():
    """Initialize database and judge on startup"""
    global judge
    try:
        await database.initialize()
        
        # Log LLM provider configuration
        llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
        logger.info(f"Judge service: Using LLM provider: {llm_provider}")
        
        if llm_provider == "ollama":
            ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            ollama_model = os.getenv("OLLAMA_MODEL", "qwen2:7b-instruct-q4_K_M")
            logger.info(f"Judge service: Ollama config - base_url={ollama_base_url}, model={ollama_model}")
        else:
            openrouter_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
            if not openrouter_api_key:
                logger.warning("Judge service: OPENROUTER_API_KEY not set. LLM will not work.")
            logger.info(f"Judge service: OpenRouter config - model={openrouter_model}")
        
        judge = LLMJudge()
        logger.info("Judge service started successfully")
    except Exception as e:
        logger.error(f"Failed to start judge service: {e}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    await database.close()


# Request/Response models
class JudgeSessionRequest(BaseModel):
    """Request model for judging a session"""
    session_id: str
    behavior_archetype: str  # e.g., "novice", "silent", "expert", "complainer"
    scenario: str  # e.g., "customer_service", "technical_support", "sales"
    difficulty_level: str  # e.g., "1", "2", "3", "4"


class JudgeSessionResponse(BaseModel):
    """Response model for judge session evaluation"""
    session_id: str
    scenario_id: str
    scores: Dict[str, Any]
    total_score: float
    critical_errors: List[str]
    feedback_positive: List[str]
    feedback_improvement: List[str]
    recommendations: List[str]
    timecodes: List[Any]
    client_profile: Dict[str, Any]
    relevant_criteria: List[str]
    model_used: str
    judge_backend: str
    error: Optional[str] = None
    details: Optional[str] = None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "judge-service",
        "status": "running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
    judge_backend = getattr(judge, "backend_name", "unknown") if judge else "not initialized"
    
    return {
        "status": "healthy",
        "database": "connected" if database._initialized else "disconnected",
        "judge": "initialized" if judge is not None else "not initialized",
        "llm_provider": llm_provider,
        "judge_backend": judge_backend
    }


@app.post("/api/judge-session", response_model=JudgeSessionResponse)
async def judge_session(request: JudgeSessionRequest):
    """
    Judge a training session.
    
    Fetches transcript from database and evaluates it using LLM judge.
    """
    try:
        logger.info(
            f"Judging session {request.session_id} "
            f"(scenario={request.scenario}, archetype={request.behavior_archetype}, "
            f"difficulty={request.difficulty_level})"
        )
        
        # Get transcript from database
        try:
            transcript = await database.get_session_transcript(request.session_id)
        except Exception as e:
            logger.error(f"Failed to get transcript for session {request.session_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=404,
                detail=f"Session {request.session_id} not found or has no transcript"
            )
        
        if not transcript:
            raise HTTPException(
                status_code=400,
                detail=f"Session {request.session_id} has no transcript data"
            )
        
        logger.info(f"Retrieved transcript with {len(transcript)} turns for session {request.session_id}")
        
        # Map parameters to scenario_id
        # Convert difficulty_level ("1", "2", "3", "4") to difficulty ("easy", "medium", "hard")
        difficulty_map = {
            "1": "easy",
            "2": "medium",
            "3": "hard",
            "4": "hard"  # Level 4 is also hard
        }
        difficulty = difficulty_map.get(request.difficulty_level, "easy")
        
        # Map behavior_archetype to client_archetype format expected by scenarios
        # The archetype might already be in the right format, but we handle common cases
        client_archetype = request.behavior_archetype
        if client_archetype == "novice":
            client_archetype = "novice_ip"  # Default mapping
        elif client_archetype == "expert":
            client_archetype = "expert_ip"  # Default mapping
        # Add more mappings as needed
        
        # Get scenario_id from difficulty and client_archetype
        scenario_id = get_scenario_id(difficulty, client_archetype)
        
        if not scenario_id:
            # Fallback to default scenario if mapping fails
            logger.warning(
                f"No scenario found for difficulty={difficulty}, "
                f"archetype={client_archetype}, using default"
            )
            scenario_id = "novice_ip_no_account_easy"
        
        logger.info(f"Using scenario_id: {scenario_id}")
        
        # Evaluate using LLM judge
        try:
            evaluation = judge.evaluate(transcript, scenario_id=scenario_id)
        except Exception as e:
            logger.error(f"LLM evaluation failed for session {request.session_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"LLM evaluation failed: {str(e)}"
            )
        
        # Build response
        response = JudgeSessionResponse(
            session_id=request.session_id,
            scenario_id=scenario_id,
            scores=evaluation.get("scores", {}),
            total_score=evaluation.get("total_score", 0.0),
            critical_errors=evaluation.get("critical_errors", []),
            feedback_positive=evaluation.get("feedback_positive", []),
            feedback_improvement=evaluation.get("feedback_improvement", []),
            recommendations=evaluation.get("recommendations", []),
            timecodes=evaluation.get("timecodes", []),
            client_profile=evaluation.get("client_profile", {}),
            relevant_criteria=evaluation.get("relevant_criteria", []),
            model_used=evaluation.get("model_used", "unknown"),
            judge_backend=evaluation.get("judge_backend", "unknown"),
            error=evaluation.get("error"),
            details=evaluation.get("details")
        )
        
        logger.info(
            f"Successfully judged session {request.session_id}: "
            f"total_score={response.total_score}, "
            f"critical_errors={len(response.critical_errors)}"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error judging session {request.session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

