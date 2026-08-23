'use strict'
// The single preload/contextBridge surface of §5.1. Everything the renderer can
// reach natively passes through here, and the confinement test pins the key set.
const { contextBridge, ipcRenderer } = require('electron')

// Isolation canary. This lands on the PRELOAD's isolated-world global. With
// contextIsolation on, the page cannot see it. If the confinement probe finds
// it, the worlds are shared and every other guarantee here is void.
globalThis.__moltrace_preload_isolated_world_marker__ = true

// §7.1: report module, pack, network and service capabilities as ONE readout,
// assembled by the desktop — no server endpoint aggregates them (§4.2). Stubbed
// to its shape here; Phase 1 fills it from the entitlement statement, the local
// pack inventory and the reachable service versions.
// CONFINEMENT SELF-REPORT (§7.1 diagnostics).
//
// This exists because of a measured failure: a probe that runs in the renderer's
// MAIN WORLD cannot see `nodeIntegration` or `sandbox` at all while
// `contextIsolation` is on — contextIsolation keeps Node out of the page world
// regardless of the other two, so both weakenings leave a main-world probe green.
// The place those two settings actually manifest is the PRELOAD's own
// environment, so the preload measures itself and reports over IPC. It does not
// cross the contextBridge, so the reviewable surface does not grow.
function measureConfinement() {
  const reach = (m) => { try { require(m); return true } catch { return false } }
  return {
    // With sandbox:true the preload gets a restricted module set; full Node
    // reach here means the sandbox is effectively off.
    fs: reach('node:fs'),
    childProcess: reach('node:child_process'),
    processType: typeof process !== 'undefined' ? process.type : null,
    // Electron sets this on a sandboxed renderer process.
    processSandboxed: typeof process !== 'undefined' ? process.sandboxed === true : null,
  }
}
try { ipcRenderer.send('moltrace:confinement-self-report', measureConfinement()) } catch { /* non-fatal */ }

// ONE namespace. The confinement test pins its key set, so adding a capability
// is a visible diff against ALLOWED_BRIDGE_KEYS — which is the "one reviewable
// allowlist" §7.1 asks for, rather than a scatter of top-level globals.
contextBridge.exposeInMainWorld('moltrace', {
  capabilities: {
    // The assembled readout, requested from the main process. The renderer gets
    // the VERDICTS, never the inputs: a page that can see the entitlement or the
    // service versions can reason about them, and §7.1's rule is that the desktop
    // decides availability once, in one place, rather than each surface deciding
    // for itself and disagreeing.
    read: async () => ipcRenderer.invoke('moltrace:capability-readout'),
  },
  service: {
    read: async () => ipcRenderer.invoke('moltrace:service-report'),
  },
  // A callback, not an event emitter: the renderer is told THAT something
  // changed and asks again, so nothing crosses the bridge except the invitation.
  onChanged: (fn) => {
    ipcRenderer.on('moltrace:readout-changed', () => fn())
  },
})
