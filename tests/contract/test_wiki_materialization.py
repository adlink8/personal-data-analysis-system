from __future__ import annotations

import sqlite3

import pytest

from personal_knowledge.services.topic_projection import TopicKey
from personal_knowledge.wiki.derived_store import connect_ro, connect_rw, latest_version
from personal_knowledge.wiki.materialization import (
    WikiMaterializer,
    classify_dependencies,
    dependency_manifest_checksum,
    projection_checksum,
)
from personal_knowledge.wiki.derived_store import ProjectionDependency


def dep(authority, stable_ref, *, version="v1", checksum="c1", sequence=1, essential=True):
    return ProjectionDependency(authority, stable_ref, version, checksum, sequence, essential, f"{authority}:{stable_ref}")


def test_derived_schema_has_only_metadata_columns(tmp_path):
    path = tmp_path / "personal_wiki_projection.sqlite"
    con = connect_rw(path)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"wiki_projection_versions", "wiki_projection_dependencies", "wiki_projection_invalidations"} <= tables
        columns = {row[1] for row in con.execute("PRAGMA table_info(wiki_projection_versions)")}
        forbidden = {"content", "raw_message", "embedding", "provider_response", "evidence_body"}
        assert columns.isdisjoint(forbidden)
    finally:
        con.close()


def test_materialization_is_immutable_and_ro_cannot_write(tmp_path):
    path = tmp_path / "wiki.sqlite"
    materializer = WikiMaterializer(path, now=lambda: "2026-07-28T00:00:00Z")
    key = TopicKey("project", ("alpha",))
    version = materializer.materialize(key, snapshot_bindings={"personal": "ps"}, dependencies=[dep("personal", "ps")])
    assert version.projection_version == "pv_1"
    with pytest.raises(ValueError, match="projection_version_immutable"):
        materializer.materialize(key, snapshot_bindings={"personal": "ps"}, dependencies=[dep("personal", "ps")], projection_version="pv_1")
    ro = connect_ro(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("INSERT INTO wiki_projection_versions VALUES ('x','project','x','x','x','x','fresh','[]','{}','x')")
    finally:
        ro.close()


def test_manifest_and_projection_checksum_ignore_order_and_time():
    deps = [dep("decision", "d", sequence=2), dep("personal", "p")]
    reversed_deps = list(reversed(deps))
    assert dependency_manifest_checksum(deps) == dependency_manifest_checksum(reversed_deps)
    assert projection_checksum(topic_id="topic_a", topic_type="project", snapshot_bindings={"personal": "ps"}, dependencies=deps, source_refs={"a": "ref"}) == projection_checksum(topic_id="topic_a", topic_type="project", snapshot_bindings={"personal": "ps"}, dependencies=reversed_deps, source_refs={"a": "ref"})


def test_only_changed_dependency_is_stale_and_unrelated_topic_stays_fresh(tmp_path):
    materializer = WikiMaterializer(tmp_path / "wiki.sqlite", now=lambda: "same-time")
    alpha = TopicKey("project", ("alpha",))
    beta = TopicKey("project", ("beta",))
    alpha_dep = dep("personal", "alpha", checksum="a1")
    beta_dep = dep("personal", "beta", checksum="b1")
    materializer.materialize(alpha, snapshot_bindings={}, dependencies=[alpha_dep])
    materializer.materialize(beta, snapshot_bindings={}, dependencies=[beta_dep])
    alpha_status = materializer.validate_latest(alpha, [dep("personal", "alpha", checksum="a2")])
    beta_status = materializer.validate_latest(beta, [beta_dep])
    assert alpha_status["status"] == "stale"
    assert "personal_snapshot_changed" in alpha_status["reason_codes"]
    assert beta_status["status"] == "fresh"


def test_persisted_stale_status_is_not_promoted_to_fresh(tmp_path):
    materializer = WikiMaterializer(tmp_path / "wiki.sqlite")
    key = TopicKey("project", ("alpha",))
    dependency = dep("personal", "alpha")
    materializer.materialize(
        key,
        snapshot_bindings={},
        dependencies=[dependency],
        freshness_status="stale",
        reason_codes=["serving_snapshot_changed"],
    )
    verdict = materializer.validate_latest(key, [dependency])
    assert verdict["status"] == "stale"
    assert verdict["reason_codes"] == ("serving_snapshot_changed",)


def test_nonessential_change_is_partial_and_missing_is_unavailable_or_stale():
    captured = [dep("personal", "p"), dep("external", "e", checksum="e1", essential=False)]
    current = [dep("personal", "p"), dep("external", "e", checksum="e2", essential=False)]
    verdict = classify_dependencies(captured, current)
    assert verdict["status"] == "partial"
    missing = classify_dependencies([dep("personal", "p")], [])
    assert missing["status"] == "stale"
    assert missing["reason_codes"] == ("dependency_missing",)


def test_deleted_derived_store_rebuilds_from_same_metadata(tmp_path):
    path = tmp_path / "wiki.sqlite"
    key = TopicKey("goal", ("work", "personal", "ship"))
    deps = [dep("personal", "ps"), dep("decision", "rec", checksum="r1")]
    first = WikiMaterializer(path, now=lambda: "2026-07-28T00:00:00Z").materialize(key, snapshot_bindings={"personal": "ps"}, dependencies=deps, source_refs={"section": "metadata"})
    path.unlink()
    rebuilt = WikiMaterializer(path, now=lambda: "2026-07-29T00:00:00Z").materialize(key, snapshot_bindings={"personal": "ps"}, dependencies=deps, source_refs={"section": "metadata"})
    assert first.projection_checksum == rebuilt.projection_checksum
    assert first.dependency_manifest_checksum == rebuilt.dependency_manifest_checksum
    latest, _ = latest_version(path, first.topic_id)
    assert latest is not None
    assert latest.projection_version == "pv_1"
