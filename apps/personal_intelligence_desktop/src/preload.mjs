// preload.mjs
//
// Minimal contextBridge for the Phase 61 conversation-first desktop shell
// (Plan 61-02 Task 3, GREEN). Exposes exactly the 15 named, schema-validated
// methods from desktop-api-schema.mjs — one per allowlisted channel. It never
// exposes ipcRenderer, nor generic invoke/send/sendSync/on, to the renderer.
//
// `buildBridge(ipcRenderer)` is a pure, injectable seam: the Wave 0 Node tests
// import it directly and feed a mock ipcRenderer. Malformed input is rejected
// by parseDesktopInput INSIDE preload, before any IPC invoke fires.
//
// Sandbox note: with `sandbox: true` Electron loads preload scripts as
// CommonJS, and this file is ESM (`.mjs`). The actual sandboxed preload
// loading is deferred to the renderer-wiring wave (no BrowserWindow is created
// in this plan); at that point the renderer wave must either ship a
// self-contained CommonJS preload (`preload.cjs`, the window config assertions
// already allow it) or evaluate Electron 43's ESM-in-sandbox support. The
// tested contract here is the named `buildBridge` seam plus the guarded
// Electron entry below.
import { BRIDGE_METHODS, CHANNELS, parseDesktopInput } from "./desktop-api-schema.mjs";

// Fixed method -> channel correspondence. buildBridge validates each channel
// against the schema allowlist, so a misconfiguration fails closed.
const BRIDGE_METHOD_TO_CHANNEL = Object.freeze({
  getLastConversation: "harness:last-conversation",
  listRecentConversations: "harness:recent-conversations",
  selectConversation: "harness:select-conversation",
  newConversation: "harness:new-conversation",
  listProjectScopes: "harness:project-scopes",
  selectProjectScope: "harness:select-project-scope",
  sendTurn: "harness:conversation-turn",
  cancelTurn: "harness:turn-cancel",
  resumeTurn: "harness:turn-resume",
  reconcileTurn: "harness:turn-reconcile",
  reviewCandidate: "harness:candidate-review",
  getProactiveState: "harness:proactive-state",
  updateProactiveControls: "harness:proactive-controls",
  dismissProactive: "harness:proactive-dismiss",
  undoProactiveDismissal: "harness:proactive-undo",
});

export function buildBridge(ipcRenderer) {
  const bridge = {};
  for (const method of BRIDGE_METHODS) {
    const channel = BRIDGE_METHOD_TO_CHANNEL[method];
    if (!channel || !(channel in CHANNELS)) {
      throw new Error(`preload bridge method ${method} has no allowlisted channel`);
    }
    bridge[method] = (value) => ipcRenderer.invoke(channel, parseDesktopInput(channel, value));
  }
  return Object.freeze(bridge);
}

// Electron runtime entry: expose the named bridge as `window.harness`. Guarded
// on the Electron runtime version so this module stays importable (and the
// tested seam stays pure) under plain `node --test`, where no Electron exists.
if (typeof process !== "undefined" && process.versions && process.versions.electron) {
  const { contextBridge, ipcRenderer } = await import("electron");
  contextBridge.exposeInMainWorld("harness", buildBridge(ipcRenderer));
}
