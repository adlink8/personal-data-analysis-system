// main.mjs
//
// Secure Electron main process for the Phase 61 conversation-first desktop
// shell (Plan 61-02 Task 3, GREEN; Plan 61-11 Task 3 binds fixed providers).
// It implements the Wave 0 privilege boundary:
//   - Local-assets BrowserWindow: nodeIntegration false, contextIsolation true,
//     sandbox true, webSecurity true, no webview tag, preload points only at
//     the local preload.cjs (self-contained CommonJS; Electron 43 sandboxed
//     preloads cannot load ESM).
//   - Restrictive local-only CSP (`default-src 'self'`, connect-src 'none').
//   - Denied webContents navigation / redirection / webview attach,
//     setWindowOpenHandler and permission requests.
//   - Exactly the allowlisted named IPC handlers. Each handler validates the
//     sender URL and the intent schema, then dispatches ONLY through the
//     injected route-provider seam. Plan 61-11 Task 3 supplies the default
//     route provider backed by an unexported localhost-only route map that
//     binds every intent to one fixed provider route; with `routeProvider:
//     null` (the injectable unbound seam) the handler keeps returning the
//     declared ROUTE_PROVIDER_UNAVAILABLE envelope and never claims a
//     last/selected thread.
//   - Cache-Control no-store on every response served to the renderer and on
//     every outbound provider request.
//   - Evidence receipt `statement_display` is normalized only when the
//     checksum binds query ID/version/parameter-name set (defense in depth);
//     logs/telemetry are redacted to IDs/counts/checksums/status.
//
// IMPORTANT: this module must import cleanly under plain `node --test` (the
// Wave 0 tests exercise every guard with injected mocks). Electron is therefore
// never imported at module scope; it is lazily imported only by the bootstrap
// that runs when this file is executed as the Electron main entry.
import { request as httpRequest } from "node:http";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve as pathResolve } from "node:path";

import {
  ALLOWED_CHANNELS,
  DesktopSchemaError,
  RESTRICTIVE_CSP,
  SECURE_WINDOW_CONFIG,
  assertSecureWindowConfig,
  canonicalJson,
  containsForbiddenFields,
  denyNavigation,
  denyNewWindow as schemaDenyNewWindow,
  denyPermissionRequest,
  digest,
  normalizeEvidenceReceipts,
  parseDesktopInput,
  PROVIDER_ROUTES,
  ROUTE_PROVIDER_UNAVAILABLE,
  senderUrlFromEvent,
  toSafeEnvelope,
  validateIpcSender,
} from "./desktop-api-schema.mjs";

// Restrictive local CSP enforced on the renderer session. No remote sources,
// no eval, no arbitrary loopback connect: the renderer reaches authorities
// only through the named preload bridge.
export const CSP = RESTRICTIVE_CSP;

// The renderer is a local file: asset rooted at this directory. The real
// bootstrap pins IPC senders to exactly this prefix (defense in depth); the
// injectable default keeps the schema's `file://` origin gate.
const RENDERER_DIR_URL = new URL("./renderer/", import.meta.url);
export const RENDERER_DIR = fileURLToPath(RENDERER_DIR_URL);
export const RENDERER_INDEX_URL = new URL("./renderer/index.html", import.meta.url);
export const SENDER_FILE_PREFIX = `file://${RENDERER_DIR}`;

// Hardened BrowserWindow webPreferences. The preload path is the only local
// preload.cjs; `assertSecureWindowConfig` fail-closes on any unsafe flag.
export function createWindowConfig() {
  const preload = fileURLToPath(new URL("./preload.cjs", import.meta.url));
  return assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, preload });
}

// Deny window.open / target=_blank attempts from the renderer.
export const denyNewWindow = schemaDenyNewWindow;

