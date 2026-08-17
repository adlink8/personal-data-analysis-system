"""Phase 62 F12: shared timestamp normalization contract (RED -> GREEN).

The seam must turn every native timestamp shape family adapters hand us into
ONE canonical UTC ISO-8601 ``...Z`` shape, so ``ce_events`` and the
compatibility projection always see consistent timestamps (F12).
"""

from __future__ import annotations

from personal_knowledge.adapters.conversation_sources.time_utils import (
    _is_epoch_millis,
    normalize_timestamp,
)


class TestEpochMillisecondDetection:
    def test_int_millis_detected(self):
        assert _is_epoch_millis(1_775_638_723_463) is True

    def test_float_millis_detected(self):
        assert _is_epoch_millis(1775638723463.0) is True

    def test_digit_string_millis_detected(self):
        assert _is_epoch_millis("1775638723463") is True

    def test_epoch_seconds_not_detected(self):
        assert _is_epoch_millis(1_775_638_723) is False

    def test_bool_is_not_a_timestamp(self):
        assert _is_epoch_millis(True) is False

    def test_non_numeric_string_is_not_millis(self):
        assert _is_epoch_millis("2026-06-03T01:52:55.112+00:00") is False

    def test_none_is_not_millis(self):
        assert _is_epoch_millis(None) is False


class TestNormalizeTimestamp:
    def test_none_passthrough(self):
        assert normalize_timestamp(None) is None

    def test_int_epoch_millis_to_iso(self):
        # 1775638723463 ms = 2026-04-08T08:58:43.463Z
        assert normalize_timestamp(1_775_638_723_463) == "2026-04-08T08:58:43.463Z"

    def test_digit_string_epoch_millis_to_iso(self):
        assert normalize_timestamp("1775638723463") == "2026-04-08T08:58:43.463Z"

    def test_whole_second_millis(self):
        # 1775638800000 = 2026-04-08T09:00:00Z (no fractional part)
        assert normalize_timestamp(1_775_638_800_000) == "2026-04-08T09:00:00Z"

    def test_iso_with_z_passthrough(self):
        assert normalize_timestamp("2026-06-03T01:52:55.112Z") == "2026-06-03T01:52:55.112Z"

    def test_iso_with_offset_normalized_to_z(self):
        assert normalize_timestamp("2026-06-03T01:52:55.112000+00:00") == "2026-06-03T01:52:55.112Z"

    def test_iso_without_tz_assumed_utc(self):
        assert normalize_timestamp("2026-06-03T01:52:55") == "2026-06-03T01:52:55Z"

    def test_empty_string_becomes_none(self):
        assert normalize_timestamp("") is None
        assert normalize_timestamp("   ") is None

    def test_non_timestamp_value_preserved_verbatim(self):
        assert normalize_timestamp("t2") == "t2"
        assert normalize_timestamp(123) == "123"

    def test_offset_iso_with_offset_not_utc(self):
        # +08:00 must shift back to UTC
        out = normalize_timestamp("2026-06-03T09:38:43+08:00")
        assert out == "2026-06-03T01:38:43Z", out

