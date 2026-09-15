import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from agent.router import classify_question, extract_merchant_id
from agent.analyst import ask, SUPPORTED_EXAMPLE_QUESTIONS
from agent import llm_provider


def test_all_documented_example_questions_are_classified():
    for q in SUPPORTED_EXAMPLE_QUESTIONS:
        intent = classify_question(q)
        assert intent is not None, f"Failed to classify documented example question: {q}"


def test_unsupported_question_returns_none_intent():
    assert classify_question("What is the meaning of life?") is None
    assert classify_question("asdkjfh aslkdjf laksjdf") is None


def test_extract_merchant_id_formats():
    assert extract_merchant_id("Why is MCH1234 high risk?") == "MCH1234"
    assert extract_merchant_id("why is mch-01234 risky") == "MCH1234"
    assert extract_merchant_id("no merchant mentioned here") is None


@pytest.mark.parametrize("question", SUPPORTED_EXAMPLE_QUESTIONS)
def test_ask_every_example_question_returns_non_empty_answer(question):
    result = ask(question, use_llm_polish=False)
    assert result["answer"]
    assert len(result["answer"]) > 10
    assert result["intent"] is not None


def test_ask_unsupported_question_says_cannot_answer_reliably():
    result = ask("Predict next year's GDP growth", use_llm_polish=False)
    assert result["intent"] is None
    assert "cannot answer this reliably" in result["answer"].lower()


def test_ask_never_fabricates_when_merchant_not_found():
    result = ask("Why is MCH99999999 considered high risk?", use_llm_polish=False)
    assert "cannot answer this reliably" in result["answer"].lower() or "doesn't appear" in result["answer"].lower()


def test_bonus_question_answer_matches_deterministic_function_directly():
    from src.analytics.merchant_category import bonus_question_highest_chargeback_ratio_category
    direct = bonus_question_highest_chargeback_ratio_category()
    result = ask("Which merchant category has the highest chargeback-to-transaction ratio this quarter?", use_llm_polish=False)
    assert direct["answer_merchant_category"] in result["answer"]


def test_llm_provider_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_provider.is_available() is False


def test_llm_provider_rephrase_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    original = "This is the deterministic answer with 42 in it."
    result = llm_provider.rephrase("some question", original)
    assert result == original  # must be unchanged, not silently altered


def test_ask_llm_polish_is_noop_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = ask("Give me a KPI overview.", use_llm_polish=True)
    assert result["llm_used"] is False


def test_agent_table_output_types():
    result = ask("Which merchant category has the highest chargeback-to-transaction ratio this quarter?", use_llm_polish=False)
    if result["table"] is not None:
        import pandas as pd
        assert isinstance(result["table"], pd.DataFrame)


def test_intent_patterns_do_not_overlap_ambiguously():
    """Spot check that closely related questions map to distinct, sensible intents."""
    assert classify_question("Show transaction volume by month.").name == "transaction_volume_trend"
    assert classify_question("Compare successful and failed transactions by month.").name == "success_failure_comparison"
