from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "integration" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_import_pipeline as imp  # noqa: E402


def sample_export() -> list[dict]:
    return [
        {
            "id": "conv-1",
            "title": "导入测试",
            "create_time": 1782914400.0,
            "default_model_slug": "gpt-5.4",
            "mapping": {
                "n1": {
                    "message": {
                        "id": "msg-1",
                        "author": {"role": "user"},
                        "create_time": 1782914401.0,
                        "content": {"content_type": "text", "parts": ["请记录这条新增数据"]},
                    }
                },
                "n2": {
                    "message": {
                        "id": "msg-2",
                        "author": {"role": "assistant"},
                        "create_time": 1782914402.0,
                        "content": {"content_type": "text", "parts": ["已经记录"]},
                    }
                },
            },
        }
    ]


class ImportPipelineTests(unittest.TestCase):
    def test_gpt_conversations_sharded_filename_supported(self) -> None:
        self.assertTrue(imp.is_gpt_conversations_file(Path("conversations.json")))
        self.assertTrue(imp.is_gpt_conversations_file(Path("conversations-000.json")))
        self.assertFalse(imp.is_gpt_conversations_file(Path("conversation_asset_file_names.json")))

    def test_gpt_core_upsert_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "conversations-000.json"
            export_path.write_text(json.dumps(sample_export(), ensure_ascii=False), encoding="utf-8")
            con = sqlite3.connect(":memory:")
            imp.ensure_gpt_core_schema(con)

            first = imp.upsert_gpt_core(con, [export_path], dry_run=False)
            second = imp.upsert_gpt_core(con, [export_path], dry_run=False)

            self.assertEqual(first["gpt_conversations_inserted"], 1)
            self.assertEqual(first["gpt_messages_inserted"], 2)
            self.assertEqual(second["gpt_conversations_updated"], 1)
            self.assertEqual(second["gpt_messages_duplicate"], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
            con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
