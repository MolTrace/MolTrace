'use strict'
// Renderer. No Node reach by construction — everything native comes through
// window.capabilities, the single contextBridge surface.
;(async () => {
  const el = document.getElementById('status')
  try {
    const caps = await window.moltrace.capabilities.read()
    const open = caps.filter((c) => c.available)
    el.textContent = open.length
      ? `${open.length} of ${caps.length} capabilities available`
      : caps[0]?.reason || 'No capabilities are available yet.'
  } catch (err) {
    el.textContent = `capability readout unavailable: ${err.message}`
  }
})()
