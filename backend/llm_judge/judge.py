import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List

from .parser import parse_llm_response
from .backends.ollama_backend import OllamaBackend
from .client_classifier import ClientClassifier
from .scenarios import get_scenario_config
from .prompt_builder import build_evaluate_prompt

# ==== Пути к ресурсам относительно текущей папки llm_judge ====
BASE_DIR = Path(__file__).resolve().parent

# здесь ожидаем:
# backend/llm_judge/spec/evaluation_spec.json
# backend/llm_judge/spec/compliance_phrases.md
# backend/llm_judge/prompts/judge_prompt.md
SPEC_PATH = BASE_DIR / "spec" / "evaluation_spec.json"
COMPLIANCE_PATH = BASE_DIR / "spec" / "compliance_phrases.md"
PROMPT_TEMPLATE_PATH = BASE_DIR / "prompts" / "judge_prompt.md"

logger = logging.getLogger(__name__)


class LLMJudge:
    """
    Основной класс для оценки тренировочных диалогов менеджеров.
    Использует LLM (Qwen2 через Ollama) и сценарную спецификацию оценки.

    Важные моменты:
    - LLM возвращает scores по критериям и оценку вежливости (politeness).
    - Итоговый балл total_score рассчитывается на бэкенде по weights сценария.
    """

    def __init__(self, model_name: str = "qwen2:7b-instruct-q4_K_M"):
        self.backend = OllamaBackend(model_name=model_name)
        # spec пока оставляем — может пригодиться для валидации/расширения
        self.spec = self._load_evaluation_spec()
        # шаблон и markdown-фразы тоже оставляем для совместимости,
        # но в evaluate() больше не используем
        self.prompt_template = self._load_prompt_template()
        self.compliance_phrases = self._load_compliance_phrases()
        self.classifier = ClientClassifier()

    # ======== Загрузка конфигов / промптов / compliance ========

    def _load_evaluation_spec(self) -> Dict[str, Any]:
        """Загружает evaluation_spec.json"""
        try:
            with open(SPEC_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Не найден файл спецификации оценки: {SPEC_PATH}")
            raise

    def _load_prompt_template(self) -> str:
        """Загружает шаблон промпта judge_prompt.md"""
        try:
            with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Не найден файл шаблона промпта: {PROMPT_TEMPLATE_PATH}")
            raise

    def _load_compliance_phrases(self) -> List[str]:
        """
        Загружает compliance-фразы из файла compliance_phrases.md.
        Если файла нет — просто логируем предупреждение и возвращаем пустой список.
        (Сейчас для оценки сценариев напрямую не используется, но оставляем на будущее.)
        """
        try:
            with open(COMPLIANCE_PATH, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            logger.warning(
                f"Файл compliance-фраз {COMPLIANCE_PATH} не найден. "
                f"Compliance-проверка будет пропущена."
            )
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

    # ======== Вспомогательные методы (старые, пока не используем, но не ломаем API) ========

    def _format_transcript(self, transcript: List[Dict[str, str]]) -> str:
        """Преобразует список реплик в читаемый текст (может пригодиться для отладки)."""
        lines: List[str] = []
        for turn in transcript:
            role = "Менеджер" if turn["role"] == "manager" else "Клиент"
            lines.append(f"[{role}]: {turn['text']}")
        return "\n".join(lines)

    def _select_relevant_criteria(self, client_profile: Dict[str, Any]) -> List[str]:
        """
        СТАРЫЙ метод выбора критериев из evaluation_spec.json через dynamic_criteria_selector.
        Сейчас для новых сценариев НЕ используется, но оставлен для совместимости.
        """
        rules = self.spec.get("dynamic_criteria_selector", {}).get("rules", [])

        for rule in rules:
            condition = rule["condition"]

            # client.type -> client['type']
            condition = re.sub(
                r"client\.([a-zA-Z_][a-zA-Z0-9_]*)",
                r"client['\1']",
                condition,
            )
            # Логические операторы
            condition = condition.replace("AND", " and ").replace("OR", " or ")

            context = {
                "client": client_profile,
                "True": True,
                "False": False,
            }

            try:
                if eval(condition, {"__builtins__": {}}, context):
                    return rule["include_criteria"]
            except Exception as e:
                logger.warning(
                    f"Ошибка при оценке условия '{condition}': {e}"
                )
                continue

        # Если ни одно условие не подошло — возвращаем все критерии
        return list(self.spec.get("criteria", {}).keys())

    def _check_compliance_phrases(self, transcript: List[Dict[str, str]]) -> Dict[str, bool]:
        """
        СТАРЫЙ способ: проверять, были ли сказаны compliance-фразы по простому вхождению строки.
        Для новых сценариев мы полагаемся на оценку LLM, но метод оставляем.
        """
        compliance_results: Dict[str, bool] = {}

        manager_texts = [
            turn["text"] for turn in transcript if turn.get("role") == "manager"
        ]
        full_manager_text = " ".join(manager_texts).lower()

        for phrase in self.compliance_phrases:
            found = phrase.lower() in full_manager_text
            compliance_results[phrase] = found

        return compliance_results

    # ======== Новый метод: пост-обработка приветствия ========

    def _postprocess_scores_greeting(
        self,
        transcript: List[Dict[str, str]],
        scores: Dict[str, Any],
    ) -> None:
        """
        Дополнительная проверка приветствия:

        Если в первых репликах менеджера явно есть:
        - самопрезентация вида "Это <имя> из Ozon" (без слова "банк"),
        - и поздравление с регистрацией ("поздрав..."),

        то мы форсируем:
        - greeting_correct = True
        - congratulation_given = True

        Это уменьшает шум от LLM, когда текстовый анализ позитивный,
        а булевый флаг почему-то False.
        """
        manager_replicas = [
            t.get("text", "") for t in transcript if t.get("role") == "manager"
        ]
        if not manager_replicas:
            return

        # Смотрим первые 1–2 реплики менеджера
        first_block = " ".join(manager_replicas[:2]).lower()

        has_self_intro = "это" in first_block and "ozon" in first_block
        has_congrats = "поздрав" in first_block  # ловим "поздравляю", "поздравляем" и т.п.
        has_bank_in_intro = "банк" in first_block

        # Корректное приветствие: "Это <имя> из Ozon", без "банк", с поздравлением
        if has_self_intro and has_congrats and not has_bank_in_intro:
            scores["greeting_correct"] = True
            scores["congratulation_given"] = True

    # ======== Новый метод: расчёт итогового балла ========

    def _compute_total_score(
        self,
        scores: Dict[str, Any],
        scenario_id: str,
    ) -> float:
        """
        Считает итоговый балл по weights сценария.

        Логика:
        - Для каждого критерия (кроме 'politeness'):
            если scores[crit] == True -> добавляем вес из сценария.
        - Для 'politeness':
            берём scores['politeness'] в диапазоне 0–10,
            нормируем на [0;1] и умножаем на вес 'politeness'.
        """
        scenario_config = get_scenario_config(scenario_id)
        weights = scenario_config.weights

        total = 0.0

        # Булевые критерии
        for crit in scenario_config.relevant_criteria:
            if crit == "politeness":
                continue
            value = scores.get(crit)
            weight = weights.get(crit, 0)
            if isinstance(value, bool) and value:
                total += float(weight)

        # Вклад вежливости
        politeness_weight = weights.get("politeness", 0)
        politeness_value = scores.get("politeness", 0)

        try:
            politeness_value = float(politeness_value)
        except (TypeError, ValueError):
            politeness_value = 0.0

        # нормируем 0–10 в 0.0–1.0
        if politeness_value < 0:
            politeness_value = 0.0
        if politeness_value > 10:
            politeness_value = 10.0

        politeness_factor = politeness_value / 10.0
        total += politeness_factor * float(politeness_weight)

        return total

    # ======== Основной метод оценки ========

    def evaluate(
        self,
        transcript: List[Dict[str, str]],
        scenario_id: str = "novice_ip_no_account_easy",
    ) -> Dict[str, Any]:
        """
        Основной метод оценки диалога.

        Args:
            transcript: список реплик [{"role": "manager", "text": "..."}, ...]
            scenario_id: идентификатор сценария (ветки скрипта).
                         Сейчас по умолчанию: "novice_ip_no_account_easy".

        Returns:
            Структурированный JSON с оценкой, ошибками и рекомендациями.
        """
        try:
            # 1. Классифицируем клиента по фактическому диалогу
            client_profile = self.classifier.classify(transcript)

            # 2. Берём конфиг сценария (ветки скрипта), привязанный к уровню сложности и архетипу
            scenario_config = get_scenario_config(scenario_id)
            relevant_criteria = scenario_config.relevant_criteria

            # 3. Собираем промпт под КОНКРЕТНЫЙ сценарий
            prompt = build_evaluate_prompt(
                transcript=transcript,
                client_profile=client_profile,
                scenario_id=scenario_id,
                model_name=self.backend.model_name,
            )

            # 4. Вызов LLM
            raw_response = self.backend.generate(prompt)

            # 5. Парсим и валидируем ответ
            result = parse_llm_response(raw_response)

            # 6. Обогащаем/подчищаем метаданные и scores
            result.setdefault("scores", {})
            result.setdefault("total_score", 0)
            result.setdefault("critical_errors", [])
            result.setdefault("feedback_positive", [])
            result.setdefault("feedback_improvement", [])
            result.setdefault("recommendations", [])
            result.setdefault("timecodes", [])
            result.setdefault("compliance_check", {})

            scores = result["scores"]

            # 6.1. Постобработка приветствия и поздравления
            self._postprocess_scores_greeting(transcript, scores)

            # 7. Метаданные по сценарию и клиенту
            result["scenario_id"] = scenario_id
            result["client_profile"] = client_profile
            result["relevant_criteria"] = relevant_criteria
            result["model_used"] = self.backend.model_name

            # 8. Перерасчитываем итоговый балл по весам сценария
            try:
                total_score = self._compute_total_score(scores, scenario_id)
            except Exception as score_err:
                logger.warning(
                    f"Не удалось пересчитать total_score для сценария {scenario_id}: {score_err}"
                )
                total_score = result.get("total_score", 0)

            result["total_score"] = total_score

            return result

        except Exception as e:
            logger.error(f"Ошибка в LLMJudge.evaluate: {e}", exc_info=True)
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

