"""
Dialogue prompt building logic based on llm_dialogue.py
Handles scenario loading, system prompt building, and conversation prompt construction.
"""
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_text_line(text: str) -> str:
    """
    Нормализуем одну строку текста:
    - приводим "красивые" кавычки и тире к обычным,
    - убираем переводы строк,
    - схлопываем лишние пробелы.
    Подходит и для длинных текстов.
    """
    if not text:
        return ""

    # Приводим красивые кавычки/тире к обычным
    replacements = {
        """: '"', """: '"', "„": '"', "«": '"', "»": '"',
        "'": "'", "'": "'",
        "—": "-", "–": "-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Переводы строк -> пробел
    text = text.replace("\r", " ").replace("\n", " ")

    # Схлопываем пробелы
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_reply(raw: str, max_sentences: int = 3) -> str:
    """
    Чистим ответ модели:
    - убираем префиксы ролей в начале строки,
    - убираем маркеры списков,
    - нормализуем кавычки/тире/пробелы,
    - оставляем только русские символы + цифры + базовую пунктуацию,
    - ограничиваемся 1–3 предложениями (но НЕ режем по первой строке).
    """
    if not raw:
        return ""

    text = raw.strip()

    # Убираем префиксы ролей только в НАЧАЛЕ строки:
    # "Оператор: ..." / "Менеджер: ..." / "Operator: ..." / "Manager: ..."
    text = re.sub(
        r"^\s*(Оператор|Менеджер|Manager|Operator)\s*[:\-–]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Убираем маркеры списков в начале: "- ", "* ", "• "
    text = re.sub(r"^\s*[\-\*\•]+\s*", "", text)

    # Нормализуем кавычки/тире/пробелы и убираем внутренние переносы строк
    text = normalize_text_line(text)

    # Оставляем только русские буквы, цифры и базовую пунктуацию
    text = re.sub(r"[^А-Яа-яЁё0-9,.;:!?()\"'\-\s]", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    if not text:
        return ""

    # Ограничиваем количество предложений (1–3), чтобы ответ не был полотном
    # Разбиваем по . ! ? с сохранением знака
    parts = re.split(r'(?<=[.!?])\s+', text)
    if parts:
        text = " ".join(parts[:max_sentences]).strip()

    return text


def normalize_phrases(raw):
    """
    Превращаем массив фраз из JSON в список строк.
    Поддерживает строки и объекты вида {"text": "..."}.
    """
    if not raw:
        return []
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            v = item.get("text") or item.get("phrase") or item.get("value")
            if isinstance(v, str):
                out.append(v)
    return [x for x in out if x]


def detect_stage(manager_turns: int) -> str:
    """
    Грубое приближение:
    1-й ход менеджера  -> attention
    2–3-й              -> interest
    4–6-й              -> desire
    7+                 -> action
    """
    if manager_turns <= 1:
        return "attention"
    if manager_turns <= 3:
        return "interest"
    if manager_turns <= 6:
        return "desire"
    return "action"


def load_scenario(name: str) -> Tuple[Dict, str]:
    """
    Загружает сценарий из JSON и Markdown-промпт.
    
    Args:
        name: Имя сценария без расширения
        
    Returns:
        Tuple[scenario_dict, markdown_prompt]
    """
    # Определяем базовый путь (backend директория)
    # Файл находится в backend/components/, поэтому parent.parent = backend/
    backend_dir = Path(__file__).parent.parent
    
    # Путь к JSON сценарию
    json_path = backend_dir / "scenarios" / f"{name}.json"
    
    if not json_path.exists():
        raise FileNotFoundError(
            f"❌ Сценарий '{name}' не найден. Проверьте наличие файла backend/scenarios/{name}.json"
        )
    
    # Путь к Markdown-промпту
    md_path = backend_dir / "prompts" / f"{name}.md"
    
    if not md_path.exists():
        # Если markdown не найден, используем пустую строку
        logger.warning(f"Markdown промпт для сценария '{name}' не найден, используется пустая строка")
        md_content = ""
    else:
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
    
    with open(json_path, "r", encoding="utf-8") as f:
        scenario = json.load(f)
    
    return scenario, md_content


def build_system_prompt(
    scenario: Dict,
    md_prompt: str,
    archetype_id: str = "novice",
    level_id: str = "1"
) -> str:
    """
    Собираем системный промпт из JSON-сценария + Markdown-промпта.
    archetype_id / level_id приходят с CLI и берутся из client_behavior_presets.
    """
    profile = scenario.get("client_profile", {}) or {}
    objectives = scenario.get("dialog_objectives", {}) or {}
    compliance = scenario.get("compliance_requirements", {}) or {}
    presets = scenario.get("client_behavior_presets", {}) or {}
    aida = scenario.get("aida_flow", {}) or {}
    scenario_id = scenario.get("scenario_id", "")
    scenario_title = scenario.get("title") or scenario.get("name") or "сценарий тренировки"

    archetypes = presets.get("archetypes", {}) or {}
    difficulty_levels = presets.get("difficulty_levels", {}) or {}

    archetype = archetypes.get(archetype_id, {}) or {}
    difficulty = difficulty_levels.get(level_id, {}) or {}

    mandatory = normalize_phrases(compliance.get("mandatory_phrases", []))
    forbidden = normalize_phrases(compliance.get("forbidden_phrases", []))

    # Более явное описание архетипа / сложности для модели
    archetype_name = archetype.get("name") or archetype_id
    archetype_personality = archetype.get("personality") or archetype.get("description") or ""
    difficulty_name = difficulty.get("name") or level_id
    difficulty_desc = difficulty.get("description") or ""

    return f"""
Ты — ИИ-клиент на телефонном звонке с менеджером по {scenario_title}.
Сценарий: {scenario_id or "без явного идентификатора"}.
Твой архетип клиента: {archetype_name} (id: {archetype_id}).
Кратко о характере архетипа: {archetype_personality or "см. описание ниже"}.
Уровень сложности: {difficulty_name} (id: {level_id}).
Что означает этот уровень сложности для поведения клиента: {difficulty_desc or "см. описание ниже"}.

Говоришь ТОЛЬКО от лица клиента, в первом лице ("я").
НИКОГДА не пишешь реплики за менеджера и не используешь префиксы "Менеджер:", "Оператор:" и т.п.

Формат речи:
- отвечаешь только на ПОСЛЕДНЮЮ фразу менеджера;
- 1–3 коротких, естественных предложения;
- деловой тон, в соответствии с архетипом ({archetype_name}) и его характером;
- ТОЛЬКО на русском языке, без английских слов и технических комментариев.

Ключевые правила поведения:
- НЕ повторяй дословно один и тот же вопрос или замечание.
  Если ты уже спрашивал что-то в духе "Подождите, какой счёт?" или аналогичный вопрос,
  больше так дословно не повторяй, переформулируй или задай новый уточняющий вопрос.
- Если менеджер уже начал объяснять условия и выгоды, НЕ возвращайся к самым первым базовым вопросам,
  лучше уточни детали или вырази сомнения/интерес.
- На этапе действия (action) — если условия понятны и в целом подходят,
  логично согласиться на следующий шаг (встреча, оформление, тест),
  либо аккуратно отказаться, но НЕ возвращаться к самому первому вопросу.

Обязательно:
- придерживайся архетипа клиента и уровня сложности;
- если сложность выше, можешь давать больше возражений, сомнений, вопросов;
- если это агрессивный/стрессовый архетип — допускается повышенный тон, перебивания, но без откровенных оскорблений.

Профиль клиента (кто ты и в какой ситуации находишься):
{json.dumps(profile, ensure_ascii=False, indent=2)}

Архетип клиента (описание поведения, эмоций и стиля общения):
{json.dumps(archetype, ensure_ascii=False, indent=2)}

Уровень сложности (что от тебя ожидается на этом уровне):
{json.dumps(difficulty, ensure_ascii=False, indent=2)}

Инструкция поведения (Markdown-промпт сценария):
{md_prompt}

Цели тренировки (что менеджер должен отработать):
{json.dumps(objectives, ensure_ascii=False, indent=2)}

AIDA (этапы диалога и логика движения разговора):
{json.dumps(aida, ensure_ascii=False, indent=2)}

Обязательные фразы менеджера (для информации клиента — он может на них реагировать):
{json.dumps(mandatory, ensure_ascii=False, indent=2)}

Запрещённые фразы для менеджера (клиент может настороженно реагировать, если слышит подобное):
{json.dumps(forbidden, ensure_ascii=False, indent=2)}
""".strip()


def make_prompt(
    system_prompt: str,
    conversation: List[Dict[str, str]],
    max_turns: int = 8
) -> str:
    """
    Собирает полный промпт для модели из системного промпта и истории диалога.
    
    Args:
        system_prompt: Системный промпт
        conversation: История диалога [{role: "manager"/"client", text: "..."}]
        max_turns: Максимальное количество последних реплик для включения
        
    Returns:
        Полный промпт для модели
    """
    manager_turns = sum(1 for t in conversation if t["role"] == "manager")
    stage = detect_stage(manager_turns)

    history = conversation[-max_turns:]
    lines = [system_prompt, ""]
    lines.append(f"Текущий этап AIDA (примерно): {stage}")
    if stage == "attention":
        lines.append("На этом этапе клиент только знакомится с менеджером и контекстом, НЕ задаёт слишком много однотипных вопросов и может проявлять лёгкое недоверие или удивление.")
    elif stage == "interest":
        lines.append("На этом этапе клиент проявляет интерес и задаёт 1–2 уточняющих вопроса, но не зацикливается на одном и том же. Он старается понять выгоды и риски.")
    elif stage == "desire":
        lines.append("На этом этапе клиент обсуждает выгоды, сравнивает с текущим решением, может осторожно соглашаться протестировать продукт или углубляться в детали.")
    else:
        lines.append("На этапе action клиент либо соглашается на следующий шаг (встреча/оформление/тест), либо вежливо отказывается, но НЕ возвращается к самым первым вопросам.")

    lines.append("")
    lines.append("История диалога (последние реплики):")
    for turn in history:
        role = "Менеджер" if turn["role"] == "manager" else "Клиент"
        lines.append(f"{role}: {turn['text']}")
    lines.append("")
    lines.append("Ответ клиента (1–3 коротких предложения, без повторения уже заданных им самим вопросов и без реплик за менеджера):")
    return "\n".join(lines)

