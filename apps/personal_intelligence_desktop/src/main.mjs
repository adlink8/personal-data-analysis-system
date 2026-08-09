// main.mjs
//
// Secure Electron main process for the Phase 61 conversation-first desktop
// shell (Plan 61-02 Task 3, GREEN). It implements the Wave 0 privilege
// boundary:
//   - Local-assets BrowserWindow: nodeIntegration false, contextIsolation true,
//     sandbox true, webSecurity true, no webview tag, preload points only at
//     the local preload.mjs.
//   - Restrictive local-only CSP (`default-src 'self'`, connect-src 'none').
//   - Denied webContents navigation / redirection / webview attach,
//     setWindowOpenHandler and permission requests.
//   - Exactly the allowlisted named IPC handlers. Each handler validates the
//     sender URL and the intent schema, then calls ONLY an injected,
//     unconfigured route-provider seam. Until Plan 61-10 binds fixed providers
//     the seam returns the declared ROUTE_PROVIDER_UNAVAILABLE envelope; this
//     file never binds a loopback URL, launches a network request, or claims a
//     last/selected thread.
//   - Cache-Control no-store on every response served to the renderer.
//
// IMPORTANT: this module must import cleanly under plain `node --test` (the
// Wave 0 tests exercise every guard with injected mocks). Electron is therefore
// never imported at module scope; it is lazily imported only by the bootstrap
// that runs when this file is executed as the Electron main entry.
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  ALLOWED_CHANNELS,
  DesktopSchemaError,
  RESTRICTIVE_CSP,
  SECURE_WINDOW_CONFIG,
  assertSecureWindowConfig,
  denyNavigation,
  denyNewWindow as schemaDenyNewWindow,
  denyPermissionRequest,
  parseDesktopInput,
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
// preload.mjs; `assertSecureWindowConfig` fail-closes on any unsafe flag.
export function createWindowConfig() {
  const preload = fileURLToPath(new URL("./preload.mjs", import.meta.url));
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
export async function bootstrapDesktopApp(options = {}) {
  const { app, BrowserWindow, ipcMain, session } = await import("electron");
  installIpcHandlers({
    ipcMain,
    routeProvider: options.routeProvider ?? null,
    senderFilePrefix: options.senderFilePrefix ?? SENDER_FILE_PREFIX,
  });
  await app.whenReady();
  const defaultSession = session.defaultSession;
  const win = createMainWindow({ BrowserWindow, session: defaultSession });
  installWindowGuards({ webContents: win.webContents, session: defaultSession });
  applyNoStoreHeaders(defaultSession);
  return win;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  bootstrapDesktopApp().catch((error) => {
    process.stderr.write(`${JSON.stringify({ ok: false, error: { code: "internal_error" } })}\n`);
    process.exitCode = 1;
  });
}
