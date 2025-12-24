import json
import logging

logger = logging.getLogger(__name__)


class MockBackend:
    """
    Offline backend for debugging: returns deterministic JSON-like answer.
    """
    def __init__(self, model_name: str = "mock"):
        self.model_name = model_name
        logger.info("MockBackend initialized")

    def generate(self, prompt: str, max_retries: int = 1) -> str:
        _ = prompt
        # Важно: возвращаем строку с JSON, чтобы parse_llm_response смог вытащить структуру
        return json.dumps(
            {
                "scores": {
                    "greeting_correct": True,
                    "congratulation_given": True,
                    "politeness": 9,
                },
                "critical_errors": [],
                "feedback_positive": ["Хорошее приветствие и корректные вопросы."],
                "feedback_improvement": [],
                "recommendations": ["Продолжайте уточнять потребности клиента (оборот, сотрудники, онлайн-касса)."],
                "timecodes": [],
                "compliance_check": {},
                "total_score": 0,  # LLMJudge пересчитает сам
            },
            ensure_ascii=False,
        )
