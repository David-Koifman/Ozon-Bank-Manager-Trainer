from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Text, DateTime, Integer
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()


class STTTranscription(Base):
    """Model for storing STT transcriptions"""
    __tablename__ = "stt_transcriptions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    transcription = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, server_default=None)
    
    def __repr__(self):
        return f"<STTTranscription(id={self.id}, session_id={self.session_id}, created_at={self.created_at})>"


class LLMResponse(Base):
    """Model for storing LLM responses"""
    __tablename__ = "llm_responses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_input = Column(Text, nullable=False)  # The STT transcription that triggered this response
    response_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, server_default=None)
    
    def __repr__(self):
        return f"<LLMResponse(id={self.id}, session_id={self.session_id}, created_at={self.created_at})>"


class Database:
    """Database connection and operations manager"""
    
    def __init__(self):
        self.engine = None
        self.async_session = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize database connection and create tables"""
        if self._initialized:
            return
        
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://operator_trainer:operator_trainer_pass@localhost:5432/operator_trainer_db"
        )
        
        logger.info(f"Database: Connecting to database...")
        try:
            self.engine = create_async_engine(
                database_url,
                echo=False,  # Set to True for SQL query logging
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20
            )
            
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            self._initialized = True
            logger.info("Database: Initialized successfully")
        except Exception as e:
            logger.error(f"Database: Failed to initialize: {str(e)}", exc_info=True)
            raise
    
    async def close(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database: Connection closed")
    
    async def log_stt_transcription(self, session_id: str, transcription: str):
        """Log STT transcription to database"""
        if not self._initialized:
            logger.warning("Database: Not initialized, skipping STT transcription log")
            return
        
        try:
            async with self.async_session() as session:
                stt_record = STTTranscription(
                    session_id=session_id,
                    transcription=transcription,
                    created_at=datetime.utcnow()
                )
                session.add(stt_record)
                await session.commit()
                logger.info(f"Database: Logged STT transcription for session {session_id}")
        except Exception as e:
            logger.error(f"Database: Error logging STT transcription: {str(e)}", exc_info=True)
    
    async def log_llm_response(self, session_id: str, user_input: str, response_text: str):
        """Log LLM response to database"""
        if not self._initialized:
            logger.warning("Database: Not initialized, skipping LLM response log")
            return
        
        try:
            async with self.async_session() as session:
                llm_record = LLMResponse(
                    session_id=session_id,
                    user_input=user_input,
                    response_text=response_text,
                    created_at=datetime.utcnow()
                )
                session.add(llm_record)
                await session.commit()
                logger.info(f"Database: Logged LLM response for session {session_id}")
        except Exception as e:
            logger.error(f"Database: Error logging LLM response: {str(e)}", exc_info=True)

