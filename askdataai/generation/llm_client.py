"""
LLM Client - Wrapper for OpenAI-compatible API.

Used for:
- Intent classification
- SQL generation
- SQL correction

Config from .env: OPENAI_API_KEY, OPENAI_BASE_URL
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """
    OpenAI-compatible LLM client.

    Usage:
        client = LLMClient(api_key="...", base_url="https://models.github.ai/inference")
        response = client.chat("Translate this to SQL", system_prompt="You are a SQL expert")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4.1-mini",
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        logger.info(f"LLM client initialized: model={model}, base_url={base_url}")

    def chat(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        """
        Send a chat request and return the response text.

        Args:
            user_prompt: Question content.
            system_prompt: System instruction.
            temperature: Override temperature.
            max_tokens: Override max_tokens.
            response_format: JSON mode format.

        Returns:
            Response text from LLM.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""

        logger.debug(f"LLM response ({len(content)} chars)")
        return content

    def chat_stream(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """
        Stream tokens from LLM — yield each small text chunk.

        Used for Stage 11 (CoT Reasoning) and Stage 12 (SQL Generation)
        to display text in real-time like ChatGPT.

        Args:
            user_prompt: Question content.
            system_prompt: System instruction.
            temperature: Override temperature.
            max_tokens: Override max_tokens.

        Yields:
            str: Each text chunk (token) from LLM.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
            "stream": True,
        }

        total_chars = 0
        with self._client.chat.completions.create(**kwargs) as stream:
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    total_chars += len(delta)
                    yield delta

        logger.debug(f"LLM stream complete ({total_chars} chars)")

    def chat_json(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> dict:
        """
        Chat and parse response as JSON.

        Returns:
            Parsed JSON dict.
        """
        response = self.chat(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        # Clean response (LLM sometimes wraps in ```json...```)
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {cleaned[:200]}")
            return {"error": "JSON parse failed", "raw": cleaned}
