import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from .parser import parse_llm_response
from .client_classifier import ClientClassifier
from .scenarios import get_scenario_config
from .prompt_builder import build_evaluate_prompt

from .backends.ollama_backend import OllamaBackend
from .backends.openrouter_backend import OpenRouterBackend

import os

BASE_DIR = Path(__file__).resolve().parent
SPEC_PATH = BASE_DIR / "spec" / "evaluation_spec.json"
COMPLIANCE_PATH = BASE_DIR / "spec" / "compliance_phrases.md"
PROMPT_TEMPLATE_PATH = BASE_DIR / "prompts" / "judge_prompt.md"

logger = logging.getLogger(__name__)


class LLMJudge:
    def __init__(self):
        backend_name = (os.getenv("JUDGE_BACKEND", "openrouter") or "openrouter").lower().strip()

        if backend_name == "ollama":
            model_name = os.getenv("OLLAMA_MODEL", "qwen2:7b-instruct-q4_K_M")
            self.backend = OllamaBackend(model_name=model_name)
            self.backend_name = "ollama"
        else:
            model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            self.backend = OpenRouterBackend(model_name=model_name)
            self.backend_name = "openrouter"

        self.spec = self._load_evaluation_spec()
        self.prompt_template = self._load_prompt_template()
        self.compliance_phrases = self._load_compliance_phrases()
        self.classifier = ClientClassifier()

        logger.info("LLMJudge initialized: backend=%s", self.backend_name)

    def _load_evaluation_spec(self) -> Dict[str, Any]:
        with open(SPEC_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_prompt_template(self) -> str:
        with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def _load_compliance_phrases(self) -> List[str]:
        try:
            text = COMPLIANCE_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("Compliance file not found: %s", COMPLIANCE_PATH)
            return []

        phrases: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            if (
                not line
                or line.startswith("#")
                or line.startswith(">")
                or line.startswith("- [ ]")
                or "|" in line
                or "---" in line
            ):
                continue
            phrases.append(line)
        return phrases

    def _postprocess_scores_greeting(self, transcript: List[Dict[str, str]], scores: Dict[str, Any]) -> None:
        manager_replicas = [t.get("text", "") for t in transcript if t.get("role") == "manager"]
        if not manager_replicas:
            return
        first_block = " ".join(manager_replicas[:2]).lower()
        has_self_intro = "это" in first_block and "ozon" in first_block
        has_congrats = "поздрав" in first_block
        has_bank_in_intro = "банк" in first_block
        if has_self_intro and has_congrats and not has_bank_in_intro:
            scores["greeting_correct"] = True
            scores["congratulation_given"] = True

    def _check_contextual_critical_errors(self, transcript: List[Dict[str, str]]) -> List[str]:
        manager_replicas = [t.get("text", "") for t in transcript if t.get("role") == "manager"]
        if not manager_replicas:
            return []
        greeting_line = manager_replicas[0].lower()

        bank_in_greeting = (
            re.search(r"\bиз\s+(ozon|озон)\s+банк(а)?\b", greeting_line) is not None
            or re.search(r"\bozon\s+bank\b", greeting_line) is not None
        )
        return ["forbidden_in_greeting: банк"] if bank_in_greeting else []

    def _compute_total_score(self, scores: Dict[str, Any], scenario_id: str) -> float:
        scenario_config = get_scenario_config(scenario_id)
        weights = scenario_config.weights

        total = 0.0
        for crit in scenario_config.relevant_criteria:
            if crit == "politeness":
                continue
            if isinstance(scores.get(crit), bool) and scores.get(crit) is True:
                total += float(weights.get(crit, 0))

        politeness_weight = float(weights.get("politeness", 0))
        politeness_value = scores.get("politeness", 0)
        try:
            politeness_value = float(politeness_value)
        except (TypeError, ValueError):
            politeness_value = 0.0
        politeness_value = max(0.0, min(10.0, politeness_value))
        total += (politeness_value / 10.0) * politeness_weight
        return total

    def evaluate(self, transcript: List[Dict[str, str]], scenario_id: str = "novice_ip_no_account_easy") -> Dict[str, Any]:
        try:
            client_profile = self.classifier.classify(transcript)
            scenario_config = get_scenario_config(scenario_id)

            prompt = build_evaluate_prompt(
                transcript=transcript,
                client_profile=client_profile,
                scenario_id=scenario_id,
                model_name=getattr(self.backend, "model_name", "unknown"),
            )

            raw_response = self.backend.generate(prompt)
            result = parse_llm_response(raw_response)

            result.setdefault("scores", {})
            result.setdefault("total_score", 0)
            result.setdefault("critical_errors", [])
            result.setdefault("feedback_positive", [])
            result.setdefault("feedback_improvement", [])
            result.setdefault("recommendations", [])
            result.setdefault("timecodes", [])
            result.setdefault("compliance_check", {})

            scores = result["scores"]

            self._postprocess_scores_greeting(transcript, scores)

            contextual_crit = self._check_contextual_critical_errors(transcript)
            if contextual_crit:
                result["critical_errors"] = list(set(result.get("critical_errors", []) + contextual_crit))
                scores["greeting_correct"] = False

            result["scenario_id"] = scenario_id
            result["client_profile"] = client_profile
            result["relevant_criteria"] = scenario_config.relevant_criteria
            result["model_used"] = getattr(self.backend, "model_name", "unknown")
            result["judge_backend"] = getattr(self, "backend_name", "unknown")

            try:
                total_score = self._compute_total_score(scores, scenario_id)
            except Exception as score_err:
                logger.warning("Failed to compute total_score: %s", score_err)
                total_score = float(result.get("total_score", 0) or 0)

            result["total_score"] = total_score

            if result.get("critical_errors"):
                result["total_score"] = 0

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
                "compliance_check": {},
            }


