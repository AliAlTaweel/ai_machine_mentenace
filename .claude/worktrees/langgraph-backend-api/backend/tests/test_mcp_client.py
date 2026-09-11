import pytest

from backend.mcp_client import _parse_tool_result


class FakeTextContent:
    def __init__(self, text):
        self.text = text


class FakeCallToolResult:
    def __init__(self, content_text, is_error=False):
        self.content = [FakeTextContent(content_text)]
        self.isError = is_error


def test_parse_tool_result_returns_parsed_json():
    result = FakeCallToolResult('{"part_id": "BEARING-X4", "status": "in_stock"}')
    assert _parse_tool_result(result) == {"part_id": "BEARING-X4", "status": "in_stock"}


def test_parse_tool_result_raises_on_error():
    result = FakeCallToolResult("Unknown part_id: NOPE-1", is_error=True)
    with pytest.raises(RuntimeError, match="Unknown part_id: NOPE-1"):
        _parse_tool_result(result)
