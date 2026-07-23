"""Async Evolution API client with retries."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config.settings import Settings, get_settings
from app.utils.phone import to_whatsapp_jid

logger = logging.getLogger(__name__)


class EvolutionError(Exception):
    """Raised when Evolution API returns an error response."""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _should_retry_evolution(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, EvolutionError):
        if exc.status_code is None:
            return True
        if exc.status_code == 429 or exc.status_code >= 500:
            return True
        return False
    return False


class EvolutionClient:
    """Thin HTTP wrapper around Evolution API v2 endpoints."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.evolution_url.rstrip("/")
        self.instance = self.settings.instance_name
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "apikey": self.settings.evolution_api_key,
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        await self.start()
        assert self._client is not None
        response = await self._client.request(method, path, json=json, params=params)
        if response.status_code >= 400:
            body: Any
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                body = response.text
            raise EvolutionError(
                f"Evolution {method} {path} failed ({response.status_code})",
                status_code=response.status_code,
                body=body,
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_should_retry_evolution),
    )
    async def request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        return await self._request(method, path, json=json, params=params)

    async def health(self) -> bool:
        try:
            await self.start()
            assert self._client is not None
            response = await self._client.get("/")
            return response.status_code < 500
        except Exception as exc:  # noqa: BLE001
            logger.warning("Evolution health check failed: %s", exc)
            return False

    async def fetch_instances(self) -> List[Dict[str, Any]]:
        data = await self.request_with_retry("GET", "/instance/fetchInstances")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("instance", [data]) if "instance" in data else [data]
        return []

    async def get_connection_state(self) -> Dict[str, Any]:
        try:
            return await self.request_with_retry(
                "GET", f"/instance/connectionState/{self.instance}"
            )
        except EvolutionError as exc:
            return {"state": "unknown", "error": str(exc), "body": exc.body}

    async def create_instance(self) -> Dict[str, Any]:
        payload = {
            "instanceName": self.instance,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": self.settings.webhook_url,
                "byEvents": False,
                "base64": True,
                "events": [
                    "MESSAGES_UPSERT",
                    "CONNECTION_UPDATE",
                    "QRCODE_UPDATED",
                ],
                "headers": {
                    "x-webhook-secret": self.settings.webhook_secret,
                },
            },
        }
        logger.info("Creating Evolution instance %s", self.instance)
        return await self.request_with_retry("POST", "/instance/create", json=payload)

    async def set_webhook(self) -> Any:
        payload = {
            "webhook": {
                "enabled": True,
                "url": self.settings.webhook_url,
                "byEvents": False,
                "base64": True,
                "events": [
                    "MESSAGES_UPSERT",
                    "CONNECTION_UPDATE",
                    "QRCODE_UPDATED",
                ],
                "headers": {
                    "x-webhook-secret": self.settings.webhook_secret,
                },
            }
        }
        # Evolution v2 has used both shapes; try nested then flat.
        try:
            return await self.request_with_retry(
                "POST", f"/webhook/set/{self.instance}", json=payload
            )
        except EvolutionError:
            flat = {
                "enabled": True,
                "url": self.settings.webhook_url,
                "webhookByEvents": False,
                "webhookBase64": True,
                "events": payload["webhook"]["events"],
                "headers": payload["webhook"]["headers"],
            }
            return await self.request_with_retry(
                "POST", f"/webhook/set/{self.instance}", json=flat
            )

    async def connect(self) -> Any:
        return await self.request_with_retry("GET", f"/instance/connect/{self.instance}")

    async def restart(self) -> Any:
        try:
            return await self.request_with_retry(
                "POST", f"/instance/restart/{self.instance}"
            )
        except EvolutionError:
            return await self.request_with_retry(
                "PUT", f"/instance/restart/{self.instance}"
            )

    async def ensure_instance(self) -> Dict[str, Any]:
        """Create instance if missing, ensure webhook, return connection state."""
        instances = []
        try:
            instances = await self.fetch_instances()
        except EvolutionError as exc:
            logger.warning("Could not fetch instances: %s", exc)

        names = set()
        for item in instances:
            if isinstance(item, dict):
                inst = item.get("instance") if isinstance(item.get("instance"), dict) else item
                name = (
                    (inst or {}).get("instanceName")
                    or (inst or {}).get("name")
                    or item.get("name")
                    or item.get("instanceName")
                )
                if name:
                    names.add(name)

        created = None
        if self.instance not in names and self.settings.auto_create_instance:
            try:
                created = await self.create_instance()
            except EvolutionError as exc:
                # Already exists race
                if exc.status_code not in {403, 409}:
                    logger.error("Instance create failed: %s %s", exc, exc.body)

        try:
            await self.set_webhook()
        except EvolutionError as exc:
            logger.warning("Webhook set failed: %s %s", exc, exc.body)

        state = await self.get_connection_state()
        return {"created": created, "state": state}

    async def send_text(self, phone: str, text: str) -> Any:
        payload = {
            "number": normalize_number(phone),
            "text": text,
        }
        return await self.request_with_retry(
            "POST", f"/message/sendText/{self.instance}", json=payload
        )

    async def send_media(
        self,
        phone: str,
        *,
        media_url: str,
        media_type: str = "image",
        caption: str = "",
        file_name: Optional[str] = None,
        mimetype: Optional[str] = None,
    ) -> Any:
        # Evolution sendMedia expects mediatype: image | video | document | audio
        mediatype = media_type if media_type != "pdf" else "document"
        payload: Dict[str, Any] = {
            "number": normalize_number(phone),
            "mediatype": mediatype,
            "media": media_url,
            "caption": caption or "",
        }
        if file_name:
            payload["fileName"] = file_name
        if mimetype:
            payload["mimetype"] = mimetype
        elif mediatype == "document":
            payload["mimetype"] = "application/pdf"
            payload["fileName"] = file_name or "document.pdf"
        return await self.request_with_retry(
            "POST", f"/message/sendMedia/{self.instance}", json=payload
        )

    async def send_presence(self, phone: str, presence: str = "composing") -> Any:
        """Send typing/recording presence. presence: composing | available | paused."""
        payload = {
            "number": normalize_number(phone),
            "presence": presence,
            "delay": 1200,
        }
        try:
            return await self.request_with_retry(
                "POST", f"/chat/sendPresence/{self.instance}", json=payload
            )
        except EvolutionError as exc:
            logger.debug("sendPresence failed (non-fatal): %s", exc)
            return None

    async def mark_as_read(self, remote_jid: str, message_id: str, from_me: bool = False) -> Any:
        payload = {
            "readMessages": [
                {
                    "remoteJid": remote_jid if "@" in remote_jid else to_whatsapp_jid(remote_jid),
                    "fromMe": from_me,
                    "id": message_id,
                }
            ]
        }
        try:
            return await self.request_with_retry(
                "POST", f"/chat/markMessageAsRead/{self.instance}", json=payload
            )
        except EvolutionError as exc:
            logger.debug("markMessageAsRead failed (non-fatal): %s", exc)
            return None

    async def get_base64_from_media_message(self, message_payload: dict) -> Optional[str]:
        """Ask Evolution to resolve media to base64."""
        payload = {"message": message_payload, "convertToMp4": False}
        try:
            data = await self.request_with_retry(
                "POST",
                f"/chat/getBase64FromMediaMessage/{self.instance}",
                json=payload,
            )
            if isinstance(data, dict):
                return data.get("base64") or data.get("data")
        except EvolutionError as exc:
            logger.warning("getBase64FromMediaMessage failed: %s", exc)
        return None


def normalize_number(phone: str) -> str:
    from app.utils.phone import normalize_phone

    return normalize_phone(phone)


# Shared singleton used by routers/services
evolution_client = EvolutionClient()
