from typing import List, Dict
import logging
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from .dialogue_prompts import make_prompt, clean_reply

logger = logging.getLogger(__name__)

# OpenRouter API configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")  # Default model
OPENROUTER_MODEL = "openai/gpt-4o-mini"  # Default model

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLM:
    """Large Language Model component using LangChain with OpenRouter API"""
    
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.model = OPENROUTER_MODEL
        self.llm = None

        print(f"OPENROUTER_MODEL: {OPENROUTER_MODEL}")
        
        if not self.api_key:
            logger.warning("LLM: OPENROUTER_API_KEY not set. LLM will not work.")
        else:
            # Initialize LangChain ChatOpenAI with OpenRouter endpoint
            self.llm = ChatOpenAI(
                model=self.model,
                openai_api_key=self.api_key,
                openai_api_base=OPENROUTER_BASE_URL,
                temperature=0.7,
                max_tokens=500,
                timeout=30.0,
            )
            logger.info(f"LLM: Initialized with model {self.model}")
    
    def _build_prompt_from_context(self, context: Dict, user_input: str) -> str:
        """
        Build full prompt using dialogue_prompts.make_prompt logic.
        
        Args:
            context: Dict with 'system_prompt' and 'conversation' keys
            user_input: Current manager input
            
        Returns:
            Full prompt string for the model
        """
        system_prompt = context.get("system_prompt", "")
        conversation = context.get("conversation", [])
        
        # Add current manager input to conversation for prompt building
        # (it will be included in the prompt but not yet in conversation history)
        temp_conversation = conversation + [{"role": "manager", "text": user_input}]
        
        # Build full prompt using make_prompt
        full_prompt = make_prompt(system_prompt, temp_conversation)
        
        return full_prompt
    
    def _convert_messages(self, prompt: str) -> List:
        """
        Convert prompt string to LangChain message format.
        Uses a single user message with the full prompt.
        """
        # For OpenRouter, we send the full prompt as a single user message
        # The system prompt is already included in the prompt text
        messages = [HumanMessage(content=prompt)]
        return messages
    
    async def generate_response_stream(
        self,
        user_input: str,
        context: Dict
    ):
        """
        Generate streaming response using LangChain with OpenRouter API.
        Yields tokens as they are generated.
        
        Args:
            user_input: Manager's input text
            context: Dict with 'system_prompt' and 'conversation' keys
            
        Yields:
            str: Text chunks as they are generated (will be cleaned with clean_reply)
        """
        if not self.api_key:
            logger.warning("LLM: API key not set, returning fallback response")
            yield "Извините, языковая модель не настроена."
            return
        
        if not self.llm:
            logger.error("LLM: LangChain model not initialized")
            yield "Извините, языковая модель не инициализирована."
            return
        
        logger.info(f"LLM: Generating streaming response (user_input: {user_input[:50]}..., conversation turns: {len(context.get('conversation', []))})")
        
        try:
            # Build full prompt using dialogue_prompts logic
            full_prompt = self._build_prompt_from_context(context, user_input)
            
            # Convert to LangChain message format
            messages = self._convert_messages(full_prompt)
            
            # Stream the LLM response
            raw_response = ""
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    raw_response += chunk.content
                    # Yield chunks as they come (will be cleaned later)
                    yield chunk.content
        
        except Exception as e:
            logger.error(f"LLM: Error generating streaming response: {str(e)}", exc_info=True)
            yield "Извините, произошла ошибка при генерации ответа."
    
    def clean_response(self, raw_response: str) -> str:
        """
        Clean LLM response using dialogue_prompts.clean_reply.
        
        Args:
            raw_response: Raw response from LLM
            
        Returns:
            Cleaned response
        """
        return clean_reply(raw_response)