import {
  receiptChecksumBinding,
  type HarnessBridge,
} from "./harness-adapter";

export type BridgeAuditEvent = {
  method: "sendTurn" | "cancelTurn" | "selectConversation" | "newConversation";
  at: string;
  metadata: Record<string, string | number | boolean>;
};

export type RecentConversation = {
  conversationId: string;
  title: string;
  source: string;
  updatedLabel: string;
};

export type SpikeHarnessBridge = HarnessBridge & {
  selectConversation(payload: { conversationId: string }): Promise<{ ok: true }>;
  newConversation(payload?: { projectScopeId?: string }): Promise<{ ok: true; data: { conversationId: string } }>;
  getAuditEvents(): readonly BridgeAuditEvent[];
  recentConversations: readonly RecentConversation[];
};

export function createFakeHarnessBridge(delayMs = 220): SpikeHarnessBridge {
  const audit: BridgeAuditEvent[] = [];
  const log = (event: BridgeAuditEvent) => audit.push(Object.freeze(event));
  return {
    recentConversations: [
      { conversationId: "conversation_ui_spike", title: "Agent 桌面 UI 复用方案", source: "Codex", updatedLabel: "刚刚" },
      { conversationId: "conversation_phase_61", title: "Phase 61 验收与反思闭环", source: "ZCode", updatedLabel: "10:42" },
      { conversationId: "conversation_pi_packages", title: "Pi SDK 包引用调查", source: "Codex", updatedLabel: "09:18" },
      { conversationId: "conversation_person_model", title: "个人模型多维度抽象", source: "ZCode", updatedLabel: "昨天" },
    ],
    async sendTurn(payload) {
      log({
        method: "sendTurn",
        at: new Date().toISOString(),
        metadata: {
          conversationId: payload.conversationId,
          textLength: payload.text.length,
          hasProjectScope: Boolean(payload.projectScopeId),
        },
      });
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      const receipt = {
        receipt_id: "receipt_ui_spike_001",
        database_id: "database_canonical_readonly",
        query_id: "conversation.evidence_messages.v1",
        descriptor_version: "1.0.0",
        parameter_names: ["session_id", "after", "limit"],
        statement_display: "conversation.evidence_messages.v1(session_id, after, limit)",
        status: "ok",
        rows: [
          { source: "Codex", sessions: 553, freshness: "stale" },
          { source: "ZCode", sessions: 226, freshness: "stale" },
        ],
        row_count: 2,
        duration_ms: 14,
        truncated: false,
        query_checksum: "",
      };
      receipt.query_checksum = await receiptChecksumBinding(receipt);
      return {
        ok: true,
        status: "ok",
        data: {
          taskId: "pi_task_ui_spike_001",
          displayText:
            "我通过受控 SQLite Tool 检查了聚合会话的来源计数。结果可用于提示同步积压，但不能把旧 watermark 描述成当前新鲜状态。",
          toolRow: {
            skillName: "conversation.evidence.read",
            effect: "read-only",
            resultStatus: "ok",
            receiptCount: 1,
            receipts: [receipt],
          },
          candidate: {
            candidateId: "candidate_refresh_agentsview",
            title: "安排一次会话新鲜度检查",
            summary: "AgentView 与项目 canonical 之间存在历史积压证据；先生成同步建议，不自动执行写入。",
            status: "pending_review",
            version: 1,
            checksum: null,
          },
        },
      };
    },
    async cancelTurn(payload) {
      log({ method: "cancelTurn", at: new Date().toISOString(), metadata: { taskId: payload.taskId } });
      return { ok: true, status: "cancelled_requested", data: null };
    },
    async selectConversation(payload) {
      log({ method: "selectConversation", at: new Date().toISOString(), metadata: { conversationId: payload.conversationId } });
      return { ok: true };
    },
    async newConversation(payload = {}) {
      log({ method: "newConversation", at: new Date().toISOString(), metadata: { hasProjectScope: Boolean(payload.projectScopeId) } });
      return { ok: true, data: { conversationId: "conversation_new_ui_spike" } };
    },
    getAuditEvents() {
      return [...audit];
    },
  };
}
