'use strict'
const path = require('node:path')
const { app, session, ipcMain } = require('electron')
const { createWindow } = require('./window-factory')
const product = require('./product')
const serviceCredential = require('./service-credential')

// Generated once per launch and held in this closure. It is NOT put on
// app.state, not exported, and never crosses the contextBridge — a renderer that
// can read it can talk to the local scientific service directly, which is the
// whole thing the transport controls exist to prevent (§7.1).
let localServiceCredential = null

// Collected per webContents id so the confinement test can assert on the
// environment each preload actually got, not on what was declared.
const confinementReports = new Map()
ipcMain.on('moltrace:confinement-self-report', (e, report) => {
  confinementReports.set(e.sender.id, report)
})
module.exports = { confinementReports }

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

  // §7.1: a fresh 256-bit credential every launch, over an inherited handle when
  // the service is spawned. Created here so its lifetime is exactly the app's.
  localServiceCredential = serviceCredential.create()

  applyCsp()
  const win = createWindow()
  win.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'))
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
