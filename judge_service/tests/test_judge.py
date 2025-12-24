import os
import sys
from unittest.mock import patch
import pytest

# --- делаем так, чтобы "import llm_judge" работал из любой рабочей директории ---
THIS_DIR = os.path.dirname(__file__)
BACKEND_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))  # .../backend (где лежит папка llm_judge)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from llm_judge.judge import LLMJudge
from llm_judge.parser import parse_llm_response


# ============ Тесты для parser.py ============

def test_parse_valid_json():
    raw = '{"scores": {"greeting_correct": true}, "total_score": 1, "critical_errors": [], "feedback_positive": [], "feedback_improvement": [], "recommendations": [], "timecodes": []}'
    result = parse_llm_response(raw)
    assert result["scores"]["greeting_correct"] is True
    assert result["total_score"] == 1

def test_parse_json_in_backticks():
    raw = '```json\n{"scores": {"greeting_correct": true}, "total_score": 1, "critical_errors": [], "feedback_positive": [], "feedback_improvement": [], "recommendations": [], "timecodes": []}\n```'
    result = parse_llm_response(raw)
    assert result["scores"]["greeting_correct"] is True

def test_parse_with_leading_text():
    raw = 'Вот оценка:\n{"scores": {"greeting_correct": false}, "total_score": 0, "critical_errors": ["Нет приветствия"], "feedback_positive": [], "feedback_improvement": [], "recommendations": [], "timecodes": []}'
    result = parse_llm_response(raw)
    assert result["scores"]["greeting_correct"] is False
    assert "Нет приветствия" in result["critical_errors"]

def test_parse_invalid_json_returns_error():
    raw = "Это не JSON"
    result = parse_llm_response(raw)
    assert "error" in result
    assert result["total_score"] == 0


# ============ Тесты для judge.py ============

@pytest.fixture
def sample_transcript():
    return [
        {"role": "manager", "text": "Добрый день, это Анна из Ozon, могу услышать Дмитрия Сергеевича?"},
        {"role": "client", "text": "Да, слушаю."},
        {"role": "manager", "text": "Поздравляю с регистрацией на Ozon!"},
        {"role": "client", "text": "Спасибо."},
        {"role": "manager", "text": "Расчетный счет от Озон Банка бесплатный для новых продавцов."},
        {"role": "manager", "text": "Для открытия счета ИП нужен только оригинал паспорта РФ."},
        {"role": "manager", "text": "Правильно ли вы поняли цель встречи и условия?"},
    ]


@patch("llm_judge.backends.ollama_backend.OllamaBackend.generate")
def test_judge_evaluate_success(mock_generate, sample_transcript):
    mock_generate.return_value = """
    {
      "scores": {
        "greeting_correct": true,
        "congratulation_given": true,
        "compliance_free_account_ip": true,
        "compliance_account_docs_ip": true,
        "compliance_buh_free_usn_income": false,
        "verification_agreement_correctly_understood": true,
        "closing_success": false,
        "politeness": 10
      },
      "total_score": 0,
      "critical_errors": [],
      "feedback_positive": ["Отличное приветствие"],
      "feedback_improvement": [],
      "recommendations": [],
      "timecodes": []
    }
    """

    judge = LLMJudge(model_name="mock-model")
    result = judge.evaluate(sample_transcript, scenario_id="novice_ip_no_account_easy")

    assert result["scenario_id"] == "novice_ip_no_account_easy"
    assert result["scores"]["greeting_correct"] is True
    assert "Отличное приветствие" in result["feedback_positive"]

    # ожидаем пересчёт на бэке:
    # greeting(1) + congrat(1) + free_account(2) + docs(2) + verification(2) + politeness(2) = 10
    assert result["total_score"] == 10.0


@patch("llm_judge.backends.ollama_backend.OllamaBackend.generate")
def test_judge_handles_llm_error(mock_generate, sample_transcript):
    mock_generate.side_effect = RuntimeError("Ollama is down")

    judge = LLMJudge(model_name="mock-model")
    result = judge.evaluate(sample_transcript, scenario_id="novice_ip_no_account_easy")

    assert "error" in result
    assert result["total_score"] == 0


@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="Integration tests disabled by default")
def test_integration_with_real_ollama(sample_transcript):
    judge = LLMJudge(model_name="qwen2:7b-instruct-q4_K_M")
    result = judge.evaluate(sample_transcript, scenario_id="novice_ip_no_account_easy")
    assert isinstance(result, dict)
    assert "scores" in result

