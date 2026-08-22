'use strict'
// The ONE place a BrowserWindow is constructed. §7.1's invariants are applied
// here and nowhere else, so there is a single reviewable site.
//
// These three are not defaults to be overridden per window. `sandbox` is the
// strongest of them — it disables the Node engine at the process level — and
// Electron AUTOMATICALLY disables it when nodeIntegration is true, so the three
// are coupled and must move together or not at all.
const path = require('node:path')
const { BrowserWindow } = require('electron')

const CONFINEMENT = Object.freeze({
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  // Sub-frames inherit the same posture; an unset value here has bitten
  // other projects because the top frame looks correct in review.
  nodeIntegrationInSubFrames: false,
  webviewTag: false,
})

function createWindow(opts = {}) {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    show: false,
    ...opts,
    webPreferences: {
      ...CONFINEMENT,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  // §7.1: "Remote origins receive no native capability by default." A window that
  // is never allowed to navigate away cannot become a remote page holding local
  // authority, which is the hazard contextIsolation exists to bound.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (e) => e.preventDefault())

  return win
}

module.exports = { createWindow, CONFINEMENT }
