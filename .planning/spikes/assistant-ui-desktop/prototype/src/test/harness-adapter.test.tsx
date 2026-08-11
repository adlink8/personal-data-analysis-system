import { describe, expect, it, vi } from "vitest";
import {
  assertNamedBridgeOnly,
  cancelHarnessTurn,
  containsForbiddenFields,
  dispatchHarnessTurn,
  normalizeEvidenceReceipt,
  normalizeTurnEnvelope,
  receiptChecksumBinding,
  toThreadMessage,
  type HarnessBridge,
} from "../harness-adapter";

async function validReceipt() {
  const receipt = {
    receipt_id: "receipt_test_001",
    database_id: "database_test_readonly",
    query_id: "conversation.evidence_messages.v1" as const,
    descriptor_version: "1.0.0",
    parameter_names: ["session_id", "after", "limit"],
    statement_display: "conversation.evidence_messages.v1(session_id, after, limit)" as const,
    status: "ok",
    rows: [{ source: "Codex", sessions: 2, nested: { rejected: true } }],
    row_count: 1,
    duration_ms: 4,
    truncated: false,
    query_checksum: "",
  };
  receipt.query_checksum = await receiptChecksumBinding(receipt);
  return receipt;
}

describe("HarnessRuntimeAdapter", () => {
  it("maps safe display messages to assistant-ui without mutating the source", () => {
    const source = Object.freeze({
      id: "message_1",
      role: "assistant" as const,
      text: "只读展示",
      createdAt: "2026-08-10T00:00:00.000Z",
      status: "complete" as const,
    });
    const mapped = toThreadMessage(source);
    expect(mapped.id).toBe("message_1");
    expect(mapped.content).toEqual([{ type: "text", text: "只读展示" }]);
    expect(source).toEqual(expect.objectContaining({ text: "只读展示" }));
  });

  it("accepts only the named bridge and rejects generic transport surfaces", () => {
    const named: HarnessBridge = { sendTurn: vi.fn(), cancelTurn: vi.fn() };
    expect(assertNamedBridgeOnly(named)).toBe(named);
    expect(() => assertNamedBridgeOnly({ ...named, fetch: vi.fn() } as HarnessBridge)).toThrow("generic_bridge_surface_rejected");
    expect(() => assertNamedBridgeOnly({ ...named, query: vi.fn() } as HarnessBridge)).toThrow("generic_bridge_surface_rejected");
  });

  it("rejects raw SQL, paths and provider bodies recursively", () => {
    expect(containsForbiddenFields({ nested: { sql: "select *" } })).toBe(true);
    expect(containsForbiddenFields({ rows: [{ path: "C:/private" }] })).toBe(true);
    expect(containsForbiddenFields({ providerBody: { value: "secret" } })).toBe(true);
    expect(containsForbiddenFields({ displayText: "safe", query_id: "descriptor" })).toBe(false);
  });

  it("renders only checksum-bound allowlisted SQLite receipts", async () => {
    const receipt = await validReceipt();
    const normalized = await normalizeEvidenceReceipt(receipt);
    expect(normalized).toEqual(expect.objectContaining({ queryId: "conversation.evidence_messages.v1", rowCount: 1 }));
    expect(normalized?.rows).toEqual([{ source: "Codex", sessions: 2 }]);
    await expect(normalizeEvidenceReceipt({ ...receipt, query_checksum: "0".repeat(64) })).resolves.toBeNull();
    await expect(normalizeEvidenceReceipt({ ...receipt, statement_display: "SELECT * FROM messages" })).resolves.toBeNull();
  });

  it("fails closed when a successful envelope carries a forbidden response field", async () => {
    const normalized = await normalizeTurnEnvelope({
      ok: true,
      data: { displayText: "looks safe", provider_body: { secret: "not allowed" } },
    });
    expect(normalized.code).toBe("forbidden_response_field");
    expect(JSON.stringify(normalized)).not.toContain("not allowed");
    expect(normalized.messages[0].status).toBe("incomplete");
  });

  it("routes a turn through the exact named sendTurn method", async () => {
    const sendTurn = vi.fn(async () => ({ ok: true, data: { displayText: "done" } }));
    const cancelTurn = vi.fn();
    const normalized = await dispatchHarnessTurn(
      { sendTurn, cancelTurn },
      { conversationId: "conversation_test", text: "hello" },
    );
    expect(sendTurn).toHaveBeenCalledOnce();
    expect(sendTurn).toHaveBeenCalledWith({ conversationId: "conversation_test", text: "hello" });
    expect(normalized.messages[0].text).toBe("done");
  });

  it("does not fabricate cancellation before an early task id exists", async () => {
    const sendTurn = vi.fn();
    const cancelTurn = vi.fn();
    await expect(cancelHarnessTurn({ sendTurn, cancelTurn }, null)).resolves.toBe(false);
    expect(cancelTurn).not.toHaveBeenCalled();
    await expect(cancelHarnessTurn({ sendTurn, cancelTurn }, "pi_task_known")).resolves.toBe(true);
    expect(cancelTurn).toHaveBeenCalledWith({ taskId: "pi_task_known" });
  });
});
