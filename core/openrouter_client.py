"""
OpenRouter API client for Everlay.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import httpx

from core.config import get_settings
from core.exceptions import AgentModelError, AgentTimeoutError, ConfigurationError
from core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Chat message."""
    role: str
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API format."""
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


@dataclass
class ChatCompletionChunk:
    """Streaming chat completion chunk."""
    id: str
    model: str
    created: int
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None


@dataclass
class ChatCompletion:
    """Complete chat completion response."""
    id: str
    model: str
    created: int
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None
    raw: Optional[Dict[str, Any]] = None


class OpenRouterClient:
    """
    Async client for OpenRouter API.

    Supports both streaming and non-streaming completions.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        http_referer: Optional[str] = None,
        x_title: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        settings = get_settings()

        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.default_model = default_model or settings.openrouter_default_model
        self.http_referer = http_referer or settings.openrouter_http_referer
        self.x_title = x_title or settings.openrouter_x_title
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise ConfigurationError("OpenRouter API key is required")

        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            if self.http_referer:
                headers["HTTP-Referer"] = self.http_referer
            if self.x_title:
                headers["X-Title"] = self.x_title

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def _prepare_messages(
        self,
        messages: List[Union[Message, Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Convert messages to API format."""
        prepared = []
        for msg in messages:
            if isinstance(msg, Message):
                prepared.append(msg.to_dict())
            elif isinstance(msg, dict):
                prepared.append(msg)
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")
        return prepared

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = await self.client.request(method, url, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    logger.warning(f"Rate limited, waiting {retry_after}s (attempt {attempt + 1})")
                    await asyncio.sleep(retry_after)
                    continue

                # Handle server errors
                if 500 <= response.status_code < 600:
                    logger.warning(f"Server error {response.status_code} (attempt {attempt + 1})")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue

                response.raise_for_status()
                return response

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"Request timeout (attempt {attempt + 1})")
                await asyncio.sleep(1 * (attempt + 1))

            except httpx.RequestError as e:
                last_exception = e
                logger.warning(f"Request error: {e} (attempt {attempt + 1})")
                await asyncio.sleep(1 * (attempt + 1))

        raise AgentTimeoutError(f"Request failed after {self.max_retries} retries: {last_exception}")

    async def chat_completion(
        self,
        messages: List[Union[Message, Dict[str, Any]]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        stop: Optional[Union[str, List[str]]] = None,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Union[ChatCompletion, AsyncGenerator[ChatCompletionChunk, None]]:
        """
        Create a chat completion.

        Args:
            messages: List of messages
            model: Model to use (defaults to default_model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            frequency_penalty: Frequency penalty
            presence_penalty: Presence penalty
            stop: Stop sequences
            stream: Whether to stream the response
            tools: Available tools
            tool_choice: Tool choice strategy
            response_format: Response format (e.g., {"type": "json_object"})
            **kwargs: Additional parameters

        Returns:
            ChatCompletion or AsyncGenerator of ChatCompletionChunk
        """
        payload = {
            "model": model or self.default_model,
            "messages": self._prepare_messages(messages),
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stream": stream,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if stop is not None:
            payload["stop"] = stop if isinstance(stop, list) else [stop]

        if tools is not None:
            payload["tools"] = tools

        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        if response_format is not None:
            payload["response_format"] = response_format

        # Add any extra parameters
        payload.update(kwargs)

        logger.debug(f"Chat completion request: model={payload['model']}, stream={stream}")

        if stream:
            return self._stream_completion(payload)
        else:
            return await self._single_completion(payload)

    async def _single_completion(self, payload: Dict[str, Any]) -> ChatCompletion:
        """Execute non-streaming completion."""
        response = await self._request_with_retry("POST", "/chat/completions", json=payload)
        data = response.json()

        return ChatCompletion(
            id=data["id"],
            model=data["model"],
            created=data["created"],
            choices=data["choices"],
            usage=data.get("usage"),
            raw=data,
        )

    async def _stream_completion(
        self, payload: Dict[str, Any]
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Execute streaming completion."""
        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue

                if line.startswith("data: "):
                    line = line[6:]  # Remove "data: " prefix

                try:
                    data = json.loads(line)
                    yield ChatCompletionChunk(
                        id=data["id"],
                        model=data["model"],
                        created=data["created"],
                        choices=data["choices"],
                        usage=data.get("usage"),
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse stream chunk: {e}")
                    continue

    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        response = await self._request_with_retry("GET", "/models")
        data = response.json()
        return data.get("data", [])

    async def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get information about a specific model."""
        models = await self.list_models()
        for model in models:
            if model.get("id") == model_id:
                return model
        raise AgentModelError(f"Model not found: {model_id}")


# Global client instance
_client: Optional[OpenRouterClient] = None


def get_client() -> OpenRouterClient:
    """Get or create global client instance."""
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


async def close_client() -> None:
    """Close global client."""
    global _client
    if _client:
        await _client.close()
        _client = None