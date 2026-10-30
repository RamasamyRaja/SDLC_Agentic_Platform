from app.agent.edges import route_after_node


def test_route_after_node_continues_on_running_status():
    assert route_after_node({"status": "RUNNING"}) == "continue"


def test_route_after_node_continues_when_status_absent():
    assert route_after_node({}) == "continue"


def test_route_after_node_fails_on_failed_status():
    assert route_after_node({"status": "FAILED"}) == "failed"
