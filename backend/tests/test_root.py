def test_root_returns_service_info(client):
    response = client.get("/")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "running"
    assert "service" in body
    assert body["docs"] == "/docs"
