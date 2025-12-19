import json
import os
from unittest.mock import patch, MagicMock
import pytest

# Добавляем корень проекта в PYTHONPATH для импортов
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.llm_judge.judge import LLMJudge
from src.llm_judge.parser import parse_llm_response


# ============ Тесты для parser.py ============

def test_parse_valid_json():
    raw = '{"scores": {"greeting_correct": 1}, "total_score": 1, "critical_errors": [], "feedback_positive": [], "feedback_improvement": [], "recommendations": [], "timecodes": []}'
    result = parse_llm_response(raw)
    assert result["scores"]["greeting_correct"] == 1
    assert result["total_score"] == 1

def test_parse_json_in_backticks():
    raw = '```json\n{"scores": {"greeting_correct": 1}, "total_score": 1, "critical_errors": [], "feedback_positive": [], "feedback_improvement": [], "recommendations": [], "timecodes": []}\n```'
    result = parse_llm_response(raw)
    assert result["scores"]["greeting_correct"] == 1

def test_parse_with_leading_text():
    raw = 'Вот оценка:\n{"scores": {"greeting_correct": 0}, "total_score": 0, "critical_errors": ["Нет приветствия"], "feedback_positive": [], "feedback_improvement": [], "recommendations": [], "timecodes": []}'
    result = parse_llm_response(raw)
    assert result["scores"]["greeting_correct"] == 0
    assert "Нет приветствия" in result["critical_errors"]

def test_parse_invalid_json_returns_error():
    raw = 'Это не JSON'
    result = parse_llm_response(raw)
    assert "error" in result
    assert result["total_score"] == 0


# ============ Тесты для judge.py ============

@pytest.fixture
def sample_transcript():
    return [
        {"role": "manager", "text": "Добрый день, это Анна из Ozon, могу услышать Дмитрия Сергеевича?"},
        {"role": "client", "text": "Да, слушаю."},
        {"role": "manager", "text": "Звоню, чтобы поздравить вас с регистрацией. Уже есть счёт в другом банке?"},
        {"role": "client", "text": "Да, в Тинькофф."},
        {"role": "manager", "text": "Сколько платите за обслуживание?"},
    ]

@patch('src.llm_judge.backends.ollama_backend.OllamaBackend.generate')
def test_judge_evaluate_success(mock_generate, sample_transcript):
    # Подменяем ответ LLM
    mock_generate.return_value = '''
    {
        "scores": {
            "greeting_correct": 1,
            "congratulation_given": 1,
            "compliance_rko_free": 0,
            "compliance_terms_clear": 0,
            "qualification_before_offer": 1,
            "objection_handling_existing": 1,
            "objection_handling_second": 0,
            "closing_success": 0,
            "politeness": 2
        },
        "total_score": 6,
        "critical_errors": [],
        "feedback_positive": ["Отличное приветствие"],
        "feedback_improvement": ["Не упомянули бесплатный счёт"],
        "recommendations": ["Скажите: «Расчетный счет от Озон Банка — бесплатный для новых продавцов»"],
        "timecodes": []
    }
    '''
    
    judge = LLMJudge(model_name="mock-model")
    result = judge.evaluate(sample_transcript, scenario_id="ozon_rko_new_seller_v1")
    
    assert result["total_score"] == 6
    assert result["scenario_id"] == "ozon_rko_new_seller_v1"
    assert "Отличное приветствие" in result["feedback_positive"]

@patch('src.llm_judge.backends.ollama_backend.OllamaBackend.generate')
def test_judge_handles_llm_error(mock_generate, sample_transcript):
    mock_generate.side_effect = RuntimeError("Ollama is down")
    
    judge = LLMJudge(model_name="mock-model")
    result = judge.evaluate(sample_transcript, scenario_id="ozon_rko_new_seller_v1")
    
    assert "error" in result
    assert result["total_score"] == 0


# ============ Интеграционный тест (опционально, с реальным LLM) ============

@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="Integration tests disabled by default")
def test_integration_with_real_ollama(sample_transcript):
    """Запускать только вручную с LLM"""
    judge = LLMJudge(model_name="qwen2:7b-instruct-q4_K_M")
    result = judge.evaluate(sample_transcript)
    assert isinstance(result, dict)
    assert "scores" in result
    print("Интеграционный тест пройден:", result["total_score"])