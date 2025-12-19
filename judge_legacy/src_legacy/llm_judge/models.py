# src/llm_judge/models.py

from pydantic import BaseModel
from typing import List, Optional

class Turn(BaseModel):
    role: str  # "manager" или "client"
    text: str

class StartTrainingRequest(BaseModel):
    manager_id: str
    scenario_id: str
    archetype: str
    difficulty: int

class ClientResponseRequest(BaseModel):
    training_id: int
    transcript: List[Turn]

class EvaluateRequest(BaseModel):
    training_id: int

class EvaluationResponse(BaseModel):
    scores: dict
    total_score: int
    critical_errors: list
    feedback_positive: list
    feedback_improvement: list
    recommendations: list
    timecodes: list
    scenario_id: str

class SessionResponse(BaseModel):
    id: int
    manager_id: str
    scenario_id: str
    transcript: List[Turn]
    evaluation: Optional[dict]
    created_at: str