import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { SkillRegistry } from "../src/skills/registry.mjs";

function checksum(skill) { const copy = { ...skill }; delete copy.checksum; return createHash("sha256").update(JSON.stringify(copy, Object.keys(copy).sort())).digest("hex"); }
function skill(overrides = {}) { const base = { id: "skill.inspect", version: "1.0.0", purpose: "inspect", input_schema: "inspect-v1", output_schema: "receipt-v1", allowed_tools: ["domain_inspect"], privacy_ceiling: "R1", owner: "repo", expires_at: "2099-01-01T00:00:00Z", ...overrides }; return { ...base, checksum: checksum(base) }; }
test("skill selection is deterministic and ambient-free", () => { const registry = new SkillRegistry({ manifests: [skill()], allowedTools: ["domain_inspect"] }); assert.equal(registry.load().length, 1); const selected = registry.select({ purpose: "inspect", input_schema: "inspect-v1", task_id: "t", session_id: "s" }); assert.equal(selected.selected, true); assert.equal(selected.skill.id, "skill.inspect"); });
test("checksum drift, collision, expiry and tool escalation abstain", () => { const drift = { ...skill(), checksum: "0".repeat(64) }; const registry = new SkillRegistry({ manifests: [drift, skill({ id: "skill.bad", allowed_tools: ["edit"] }), skill({ id: "skill.expired", expires_at: "2020-01-01T00:00:00Z" })], allowedTools: ["domain_inspect"] }); assert.equal(registry.load().length, 0); const collision = new SkillRegistry({ manifests: [skill(), skill({ id: "skill.other" })], allowedTools: ["domain_inspect"] }); collision.load(); assert.equal(collision.select({ purpose: "inspect", input_schema: "inspect-v1" }).reason, "skill_collision"); });
