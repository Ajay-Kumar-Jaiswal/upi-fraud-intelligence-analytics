"""
Top-level entry point for the AI Analyst agent.

    from agent.analyst import ask
    result = ask("Which merchant category has the highest chargeback ratio?")

Flow: classify_question() [deterministic pattern match] -> execute()
[deterministic, calls real tested analytics functions] -> optionally
llm_provider.rephrase() [cosmetic only, never changes numbers, no-op if
no API key configured].
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.router import classify_question
from agent.query_engine import execute, AgentAnswer
from agent import llm_provider


SUPPORTED_EXAMPLE_QUESTIONS = [
    "Which merchant category has the highest chargeback-to-transaction ratio this quarter?",
    "Show me the riskiest merchants.",
    "Which users have suspicious transaction patterns?",
    "What are the largest chargeback categories?",
    "Show suspicious network clusters.",
    "Why is MCH1234 considered high risk?",
    "Show transaction volume by month.",
    "Compare successful and failed transactions by month.",
    "Which merchant has the highest chargeback amount?",
    "Which users have the highest number of chargebacks?",
    "Compare average transaction value across merchant categories.",
    "Give me a KPI overview.",
]


def ask(question: str, use_llm_polish: bool = True) -> dict:
    intent = classify_question(question)
    if intent is None:
        return {
            "question": question,
            "answer": (
                "I cannot answer this reliably because the required information is not "
                "available in the dataset, or this question isn't one of the supported "
                "analysis types yet. Try one of these:\n- " + "\n- ".join(SUPPORTED_EXAMPLE_QUESTIONS)
            ),
            "table": None,
            "chart_type": None,
            "chart_x": None,
            "chart_y": None,
            "intent": None,
            "methodology": "",
            "llm_used": False,
        }

    result: AgentAnswer = execute(intent, question)
    answer_text = result.text
    llm_used = False
    if use_llm_polish and llm_provider.is_available():
        polished = llm_provider.rephrase(question, result.text)
        if polished != result.text:
            answer_text = polished
            llm_used = True

    return {
        "question": question,
        "answer": answer_text,
        "table": result.table,
        "chart_type": result.chart_type,
        "chart_x": result.chart_x,
        "chart_y": result.chart_y,
        "intent": intent.name,
        "methodology": result.methodology,
        "llm_used": llm_used,
    }


if __name__ == "__main__":
    for q in SUPPORTED_EXAMPLE_QUESTIONS:
        r = ask(q, use_llm_polish=False)
        print(f"\nQ: {q}\nIntent: {r['intent']}\nA: {r['answer'][:300]}")

    print("\n--- unsupported question ---")
    r = ask("What is the meaning of life?", use_llm_polish=False)
    print(r["answer"][:200])
