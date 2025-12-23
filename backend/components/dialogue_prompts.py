"""
Dialogue prompt building logic based on dialogue_simulator.py
Handles system prompt building and conversation prompt construction.
All prompt settings are hardcoded, no external config files.
"""
import json
import re
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# Regex patterns for text processing
ROLE_PREFIX_RE = re.compile(r"^\s*(Оператор|Менеджер|Клиент|Manager|Operator|Client)\s*[:\-–]\s*", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*[\-\*\•]+\s*")
WS_RE = re.compile(r"\s+")

# Разрешаем: русские, английские, цифры, базовая пунктуация, пробелы
# + добавили "…" и "№" (часто встречаются в русском, чтобы не было ложных NON_RU)
ALLOWED_BASIC_RE = re.compile(
    r"[^А-Яа-яЁёA-Za-z0-9,.;:!?()\"'«»""„\-\s/&_+%#…№]"
)

# Быстрый детектор "чужих" символов (CJK/арабский и т.п.) — также разрешаем … и №
NON_RU_EN_LETTER_RE = re.compile(
    r"[^\sА-Яа-яЁёA-Za-z0-9,.;:!?()\"'«»""„\-\s/&_+%#…№]"
)

# Детектор "клиент начал интервьюировать менеджера" (вопросы во 2-м лице)
ROLE_SWAP_PATTERNS = [
    r"\bсколько\s+вы\b",
    r"\bсколько\s+у\s+вас\b",
    r"\bкакие\s+у\s+вас\b",
    r"\bкакая\s+у\s+вас\b",
    r"\bкаков[ао]\s+у\s+вас\b",
    r"\bу\s+вас\b.*\?",
    r"\bвы\b.*\?",
    r"\bскажите\b.*\?",
    r"\bподскажите\b.*\?",
]
ROLE_SWAP_RE = re.compile("|".join(ROLE_SWAP_PATTERNS), re.IGNORECASE)

# Мета-триггеры для детекции утечек
META_TRIGGERS = [
    "как клиент", "как менеджер", "инструкция", "правила", "план", "aida", "методич",
    "язык модели", "system", "prompt", "в этом диалоге", "буду отвечать", "рекомендац",
]
ROLE_LEAK_TRIGGERS = ["менеджер:", "оператор:", "manager:", "operator:"]


def normalize_text_line(text: str) -> str:
    """
    Нормализуем одну строку текста:
    - приводим "красивые" кавычки и тире к обычным,
    - убираем переводы строк,
    - схлопываем лишние пробелы,
    - нормализуем non-breaking space и многоточие.
    Подходит и для длинных текстов.
    """
    if not text:
        return ""

    replacements = {
        """: '"', """: '"', "„": '"', "«": '"', "»": '"',
        "'": "'", "'": "'",
        "—": "-", "–": "-",
        "\u00a0": " ",  # non-breaking space
        "…": "...",     # нормализуем многоточие
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Переводы строк -> пробел
    text = text.replace("\r", " ").replace("\n", " ")
    text = WS_RE.sub(" ", text)
    return text.strip()


def _trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """Режем по последней границе предложения в пределах max_chars (чтобы не обрубать мысль)."""
    if not text or max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars].rstrip()

    # Ищем последнюю пунктуацию конца предложения.
    last_end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))

    # Если нашли конец предложения достаточно далеко (>= 55% лимита), режем там.
    if last_end >= max(0, int(max_chars * 0.55)):
        return cut[: last_end + 1].strip()

    # Иначе просто мягко обрежем по символам (лучше чем пусто).
    return cut.strip()


def clean_reply(raw: str, max_sentences: int = 5, reply_max_chars: int = 320) -> str:
    """
    1) вычищает префиксы ролей/буллеты
    2) нормализует
    3) удаляет "странные" символы, но сохраняет RU+EN (бренды)
    4) ограничивает по предложениям и по символам (по границе предложения)
    """
    if not raw:
        return ""
    text = raw.strip()
    text = ROLE_PREFIX_RE.sub("", text)
    text = BULLET_RE.sub("", text)
    text = normalize_text_line(text)

    # выкидываем совсем "левые" символы, но не трогаем A-Za-z (Google Sheets/Excel)
    text = ALLOWED_BASIC_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    if not text:
        return ""

    # ограничение по предложениям
    parts = re.split(r"(?<=[.!?])\s+", text)
    if parts:
        text = " ".join(parts[:max_sentences]).strip()

    # ограничение по символам (по границе предложения)
    text = _trim_to_sentence_boundary(text, reply_max_chars)
    return text


def clean_manager_input(raw: str) -> str:
    """Очищает ввод менеджера от префиксов ролей и нормализует."""
    if not raw:
        return ""
    text = raw.strip()
    text = ROLE_PREFIX_RE.sub("", text)
    return normalize_text_line(text)


def has_non_ru_en_garbage(text: str) -> bool:
    """True если есть символы вне RU/EN/цифр/базовой пунктуации."""
    if not text:
        return True
    return bool(NON_RU_EN_LETTER_RE.search(text))