// Register navigation/new-window/permission denials on a live webContents and
// session. Fully injectable: it only uses `webContents.on`, the optional
// `setWindowOpenHandler`, and `session.setPermissionRequestHandler`, so the
// Wave 0 test can prove every denial with mocks.
export function installWindowGuards({ webContents, session }) {
  if (!webContents || typeof webContents.on !== "function") {
    throw new TypeError("installWindowGuards requires a webContents");
  }
  webContents.on("will-navigate", (event) => denyNavigation(event));
  webContents.on("will-redirect", (event) => denyNavigation(event));
  webContents.on("will-attach-webview", (event) => {
    event.preventDefault();
    return denyNewWindow();
  });
  if (typeof webContents.setWindowOpenHandler === "function") {
    webContents.setWindowOpenHandler(() => denyNewWindow());
  }
  if (session && typeof session.setPermissionRequestHandler === "function") {
    session.setPermissionRequestHandler((webContents_, permission, callback) => {
      denyPermissionRequest(webContents_, permission, callback);
    });
  }
  return webContents;
}

// Cache-Control no-store for every response crossing the renderer session.
// Local conversation view models must never be replayed from cache.
export function applyNoStoreHeaders(targetSession) {
  if (!targetSession || typeof targetSession.webRequest?.onHeadersReceived !== "function") {
    return targetSession;
  }
  targetSession.webRequest.onHeadersReceived((details, callback) => {
    const responseHeaders = { ...(details.responseHeaders ?? {}) };
    responseHeaders["Cache-Control"] = ["no-store"];
    callback({ responseHeaders });
  });
  return targetSession;
}

// One IPC handler factory per allowlisted channel.
//
// Handler contract (defense in depth, renderer is always untrusted):
//   1. Extract and validate the sender URL (untrusted -> denied).
//   2. Parse/validate the intent payload (unknown key, malformed ID, endpoint
//      override -> denied before any provider work).
//   3. Call ONLY the injected route-provider seam. With no provider bound the
//      seam is unconfigured, so the fixed ROUTE_PROVIDER_UNAVAILABLE envelope
//      is returned until Plan 61-10 binds fixed local providers.
// The provider seam receives `(intent, normalizedInput)` and returns a
// result that `toSafeEnvelope` projects onto the safe `{ok,status,error,data}`
// view model; cancelled/outcome_unknown results can never normalize to success.
function makeIpcHandler(channel, options) {
  const senderPrefix = options.senderFilePrefix;
  const routeProvider = options.routeProvider ?? null;
  return async (event, value) => {
    try {
      const senderUrl = senderUrlFromEvent(event);
      validateIpcSender(
        senderUrl,
        senderPrefix === undefined ? undefined : { allowedFilePrefix: senderPrefix },
      );
      const input = parseDesktopInput(channel, value);
      if (!routeProvider || typeof routeProvider.handle !== "function") {
        return ROUTE_PROVIDER_UNAVAILABLE;
      }
      const result = await routeProvider.handle(input.intent, input);
      return toSafeEnvelope(result);
    } catch (error) {
      if (error instanceof DesktopSchemaError) {
        return toSafeEnvelope({ ok: false, status: "denied", error: { code: error.code } });
      }
      return toSafeEnvelope({ ok: false, status: "error", error: { code: "internal_error" } });
    }
  };
}

// ===========================================================================
// Plan 61-11 Task 3: fixed localhost-only route map + bound route provider.
//
// ROUTE_MAP is deliberately NOT exported: the renderer can never select an
// endpoint, path or provider. Every desktop intent resolves to exactly one
// fixed provider route in this map, and the route provider validates sender,
// schema, response privacy ceiling, statement_display binding and truthful
// empty/unknown/stale states before any renderer-visible projection.
// ===========================================================================

// Loopback authorities. Kernel (server.mjs) owns session.create/turn/recovery/
// review/projection/proactive; the Python canonical gateway owns thread and
// project-scope reads. Both are fixed 127.0.0.1 loopback-only authorities.
export const DEFAULT_KERNEL_BASE_URL = "http://127.0.0.1:8790";
export const DEFAULT_PYTHON_BASE_URL = "http://127.0.0.1:8000";
const PYTHON_DISPATCH_PATH = "/internal/pi-domain/dispatch";

