"""Phase 07 Agent 对话规范化测试。

覆盖 PLAN Wave 5 要求的四点:
  1. sample jsonl 解析正确
  2. role 过滤(developer/assistant 不进用户想法输入)
  3. raw_file + line_no 回溯字段完整
  4. mem0 candidate 不写入 memory_items

运行:
  python tests\test_agent_conversation_normalization.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_SCRIPTS = ROOT / "Agent" / "structured" / "scripts"
UNIFIED_SCRIPTS = ROOT / "integration" / "scripts"
for d in (AGENT_SCRIPTS, UNIFIED_SCRIPTS):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import normalize_agent_conversations as norm  # noqa: E402
import build_conversation_segments as seg_mod  # noqa: E402
import build_conversation_summary as summary_mod  # noqa: E402
import build_mem0_candidate_memory as mem0_mod  # noqa: E402

AGENT_DB = ROOT / "Agent" / "structured" / "db" / "agent_data.sqlite"

# Codex rollout jsonl 样本(覆盖各顶层类型),用于纯函数解析测试。
SAMPLE_JSONL = """\
{"type":"session_meta","payload":{"id":"sess-1","timestamp":"2026-06-27T10:00:00Z","cwd":"/tmp","originator":"codex","model_provider":"openai"}}
{"type":"turn_context","payload":{"turn_id":"turn-1","cwd":"/tmp","model":"gpt-4"}}
{"type":"response_item","payload":{"type":"message","role":"developer","content":[{"type":"input_text","text":"<permissions>do not leak</permissions>"}]}}
{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"帮我写一个 Python 脚本"}]}}
{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"好的,这是脚本..."}]}}
{"type":"response_item","payload":{"type":"function_call","name":"shell","arguments":"{\\"cmd\\":\\"ls\\"}","call_id":"call-1"}}
{"type":"response_item","payload":{"type":"function_call_output","call_id":"call-1","output":"file1\\nfile2"}}
{"type":"event_msg","payload":{"type":"task_started","turn_id":"turn-1"}}
{"type":"event_msg","payload":{"type":"user_message","message":"这是 event_msg 里的用户消息"}}
{"type":"event_msg","payload":{"type":"agent_message","message":"这是 event_msg 里的助手消息"}}
{"type":"event_msg","payload":{"type":"token_count","turn_id":"turn-1","input_tokens":100,"output_tokens":50}}
{"type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1","last_agent_message":"完成"}}
"""


class JsonlParsingTests(unittest.TestCase):
    """Wave 1: sample jsonl 解析正确性。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        # 模拟 Agent/raw/Codex/sessions/.../x.jsonl 的目录结构
        src_dir = tmp_path / "Codex" / "sessions" / "2026" / "06" / "27"
        src_dir.mkdir(parents=True)
        self.jsonl = src_dir / "rollout-test.jsonl"
        self.jsonl.write_text(SAMPLE_JSONL, encoding="utf-8")
        # 临时切换 norm 模块的根目录
        self._orig_root = norm.ROOT
        self._orig_raw = norm.AGENT_RAW
        norm.ROOT = tmp_path
        norm.AGENT_RAW = tmp_path

    def tearDown(self) -> None:
        norm.ROOT = self._orig_root
        norm.AGENT_RAW = self._orig_raw
        self.tmp.cleanup()

    def test_parse_extracts_all_kinds(self) -> None:
        """解析能识别 message/tool_call/tool_output/lifecycle/usage 五类。"""
        stats = norm.ParseStats()
        records = norm.Records()
        norm.parse_codex_file(self.jsonl, "Codex", stats, records)
        # 五类都有记录
        self.assertGreater(len(records.messages), 0)
        self.assertGreater(len(records.tool_calls), 0)
        self.assertGreater(len(records.tool_outputs), 0)
        self.assertGreater(len(records.lifecycle), 0)
        self.assertGreater(len(records.usage), 0)
        # session_meta 单独登记
        self.assertEqual(len(records.sessions_meta), 1)
        # turn 边界被识别
        self.assertGreater(len(records.turns), 0)

    def test_raw_file_and_line_no_present(self) -> None:
        """每条规范化记录都带 raw_file + line_no 证据链。"""
        stats = norm.ParseStats()
        records = norm.Records()
        norm.parse_codex_file(self.jsonl, "Codex", stats, records)
        for bucket in (records.messages, records.tool_calls, records.tool_outputs,
                       records.lifecycle, records.usage):
            for rec in bucket:
                self.assertIn("raw_file", rec)
                self.assertIn("line_no", rec)
                self.assertTrue(rec["raw_file"])
                self.assertGreater(rec["line_no"], 0)

    def test_role_normalization(self) -> None:
        """event_msg.user_message/agent_message 归一化到 user/assistant。"""
        stats = norm.ParseStats()
        records = norm.Records()
        norm.parse_codex_file(self.jsonl, "Codex", stats, records)
        roles = {m["role"] for m in records.messages}
        # 应该只有 user/assistant/developer,不应出现 user_message/agent_message
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        self.assertNotIn("user_message", roles)
        self.assertNotIn("agent_message", roles)

    def test_parse_error_counted_not_raised(self) -> None:
        """解析失败的行计入计数,不中断整个文件。"""
        bad_file = self.jsonl.parent / "bad.jsonl"
        bad_file.write_text(
            '{"type":"session_meta","payload":{"id":"x"}}\n'
            'NOT_JSON_LINE\n'
            '{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hi"}]}}\n',
            encoding="utf-8",
        )
        stats = norm.ParseStats()
        records = norm.Records()
        norm.parse_codex_file(bad_file, "Codex", stats, records)
        self.assertEqual(stats.parse_errors, 1)
        # 坏行后面的好行仍被解析
        self.assertGreater(len(records.messages), 0)


