import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { resolve } from "node:path";

import {
  createContainedSession,
  PHASE_48_TOOL_NAMES,
  SYNTHETIC_SYSTEM_PROMPT,
} from "./runtime/resource-policy.mjs";
import { EventJournal, PI_KERNEL_EVENTS_DB } from "./events/journal.mjs";

export const DEFAULT_KERNEL_HOST = Object.freeze({ host: "127.0.0.1", port: 8790 });
export const PHASE_48_DECISION_RUN_ID = "piq_f7896e839999ed2eac87ebd4";
export const RESOURCE_POLICY_VERSION = "pi_resource_policy_v1_exact";

export class KernelHostError extends Error {
  constructor(code, message = code) {
    super(message);
    this.name = "KernelHostError";
    this.code = code;
  }
}

function safeError(code) {
  return new KernelHostError(code);
}

export async function readPhase48Decision(decisionPath, now = new Date()) {
  let decision;
  try {
    decision = JSON.parse(await readFile(decisionPath, "utf8"));
  } catch {
    throw safeError("package_decision_missing");
  }
  if (!decision || decision.schema !== "pi-package-decision-v1" || decision.run_id !== PHASE_48_DECISION_RUN_ID || decision.status !== "accepted" || decision.accepted !== true) {
    throw safeError("package_decision_not_accepted");
  }
  const expiry = Date.parse(decision.expiry || "");
  if (!Number.isFinite(expiry) || expiry <= now.getTime()) throw safeError("package_decision_expired");
  return Object.freeze({ run_id: decision.run_id, status: decision.status, accepted: true, expiry: decision.expiry });
}

function assertLoopback(host) {
  if (host !== DEFAULT_KERNEL_HOST.host) throw safeError("non_loopback_bind");
}

function assertExactResourcePolicy(resourceLoader, session) {
  const exactFlags = ["noExtensions", "noSkills", "noPromptTemplates", "noThemes", "noContextFiles"];
  if (!resourceLoader || exactFlags.some((flag) => resourceLoader[flag] !== true)) throw safeError("resource_policy_mismatch");
  if (resourceLoader.getSystemPrompt() !== SYNTHETIC_SYSTEM_PROMPT) throw safeError("resource_policy_mismatch");
  if (resourceLoader.getExtensions().extensions?.length || resourceLoader.getSkills().skills?.length || resourceLoader.getPrompts().prompts?.length || resourceLoader.getThemes().themes?.length || resourceLoader.getAgentsFiles().agentsFiles?.length) {
    throw safeError("resource_policy_not_empty");
  }
  const tools = session.getAllTools().map((tool) => tool.name).sort();
  const expected = [...PHASE_48_TOOL_NAMES].sort();
  if (tools.length !== expected.length || tools.some((name, index) => name !== expected[index])) throw safeError("tool_registry_mismatch");
}

export class KernelHost {
  constructor({ journal, session, resourceLoader, modelRuntime, decision, host, port, shutdownTimeoutMs }) {
    this.journal = journal;
    this.session = session;
    this.resourceLoader = resourceLoader;
    this.modelRuntime = modelRuntime;
    this.decision = decision;
    this.host = host;
    this.port = port;
    this.shutdownTimeoutMs = shutdownTimeoutMs;
    this.server = createServer((_request, response) => {
      response.statusCode = 404;
      response.end();
    });
    this.lifecycle = "ready";
  }

  get providerCalls() { return this.modelRuntime.providerCalls; }

  readiness() {
    if (this.lifecycle !== "ready") return { ready: false, reason: "host_not_running" };
    const integrity = this.journal.integrityCheck();
    const policy = this.resourceLoader && this.resourceLoader.noExtensions === true && this.resourceLoader.noSkills === true && this.resourceLoader.noPromptTemplates === true && this.resourceLoader.noThemes === true && this.resourceLoader.noContextFiles === true;
    return {
      ready: Boolean(this.decision.accepted && policy && integrity.ok && this.host === DEFAULT_KERNEL_HOST.host),
      decision: "accepted",
      resource_policy: RESOURCE_POLICY_VERSION,
      journal: integrity.ok ? "ok" : "failed",
      provider_calls: this.providerCalls,
    };
  }

