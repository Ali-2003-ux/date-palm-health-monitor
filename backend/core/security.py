"""Authentication: bcrypt password hashing, JWT tokens, role guards."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import get_db
from backend.models import User, UserRole

_BCRYPT_ROUNDS = 12
_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time password check; False on malformed hashes."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user: User, expires_minutes: int | None = None) -> str:
    """Sign a JWT carrying the identity and role claims."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(
        payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict[str, Any]:
    """Verify signature/expiry and return the claims."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )


def _oauth2_scheme() -> OAuth2PasswordBearer:
    return OAuth2PasswordBearer(
        tokenUrl=f"{get_settings().API_V1_PREFIX}/auth/login", auto_error=True
    )


oauth2_scheme = _oauth2_scheme()


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the bearer token to an active user row."""
    try:
        claims = decode_token(token)
        user_id = uuid.UUID(str(claims.get("sub")))
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXCEPTION
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """Dependency factory: allow only the given roles (403 otherwise)."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(r.value for r in roles)}",
            )
        return user

    return checker


def ensure_palm_access(palm_owner_id: uuid.UUID, user: User) -> None:
    """Farmers may only touch their own palms; staff roles see everything."""
    if user.role is UserRole.FARMER and palm_owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this palm tree.",
        )