// Intent -> { provider, authority, method, path }.
// authority "kernel" reaches the Kernel HTTP server; "python" reaches the
// Python canonical gateway dispatch endpoint. No renderer field influences any
// of these values.
const ROUTE_MAP = Object.freeze({
  "last-conversation": Object.freeze({ provider: PROVIDER_ROUTES["last-conversation"], authority: "python", method: "POST", path: PYTHON_DISPATCH_PATH }),
  "recent-list": Object.freeze({ provider: PROVIDER_ROUTES["recent-list"], authority: "python", method: "POST", path: PYTHON_DISPATCH_PATH }),
  "conversation-select": Object.freeze({ provider: PROVIDER_ROUTES["conversation-select"], authority: "python", method: "POST", path: PYTHON_DISPATCH_PATH }),
  "conversation-new": Object.freeze({ provider: PROVIDER_ROUTES["conversation-new"], authority: "kernel", method: "POST", path: "/v1/conversations/session" }),
  "project-scope-list": Object.freeze({ provider: PROVIDER_ROUTES["project-scope-list"], authority: "python", method: "POST", path: PYTHON_DISPATCH_PATH }),
  "project-scope-select": Object.freeze({ provider: PROVIDER_ROUTES["project-scope-select"], authority: "python", method: "POST", path: PYTHON_DISPATCH_PATH }),
  turn: Object.freeze({ provider: PROVIDER_ROUTES.turn, authority: "kernel", method: "POST", path: "/v1/conversations/turn" }),
  cancel: Object.freeze({ provider: PROVIDER_ROUTES.cancel, authority: "kernel", method: "POST", path: "/v1/conversations/cancel" }),
  resume: Object.freeze({ provider: PROVIDER_ROUTES.resume, authority: "kernel", method: "POST", path: "/v1/conversations/resume" }),
  reconcile: Object.freeze({ provider: PROVIDER_ROUTES.reconcile, authority: "kernel", method: "POST", path: "/v1/conversations/reconcile" }),
  review: Object.freeze({ provider: PROVIDER_ROUTES.review, authority: "kernel", method: "POST", path: "/v1/candidates/review" }),
  projection: Object.freeze({ provider: PROVIDER_ROUTES.projection, authority: "kernel", method: "GET", path: "/v1/personal/model-projection" }),
  "proactive-read": Object.freeze({ provider: PROVIDER_ROUTES["proactive-read"], authority: "kernel", method: "POST", path: "/v1/proactive/state" }),
  "proactive-controls": Object.freeze({ provider: PROVIDER_ROUTES["proactive-controls"], authority: "kernel", method: "POST", path: "/v1/proactive/controls" }),
  "proactive-dismiss": Object.freeze({ provider: PROVIDER_ROUTES["proactive-dismiss"], authority: "kernel", method: "POST", path: "/v1/proactive/dismiss" }),
  "proactive-undo": Object.freeze({ provider: PROVIDER_ROUTES["proactive-undo"], authority: "kernel", method: "POST", path: "/v1/proactive/undo" }),
});

// Field translation from the normalized desktop input to the fixed provider
// request body. Only allowlisted keys map; anything else is dropped by the
// schema layer before it ever reaches the route provider.
const INPUT_FIELD_TO_PROVIDER_PARAM = Object.freeze({
  conversationId: "conversation_id",
  projectScopeId: "project_scope_id",
  taskId: "task_id",
  candidateId: "candidate_id",
  action: "action",
  version: "expected_version",
  checksum: "edited_payload_checksum",
  scope: "scope",
  text: "prompt",
  skillId: "skill_id",
  category: "category",
  enabled: "enabled",
  quietHours: "quiet_hours",
  itemId: "cluster_key",
  reason: "feedback_reason",
  feedbackId: "feedback_id",
});

