from typing import Dict, List, Optional
import logging
from .client_config import CLIENT_CONFIG
from .dialogue_prompts import (
    load_scenario,
    build_system_prompt,
    make_prompt
)

logger = logging.getLogger(__name__)


class Context:
    """Manages conversation context for each session"""
    
    def __init__(self):
        # Store conversation history in format: [{role: "manager"/"client", text: "..."}]
        self.conversations: Dict[str, List[Dict[str, str]]] = {}
        # Store system prompts per session
        self.system_prompts: Dict[str, str] = {}
        # Store loaded scenarios per session
        self.scenarios: Dict[str, Dict] = {}
        logger.info("Context: Initialized")
    
    def _load_and_build_system_prompt(self, session_info: Optional[Dict]) -> str:
        """Load scenario and build system prompt using dialogue_prompts logic"""
        if not session_info:
            return "You are a helpful training assistant."
        
        scenario_name = session_info.get("scenario", "default")
        archetype_id = session_info.get("behavior_archetype", "novice")
        level_id = session_info.get("difficulty_level", "1")
        
        # Try to load scenario from file, fallback to CLIENT_CONFIG
        try:
            scenario, md_prompt = load_scenario(scenario_name)
            logger.info(f"Context: Loaded scenario '{scenario_name}' from file")
        except FileNotFoundError as e:
            logger.warning(f"Context: Scenario file not found, using CLIENT_CONFIG fallback: {e}")
            # Fallback: construct scenario dict from CLIENT_CONFIG
            scenario = {
                "scenario_id": scenario_name,
                "title": "Сценарий тренировки",
                "client_profile": CLIENT_CONFIG.get("client_profile", {}),
                "dialog_objectives": CLIENT_CONFIG.get("dialog_objectives", {}),
                "compliance_requirements": {},
                "client_behavior_presets": CLIENT_CONFIG.get("client_behavior_presets", {}),
                "aida_flow": {}
            }
            md_prompt = ""
        
        # Store scenario for later use
        self.scenarios[session_info.get("session_id", "")] = scenario
        
        # Build system prompt using dialogue_prompts logic
        system_prompt = build_system_prompt(
            scenario=scenario,
            md_prompt=md_prompt,
            archetype_id=archetype_id,
            level_id=level_id
        )
        
        return system_prompt
    
    def get_conversation(self, session_id: str) -> List[Dict[str, str]]:
        """Get conversation history in format [{role: "manager"/"client", text: "..."}]"""
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        return self.conversations[session_id].copy()
    
    def get_system_prompt(self, session_id: str) -> Optional[str]:
        """Get system prompt for a session"""
        return self.system_prompts.get(session_id)
    
    def get_context(self, session_id: str, session_info: Optional[Dict]) -> Dict:
        """
        Get context for a session.
        Returns dict with 'system_prompt' and 'conversation' keys.
        This format is used by LLM component to build prompts.
        """
        # Initialize conversation if needed
        if session_id not in self.conversations:
            self.conversations[session_id] = []
            logger.info(f"Context: Created new conversation for session {session_id}")
        
        # Build system prompt if it doesn't exist and we have session_info
        if session_id not in self.system_prompts and session_info:
            # Add session_id to session_info for scenario storage
            if "session_id" not in session_info:
                session_info = {**session_info, "session_id": session_id}
            system_prompt = self._load_and_build_system_prompt(session_info)
            self.system_prompts[session_id] = system_prompt
            logger.info(f"Context: Built system prompt for session {session_id}")
        
        return {
            "system_prompt": self.system_prompts.get(session_id, ""),
            "conversation": self.conversations[session_id].copy()
        }
    
    def update_context(self, session_id: str, user_input: str, assistant_response: str):
        """Update conversation with new interaction (manager input and client response)"""
        if session_id not in self.conversations:
            self.conversations[session_id] = []
            logger.info(f"Context: Created new conversation for session {session_id}")
        
        # Add manager turn
        self.conversations[session_id].append({
            "role": "manager",
            "text": user_input
        })
        # Add client turn
        self.conversations[session_id].append({
            "role": "client",
            "text": assistant_response
        })
        logger.info(f"Context: Updated conversation for session {session_id} (total turns: {len(self.conversations[session_id])})")
    
    def clear_context(self, session_id: str):
        """Clear context for a session"""
        cleared = False
        if session_id in self.conversations:
            del self.conversations[session_id]
            cleared = True
        if session_id in self.system_prompts:
            del self.system_prompts[session_id]
        if session_id in self.scenarios:
            del self.scenarios[session_id]
        
        if cleared:
            logger.info(f"Context: Cleared context for session {session_id}")
        else:
            logger.warning(f"Context: Cannot clear context - session {session_id} not found")

