import json
from typing import List, Dict, Any

from .scenarios import get_scenario_config


def build_evaluate_prompt(
    transcript: List[Dict[str, str]],
    client_profile: Dict[str, Any],
    scenario_id: str,
    model_name: str,
) -> str:
    """
    Собирает промпт для LLM под КОНКРЕТНЫЙ сценарий (ветку скрипта).

    transcript: список dict'ов вида {"role": "manager"|"client", "text": "..."}
    client_profile: профиль клиента (тип, налоговый режим, сотрудники и т.п.)
    scenario_id: id сценария из SCENARIO_CONFIG
    model_name: имя модели (например, "qwen2:7b-instruct-q4_K_M") — пишем в ответ для трассировки
    """
    scenario = get_scenario_config(scenario_id)

    relevant_criteria = scenario.relevant_criteria
    must_have = scenario.compliance_must_have
    must_avoid = scenario.compliance_must_avoid

    # текстовый вид диалога
    transcript_str = "\n".join(
        f"{msg['role'].upper()}: {msg['text']}"
        for msg in transcript
    )

    criteria_str = ", ".join(relevant_criteria)

    # "скелет" JSON-ответа, по которому мы ориентируем модель
    expected_json_schema = {
        # все критерии по умолчанию False, politeness по умолчанию 0
        "scores": {name: False for name in relevant_criteria} | {"politeness": 0},
        # total_score будет пересчитан на бэкенде по scores и weights
        "total_score": 0,
        "critical_errors": [],
        "feedback_positive": [],
        "feedback_improvement": [],
        "recommendations": [],
        "timecodes": [],
        "scenario_id": scenario_id,
        "client_profile": client_profile,
        "relevant_criteria": relevant_criteria,
        "model_used": model_name,
        "compliance_check": {}
    }

    prompt = f"""
Ты — внутренний ассистент по контролю качества звонков Ozon Bank.
Оцени ОДИН конкретный диалог по сценарию: "{scenario.title}".

Описание сценария (контекст для тебя, не повторяй его в ответе):
{scenario.description}

Важно по приветствию:
- Менеджер должен представиться в формате: "Это <имя> из Ozon" (без слова "банк" в самопрезентации).
- В начале разговора менеджер должен поздравить клиента с регистрацией на Ozon фразой типа:
  "Поздравляю с регистрацией!" или близкой по смыслу.
- ВАЖНО: слово "банк" запрещено именно в САМОПРЕЗЕНТАЦИИ/ПРИВЕТСТВИИ.
  В описании продукта фраза "расчетный счет от Озон Банка ..." допустима.

Профиль клиента:
{json.dumps(client_profile, ensure_ascii=False, indent=2)}

Уровень сложности тренировки: {scenario.difficulty}
Архетип клиента: {scenario.client_archetype}

Транскрипт диалога (порядок реплик важен):
{transcript_str}

Твоя задача:
1. Оценить только следующие критерии: {criteria_str}.
2. Проверить, были ли соблюдены обязательные элементы для ЭТОГО сценария:
   - {chr(10).join("- " + item for item in must_have)}
3. Убедиться, что НЕ используются запрещённые формулировки:
   - {chr(10).join("- " + item for item in must_avoid)}
4. НЕ придумывать дополнительных критериев, сценариев или веток.

Поле "politeness":
- Это целое число от 0 до 10.
- 0–2: грубо/резко, много некорректных формулировок.
- 3–5: нейтрально/сухо, вежливость минимальная.
- 6–8: вежливо, корректно, профессионально.
- 9–10: образцово вежливо и деликатно.

Поле "total_score":
- НЕ вычисляй итоговый балл.
- Поставь "total_score": 0.
- Итоговый балл будет рассчитан на бэкенде по твоим "scores" и "politeness" с учётом весов сценария.

Формат ответа:
Верни ТОЛЬКО один JSON-объект без Markdown, без ```json, без пояснений.
JSON должен строго соответствовать структуре ниже по ключам,
но значения (кроме total_score) выставь по результатам анализа:

{json.dumps(expected_json_schema, ensure_ascii=False, indent=2)}

Ещё раз: ответ должен быть ЧИСТЫМ JSON, без Markdown, без дополнительного текста.
"""
    return prompt.strip()
