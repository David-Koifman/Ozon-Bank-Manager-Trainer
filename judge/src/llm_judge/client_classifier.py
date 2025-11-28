import re
from typing import Dict, Any

class ClientClassifier:
    """
    Извлекает профиль клиента из транскрипции менеджера и клиента.
    """
    def __init__(self):
        # Паттерны для определения типа клиента
        self.ip_patterns = [
            r"\bип\b",
            r"\bиндивидуальный предприниматель\b",
            r"\bиндивидуальный бизнес\b"
        ]
        self.oao_patterns = [
            r"\bооо\b",
            r"\bпао\b",
            r"\bао\b",
            r"\bюрлицо\b",
            r"\bюридическое лицо\b"
        ]
        self.tax_patterns = {
            "USN_income": [
                r"\bуСН доходы\b",
                r"\bдоходы без расходов\b"
            ],
            "USN_income_expense": [
                r"\bуСН доходы минус расходы\b",
                r"\bдоходы минус расходы\b"
            ],
            "OSNO": [
                r"\bОСНО\b",
                r"\bобщая система налогообложения\b"
            ]
        }
        self.employees_patterns = [
            r"\bсотрудник",
            r"\bработник",
            r"\bофициально трудоустроен",
            r"\bштат"
        ]

    def classify(self, transcript: list) -> Dict[str, Any]:
        """
        Анализирует транскрипцию и возвращает профиль клиента.
        
        Args:
            transcript: список реплик [{"role": "manager", "text": "..."}, ...]
        
        Returns:
            Словарь с профилем: {"type": "IP", "tax_system": "USN_income", "has_employees": False}
        """
        # Объединяем все реплики в один текст
        full_text = " ".join([turn["text"].lower() for turn in transcript])

        # Определяем тип клиента
        client_type = "IP"  # по умолчанию
        if any(re.search(pattern, full_text) for pattern in self.oao_patterns):
            client_type = "OAO"
        elif any(re.search(pattern, full_text) for pattern in self.ip_patterns):
            client_type = "IP"

        # Определяем систему налогообложения
        tax_system = "OSNO"  # по умолчанию
        for tax, patterns in self.tax_patterns.items():
            if any(re.search(pattern, full_text) for pattern in patterns):
                tax_system = tax
                break

        # Определяем наличие сотрудников
        has_employees = any(re.search(pattern, full_text) for pattern in self.employees_patterns)

        # Определяем быстрое согласие (если менеджер сразу назначил встречу)
        quick_agreement = False
        for i, turn in enumerate(transcript):
            if turn["role"] == "manager" and "назначим встречу" in turn["text"].lower():
                # Если это произошло в первые 3 реплики — согласие быстрое
                if i < 3:
                    quick_agreement = True
                    break

        return {
            "type": client_type,
            "tax_system": tax_system,
            "has_employees": has_employees,
            "agrees_quickly": quick_agreement
        }