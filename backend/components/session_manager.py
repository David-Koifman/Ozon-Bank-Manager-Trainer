from typing import Dict, Optional
from datetime import datetime
import logging

from llm_judge.scenarios import get_scenario_id  # NEW

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages training sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        logger.info("SessionManager: Initialized")

    def _map_ui_to_llm_scenario(self, behavior_archetype: str, difficulty_level: str) -> str:
        """
        Маппинг из UI-понятий (behavior_archetype, difficulty_level)
        в сценарий для LLMJudge (scenario_id из llm_judge.scenarios).

        Пока у нас реально описан только один сценарий:
        - difficulty = "easy"
        - client_archetype = "novice_ip"
        с id = "novice_ip_no_account_easy".

        Остальные комбинации сейчас просто сводим к нему с предупреждением в логах.
        """
        # Маппинг уровней сложности UI → difficulty для сценария
        difficulty_map = {
            "1": "easy",
            "2": "medium",
            "3": "hard",
            "4": "hard",
        }
        # Маппинг архетипов UI → client_archetype
        archetype_map = {
            "novice": "novice_ip",       # новый продавец ИП
            "silent": "novice_ip",       # пока нет отдельного сценария — временно туда же
            "expert": "novice_ip",
            "complainer": "novice_ip",
        }

        difficulty = difficulty_map.get(difficulty_level, "easy")
        client_archetype = archetype_map.get(behavior_archetype, "novice_ip")

        scenario_id = get_scenario_id(difficulty, client_archetype)

        if scenario_id is None:
            logger.warning(
                "SessionManager: no scenario_id found for difficulty=%s, archetype=%s; "
                "fallback to 'novice_ip_no_account_easy'",
                difficulty,
                client_archetype,
            )
            scenario_id = "novice_ip_no_account_easy"

        return scenario_id
    
    def start_session(
        self,
        session_id: str,
        scenario: str = "default",
        speaker: str = "aidar",
        behavior_archetype: str = "novice",
        difficulty_level: str = "1",
    ):
        """Start a new training session"""
        # Выбираем сценарий для LLMJudge
        llm_scenario_id = self._map_ui_to_llm_scenario(
            behavior_archetype=behavior_archetype,
            difficulty_level=difficulty_level,
        )

        logger.info(
            "SessionManager: Starting session %s with scenario='%s', speaker='%s', "
            "behavior='%s', difficulty='%s', llm_scenario_id='%s'",
            session_id,
            scenario,
            speaker,
            behavior_archetype,
            difficulty_level,
            llm_scenario_id,
        )

        self.sessions[session_id] = {
            "scenario": scenario,
            "speaker": speaker,
            "behavior_archetype": behavior_archetype,
            "difficulty_level": difficulty_level,
            "llm_scenario_id": llm_scenario_id,   # NEW
            "started_at": datetime.now().isoformat(),
            "status": "active",
            "interactions": [],
        }
        logger.info(f"SessionManager: Session {session_id} started successfully")
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session information"""
        session = self.sessions.get(session_id)
        if session:
            logger.info(
                "SessionManager: Retrieved session %s (status: %s, llm_scenario_id=%s)",
                session_id,
                session.get("status"),
                session.get("llm_scenario_id"),
            )
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