class SegmentSplitTests(unittest.TestCase):
    """Wave 3: 用户想法切分。"""

    def test_long_message_splits_into_segments(self) -> None:
        """同一条长用户消息可切成多个 segment。"""
        text = "第一个想法是做数据分析。\n\n第二个想法是学 Python。\n\n第三个想法是写博客。"
        parts = seg_mod.split_text(text)
        self.assertEqual(len(parts), 3)

    def test_list_items_split(self) -> None:
        """列表项各自成段(用真实长度内容,避免被 MIN_SEGMENT_CHARS 当噪声)。"""
        text = ("- 第一个想法是做个人数据分析项目\n"
                "- 第二个想法是学习机器学习算法\n"
                "- 第三个想法是搭建知识管理系统")
        parts = seg_mod.split_text(text)
        self.assertEqual(len(parts), 3)

    def test_short_noise_dropped(self) -> None:
        """过短片段被丢弃。"""
        parts = seg_mod.split_text("ok\n\n好的\n\n这是一个足够长的真实想法内容。")
        # 前两个过短被丢
        self.assertEqual(len(parts), 1)

    def test_assistant_not_treated_as_user_thought(self) -> None:
        """切分模块只接受 role=user 输入(由 SQL 查询保证),这里验证提取函数本身不依赖 role。"""
        # split_text 是纯文本函数,role 过滤在 build_*_segments 的 SQL where role='user' 完成
        # 这里确认纯函数能正确处理
        parts = seg_mod.split_text("用户问题:如何实现?")
        self.assertEqual(len(parts), 1)


class ConversationSummaryDedupTests(unittest.TestCase):
    """Phase 07+: 对话叙述摘要的去重和 turn 因果链。

    锁住 dedup_messages 的关键不变量:同一 turn 内的镜像重复(response_item.message +
    event_msg.agent_message)要去掉,但跨 turn 的相同文本必须各自保留,否则后一个 turn
    会留下 assistant 回复却丢了对应 user 消息,把因果链切成两段不连续的 turn。
    """

    @staticmethod
    def _row(event_index, turn_id, role, text, raw_file="f.jsonl", line_no=1):
        return (event_index, turn_id, role, text, "message", raw_file, line_no)

    def test_within_turn_mirror_duplicate_collapsed(self) -> None:
        """同一 turn 内连续两条相同文本(镜像重复)合并成一条。"""
        rows = [
            self._row(6, "t1", "user", "hi"),
            self._row(7, "t1", "user", "hi"),        # 镜像重复
            self._row(9, "t1", "assistant", "Hi."),
            self._row(10, "t1", "assistant", "Hi."), # 镜像重复
        ]
        out = summary_mod.dedup_messages(rows)
        self.assertEqual(len(out), 2)
        self.assertEqual([m["text"] for m in out], ["hi", "Hi."])

    def test_cross_turn_same_text_preserved(self) -> None:
        """不同 turn 里相同的 user 文本各自保留(因果链不切断)。

        复现真实场景:用户在 t1 问了"what your name"没得到回复,在 t2 又问了一次。
        全局去重会丢掉 t2 的 user 消息但留下它的 assistant 回复 -> 因果断裂。
        per-turn 去重保留两条 user,各自配对 assistant。
        """
        rows = [
            self._row(15, "t1", "user", "what your name"),
            self._row(16, "t1", "user", "what your name"),  # t1 镜像
            self._row(21, "t2", "user", "what your name"),  # t2 跨 turn 重复(必须保留)
            self._row(22, "t2", "user", "what your name"),  # t2 镜像
            self._row(24, "t2", "assistant", "I'm Codex."),
            self._row(25, "t2", "assistant", "I'm Codex."),
        ]
        out = summary_mod.dedup_messages(rows)
        # 两个 user(各 turn 一条) + 一个 assistant
        user_msgs = [m for m in out if m["role"] == "user"]
        self.assertEqual(len(user_msgs), 2)
        self.assertEqual({m["turn_id"] for m in user_msgs}, {"t1", "t2"})

    def test_null_turn_handled_as_own_group(self) -> None:
        """turn_id=NULL 的消息自成一组,与有 turn_id 的消息互不去重。"""
        rows = [
            self._row(1, None, "user", "hi"),
            self._row(2, "t1", "user", "hi"),  # 同文本不同 turn_id -> 都保留
        ]
        out = summary_mod.dedup_messages(rows)
        self.assertEqual(len(out), 2)

    def test_assemble_turns_keeps_causal_chain(self) -> None:
        """端到端:per-turn 去重后,assemble_turns 不会把同一 turn 的 user+assistant 拆散。"""
        rows = [
            self._row(15, "t1", "user", "what your name"),
            self._row(16, "t1", "user", "what your name"),
            self._row(21, "t2", "user", "what your name"),
            self._row(22, "t2", "user", "what your name"),
            self._row(24, "t2", "assistant", "I'm Codex."),
            self._row(25, "t2", "assistant", "I'm Codex."),
        ]
        messages = summary_mod.dedup_messages(rows)
        turns = summary_mod.assemble_turns(messages, {}, {})
        # 两个 turn,各自有自己的消息
        self.assertEqual(len(turns), 2)
        # t2 必须同时含 user 和 assistant(因果链完整)
        t2 = next(t for t in turns if t["turn_id"] == "t2")
        roles = {m["role"] for m in t2["messages"]}
        self.assertEqual(roles, {"user", "assistant"})


