"""Authentication API — register, login, current user."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..database import get_session
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ──────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: dict


class UserInfo(BaseModel):
    id: str
    username: str
    role: str


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    """Register a new user.  The very first user gets the admin role."""
    logger.info("Register attempt: username=%s", body.username)
    username = body.username.strip()
    if not username or len(username) < 2:
        logger.warning("Registration failed: username too short (%s)", username)
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    if len(body.password) < 6:
        logger.warning("Registration failed: password too short for user %s", username)
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Check if username already exists
    result = await session.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    # First user becomes admin
    count_result = await session.execute(select(User))
    existing_users = count_result.scalars().all()
    role = "admin" if len(existing_users) == 0 else "user"

    user = User(
        username=username,
        password_hash=hash_password(body.password),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(str(user.id), user.username, user.role)
    logger.info("User registered successfully: username=%s, role=%s, id=%s", user.username, user.role, user.id)
    return TokenResponse(
        token=token,
        user={"id": str(user.id), "username": user.username, "role": user.role},
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    """Authenticate a user and return a JWT token."""
    logger.info("Login attempt: username=%s", body.username)
    result = await session.execute(
        select(User).where(User.username == body.username.strip())
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        logger.warning("Login failed: invalid credentials for username=%s", body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(str(user.id), user.username, user.role)
    logger.info("Login successful: username=%s, role=%s", user.username, user.role)
    return TokenResponse(
        token=token,
        user={"id": str(user.id), "username": user.username, "role": user.role},
    )


@router.get("/me", response_model=UserInfo)
async def me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's info."""
    logger.debug("User info requested: username=%s, role=%s", current_user.get("username"), current_user.get("role"))
    return UserInfo(**current_user)
