from typing import List, Dict
import logging
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from .dialogue_prompts import make_prompt, clean_reply

logger = logging.getLogger(__name__)

# LLM Provider configuration
# Set LLM_PROVIDER to "ollama" or "openrouter" (default: "openrouter")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()

# OpenRouter API configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-7b-instruct")  # Default model
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Ollama configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")  # Default Ollama model


class LLM:
    """Large Language Model component using LangChain with OpenRouter or Ollama"""
    
    def __init__(self):
        self.provider = LLM_PROVIDER
        self.llm = None
        
        if self.provider == "ollama":
            # Initialize with Ollama
            try:
                from langchain_community.chat_models import ChatOllama
                
                self.model = OLLAMA_MODEL
                self.llm = ChatOllama(
                    model=self.model,
                    base_url=OLLAMA_BASE_URL,
                    temperature=0.7,
                    num_predict=500,  # Ollama uses num_predict instead of max_tokens
                    timeout=30.0,
                )
                logger.info(f"LLM: Initialized with Ollama model {self.model} at {OLLAMA_BASE_URL}")
            except ImportError:
                logger.error("LLM: langchain-community not installed. Install with: pip install langchain-community")
                raise
            except Exception as e:
                logger.error(f"LLM: Failed to initialize Ollama: {e}")
                logger.warning("LLM: Make sure Ollama is running. Start with: ollama serve")
                raise
        
        elif self.provider == "openrouter":
            # Initialize with OpenRouter
            self.api_key = OPENROUTER_API_KEY
            self.model = OPENROUTER_MODEL
            
            if not self.api_key:
                logger.warning("LLM: OPENROUTER_API_KEY not set. LLM will not work.")
            else:
                self.llm = ChatOpenAI(
                    model=self.model,
                    openai_api_key=self.api_key,
                    openai_api_base=OPENROUTER_BASE_URL,
                    temperature=0.7,
                    max_tokens=500,
                    timeout=30.0,
                )
                logger.info(f"LLM: Initialized with OpenRouter model {self.model}")
        else:
            raise ValueError(f"LLM: Unknown provider '{self.provider}'. Use 'ollama' or 'openrouter'")
    
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
        if not self.llm:
            if self.provider == "openrouter" and not OPENROUTER_API_KEY:
                logger.warning("LLM: API key not set, returning fallback response")
            else:
                logger.error("LLM: LangChain model not initialized")
            yield "Извините, языковая модель не настроена."
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