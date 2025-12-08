from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# Отдельный URL для judge, чтобы не конфликтовать с async DATABASE_URL
DATABASE_URL = os.getenv(
    "JUDGE_DATABASE_URL",
    os.getenv("DATABASE_URL_SYNC", "postgresql://user:pass@localhost/ozon_voice")
)

engine = create_engine(
    DATABASE_URL,
    connect_args={}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(String, index=True)
    scenario_id = Column(String)
    transcript = Column(Text)   # JSON-строка с репликами
    evaluation = Column(Text)   # JSON-строка с оценкой от judge
    created_at = Column(DateTime, default=datetime.utcnow)


# Создание таблиц при импорте (можно потом вынести в init)
Base.metadata.create_all(bind=engine)
