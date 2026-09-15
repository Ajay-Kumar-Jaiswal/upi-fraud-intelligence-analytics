import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx
from src.graph.network_analysis import (
    build_transaction_graph, graph_summary_stats, high_degree_nodes,
    repeated_relationship_pairs, connected_components_summary,
    dense_merchant_clusters, cycle_detection,
)
from src.analytics.loaders import load_transactions


def test_graph_node_counts_match_distinct_ids():
    txn = load_transactions()
    G = build_transaction_graph(txn)
    assert G.number_of_nodes() == txn["user_id"].nunique() + txn["merchant_id"].nunique()


def test_graph_edge_count_matches_distinct_user_merchant_pairs():
    txn = load_transactions()
    G = build_transaction_graph(txn)
    expected_edges = txn.drop_duplicates(subset=["user_id", "merchant_id"]).shape[0]
    assert G.number_of_edges() == expected_edges


def test_graph_is_bipartite():
    G = build_transaction_graph()
    assert nx.is_bipartite(G)


def test_graph_summary_stats_no_crash_and_bounded():
    stats = graph_summary_stats()
    assert stats["total_nodes"] == stats["user_nodes"] + stats["merchant_nodes"]
    assert stats["total_edges"] > 0
    assert stats["is_this_structurally_a_pure_bipartite_graph"] is True


def test_high_degree_nodes_sorted_descending():
    out = high_degree_nodes(top_n=15)
    degrees = out["degree"].tolist()
    assert degrees == sorted(degrees, reverse=True)


def test_high_degree_nodes_only_real_node_kinds():
    out = high_degree_nodes(top_n=15)
    assert set(out["kind"]) <= {"user", "merchant"}


def test_repeated_relationship_pairs_respects_threshold():
    out = repeated_relationship_pairs(min_txn_count=2)
    if len(out):
        assert (out["txn_count"] >= 2).all()


def test_connected_components_sizes_sum_le_total_nodes():
    G = build_transaction_graph()
    cov = connected_components_summary(G)
    assert cov["largest_component_size"] <= G.number_of_nodes()
    assert cov["total_components"] > 0


def test_dense_merchant_clusters_no_crash():
    out = dense_merchant_clusters(min_shared_users=2, top_n=10)
    if len(out):
        assert (out["shared_user_count"] >= 2).all()
        assert (out["merchant_id_a"] != out["merchant_id_b"]).all()


def test_cycle_detection_confirms_bipartite_namespace_and_does_not_fabricate_cycles():
    result = cycle_detection()
    assert result["disjoint_user_merchant_namespaces_confirmed"] is True
    assert "cannot" in result["finding"].lower()  # must explicitly state the structural limitation


def test_graph_reproducible_across_two_builds():
    G1 = build_transaction_graph()
    G2 = build_transaction_graph()
    assert G1.number_of_nodes() == G2.number_of_nodes()
    assert G1.number_of_edges() == G2.number_of_edges()
