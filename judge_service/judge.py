import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.llms import Ollama
from langchain_core.output_parsers import PydanticOutputParser

from evaluation_models import EvaluationResponse
from scenarios import get_scenario_config

import os

BASE_DIR = Path(__file__).resolve().parent
PROMPT_TEMPLATE_PATH = BASE_DIR / "judge_prompt.txt"

logger = logging.getLogger(__name__)


class LLMJudge:
    def __init__(self):
        # LLM Provider configuration
        llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
        
        # OpenRouter API configuration
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        openrouter_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        
        # Ollama configuration
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2:7b-instruct-q4_K_M")

        # Load prompt template
        self.prompt_template = self._load_prompt_template()
        
        # Initialize LLM with structured output
        if llm_provider == "ollama":
            try:
                # Use Ollama via langchain
                self.llm = Ollama(
                    model=ollama_model,
                    base_url=ollama_base_url,
                    temperature=0.2,
                )
                self.backend_name = "ollama"
                self.use_structured_output = False  # Ollama may not support structured output
                logger.info(f"LLMJudge: Initialized with Ollama model {ollama_model} at {ollama_base_url}")
            except Exception as e:
                logger.error(f"Failed to initialize Ollama: {e}")
                raise
        else:
            # Use OpenRouter via OpenAI-compatible API
            if not openrouter_api_key:
                logger.warning("OPENROUTER_API_KEY not set. LLM will not work.")
            
            # OpenRouter via OpenAI client
            self.llm = ChatOpenAI(
                model=openrouter_model,
                api_key=openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/your-repo",
                    "X-Title": "Judge Service",
                },
                temperature=0.2,
                extra_body={
                    "reasoning": {
                        # "effort": "none",
                        "max_tokens": 0
                    }
                },
            )
            self.backend_name = "openrouter"
            self.use_structured_output = True  # OpenAI-compatible APIs support structured output
            logger.info(f"LLMJudge: Initialized with OpenRouter model {openrouter_model}")

        # Set up structured output parser
        self.output_parser = PydanticOutputParser(pydantic_object=EvaluationResponse)
        
        logger.info("LLMJudge initialized: provider=%s", self.backend_name)

    def _load_prompt_template(self) -> str:
        with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def _build_prompt(
        self,
        transcript: List[Dict[str, str]],
        scenario_config: Any,
    ) -> str:
        """Build prompt from template with scenario and transcript data."""
        # Format transcript
        transcript_str = "\n".join(
            f"{msg['role'].upper()}: {msg['text']}"
            for msg in transcript
        )
        
        # Format compliance must_have
        compliance_must_have = "\n".join(
            f"- {item}" for item in scenario_config.compliance_must_have
        )
        
        # Format compliance must_avoid
        compliance_must_avoid = "\n".join(
            f"- {item}" for item in scenario_config.compliance_must_avoid
        )
        
        # Format relevant criteria
        relevant_criteria_str = ", ".join(scenario_config.relevant_criteria)
        
        # Fill template
        prompt = self.prompt_template.format(
            scenario_title=scenario_config.title,
            scenario_description=scenario_config.description,
            scenario_difficulty=scenario_config.difficulty,
            scenario_archetype=scenario_config.client_archetype,
            transcript=transcript_str,
            compliance_must_have=compliance_must_have,
            compliance_must_avoid=compliance_must_avoid,
            relevant_criteria=relevant_criteria_str,
        )
        
        return prompt

    def evaluate(self, transcript: List[Dict[str, str]], scenario_id: str = "novice_ip_no_account_easy") -> Dict[str, Any]:
        """Evaluate transcript using LLM with structured output."""
        try:
            scenario_config = get_scenario_config(scenario_id)

            prompt_text = self._build_prompt(
                transcript=transcript,
                scenario_config=scenario_config,
            )

            # Get structured output from LLM
            if self.use_structured_output:
                # Try structured output first (works with OpenAI-compatible APIs)
                try:
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", "You are a strict evaluator. Follow the instructions precisely."),
                        ("user", prompt_text),
                    ])
                    structured_llm = self.llm.with_structured_output(EvaluationResponse)
                    chain = prompt | structured_llm
                    evaluation = chain.invoke({})
                    
                    # Check if evaluation is None
                    if evaluation is None:
                        raise ValueError("Structured output returned None")
                        
                except Exception as struct_err:
                    # Fallback to manual parsing if structured output fails
                    logger.warning(f"Structured output failed ({struct_err}), falling back to manual parsing")
                    format_instructions = self.output_parser.get_format_instructions()
                    full_prompt_text = prompt_text + "\n\n" + format_instructions
                    
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", "You are a strict evaluator. Follow the instructions precisely."),
                        ("user", "{prompt_text}"),
                    ])
                    raw_chain = prompt | self.llm
                    raw_response = raw_chain.invoke({"prompt_text": full_prompt_text})
                    
                    if hasattr(raw_response, 'content'):
                        content = raw_response.content
                    else:
                        content = str(raw_response)
                    
                    try:
                        evaluation = self.output_parser.parse(content)
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse response, trying to extract JSON: {parse_err}")
                        # Fallback: try to extract JSON from markdown code blocks or plain text
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            content = json_match.group(0)
                        evaluation = self.output_parser.parse(content)
            else:
                # For Ollama, parse JSON response manually
                # Add format instructions as plain text (not in template)
                format_instructions = self.output_parser.get_format_instructions()
                full_prompt_text = prompt_text + "\n\n" + format_instructions
                
                # Use ChatPromptTemplate with escaped braces or just pass as string
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are a strict evaluator. Follow the instructions precisely."),
                    ("user", "{prompt_text}"),
                ])
                chain = prompt | self.llm
                raw_response = chain.invoke({"prompt_text": full_prompt_text})
                # Extract content from message
                if hasattr(raw_response, 'content'):
                    content = raw_response.content
                elif isinstance(raw_response, str):
                    content = raw_response
                else:
                    content = str(raw_response)
                
                # Try to parse JSON response
                try:
                    evaluation = self.output_parser.parse(content)
                except Exception as parse_err:
                    logger.warning(f"Failed to parse Ollama response, trying to extract JSON: {parse_err}")
                    # Fallback: try to extract JSON from markdown code blocks or plain text
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        content = json_match.group(0)
                    evaluation = self.output_parser.parse(content)

            # Convert Pydantic model to dict
            if evaluation is None:
                raise ValueError("LLM evaluation returned None - unable to parse response")
            
            result = evaluation.model_dump()
            
            # Add metadata
            result["scenario_id"] = scenario_id
            result["relevant_criteria"] = scenario_config.relevant_criteria
            result["model_used"] = getattr(self.llm, "model_name", getattr(self.llm, "model", "unknown"))
            result["judge_backend"] = self.backend_name
            # client_profile is no longer classified, but kept for API compatibility
            result["client_profile"] = {}

            # Handle critical errors - set total_score to 0 if there are critical errors
            if result.get("critical_errors"):
                result["total_score"] = 0.0

            return result

        except Exception as e:
            logger.error("Error in LLMJudge.evaluate: %s", e, exc_info=True)
            return {
                "error": "LLM evaluation failed",
                "details": str(e),
                "scores": {},
                "total_score": 0,
                "critical_errors": ["Не удалось обработать диалог"],
                "feedback_positive": [],
                "feedback_improvement": [],
                "recommendations": [],
                "timecodes": [],
            }
