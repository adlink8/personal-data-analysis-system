"""Phase P0-1: Codex usage extraction fix - RED to GREEN.

Fixes the codex adapter token_count branch (event_msg.payload.type ==
"token_count"): it previously always emitted a USAGE event with NO token data
(empty summary), which produced ~49,992 hollow USAGE events.

Real Codex exports carry token counts on these token_count records under
payload.info:

  {
    "type": "event_msg",
    "payload": {
      "type": "token_count",
      "info": {
        "total_token_usage": {"input_tokens": ..., "cached_input_tokens": ...,
                              "cache_write_input_tokens": ..., "output_tokens": ...},
        "last_token_usage":   { increments for this turn },
        "model_context_window": ...
      }
    }
  }

Contract for the token_count branch:

  a) when the record carries token data we map the incremental
     last_token_usage onto the machine-parseable summary grammar
     "input_tokens=X output_tokens=Y [cache_read=Z cache_write=W]" and keep the
     USAGE event;
  b) when no token data is present we degrade to UNKNOWN_NATIVE and never emit a
     hollow USAGE event.

Fixtures are synthetic real-shape records (fields nested under payload) so the
fix is exercised against the wire shape Codex writes.
"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from personal_knowledge.adapters.conversation_sources import codex
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.core.conversation_events import (
    EventKind,
)


def _adapted(tmp_path: Path, rows: list[dict]):
    """Write synthetic real-shape rows and adapt them through the seam."""
    src = tmp_path / "session.jsonl"
    text = "\n".join(json.dumps(row) for row in rows) + "\n"
    src.write_text(text, encoding="utf-8")
    artifact, blob = capture_file(
        src, tmp_path / "capture", relative_path=src.name,
        byte_limit=1_000_000, count_limit=1,
    )
    assert codex.detect(artifact, artifact_root=blob.parent)
    return codex.adapt(
        SourceArtifactSet(artifacts=(artifact,)), artifact_root=blob.parent
    )


_META = {
    "type": "session_meta",
    "payload": {"id": "sess_usage_01", "timestamp": "2026-08-13T10:00:00Z"},
}


def _token_count_record(*, total=None, last=None):
    """A real-shape event_msg token_count record, matching Codex wire format."""
    payload = {"type": "token_count"}
    info = {}
    if total is not None:
        info["total_token_usage"] = total
    if last is not None:
        info["last_token_usage"] = last
    info["model_context_window"] = 258400
    payload["info"] = info
    return {"type": "event_msg", "timestamp": "2026-08-13T10:01:00Z", "payload": payload}


def _usage_events(adapted):
    return [e for e in adapted.events if e.kind is EventKind.USAGE]


def _unknown_events(adapted):
    return [e for e in adapted.events if e.kind is EventKind.UNKNOWN_NATIVE]


class TestTokenCountUsageExtraction:
    def test_token_count_with_usage_emits_summary(self, tmp_path):
        record = _token_count_record(
            last={
                "input_tokens": 1234,
                "cached_input_tokens": 500,
                "cache_write_input_tokens": 20,
                "output_tokens": 88,
            }
        )
        adapted = _adapted(tmp_path, [_META, record])
        usage = _usage_events(adapted)
        assert len(usage) == 1
        summary = usage[0].summary or ""
        assert "input_tokens=1234" in summary
        assert "output_tokens=88" in summary

    def test_token_count_usage_summary_cache_fields(self, tmp_path):
        record = _token_count_record(
            last={
                "input_tokens": 100,
                "cached_input_tokens": 30,
                "cache_write_input_tokens": 7,
                "output_tokens": 50,
            }
        )
        adapted = _adapted(tmp_path, [_META, record])
        summary = _usage_events(adapted)[0].summary or ""
        assert "cache_read=30" in summary
        assert "cache_write=7" in summary

    def test_token_count_uses_last_token_usage_incremental(self, tmp_path):
        record = _token_count_record(
            total={"input_tokens": 99999, "output_tokens": 88888},
            last={"input_tokens": 42, "output_tokens": 7},
        )
        adapted = _adapted(tmp_path, [_META, record])
        usage = _usage_events(adapted)
        assert len(usage) == 1
        summary = usage[0].summary or ""
        assert "input_tokens=42 output_tokens=7" in summary

    def test_token_count_falls_back_to_total_when_no_last(self, tmp_path):
        record = _token_count_record(
            total={"input_tokens": 300, "cached_input_tokens": 10, "output_tokens": 45},
        )
        adapted = _adapted(tmp_path, [_META, record])
        usage = _usage_events(adapted)
        assert len(usage) == 1
        summary = usage[0].summary or ""
        assert "input_tokens=300" in summary
        assert "output_tokens=45" in summary

    def test_token_count_without_data_degrades_to_unknown(self, tmp_path):
        record = _token_count_record(total={}, last={})
        adapted = _adapted(tmp_path, [_META, record])
        assert not _usage_events(adapted)
        unknown = _unknown_events(adapted)
        assert len(unknown) == 1
        assert unknown[0].content is None
        assert unknown[0].summary is None

    def test_token_count_without_info_degrades_to_unknown(self, tmp_path):
        record = {"type": "event_msg", "timestamp": "2026-08-13T10:01:00Z",
                  "payload": {"type": "token_count"}}
        adapted = _adapted(tmp_path, [_META, record])
        assert not _usage_events(adapted)
        assert len(_unknown_events(adapted)) == 1

    def test_no_usage_when_fields_present_without_token_numbers(self, tmp_path):
        record = _token_count_record(last={"model_context_window": 1})
        adapted = _adapted(tmp_path, [_META, record])
        assert not _usage_events(adapted)

    def test_token_count_usage_kind_and_stream_position(self, tmp_path):
        record = _token_count_record(last={"input_tokens": 10, "output_tokens": 5})
        adapted = _adapted(tmp_path, [_META, record])
        usage = _usage_events(adapted)
        assert len(usage) == 1
        assert usage[0].kind is EventKind.USAGE
        kinds = [e.kind for e in adapted.events]
        assert kinds.index(EventKind.USAGE) >= 0
