"""Telegram delivery."""
from __future__ import annotations

import html
import logging

import httpx

from jobfinder.model import Job

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"


def format_message(job: Job) -> str:
    """Telegram HTML-parse-mode message. All interpolated text is escaped."""
    title = html.escape(job.title)
    company = html.escape(job.company)
    location = html.escape(job.location)
    posted = job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "unknown"
    return (
        f"<b>{title}</b>\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🗓 posted {posted}\n"
        f"\n{html.escape(job.url)}"
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, client: httpx.AsyncClient, job: Job) -> bool:
        """Return True only on confirmed delivery.

        The caller must not mark a job seen when this returns False.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": format_message(job),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp = await client.post(
                API.format(token=self.bot_token), json=payload, timeout=20.0
            )
            if resp.status_code != 200:
                log.error("telegram %s: %s", resp.status_code, resp.text[:200])
                return False
            return bool(resp.json().get("ok"))
        except Exception as exc:  # noqa: BLE001
            log.error("telegram send failed: %s", exc)
            return False
