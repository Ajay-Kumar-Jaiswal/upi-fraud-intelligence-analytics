import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import (
    data_available, get_graph_stats, get_high_degree_nodes, get_repeated_relationships,
    get_connected_components, get_dense_clusters, get_cycle_detection,
)
from components.filters import empty_state

st.set_page_config(page_title="Network / Fraud Rings", page_icon="🕸️", layout="wide")
st.title("Transaction Network Analysis")
# st.warning(
#     "⚠️ **Limitation, read before interpreting this page**: nodes are raw transaction-fact "
#     "user_id/merchant_id values, which are NOT confirmed unique-per-real-entity (see "
#     "DATA_AUDIT.md Open Question #1). Findings here describe **structural patterns in "
#     "transaction IDs**, not confirmed real-world fraud rings."
# )

if not data_available():
    st.error("No cleaned data found. Run `python scripts/run_pipeline.py` first.")
    st.stop()

stats = get_graph_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Nodes", f"{stats['total_nodes']:,}")
c2.metric("User Nodes", f"{stats['user_nodes']:,}")
c3.metric("Merchant Nodes", f"{stats['merchant_nodes']:,}")
c4.metric("Total Edges", f"{stats['total_edges']:,}")

st.markdown("---")
tab1, tab2, tab3, tab4 = st.tabs(["High-Degree Nodes", "Repeated Relationships", "Connected Components", "Cycle Analysis"])

with tab1:
    st.caption("Users transacting with unusually many merchants, or merchants transacting with unusually many users.")
    top_n = st.slider("Show top N", 5, 50, 20, key="degree_topn")
    hd = get_high_degree_nodes(top_n)
    if hd.empty:
        empty_state()
    else:
        fig = px.bar(hd, x="node_id", y="degree", color="kind", title="Highest-degree nodes")
        st.plotly_chart(fig, width='stretch')
        st.dataframe(hd, width='stretch')

with tab2:
    st.caption("user_id ↔ merchant_id pairs with an unusually high repeat-transaction count.")
    min_txn = st.slider("Minimum repeat count", 2, 10, 2, key="repeat_min")
    rp = get_repeated_relationships(min_txn, 20)
    if rp.empty:
        st.caption(
            f"No user-merchant pair has {min_txn}+ repeat transactions in this dataset. "
            "Every user-merchant relationship in this data window occurs at most once."
        )
    else:
        st.dataframe(rp, width='stretch')

with tab3:
    cc = get_connected_components()
    c1, c2 = st.columns(2)
    c1.metric("Total connected components", f"{cc['total_components']:,}")
    c2.metric("Largest component size", f"{cc['largest_component_size']} ({cc['largest_component_pct_of_nodes']}% of all nodes)")
    st.write("Top 10 component sizes:", cc["component_size_distribution_top10"])
    st.caption(
        f"{cc['isolated_pairs_count']:,} components are isolated user-merchant pairs (size 2) — "
        "single transactions with no further connection to the rest of the graph."
    )

with tab4:
    st.markdown("### Dense merchant clusters (shared users)")
    min_shared = st.slider("Minimum shared users", 2, 5, 2, key="cluster_min")
    dc = get_dense_clusters(min_shared, 15)
    if dc.empty:
        st.caption(
            f"No two merchants share {min_shared}+ common users in this dataset."
        )
    else:
        st.dataframe(dc, width='stretch')

    st.markdown("### Cycle / circular-flow analysis")
    cyc = get_cycle_detection()
    st.caption(cyc["finding"])
