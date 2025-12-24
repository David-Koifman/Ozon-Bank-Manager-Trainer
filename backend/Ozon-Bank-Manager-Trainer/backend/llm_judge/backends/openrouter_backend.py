import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class OpenRouterBackend:
    def __init__(
        self,
        model_name: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ):
        self.model_name = model_name or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        self.timeout_sec = float(timeout_sec or os.getenv("JUDGE_TIMEOUT_SEC", "45"))

    def generate(self, prompt: str, max_retries: int = 2) -> str:
        # Fail fast with a clear message (instead of sending empty key and getting 401)
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set (empty). Put it into backend/.env or export it before запуском.")

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional but nice-to-have (не обязателен для 200; 401 не из-за них)
            "X-Title": "Operator Voice Trainer",
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a strict evaluator. Return only the final answer."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                return (data["choices"][0]["message"]["content"] or "").strip()
            except Exception as e:
                last_err = e
                logger.warning("OpenRouter error attempt %s/%s: %s", attempt, max_retries, e)
        raise RuntimeError(f"OpenRouter failed after {max_retries} attempts: {last_err}")

