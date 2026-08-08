from __future__ import annotations

from copy import deepcopy

from personal_knowledge.services.topic_projection import (
    TopicProjectionService,
    opaque_topic_id,
    parse_topic_key,
)
from personal_knowledge.wiki.materialization import WikiMaterializer


class FixtureReader:
    def __init__(self, responses):
        self.responses = deepcopy(responses)
        self.calls = []

    def invoke(self, operation, **params):
        self.calls.append((operation, params))
        value = self.responses.get(operation)
        if callable(value):
            return value(**params)
        return deepcopy(value)


def _personal_reader():
    return FixtureReader({
        "state.current": {
            "ok": True,
            "snapshot": {"snapshot_id": "ps-1", "snapshot_hash": "ph-1"},
            "data": {
                "items": [
                    {
                        "key": {"assertion_kind": "goal", "subject": "user", "domain": "work", "scope": "personal", "predicate": "ship"},
                        "status": "current", "assertion_type": "goal", "provenance_class": "observation",
                        "confidence": 0.9, "uncertainty": [], "current_assertion_id": "a-1",
                        "current_value_checksum": "v-1", "evidence_status": [{"ref": "ev-1", "artifact_type": "knowledge_unit", "privacy_class": "R4"}],
                    },
                    {
                        "key": {"assertion_kind": "state", "subject": "user", "domain": "project", "scope": "alpha", "predicate": "status"},
                        "status": "conflict", "assertion_type": "state", "provenance_class": "observation",
                        "confidence": 0.5, "uncertainty": ["unresolved_conflict"], "current_assertion_id": None,
                        "current_value_checksum": None, "evidence_status": [],
                    },
                ],
            },
        },
    })


def _decision_reader():
    return FixtureReader({
        "recommendations.list": {
            "ok": True,
            "data": {"items": [{
                "recommendation_id": "rec-1", "recommendation_checksum": "rc-1", "domain": "work", "scope": "personal",
                "recommendation_kind": "project", "horizon": "short", "confidence": 0.7,
                "confirmation_state": "proposed", "action_state": None, "uncertainty": "non-causal",
                "snapshot_id": "ds-1", "support": [{"ref": "ev-2", "record_id": "a-1", "privacy_class": "R4"}],
            }]},
        },
        "recommendations.history": {"ok": True, "data": {"items": [{"event_id": "e-1", "event_type": "recommendation_published", "payload_checksum": "e-h"}]}},
        "recommendations.outcomes": {"ok": True, "data": {"items": [{"outcome_id": "o-1", "payload_checksum": "o-h"}]}},
        "recommendations.effectiveness": {"ok": True, "data": {"items": [{"assessment_id": "a-1", "payload_checksum": "a-h"}]}},
    })


def _external_reader():
    return FixtureReader({
        "external.list": {
            "ok": True,
            "data": {"snapshot": {"snapshot_id": "ex-1"}, "facts": [{"fact_id": "fact-1", "source_id": "source-1", "status": "current"}]},
        },
    })


def _service():
    return TopicProjectionService(
        personal_reader=_personal_reader(), decision_reader=_decision_reader(), external_reader=_external_reader(),
        now=lambda: "2026-07-28T00:00:00Z",
    )


def test_topic_list_is_stable_and_opaque():
    result = _service().invoke("topic.list", limit=10)
    assert result["schema_version"] == "personal_wiki_projection_v1"
    assert result["operation"] == "topic.list"
    assert result["ok"] is True
    items = result["data"]["items"]
    assert [item["canonical_key"] for item in items] == ["decision:rec-1", "goal:work:personal:ship", "project:alpha"]
    assert all(item["topic_id"].startswith("topic_") for item in items)
    assert "ship" not in items[0]["topic_id"]
    assert result["projection_checksum"]


