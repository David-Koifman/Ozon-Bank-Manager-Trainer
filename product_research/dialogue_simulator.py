
import os
import re
import json
import time
import argparse
import subprocess
from typing import Optional, Tuple, List, Dict, Any
from urllib import request, error as urlerror

# ============================================================
# ТЕКСТОВЫЕ УТИЛИТЫ
# ============================================================

ROLE_PREFIX_RE = re.compile(r"^\s*(Оператор|Менеджер|Клиент|Manager|Operator|Client)\s*[:\-–]\s*", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*[\-\*\•]+\s*")
WS_RE = re.compile(r"\s+")

# Разрешаем: русские, английские, цифры, базовая пунктуация, пробелы
# + добавили “…” и “№” (часто встречаются в русском, чтобы не было ложных NON_RU)
ALLOWED_BASIC_RE = re.compile(
    r"[^А-Яа-яЁёA-Za-z0-9,.;:!?()\"'«»“”„\-\s/&_+%#…№]"
)

# Быстрый детектор "чужих" символов (CJK/арабский и т.п.) — также разрешаем … и №
NON_RU_EN_LETTER_RE = re.compile(
    r"[^\sА-Яа-яЁёA-Za-z0-9,.;:!?()\"'«»“”„\-\s/&_+%#…№]"
)

def normalize_text_line(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
        "’": "'", "‘": "'",
        "—": "-", "–": "-",
        "\u00a0": " ",  # non-breaking space
        "…": "...",     # нормализуем многоточие
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = text.replace("\r", " ").replace("\n", " ")
    text = WS_RE.sub(" ", text)
    return text.strip()

def clean_manager_input(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()
    text = ROLE_PREFIX_RE.sub("", text)
    return normalize_text_line(text)

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

# ============================================================
# ПРИБЛИЖЁННАЯ ОЦЕНКА ТОКЕНОВ
# ============================================================

def _approx_tokens_ru(text: str) -> int:
    if not text:
        return 0
    t = normalize_text_line(text)
    words = re.findall(r"\w+", t, flags=re.UNICODE)
    by_words = len(words)
    by_chars = max(1, int(len(t) / 4))
    return max(1, int((by_words + by_chars) / 2))

# ============================================================
# МЕТРИКИ
# ============================================================

def summarize_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {"count": 0}

    lat_total = [r["latency_total_s"] for r in records if r.get("latency_total_s") is not None]
    lat_model = [r["latency_model_s"] for r in records if r.get("latency_model_s") is not None]
    out_tok = [r["out_tokens"] for r in records if r.get("out_tokens") is not None]
    in_tok = [r["in_tokens"] for r in records if r.get("in_tokens") is not None]
    tps = [r["tps"] for r in records if r.get("tps") is not None]

    ok = [r for r in records if r.get("err_reason") is None]
    timeouts = sum(1 for r in records if r.get("err_reason") == "TIMEOUT")
    errors = sum(1 for r in records if r.get("err_reason") in ("OLLAMA_ERROR", "HTTP_ERROR"))

    def p50(xs):
        xs = sorted(xs)
        return xs[len(xs)//2] if xs else None

    def avg(xs):
        return (sum(xs) / len(xs)) if xs else None

    return {
        "count": len(records),
        "ok": len(ok),
        "timeouts": timeouts,
        "errors": errors,
        "lat_total_avg": avg(lat_total),
        "lat_total_p50": p50(lat_total),
        "lat_total_min": min(lat_total) if lat_total else None,
        "lat_total_max": max(lat_total) if lat_total else None,
        "lat_model_avg": avg(lat_model),
        "lat_model_p50": p50(lat_model),
        "in_tokens_total": sum(in_tok) if in_tok else 0,
        "out_tokens_total": sum(out_tok) if out_tok else 0,
        "tps_avg": avg(tps),
        "tps_p50": p50(tps),
    }

def print_metrics_summary(records: List[Dict[str, Any]]):
    s = summarize_metrics(records)
    if s["count"] == 0:
        print("\n📊 Метрики: нет данных.")
        return

    print("\n📊 Метрики сессии (приближённые):")
    print(f"- запросов: {s['count']} | ok: {s['ok']} | timeout: {s['timeouts']} | errors: {s['errors']}")
    if s["lat_total_avg"] is not None:
        print(f"- latency_total (s): avg={s['lat_total_avg']:.2f} | p50={s['lat_total_p50']:.2f} | min={s['lat_total_min']:.2f} | max={s['lat_total_max']:.2f}")
    if s["lat_model_avg"] is not None:
        print(f"- latency_model (s): avg={s['lat_model_avg']:.2f} | p50={s['lat_model_p50']:.2f}")
    print(f"- tokens: in_total={s['in_tokens_total']} | out_total={s['out_tokens_total']}")
    if s["tps_avg"] is not None:
        print(f"- tokens/sec: avg={s['tps_avg']:.2f} | p50={s['tps_p50']:.2f}")

def save_jsonl(records: List[Dict[str, Any]], path: str):
    if not records or not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ============================================================
# КОНФИГ
# ============================================================

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

DIFFICULTY: Dict[str, Dict[str, Any]] = {
    "1": {"name": "1 — Лёгкий", "question_rate": "low", "resistance": "low", "traps": False},
    "2": {"name": "2 — Нормальный", "question_rate": "medium", "resistance": "medium", "traps": False},
    "3": {"name": "3 — Сложный", "question_rate": "medium", "resistance": "high", "traps": True},
    "4": {"name": "4 — Очень сложный", "question_rate": "high", "resistance": "very_high", "traps": True},
}

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

def _list_keys(d: Dict[str, Any]) -> str:
    return ", ".join(sorted(d.keys()))

def resolve_archetype(archetype_id: str) -> Dict[str, Any]:
    return ARCHETYPES.get(archetype_id, {
        "name": archetype_id,
        "personality": "Неизвестный архетип (fallback). Веди себя нейтрально.",
        "speech_style": "кратко",
        "default_goal": "понять суть",
        "taboos": [],
    })

def resolve_difficulty(level_id: str) -> Dict[str, Any]:
    return DIFFICULTY.get(level_id, {
        "name": level_id, "question_rate": "medium", "resistance": "medium", "traps": False,
    })

def resolve_product(product_id: str) -> Dict[str, Any]:
    return PRODUCTS.get(product_id, {
        "name": product_id, "description": "Неизвестный продукт (fallback).",
        "facts": [], "goal": "", "typical_next_steps": [],
    })

# ============================================================
# PROMPT (FAST-SAFE)
# ============================================================

def _compact_json_list(xs: List[str]) -> str:
    if not xs:
        return "[]"
    return "[" + "; ".join(xs) + "]"

def build_system_prompt(archetype_id: str, difficulty_id: str, product_id: str) -> str:
    a = resolve_archetype(archetype_id)
    d = resolve_difficulty(difficulty_id)
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

    # Усиление правила инициативы: запрет на “интервью менеджера”
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

    return (
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

def _select_history_by_budget(conversation: List[Dict[str, str]], max_turns: int, budget_tokens: int) -> List[Dict[str, str]]:
    if not conversation:
        return []
    tail = conversation[-max_turns:] if max_turns > 0 else conversation[:]
    out: List[Dict[str, str]] = []
    used = 0
    for t in reversed(tail):
        line = f"{t['role']}: {t['text']}"
        cost = _approx_tokens_ru(line)
        if out and used + cost > budget_tokens:
            break
        if not out and cost > budget_tokens:
            out.append(t)
            break
        out.append(t)
        used += cost
    out.reverse()
    return out

def make_prompt(system_prompt: str, conversation: List[Dict[str, str]], max_turns: int, budget_tokens: int) -> str:
    history = _select_history_by_budget(conversation, max_turns=max_turns, budget_tokens=budget_tokens)
    lines = [system_prompt, "\nДиалог:"]
    for turn in history:
        role = "M" if turn["role"] == "manager" else "C"
        lines.append(f"{role}: {turn['text']}")
    lines.append("C:")
    return "\n".join(lines)

# ============================================================
# GUARD / REPEAT / ROLE-SWAP
# ============================================================

META_TRIGGERS = [
    "как клиент", "как менеджер", "инструкция", "правила", "план", "aida", "методич",
    "язык модели", "system", "prompt", "в этом диалоге", "буду отвечать", "рекомендац",
]
ROLE_LEAK_TRIGGERS = ["менеджер:", "оператор:", "manager:", "operator:"]

# Детектор “клиент начал интервьюировать менеджера” (вопросы во 2-м лице)
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

def is_meta_or_role_leak(text: str) -> bool:
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
    t = (text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = WS_RE.sub(" ", t).strip()
    return t

def is_repeat_reply(prev: str, new: str) -> bool:
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

# ============================================================
# FALLBACK
# ============================================================

def _fallback_client_reply(manager_text: str, product_id: str = "free") -> str:
    mt = (manager_text or "").lower()
    if product_id == "free":
        if any(x in mt for x in ["почему", "как", "что", "зачем"]):
            return "Понял. Уточните, пожалуйста, что вы имеете в виду - что именно от меня нужно?"
        return "Понял вас. Можете коротко сказать, в чём суть и что вы предлагаете?"
    return "Понял. Можете коротко пояснить детали?"

# ============================================================
# OLLAMA HTTP + CLI
# ============================================================

def _ollama_http_generate(
    base_url: str,
    model: str,
    prompt: str,
    timeout_s: int,
    options: Dict[str, Any],
) -> Tuple[str, Optional[float], Dict[str, Any]]:
    url = base_url.rstrip("/") + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "options": options or {}}
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    obj = json.loads(raw)
    text = obj.get("response", "") or ""

    eval_ns = obj.get("eval_duration")
    model_s = float(eval_ns) / 1e9 if isinstance(eval_ns, (int, float)) and eval_ns > 0 else None

    extra = {}
    for k in ["load_duration", "prompt_eval_duration", "eval_duration", "total_duration",
              "prompt_eval_count", "eval_count", "done_reason"]:
        if k in obj:
            extra[k] = obj.get(k)

    def ns_to_s(v):
        return float(v) / 1e9 if isinstance(v, (int, float)) else None

    if "load_duration" in extra:
        extra["load_duration_s"] = ns_to_s(extra.get("load_duration"))
    if "prompt_eval_duration" in extra:
        extra["prompt_eval_duration_s"] = ns_to_s(extra.get("prompt_eval_duration"))
    if "eval_duration" in extra:
        extra["eval_duration_s"] = ns_to_s(extra.get("eval_duration"))
    if "total_duration" in extra:
        extra["total_duration_s"] = ns_to_s(extra.get("total_duration"))

    for k in ["load_duration", "prompt_eval_duration", "eval_duration", "total_duration"]:
        extra.pop(k, None)

    return text, model_s, extra

def _ollama_cli_generate(model: str, prompt: str, timeout_s: int) -> str:
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or "ollama CLI error")
    return result.stdout or ""

def _http_get_json(url: str, timeout_s: int) -> dict:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)

def ollama_ping(ollama_url: str, timeout_s: int = 3, debug: bool = False) -> bool:
    url = ollama_url.rstrip("/") + "/api/tags"
    t0 = time.perf_counter()
    try:
        _ = _http_get_json(url, timeout_s=timeout_s)
        if debug:
            print(f"🟢 ping ok ({time.perf_counter() - t0:.2f}s): {url}")
        return True
    except Exception as e:
        if debug:
            print(f"🔴 ping failed ({time.perf_counter() - t0:.2f}s): {e}")
        return False

# ============================================================
# WARM-UP
# ============================================================

def warm_up(
    model: str,
    transport: str,
    ollama_url: str,
    timeout_s: int,
    num_predict: int,
    keep_alive: str,
    num_ctx: Optional[int],
    stop: Optional[List[str]],
    debug: bool,
) -> bool:
    print("🔥 Прогрев модели (warm-up)...")
    t0 = time.perf_counter()

    prompt = "Ответь одним словом: ок.\nC:"
    options: Dict[str, Any] = {
        "num_predict": int(num_predict),
        "temperature": 0.0,
        "top_p": 1.0,
        "repeat_penalty": 1.0,
        "keep_alive": keep_alive,
    }
    if num_ctx is not None:
        options["num_ctx"] = int(num_ctx)
    if stop:
        options["stop"] = stop

    if transport in ("http", "auto"):
        if not ollama_ping(ollama_url, timeout_s=3, debug=debug) and transport == "http":
            print("⚠️ warm-up: Ollama HTTP не отвечает (ping fail).")
            return False
        try:
            _ollama_http_generate(ollama_url, model, prompt, timeout_s, options)
            print(f"✅ Warm-up готово (http) за {time.perf_counter() - t0:.2f}s\n")
            return True
        except Exception as e:
            if transport == "http":
                print(f"⚠️ warm-up failed (http): {e}\n")
                return False
            if debug:
                print(f"⚠️ warm-up http failed, fallback to cli: {e}")

    try:
        _ollama_cli_generate(model, prompt, timeout_s)
        print(f"✅ Warm-up готово (cli) за {time.perf_counter() - t0:.2f}s\n")
        return True
    except Exception as e:
        print(f"⚠️ warm-up failed (cli): {e}\n")
        return False

def warm_up_if_enabled(args):
    if not args.warm_up:
        return
    warm_up(
        model=args.model,
        transport=args.transport,
        ollama_url=args.ollama_url,
        timeout_s=int(args.warm_up_timeout),
        num_predict=int(args.warm_up_tokens),
        keep_alive=args.keep_alive,
        num_ctx=args.num_ctx,
        stop=args.stop,
        debug=args.debug,
    )

# ============================================================
# GENERATE
# ============================================================

def generate_client_reply(
    system_prompt: str,
    conversation: List[Dict[str, str]],
    model: str,
    last_client_reply: str,
    product_id: str,
    timeout_s: int,
    max_turns: int,
    max_sentences: int,
    reply_max_chars: int,
    retries: int,
    debug: bool,
    metrics_sink: Optional[List[Dict[str, Any]]],
    transport: str,
    ollama_url: str,
    context_budget: int,
    num_predict: int,
    temperature: float,
    top_p: float,
    repeat_penalty: float,
    keep_alive: str,
    num_ctx: Optional[int],
    stop: Optional[List[str]],
    meta_guard: bool = True,
) -> Tuple[str, bool, bool, Optional[str]]:
    prompt = make_prompt(system_prompt, conversation, max_turns=max_turns, budget_tokens=context_budget)
    in_tokens = _approx_tokens_ru(prompt)
    manager_last = next((t["text"] for t in reversed(conversation) if t["role"] == "manager"), "")

    def record(err_reason: Optional[str], reply_text: str, lat_total: float, lat_model: Optional[float], extra: Dict[str, Any] = None):
        if metrics_sink is None:
            return
        out_tokens = _approx_tokens_ru(reply_text) if reply_text else 0
        tps = (out_tokens / lat_total) if lat_total > 0 and out_tokens > 0 else None
        rec = {
            "ts": time.time(),
            "model": model,
            "transport": transport,
            "latency_total_s": lat_total,
            "latency_model_s": lat_model,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "tps": tps,
            "err_reason": err_reason,
        }
        if extra:
            rec.update(extra)
        metrics_sink.append(rec)

    options: Dict[str, Any] = {
        "num_predict": int(num_predict),
        "temperature": float(temperature),
        "top_p": float(top_p),
        "repeat_penalty": float(repeat_penalty),
        "keep_alive": keep_alive,
    }
    if num_ctx is not None:
        options["num_ctx"] = int(num_ctx)
    if stop:
        options["stop"] = stop

    def _generate_once() -> Tuple[str, Optional[float], Dict[str, Any], float]:
        t0 = time.perf_counter()
        if transport in ("http", "auto"):
            try:
                raw, model_s, extra = _ollama_http_generate(ollama_url, model, prompt, timeout_s, options)
                lat_total = time.perf_counter() - t0
                return raw, model_s, extra, lat_total
            except Exception:
                if transport == "http":
                    raise
                raw = _ollama_cli_generate(model, prompt, timeout_s)
                lat_total = time.perf_counter() - t0
                return raw, None, {}, lat_total
        else:
            raw = _ollama_cli_generate(model, prompt, timeout_s)
            lat_total = time.perf_counter() - t0
            return raw, None, {}, lat_total

    # Несколько попыток: если модель выдала мусор (не RU/EN) или “перехватила роль”, попробуем ещё раз
    last_err = None
    for attempt in range(max(1, int(retries) + 1)):
        t0 = time.perf_counter()
        try:
            raw, model_s, extra, lat_total = _generate_once()
        except subprocess.TimeoutExpired:
            fb = _fallback_client_reply(manager_last, product_id)
            record("TIMEOUT", fb, time.perf_counter() - t0, None, {"used_fallback": True})
            return fb, False, True, "TIMEOUT"
        except urlerror.URLError as e:
            fb = _fallback_client_reply(manager_last, product_id)
            record("HTTP_ERROR", fb, time.perf_counter() - t0, None, {"used_fallback": True, "http_error": str(e)})
            return fb, False, True, "HTTP_ERROR"
        except Exception as e:
            if debug:
                print("⚠️ ollama error:", str(e))
            fb = _fallback_client_reply(manager_last, product_id)
            record("OLLAMA_ERROR", fb, time.perf_counter() - t0, None, {"used_fallback": True, "error": str(e)})
            return fb, False, True, "OLLAMA_ERROR"

        # 1) Если сырой ответ содержит явно “чужие” символы — ретрай.
        if raw_has_non_ru_en_garbage(raw):
            last_err = "NON_RU_RAW"
            record("NON_RU_RAW", normalize_text_line(raw)[:200], lat_total, model_s,
                   {"attempt": attempt + 1, "will_retry": attempt < retries, **extra})
            continue

        reply = clean_reply(raw, max_sentences=max_sentences, reply_max_chars=reply_max_chars)

        if not reply:
            last_err = "NO_REPLY"
            record("NO_REPLY", "", lat_total, model_s, extra)
            continue

        # 2) Если даже после чистки остался мусор — ретрай.
        if has_non_ru_en_garbage(reply):
            last_err = "NON_RU"
            record("NON_RU", reply, lat_total, model_s,
                   {"attempt": attempt + 1, "will_retry": attempt < retries, **extra})
            continue

        # 3) Мета-утечки / префиксы ролей
        if meta_guard and is_meta_or_role_leak(reply):
            last_err = "META_GUARD"
            record("META_GUARD", reply, lat_total, model_s,
                   {"attempt": attempt + 1, "will_retry": attempt < retries, **extra})
            continue

        # 4) Новая защита: “клиент начал задавать вопросы менеджеру”
        if meta_guard and is_role_swap(reply):
            last_err = "ROLE_SWAP"
            record("ROLE_SWAP", reply, lat_total, model_s,
                   {"attempt": attempt + 1, "will_retry": attempt < retries, **extra})
            continue

        is_rep = is_repeat_reply(last_client_reply, reply)
        record(None, reply, lat_total, model_s, {"is_repeat": is_rep, "attempt": attempt + 1, **extra})
        return reply, is_rep, True, None

    # Если все попытки не дали нормальный текст — тогда уже фолбэк
    fb = _fallback_client_reply(manager_last, product_id)
    record(last_err or "FALLBACK", fb, 0.0001, None, {"used_fallback": True})
    return fb, False, True, last_err or "FALLBACK"

# ============================================================
# LIVE
# ============================================================

def run_live(
    model: str,
    archetype_id: str,
    difficulty_id: str,
    product_id: str,
    timeout_s: int,
    max_turns: int,
    max_sentences: int,
    reply_max_chars: int,
    retries: int,
    debug: bool,
    turn_limit: int,
    metrics_path: Optional[str],
    transport: str,
    ollama_url: str,
    context_budget: int,
    num_predict: int,
    temperature: float,
    top_p: float,
    repeat_penalty: float,
    keep_alive: str,
    num_ctx: Optional[int],
    stop: Optional[List[str]],
    meta_guard: bool,
):
    conversation: List[Dict[str, str]] = []
    last_client_reply = ""
    turn_counter = 0
    metrics: List[Dict[str, Any]] = []

    system_prompt = build_system_prompt(archetype_id, difficulty_id, product_id)
    print("Введите 'exit'/'выход' (или 'done'/'конец') для завершения.\n")

    try:
        while True:
            manager_raw = input("Оператор: ")
            manager = clean_manager_input(manager_raw)

            if manager.lower() in ("exit", "выход", "done", "конец"):
                print("Диалог завершён.")
                break
            if not manager:
                continue

            turn_counter += 1
            conversation.append({"role": "manager", "text": manager})

            reply, is_repeat, had_reply, err = generate_client_reply(
                system_prompt=system_prompt,
                conversation=conversation,
                model=model,
                last_client_reply=last_client_reply,
                product_id=product_id,
                timeout_s=timeout_s,
                max_turns=max_turns,
                max_sentences=max_sentences,
                reply_max_chars=reply_max_chars,
                retries=retries,
                debug=debug,
                metrics_sink=metrics,
                transport=transport,
                ollama_url=ollama_url,
                context_budget=context_budget,
                num_predict=num_predict,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                keep_alive=keep_alive,
                num_ctx=num_ctx,
                stop=stop,
                meta_guard=meta_guard,
            )

            if not had_reply:
                print("⚠️ Пустой ответ модели, попробуйте ещё раз.\n")
                continue

            if err:
                print(f"⚠️ {err}: дал защиту/ретраи/фолбэк.")

            if is_repeat:
                print("⚠️ Клиент повторяется. Продвинься по теме.\n")

            print(f"Клиент: {reply}")
            print("-" * 60)
            print()
            conversation.append({"role": "client", "text": reply})
            last_client_reply = reply

            if turn_counter >= turn_limit:
                print("⚠️ Достигнут лимит по количеству ходов. Завершаю.")
                break

    except KeyboardInterrupt:
        print("\n⛔ Остановлено (Ctrl-C).")

    finally:
        print_metrics_summary(metrics)
        if metrics_path:
            save_jsonl(metrics, metrics_path)

    return conversation

# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Trainer (fast-safe)")
    parser.add_argument("--model", default="qwen2.5:14b-instruct-q4_K_M")
    parser.add_argument("--mode", choices=["live"], default="live")

    parser.add_argument("--product", default="free", help=f"one of [{_list_keys(PRODUCTS)}]")
    parser.add_argument("--archetype", default="novice", help=f"one of [{_list_keys(ARCHETYPES)}]")
    parser.add_argument("--difficulty", default="1", help=f"one of [{_list_keys(DIFFICULTY)}]")

    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--context-budget", type=int, default=650)

    # Разрешаем до 5 предложений (по смыслу), чтобы мысль не обрубалась.
    parser.add_argument("--max-sentences", type=int, default=5)

    # чтобы мысль не обрезалась криво
    parser.add_argument("--reply-max-chars", type=int, default=320)
    parser.add_argument("--retries", type=int, default=2)

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--turn-limit", type=int, default=30)

    parser.add_argument("--num-predict", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--repeat-penalty", type=float, default=1.1)

    parser.add_argument("--transport", choices=["auto", "http", "cli"], default="http")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--no-meta-guard", action="store_true")

    # ускорители ollama
    parser.add_argument("--keep-alive", default="15m")
    parser.add_argument("--num-ctx", type=int, default=1024)

    # stop-триггеры (не добавляем "\nC:" чтобы не рубило ответ)
    parser.add_argument("--stop", nargs="*", default=[
        "\nM:", "\nДиалог:", "\nОператор:", "\nМенеджер:", "\nКлиент:",
        "\nManager:", "\nOperator:", "\nClient:"
    ])

    # warm-up
    parser.add_argument("--warm-up", action="store_true")
    parser.add_argument("--warm-up-timeout", type=int, default=120)
    parser.add_argument("--warm-up-tokens", type=int, default=2)

    parser.add_argument("--no-metrics", action="store_true")
    args = parser.parse_args()

    print("🎙️ Trainer (fast single file)")
    print(f"🧠 model: {args.model}")
    print(f"👤 archetype: {args.archetype}")
    print(f"🎚 difficulty: {args.difficulty}")
    print(f"🧩 product: {args.product} ({resolve_product(args.product).get('name')})")
    print(f"⏱ timeout={args.timeout}s | max_turns={args.max_turns} | context_budget={args.context_budget} | num_ctx={args.num_ctx}")
    print(f"🧪 gen: num_predict={args.num_predict} | temp={args.temperature} | top_p={args.top_p} | repeat_penalty={args.repeat_penalty}")
    print(f"🚚 transport={args.transport} | ollama_url={args.ollama_url} | keep_alive={args.keep_alive}")
    print(f"🛡 meta_guard={'OFF' if args.no_meta_guard else 'ON'}")
    print(f"🧷 stop={args.stop}")
    print(f"✂️ reply_max_chars={args.reply_max_chars} | retries={args.retries} | max_sentences={args.max_sentences}")
    print(f"🔥 warm_up={'ON' if args.warm_up else 'OFF'} (timeout={args.warm_up_timeout}s, tokens={args.warm_up_tokens})")
    print(f"📊 metrics={'OFF' if args.no_metrics else 'ON'}")
    if args.debug:
        print("🛠 debug=ON")
    print()

    warm_up_if_enabled(args)

    ts = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)

    metrics_path = None
    if not args.no_metrics:
        metrics_path = f"logs/metrics_{args.product}_{args.archetype}_L{args.difficulty}_{ts}.jsonl"

    conv = run_live(
        model=args.model,
        archetype_id=args.archetype,
        difficulty_id=args.difficulty,
        product_id=args.product,
        timeout_s=args.timeout,
        max_turns=args.max_turns,
        max_sentences=args.max_sentences,
        reply_max_chars=args.reply_max_chars,
        retries=args.retries,
        debug=args.debug,
        turn_limit=args.turn_limit,
        metrics_path=metrics_path,
        transport=args.transport,
        ollama_url=args.ollama_url,
        context_budget=args.context_budget,
        num_predict=args.num_predict,
        temperature=args.temperature,
        top_p=args.top_p,
        repeat_penalty=args.repeat_penalty,
        keep_alive=args.keep_alive,
        num_ctx=args.num_ctx,
        stop=args.stop,
        meta_guard=(not args.no_meta_guard),
    )

    dialog_path = f"logs/dialog_{args.product}_{args.archetype}_L{args.difficulty}_{ts}.json"
    payload = {
        "ts": ts,
        "model": args.model,
        "product": args.product,
        "archetype": args.archetype,
        "difficulty": args.difficulty,
        "turns": conv,
    }
    with open(dialog_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"💾 История диалога сохранена: {dialog_path}")
    if metrics_path:
        print(f"📈 Метрики сохранены: {metrics_path}")

if __name__ == "__main__":
    main()