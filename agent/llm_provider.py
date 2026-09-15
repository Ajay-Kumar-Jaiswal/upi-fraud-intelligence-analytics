"""
Optional LLM layer. The agent's NUMBERS always come from the
deterministic query_engine - this module, if configured, is used ONLY
to rephrase the deterministic answer more naturally or to help match an
oddly-phrased question to a known intent. It is never given tool/code
execution ability and never invents figures.

Configuration: reads ANTHROPIC_API_KEY from the environment (never
hardcoded - see .env.example). If absent, `is_available()` returns
False and the agent falls back to the deterministic text as-is, which
is a fully complete answer on its own.
"""
import os


def is_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def rephrase(question: str, deterministic_answer: str) -> str:
    """Best-effort natural-language polish of an already-computed,
    deterministic answer. On any failure (no key, network error, import
    error), returns the deterministic answer UNCHANGED - the agent must
    remain fully functional without this."""
    if not is_available():
        return deterministic_answer
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=(
                "You rephrase a data-analysis answer to be more conversational, "
                "WITHOUT changing, adding, or removing any number or fact. If you "
                "are not sure how to rephrase safely, return the original text "
                "unchanged verbatim."
            ),
            messages=[{"role": "user", "content": f"Question: {question}\n\nAnswer to rephrase (preserve all numbers exactly): {deterministic_answer}"}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text").strip()
        return text or deterministic_answer
    except Exception:
        # Never let an LLM failure break the agent - deterministic answer stands.
        return deterministic_answer
