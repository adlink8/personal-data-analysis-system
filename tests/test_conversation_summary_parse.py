"""Wave 8.2.1 / 8.2.3 单元测试。

覆盖:
  - 8.2.3: parse_turn_summaries 的 4 类 LLM 输出(标准/加粗/标题/合并叙述)
  - 8.2.1: summarize_chunk 段数校验 + 重试(段数不匹配触发重试,匹配则接受)

运行:
  python tests\test_conversation_summary_parse.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
UNIFIED_SCRIPTS = ROOT / "统合模块" / "脚本"
if str(UNIFIED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SCRIPTS))

import build_conversation_summary as mod  # noqa: E402


class TestParseTurnSummaries(unittest.TestCase):
    """Wave 8.2.3:正则加固,4 类 LLM 输出全部正确切分。"""

    def test_standard_format(self):
        """标准 `Turn N:` 格式。"""
        raw = "Turn 1: 用户问a\n\nTurn 2: 助手答b\n\nTurn 3: 结束c"
        parts = mod.parse_turn_summaries(raw, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "用户问a")
        self.assertEqual(parts[1], "助手答b")
        self.assertEqual(parts[2], "结束c")

    def test_bold_format(self):
        """加粗 `**Turn N:**` 格式(MiMo 高频出现,旧正则会切成 `**`)。"""
        raw = "**Turn 1:** 用户问a\n\n**Turn 2:** 助手答b"
        parts = mod.parse_turn_summaries(raw, 2)
        self.assertEqual(len(parts), 2)
        self.assertNotIn("**", parts[0])  # 不残留装饰符
        self.assertNotIn("**", parts[1])
        self.assertEqual(parts[0], "用户问a")

    def test_heading_format(self):
        """标题 `### Turn N` 格式。"""
        raw = "### Turn 1\n用户问a\n\n### Turn 2\n助手答b"
        parts = mod.parse_turn_summaries(raw, 2)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "用户问a")

    def test_merged_inline_two(self):
        """合并叙述:两个 turn 塞进一段,需二次拆分。"""
        raw = "Turn 1: 用户问a Turn 2: 助手答b\n\nTurn 3: 结束c"
        parts = mod.parse_turn_summaries(raw, 3)
        self.assertEqual(len(parts), 3, f"应拆成3段,实得 {parts}")
        self.assertEqual(parts[0], "用户问a")
        self.assertEqual(parts[1], "助手答b")
        self.assertEqual(parts[2], "结束c")

    def test_merged_inline_three(self):
        """合并叙述:三个 turn 塞进一段。"""
        raw = "Turn 1: aa Turn 2: bb Turn 3: cc"
        parts = mod.parse_turn_summaries(raw, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "aa")
        self.assertEqual(parts[1], "bb")
        self.assertEqual(parts[2], "cc")

    def test_absolute_numbering_skip(self):
        """绝对编号:LLM 跳过 Turn 2,按编号对齐补空。"""
        raw = "Turn 1: a\n\nTurn 3: c"
        parts = mod.parse_turn_summaries(raw, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "a")
        self.assertEqual(parts[2], "c")
        # Turn 2 缺失,补空字符串(不报错)
        self.assertEqual(parts[1], "")

    def test_chinese_colon(self):
        """中文冒号 `Turn N：`。"""
        raw = "Turn 1：用户问a\n\nTurn 2：助手答b"
        parts = mod.parse_turn_summaries(raw, 2)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "用户问a")

    def test_no_marker_fallback(self):
        """完全无 Turn 标记:fallback 不崩。"""
        raw = "就是一段普通文本,没有任何标记。"
        parts = mod.parse_turn_summaries(raw, 2)
        # 不崩即可(可能返回 1 段或空)
        self.assertIsInstance(parts, list)


class TestSummarizeChunkRetry(unittest.TestCase):
    """Wave 8.2.1:段数校验 + 重试机制。"""

    def _make_client(self, return_texts: list[str]):
        """构造 mock client,按顺序返回指定文本。"""
        client = MagicMock()
        resp = MagicMock()
        # 依次返回不同的 content
        contents = list(return_texts)
        def _create(**kwargs):
            r = MagicMock()
            r.choices = [MagicMock()]
            r.choices[0].message.content = contents.pop(0) if contents else ""
            return r
        client.chat.completions.create.side_effect = _create
        return client

    def test_count_match_accepted_first_try(self):
        """段数匹配 → 第一次就接受,不重试。"""
        client = self._make_client(["Turn 1: a\n\nTurn 2: b"])
        raw = mod.summarize_chunk(client, "m", "chunk", 1, turn_count=2, max_attempts=2)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertIn("Turn 1", raw)

    def test_count_mismatch_triggers_retry(self):
        """段数不足 → 触发重试,重试后匹配则接受。"""
        # 第一次返回 1 段(不足),第二次返回 2 段(匹配)
        client = self._make_client([
            "Turn 1: only one",
            "Turn 1: a\n\nTurn 2: b",
        ])
        raw = mod.summarize_chunk(client, "m", "chunk", 1, turn_count=2, max_attempts=2)
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertIn("Turn 2", raw)

    def test_retry_exhausted_returns_last(self):
        """重试用尽仍不匹配 → 返回最后一次输出(不抛异常)。"""
        client = self._make_client([
            "Turn 1: only one",
            "Turn 1: still one",
            "Turn 1: still one again",
        ])
        raw = mod.summarize_chunk(client, "m", "chunk", 1, turn_count=3, max_attempts=2)
        # 调用次数 = 1(初次) + 2(重试) = 3
        self.assertEqual(client.chat.completions.create.call_count, 3)
        # 返回最后一次,不抛异常
        self.assertIsInstance(raw, str)

    def test_too_many_segments_accepted_via_truncation(self):
        """段数过多:summarize_chunk 返回原始,调用方(parse)截断。"""
        client = self._make_client(["Turn 1: a\n\nTurn 2: b\n\nTurn 3: extra"])
        # 期望 2 段,实际 3 段 → 重试逻辑判定不匹配会重试
        # 但 max_attempts=0 时不重试,直接返回
        raw = mod.summarize_chunk(client, "m", "chunk", 1, turn_count=2, max_attempts=0)
        self.assertEqual(client.chat.completions.create.call_count, 1)


class TestPromptConstraints(unittest.TestCase):
    """Wave 8.2.2:prompt 强化(绝对编号/段数/不合并约束)。"""

    def test_prompt_has_turn_count_placeholder(self):
        """user prompt 含 {turn_count} 占位符(强化段数约束)。"""
        self.assertIn("{turn_count}", mod.SUMMARY_USER_PROMPT_TEMPLATE)

    def test_system_prompt_forbids_merge(self):
        """system prompt 明确禁止合并多个 turn。"""
        self.assertIn("禁止合并", mod.SUMMARY_SYSTEM_PROMPT)

    def test_system_prompt_requires_absolute_numbering(self):
        """system prompt 明确要求绝对编号。"""
        self.assertIn("绝对编号", mod.SUMMARY_SYSTEM_PROMPT)

    def test_prompt_version_incremented(self):
        """prompt 版本自增(v1 → v2)。"""
        self.assertEqual(mod.PROMPT_VERSION, "v2")

    def test_user_prompt_renders_turn_count(self):
        """user prompt 能正确渲染 turn_count。"""
        rendered = mod.SUMMARY_USER_PROMPT_TEMPLATE.format(
            turns_text="xxx", start_no=1, turn_count=5)
        self.assertIn("5 个 turn", rendered)
        self.assertIn("5 段", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