// Provider-required binding metadata is synthesized deterministically in the
// main process (never renderer-supplied): idempotency_key/binding are fixed by
// the route contract, and task_id/session_id are derived from a canonical
// digest of the intent+input so replays stay idempotent and no renderer field
// can forge authority identity.
function synthesizeProviderMeta(intent, input) {
  const seed = digest(canonicalJson({ intent, input }));
  const idempotencyKey = `pi_desktop_${intent}_${seed.slice(0, 24)}`;
  const meta = {
    idempotency_key: idempotencyKey,
    binding: "pi_desktop_route_v1",
    task_id: `pi_task_${digest(canonicalJson({ seed, kind: "task" })).slice(0, 24)}`,
  };
  // Only the conversation-turn provider accepts a session_id; review,
  // projection and the Python canonical providers reject undeclared fields
  // (their fixed contracts do not include session_id).
  if (intent === "turn") {
    meta.session_id = `pi_session_${digest(canonicalJson({ seed, kind: "session" })).slice(0, 24)}`;
  }
  return meta;
}

function translateToProviderBody(intent, input) {
  const body = synthesizeProviderMeta(intent, input);
  for (const [desktopKey, providerKey] of Object.entries(INPUT_FIELD_TO_PROVIDER_PARAM)) {
    if (input[desktopKey] !== undefined) body[providerKey] = input[desktopKey];
  }
  // An ordinary conversation turn always runs the governed read-only
  // knowledge.research Skill lease (Plan 61-03); the renderer cannot select a
  // Skill, so the fixed default is applied here when none is supplied.
  if (intent === "turn" && body.skill_id === undefined) {
    body.skill_id = "knowledge.research";
  }
  return body;
}

// Redacted telemetry/logging: only IDs/counts/checksums/status ever leave the
// process. Body text, credentials, SQL, thinking and raw fields are never part
// of a telemetry record.
function redactForTelemetry(entry) {
  const out = { intent: entry.intent, status: entry.status, ok: entry.ok };
  if (entry.provider) out.provider = entry.provider;
  if (entry.error && typeof entry.error.code === "string") out.error_code = entry.error.code;
  return out;
}

// Build the fixed localhost request for one intent. The route descriptor is the
// ONLY source of the URL; the normalized input contributes only allowlisted
// provider parameters.
function buildRouteRequest(route, intent, input) {
  const body = translateToProviderBody(intent, input);
  if (route.authority === "python") {
    const base = DEFAULT_PYTHON_BASE_URL;
    return {
      method: route.method,
      url: `${base}${route.path}`,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "X-PI-Domain-Capability": process.env.PI_DOMAIN_CAPABILITY ?? "pi-domain-local-capability-v1",
      },
      body: JSON.stringify({ operation: route.provider, params: body }),
      provider: route.provider,
      intent,
    };
  }
  const base = DEFAULT_KERNEL_BASE_URL;
  if (route.method === "GET") {
    // The fixed projection read route takes query parameters only (no body).
    const query = new URLSearchParams(body).toString();
    return {
      method: "GET",
      url: `${base}${route.path}${query ? `?${query}` : ""}`,
      headers: { "Cache-Control": "no-store" },
      body: "",
      provider: route.provider,
      intent,
    };
  }
  return {
    method: route.method,
    url: `${base}${route.path}`,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    body: JSON.stringify(body),
    provider: route.provider,
    intent,
  };
}

