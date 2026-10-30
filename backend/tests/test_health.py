def test_health_returns_200_with_expected_shape(client):
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"status", "app_name", "environment", "database"}
    assert body["status"] in {"ok", "degraded"}


def test_health_reports_database_ok_when_db_reachable(client):
    """
    This test assumes a reachable PostgreSQL instance configured via the
    same environment variables as the application (see .env.example /
    docker-compose.yml). If the database is unreachable, `database` will
    report an `error: ...` string instead of `ok` and this test documents
    that expectation rather than silently passing either way.
    """
    response = client.get("/health")
    body = response.json()
    assert body["database"] == "ok", (
        "Expected the configured PostgreSQL database to be reachable during "
        "tests. Ensure POSTGRES_* env vars point to a running instance "
        "(e.g. `docker compose up -d db`)."
    )
