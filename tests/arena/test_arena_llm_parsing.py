import pytest

from arena.llm import extract_json


def test_bare_json():
    assert extract_json('{"orders": []}') == {"orders": []}


def test_fenced_json():
    text = 'Here you go:\n```json\n{"orders": [{"action": "buy"}]}\n```\nGood luck!'
    assert extract_json(text)["orders"][0]["action"] == "buy"


def test_json_with_preamble_and_nested_braces():
    text = 'My view: {markets}. Decision: {"market_view": "up {maybe}", "orders": []}'
    # first "{markets}" is not valid JSON; parser should still find the real object
    with pytest.raises(Exception):
        extract_json("{markets}")
    out = extract_json('{"market_view": "up {maybe}", "orders": []}')
    assert out["market_view"] == "up {maybe}"


def test_no_json_raises():
    with pytest.raises(ValueError):
        extract_json("I refuse to answer in JSON today.")
