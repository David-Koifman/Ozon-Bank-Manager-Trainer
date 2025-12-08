import logging
import ollama

logger = logging.getLogger(__name__)


class OllamaBackend:
    """
    Адаптер для взаимодействия с Ollama (локальный LLM).
    Поддерживает генерацию текста через Qwen2 или другие модели.
    """

    def __init__(self, model_name: str = "qwen2:7b-instruct-q4_K_M"):
        self.model_name = model_name
        logger.info(f"Инициализация OllamaBackend с моделью: {self.model_name}")

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