def raw_has_non_ru_en_garbage(raw: str) -> bool:
    """Проверка мусора на сыром тексте (до чистки), чтобы ретраи реально имели смысл."""
    if not raw:
        return True
    t = raw.strip()
    t = ROLE_PREFIX_RE.sub("", t)
    t = normalize_text_line(t)
    return bool(NON_RU_EN_LETTER_RE.search(t))


def is_meta_or_role_leak(text: str) -> bool:
    """Проверяет наличие мета-утечек или префиксов ролей в ответе."""
    if not text:
        return True
    t = text.strip().lower()
    if any(x in t for x in ROLE_LEAK_TRIGGERS):
        return True
    if any(x in t for x in META_TRIGGERS):
        return True
    if "\n" in t:
        return True
    return False


def is_role_swap(reply: str) -> bool:
    """True если ответ клиента выглядит как вопрос менеджеру (2-е лицо)."""
    if not reply:
        return True
    t = reply.strip()
    if "?" in t and ROLE_SWAP_RE.search(t):
        return True
    return False


def _simple_normalized(text: str) -> str:
    """Нормализует текст для сравнения (убирает пунктуацию, приводит к нижнему регистру)."""
    t = (text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = WS_RE.sub(" ", t).strip()
    return t


def is_repeat_reply(prev: str, new: str) -> bool:
    """Проверяет, не повторяется ли новый ответ относительно предыдущего (Jaccard >= 0.85)."""
    a = _simple_normalized(prev)
    b = _simple_normalized(new)
    if not a or not b:
        return False
    if a == b:
        return True
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return False
    j = len(sa & sb) / max(1, len(sa | sb))
    return j >= 0.85


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


# Архетипы клиентов (как в dialogue_simulator.py)
ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "novice": {
        "name": "Новичок",
        "personality": "Я только начинаю, хочу простые объяснения, могу путаться, но без агрессии.",
        "speech_style": "коротко, по делу, иногда уточняю базовые вещи",
        "default_goal": "понять, что это и нужно ли мне",
        "taboos": ["не изображай эксперта", "не используй сложные термины без просьбы"],
    },
    "skeptic": {
        "name": "Скептик",
        "personality": "Не доверяю, ищу подвох, не люблю воду, требую конкретику.",
        "speech_style": "строго, без эмоций, 'покажите цифры'",
        "default_goal": "минимизировать риск и не попасть на комиссии",
        "taboos": ["не становись дружелюбным", "не соглашайся слишком быстро"],
    },
    "busy_owner": {
        "name": "Занятой предприниматель",
        "personality": "У меня нет времени, я постоянно в делах. Если тянут время — раздражаюсь.",
        "speech_style": "короткие фразы, перебиваю, прошу тезисы",
        "default_goal": "быстро понять выгоду и сколько времени займёт",
        "taboos": ["не уходи в длинные монологи"],
    },
    "friendly": {
        "name": "Дружелюбный",
        "personality": "Нормально отношусь к звонку, готов обсудить, но всё равно считаю деньги.",
        "speech_style": "вежливо, без резкости, задаю вопросы",
        "default_goal": "подобрать удобный вариант",
        "taboos": ["не становись слишком 'сладким'"],
    },
}

# Уровни сложности (как в dialogue_simulator.py)
DIFFICULTY: Dict[str, Dict[str, Any]] = {
    "1": {"name": "1 — Лёгкий", "question_rate": "low", "resistance": "low", "traps": False},
    "2": {"name": "2 — Нормальный", "question_rate": "medium", "resistance": "medium", "traps": False},
    "3": {"name": "3 — Сложный", "question_rate": "medium", "resistance": "high", "traps": True},
    "4": {"name": "4 — Очень сложный", "question_rate": "high", "resistance": "very_high", "traps": True},
}

# Продукты/сценарии (как в dialogue_simulator.py)
PRODUCTS: Dict[str, Dict[str, Any]] = {
    "free": {
        "name": "Свободная тема",
        "description": "Без сценариев. Клиент — личность (архетип+сложность).",
        "facts": [],
        "goal": "",
        "typical_next_steps": [],
    },
    "rko": {
        "name": "РКО",
        "description": "Разговор про расчётный счёт/комиссии/обслуживание/подключение.",
        "facts": [
            "У клиента может быть счёт в другом банке",
            "Клиента волнуют комиссии, обслуживание, лимиты, скорость операций",
        ],
        "goal": "понять выгоду/риски и решить, есть ли смысл двигаться дальше",
        "typical_next_steps": ["получить расчёт тарифа", "назначить созвон/встречу", "оставить контакты"],
    },
    "bank_card": {
        "name": "Бизнес-карта",
        "description": "Разговор про карту, лимиты, кэшбэк, контроль расходов.",
        "facts": [
            "Клиенту важны лимиты, комиссии, безопасность",
            "Иногда нужна карта для сотрудников",
        ],
        "goal": "понять выгоду и стоит ли оформлять",
        "typical_next_steps": ["уточнить тариф", "оформить заявку", "созвон для деталей"],
    },
}


