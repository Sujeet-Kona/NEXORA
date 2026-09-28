import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.core.exceptions import (
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
)
from backend.services.auth_service import (
    login_user_service,
    register_user_service,
)
from backend.services.login_throttle import LoginThrottle
from backend.services.storage import LocalStorage


STRONG_SECRET = "a-strong-unique-production-secret-value-123456"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _settings(**overrides):
    base = {
        "database_url": "postgresql+psycopg://u:p@localhost:5432/nexora",
        "jwt_secret_key": "test-secret",
    }
    base.update(overrides)
    return Settings(**base)


# --- M2a: environment + JWT algorithm + production guards ---


def test_environment_defaults_to_development(monkeypatch):
    # Hermetic: a developer/CI shell may export ENVIRONMENT, which would
    # otherwise override the default this test asserts.
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    assert _settings().environment == "development"
    assert _settings().is_production is False


def test_environment_is_normalized_and_validated():
    assert _settings(
        environment=" Production ",
        jwt_secret_key=STRONG_SECRET,
        ollama_model="qwen3:8b",
    ).environment == ("production")

    with pytest.raises(ValidationError):
        _settings(environment="banana")


def test_jwt_algorithm_rejects_unsupported():
    assert _settings(jwt_algorithm="hs256").jwt_algorithm == "HS256"

    for bad in ("none", "RS256", ""):
        with pytest.raises(ValidationError):
            _settings(jwt_algorithm=bad)


def test_production_rejects_weak_jwt_secret():
    for weak in ("", "changeme", "secret", "short"):
        with pytest.raises(ValidationError):
            _settings(
                environment="production",
                jwt_secret_key=weak,
            )


def test_production_rejects_known_ci_secret():
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            jwt_secret_key=(
                "ci-only-insecure-secret-do-not-use-in-production"
            ),
        )


def test_production_accepts_strong_secret():
    settings = _settings(
        environment="production",
        jwt_secret_key=STRONG_SECRET,
        ollama_model="qwen3:8b",
    )

    assert settings.is_production is True


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            jwt_secret_key=STRONG_SECRET,
            cors_origins="*",
        )


def test_production_accepts_explicit_cors_origins():
    settings = _settings(
        environment="production",
        jwt_secret_key=STRONG_SECRET,
        cors_origins="https://app.example.com, https://admin.example.com",
        ollama_model="qwen3:8b",
    )

    assert settings.cors_allowed_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_development_allows_wildcard_cors():
    settings = _settings(cors_origins="*")

    assert settings.cors_allowed_origins == ["*"]


def test_cors_allowed_origins_empty_by_default():
    assert _settings().cors_allowed_origins == []


# --- M12: production LLM configuration fail-fast ---


def test_production_ollama_requires_model():
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            jwt_secret_key=STRONG_SECRET,
            llm_provider="ollama",
            ollama_model="",
        )


def test_production_ollama_accepts_model():
    settings = _settings(
        environment="production",
        jwt_secret_key=STRONG_SECRET,
        llm_provider="ollama",
        ollama_model="qwen3:8b",
    )

    assert settings.llm_provider == "ollama"


def test_production_openai_requires_key_and_model():
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            jwt_secret_key=STRONG_SECRET,
            llm_provider="openai",
        )

    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            jwt_secret_key=STRONG_SECRET,
            llm_provider="openai",
            openai_api_key="sk-live",
            openai_model="",
        )


def test_production_openai_accepts_key_and_model():
    settings = _settings(
        environment="production",
        jwt_secret_key=STRONG_SECRET,
        llm_provider="openai",
        openai_api_key="sk-live",
        openai_model="gpt-4o-mini",
    )

    assert settings.llm_provider == "openai"


def test_development_allows_missing_llm_model():
    # Outside production the late 503 LLM-error contract still applies, so a
    # missing model must not block startup.
    settings = _settings(llm_provider="ollama", ollama_model=None)

    assert settings.is_production is False


# --- M2b: login throttle unit behaviour ---


def _throttle(max_attempts=3, lockout_seconds=60):
    clock = FakeClock()
    throttle = LoginThrottle(
        max_attempts=max_attempts,
        lockout_seconds=lockout_seconds,
        clock=clock,
    )
    return throttle, clock


def test_throttle_locks_after_max_failures():
    throttle, clock = _throttle(max_attempts=3, lockout_seconds=60)

    throttle.register_failure("user@example.com")
    throttle.register_failure("user@example.com")
    assert throttle.is_locked("user@example.com") is False

    throttle.register_failure("user@example.com")
    assert throttle.is_locked("user@example.com") is True
    assert throttle.seconds_until_unlock("user@example.com") == 60


def test_throttle_unlocks_after_window():
    throttle, clock = _throttle(max_attempts=2, lockout_seconds=30)

    throttle.register_failure("user@example.com")
    throttle.register_failure("user@example.com")
    assert throttle.is_locked("user@example.com") is True

    clock.advance(31)
    assert throttle.is_locked("user@example.com") is False
    assert throttle.seconds_until_unlock("user@example.com") == 0


