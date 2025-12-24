from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Text, DateTime, Integer, select
from datetime import datetime
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

Base = declarative_base()


class STTTranscription(Base):
    """Model for STT transcriptions (matches backend schema)"""
    __tablename__ = "stt_transcriptions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    transcription = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LLMResponse(Base):
    """Model for LLM responses (matches backend schema)"""
    __tablename__ = "llm_responses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_input = Column(Text, nullable=False)  # The STT transcription that triggered this response
    response_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Database:
    """Database connection and operations manager for judge service"""
    
    def __init__(self):
        self.engine = None
        self.async_session = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize database connection"""
        if self._initialized:
            return
        
        # Use the same database URL format as backend
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://operator_trainer:operator_trainer_pass@localhost:5432/operator_trainer_db"
        )
        
        # Convert postgresql:// to postgresql+asyncpg:// if needed
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        logger.info(f"Database: Connecting to database...")
        try:
            self.engine = create_async_engine(
                database_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20
            )
            
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
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
    
    async def get_session_transcript(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get transcript for a session by combining STT transcriptions and LLM responses.
        
        Returns a list of turns in chronological order:
        [
            {"role": "manager", "text": "..."},
            {"role": "client", "text": "..."},
            ...
        ]
        """
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        try:
            async with self.async_session() as session:
                # Get all STT transcriptions for this session (ordered by created_at)
                stt_query = select(STTTranscription).where(
                    STTTranscription.session_id == session_id
                ).order_by(STTTranscription.created_at)
                stt_result = await session.execute(stt_query)
                stt_records = stt_result.scalars().all()
                
                # Get all LLM responses for this session (ordered by created_at)
                llm_query = select(LLMResponse).where(
                    LLMResponse.session_id == session_id
                ).order_by(LLMResponse.created_at)
                llm_result = await session.execute(llm_query)
                llm_records = llm_result.scalars().all()
                
                # Build transcript by interleaving STT and LLM responses
                # Each STT transcription is followed by its corresponding LLM response
                transcript = []
                
                # Create a map of user_input -> LLM response for matching
                llm_map = {llm.user_input: llm.response_text for llm in llm_records}
                
                # Process STT transcriptions in order
                for stt in stt_records:
                    # Add manager turn (STT transcription)
                    transcript.append({
                        "role": "manager",
                        "text": stt.transcription
                    })
                    
                    # Find corresponding LLM response (match by user_input)
                    # The LLMResponse.user_input should match STTTranscription.transcription
                    if stt.transcription in llm_map:
                        transcript.append({
                            "role": "client",
                            "text": llm_map[stt.transcription]
                        })
                    else:
                        # Log warning if no matching LLM response found
                        logger.warning(
                            f"No matching LLM response found for STT transcription: "
                            f"{stt.transcription[:50]}... (session_id={session_id})"
                        )
                
                logger.info(f"Database: Retrieved transcript for session {session_id}: {len(transcript)} turns")
                return transcript
                
        except Exception as e:
            logger.error(f"Database: Error getting transcript for session {session_id}: {str(e)}", exc_info=True)
            raise
