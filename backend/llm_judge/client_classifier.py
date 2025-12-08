import re
from typing import List, Dict, Any


class ClientClassifier:
    """
    Очень простой эвристический классификатор профиля клиента по тексту его реплик.
    Выделяем:
    - type: IP / OOO
    - tax_system: OSNO / USN / USN_D / USN_DR / UNKNOWN
    - has_employees: bool
    - has_other_account: bool
    - agrees_quickly: bool
    """

    def classify(self, transcript: List[Dict[str, str]]) -> Dict[str, Any]:
        client_replicas = [t.get("text", "") for t in transcript if t.get("role") == "client"]
        client_text = " ".join(client_replicas).lower()

        client_type = self._detect_type(client_text)
        tax_system = self._detect_tax_system(client_text)
        has_employees = self._detect_employees(client_text)
        has_other_account = self._detect_other_account(client_text)
        agrees_quickly = self._detect_agrees_quickly(transcript)

        return {
            # если тип не распознан, считаем по умолчанию ИП — это чаще всего твой кейс
            "type": client_type or "IP",
            "tax_system": tax_system,
            "has_employees": has_employees,
            "has_other_account": has_other_account,
            "agrees_quickly": agrees_quickly,
        }

    # ======== детект типа клиента (ИП / ООО) ========

    def _detect_type(self, text: str) -> str:
        if "ип " in text or " ип" in text or "индивидуальный предпринимател" in text:
            return "IP"
        if "ооо" in text or "общество с ограниченной ответственностью" in text:
            return "OOO"
        return ""

    # ======== детект системы налогообложения ========

    def _detect_tax_system(self, text: str) -> str:
        if "осно" in text or "общая система налогообложения" in text:
            return "OSNO"

        if "усн" in text or "упрощен" in text:
            # попытка различить подвиды
            if "доходы минус расходы" in text:
                return "USN_DR"
            if "доходы" in text:
                return "USN_D"
            return "USN"

        return "UNKNOWN"

    # ======== детект сотрудников (в т.ч. "сотрудников пока нет") ========

    def _detect_employees(self, text: str) -> bool:
        """
        Логика:
        1) если явно сказано, что сотрудников нет — возвращаем False;
        2) если явно сказано, что сотрудники есть — True;
        3) иначе по умолчанию считаем, что сотрудников нет (False).
        """
        # отрицательные паттерны: "сотрудников пока нет", "без сотрудников", "нет сотрудников" и т.п.
        negative_patterns = [
            r"сотрудник(ов)?\s+нет",
            r"сотрудников\s+пока\s+нет",
            r"без\s+сотрудник",
            r"без\s+персонал",
            r"без\s+штата",
            r"я\s+один\s+работаю",
            r"работаю\s+один",
            r"работаю\s+сам",
        ]

        for pat in negative_patterns:
            if re.search(pat, text):
                return False

        # положительные паттерны: "есть сотрудники", "у меня сотрудники", "10 сотрудников" и т.п.
        positive_patterns = [
            r"есть\s+сотрудник",
            r"есть\s+персонал",
            r"у\s+меня\s+сотрудник",
            r"\d+\s+сотрудник",
            r"коллектив\s+из\s+\d+",
        ]

        for pat in positive_patterns:
            if re.search(pat, text):
                return True

        # по умолчанию считаем, что сотрудников нет
        return False

    # ======== детект наличия другого счёта ========

    def _detect_other_account(self, text: str) -> bool:
        patterns = [
            r"у\s+меня\s+уже\s+есть\s+сч[её]т",
            r"уже\s+есть\s+сч[её]т",
            r"есть\s+сч[её]т\s+в\s+другом\s+банке",
            r"сч[её]т\s+в\s+другом\s+банке",
        ]
        return any(re.search(p, text) for p in patterns)

    # ======== детект "быстро соглашается" ========

    def _detect_agrees_quickly(self, transcript: List[Dict[str, str]]) -> bool:
        """
        Смотрим первые 2–3 реплики клиента.
        Если там сразу явное согласие — считаем, что клиент "быстро согласился".
        """
        first_client_replicas = [
            t.get("text", "").lower()
            for t in transcript
            if t.get("role") == "client"
        ][:3]

        agree_phrases = [
            "да, давайте",
            "давайте",
            "да, конечно",
            "да, удобно",
            "готов",
            "можно прямо сейчас",
            "да, подойдёт",
        ]

        return any(
            any(p in replica for p in agree_phrases)
            for replica in first_client_replicas
        )

