"""Phase 62-02: shared JSONL stream parsing primitives (contract tests).

Covers :func:`personal_knowledge.adapters.conversation_sources.jsonl_stream.iter_jsonl_lines`
fail-closed behaviour:

  - one JSON object per line, parsed in order
  - corrupt / non-JSON lines raise by default (strict=True) or are skipped
    when strict=False
  - ``max_entries`` / ``max_bytes`` limits fail closed with a typed exception
  - empty input yields nothing

All fixtures are synthetic ``tmp_path`` files; no real conversation data is
touched.
"""

from __future__ import annotations

import json

import pytest

from personal_knowledge.adapters.conversation_sources.jsonl_stream import (
    JSONLLineError,
    JSONLLimitExceeded,
    iter_jsonl_lines,
)


def _write(path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parses_each_json_object_line_in_order(tmp_path):
    path = tmp_path / "conversation.jsonl"
    rows = [
        {"seq": 1, "role": "user", "text": "hello"},
        {"seq": 2, "role": "assistant", "text": "hi"},
        {"seq": 3, "role": "user", "text": "bye"},
    ]
    _write(path, [json.dumps(r, ensure_ascii=False) for r in rows])

    assert list(iter_jsonl_lines(path)) == rows


def test_empty_file_yields_nothing(tmp_path):
    path = tmp_path / "empty.jsonl"
    _write(path, [])

    assert list(iter_jsonl_lines(path)) == []


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "blanky.jsonl"
    _write(path, ['{"a": 1}', "", "   ", '{"b": 2}'])

    assert list(iter_jsonl_lines(path)) == [{"a": 1}, {"b": 2}]


def test_corrupt_line_raises_by_default_with_line_number(tmp_path):
    path = tmp_path / "corrupt.jsonl"
    _write(path, ['{"seq": 1}', "this is not json", '{"seq": 3}'])

    with pytest.raises(JSONLLineError) as excinfo:
        list(iter_jsonl_lines(path))

    assert "line 2" in str(excinfo.value)


def test_corrupt_line_skipped_when_strict_false(tmp_path):
    path = tmp_path / "corrupt.jsonl"
    _write(path, ['{"seq": 1}', "not json", '{"seq": 3}'])

    assert list(iter_jsonl_lines(path, strict=False)) == [{"seq": 1}, {"seq": 3}]


def test_max_entries_exceeded_raises(tmp_path):
    path = tmp_path / "too_many.jsonl"
    _write(path, ['{"seq": %d}' % i for i in range(3)])

    with pytest.raises(JSONLLimitExceeded):
        list(iter_jsonl_lines(path, max_entries=2))


def test_max_entries_exact_count_is_allowed(tmp_path):
    path = tmp_path / "exact.jsonl"
    _write(path, ['{"seq": %d}' % i for i in range(2)])

    assert len(list(iter_jsonl_lines(path, max_entries=2))) == 2


def test_max_bytes_exceeded_raises_before_parsing(tmp_path):
    path = tmp_path / "big.jsonl"
    _write(path, ['{"seq": %d}' % i for i in range(10)])

    with pytest.raises(JSONLLimitExceeded):
        list(iter_jsonl_lines(path, max_bytes=10))


def test_max_bytes_larger_than_file_is_allowed(tmp_path):
    path = tmp_path / "small.jsonl"
    _write(path, ['{"seq": 1}'])

    assert list(iter_jsonl_lines(path, max_bytes=10**6)) == [{"seq": 1}]
