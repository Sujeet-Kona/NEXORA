from unittest.mock import Mock


def test_liveness_probe_does_not_require_dependencies(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_legacy_health_endpoint_remains_a_liveness_probe(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_probe_checks_postgres_and_qdrant(client, monkeypatch):
    qdrant = Mock()
    monkeypatch.setattr(
        "backend.main.get_qdrant_repository",
        lambda: qdrant,
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"postgres": "ok", "qdrant": "ok"},
    }
    qdrant.client.get_collections.assert_called_once_with()


def test_readiness_probe_returns_503_without_leaking_dependency_errors(
    client,
    monkeypatch,
):
    def unavailable_qdrant():
        raise RuntimeError("private endpoint and credentials")

    monkeypatch.setattr(
        "backend.main.get_qdrant_repository",
        unavailable_qdrant,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "postgres": "ok",
            "qdrant": "unavailable",
        },
    }
    assert "private endpoint" not in response.text
