"""Owner alerts via Telegram Bot API. Failures are logged, never raised into business flows."""
import logging

import httpx

from app.config import Settings

log = logging.getLogger("ada.telegram")


class TelegramNotifier:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._token = settings.telegram_bot_token.get_secret_value()
        self._chat_id = settings.telegram_chat_id
        self._client = client or httpx.Client(timeout=10)

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> bool:
        """Send a plain-text message. Returns True on delivery."""
        if not self.enabled:
            log.info("Telegram disabled; alert not sent: %s", text)
            return False
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            r = self._client.post(url, json={"chat_id": self._chat_id, "text": text[:4096]})
            r.raise_for_status()
            return bool(r.json().get("ok"))
        except httpx.HTTPError as exc:
            # Never log the URL: it contains the bot token.
            log.warning("Telegram delivery failed: %s", type(exc).__name__)
            return False
