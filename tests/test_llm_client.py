"""Tests for the LLM client JSON parsing."""

from legal_eagle.llm.client import _parse_json_lenient


def test_parse_strict_json() -> None:
    assert _parse_json_lenient('{"a": 1}') == {"a": 1}


def test_parse_stripped_code_fence() -> None:
    s = "```json\n{\"a\": 2}\n```"
    assert _parse_json_lenient(s) == {"a": 2}


def test_parse_extracts_from_prose() -> None:
    s = "Sure, here it is: {\"b\": 3} — hope that helps!"
    assert _parse_json_lenient(s) == {"b": 3}


def test_parse_returns_empty_on_garbage() -> None:
    assert _parse_json_lenient("not json at all") == {}
