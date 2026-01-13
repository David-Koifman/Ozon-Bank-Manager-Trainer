from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Enum as SQLEnum
from datetime import datetime
import os
import logging
import enum

logger = logging.getLogger(__name__)

Base = declarative_base()


class UserRole(enum.Enum):
    """User roles in the system"""
    MANAGER = "manager"
    COACH = "coach"


class User(Base):
    """Model for users (managers and coaches)"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.MANAGER)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    sessions = relationship("TrainingSession", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role.value})>"


class TrainingSession(Base):
    """Model for training sessions"""
    __tablename__ = "training_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scenario = Column(String(255), nullable=False)
    speaker = Column(String(255), nullable=False)
    behavior_archetype = Column(String(255), nullable=False)
    difficulty_level = Column(String(255), nullable=False)
    status = Column(String(50), default="active", nullable=False)
    judgment = Column(Text, nullable=True)  # JSON string of judgment results
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    
    def __repr__(self):
        return f"<TrainingSession(id={self.id}, session_id={self.session_id}, user_id={self.user_id})>"


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
    
    async def batch_log_session_data(self, session_id: str, stt_transcriptions: list, llm_responses: list):
        """Batch log all STT transcriptions and LLM responses for a session"""
        if not self._initialized:
            logger.warning("Database: Not initialized, skipping batch log")
            return
        
        import time
        start_time = time.time()
        
        try:
            async with self.async_session() as session:
                # Log all STT transcriptions
                stt_start = time.time()
                for transcription in stt_transcriptions:
                    stt_record = STTTranscription(
                        session_id=session_id,
                        transcription=transcription,
                        created_at=datetime.utcnow()
                    )
                    session.add(stt_record)
                
                # Log all LLM responses
                llm_start = time.time()
                for response in llm_responses:
                    llm_record = LLMResponse(
                        session_id=session_id,
                        user_input=response["user_input"],
                        response_text=response["response_text"],
                        created_at=datetime.utcnow()
                    )
                    session.add(llm_record)
                
                # Commit all records at once
                commit_start = time.time()
                await session.commit()
                commit_time = time.time() - commit_start
                
                total_time = time.time() - start_time
                stt_time = llm_start - stt_start
                llm_time = commit_start - llm_start
                
                logger.info(
                    f"Database: Batch logged session {session_id} - "
                    f"STT: {len(stt_transcriptions)} records ({stt_time:.3f}s), "
                    f"LLM: {len(llm_responses)} records ({llm_time:.3f}s), "
                    f"Commit: {commit_time:.3f}s, "
                    f"Total: {total_time:.3f}s"
                )
        except Exception as e:
            logger.error(f"Database: Error batch logging session data: {str(e)}", exc_info=True)
            raise
    
    # User management methods
    async def create_user(self, email: str, name: str, role: UserRole = UserRole.MANAGER) -> User:
        """Create a new user"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        try:
            async with self.async_session() as session:
                user = User(email=email, name=name, role=role)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info(f"Database: Created user {email} with role {role.value}")
                return user
        except Exception as e:
            logger.error(f"Database: Error creating user: {str(e)}", exc_info=True)
            raise
    
    async def get_user_by_email(self, email: str) -> User:
        """Get user by email"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select
        try:
            async with self.async_session() as session:
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()
                return user
        except Exception as e:
            logger.error(f"Database: Error getting user by email: {str(e)}", exc_info=True)
            raise
    
    async def get_user_by_id(self, user_id: int) -> User:
        """Get user by ID"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select
        try:
            async with self.async_session() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                return user
        except Exception as e:
            logger.error(f"Database: Error getting user by ID: {str(e)}", exc_info=True)
            raise
    
    # Training session methods
    async def create_training_session(
        self, 
        session_id: str, 
        user_id: int, 
        scenario: str, 
        speaker: str, 
        behavior_archetype: str, 
        difficulty_level: str
    ) -> TrainingSession:
        """Create a new training session"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        try:
            async with self.async_session() as session:
                training_session = TrainingSession(
                    session_id=session_id,
                    user_id=user_id,
                    scenario=scenario,
                    speaker=speaker,
                    behavior_archetype=behavior_archetype,
                    difficulty_level=difficulty_level,
                    status="active"
                )
                session.add(training_session)
                await session.commit()
                await session.refresh(training_session)
                logger.info(f"Database: Created training session {session_id} for user {user_id}")
                return training_session
        except Exception as e:
            logger.error(f"Database: Error creating training session: {str(e)}", exc_info=True)
            raise
    
    async def get_training_session(self, session_id: str) -> TrainingSession:
        """Get training session by session_id"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(TrainingSession).where(TrainingSession.session_id == session_id)
                )
                training_session = result.scalar_one_or_none()
                return training_session
        except Exception as e:
            logger.error(f"Database: Error getting training session: {str(e)}", exc_info=True)
            raise
    
    async def update_training_session_judgment(self, session_id: str, judgment: str):
        """Update training session with judgment results"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select
        from datetime import datetime
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(TrainingSession).where(TrainingSession.session_id == session_id)
                )
                training_session = result.scalar_one_or_none()
                if training_session:
                    training_session.judgment = judgment
                    training_session.status = "completed"
                    training_session.ended_at = datetime.utcnow()
                    await session.commit()
                    logger.info(f"Database: Updated training session {session_id} with judgment")
        except Exception as e:
            logger.error(f"Database: Error updating training session judgment: {str(e)}", exc_info=True)
            raise
    
    async def get_user_sessions(self, user_id: int, limit: int = 100) -> list:
        """Get all training sessions for a user"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select, desc
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(TrainingSession)
                    .where(TrainingSession.user_id == user_id)
                    .order_by(desc(TrainingSession.created_at))
                    .limit(limit)
                )
                sessions = result.scalars().all()
                return sessions
        except Exception as e:
            logger.error(f"Database: Error getting user sessions: {str(e)}", exc_info=True)
            raise
    
    async def get_all_sessions(self, limit: int = 100) -> list:
        """Get all training sessions (for coaches)"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select, desc
        from sqlalchemy.orm import joinedload
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(TrainingSession)
                    .options(joinedload(TrainingSession.user))
                    .order_by(desc(TrainingSession.created_at))
                    .limit(limit)
                )
                sessions = result.unique().scalars().all()
                return sessions
        except Exception as e:
            logger.error(f"Database: Error getting all sessions: {str(e)}", exc_info=True)
            raise
    
    async def get_sessions_statistics(self, user_id: int = None) -> dict:
        """Get statistics about training sessions"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select, func, case
        try:
            async with self.async_session() as session:
                query = select(TrainingSession)
                if user_id:
                    query = query.where(TrainingSession.user_id == user_id)
                
                result = await session.execute(query)
                sessions = result.scalars().all()
                
                total_sessions = len(sessions)
                completed_sessions = sum(1 for s in sessions if s.status == "completed")
                active_sessions = sum(1 for s in sessions if s.status == "active")
                
                # Calculate average scores if judgments exist
                scores = []
                for s in sessions:
                    if s.judgment:
                        try:
                            import json
                            judgment_data = json.loads(s.judgment)
                            if "total_score" in judgment_data:
                                scores.append(judgment_data["total_score"])
                        except:
                            pass
                
                avg_score = sum(scores) / len(scores) if scores else 0
                
                return {
                    "total_sessions": total_sessions,
                    "completed_sessions": completed_sessions,
                    "active_sessions": active_sessions,
                    "average_score": round(avg_score, 2),
                    "sessions_with_scores": len(scores)
                }
        except Exception as e:
            logger.error(f"Database: Error getting sessions statistics: {str(e)}", exc_info=True)
            raise
    
    async def get_all_users_statistics(self) -> list:
        """Get statistics for all users (grouped by user)"""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        from sqlalchemy import select
        try:
            async with self.async_session() as session:
                # Get all users (managers and coaches)
                users_result = await session.execute(select(User))
                users = users_result.scalars().all()
                
                # Get statistics for each user
                user_stats = []
                for user in users:
                    stats = await self.get_sessions_statistics(user_id=user.id)
                    user_stats.append({
                        "user": {
                            "id": user.id,
                            "email": user.email,
                            "name": user.name,
                            "role": user.role.value
                        },
                        "statistics": stats
                    })
                
                return user_stats
        except Exception as e:
            logger.error(f"Database: Error getting all users statistics: {str(e)}", exc_info=True)
            raise

