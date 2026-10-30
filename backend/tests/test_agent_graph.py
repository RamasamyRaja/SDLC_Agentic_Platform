from app.agent.graph import build_agent_graph


def test_graph_compiles_without_error():
    graph = build_agent_graph()
    assert graph is not None


def test_graph_contains_expected_nodes():
    graph = build_agent_graph()
    nodes = set(graph.get_graph().nodes.keys())
    expected = {
        "__start__",
        "LOAD_TASK",
        "BUILD_CONTEXT",
        "REASON",
        "VALIDATE_REASONING",
        "DECIDE_ACTION",
        "FINALIZE",
        "__end__",
    }
    assert expected.issubset(nodes)


def test_graph_has_edge_from_start_to_load_task():
    graph = build_agent_graph()
    edges = graph.get_graph().edges
    edge_pairs = {(e.source, e.target) for e in edges}
    assert ("__start__", "LOAD_TASK") in edge_pairs


def test_graph_has_edge_from_finalize_to_end():
    graph = build_agent_graph()
    edges = graph.get_graph().edges
    edge_pairs = {(e.source, e.target) for e in edges}
    assert ("FINALIZE", "__end__") in edge_pairs


def test_graph_build_is_cached():
    """build_agent_graph() is lru_cache'd — repeated calls must return the
    exact same compiled graph instance, not rebuild each time."""
    graph_a = build_agent_graph()
    graph_b = build_agent_graph()
    assert graph_a is graph_b
