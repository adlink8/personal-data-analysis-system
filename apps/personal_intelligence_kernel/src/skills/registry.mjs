import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

export class SkillRegistryError extends Error { constructor(code, message = code) { super(message); this.name = "SkillRegistryError"; this.code = code; } }
const digest = (value) => createHash("sha256").update(JSON.stringify(value, Object.keys(value ?? {}).sort())).digest("hex");
const canonicalSkill = (skill) => { const copy = { ...skill }; delete copy.checksum; return copy; };
export class SkillRegistry {
  constructor({ manifests = [], allowedTools = ["domain_candidate", "domain_inspect"], now = new Date() } = {}) { this.manifests = manifests; this.allowedTools = new Set(allowedTools); this.now = now; }
  validate(skill) { if (!skill?.id || !skill.version || !skill.checksum || !skill.owner || !skill.expires_at) throw new SkillRegistryError("skill_manifest_invalid"); if (skill.checksum !== digest(canonicalSkill(skill))) throw new SkillRegistryError("skill_checksum_mismatch"); if (Date.parse(skill.expires_at) <= this.now.getTime()) throw new SkillRegistryError("skill_expired"); if (!Array.isArray(skill.allowed_tools) || skill.allowed_tools.some((tool) => !this.allowedTools.has(tool))) throw new SkillRegistryError("skill_tool_escalation"); return Object.freeze({ ...skill }); }
  load() { const valid = []; for (const skill of this.manifests) { try { valid.push(this.validate(skill)); } catch { /* invalid manifests abstain */ } } this.manifests = valid; return valid; }
  select({ purpose, input_schema, task_id, session_id, evidence_ref } = {}) { const matches = this.manifests.filter((skill) => skill.purpose === purpose && (!input_schema || skill.input_schema === input_schema)); if (matches.length !== 1) return { selected: false, reason: matches.length ? "skill_collision" : "skill_not_found", skill: null }; const skill = matches[0]; return { selected: true, reason: "selected", skill: { id: skill.id, version: skill.version, checksum: skill.checksum, purpose: skill.purpose, task_id: task_id ?? null, session_id: session_id ?? null, evidence_ref: evidence_ref ?? null } }; }
  static async fromFile(path, options = {}) { const raw = JSON.parse(await readFile(resolve(path), "utf8")); const items = Array.isArray(raw) ? raw : raw.skills; return new SkillRegistry({ ...options, manifests: items ?? [] }); }
}
export const createSkillRegistry = (options) => new SkillRegistry(options);
