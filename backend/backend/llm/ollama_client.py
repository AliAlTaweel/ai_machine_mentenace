import json

import ollama
import pydantic

from backend.llm.base import LLMClient, T


class OllamaClient(LLMClient):
    def __init__(self, model: str = "gemma3:4b", host: str | None = None):
        self._model = model
        self._client = ollama.Client(host=host) if host else ollama.Client()

    def generate(self, prompt: str) -> str:
        response = self._client.chat(
            model=self._model, messages=[{"role": "user", "content": prompt}]
        )
        return response.message.content

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        try:
            return self._generate_structured_once(prompt, schema)
        except (json.JSONDecodeError, pydantic.ValidationError):
            retry_prompt = (
                f"{prompt}\n\nYour previous response was not valid JSON matching the "
                "required schema. Respond with ONLY valid JSON matching the schema."
            )
            return self._generate_structured_once(retry_prompt, schema)

    def _generate_structured_once(self, prompt: str, schema: type[T]) -> T:
        response = self._client.chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            format=schema.model_json_schema(),
        )
        data = json.loads(response.message.content)
        return schema.model_validate(data)
