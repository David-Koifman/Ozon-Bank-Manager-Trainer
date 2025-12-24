import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _default_error_result(raw: str, err: Exception) -> Dict[str, Any]:
    """
    Единая заглушка на случай, если LLM вернул мусор / невалидный JSON.
    """
    logger.warning(
        "LLM вернул некорректный JSON, возвращаю заглушку. Ошибка: %s\nОтвет: %s",
        str(err),
        raw,
    )
    return {
        "error": "invalid_json",
        "scores": {},
        "total_score": 0,
        "critical_errors": ["LLM вернул некорректный JSON"],
        "feedback_positive": [],
        "feedback_improvement": [],
        "recommendations": [],
        "timecodes": [],
    }


def _strip_code_fences(text: str) -> str:
    """
    Убирает ```json ... ``` и ``` ... ``` если модель завернула ответ в Markdown.
    """
    t = text.strip()

    # ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return t


def _extract_json_object(text: str) -> str:
    """
    Пытается извлечь JSON-объект из произвольного текста.
    Работает для кейсов вида:
      "Вот оценка:\n{...json...}"
      "{...json...}\nСпасибо!"
    """
    s = text.strip()

    first = s.find("{")
    last = s.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError("No JSON object boundaries found")

    candidate = s[first : last + 1].strip()
    return candidate


def parse_llm_response(raw: str) -> Dict[str, Any]:
    """
    Парсит ответ LLM в JSON.

    Поддерживаемые форматы:
    - чистый JSON
    - JSON в ```json ... ```
    - JSON с префиксом/суффиксом (например "Вот оценка:")

    Возвращает dict. В случае ошибки возвращает заглушку.
    """
    if raw is None:
        return _default_error_result("", ValueError("raw is None"))

    raw_text = str(raw)

    # 1) Снимаем markdown fences
    cleaned = _strip_code_fences(raw_text)

    # 2) Попытка №1: json.loads как есть
    try:
        data = json.loads(cleaned)
    except Exception as e1:
        # 3) Попытка №2: вытащить подстроку с {...}
        try:
            extracted = _extract_json_object(cleaned)
            data = json.loads(extracted)
        except Exception as e2:
            return _default_error_result(raw_text, e2)

    # 4) Нормализуем структуру (чтобы judge не падал на отсутствующих ключах)
    if not isinstance(data, dict):
        return _default_error_result(raw_text, ValueError("JSON root is not an object"))

    data.setdefault("scores", {})
    data.setdefault("total_score", 0)
    data.setdefault("critical_errors", [])
    data.setdefault("feedback_positive", [])
    data.setdefault("feedback_improvement", [])
    data.setdefault("recommendations", [])
    data.setdefault("timecodes", [])

    return data