def test_throttle_counts_restart_after_lockout_expiry():
    throttle, clock = _throttle(max_attempts=2, lockout_seconds=30)

    throttle.register_failure("user@example.com")
    throttle.register_failure("user@example.com")
    clock.advance(31)

    throttle.register_failure("user@example.com")
    assert throttle.is_locked("user@example.com") is False


def test_throttle_reset_clears_state():
    throttle, _clock = _throttle(max_attempts=2, lockout_seconds=30)

    throttle.register_failure("user@example.com")
    throttle.register_failure("user@example.com")
    assert throttle.is_locked("user@example.com") is True

    throttle.reset("user@example.com")
    assert throttle.is_locked("user@example.com") is False


def test_throttle_is_per_email():
    throttle, _clock = _throttle(max_attempts=2, lockout_seconds=30)

    throttle.register_failure("a@example.com")
    throttle.register_failure("a@example.com")

    assert throttle.is_locked("a@example.com") is True
    assert throttle.is_locked("b@example.com") is False


# --- M2b: throttle wired into the login service ---


def test_login_service_locks_after_repeated_failures(db):
    register_user_service(
        db=db,
        email="throttle@example.com",
        full_name="Throttle User",
        password="MySecret123!",
    )

    clock = FakeClock()
    throttle = LoginThrottle(
        max_attempts=3,
        lockout_seconds=60,
        clock=clock,
    )

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            login_user_service(
                db=db,
                email="throttle@example.com",
                password="WrongPassword!",
                throttle=throttle,
            )

    with pytest.raises(TooManyLoginAttemptsError) as exc_info:
        login_user_service(
            db=db,
            email="throttle@example.com",
            password="MySecret123!",
            throttle=throttle,
        )

    assert exc_info.value.retry_after == 60


def test_login_service_recovers_after_lockout_window(db):
    register_user_service(
        db=db,
        email="recover@example.com",
        full_name="Recover User",
        password="MySecret123!",
    )

    clock = FakeClock()
    throttle = LoginThrottle(
        max_attempts=2,
        lockout_seconds=30,
        clock=clock,
    )

    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            login_user_service(
                db=db,
                email="recover@example.com",
                password="WrongPassword!",
                throttle=throttle,
            )

    assert throttle.is_locked("recover@example.com") is True

    clock.advance(31)

    access_token, refresh_token = login_user_service(
        db=db,
        email="recover@example.com",
        password="MySecret123!",
        throttle=throttle,
    )

    assert access_token
    assert refresh_token


def test_login_service_success_resets_throttle(db):
    register_user_service(
        db=db,
        email="reset@example.com",
        full_name="Reset User",
        password="MySecret123!",
    )

    clock = FakeClock()
    throttle = LoginThrottle(
        max_attempts=3,
        lockout_seconds=60,
        clock=clock,
    )

    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            login_user_service(
                db=db,
                email="reset@example.com",
                password="WrongPassword!",
                throttle=throttle,
            )

    login_user_service(
        db=db,
        email="reset@example.com",
        password="MySecret123!",
        throttle=throttle,
    )

    assert throttle.is_locked("reset@example.com") is False

    # Two more failures are needed to lock again since state was cleared.
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            login_user_service(
                db=db,
                email="reset@example.com",
                password="WrongPassword!",
                throttle=throttle,
            )

    assert throttle.is_locked("reset@example.com") is False


# --- M2b: throttle surfaces as HTTP 429 ---


def test_login_endpoint_returns_429_after_repeated_failures(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "bruteforce@example.com",
            "full_name": "Brute Force",
            "password": "MySecret123!",
        },
    )

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "bruteforce@example.com",
                "password": "WrongPassword!",
            },
        )
        assert response.status_code == 401

    locked = client.post(
        "/api/v1/auth/login",
        json={
            "email": "bruteforce@example.com",
            "password": "MySecret123!",
        },
    )

    assert locked.status_code == 429
    assert locked.json() == {
        "detail": "Too many login attempts. Try again later."
    }
    assert int(locked.headers["Retry-After"]) > 0


# --- M2c: storage path-traversal containment ---


def test_storage_read_rejects_traversal(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))

    (tmp_path / "secret.txt").write_text("top secret")

    with pytest.raises(ValueError):
        storage.read("../secret.txt")


def test_storage_delete_rejects_traversal(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))

    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")

    with pytest.raises(ValueError):
        storage.delete("../secret.txt")

    assert secret.exists()


def test_storage_roundtrip_still_works(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))

    key = storage.save(
        organization_id=1,
        document_id=2,
        filename="ok.pdf",
        content=b"hello",
    )

    assert storage.read(key) == b"hello"

    storage.delete(key)

    with pytest.raises(FileNotFoundError):
        storage.read(key)