  isReady() { return this.readiness().ready; }

  status() {
    return { lifecycle: this.lifecycle, host: this.host, port: this.port, provider_calls: this.providerCalls, ready: this.isReady() };
  }

  async listen() {
    if (this.server.listening) return;
    await new Promise((resolveListen, rejectListen) => {
      const onError = () => {
        this.server.removeListener("listening", onListening);
        rejectListen(safeError("host_bind_failed"));
      };
      const onListening = () => {
        this.server.removeListener("error", onError);
        resolveListen();
      };
      this.server.once("error", onError);
      this.server.once("listening", onListening);
      this.server.listen(this.port, this.host);
    });
  }

  async closeServer(timeoutMs) {
    if (!this.server.listening) return false;
    let timedOut = false;
    await Promise.race([
      new Promise((resolveClose) => this.server.close(() => resolveClose())),
      new Promise((resolveTimeout) => setTimeout(() => { timedOut = true; resolveTimeout(); }, timeoutMs)),
    ]);
    return timedOut;
  }

  async shutdown(timeoutMs = this.shutdownTimeoutMs) {
    if (this.lifecycle === "disposed") return { lifecycle: "disposed", timed_out: false };
    this.lifecycle = "stopping";
    let timedOut = false;
    const abort = Promise.resolve().then(() => this.session?.abort?.()).catch(() => undefined);
    await Promise.race([
      abort,
      new Promise((resolveTimeout) => setTimeout(() => { timedOut = true; resolveTimeout(); }, timeoutMs)),
    ]);
    try {
      await Promise.race([
        Promise.resolve().then(() => this.session?.dispose?.()),
        new Promise((resolveTimeout) => setTimeout(() => { timedOut = true; resolveTimeout(); }, timeoutMs)),
      ]);
    } catch { /* bounded disposal must continue */ }
    timedOut = (await this.closeServer(timeoutMs)) || timedOut;
    this.journal.close();
    this.lifecycle = "disposed";
    return { lifecycle: this.lifecycle, timed_out: timedOut };
  }

  async dispose(timeoutMs = this.shutdownTimeoutMs) { return this.shutdown(timeoutMs); }
}

/** Construct the sole Phase 49 host after all package and resource gates pass. */
export async function createKernelHost(options = {}) {
  const host = options.host ?? DEFAULT_KERNEL_HOST.host;
  const port = options.port ?? DEFAULT_KERNEL_HOST.port;
  assertLoopback(host);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw safeError("invalid_port");
  const projectRoot = resolve(options.projectRoot ?? process.cwd());
  const decisionPath = resolve(options.decisionPath ?? resolve(projectRoot, "governance/manifests/ai/pi-package-decision.json"));
  const decision = await readPhase48Decision(decisionPath, options.now ?? new Date());
  const journal = new EventJournal(options.databasePath ?? resolve(projectRoot, PI_KERNEL_EVENTS_DB));
  let hostInstance;
  try {
    const cwd = resolve(options.cwd ?? projectRoot);
    const agentDir = resolve(options.agentDir ?? resolve(projectRoot, ".pi-agent-disabled"));
    const contained = await createContainedSession({ cwd, agentDir });
    assertExactResourcePolicy(contained.resourceLoader, contained.session);
    if (contained.modelRuntime.providerCalls !== 0) throw safeError("provider_call_detected");
    hostInstance = new KernelHost({
      journal,
      session: contained.session,
      resourceLoader: contained.resourceLoader,
      modelRuntime: contained.modelRuntime,
      decision,
      host,
      port,
      shutdownTimeoutMs: options.shutdownTimeoutMs ?? 1000,
    });
    if (!hostInstance.isReady()) throw safeError("host_not_ready");
    await hostInstance.listen();
    return hostInstance;
  } catch (error) {
    try { await hostInstance?.shutdown(options.shutdownTimeoutMs ?? 1000); } catch { /* preserve bootstrap error */ }
    try { journal.close(); } catch { /* preserve bootstrap error */ }
    if (error instanceof KernelHostError) throw error;
    throw safeError("resource_policy_mismatch");
  }
}

export const createKernelHostFactory = createKernelHost;
