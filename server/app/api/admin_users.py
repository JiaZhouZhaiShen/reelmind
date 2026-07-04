"""Admin users API."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.user import User
from ..auth import get_current_user, hash_password
from .admin import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/users")
async def list_admin_users(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """List all users (without password hashes)."""
    rows = (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]


@router.post("/users", status_code=201)
async def create_admin_user(
    data: dict,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Create a new user."""
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")
    if not username or not password:
        raise HTTPException(400, "Username and password are required")
    existing = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"User '{username}' already exists")
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Created user %s (role=%s)", username, role)
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }



@router.patch("/users/{user_id}")
async def update_admin_user(
    user_id: uuid.UUID,
    data: dict,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Update a user's role or password."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    if "role" in data:
        user.role = data["role"]
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])
    session.add(user)
    await session.commit()
    logger.info("Updated user %s", user.username)
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_admin_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Delete a user."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    await session.delete(user)
    await session.commit()
    logger.info("Deleted user %s", user.username)
    return {"status": "ok"}