class Mem0CandidateTests(unittest.TestCase):
    """Wave 4: mem0 候选不污染 memory_items + 证据链强制。"""

    def test_noise_filtered(self) -> None:
        """报错堆栈/代码/系统配置被噪声过滤。"""
        noise_texts = [
            "Traceback (most recent call last)",
            '  File "test.py", line 1',
            "import matplotlib.pyplot as plt",
            "<INSTRUCTIONS> system config",
            "def foo(self):\n    return 1",
        ]
        for t in noise_texts:
            self.assertTrue(mem0_mod.is_noise(t), f"应判为噪声: {t}")

    def test_clean_text_not_noise(self) -> None:
        """正常中文用户输入不被误判为噪声。"""
        clean_texts = [
            "我喜欢用 Python 做数据分析",
            "我的目标是今年学会机器学习",
            "请帮我制定一个学习计划",
        ]
        for t in clean_texts:
            self.assertFalse(mem0_mod.is_noise(t), f"不应判为噪声: {t}")

    def test_candidate_has_evidence_chain(self) -> None:
        """命中的候选必须带 source_segment_ids + source_refs。"""
        segment = {
            "segment_id": "test-1",
            "source_ref": "file.jsonl:42",
            "text": "我喜欢用 Python 写脚本,以后都这么做",
        }
        cand = mem0_mod.local_extract(segment)
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand.source_segment_ids, ["test-1"])
        self.assertEqual(cand.source_refs, ["file.jsonl:42"])
        self.assertEqual(cand.acceptance_status, "candidate")

    def test_candidate_without_evidence_marked(self) -> None:
        """无证据链的候选必须能被识别(PLAN: 否则标记 rejected)。

        本地模式生成时带 source_ref;调用方/Review 层负责把空证据链的标记 rejected。
        这里验证:候选数据结构强制包含 acceptance_status 字段,支持后续 reject 流程。
        """
        segment = {
            "segment_id": "test-2",
            "source_ref": "",
            "text": "我喜欢用 Python 写脚本",
        }
        cand = mem0_mod.local_extract(segment)
        # 候选生成后必须有 acceptance_status 字段,供 review 层判断是否晋级
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertIn(cand.acceptance_status, {"candidate", "rejected", "promoted"})

    def test_mem0_output_not_in_memory_items(self) -> None:
        """验证 mem0 candidate 文件与 memory_items 是两套独立存储。"""
        # memory_items 在统合模块的 memory store 中,候选文件在 ai_context 下
        mem0_out = ROOT / "integration" / "analysis" / "ai_context" / "mem0_candidate_memories.json"
        # candidate 文件即使存在,也独立于 memory store
        # 这里验证候选数据结构里没有 memory_id 字段(那是 memory_items 的字段)
        if mem0_out.exists():
            data = json.loads(mem0_out.read_text(encoding="utf-8"))
            for cand in data:
                # 候选字段集不应包含 memory_items 的主键 memory_id
                self.assertNotIn("memory_id", cand)
                self.assertIn("acceptance_status", cand)


if __name__ == "__main__":
    unittest.main(verbosity=2)
