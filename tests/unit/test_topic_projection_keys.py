import pytest

from personal_knowledge.services.topic_projection import (
    TopicKey,
    TopicProjectionError,
    WIKI_OPERATIONS,
    WIKI_REASON_CODES,
    WIKI_SCHEMA_VERSION,
    make_wiki_envelope,
    parse_topic_key,
    safe_reason_code,
)


@pytest.mark.parametrize(
    ("raw", "topic_type", "parts"),
    [
        ("project:work", "project", ("work",)),
        ("goal:health:personal:exercise", "goal", ("health", "personal", "exercise")),
        ("decision:rec-123", "decision", ("rec-123",)),
    ],
)
def test_valid_topic_keys_are_immutable_and_canonical(raw, topic_type, parts):
    key = parse_topic_key(raw)
    assert key == TopicKey(topic_type, parts)
    assert key.canonical == raw
    with pytest.raises((AttributeError, TypeError)):
        key.topic_type = "decision"


def test_url_decoding_happens_once_and_round_trips():
    assert parse_topic_key("project:工作%20区").canonical == "project:工作 区"
    assert parse_topic_key("goal:health:personal:exercise").canonical == "goal:health:personal:exercise"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "project:",
        "project:a:b",
        "goal:a:b",
        "goal:a:b:c:d",
        "decision:",
        "project:a:b:c",
        "project:a%3Ab",
        "project:a%252Fb",
        "project:a%2",
        "project:a%ZZ",
        "project:a/b",
        "project:a\\b",
        "project:a\n",
    ],
)
def test_malformed_or_ambiguous_keys_are_rejected(raw):
    with pytest.raises(TopicProjectionError) as exc_info:
        parse_topic_key(raw)
    assert exc_info.value.reason_code == "invalid_topic_key"
    assert str(exc_info.value) == "invalid_topic_key"


def test_unknown_topic_type_has_stable_reason_code():
    with pytest.raises(TopicProjectionError) as exc_info:
        parse_topic_key("note:abc")
    assert exc_info.value.reason_code == "unsupported_topic_type"


def test_operations_and_reason_codes_are_closed_vocabularies():
    assert WIKI_SCHEMA_VERSION == "personal_wiki_projection_v1"
    assert WIKI_OPERATIONS == {"topic.list", "topic.get", "topic.backlinks", "topic.resolve"}
    assert "authority_unavailable" in WIKI_REASON_CODES
    assert safe_reason_code("private-debug-detail") == "projection_partial"


def test_read_envelope_is_independent_and_stable():
    envelope = make_wiki_envelope(
        "topic.get",
        ok=True,
        data={"topic_key": "project:work"},
        snapshot_bindings={"project": "snap-1"},
        freshness={"project": "fresh"},
        authorities={"project": "ok"},
    )
    assert envelope["schema_version"] == WIKI_SCHEMA_VERSION
    assert envelope["operation"] == "topic.get"
    assert envelope["ok"] is True
    assert envelope["data"]["topic_key"] == "project:work"
    assert envelope["error"] is None


def test_failed_envelope_has_safe_error_only():
    envelope = make_wiki_envelope("topic.list", ok=False, partial=True)
    assert envelope["error"] == "projection_partial"
    with pytest.raises(ValueError):
        make_wiki_envelope("topic.delete", ok=True)
    with pytest.raises(ValueError):
        make_wiki_envelope("topic.get", ok=True, error="private-detail")
