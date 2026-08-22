'use strict'
// Renderer. No Node reach by construction — everything native comes through
// window.moltrace, the single contextBridge surface.
//
// Renders the four upgrade states distinctly. A capability that is unavailable
// says WHY and what to do next; §4.2's four causes imply four different next
// actions, and rendering them all as one disabled control throws that away at
// the last step.
;(async () => {
  const root = document.getElementById('root')
  const status = document.getElementById('status')
  let readout
  try {
    readout = await window.moltrace.capabilities.read()
  } catch (err) {
    status.textContent = `Capabilities could not be read: ${err.message}`
    return
  }

  status.remove()
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
})()
