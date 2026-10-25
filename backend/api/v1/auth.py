"""Authentication endpoints: register, login (OAuth2), current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.security import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from backend.db.session import get_db
from backend.models import User
from backend.schemas import Token, UserCreate, UserRead

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new farmer account",
)
def register(payload: UserCreate, db: DbSession) -> User:
    exists = db.scalar(select(User).where(User.email == payload.email))
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # race on the unique email index
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    logger.info("Registered user %s (%s)", user.email, user.role.value)
    return user


@router.post("/login", response_model=Token, summary="Obtain a JWT access token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession
) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )
    settings = get_settings()
    return Token(
        access_token=create_access_token(user),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserRead, summary="Current authenticated user")
def me(user: CurrentUser) -> User:
    return user
