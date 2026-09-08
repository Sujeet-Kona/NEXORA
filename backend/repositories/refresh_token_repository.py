from datetime import datetime

from sqlalchemy.orm import Session

from backend.db.models import RefreshToken


def create_refresh_token(
    db: Session,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
) -> RefreshToken:
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    db.add(refresh_token)
    db.commit()
    db.refresh(refresh_token)

    return refresh_token


def get_refresh_token_by_hash(
    db: Session,
    token_hash: str,
) -> RefreshToken | None:
    return (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )


def revoke_refresh_token(
    db: Session,
    refresh_token: RefreshToken,
    revoked_at: datetime,
) -> RefreshToken:
    refresh_token.revoked_at = revoked_at

    db.commit()
    db.refresh(refresh_token)

    return refresh_token


def rotate_refresh_token(
    db: Session,
    current_refresh_token: RefreshToken,
    new_user_id: int,
    new_token_hash: str,
    new_expires_at: datetime,
    revoked_at: datetime,
) -> RefreshToken:
    current_refresh_token.revoked_at = revoked_at

    new_refresh_token = RefreshToken(
        user_id=new_user_id,
        token_hash=new_token_hash,
        expires_at=new_expires_at,
    )

    db.add(new_refresh_token)
    db.commit()
    db.refresh(new_refresh_token)

    return new_refresh_token