// Default transport: loopback-only HTTP. The URL host is validated to be
// loopback so no renderer-influenced or misconfigured remote host can be
// reached. Returns `{ status, body }` with the parsed JSON envelope.
function createLoopbackTransport({ timeoutMs = 3000 } = {}) {
  return (request) => new Promise((resolve, reject) => {
    let url;
    try {
      url = new URL(request.url);
    } catch {
      reject(Object.assign(new Error("invalid_route_url"), { code: "invalid_route_url" }));
      return;
    }
    const host = url.hostname;
    if (host !== "127.0.0.1" && host !== "::1" && host !== "localhost") {
      reject(Object.assign(new Error("non_loopback_route"), { code: "non_loopback_route" }));
      return;
    }
    const req = httpRequest(
      {
        hostname: host,
        port: url.port,
        method: request.method,
        path: `${url.pathname}${url.search}`,
        headers: {
          ...request.headers,
          "Content-Length": Buffer.byteLength(request.body ?? ""),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const raw = Buffer.concat(chunks).toString("utf8");
          let body = null;
          try {
            body = raw ? JSON.parse(raw) : null;
          } catch {
            body = null;
          }
          resolve({ status: res.statusCode ?? 0, body });
        });
      },
    );
    req.setTimeout(timeoutMs, () => {
      req.destroy(Object.assign(new Error("provider_timeout"), { code: "provider_timeout" }));
    });
    req.on("error", (error) => reject(Object.assign(error, { code: error.code ?? "provider_transport_error" })));
    if (request.body) req.write(request.body);
    req.end();
  });
}

function providerErrorCode(error) {
  if (error && typeof error.code === "string") return error.code;
  if (error && typeof error.message === "string" && error.message.length < 128) return error.message;
  return "provider_unavailable";
}

// Normalize one provider envelope. Non-success stays truthful; success data is
// passed through `normalizeEvidenceReceipts` so `statement_display` survives
// only when its checksum binding verifies. The privacy ceiling runs after
// normalization as a final deny-by-default guard.
//
// Two provider envelope shapes are accepted:
//   - Python canonical gateway: { schema_version, operation, ok, status, data }
//   - Kernel HTTP server:       { ok, ...payload }  (payload fields such as
//     session/thread/receipts sit at the top level, e.g. POST
//     /v1/conversations/session returns {ok, duplicate, session, thread})
// In both cases the safe projection exposes the payload as `data` so the
// renderer view-model reads `envelope.data.session` etc.
const PROVIDER_ENVELOPE_KEYS = new Set(["ok", "status", "error", "schema_version", "operation", "duplicate", "schema"]);

function normalizeProviderEnvelope(providerEnvelope) {
  if (providerEnvelope === null || typeof providerEnvelope !== "object") {
    return { ok: false, status: "error", error: { code: "provider_response_invalid" }, data: null };
  }
  if (providerEnvelope.ok !== true) {
    return {
      ok: false,
      status: typeof providerEnvelope.status === "string" ? providerEnvelope.status : "error",
      error: providerEnvelope.error && typeof providerEnvelope.error === "object"
        ? { code: typeof providerEnvelope.error.code === "string" ? providerEnvelope.error.code : "provider_unavailable" }
        : { code: "provider_unavailable" },
      data: null,
    };
  }
  let rawData = providerEnvelope.data;
  if (rawData === null || rawData === undefined || typeof rawData !== "object") {
    // Kernel-style top-level payload envelope.
    rawData = {};
    for (const [key, value] of Object.entries(providerEnvelope)) {
      if (!PROVIDER_ENVELOPE_KEYS.has(key)) rawData[key] = value;
    }
  }
  const normalizedData = normalizeEvidenceReceipts(rawData);
  if (containsForbiddenFields(normalizedData)) {
    return { ok: false, status: "denied", error: { code: "forbidden_response_field" }, data: null };
  }
  return {
    ok: true,
    status: typeof providerEnvelope.status === "string" ? providerEnvelope.status : "ok",
    data: normalizedData,
  };
}

/**
 * Build the default bound route provider used by the desktop shell.
 *
 * `createRouteProvider({ transport })` injects a transport (defaults to the
 * loopback HTTP client) so the Wave 0 tests can drive the route map with a
 * recording transport. `telemetry` is an optional sink that receives only
 * redacted records (IDs/counts/checksums/status).
 */