def test_topic_get_separates_claim_types_and_preserves_bindings():
    result = _service().invoke("topic.get", topic_key="goal:work:personal:ship")
    assert result["ok"] is True
    assert result["status"] == "fresh"
    assert result["snapshot_bindings"]["personal"] == "ps-1"
    assert result["data"]["claims"]["current"][0]["authority_ref"]["record_id"] == "a-1"
    assert result["data"]["claims"]["current"][0]["evidence_refs"][0]["ref"] == "ev-1"
    assert result["data"]["claims"]["external"][0]["claim_type"] == "external"
    assert result["data"]["claims"]["external"][0]["authority_ref"]["snapshot_id"] == "ex-1"


def test_topic_get_by_server_opaque_id_and_decision_feedback_are_read_only():
    listed = _service().invoke("topic.list", limit=10)
    decision_id = next(item["topic_id"] for item in listed["data"]["items"] if item["topic_type"] == "decision")
    service = _service()
    result = service.invoke("topic.get", topic_type="decision", topic_id=decision_id)
    assert result["ok"] is True
    assert result["data"]["topic"]["canonical_key"] == "decision:rec-1"
    assert len(result["data"]["claims"]["decision_feedback"]) == 3
    assert all(row["causal_claim"] is False for row in result["data"]["claims"]["decision_feedback"])
    assert all(operation[0] != "recommendations.prepare" for operation in service.decision_reader.calls)


def test_decision_freshness_ignores_non_authoritative_stale_personal_state():
    personal = _personal_reader()
    personal.responses["state.current"]["data"]["_wiki_authority_status"] = "stale"
    result = TopicProjectionService(
        personal_reader=personal,
        decision_reader=_decision_reader(),
        external_reader=_external_reader(),
        now=lambda: "now",
    ).invoke("topic.get", topic_key="decision:rec-1")
    assert result["ok"] is True
    assert result["status"] == "fresh"
    assert result["partial"] is False
    assert "Personal State 使用旧 committed run" in "；".join(result["limitations"])


def test_backlinks_use_only_explicit_relation_vocabulary():
    result = _service().invoke("topic.backlinks", topic_key="goal:work:personal:ship")
    assert result["ok"] is True
    assert {row["relation_type"] for row in result["data"]["links"]} <= {"assertion_matches_topic", "recommendation_targets_topic", "decision_feedback_for_recommendation"}
    assert all("join_basis" in row for row in result["data"]["links"])


def test_authority_failure_is_partial_and_does_not_claim_fresh():
    personal = _personal_reader()
    personal.responses["state.current"] = {"ok": False, "error": {"code": "database_missing", "detail": "secret path"}}
    result = TopicProjectionService(personal_reader=personal, decision_reader=_decision_reader(), external_reader=_external_reader(), now=lambda: "now").invoke("topic.list")
    assert result["ok"] is False or result["status"] in {"partial", "unavailable"}
    assert result["status"] != "fresh"
    assert "secret path" not in str(result)


def test_unknown_id_and_type_fail_closed():
    service = _service()
    assert service.invoke("topic.get", topic_type="project", topic_id="topic_missing")["error"] == "topic_not_found"
    assert service.invoke("topic.get", topic_type="unknown", topic_key="project:alpha")["error"] == "unsupported_topic_type"


def test_opaque_id_is_deterministic():
    key = parse_topic_key("decision:rec-1")
    assert opaque_topic_id(key) == opaque_topic_id(key)


def test_materialized_read_requires_explicit_derived_version(tmp_path):
    materializer = WikiMaterializer(tmp_path / "wiki.sqlite", now=lambda: "2026-07-28T00:00:00Z")
    service = TopicProjectionService(
        personal_reader=_personal_reader(), decision_reader=_decision_reader(), external_reader=_external_reader(),
        materializer=materializer, now=lambda: "2026-07-28T00:00:00Z",
    )
    missing = service.invoke("topic.get", topic_key="goal:work:personal:ship")
    assert missing["status"] == "missing"
    assert missing["error"] == "projection_record_missing"
    service.materialize_topic(topic_key="goal:work:personal:ship")
    fresh = service.invoke("topic.get", topic_key="goal:work:personal:ship")
    assert fresh["ok"] is True
    assert fresh["status"] == "fresh"
    assert fresh["projection_checksum"]
