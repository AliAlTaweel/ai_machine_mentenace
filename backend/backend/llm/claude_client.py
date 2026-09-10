import json

import anthropic
import pydantic

from backend.llm.base import LLMClient, T


class ClaudeClient(LLMClient):
    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        try:
            return self._generate_structured_once(prompt, schema)
        except (json.JSONDecodeError, pydantic.ValidationError, ValueError):
            retry_prompt = (
                f"{prompt}\n\nYour previous response did not match the required schema. "
                "Respond with output matching the schema exactly."
            )
            return self._generate_structured_once(retry_prompt, schema)

    def _generate_structured_once(self, prompt: str, schema: type[T]) -> T:
        result = self._client.beta.messages.parse(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        if result.parsed_output is None:
            # The SDK can return a message with parsed_output=None (refusal,
            # max_tokens truncation, etc.) without raising — treat that the
            # same as a schema-validation failure so the retry-once wrapper
            # kicks in instead of returning None to the caller.
            raise ValueError("model returned no parsable structured output")
        return result.parsed_output