def _compact_json_list(xs: List[str]) -> str:
    """Компактный формат списка для промпта: [item1; item2; item3]"""
    if not xs:
        return "[]"
    return "[" + "; ".join(xs) + "]"


def resolve_archetype(archetype_id: str) -> Dict[str, Any]:
    """Разрешает архетип по ID с fallback."""
    return ARCHETYPES.get(archetype_id, {
        "name": archetype_id,
        "personality": "Неизвестный архетип (fallback). Веди себя нейтрально.",
        "speech_style": "кратко",
        "default_goal": "понять суть",
        "taboos": [],
    })


def resolve_difficulty(level_id: str) -> Dict[str, Any]:
    """Разрешает уровень сложности по ID с fallback."""
    return DIFFICULTY.get(level_id, {
        "name": level_id, "question_rate": "medium", "resistance": "medium", "traps": False,
    })


def resolve_product(product_id: str) -> Dict[str, Any]:
    """Разрешает продукт/сценарий по ID с fallback."""
    return PRODUCTS.get(product_id, {
        "name": product_id, "description": "Неизвестный продукт (fallback).",
        "facts": [], "goal": "", "typical_next_steps": [],
    })


def build_system_prompt(
    archetype_id: str = "novice",
    level_id: str = "1",
    product_id: str = "free"
) -> str:
    """
    Собираем системный промпт в новом компактном формате (как в dialogue_simulator.py).
    archetype_id / level_id / product_id приходят с frontend.
    
    Args:
        archetype_id: ID архетипа клиента
        level_id: ID уровня сложности
        product_id: ID продукта/сценария
    """
    a = resolve_archetype(archetype_id)
    d = resolve_difficulty(level_id)
    p = resolve_product(product_id)

    traps_hint = "ловушки=да" if d.get("traps") else "ловушки=нет"
    taboos_line = _compact_json_list(a.get("taboos", []) or [])

    product_line = ""
    if product_id != "free":
        product_line = (
            f"\nКонтекст: {p.get('name')} ({p.get('description')})"
            f"\nФакты: {_compact_json_list(p.get('facts', []) or [])}"
            f"\nЦель клиента: {p.get('goal','')}"
        )

    # Усиление правила инициативы: запрет на "интервью менеджера"
    if archetype_id == "novice":
        initiative_rule = (
            "Правило инициативы: если менеджер задаёт вопросы — отвечай ТОЛЬКО про себя/свою компанию. "
            "Вообще не задавай встречных вопросов менеджеру. "
            "Если не понял — скажи 'Не понял, поясните простыми словами' (без вопроса 'у вас/вы').\n"
        )
    else:
        initiative_rule = (
            "Правило инициативы: если менеджер задаёт вопросы — отвечай ТОЛЬКО про себя/свою компанию. "
            "Не задавай встречных вопросов менеджеру. "
            "Если нужно уточнение — максимум ОДИН вопрос и только про себя/свою ситуацию.\n"
        )

    hard_bans = (
        "Запрещено: задавать вопросы про менеджера/банк/условия менеджера во 2-м лице "
        "(например: 'Скажите, сколько вы платите', 'Какие у вас комиссии', 'Сколько у вас платежей').\n"
    )

    # Базовый промпт (как в dialogue_simulator)
    prompt = (
        "Ты — ИИ-клиент. Отвечай ТОЛЬКО как клиент.\n"
        "Язык: ТОЛЬКО русский.\n"
        "Английские слова допускаются ТОЛЬКО как названия брендов/сервисов/продуктов (пример: Google Sheets, Excel, CRM).\n"
        "НЕ используй другие языки (например: 中文, العربية) — если так получилось, перефразируй по-русски, оставив только бренды на английском.\n"
        "Формат: 1–5 коротких предложений (по смыслу), без списков.\n"
        f"{initiative_rule}"
        f"{hard_bans}"
        "Нельзя: инструкции/планы/объяснение правил/роль 'менеджера'.\n"
        f"Личность: {a.get('name')} | {a.get('personality')} | стиль: {a.get('speech_style')} | цель: {a.get('default_goal')} | табу: {taboos_line}\n"
        f"Сложность: {d.get('name')} | сопротивление={d.get('resistance')} | вопросы={d.get('question_rate')} | {traps_hint}"
        f"{product_line}"
    )

    return prompt


def make_prompt(
    system_prompt: str,
    conversation: List[Dict[str, str]],
    max_turns: int = 8
) -> str:
    """
    Собирает полный промпт для модели в новом формате (как в dialogue_simulator.py).
    
    Args:
        system_prompt: Системный промпт
        conversation: История диалога [{role: "manager"/"client", text: "..."}]
        max_turns: Максимальное количество последних реплик для включения
        
    Returns:
        Полный промпт для модели в формате:
        [system_prompt]
        
        Диалог:
        M: [manager text]
        C: [client text]
        ...
        C:
    """
    history = conversation[-max_turns:] if max_turns > 0 else conversation[:]
    lines = [system_prompt, "\nДиалог:"]
    for turn in history:
        role = "M" if turn["role"] == "manager" else "C"
        lines.append(f"{role}: {turn['text']}")
    lines.append("C:")
    return "\n".join(lines)

