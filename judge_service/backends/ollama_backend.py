import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import ollama, but handle gracefully if not available
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("ollama package not installed. Install with: pip install ollama")


class OllamaBackend:
    """
    Адаптер для взаимодействия с Ollama (локальный LLM).
    Поддерживает генерацию текста через Qwen2 или другие модели.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        if not OLLAMA_AVAILABLE:
            raise ImportError(
                "ollama package not installed. Install with: pip install ollama"
            )
        
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "qwen2:7b-instruct-q4_K_M")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        # Configure ollama client with custom base URL
        # The ollama library uses OLLAMA_HOST environment variable
        # Format: host:port (without http://)
        if self.base_url.startswith("http://"):
            host_port = self.base_url.replace("http://", "")
        elif self.base_url.startswith("https://"):
            host_port = self.base_url.replace("https://", "")
        else:
            host_port = self.base_url
        
        # Set environment variable for ollama client
        os.environ["OLLAMA_HOST"] = host_port
        
        logger.info(f"Инициализация OllamaBackend с моделью: {self.model_name}, base_url: {self.base_url}")

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        """
        Генерирует текст с использованием LLM через Ollama.

        Args:
            prompt: полный промпт для модели
            max_retries: количество попыток при ошибке

        Returns:
            Сырой текстовый ответ от модели

        Raises:
            RuntimeError: если все попытки завершились ошибкой
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"Попытка {attempt}: отправка промпта в Ollama")
                response = ollama.generate(
                    model=self.model_name,
                    prompt=prompt,
                    options={
                        "temperature": 0.2,
                        "num_predict": 512,
                        "top_p": 0.95,
                        "repeat_penalty": 1.1
                    }
                )
                raw_text = response["response"].strip()
                logger.debug(f"Получен ответ (длина: {len(raw_text)} символов)")
                return raw_text

            except Exception as e:
                logger.warning(f"Ошибка Ollama на попытке {attempt}: {e}")
                if attempt == max_retries:
                    raise RuntimeError(f"Ollama не ответил после {max_retries} попыток") from e
                # пауза между попытками (опционально)
                import time
                time.sleep(1)