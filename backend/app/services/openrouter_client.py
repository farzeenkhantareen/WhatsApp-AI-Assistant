"""Async OpenRouter client with retries, tools, and multimodal support."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class OpenRouterError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _should_retry_openrouter(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, OpenRouterError):
        if exc.status_code is None:
            return True
        return exc.status_code == 429 or exc.status_code >= 500
    return False


class OpenRouterClient:
    """Chat completions against OpenRouter (OpenAI-compatible)."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.openrouter_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self.settings.openrouter_site_url,
                    "X-Title": self.settings.openrouter_app_name,
                },
                timeout=httpx.Timeout(120.0, connect=15.0),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception(_should_retry_openrouter),
    )
    async def chat_completion(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str | dict] = None,
    ) -> Dict[str, Any]:
        await self.start()
        assert self._client is not None

        payload: Dict[str, Any] = {
            "model": model or self.settings.openrouter_model,
            "messages": list(messages),
            "temperature": (
                self.settings.openrouter_temperature if temperature is None else temperature
            ),
            "max_tokens": max_tokens or self.settings.openrouter_max_tokens,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        response = await self._client.post("/chat/completions", json=payload)
        if response.status_code >= 400:
            body: Any
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                body = response.text
            raise OpenRouterError(
                f"OpenRouter error {response.status_code}",
                status_code=response.status_code,
                body=body,
            )

        data = response.json()
        logger.info(
            "OpenRouter completion model=%s usage=%s",
            payload["model"],
            data.get("usage"),
        )
        return data

    async def complete_text(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        data = await self.chat_completion(
            messages, model=model, temperature=temperature
        )
        return extract_assistant_text(data)

    async def complete_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_rounds: Optional[int] = None,
    ) -> str:
        """Run a tool-calling loop until the model returns a final message."""
        settings = self.settings
        rounds = max_rounds or settings.max_tool_rounds
        working = list(messages)

        for _ in range(rounds):
            data = await self.chat_completion(
                working,
                model=model,
                temperature=temperature,
                tools=tools,
                tool_choice="auto",
            )
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return extract_assistant_text(data)

            working.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                result = await tool_executor(name, args or {})
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": result if isinstance(result, str) else json.dumps(result),
                    }
                )

        # Final pass without tools if still looping
        return await self.complete_text(working, model=model, temperature=temperature)

    async def describe_image(
        self,
        prompt: str,
        image_url_or_data_uri: str,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
    ) -> str:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            messages.extend(history)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "Describe this image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url_or_data_uri},
                    },
                ],
            }
        )
        return await self.complete_text(
            messages, model=self.settings.openrouter_vision_model
        )

    async def transcribe_audio_data_uri(
        self,
        data_uri: str,
        *,
        hint: str = "Transcribe the spoken content of this audio. Reply with text only.",
    ) -> str:
        """Best-effort audio transcription via multimodal chat models."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": hint},
                    {"type": "input_audio", "input_audio": {"data": data_uri, "format": "wav"}},
                ],
            }
        ]
        try:
            return await self.complete_text(
                messages, model=self.settings.openrouter_audio_model
            )
        except OpenRouterError:
            # Fallback: some models prefer image_url-style data URIs for audio unsupported
            logger.warning("Audio model failed; trying vision model with text fallback hint")
            return (
                "[Voice message received but transcription is unavailable with current model. "
                "Please ask the user to type their message.]"
            )


def extract_assistant_text(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text") or "")
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p).strip()
    return ""


openrouter_client = OpenRouterClient()

# Default network timeout configuration
