from __future__ import annotations

from personal_knowledge.services.topic_projection import TopicProjectionService
from personal_knowledge.wiki.read_router import WikiReadRouter


class Reader:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        return self.result


class WikiStub:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, operation, **params):
        self.calls.append((operation, params))
        return self.result


def test_fresh_wiki_is_selected_without_fallback_calls():
    wiki = WikiStub({
        "ok": True, "status": "fresh", "generated_at": "now", "snapshot_bindings": {"personal": "ps"},
        "freshness": {"state": "fresh"}, "authorities": {"personal": "ok"}, "limitations": [],
        "projection_checksum": "pc", "data": {"topic": {"canonical_key": "project:alpha"}, "claims": {}},
    })
    structured, ku, evidence = Reader({"data": {"marker": "structured"}}), Reader({}), Reader({})
    result = WikiReadRouter(topic_service=wiki, structured_reader=structured, ku_reader=ku, evidence_reader=evidence).resolve(topic_key="project:alpha")
    assert result["ok"] is True
    assert result["data"]["selected_source"] == "fresh_wiki"
    assert structured.calls == ku.calls == evidence.calls == 0


def test_stale_wiki_falls_back_in_fixed_order_with_provenance():
    wiki = WikiStub({"ok": True, "status": "stale", "error": None, "data": {"old": "must-not-be-selected"}})
    calls = []

    def structured(**kwargs):
        calls.append("structured_authority")
        return None

    def ku(**kwargs):
        calls.append("active_ku_search")
        return {"data": {"marker": "ku"}, "snapshot_bindings": {"serving": "ss"}, "epistemic_label": "retrieved_observation"}

    def evidence(**kwargs):
        calls.append("raw_evidence")
        return {"data": {"marker": "evidence"}}

    result = WikiReadRouter(topic_service=wiki, structured_reader=structured, ku_reader=ku, evidence_reader=evidence).resolve(topic_key="project:alpha")
    assert result["data"]["selected_source"] == "active_ku_search"
    assert result["data"]["attempted_sources"] == ["wiki", "structured_authority", "active_ku_search"]
    assert result["data"]["fallback_reason"] == "snapshot_mismatch"
    assert calls == ["structured_authority", "active_ku_search"]
    assert "old" not in str(result)


def test_long_tail_bypasses_wiki_and_uses_fallback():
    wiki = WikiStub({"ok": True, "status": "fresh", "data": {"should": "not-call"}})
    structured = Reader({"data": {"marker": "structured"}})
    result = WikiReadRouter(topic_service=wiki, structured_reader=structured, ku_reader=Reader({}), evidence_reader=Reader({})).resolve(query="long tail question")
    assert result["data"]["selected_source"] == "structured_authority"
    assert wiki.calls == []
    assert result["data"]["fallback_reason"] == "long_tail_bypass"


def test_topic_service_exposes_resolve_operation_without_provider_path():
    router = WikiReadRouter(topic_service=object(), structured_reader=lambda **_: {"data": {"marker": "structured"}})
    service = TopicProjectionService(
        personal_reader=lambda *args, **kwargs: {"ok": True, "data": {}},
        decision_reader=lambda *args, **kwargs: {"ok": True, "data": {}},
        external_reader=lambda *args, **kwargs: {"ok": True, "data": {}},
        read_router=router,
    )
    result = service.invoke("topic.resolve", query="long tail")
    assert result["operation"] == "topic.resolve"
    assert result["data"]["selected_source"] == "structured_authority"
