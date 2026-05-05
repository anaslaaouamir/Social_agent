"""
Dispatcher d'alertes temps réel : WebSocket + Email + Slack
Consomme le topic Kafka social.alerts
"""
from __future__ import annotations
import asyncio
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Set
import websockets
from websockets.server import WebSocketServerProtocol
from core.config import get_settings
from core.kafka_client import get_consumer

settings = get_settings()
logger = logging.getLogger(__name__)

# ─── WebSocket Manager ────────────────────────────────────────────────────────

class WebSocketManager:
    """Gère les connexions WebSocket actives pour les alertes temps réel."""

    def __init__(self):
        self._connections: Set[WebSocketServerProtocol] = set()

    async def connect(self, ws: WebSocketServerProtocol):
        self._connections.add(ws)
        logger.info(f"WS connected: {ws.remote_address}. Total: {len(self._connections)}")

    async def disconnect(self, ws: WebSocketServerProtocol):
        self._connections.discard(ws)
        logger.info(f"WS disconnected. Total: {len(self._connections)}")

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
    """Declenche une alerte si ratio negatif/toxique depasse le seuil."""
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


# ─── Email sender ─────────────────────────────────────────────────────────────

def send_email_alert(subject: str, body: str, to: str = None):
    """Envoie un email d'alerte via SMTP."""
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
        logger.info(f"Email alert sent to {to}")
    except Exception as e:
        logger.error(f"Email send failed: {e}")


# ─── Slack sender ─────────────────────────────────────────────────────────────

async def send_slack_alert(message: str, severity: str = "medium"):
    """Envoie une notification Slack via webhook."""
    if not settings.slack_webhook_url:
        return
    import httpx
    emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🚨", "critical": "🔴"}.get(severity, "⚠️")
    payload = {
        "channel": settings.slack_alert_channel,
        "text": f"{emoji} *Social Agent Alert*\n{message}",
        "mrkdwn": True,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.slack_webhook_url, json=payload)
        if resp.status_code != 200:
            logger.error(f"Slack webhook failed: {resp.text}")


# ─── Kafka Alert Consumer ─────────────────────────────────────────────────────

async def consume_alerts():
    """
    Consomme le topic social.alerts en continu.
    Pour chaque alerte → broadcast WS + email + Slack selon sévérité.
    """
    consumer = get_consumer(
        group_id="alert-dispatcher",
        topics=[settings.kafka_topic_alerts],
    )
    loop = asyncio.get_event_loop()

    logger.info("Alert consumer started")
    try:
        while True:
            msg = await loop.run_in_executor(None, lambda: consumer.poll(timeout=1.0))
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka consumer error: {msg.error()}")
                continue

            try:
                alert = json.loads(msg.value().decode("utf-8"))
                severity = alert.get("severity", "medium")
                message = alert.get("message", "Alert from social agent")

                # 1. WebSocket broadcast (toujours)
                await ws_manager.broadcast({
                    "type": "alert",
                    "severity": severity,
                    "message": message,
                    "data": alert,
                })

                # 2. Email si high ou critical
                if severity in ("high", "critical"):
                    subject = f"{severity.upper()}: {message[:80]}"
                    body = f"<pre>{json.dumps(alert, indent=2)}</pre>"
                    loop.run_in_executor(None, send_email_alert, subject, body)

                # 3. Slack si medium+
                if severity in ("medium", "high", "critical"):
                    await send_slack_alert(
                        f"*{severity.upper()}*: {message}",
                        severity=severity,
                    )

            except Exception as e:
                logger.error(f"Alert processing error: {e}")
    finally:
        consumer.close()
