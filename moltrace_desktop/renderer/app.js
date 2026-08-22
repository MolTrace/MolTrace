'use strict'
// Renderer. No Node reach by construction — everything native comes through
// window.capabilities, the single contextBridge surface.
;(async () => {
  const el = document.getElementById('status')
  try {
    const caps = await window.moltrace.capabilities.read()
    el.textContent = `shell: ${caps.shell} — capability readout not yet populated`
  } catch (err) {
    el.textContent = `capability readout unavailable: ${err.message}`
  }
})()
