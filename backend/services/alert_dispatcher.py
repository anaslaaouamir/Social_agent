"""Real-time alert dispatch via WebSocket, email, and Slack."""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

from core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class WebSocketManager:
    """Tracks active WebSocket connections for live alerts."""

    def __init__(self):
        self._connections: Set[WebSocketServerProtocol] = set()

    async def connect(self, ws: WebSocketServerProtocol):
        self._connections.add(ws)
        logger.info("WS connected: %s. Total: %s", ws.remote_address, len(self._connections))

    async def disconnect(self, ws: WebSocketServerProtocol):
        self._connections.discard(ws)
        logger.info("WS disconnected. Total: %s", len(self._connections))

    async def broadcast(self, message: dict):
        if not self._connections:
            return
        payload = json.dumps(message)
        dead = set()
        for ws in self._connections.copy():
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        self._connections -= dead


ws_manager = WebSocketManager()


async def dispatch(account_id: str, severity: str, alert_type: str, message: str, metadata: dict | None = None):
    """Dispatch lightweight real-time alert payload to connected clients."""
    payload = {
        "type": "alert",
        "account_id": account_id,
        "severity": severity,
        "alert_type": alert_type,
        "message": message,
        "metadata": metadata or {},
    }
    await ws_manager.broadcast(payload)
    if severity in ("medium", "high", "critical"):
        await send_slack_alert(message, severity=severity)
    if severity in ("high", "critical"):
        send_email_alert(f"{alert_type}: {message[:80]}", f"<pre>{json.dumps(payload, indent=2)}</pre>")


async def check_sentiment_crisis(account_id: str, recent_comments: list) -> None:
    """Create a live alert if negative/toxic comments exceed a crisis threshold."""
    if not recent_comments:
        return
    negative = sum(
        1
        for comment in recent_comments
        if (getattr(comment, "sentiment", None) and getattr(comment.sentiment, "value", None) == "negative")
        or getattr(comment, "is_toxic", False)
    )
    ratio = negative / len(recent_comments)
    if ratio >= 0.5 and len(recent_comments) >= 10:
        await dispatch(
            account_id=account_id,
            severity="high",
            alert_type="sentiment_crisis",
            message=f"Crisis detectee : {ratio:.0%} commentaires negatifs/toxiques ({len(recent_comments)} analyses)",
            metadata={"negative_ratio": ratio, "sample_size": len(recent_comments)},
        )


def send_email_alert(subject: str, body: str, to: str = None):
    """Send an alert email via SMTP when configured."""
    to = to or settings.alert_email
    if not to or not settings.smtp_user:
        logger.warning("Email alert skipped: SMTP not configured")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Social Agent Alert] {subject}"
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, to, msg.as_string())
        logger.info("Email alert sent to %s", to)
    except Exception as exc:
        logger.error("Email send failed: %s", exc)


async def send_slack_alert(message: str, severity: str = "medium"):
    """Send a Slack notification via webhook when configured."""
    if not settings.slack_webhook_url:
        return
    import httpx

    label = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "critical": "CRITICAL"}.get(severity, "MEDIUM")
    payload = {
        "channel": settings.slack_alert_channel,
        "text": f"*Social Agent Alert [{label}]*\n{message}",
        "mrkdwn": True,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.slack_webhook_url, json=payload)
        if resp.status_code != 200:
            logger.error("Slack webhook failed: %s", resp.text)
