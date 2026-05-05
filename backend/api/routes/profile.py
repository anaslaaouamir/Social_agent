"""User profile management route."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import (
    get_current_user,
    hash_password,
    validate_password_length,
    verify_password,
)
from core.database import get_db
from models.domain import User

router = APIRouter()


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    preferred_language: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_length(value)


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    preferred_language: str
    model_config = {"from_attributes": True}


@router.get("/", response_model=ProfileOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/", response_model=ProfileOut)
async def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.preferred_language is not None:
        if data.preferred_language not in {"fr", "ar", "en"}:
            raise HTTPException(400, "Language must be fr, ar or en")
        current_user.preferred_language = data.preferred_language
    await db.flush()
    return current_user


@router.post("/change-password")
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()
    return {"message": "Mot de passe modifie avec succes"}
