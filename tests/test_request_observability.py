import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.core.middleware import REQUEST_ID_HEADER
from backend.main import app


@pytest.fixture()
def error_client():
    """Client that lets the top-level 500 handler run instead of re-raising."""

    def boom():
        raise RuntimeError("boom")

    app.router.add_api_route(
        "/__observability_error__",
        boom,
        methods=["GET"],
    )

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", None)
            != "/__observability_error__"
        ]


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False

    return True


def test_request_without_id_gets_generated_id(client):
    response = client.get("/health")

    assert response.status_code == 200

    request_id = response.headers[REQUEST_ID_HEADER]

    assert _is_uuid(request_id)


def test_valid_client_supplied_id_is_preserved(client):
    supplied = str(uuid.uuid4())

    response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied},
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_valid_token_id_is_preserved(client):
    supplied = "trace-abc_123.xyz"

    response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied},
    )

    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_invalid_id_is_replaced_with_generated_id(client):
    supplied = "bad id with spaces"

    response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied},
    )

    returned = response.headers[REQUEST_ID_HEADER]

    assert returned != supplied
    assert _is_uuid(returned)


def test_header_injection_id_is_replaced(client):
    supplied = "abc\r\nX-Injected: true"

    response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied},
    )

    returned = response.headers[REQUEST_ID_HEADER]

    assert "\n" not in returned
    assert "Injected" not in returned
    assert _is_uuid(returned)


def test_oversized_id_is_replaced_with_generated_id(client):
    supplied = "a" * 200

    response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied},
    )

    returned = response.headers[REQUEST_ID_HEADER]

    assert returned != supplied
    assert len(returned) <= 128
    assert _is_uuid(returned)


def test_error_response_contains_request_id(client):
    supplied = str(uuid.uuid4())

    response = client.get(
        "/does-not-exist",
        headers={REQUEST_ID_HEADER: supplied},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_unhandled_exception_response_contains_request_id(
    error_client,
):
    supplied = str(uuid.uuid4())

    response = error_client.get(
        "/__observability_error__",
        headers={REQUEST_ID_HEADER: supplied},
    )

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_completion_log_contains_required_fields(client, caplog):
    caplog.set_level(logging.INFO, logger="nexora")

    supplied = str(uuid.uuid4())

    client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied},
    )

    completion_records = [
        record
        for record in caplog.records
        if getattr(record, "request_id", None) == supplied
    ]

    assert completion_records

    record = completion_records[-1]

    assert record.request_id == supplied
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert isinstance(record.duration_ms, float)
    assert record.duration_ms >= 0.0


def test_completion_log_records_error_status(error_client, caplog):
    caplog.set_level(logging.INFO, logger="nexora")

    supplied = str(uuid.uuid4())

    error_client.get(
        "/__observability_error__",
        headers={REQUEST_ID_HEADER: supplied},
    )

    completion_records = [
        record
        for record in caplog.records
        if getattr(record, "request_id", None) == supplied
        and getattr(record, "path", None)
        == "/__observability_error__"
        and hasattr(record, "status_code")
    ]

    assert completion_records
    assert completion_records[-1].status_code == 500


def test_sensitive_data_is_not_logged(client, caplog):
    caplog.set_level(logging.INFO, logger="nexora")

    secret_token = "super-secret-bearer-token-value"
    secret_password = "SuperSecretPassword123!"

    response = client.post(
        "/api/v1/auth/register",
        headers={"Authorization": f"Bearer {secret_token}"},
        json={
            "email": "observability@example.com",
            "full_name": "Observability User",
            "password": secret_password,
        },
    )

    assert response.status_code == 201
    assert REQUEST_ID_HEADER in response.headers

    logged = caplog.text

    assert secret_token not in logged
    assert secret_password not in logged
    assert "Authorization" not in logged

    # Positive control: the request itself was still observed.
    assert "/api/v1/auth/register" in logged
