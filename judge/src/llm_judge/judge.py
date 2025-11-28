import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import re

from .parser import parse_llm_response
from .backends.ollama_backend import OllamaBackend
from .client_classifier import ClientClassifier

# Пути к ресурсам
BASE_DIR = Path(__file__).parent.parent.parent
# ✅ Исправленный путь к compliance_phrases.md
COMPLIANCE_PATH = BASE_DIR / "src" / "llm_judge" / "spec" / "compliance_phrases.md"
SPEC_PATH = BASE_DIR / "src" / "llm_judge" / "spec" / "evaluation_spec.json"
PROMPT_TEMPLATE_PATH = BASE_DIR / "src" / "llm_judge" / "prompts" / "judge_prompt.md"

logger = logging.getLogger(__name__)


class LLMJudge:
    """
    Основной класс для оценки тренировочных диалогов менеджеров.
    Использует LLM (Qwen2 через Ollama) и строгую спецификацию оценки.
    """

    def __init__(self, model_name: str = "qwen2:7b-instruct-q4_K_M"):
        self.backend = OllamaBackend(model_name=model_name)
        self.spec = self._load_evaluation_spec()
        self.prompt_template = self._load_prompt_template()
        # ✅ Загружаем compliance-фразы
        self.compliance_phrases = self._load_compliance_phrases()
        self.classifier = ClientClassifier()

    def _load_evaluation_spec(self) -> Dict[str, Any]:
        """Загружает evaluation_spec.json"""
        with open(SPEC_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_prompt_template(self) -> str:
        """Загружает шаблон промпта judge_prompt.md"""
        with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def _load_compliance_phrases(self) -> list:
        """Загружает compliance-фразы из файла compliance_phrases.md"""
        try:
            with open(COMPLIANCE_PATH, "r", encoding="utf-8") as f:
                text = f.read()
            # Разбить на фразы (например, по строкам или по маркерам)
            # Пропускаем пустые строки и строки, начинающиеся с #
            phrases = [
                line.strip()
                for line in text.split("\n")
                if line.strip() and not line.startswith("#") and not line.startswith(">") and not line.startswith("- [ ]") and "|" not in line and "---" not in line
            ]
            return phrases
        except FileNotFoundError:
            logger.warning(f"Файл {COMPLIANCE_PATH} не найден. Compliance-фразы не будут проверяться.")
            return []

    def _format_transcript(self, transcript: list) -> str:
        """Преобразует список реплик в читаемый текст для промпта"""
        lines = []
        for turn in transcript:
            role = "Менеджер" if turn["role"] == "manager" else "Клиент"
            lines.append(f"[{role}]: {turn['text']}")
        return "\n".join(lines)

    def _select_relevant_criteria(self, client_profile: Dict[str, Any]) -> list:
        """
        Выбирает релевантные критерии на основе профиля клиента из evaluation_spec.json.
        """
        rules = self.spec.get("dynamic_criteria_selector", {}).get("rules", [])
        
        for rule in rules:
            condition = rule["condition"]
            # Заменяем . на [' и '] для доступа к словарю
            # Например: client.type == 'IP' -> client['type'] == 'IP'
            condition = re.sub(r"client\.([a-zA-Z_][a-zA-Z0-9_]*)", r"client['\1']", condition)
            # Заменяем логические операторы
            condition = condition.replace("AND", " and ").replace("OR", " or ")
            
            # Создаём безопасный контекст для eval
            context = {
                "client": client_profile,
                "True": True,
                "False": False
            }
            
            try:
                if eval(condition, {"__builtins__": {}}, context):
                    return rule["include_criteria"]
            except Exception as e:
                logger.warning(f"Ошибка при оценке условия: {condition} — {e}")
                continue
        
        # Если ни одно условие не подошло — возвращаем все критерии
        return list(self.spec["criteria"].keys())

    def _check_compliance_phrases(self, transcript: list) -> dict:
        """
        Проверяет, были ли сказаны обязательные compliance-фразы.
        Возвращает словарь: {"фраза": True/False}
        """
        compliance_results = {}
        # Объединяем весь текст менеджера в одну строку для поиска
        manager_texts = [turn["text"] for turn in transcript if turn["role"] == "manager"]
        full_manager_text = " ".join(manager_texts).lower()

        for phrase in self.compliance_phrases:
            # Проверяем, содержится ли фраза в транскрипте менеджера (без учета регистра)
            found = phrase.lower() in full_manager_text
            compliance_results[phrase] = found

        return compliance_results

    def evaluate(self, transcript: list, scenario_id: str = "ozon_rko_new_seller_v1") -> Dict[str, Any]:
        """
        Основной метод оценки диалога.
        
        Args:
            transcript: список реплик [{"role": "manager", "text": "..."}, ...]
            scenario_id: идентификатор сценария
        
        Returns:
            Структурированный JSON с оценкой, ошибками и рекомендациями.
        """
        try:
            # Классифицируем клиента из транскрипции
            client_profile = self.classifier.classify(transcript)
            
            # Выбираем релевантные критерии
            relevant_criteria = self._select_relevant_criteria(client_profile)
            
            # Форматируем транскрипцию
            transcript_str = self._format_transcript(transcript)
            
            # ✅ Проверяем compliance-фразы
            compliance_results = self._check_compliance_phrases(transcript)
            
            # Подготавливаем промпт с профилем, критериями и compliance-результатами
            prompt = self.prompt_template.replace("{{ transcript }}", transcript_str)
            prompt = prompt.replace("{{ client_profile }}", str(client_profile))
            prompt = prompt.replace("{{ relevant_criteria }}", str(relevant_criteria))
            prompt = prompt.replace("{{ compliance_results }}", str(compliance_results))  # ✅ Новое

            # Вызываем LLM
            raw_response = self.backend.generate(prompt)

            # Парсим и валидируем ответ
            result = parse_llm_response(raw_response)

            # Добавляем метаданные
            result["scenario_id"] = scenario_id
            result["client_profile"] = client_profile
            result["relevant_criteria"] = relevant_criteria
            result["model_used"] = self.backend.model_name
            result["compliance_check"] = compliance_results  # ✅ Добавляем результат проверки

            return result

        except Exception as e:
            logger.error(f"Ошибка в LLMJudge.evaluate: {e}")
            return {
                "error": "LLM evaluation failed",
                "details": str(e),
                "scores": {},
                "total_score": 0,
                "critical_errors": ["Не удалось обработать диалог"],
                "feedback_positive": [],
                "feedback_improvement": [],
                "recommendations": [],
                "timecodes": [],  # оставлено для совместимости, но не заполняется
                "compliance_check": {}  # ✅ Добавляем пустой результат при ошибке
            }