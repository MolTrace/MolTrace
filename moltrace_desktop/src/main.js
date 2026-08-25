'use strict'
const path = require('node:path')
const { app, session, ipcMain, safeStorage } = require('electron')
const { createWindow } = require('./window-factory')
const product = require('./product')
const serviceCredential = require('./service-credential')
const capabilities = require('./capabilities')
const capabilityView = require('./capability-view')
const keyHierarchy = require('./key-hierarchy')
const localService = require('./local-service')
const pathMod = require('node:path')

// Generated once per launch and held in this closure. It is NOT put on
// app.state, not exported, and never crosses the contextBridge — a renderer that
// can read it can talk to the local scientific service directly, which is the
// whole thing the transport controls exist to prevent (§7.1).
let localServiceCredential = null

// The running service, or a description of why it is not running. Never null:
// the capability readout needs an answer, and "we did not look" is not one.
let serviceState = { reachable: false, versions: {}, reason: 'The local science service has not been started yet.' }
let service = null
// Set by shutdown(). A readiness poll in flight must not report a service the
// app has already stopped, and must not dereference the binding shutdown cleared.
let stopped = false
// The window the readout is pushed to, so a service death reaches the screen
// without waiting for the user to do something.
let mainWindow = null

// Collected per webContents id so the confinement test can assert on the
// environment each preload actually got, not on what was declared.
const confinementReports = new Map()
ipcMain.on('moltrace:confinement-self-report', (e, report) => {
  confinementReports.set(e.sender.id, report)
})
module.exports = { confinementReports }

// §7.1's declared capability set. Adding one here is the visible diff a reviewer
// sees; a capability that is not declared is not reported, and the readout test
// asserts nothing is silently omitted.
const DECLARED_CAPABILITIES = [
  {
    key: 'fid.process',
    displayName: 'Process a raw acquisition',
    requiresModule: 'spectracheck',
    requiresPack: 'rules-ich',
    requiresService: 'fid',
  },
]

async function startLocalService() {
  // Failure here must NOT stop the window opening. A desktop that will not open
  // because a subprocess did not start is worse than one that opens and says so:
  // §9.2 is absolute that reading local records never depends on anything being
  // reachable, and the capability readout already renders an unreachable service
  // as not-provisioned with a cause.
  try {
    // Held in a LOCAL const as well as the module binding. The readiness poll
    // closes over this one: shutdown() sets the module binding to null, and a
    // poll still in flight would then dereference null from a timer callback --
    // an uncaught exception in the main process, which is the failure class this
    // whole area keeps producing. Closing over the local means a late probe sees
    // the service it was started for.
    const started = localService.start({
      credential: localServiceCredential,
      backendDir: pathMod.join(__dirname, '..', '..', 'moltrace_backend'),
      onExit: (err, output) => {
        // A service that dies AFTER startup has to reach the screen. serviceState
        // is otherwise written once, by the poll below, so a dead service went on
        // being reported as running for the life of the window.
        serviceState = localService.describeFailure(err, output)
        pushReadout(mainWindow)
      },
    })
    service = started
    serviceState = await localService.waitUntilReady({
      started,
      headers: () => localServiceCredential.headers(),
      cancelled: () => stopped,
    })
  } catch (err) {
    serviceState = localService.describeFailure(err)
  }
}

// No orphans. A service left running holds the socket and its credential is
// already gone, so nothing could talk to it anyway -- it would just sit there.
//
// EXPORTED because app.exit() does not emit this, and app.exit() is how the
// confinement test ends. Measured: after app.exit(0) the `uv` and `python`
// processes were still alive, reparented to init (PPID 1). Anything that exits
// the app by that route must call shutdown() itself.
function shutdown() {
  stopped = true
  if (service) { try { service.close() } catch {} }
  service = null
}
module.exports.shutdown = shutdown

app.on('will-quit', shutdown)

// §7.1 asks the readout to report "module, local-pack, network, and SERVICE
// capabilities". The service is not only a gate input -- an operator needs to see
// whether the local science service is running, separately from whether any
// given capability is unlocked, because those fail for different reasons and
// have different remedies.
function serviceReport() {
  return {
    running: serviceState.reachable === true,
    headline: serviceState.reachable ? 'Local science service running' : 'Local science service not running',
    detail: serviceState.reachable
      ? 'Analysis can run on this computer without a network connection.'
      : serviceState.reason,
  }
}

function pushReadout(win) {
  if (win && !win.isDestroyed()) {
    win.webContents.send('moltrace:readout-changed')
  }
}

ipcMain.handle('moltrace:service-report', () => serviceReport())

ipcMain.handle('moltrace:capability-readout', () => {
  // The world is assembled here from the four sources §7.1 names. Each is null
  // until its subsystem exists, and null fails CLOSED — so today the honest
  // answer is that nothing is available, and the readout says so with a cause
  // rather than reporting an empty list.
  // The service source is now REAL. The other three are still null and null
  // fails closed, which is the honest answer while they do not exist.
  return capabilities
    .readout(DECLARED_CAPABILITIES, localService.capabilityWorld(serviceState))
    .map(capabilityView.present)
})

function applyCsp() {
  // Belt and braces with the page's meta CSP: a header the page cannot weaken.
  session.defaultSession.webRequest.onHeadersReceived((details, cb) => {
    cb({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; " +
          "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        ],
      },
    })
  })
}

app.whenReady().then(() => {
  // Fail closed on an unconfigured build. A build from public source has no
  // workspace and no pinned root key, so it must refuse and say why rather than
  // opening a window that cannot do anything. The refusal is asserted by test —
  // "it would refuse" is not the same as "it refuses".
  const cfg = product.validate()
  if (cfg.problems.length) {
    console.error('MolTrace cannot start — product configuration is not valid:')
    for (const p of cfg.problems) console.error('  - ' + p)
    return app.exit(78)
  }
  if (!cfg.configured) {
    console.error('MolTrace cannot start — ' + product.unconfiguredMessage(cfg.missing))
    return app.exit(78)
  }

  // §8.2: assess the secret store BEFORE anything relies on it, and record what
  // it actually provides. `isEncryptionAvailable()` alone is not the answer — on
  // Linux it returns true while the backend is 'basic_text', which keeps its
  // password in memory rather than in a keyring. Measured, not assumed.
  const storeAssessment = keyHierarchy.assessStore({
    available: safeStorage.isEncryptionAvailable(),
    backend: typeof safeStorage.getSelectedStorageBackend === 'function'
      ? safeStorage.getSelectedStorageBackend()
      : 'n/a',
    platform: process.platform,
  })
  // Stated, never implied. This line is what a customer's IT reviewer is entitled
  // to see, and it says the same thing on every platform because none of the
  // three binds the entry to the signed application.
  console.log(`[key store] usable=${storeAssessment.usable} os-backed=${storeAssessment.osBacked} — ${storeAssessment.limitation}`)

  // §7.1: a fresh 256-bit credential every launch, over an inherited handle when
  // the service is spawned. Created here so its lifetime is exactly the app's.
  localServiceCredential = serviceCredential.create()

  applyCsp()
  const win = createWindow()
  mainWindow = win
  // Started alongside the window, not before it: the window must open whatever
  // the service does.
  startLocalService().then(() => pushReadout(win))
  win.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'))
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
