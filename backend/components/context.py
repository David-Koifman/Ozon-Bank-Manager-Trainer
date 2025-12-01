from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class Context:
    """Manages conversation context for each session"""
    
    def __init__(self):
        self.contexts: Dict[str, List[Dict[str, str]]] = {}
        logger.info("Context: Initialized")
    
    def get_context(self, session_id: str, session_info: Optional[Dict]) -> List[Dict[str, str]]:
        """Get context for a session"""
        if session_id not in self.contexts:
            self.contexts[session_id] = []
            logger.info(f"Context: Created new context for session {session_id}")
        
        # Add scenario information to context
        context_data = self.contexts[session_id].copy()
        
        if session_info:
            scenario = session_info.get("scenario", "default")
            context_data.insert(0, {
                "role": "system",
                "content": f"Training scenario: {scenario}. You are a helpful training assistant."
            })
            logger.info(f"Context: Added scenario '{scenario}' to context for session {session_id}")
        
        logger.info(f"Context: Returning context for session {session_id} (length: {len(context_data)})")
        return context_data
    
    def update_context(self, session_id: str, user_input: str, assistant_response: str):
        """Update context with new interaction"""
        if session_id not in self.contexts:
            self.contexts[session_id] = []
            logger.info(f"Context: Created new context for session {session_id}")
        
        self.contexts[session_id].append({
            "role": "user",
            "content": user_input
        })
        self.contexts[session_id].append({
            "role": "assistant",
            "content": assistant_response
        })
        logger.info(f"Context: Updated context for session {session_id} (total messages: {len(self.contexts[session_id])})")
    
    def clear_context(self, session_id: str):
        """Clear context for a session"""
        if session_id in self.contexts:
            del self.contexts[session_id]
            logger.info(f"Context: Cleared context for session {session_id}")
        else:
            logger.warning(f"Context: Cannot clear context - session {session_id} not found")

