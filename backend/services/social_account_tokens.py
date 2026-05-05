"""Helpers to resolve account access tokens with optional env overrides."""
from __future__ import annotations

from core.config import get_settings
from models.domain import Platform, SocialAccount

settings = get_settings()


def resolve_account_access_tokens(account: SocialAccount) -> list[tuple[str, str]]:
    """Return candidate tokens to try for an account, ordered by preference."""
    candidates: list[tuple[str, str]] = []

    if account.platform == Platform.INSTAGRAM:
        metadata = account.metadata_ or {}
        configured_account_id = (settings.instagram_manual_account_id or "").strip()
        configured_username = (settings.instagram_manual_account_username or "").strip().lower()
        manual_token = (settings.instagram_manual_access_token or "").strip()

        account_ids = {
            str(account.account_id or "").strip(),
            str(metadata.get("instagram_account_id") or "").strip(),
        }
        usernames = {
            str(account.account_name or "").strip().lower(),
            str(metadata.get("instagram_username") or "").strip().lower(),
        }

        if manual_token and (
            (configured_account_id and configured_account_id in account_ids)
            or (configured_username and configured_username in usernames)
        ):
            candidates.append((manual_token, "env:instagram_manual_access_token"))

    db_token = (account.access_token or "").strip()
    if db_token and all(token != db_token for token, _source in candidates):
        candidates.append((db_token, "db:access_token"))
    return candidates


def resolve_account_access_token(account: SocialAccount) -> tuple[str, str]:
    """Return the preferred token to use for an account plus its source label."""
    candidates = resolve_account_access_tokens(account)
    if candidates:
        return candidates[0]
    return "", "missing"
