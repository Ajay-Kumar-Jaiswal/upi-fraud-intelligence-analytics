import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import data_available
from agent.analyst import ask, SUPPORTED_EXAMPLE_QUESTIONS
from agent import llm_provider

st.set_page_config(page_title="AI Analyst", page_icon="🤖", layout="wide")
st.title("AI Analyst")
# st.caption(
#     "Ask a question in plain English. Answers are computed by a **deterministic analytics "
#     "layer** (the same tested functions powering every other page) — the agent matches your "
#     "question to a known analysis type and never invents numbers. If a question doesn't match "
#     "a supported analysis, it says so explicitly instead of guessing."
# )

if not data_available():
    st.error("No cleaned data found. Run `python scripts/run_pipeline.py` first.")
    st.stop()

# if llm_provider.is_available():
#     st.success("✨ Optional LLM phrasing polish is ACTIVE (ANTHROPIC_API_KEY detected) — numbers are still 100% deterministic.")
# else:
#     st.info(
#         "ℹ️ Running in fully deterministic mode (no ANTHROPIC_API_KEY set). Answers are precise "
#         "but plainly worded rather than conversationally polished. See `.env.example` to enable "
#         "optional LLM phrasing — it is never required for correct answers."
#     )

with st.expander("💡 Example questions you can ask"):
    for q in SUPPORTED_EXAMPLE_QUESTIONS:
        st.markdown(f"- {q}")

question = st.text_input("Your question", placeholder="e.g. Which merchant category has the highest chargeback-to-transaction ratio this quarter?")
col1, col2 = st.columns([1, 5])
ask_clicked = col1.button("Ask", type="primary")

if ask_clicked and question.strip():
    with st.spinner("Analyzing..."):
        result = ask(question, use_llm_polish=True)

    st.markdown("### Answer")
    st.markdown(result["answer"])

    if result["intent"] is None:
        st.caption("No matching analysis type found for this question.")
    else:
        st.caption(f"Intent: `{result['intent']}` | Source: `{result['methodology']}`" + (" | ✨ LLM-polished phrasing" if result["llm_used"] else ""))

        if result["table"] is not None and not result["table"].empty:
            df = result["table"]
            if result["chart_type"] == "bar" and result["chart_x"] in df.columns and result["chart_y"] in df.columns:
                fig = px.bar(df, x=result["chart_x"], y=result["chart_y"], title=question)
                st.plotly_chart(fig, width='stretch')
            elif result["chart_type"] == "line" and result["chart_x"] in df.columns and result["chart_y"] in df.columns:
                fig = px.line(df, x=result["chart_x"], y=result["chart_y"], title=question)
                st.plotly_chart(fig, width='stretch')

            st.markdown("**Underlying data:**")
            display_df = df.copy()
            for c in display_df.columns:
                if display_df[c].apply(lambda v: isinstance(v, list)).any():
                    display_df[c] = display_df[c].apply(lambda v: "; ".join(v) if isinstance(v, list) else v)
            st.dataframe(display_df, width='stretch')
elif ask_clicked:
    st.caption("Please enter a question.")
