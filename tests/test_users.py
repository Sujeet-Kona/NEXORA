import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import get_db
from backend.db.models import Base
from backend.main import app


TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_user(client):
    response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "full_name": "Alice Smith",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Smith"
    assert isinstance(data["id"], int)
    assert "created_at" in data


def test_duplicate_email_returns_409(client):
    payload = {
        "email": "duplicate@example.com",
        "full_name": "First User",
    }

    first_response = client.post("/users", json=payload)

    duplicate_response = client.post(
        "/users",
        json={
            "email": payload["email"],
            "full_name": "Second User",
        },
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "Email already registered"
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "invalid-email",
            "full_name": "Invalid Email",
        },
        {
            "full_name": "Missing Email",
        },
        {
            "email": "missingname@example.com",
        },
    ],
)
def test_invalid_user_payload_returns_422(client, payload):
    response = client.post("/users", json=payload)

    assert response.status_code == 422


def test_empty_full_name_returns_422(client):
    response = client.post(
        "/users",
        json={
            "email": "empty@example.com",
            "full_name": "",
        },
    )

    assert response.status_code == 422


def test_whitespace_full_name_returns_422(client):
    response = client.post(
        "/users",
        json={
            "email": "spaces@example.com",
            "full_name": "   ",
        },
    )

    assert response.status_code == 422


def test_full_name_at_max_length_is_accepted(client):
    response = client.post(
        "/users",
        json={
            "email": "max@example.com",
            "full_name": "A" * 255,
        },
    )

    assert response.status_code == 201
    assert len(response.json()["full_name"]) == 255


def test_full_name_over_max_length_returns_422(client):
    response = client.post(
        "/users",
        json={
            "email": "overmax@example.com",
            "full_name": "A" * 256,
        },
    )

    assert response.status_code == 422


def test_get_users_returns_created_users(client):
    first_response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "full_name": "Alice Smith",
        },
    )

    second_response = client.post(
        "/users",
        json={
            "email": "bob@example.com",
            "full_name": "Bob Jones",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get("/users")

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["email"] == "alice@example.com"
    assert data[1]["email"] == "bob@example.com"


def test_get_user_returns_user(client):
    create_response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "full_name": "Alice Smith",
        },
    )

    assert create_response.status_code == 201

    user_id = create_response.json()["id"]

    response = client.get(f"/users/{user_id}")

    assert response.status_code == 200
    assert response.json()["id"] == user_id
    assert response.json()["email"] == "alice@example.com"
    assert response.json()["full_name"] == "Alice Smith"


def test_get_user_not_found_returns_404(client):
    response = client.get("/users/9999")

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_invalid_user_id_returns_400(client):
    response = client.get("/users/0")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "User ID must be a positive integer"
    }


def test_negative_user_id_returns_400(client):
    response = client.get("/users/-1")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "User ID must be a positive integer"
    }


def test_non_integer_user_id_returns_422(client):
    response = client.get("/users/not-an-integer")

    assert response.status_code == 422


def test_unexpected_error_returns_500_and_logs(monkeypatch):
    logged_messages = []

    def fake_logger_exception(message, **kwargs):
        logged_messages.append(message)

    monkeypatch.setattr(
        "backend.main.logger.exception",
        fake_logger_exception,
    )

    def broken_get_db():
        raise RuntimeError("simulated internal failure")

    app.dependency_overrides[get_db] = broken_get_db

    try:
        with TestClient(
            app,
            raise_server_exceptions=False,
        ) as test_client:
            response = test_client.get("/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error"
    }

    assert "Unhandled application error" in logged_messages


def test_versioned_get_users_works(client):
    response = client.get("/api/v1/users")

    assert response.status_code == 200
    assert response.json() == []


def test_versioned_create_user_works(client):
    response = client.post(
        "/api/v1/users",
        json={
            "email": "versioned@example.com",
            "full_name": "Versioned User",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "versioned@example.com"
    assert response.json()["full_name"] == "Versioned User"
