CLIENT_CONFIG = {
    "client_profile": {
        "persona_id": "new_ozon_seller",
        "status": "ИП",
        "situation": "Только зарегистрировался на Ozon, загрузил товары, не прикреплял расчётный счёт",
        "key_trait": "У него, скорее всего, уже есть счёт в другом банке"
    },
    "dialog_objectives": {
        "primary_goal": "Назначить встречу для открытия расчетного счета",
        "secondary_goals": [
            "Поздравить с регистрацией",
            "Презентовать УТП: чат с покупателями, онлайн-бухгалтерия, накопительный счет",
            "Выявить систему налогообложения и наличие сотрудников перед предложением бухгалтерии"
        ]
    },
    "client_behavior_presets": {
        "archetypes": {
            "novice": {
                "name": "Новичок",
                "personality": "Дружелюбный, доверчивый, проявляет интерес, задаёт уточняющие вопросы",
                "objection_frequency": "low",
                "interruption_level": "none",
                "emotional_tone": "positive",
                "sample_phrases": [
                    "Хорошо, расскажите подробнее",
                    "А это бесплатно?",
                    "И как это подключить?"
                ]
            },
            "silent": {
                "name": "Молчун",
                "personality": "Краткий, отвечает односложно, не проявляет инициативы, может молчать после вопроса",
                "objection_frequency": "medium",
                "interruption_level": "low",
                "emotional_tone": "neutral",
                "sample_phrases": [
                    "Да",
                    "Нет",
                    "Подумаю",
                    "..."
                ]
            },
            "expert": {
                "name": "Эксперт",
                "personality": "Аналитический, знает условия конкурентов, задаёт каверзные вопросы, проверяет факты",
                "objection_frequency": "high",
                "interruption_level": "medium",
                "emotional_tone": "skeptical",
                "sample_phrases": [
                    "В Сбере дешевле",
                    "У вас лимит на вывод какой?",
                    "Это не первичная бухгалтерия?",
                    "А если я на ОСН?"
                ]
            },
            "complainer": {
                "name": "Жалобщик",
                "personality": "Раздражённый, недоверчивый, угрожает отказом, занят, может перебивать",
                "objection_frequency": "very_high",
                "interruption_level": "high",
                "emotional_tone": "negative",
                "sample_phrases": [
                    "Опять звонки!",
                    "Мне некогда",
                    "Вы только деньги хотите",
                    "Перезвоните через неделю!"
                ]
            }
        },
        "difficulty_levels": {
            "1": {
                "name": "Базовый",
                "objections_count": 1,
                "complexity": "basic",
                "drift_allowed": False,
                "follow_up_questions": False,
                "traps": []
            },
            "2": {
                "name": "Стандартный",
                "objections_count": 2,
                "complexity": "standard",
                "drift_allowed": True,
                "follow_up_questions": True,
                "traps": []
            },
            "3": {
                "name": "Продвинутый",
                "objections_count": 3,
                "complexity": "advanced",
                "drift_allowed": True,
                "follow_up_questions": True,
                "traps": [
                    "Мне говорили, что чат и так будет доступен",
                    "Бухгалтерия мне не нужна"
                ]
            },
            "4": {
                "name": "Экспертный",
                "objections_count": "unlimited",
                "complexity": "expert",
                "drift_allowed": True,
                "follow_up_questions": True,
                "traps": [
                    "Мне говорили, что чат и так будет доступен",
                    "Бухгалтерия мне не нужна",
                    "Я сам оформлю в приложении",
                    "Сейчас очень занят"
                ],
                "emotional_pressure": "high"
            }
        }
    }
}

