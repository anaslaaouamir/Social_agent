"""Alerts router."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from models.domain import User, Alert, SocialAccount
from api.auth_utils import get_current_user

router = APIRouter()


@router.get("/")
async def list_alerts(
    severity: str = Query(None),
    acknowledged: bool = Query(None),
    limit: int = Query(50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Alert).join(SocialAccount)
        .where(SocialAccount.user_id == current_user.id)
    )
    if severity:
        q = q.where(Alert.severity == severity)
    if acknowledged is not None:
        q = q.where(Alert.is_acknowledged == acknowledged)
    q = q.order_by(Alert.created_at.desc()).limit(limit)
    result = await db.execute(q)
    alerts = result.scalars().all()
    deduped = []
    seen_keys = set()
    for alert in alerts:
        metadata = alert.metadata_ or {}
        dedupe_key = (
            str(alert.account_id),
            alert.alert_type,
            metadata.get("target_key") or str(alert.id),
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped.append(alert)
    return [
        {
            "id": str(a.id),
            "severity": a.severity.value,
            "alert_type": a.alert_type,
            "title": a.title,
            "description": a.description,
            "metadata": a.metadata_ or {},
            "action_url": (a.metadata_ or {}).get("action_url", ""),
            "is_acknowledged": a.is_acknowledged,
            "created_at": a.created_at.isoformat(),
        }
        for a in deduped
    ]


@router.patch("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Alert).join(SocialAccount)
        .where(Alert.id == uuid.UUID(alert_id), SocialAccount.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(404, "Alert not found")
    alert.is_acknowledged = True
    alert.acknowledged_by = str(current_user.id)
    await db.flush()
    return {"status": "acknowledged"}