export function createRouteProvider({ transport, timeoutMs = 3000, telemetry } = {}) {
  const call = transport ?? createLoopbackTransport({ timeoutMs });
  const emit = typeof telemetry === "function" ? telemetry : () => {};
  return {
    async handle(intent, input) {
      const route = ROUTE_MAP[intent];
      if (!route) {
        emit(redactForTelemetry({ intent, status: "denied", ok: false, error: { code: "unknown_intent" } }));
        return { ok: false, status: "denied", error: { code: "unknown_intent" }, data: null };
      }
      const request = buildRouteRequest(route, intent, input);
      let response;
      try {
        response = await call(request);
      } catch (error) {
        emit(redactForTelemetry({ intent, status: "error", ok: false, error: { code: providerErrorCode(error) } }));
        return { ok: false, status: "error", error: { code: providerErrorCode(error) }, data: null };
      }
      const normalized = normalizeProviderEnvelope(response?.body);
      emit(redactForTelemetry({ intent, status: normalized.status, ok: normalized.ok, provider: route.provider, error: normalized.error }));
      return normalized;
    },
  };
}

// Register exactly the allowlisted named channels; no generic `send`/`invoke`
// handler is ever registered. Returns the sorted registered channel list.
export function installIpcHandlers({ ipcMain, routeProvider = null, senderFilePrefix } = {}) {
  if (!ipcMain || typeof ipcMain.handle !== "function") {
    throw new TypeError("installIpcHandlers requires ipcMain");
  }
  const options = { routeProvider, senderFilePrefix };
  for (const channel of ALLOWED_CHANNELS) {
    ipcMain.handle(channel, makeIpcHandler(channel, options));
  }
  return [...ALLOWED_CHANNELS].sort();
}

// Create a hardened local-assets BrowserWindow. The renderer index is deferred
// to a later 61 wave; if it is not present yet the window stays blank rather
// than loading a remote/loopback URL.
export function createMainWindow({ BrowserWindow, session }) {
  if (typeof BrowserWindow !== "function") {
    throw new TypeError("createMainWindow requires BrowserWindow");
  }
  const win = new BrowserWindow({
    webPreferences: createWindowConfig(),
    show: false,
    backgroundColor: "#1A2228",
  });
  win.once("ready-to-show", () => win.show());
  if (session) installWindowGuards({ webContents: win.webContents, session });
  const rendererIndex = fileURLToPath(RENDERER_INDEX_URL);
  if (existsSync(rendererIndex)) {
    win.loadFile(rendererIndex).catch(() => { /* renderer wiring deferred */ });
  }
  return win;
}

// Electron main bootstrap (only runs as the Electron main entry). Lazily
// imports Electron so this module stays importable under plain `node --test`.
// Plan 61-11 Task 3: the real desktop shell binds the fixed route map by
// default; an explicitly injected routeProvider still wins (tests inject
// recording transports).
export async function bootstrapDesktopApp(options = {}) {
  const { app, BrowserWindow, ipcMain, session } = await import("electron");
  installIpcHandlers({
    ipcMain,
    routeProvider: options.routeProvider ?? createRouteProvider({ timeoutMs: options.routeTimeoutMs }),
    senderFilePrefix: options.senderFilePrefix ?? SENDER_FILE_PREFIX,
  });
  await app.whenReady();
  const defaultSession = session.defaultSession;
  const win = createMainWindow({ BrowserWindow, session: defaultSession });
  installWindowGuards({ webContents: win.webContents, session: defaultSession });
  applyNoStoreHeaders(defaultSession);
  return win;
}

export function isDesktopEntry(argv1, selfFile = fileURLToPath(import.meta.url)) {
  // `electron .` passes "." as argv[1]; direct `electron main.mjs` passes the
  // module path. Node under `node --test` imports this module without either
  // matching, so bootstrap stays inert there.
  return Boolean(argv1) && (argv1 === "." || pathResolve(argv1) === selfFile);
}
const _isDesktopEntry = isDesktopEntry(process.argv[1]);
if (_isDesktopEntry) {
  bootstrapDesktopApp().catch((error) => {
    process.stderr.write(`${JSON.stringify({ ok: false, error: { code: "internal_error" } })}\n`);
    process.exitCode = 1;
  });
}
