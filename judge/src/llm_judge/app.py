# src/llm_judge/app.py

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json
import os
from dotenv import load_dotenv

# Загрузка .env
load_dotenv()

# Импорты из модуля llm_judge
from .judge import LLMJudge
from .backends.ollama_backend import OllamaBackend
from .database import SessionLocal, engine, TrainingSession
from .models import StartTrainingRequest, EvaluateRequest, EvaluationResponse

# ======================
# Модели Pydantic
# ======================

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


# ======================
# Инициализация моделей
# ======================

# Лёгкая модель для генерации ответа клиента
class DialogAgent:
    def __init__(self):
        self.backend = OllamaBackend(model_name="qwen2:1.5b-instruct-q4_K_M")

    def generate(self, transcript: List[dict], archetype: str, difficulty: int) -> str:
        # Упрощённый промпт (в продакшене — из файла)
        prompt = f"""
Ты — ИИ-клиент на звонке от менеджера Ozon.
Архетип: {archetype}
Уровень сложности: {difficulty}
История диалога:
"""
        for turn in transcript:
            role = "Менеджер" if turn["role"] == "manager" else "Клиент"
            prompt += f"{role}: {turn['text']}\n"
        prompt += "Клиент:"
        return self.backend.generate(prompt)


dialog_agent = DialogAgent()

# Тяжёлая модель для оценки
judge = LLMJudge(model_name="qwen2:7b-instruct-q4_K_M")


# ======================
# FastAPI App
# ======================

app = FastAPI(title="Ozon Bank Voice Trainer", version="0.2")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ======================
# Эндпоинты
# ======================

@app.post("/start_training")
def start_training(request: StartTrainingRequest, db: Session = Depends(get_db)):
    session = TrainingSession(
        manager_id=request.manager_id,
        scenario_id=request.scenario_id,
        transcript="[]"
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"training_id": session.id}


@app.post("/generate_client_response")
def generate_client_response(request: ClientResponseRequest, db: Session = Depends(get_db)):
    session = db.query(TrainingSession).filter(TrainingSession.id == request.training_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")

    # Получить текущий транскрипт из БД
    current_transcript = json.loads(session.transcript) if session.transcript else []

    # Подготовить реплики для генерации (только для LLM) — преобразовать в словари
    transcript_list = [turn.dict() for turn in request.transcript]

    # Сгенерировать ответ клиента
    client_text = dialog_agent.generate(transcript_list, "expert", 3)  # временно хардкод

    # Добавить реплики менеджера и клиента в текущий транскрипт
    # Преобразовать объекты Turn в словари перед добавлением
    current_transcript.extend([turn.dict() for turn in request.transcript])  # добавить реплики менеджера
    current_transcript.append({"role": "client", "text": client_text})  # добавить реплику клиента

    # Сохранить обновлённый транскрипт в БД
    session.transcript = json.dumps(current_transcript)
    db.commit()

    return {"role": "client", "text": client_text}


@app.post("/evaluate")
def evaluate_training(request: EvaluateRequest, db: Session = Depends(get_db)):
    session = db.query(TrainingSession).filter(TrainingSession.id == request.training_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")

    # Загрузить транскрипт из БД
    transcript = json.loads(session.transcript) if session.transcript else []

    # Вызвать LLMJudge для оценки
    result = judge.evaluate(transcript, scenario_id=session.scenario_id)

    # Сохранить результат оценки в БД
    session.evaluation = json.dumps(result)
    db.commit()

    return result


@app.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")

    return {
        "id": session.id,
        "manager_id": session.manager_id,
        "scenario_id": session.scenario_id,
        "transcript": json.loads(session.transcript),
        "evaluation": json.loads(session.evaluation) if session.evaluation else None,
    }