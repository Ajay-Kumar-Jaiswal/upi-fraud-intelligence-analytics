"""
Stage 7 — Transaction network analysis.

Graph structure: bipartite directed graph, nodes = user_id and
merchant_id (raw transaction-fact IDs - 100% coverage, no dependency
on the low-coverage KYC/merchant-master identity joins), edges =
transactions (user -> merchant), edge weight = transaction count,
edge attribute = total amount.

IMPORTANT LIMITATION (must be read alongside every graph finding):
per DATA_AUDIT.md Open Question #1, the same user_id/merchant_id can
be reused across different real people/merchants in the KYC/merchant
master files. This graph is built directly from fact_transactions,
so a "high-degree user_id" or "cycle" reflects transaction-ID-level
graph structure, not confirmed same-real-person behavior. This is
flagged explicitly wherever a finding is reported below.

No graph finding here is asserted as "confirmed fraud" or "money
laundering" - only as a "structural pattern that may warrant
investigation", per the brief's required terminology.
"""
import itertools
import networkx as nx
import pandas as pd
from src.analytics.loaders import load_transactions

MIN_CYCLE_LENGTH = 3          # a cycle of length 2 (A pays B, B pays A back through the same 2 nodes) is not meaningful in a simple bipartite user->merchant graph
HIGH_DEGREE_PERCENTILE = 0.99  # top 1% of nodes by degree
DENSE_CLUSTER_MIN_SIZE = 4


def build_transaction_graph(txn: pd.DataFrame = None) -> nx.DiGraph:
    """
    Builds a directed multigraph collapsed into a weighted DiGraph:
    node bipartite=0 -> user_id, bipartite=1 -> merchant_id.
    Edge (user_id -> merchant_id): weight=transaction_count, amount=total ₹.
    """
    if txn is None:
        txn = load_transactions()
    G = nx.DiGraph()
    for uid in txn["user_id"].unique():
        G.add_node(uid, kind="user")
    for mid in txn["merchant_id"].unique():
        G.add_node(mid, kind="merchant")

    agg = txn.groupby(["user_id", "merchant_id"]).agg(
        txn_count=("txn_id", "count"), total_amount=("amount", "sum")
    ).reset_index()
    for _, row in agg.iterrows():
        G.add_edge(row["user_id"], row["merchant_id"], weight=int(row["txn_count"]), amount=round(float(row["total_amount"]), 2))
    return G


def graph_summary_stats(G: nx.DiGraph = None) -> dict:
    if G is None:
        G = build_transaction_graph()
    user_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "user"]
    merchant_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "merchant"]
    return {
        "total_nodes": G.number_of_nodes(),
        "user_nodes": len(user_nodes),
        "merchant_nodes": len(merchant_nodes),
        "total_edges": G.number_of_edges(),
        "average_user_out_degree": round(sum(dict(G.out_degree(user_nodes)).values()) / len(user_nodes), 3) if user_nodes else 0,
        "average_merchant_in_degree": round(sum(dict(G.in_degree(merchant_nodes)).values()) / len(merchant_nodes), 3) if merchant_nodes else 0,
        "is_this_structurally_a_pure_bipartite_graph": nx.is_bipartite(G),
        "limitation": (
            "Nodes are raw transaction-fact user_id/merchant_id values. Per DATA_AUDIT.md "
            "Open Question #1, these IDs are not confirmed unique-per-real-entity in the "
            "KYC/merchant master files, so graph structure reflects ID-level patterns, not "
            "confirmed real-world entity relationships."
        ),
    }


def high_degree_nodes(G: nx.DiGraph = None, top_n: int = 20) -> pd.DataFrame:
    """
    High-degree nodes = users transacting with unusually many distinct
    merchants, or merchants transacting with unusually many distinct
    users. Reported as a structural observation ("high fan-out/fan-in"),
    not a fraud conclusion.
    """
    if G is None:
        G = build_transaction_graph()
    rows = []
    for n, d in G.nodes(data=True):
        deg = G.out_degree(n) if d.get("kind") == "user" else G.in_degree(n)
        rows.append({"node_id": n, "kind": d.get("kind"), "degree": deg})
    out = pd.DataFrame(rows).sort_values("degree", ascending=False).reset_index(drop=True)
    return out.head(top_n)


def repeated_relationship_pairs(min_txn_count: int = 5, top_n: int = 20) -> pd.DataFrame:
    """
    user_id <-> merchant_id pairs with an unusually high number of
    repeated transactions between the SAME two nodes - a structural
    concentration signal (dataset notes example: 'repeated transfer
    paths').
    """
    txn = load_transactions()
    agg = txn.groupby(["user_id", "merchant_id"]).agg(
        txn_count=("txn_id", "count"), total_amount=("amount", "sum")
    ).reset_index()
    flagged = agg[agg["txn_count"] >= min_txn_count].sort_values("txn_count", ascending=False)
    flagged["total_amount"] = flagged["total_amount"].round(2)
    return flagged.head(top_n).reset_index(drop=True)


