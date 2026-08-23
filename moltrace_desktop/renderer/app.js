'use strict'
// Renderer. No Node reach by construction — everything native comes through
// window.moltrace, the single contextBridge surface.
//
// Renders two things, because §7.1 asks for both and they fail for different
// reasons: whether the local science service is RUNNING, and whether each
// capability is AVAILABLE. A capability can be locked while the service runs
// perfectly, and the remedies are not the same.
;(async () => {
  const root = document.getElementById('root')

  async function render() {
    root.textContent = ''

    const h = document.createElement('h1')
    h.textContent = 'MolTrace Desktop'
    root.append(h)

    // The service line.
    try {
      const svc = await window.moltrace.service.read()
      const box = document.createElement('div')
      box.className = `service service--${svc.running ? 'running' : 'stopped'}`
      box.dataset.running = String(svc.running)
      const head = document.createElement('strong')
      head.textContent = svc.headline
      const det = document.createElement('p')
      det.className = 'service__detail'
      det.textContent = svc.detail || ''
      box.append(head, det)
      root.append(box)
    } catch (err) {
      const p = document.createElement('p')
      p.textContent = `Service status unavailable: ${err.message}`
      root.append(p)
    }

    // The capabilities.
    let readout
    try {
      readout = await window.moltrace.capabilities.read()
    } catch (err) {
      const p = document.createElement('p')
      p.textContent = `Capabilities could not be read: ${err.message}`
      root.append(p)
      return
    }

    const list = document.createElement('ul')
    list.className = 'capabilities'
    for (const c of readout) {
      const li = document.createElement('li')
      li.className = `cap cap--${c.tone}`
      li.dataset.code = c.code || ''
      li.dataset.available = String(c.available)

      const name = document.createElement('strong')
      name.textContent = c.displayName
      li.append(name)

      const head = document.createElement('span')
      head.className = 'cap__headline'
      head.textContent = c.headline
      li.append(head)

      if (c.action) {
        const act = document.createElement('p')
        act.className = 'cap__action'
        act.textContent = c.action
        li.append(act)
      }
      list.append(li)
    }
    root.append(list)
  }

  await render()
  // The service starts alongside the window, so the first render happens before
  // it is up. Re-render when the main process says something changed, rather
  // than polling or delaying the window.
  window.moltrace.onChanged(() => { render() })
})()
