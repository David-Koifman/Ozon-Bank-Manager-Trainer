from typing import List, Dict
import logging
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

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
                # default_headers={
                #     "HTTP-Referer": "https://github.com/operator-voice-trainer",  # Optional: for analytics
                #     "X-Title": "Operator Voice Trainer"  # Optional: for analytics
                # }
            )
            logger.info(f"LLM: Initialized with model {self.model}")
    
    def _convert_messages(self, context: List[Dict[str, str]], user_input: str) -> List:
        """
        Convert context and user input to LangChain message format
        """
        messages = []
        
        # Check if context already has a system message
        has_system_message = any(msg.get("role") == "system" for msg in context)
        
        # Add context messages (system messages from context will be used)
        for msg in context:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            elif role == "user":
                messages.append(HumanMessage(content=content))
        
        # If no system message in context, add a default one
        if not has_system_message:
            system_prompt = (
                "You are a helpful assistant. Respond in plain text only, without any formatting, "
                "markdown, or special characters. Speak naturally and conversationally, as a human would. "
                "Keep your responses concise and natural-sounding."
            )
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Add current user input
        messages.append(HumanMessage(content=user_input))
        
        return messages
    
    async def generate_response(
        self,
        user_input: str,
        context: List[Dict[str, str]]
    ) -> str:
        """
        Generate response using LangChain with OpenRouter API
        """
        if not self.api_key:
            logger.warning("LLM: API key not set, returning fallback response")
            return "I'm sorry, but the language model is not configured. Please set OPENROUTER_API_KEY environment variable."
        
        if not self.llm:
            logger.error("LLM: LangChain model not initialized")
            return "I'm sorry, the language model is not properly initialized."
        
        logger.info(f"LLM: Generating response (user_input: {user_input[:50]}..., context length: {len(context)})")
        
        try:
            # Convert messages to LangChain format
            messages = self._convert_messages(context, user_input)
            
            # Invoke the LLM
            response = await self.llm.ainvoke(messages)
            
            # Extract response text
            response_text = response.content
            logger.info(f"LLM: Generated response: {response_text[:100]}...")
            return response_text
        
        except Exception as e:
            logger.error(f"LLM: Error generating response: {str(e)}", exc_info=True)
            return "I'm sorry, an error occurred while generating the response."
