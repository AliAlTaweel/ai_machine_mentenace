import pytest
from pydantic import BaseModel


class FakeLLMClient:
    """Test double for LLMClient: returns pre-scripted structured responses in order."""

    def __init__(self, structured_responses: list[BaseModel] | None = None, text_responses: list[str] | None = None):
        self._structured_responses = list(structured_responses or [])
        self._text_responses = list(text_responses or [])
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._text_responses.pop(0)

    def generate_structured(self, prompt: str, schema):
        self.prompts.append(prompt)
        return self._structured_responses.pop(0)


@pytest.fixture
def fake_llm():
    return FakeLLMClient
