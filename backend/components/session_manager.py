from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages training sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        logger.info("SessionManager: Initialized")
    
    def start_session(self, session_id: str, scenario: str = "default", speaker: str = "aidar", behavior_archetype: str = "novice", difficulty_level: str = "1"):
        """Start a new training session"""
        logger.info(f"SessionManager: Starting session {session_id} with scenario '{scenario}', speaker '{speaker}', behavior '{behavior_archetype}', difficulty '{difficulty_level}'")
        self.sessions[session_id] = {
            "scenario": scenario,
            "speaker": speaker,
            "behavior_archetype": behavior_archetype,
            "difficulty_level": difficulty_level,
            "started_at": datetime.now().isoformat(),
            "status": "active",
            "interactions": [],
            "stt_transcriptions": [],  # Store transcriptions for batch database write
            "llm_responses": []  # Store LLM responses for batch database write
        }
        logger.info(f"SessionManager: Session {session_id} started successfully")
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session information"""
        session = self.sessions.get(session_id)
        if session:
            logger.info(f"SessionManager: Retrieved session {session_id} (status: {session.get('status')})")
        else:
            logger.warning(f"SessionManager: Session {session_id} not found")
        return session
    
    def end_session(self, session_id: str):
        """End a training session"""
        if session_id in self.sessions:
            logger.info(f"SessionManager: Ending session {session_id}")
            self.sessions[session_id]["status"] = "ended"
            self.sessions[session_id]["ended_at"] = datetime.now().isoformat()
            logger.info(f"SessionManager: Session {session_id} ended")
        else:
            logger.warning(f"SessionManager: Cannot end session {session_id} - not found")
    
    def add_interaction(self, session_id: str, interaction: Dict):
        """Add an interaction to the session"""
        if session_id in self.sessions:
            self.sessions[session_id]["interactions"].append(interaction)
            logger.info(f"SessionManager: Added interaction to session {session_id}")
        else:
            logger.warning(f"SessionManager: Cannot add interaction - session {session_id} not found")
    
    def add_stt_transcription(self, session_id: str, transcription: str):
        """Add STT transcription to session (for batch database write)"""
        if session_id in self.sessions:
            self.sessions[session_id]["stt_transcriptions"].append(transcription)
            logger.debug(f"SessionManager: Stored STT transcription for session {session_id} (total: {len(self.sessions[session_id]['stt_transcriptions'])})")
        else:
            logger.warning(f"SessionManager: Cannot add STT transcription - session {session_id} not found")
    
    def add_llm_response(self, session_id: str, user_input: str, response_text: str):
        """Add LLM response to session (for batch database write)"""
        if session_id in self.sessions:
            self.sessions[session_id]["llm_responses"].append({
                "user_input": user_input,
                "response_text": response_text
            })
            logger.debug(f"SessionManager: Stored LLM response for session {session_id} (total: {len(self.sessions[session_id]['llm_responses'])})")
        else:
            logger.warning(f"SessionManager: Cannot add LLM response - session {session_id} not found")
    
    def get_pending_data(self, session_id: str) -> Dict:
        """Get all pending transcriptions and responses for a session"""
        if session_id in self.sessions:
            return {
                "stt_transcriptions": self.sessions[session_id].get("stt_transcriptions", []),
                "llm_responses": self.sessions[session_id].get("llm_responses", [])
            }
        return {"stt_transcriptions": [], "llm_responses": []}
    
    def clear_pending_data(self, session_id: str):
        """Clear pending data after writing to database"""
        if session_id in self.sessions:
            self.sessions[session_id]["stt_transcriptions"] = []
            self.sessions[session_id]["llm_responses"] = []
            logger.debug(f"SessionManager: Cleared pending data for session {session_id}")

