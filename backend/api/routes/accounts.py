"""Social accounts router."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from pydantic import BaseModel
from core.database import get_db
from models.domain import (
    Alert,
    AccountMetric,
    Comment,
    DirectMessage,
    Post,
    SocialAccount,
    Platform,
    User,
)
from api.auth_utils import get_current_user

router = APIRouter()


class AccountCreate(BaseModel):
    platform: str
    account_id: str
    account_name: str
    access_token: str
    refresh_token: str = ""
    followers_count: int = 0


@router.get("/")
async def list_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SocialAccount).where(SocialAccount.user_id == current_user.id))
    accounts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "platform": a.platform.value,
            "account_name": a.account_name,
            "account_id": a.account_id,
            "followers_count": a.followers_count,
        }
        for a in accounts
    ]


@router.post("/", status_code=201)
async def connect_account(
    data: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = SocialAccount(
        id=uuid.uuid4(),
        user_id=current_user.id,
        platform=Platform(data.platform),
        account_id=data.account_id,
        account_name=data.account_name,
        access_token=data.access_token,
        refresh_token=data.refresh_token,
        followers_count=data.followers_count,
    )
    db.add(account)
    await db.flush()
    return {"id": str(account.id), "platform": account.platform.value, "account_name": account.account_name}


@router.delete("/{account_id}", status_code=204)
async def disconnect_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account_uuid = uuid.UUID(account_id)
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == account_uuid,
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    post_ids = (
        select(Post.id)
        .where(Post.account_id == account_uuid)
        .scalar_subquery()
    )

    await db.execute(delete(Comment).where(Comment.post_id.in_(post_ids)))
    await db.execute(delete(Post).where(Post.account_id == account_uuid))
    await db.execute(delete(Alert).where(Alert.account_id == account_uuid))
    await db.execute(delete(AccountMetric).where(AccountMetric.account_id == account_uuid))
    await db.execute(delete(DirectMessage).where(DirectMessage.account_id == account_uuid))
    await db.delete(account)
