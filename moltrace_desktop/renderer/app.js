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

  // Survives a re-render. The service line refreshes whenever the main process
  // says something changed, and a result the scientist is reading must not
  // vanish because a background subprocess reported in.
  let lastResult = null
  let busy = false
  let lastError = null

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

    renderAnalysis(readout)
  }

  // The analysis surface. Drawn only when the capability readout says the
  // capability is available -- and the main process re-checks that on every call
  // regardless, because a hidden button is not a gate.
  function renderAnalysis(readout) {
    const cap = readout.find((c) => c.key === 'spectrum.open')
    if (!cap || !cap.available) return

    const section = document.createElement('section')
    section.className = 'analysis'

    const button = document.createElement('button')
    button.className = 'analysis__open'
    button.textContent = busy ? 'Reading…' : 'Read a spectrum…'
    button.disabled = busy
    button.addEventListener('click', openSpectrum)
    section.append(button)

    const hint = document.createElement('p')
    hint.className = 'analysis__hint'
    hint.textContent = 'Choose an acquisition folder or a JCAMP-DX file. Nothing leaves this computer.'
    section.append(hint)

    if (lastError) {
      const err = document.createElement('p')
      err.className = 'analysis__error'
      err.textContent = lastError
      section.append(err)
    }
    if (lastResult) section.append(resultView(lastResult))
    root.append(section)
  }

  async function openSpectrum() {
    busy = true; lastError = null
    await render()
    try {
      const out = await window.moltrace.analysis.openSpectrum()
      if (out.ok) { lastResult = out.summary } else if (!out.cancelled) { lastError = out.reason }
    } catch (err) {
      lastError = err.message
    } finally {
      busy = false
      await render()
    }
  }

  function resultView(s) {
    const wrap = document.createElement('div')
    wrap.className = 'result'

    const head = document.createElement('p')
    head.className = 'result__head'
    // No file path on screen. The name is what the scientist chose; the path is
    // machine detail and can carry a compound name into a screenshot.
    head.textContent = `${s.file_name} — ${s.nucleus} at ${s.field_mhz.toFixed(2)} MHz`
    wrap.append(head)

    const counts = document.createElement('p')
    counts.className = 'result__counts'
    counts.textContent =
      `${s.multiplets.length} signals resolved from ${s.peak_count} fitted lines ` +
      `across ${s.points.toLocaleString()} points.`
    wrap.append(counts)

    const table = document.createElement('table')
    table.className = 'peaks'
    const thead = document.createElement('thead')
    const hrow = document.createElement('tr')
    // "Share of signal", never "H". Without an assigned structure there is
    // nothing to normalise a proton count against, so a column headed H would be
    // a number this analysis did not compute.
    for (const label of ['', 'Shift (ppm)', 'Pattern', 'Couplings (Hz)', 'Lines', 'Share of signal']) {
      const th = document.createElement('th')
      th.textContent = label
      hrow.append(th)
    }
    thead.append(hrow); table.append(thead)

    const tbody = document.createElement('tbody')
    for (const m of s.multiplets) {
      const tr = document.createElement('tr')
      const cells = [
        m.name,
        m.center_ppm.toFixed(3),
        m.multiplicity,
        m.j_couplings_hz.length ? m.j_couplings_hz.map((j) => j.toFixed(1)).join(', ') : '—',
        String(m.line_count),
        `${(m.relative_area * 100).toFixed(1)}%`,
      ]
      for (const c of cells) {
        const td = document.createElement('td')
        td.textContent = c
        tr.append(td)
      }
      tbody.append(tr)
    }
    table.append(tbody)
    wrap.append(table)

    // The limits travel WITH the numbers, and are rendered every time. A caveat
    // behind a disclosure control is a caveat most readers never see, and this
    // table is exactly the kind of thing that gets screenshotted into a slide.
    const limits = document.createElement('ul')
    limits.className = 'result__limits'
    for (const line of s.limits || []) {
      const li = document.createElement('li')
      li.textContent = line
      limits.append(li)
    }
    wrap.append(limits)
    return wrap
  }

  await render()
  // The service starts alongside the window, so the first render happens before
  // it is up. Re-render when the main process says something changed, rather
  // than polling or delaying the window.
  window.moltrace.onChanged(() => { render() })
})()
