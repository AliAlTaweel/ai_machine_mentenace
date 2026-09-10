import json

import pytest
from pydantic import BaseModel

from backend.llm.ollama_client import OllamaClient
from backend.llm.claude_client import ClaudeClient


class Person(BaseModel):
    name: str
    age: int


class FakeOllamaMessage:
    def __init__(self, content):
        self.content = content


class FakeOllamaResponse:
    def __init__(self, content):
        self.message = FakeOllamaMessage(content)


def test_ollama_generate_returns_message_content(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    monkeypatch.setattr(
        client._client, "chat", lambda **kwargs: FakeOllamaResponse("hello there")
    )
    assert client.generate("hi") == "hello there"


def test_ollama_generate_structured_parses_json(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return FakeOllamaResponse(json.dumps({"name": "Ada", "age": 30}))

    monkeypatch.setattr(client._client, "chat", fake_chat)
    result = client.generate_structured("describe a person", Person)
    assert result == Person(name="Ada", age=30)
    assert calls[0]["format"] == Person.model_json_schema()


def test_ollama_generate_structured_retries_once_on_bad_json(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    responses = [
        FakeOllamaResponse("not json"),
        FakeOllamaResponse(json.dumps({"name": "Ada", "age": 30})),
    ]

    def fake_chat(**kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client._client, "chat", fake_chat)
    result = client.generate_structured("describe a person", Person)
    assert result == Person(name="Ada", age=30)


def test_ollama_generate_structured_raises_after_second_failure(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    monkeypatch.setattr(
        client._client, "chat", lambda **kwargs: FakeOllamaResponse("still not json")
    )
    with pytest.raises(json.JSONDecodeError):
        client.generate_structured("describe a person", Person)


class FakeClaudeTextBlock:
    def __init__(self, text):
        self.text = text


class FakeClaudeMessage:
    def __init__(self, text):
        self.content = [FakeClaudeTextBlock(text)]


class FakeClaudeParsedMessage:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


def test_claude_generate_returns_first_text_block(monkeypatch):
    client = ClaudeClient(model="claude-sonnet-5", api_key="test-key")
    monkeypatch.setattr(
        client._client.messages, "create", lambda **kwargs: FakeClaudeMessage("hi back")
    )
    assert client.generate("hi") == "hi back"


def test_claude_generate_structured_returns_parsed_output(monkeypatch):
    client = ClaudeClient(model="claude-sonnet-5", api_key="test-key")
    expected = Person(name="Ada", age=30)
    monkeypatch.setattr(
        client._client.beta.messages,
        "parse",
        lambda **kwargs: FakeClaudeParsedMessage(expected),
    )
    result = client.generate_structured("describe a person", Person)
    assert result == expected


def test_claude_generate_structured_retries_once_when_parsed_output_is_none(monkeypatch):
    """The SDK can return parsed_output=None (refusal/truncation) without
    raising. That must trigger the same retry-once behaviour as a schema
    validation failure, not silently return None to the caller."""
    client = ClaudeClient(model="claude-sonnet-5", api_key="test-key")
    expected = Person(name="Ada", age=30)
    responses = [
        FakeClaudeParsedMessage(None),
        FakeClaudeParsedMessage(expected),
    ]

    def fake_parse(**kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client._client.beta.messages, "parse", fake_parse)
    result = client.generate_structured("describe a person", Person)
    assert result == expected


def test_claude_generate_structured_raises_clear_error_after_second_none(monkeypatch):
    client = ClaudeClient(model="claude-sonnet-5", api_key="test-key")
    monkeypatch.setattr(
        client._client.beta.messages,
        "parse",
        lambda **kwargs: FakeClaudeParsedMessage(None),
    )
    with pytest.raises(ValueError):
        client.generate_structured("describe a person", Person)
