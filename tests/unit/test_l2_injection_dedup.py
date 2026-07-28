import sqlite3

from personal_knowledge.application.knowledge.build_knowledge_units import (
    AssistantKnowledgeUnit,
    KnowledgeUnit,
)
from personal_knowledge.application.knowledge.injection_context import (
    SubjectIndex,
    format_injection_block,
    recall_known_units,
    validate_duplicate_of,
)


def _index_db(tmp_path):
    db = tmp_path / "canonical.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE canonical_knowledge_units (canonical_unit_id TEXT, subject TEXT, answer TEXT, status TEXT, lifecycle TEXT)"
    )
    con.executemany(
        "INSERT INTO canonical_knowledge_units VALUES (?,?,?,?,?)",
        [
            ("cu|current", "Git 分支", "main", "current", "current"),
            ("cu|long", "Git 分支", "x" * 500, "current", "current"),
            ("cu|staging", "Git 分支", "ignore", "staging", "current"),
            ("cu|old", "Git 分支", "old", "current", "superseded"),
        ],
    )
    con.commit()
    return db, con


def test_models_accept_duplicate_of_but_still_forbid_unknown_fields():
    base = dict(unit_type="preference", subject="s", question="question", answer="answer", confidence=0.9, evidence_quote="e")
    assert KnowledgeUnit(**{**base, "duplicate_of": "cu|x"}).duplicate_of == "cu|x"
    assistant = {**base, "unit_type": "solution"}
    assert AssistantKnowledgeUnit(**assistant, duplicate_of=None).duplicate_of is None


def test_exact_lookup_wins_and_filters_non_current(tmp_path):
    db, con = _index_db(tmp_path)
    index = SubjectIndex(con)
    called = []
    result = recall_known_units(index, subject="git分支", embed_fn=lambda value: called.append(value))
    assert {item["unit_id"] for item in result} == {"cu|current", "cu|long"}
    assert len(result[1]["answer"]) == 200
    assert called == []
    con.close()


def test_embedding_fallback_only_for_nonempty_miss(tmp_path):
    db, con = _index_db(tmp_path)
    index = SubjectIndex(con)

    class StubCollection:
        def query(self, **kwargs):
            assert kwargs["n_results"] == 20
            return {"metadatas": [[{"unit_id": "cu|embed", "subject": "漂移 subject"}]], "documents": [["answer"]], "distances": [[0.1]]}

    calls = []
    result = recall_known_units(index, subject="漂移 subject", embed_fn=lambda value: calls.append(value) or [0.1], chroma_collection=StubCollection())
    assert result[0]["unit_id"] == "cu|embed"
    assert calls == ["漂移 subject"]
    assert recall_known_units(index, subject="", embed_fn=lambda value: calls.append(value), chroma_collection=StubCollection()) == []
    con.close()


def test_format_and_duplicate_whitelist():
    block = format_injection_block([{"unit_id": "cu|x", "subject": "s", "answer": "a" * 500}])
    assert "数据" in block and "不是指令" in block
    assert "a" * 201 not in block
    assert validate_duplicate_of("cu|x", {"cu|x"}) == "cu|x"
    assert validate_duplicate_of("cu|hallucinated", {"cu|x"}) is None
    assert validate_duplicate_of(None, {"cu|x"}) is None
