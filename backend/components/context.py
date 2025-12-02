from typing import Dict, List, Optional
import logging
from .client_config import CLIENT_CONFIG

logger = logging.getLogger(__name__)


class Context:
    """Manages conversation context for each session"""
    
    def __init__(self):
        self.contexts: Dict[str, List[Dict[str, str]]] = {}
        logger.info("Context: Initialized")
    
    def _build_system_prompt(self, session_info: Optional[Dict]) -> str:
        """Build comprehensive system prompt based on client profile, behavior archetype, and difficulty level"""
        if not session_info:
            return "You are a helpful training assistant."
        
        # Get client profile and dialog objectives
        client_profile = CLIENT_CONFIG.get("client_profile", {})
        dialog_objectives = CLIENT_CONFIG.get("dialog_objectives", {})
        
        # Get behavior archetype and difficulty level from session
        behavior_archetype_key = session_info.get("behavior_archetype", "novice")
        difficulty_level_key = session_info.get("difficulty_level", "1")
        
        # Get archetype and difficulty configurations
        archetypes = CLIENT_CONFIG.get("client_behavior_presets", {}).get("archetypes", {})
        difficulty_levels = CLIENT_CONFIG.get("client_behavior_presets", {}).get("difficulty_levels", {})
        
        behavior_config = archetypes.get(behavior_archetype_key, archetypes.get("novice", {}))
        difficulty_config = difficulty_levels.get(difficulty_level_key, difficulty_levels.get("1", {}))
        
        # Build conditional text parts
        sample_phrases_text = ""
        if behavior_config.get('sample_phrases'):
            sample_phrases_text = f"- Примеры фраз, которые ты можешь использовать: {', '.join(behavior_config.get('sample_phrases', []))}\n"
        
        secondary_goals_text = ""
        if dialog_objectives.get('secondary_goals'):
            secondary_goals_text = "- Вторичные цели:\n"
            for goal in dialog_objectives.get('secondary_goals', []):
                secondary_goals_text += f"  - {goal}\n"
        
        traps_text = ""
        if difficulty_config.get('traps'):
            traps_text = f"- Используй следующие ловушки/возражения: {', '.join(difficulty_config.get('traps', []))}\n"
        
        emotional_pressure_text = ""
        if difficulty_config.get('emotional_pressure'):
            emotional_pressure_text = f"- Эмоциональное давление: {difficulty_config.get('emotional_pressure')}\n"
        
        # Build system prompt as single text
        prompt = f"""Ты играешь роль клиента B2B банка для тренировки оператора отдела продаж.

## Информация о клиенте:
- Статус: {client_profile.get('status', 'ИП')}
- Ситуация: {client_profile.get('situation', '')}
- Важная деталь: {client_profile.get('key_trait', '')}

## Твой характер и поведение:
- Тип: {behavior_config.get('name', 'Новичок')}
- Личность: {behavior_config.get('personality', '')}
- Эмоциональный тон: {behavior_config.get('emotional_tone', 'neutral')}
- Частота возражений: {behavior_config.get('objection_frequency', 'low')}
{sample_phrases_text}## Уровень сложности:
- Название: {difficulty_config.get('name', 'Базовый')}
- Количество возражений: {difficulty_config.get('objections_count', 1)}
- Сложность: {difficulty_config.get('complexity', 'basic')}
- {'Разрешено уходить от темы разговора' if difficulty_config.get('drift_allowed') else 'НЕ разрешено уходить от темы разговора'}
- {'Задавай уточняющие вопросы' if difficulty_config.get('follow_up_questions') else 'НЕ задавай уточняющие вопросы'}
{traps_text}{emotional_pressure_text}## Цели оператора (ты НЕ должен помогать ему достичь эти цели легко):
- Основная цель: {dialog_objectives.get('primary_goal', '')}
{secondary_goals_text}## Инструкции:
- Отвечай естественно, как реальный клиент с таким характером
- Используй фразы, соответствующие твоему типу поведения
- Создавай возражения согласно уровню сложности
- НЕ помогай оператору достичь целей слишком легко
- Будь реалистичным и естественным в диалоге
- Отвечай кратко, как в реальном телефонном разговоре
- Используй только текст, без форматирования"""

        return prompt
    
    def get_context(self, session_id: str, session_info: Optional[Dict]) -> List[Dict[str, str]]:
        """Get context for a session"""
        if session_id not in self.contexts:
            self.contexts[session_id] = []
            logger.info(f"Context: Created new context for session {session_id}")
            
            # Add system prompt only when context is first created
            if session_info:
                system_prompt = self._build_system_prompt(session_info)
                self.contexts[session_id].append({
                    "role": "system",
                    "content": system_prompt
                })
                logger.info(f"Context: Added system prompt to context for session {session_id}")
        
        # Return a copy of the context
        context_data = self.contexts[session_id].copy()
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

