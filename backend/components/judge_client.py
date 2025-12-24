import httpx
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

JUDGE_SERVICE_URL = os.getenv("JUDGE_SERVICE_URL", "http://localhost:8003")


class JudgeClient:
    """Client for communicating with the judge service"""
    
    def __init__(self):
        self.service_url = JUDGE_SERVICE_URL
        self.timeout = 120.0  # 2 minutes timeout for LLM judgment
        logger.info(f"JudgeClient: Initialized with service URL: {self.service_url}")
    
    async def judge_session(
        self,
        session_id: str,
        behavior_archetype: str,
        scenario: str,
        difficulty_level: str
    ) -> Optional[Dict]:
        """
        Judge a session's quality.
        
        Args:
            session_id: Session ID to judge
            behavior_archetype: Client archetype
            scenario: Product/scenario
            difficulty_level: Difficulty level
            
        Returns:
            Dict with judgment results or None if error
        """
        try:
            url = f"{self.service_url}/api/judge-session"
            payload = {
                "session_id": session_id,
                "behavior_archetype": behavior_archetype,
                "scenario": scenario,
                "difficulty_level": difficulty_level
            }
            
            logger.info(f"JudgeClient: Judging session {session_id}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"JudgeClient: Successfully judged session {session_id}")
                return result
                
        except httpx.HTTPError as e:
            logger.error(f"JudgeClient: HTTP error judging session {session_id}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"JudgeClient: Error judging session {session_id}: {e}", exc_info=True)
            return None
    
    async def close(self):
        """Close client (no-op for HTTP client)"""
        pass