def connected_components_summary(G: nx.DiGraph = None) -> dict:
    """
    Weakly-connected-component analysis. A user->merchant bipartite
    graph built from real transaction data is generically expected to
    have one giant connected component plus possibly isolated pairs -
    this function reports the ACTUAL distribution rather than assuming
    that shape.
    """
    if G is None:
        G = build_transaction_graph()
    components = list(nx.weakly_connected_components(G))
    sizes = sorted([len(c) for c in components], reverse=True)
    return {
        "total_components": len(components),
        "largest_component_size": sizes[0] if sizes else 0,
        "largest_component_pct_of_nodes": round(sizes[0] / G.number_of_nodes() * 100, 2) if sizes and G.number_of_nodes() else 0.0,
        "component_size_distribution_top10": sizes[:10],
        "isolated_pairs_count": sum(1 for s in sizes if s == 2),
    }


def dense_merchant_clusters(min_shared_users: int = 3, top_n: int = 15) -> pd.DataFrame:
    """
    Merchant pairs that share an unusually large number of common users
    (both merchants transacted with with the same set of user_ids) -
    a structural concentration/potential-collusion indicator, reported
    plainly as a pattern, not a confirmed finding.

    NOTE: computed only among merchants with a manageable user-list size
    to keep this an O(n^2) operation tractable on this dataset's scale
    (documented performance choice, not a data limitation).
    """
    txn = load_transactions()
    merchant_users = txn.groupby("merchant_id")["user_id"].apply(set)
    # restrict candidate pool to merchants with >=2 and <=200 distinct users to bound comparisons
    candidates = merchant_users[(merchant_users.apply(len) >= 2) & (merchant_users.apply(len) <= 200)]
    rows = []
    ids = list(candidates.index)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            shared = candidates[ids[i]] & candidates[ids[j]]
            if len(shared) >= min_shared_users:
                rows.append({
                    "merchant_id_a": ids[i], "merchant_id_b": ids[j],
                    "shared_user_count": len(shared),
                })
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("shared_user_count", ascending=False).head(top_n).reset_index(drop=True)
    return out


def cycle_detection(max_users_for_full_search: int = 2000) -> dict:
    """
    Cycle detection in the FULL transaction graph (users + merchants as
    distinct node types) will structurally never contain a cycle shorter
    than length 4 (user->merchant->user->merchant, since edges only go
    user->merchant) UNLESS a merchant also transacts as a "user" in
    another row, which this dataset's schema does not support (merchants
    and users are disjoint ID namespaces: MCH#### vs USR#####, verified
    in DATA_AUDIT.md). This function reports that structural fact
    explicitly rather than running an expensive/meaningless cycle search
    or fabricating a "circular fraud ring" finding the bipartite
    structure cannot actually produce.
    """
    txn = load_transactions()
    user_prefixes = txn["user_id"].str.startswith("USR").all()
    merchant_prefixes = txn["merchant_id"].str.startswith("MCH").all()
    disjoint_namespaces = user_prefixes and merchant_prefixes
    return {
        "disjoint_user_merchant_namespaces_confirmed": bool(disjoint_namespaces),
        "finding": (
            "This dataset's transaction graph is structurally bipartite (every edge "
            "goes user_id -> merchant_id, and the two ID namespaces never overlap - "
            "confirmed above). A bipartite graph with edges in only one direction "
            "cannot contain a true transaction cycle (money returning to its origin "
            "through a chain of distinct parties), because there is no user->user or "
            "merchant->merchant edge for a cycle to close through. Reporting this "
            "structural limitation explicitly rather than fabricating a 'circular "
            "money-laundering ring' finding this graph shape cannot support. A genuine "
            "circular-flow analysis would require account-to-account transfer data "
            "(not present in this dataset - see DATA_AUDIT.md), not user-to-merchant "
            "payment data."
        ),
    }


if __name__ == "__main__":
    import json
    G = build_transaction_graph()
    print(json.dumps(graph_summary_stats(G), indent=2))
    print("\n--- high degree nodes ---")
    print(high_degree_nodes(G, 10).to_string(index=False))
    print("\n--- repeated relationship pairs ---")
    print(repeated_relationship_pairs(3, 10).to_string(index=False))
    print("\n--- connected components ---")
    print(json.dumps(connected_components_summary(G), indent=2))
    print("\n--- dense merchant clusters (shared users) ---")
    print(dense_merchant_clusters(3, 10).to_string(index=False))
    print("\n--- cycle detection ---")
    print(json.dumps(cycle_detection(), indent=2))
