# src/llm_judge/database.py

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime

# Загрузка переменных окружения
from dotenv import load_dotenv
load_dotenv()

# Настройка подключения к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/ozon_voice")

engine = create_engine(
    DATABASE_URL,
    connect_args={}  # psycopg2 сам обрабатывает соединения
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(String, index=True)
    scenario_id = Column(String)
    transcript = Column(Text)  # JSON-строка с репликами
    evaluation = Column(Text)  # JSON-строка с оценкой от judge
    created_at = Column(DateTime, default=datetime.utcnow)

# ✅ Создание таблиц при запуске
Base.metadata.create_all(bind=engine)