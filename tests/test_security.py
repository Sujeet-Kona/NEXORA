from backend.core.security import hash_password, verify_password


def test_hash_password_returns_hash():
    password = "TestPassword123!"

    hashed_password = hash_password(password)

    assert hashed_password != password
    assert hashed_password.startswith("$argon2")


def test_verify_password_accepts_correct_password():
    password = "TestPassword123!"
    hashed_password = hash_password(password)

    assert verify_password(
        password,
        hashed_password,
    ) is True


def test_verify_password_rejects_wrong_password():
    password = "TestPassword123!"
    hashed_password = hash_password(password)

    assert verify_password(
        "WrongPassword!",
        hashed_password,
    ) is False


def test_same_password_produces_different_hashes():
    password = "TestPassword123!"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)
