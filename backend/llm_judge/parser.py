import json
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def parse_llm_response(raw_response: str) -> Dict[str, Any]:
    """
    Парсит ответ LLM в формат JSON.
    Возвращает стандартный словарь с оценкой.

    Args:
        raw_response: Ответ от LLM (строка).

    Returns:
        Словарь в формате:
        {
          "scores": { ... },
          "total_score": int,
          "critical_errors": [...],
          "feedback_positive": [...],
          "feedback_improvement": [...],
          "recommendations": [...],
          "timecodes": [...],
          ...
        }
        Если парсинг не удался — возвращает заглушку с ошибкой.
    """
    try:
        # 1. Извлечь JSON из ответа (если LLM обернул его в ```json ... ```)
        # Ищем блок ```json ... ``` (с учётом многострочности)
        match = re.search(r"```json\n(.*?)\n```", raw_response, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
        else:
            # Если не нашли блок, пробуем использовать весь raw_response
            json_str = raw_response.strip()

        # 2. Попробовать распарсить JSON
        parsed = json.loads(json_str)

    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        # Если не удалось распарсить — вернуть заглушку
        logger.warning(f"LLM вернул некорректный JSON, возвращаю заглушку. Ошибка: {e}\nОтвет: {raw_response}")
        return _get_default_response(error="LLM вернул некорректный формат ответа")

    # 3. Валидация структуры
    expected_keys = [
        "scores", "total_score", "critical_errors", "feedback_positive",
        "feedback_improvement", "recommendations", "timecodes"
    ]

    for key in expected_keys:
        if key not in parsed:
            logger.warning(f"LLM не вернул ключ '{key}', использую значение по умолчанию.")
            # Заполнить недостающие ключи пустыми значениями
            parsed[key] = {} if key == "scores" else [] if key in ["critical_errors", "feedback_positive", "feedback_improvement", "recommendations", "timecodes"] else 0

    # 4. Дополнительная валидация: убедиться, что 'scores' — словарь, 'critical_errors' — список и т.д.
    if not isinstance(parsed["scores"], dict):
        logger.warning("Поле 'scores' не является словарём, заменяю на пустой словарь.")
        parsed["scores"] = {}
    if not isinstance(parsed["critical_errors"], list):
        logger.warning("Поле 'critical_errors' не является списком, заменяю на пустой список.")
        parsed["critical_errors"] = []
    if not isinstance(parsed["feedback_positive"], list):
        logger.warning("Поле 'feedback_positive' не является списком, заменяю на пустой список.")
        parsed["feedback_positive"] = []
    if not isinstance(parsed["feedback_improvement"], list):
        logger.warning("Поле 'feedback_improvement' не является списком, заменяю на пустой список.")
        parsed["feedback_improvement"] = []
    if not isinstance(parsed["recommendations"], list):
        logger.warning("Поле 'recommendations' не является списком, заменяю на пустой список.")
        parsed["recommendations"] = []
    if not isinstance(parsed["timecodes"], list):
        logger.warning("Поле 'timecodes' не является списком, заменяю на пустой список.")
        parsed["timecodes"] = []
    if not isinstance(parsed["total_score"], (int, float)):
        logger.warning("Поле 'total_score' не является числом, заменяю на 0.")
        parsed["total_score"] = 0

    # 5. Возврат корректного JSON
    return parsed


def _get_default_response(error: str = None) -> Dict[str, Any]:
    """
    Возвращает стандартную заглушку в случае ошибки.
    """
    base_response = {
        "scores": {},
        "total_score": 0,
        "critical_errors": ["LLM вернул некорректный формат ответа"] if error else [],
        "feedback_positive": [],
        "feedback_improvement": [],
        "recommendations": [],
        "timecodes": []
    }
    if error:
        base_response["error"] = error
    return base_response
