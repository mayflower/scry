from __future__ import annotations

import json
import os
from typing import TypeVar

from browser_use.llm.base import BaseChatModel
from browser_use.llm.messages import (
    AssistantMessage,
    BaseMessage,
    SystemMessage,
    UserMessage,
)
from browser_use.llm.views import ChatInvokeCompletion


T = TypeVar("T")


class AnthropicChat(BaseChatModel):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set for AnthropicChat")

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def name(self) -> str:
        return f"Anthropic({self.model})"

    async def ainvoke(
        self, messages: list[BaseMessage], output_format: type[T] | None = None
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        # Build Anthropic call
        from anthropic import Anthropic

        client = Anthropic(api_key=self._api_key)

        system_parts: list[str] = []
        content_messages: list[dict[str, str]] = []
        for m in messages:
            if isinstance(m, SystemMessage):
                system_parts.append(str(m.content))
            elif isinstance(m, UserMessage):
                content_messages.append({"role": "user", "content": str(m.content)})
            elif isinstance(m, AssistantMessage):
                content_messages.append(
                    {"role": "assistant", "content": str(m.content)}
                )
            else:
                content_messages.append(
                    {"role": "user", "content": str(getattr(m, "content", ""))}
                )

        system_prompt = "\n\n".join(system_parts) if system_parts else None

        resp = client.messages.create(
            model=self.model,
            max_tokens=1200,
            temperature=0.2,
            system=system_prompt,
            messages=content_messages,
        )

        # Concatenate text blocks
        texts: list[str] = []
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                texts.append(getattr(block, "text", ""))
        text = "".join(texts)

        # If a structured output is requested, try to parse JSON into that pydantic model
        if output_format is not None:
            try:
                data = json.loads(text)
                completion = output_format.parse_obj(data)  # type: ignore[attr-defined]
            except Exception:
                completion = text  # type: ignore[assignment]
            return ChatInvokeCompletion(
                completion=completion, thinking=None, redacted_thinking=None, usage=None
            )

        return ChatInvokeCompletion(
            completion=text, thinking=None, redacted_thinking=None, usage=None
        )
