import os
import json
import time
import random
from pathlib import Path
from jinja2 import Template
import ollama

MODEL_NAME = "qwen2:7b-instruct-q4_K_M"
NUM_DIALOGS_PER_COMBO = 2  
OUTPUT_PATH = Path("data/synthetic/ozon_dialogs.jsonl")
SCENARIOS_DIR = Path("scenarios")
PROMPTS_DIR = Path("src/prompts/dialog_agent")

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_prompt(scenario_id):
    prompt_path = PROMPTS_DIR / f"{scenario_id}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Промпт не найден: {prompt_path}")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

def render_prompt(template_str, context):
    return Template(template_str).render(**context)

def generate_client_response(client_prompt, history):
    full_prompt = client_prompt + "\n\nИстория диалога:\n" + "\n".join(
        f"{turn['role'].capitalize()}: {turn['text']}" for turn in history
    ) + "\nКлиент:"
    
    response = ollama.generate(
        model=MODEL_NAME,
        prompt=full_prompt,
        options={"temperature": 0.7, "num_predict": 100}
    )
    return response["response"].strip()

def generate_manager_response(manager_prompt, history):
    full_prompt = manager_prompt + "\n\nИстория диалога:\n" + "\n".join(
        f"{turn['role'].capitalize()}: {turn['text']}" for turn in history
    ) + "\nМенеджер:"
    
    response = ollama.generate(
        model=MODEL_NAME,
        prompt=full_prompt,
        options={"temperature": 0.3, "num_predict": 120}
    )
    return response["response"].strip()

def main():
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out_f:
        pass

    dialog_count = 0
    for scenario_path in SCENARIOS_DIR.rglob("*.json"):
        print(f"\nОбрабатываю сценарий: {scenario_path.name}")
        scenario_config = load_json(scenario_path)
        scenario_id = scenario_config["scenario_id"].replace("_v1", "")
        try:
            client_prompt_template = load_prompt(scenario_id)
        except FileNotFoundError:
            print(f"  Пропущен: нет промпта")
            continue

        manager_prompt_template = """
Ты — эталонный менеджер Ozon. Следуй сценарию идеально:
- Не используй слово "банк"
- Всегда поздравляй с регистрацией
- Задавай квалификационные вопросы перед предложением услуг
- Завершай вежливо
Отвечай кратко, по делу.
"""

        presets = scenario_config.get("client_behavior_presets", {})
        archetypes = presets.get("archetypes", {})
        levels = presets.get("difficulty_levels", {})

        if not archetypes or not levels:
            if "aggressor" in archetypes:
                archetypes = {"aggressor": archetypes["aggressor"]}
            else:
                archetypes = {"default": {}}
            levels = {"1": levels.get("1", {})} if "1" in levels else {"1": {}}

        for arch_name, arch_data in archetypes.items():
            for level_key, level_data in levels.items():
                for i in range(NUM_DIALOGS_PER_COMBO):
                    print(f"  Генерация: {arch_name} / уровень {level_key} / {i+1}")
                    turns = []

                    context = {
                        "client": {"name": random.choice(["Дмитрий", "Анна", "Сергей", "Ольга"])},
                        "preset": {
                            "archetype": {"name": arch_name, **arch_data},
                            "difficulty": {"name": level_data.get("name", level_key), **level_data}
                        }
                    }

                    client_prompt = render_prompt(client_prompt_template, context)
                    manager_prompt = manager_prompt_template

                    for turn in range(12):
                        if turn == 0:
                            manager_text = generate_manager_response(manager_prompt, [])
                            if not manager_text:
                                break
                            turns.append({"role": "manager", "text": manager_text})
                        else:
                            client_text = generate_client_response(client_prompt, turns)
                            if not client_text or "до свидания" in client_text.lower():
                                turns.append({"role": "client", "text": client_text})
                                break
                            turns.append({"role": "client", "text": client_text})

                            manager_text = generate_manager_response(manager_prompt, turns)
                            if not manager_text:
                                break
                            turns.append({"role": "manager", "text": manager_text})

                            if any(phrase in manager_text.lower() for phrase in ["хорошего дня", "до встречи", "спасибо за время"]):
                                break

                    if len(turns) < 3:
                        continue

                    record = {
                        "dialog_id": f"{scenario_id}_{arch_name}_L{level_key}_{str(dialog_count).zfill(4)}",
                        "scenario_id": scenario_config["scenario_id"],
                        "archetype": arch_name,
                        "difficulty_level": int(level_key),
                        "turns": turns,
                        "annotations": {},
                        "metadata": {"generated_by": MODEL_NAME, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
                    }

                    with open(OUTPUT_PATH, "a", encoding="utf-8") as out_f:
                        out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    dialog_count += 1

                    time.sleep(1.5)

    print(f"\n✅ Готово! Сгенерировано {dialog_count} диалогов в {OUTPUT_PATH}")

if __name__ == "__main__":
    main()