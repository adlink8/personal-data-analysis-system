from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import personal_knowledge.services.api_server as api_server
from personal_knowledge.services.api_server import Handler, topic_rest_contract
from personal_knowledge.services.topic_projection import TopicProjectionService


class Reader:
    def __init__(self, data):
        self.data = data

    def invoke(self, operation, **params):
        return self.data.get(operation, {"ok": True, "data": {}})


def service_fixture() -> TopicProjectionService:
    return TopicProjectionService(
        personal_reader=Reader({
            "state.current": {"ok": True, "snapshot": {"snapshot_id": "ps"}, "data": {"items": [{
                "key": {"assertion_kind": "goal", "subject": "user", "domain": "work", "scope": "personal", "predicate": "ship"},
                "status": "current", "assertion_type": "goal", "provenance_class": "observation", "confidence": 0.9,
                "uncertainty": [], "current_assertion_id": "a1", "current_value_checksum": "c1", "evidence_status": [],
            }]}},
        }),
        decision_reader=Reader({"recommendations.list": {"ok": True, "data": {"items": []}}}),
        external_reader=Reader({"external.list": {"ok": True, "data": {"snapshot": {"snapshot_id": "ex"}, "facts": []}}}),
        now=lambda: "2026-07-28T00:00:00Z",
    )


def _request(server, method, path):
    host, port = server.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()


def test_direct_topic_transport_preserves_schema_and_operation():
    service = service_fixture()
    result = topic_rest_contract("topic.list", {"limit": "10"}, service=service)
    assert result["schema_version"] == "personal_wiki_projection_v1"
    assert result["operation"] == "topic.list"
    assert result["data"]["items"][0]["topic_type"] == "goal"


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setattr(api_server, "TopicProjectionService", lambda **_: service_fixture())
    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_get_only_topic_routes_and_typed_bad_id(server):
    status, payload = _request(server, "GET", "/ui/topics?limit=10")
    assert status == 200
    assert payload["schema_version"] == "personal_wiki_projection_v1"
    topic_id = payload["data"]["items"][0]["topic_id"]
    status, payload = _request(server, "GET", f"/ui/topic?topic_type=goal&topic_id={topic_id}")
    assert status == 200
    assert payload["operation"] == "topic.get"
    status, payload = _request(server, "GET", "/ui/topic?topic_type=goal&topic_id=topic_missing")
    assert status == 404
    assert payload["error"] == "topic_not_found"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_non_get_topic_routes_are_rejected_without_service_use(server, method):
    status, payload = _request(server, method, "/ui/topics")
    assert status == 405
    assert payload["error"]["code"] == "method_not_allowed"
