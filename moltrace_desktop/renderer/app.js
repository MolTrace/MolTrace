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

    // A preview build says so before anything else on the page. Someone
    // evaluating this needs to know that what unlocked these capabilities was a
    // declaration in a development build and not a verified licence -- and they
    // need to know it before they read the numbers, not after.
    if (readout.some((c) => c.preview)) {
      const banner = document.createElement('p')
      banner.className = 'preview-banner'
      banner.textContent =
        'Preview build. Entitlement has not been verified — the products below are declared by this ' +
        'build, not confirmed by a licence.'
      root.append(banner)
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

  const SVG = 'http://www.w3.org/2000/svg'
  const el = (name, attrs) => {
    const n = document.createElementNS(SVG, name)
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v))
    return n
  }

  // The spectrum itself. A peak table with no trace beside it cannot be checked:
  // reading NMR is looking at the lines and the numbers together, and a chemist
  // handed only a table has to take every row on trust.
  function spectrumView(s) {
    const t = s.trace
    const W = 1000, H = 240, PAD_L = 8, PAD_R = 8, PAD_B = 26, PAD_T = 10
    const n = t.ppm.length
    const lo = Math.min(...t.min), hi = Math.max(...t.max)
    const span = (hi - lo) || 1
    const xAt = (i) => PAD_L + (i / (n - 1)) * (W - PAD_L - PAD_R)
    const yAt = (v) => PAD_T + (1 - (v - lo) / span) * (H - PAD_T - PAD_B)

    const fig = document.createElement('figure')
    fig.className = 'spectrum'
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'spectrum__svg', role: 'img' })
    // Named for a screen reader, which otherwise gets an unlabelled graphic.
    svg.setAttribute('aria-label',
      `${s.nucleus} spectrum from ${t.ppm[0].toFixed(1)} to ${t.ppm[n - 1].toFixed(1)} ppm, ` +
      `${s.multiplets.length} signals`)

    // The envelope as one closed shape: the top edge left-to-right, the bottom
    // edge back. Drawing only the maxima would hide negative excursions, which
    // are how a chemist sees bad phasing.
    let d = `M ${xAt(0)} ${yAt(t.max[0])}`
    for (let i = 1; i < n; i++) d += ` L ${xAt(i)} ${yAt(t.max[i])}`
    for (let i = n - 1; i >= 0; i--) d += ` L ${xAt(i)} ${yAt(t.min[i])}`
    svg.append(el('path', { d: d + ' Z', class: 'spectrum__trace' }))

    // Zero, so a baseline that is not flat is visible as such.
    if (lo < 0 && hi > 0) {
      svg.append(el('line', { x1: PAD_L, x2: W - PAD_R, y1: yAt(0), y2: yAt(0), class: 'spectrum__zero' }))
    }

    // ppm ticks. The axis runs high-to-low left-to-right, which is the direction
    // an NMR spectrum is read; reversing it makes a chemist translate every time.
    const first = t.ppm[0], last = t.ppm[n - 1]
    for (let k = 0; k <= 6; k++) {
      const i = Math.round((k / 6) * (n - 1))
      const label = t.ppm[i]
      svg.append(el('line', { x1: xAt(i), x2: xAt(i), y1: H - PAD_B, y2: H - PAD_B + 4, class: 'spectrum__tick' }))
      const txt = el('text', { x: xAt(i), y: H - PAD_B + 16, class: 'spectrum__tick-label', 'text-anchor': 'middle' })
      txt.textContent = Math.abs(first - last) > 40 ? label.toFixed(0) : label.toFixed(1)
      svg.append(txt)
    }

    // Where each reported signal sits, so a row in the table can be found on the
    // trace without counting.
    for (const m of s.multiplets) {
      const i = t.ppm.findIndex((p) => p <= m.center_ppm)
      if (i < 0) continue
      svg.append(el('line', { x1: xAt(i), x2: xAt(i), y1: PAD_T, y2: PAD_T + 8, class: 'spectrum__marker' }))
    }
    fig.append(svg)

    const cap = document.createElement('figcaption')
    cap.className = 'spectrum__caption'
    const sweep = t.sweep_ppm
    // Worth a sentence only when a MEANINGFUL part of the acquisition is off
    // screen. A 0.7 ppm trim off an 8 ppm sweep told the reader the axis had been
    // cut when what they were looking at was effectively the whole thing —
    // a caveat that fires on nothing teaches people to ignore the ones that don't.
    const hidden = Math.abs(sweep[0] - sweep[1]) - Math.abs(first - last)
    const trimmed = hidden > Math.abs(sweep[0] - sweep[1]) * 0.1
    // Rounding can MAKE a negative zero out of a real number: (-0.494).toFixed(0)
    // is "-0". Guarding the literal -0 does not catch that, so the check has to
    // be on the formatted string.
    const ppm = (v, dp) => {
      const text = v.toFixed(dp)
      return /^-0(\.0*)?$/.test(text) ? text.slice(1) : text
    }
    cap.textContent =
      `${s.nucleus}, ${ppm(first, 1)} to ${ppm(last, 1)} ppm. ` +
      // The reduction is stated. A drawn line is 1200 columns and the spectrum is
      // hundreds of thousands of points; each column spans the full height of the
      // points beneath it, so nothing is dropped, but it is not point-for-point.
      `Drawn from ${t.points_represented.toLocaleString()} points as ${n} columns, ` +
      `each spanning the full range beneath it. ` +
      // A trimmed axis that does not say so is a claim that nothing lies outside.
      (trimmed
        ? `The acquisition swept ${ppm(sweep[0], 0)} to ${ppm(sweep[1], 0)} ppm; this shows where the signals are.`
        : '')
    fig.append(cap)
    return fig
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
      `across ${s.points.toLocaleString()} points. ` +
      // Where the numbers came from changes what they mean, so it sits with them
      // rather than in the caveats underneath.
      // Three cases, not two. "Your instrument produced no processed spectrum"
      // is false when it produced one that could not be trusted — an incomplete
      // 1r is refused rather than read — and it sends the reader to the wrong
      // place: they go looking for a missing file that is sitting right there.
      (s.processing === 'instrument'
        ? 'Read from the spectrum your instrument produced.'
        : s.processed_spectrum_rejected
          ? 'Computed here from the raw measurement — the processed spectrum in this acquisition could not be used.'
          : 'Computed here from the raw measurement — your instrument produced no processed spectrum.')
    wrap.append(counts)

    // SATURATION IS A WARNING, NOT A CAVEAT. When the detector runs out of room
    // the count is a floor rather than a result, and a reader who misses that
    // will quote a number that means something else. A bullet among three others
    // is a bullet most readers skim.
    const refined = (s.multiplets || []).filter((m) => m.resolved_lines > m.line_count)
    if (refined.length) {
      const note = document.createElement('p')
      note.className = 'result__refined'
      note.textContent =
        `${refined.length} signal${refined.length === 1 ? '' : 's'} below fit as more than one line. `
        + 'The detector reports one maximum per resolvable feature, so lines closer than it can '
        + 'separate arrive as a single signal; fitting the window asks whether more than one '
        + 'explains it better than noise allows.'
      wrap.append(note)
    }

    if (s.saturated) {
      const warn = document.createElement('p')
      warn.className = 'result__warning'
      warn.textContent =
        'The peak detector reached its limit on this spectrum. The signals below are the strongest '
        + 'it could fit, not all of them — treat the count as a floor, and do not read the weakest '
        + 'rows as real.'
      wrap.append(warn)
    }

    if (s.trace && s.trace.ppm && s.trace.ppm.length > 1) wrap.append(spectrumView(s))

    const quantifiable = s.multiplets.filter((m) => m.quantifiable)
    const detectedOnly = s.multiplets.filter((m) => !m.quantifiable)

    // TWO TABLES, because these are two different claims. Detection and
    // quantitation are not the same thing and this platform draws that line
    // everywhere else; a single table presents a three-sigma bump beside a real
    // carbon as though they were the same kind of row. On a real acquisition
    // that meant 47 of 55 rows were at the detection floor — six sevenths of the
    // table was noise, and nothing on screen said so.
    if (quantifiable.length) wrap.append(peakTable(quantifiable, s, 'Signals you can measure', null))
    if (detectedOnly.length) {
      wrap.append(peakTable(detectedOnly, s, 'Detected, but not strong enough to measure',
        'These stand between ' + fmtSnr(Math.min(...detectedOnly.map((m) => m.snr)))
        + ' and ' + fmtSnr(Math.max(...detectedOnly.map((m) => m.snr)))
        + ' times the baseline noise. Real enough to see, not strong enough to read numbers off: '
        + 'a shift or an integral taken from one of these is not a measurement.'))
    }

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

  const fmtSnr = (v) => (v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1))

  function peakTable(rows, s, heading, note) {
    const section = document.createElement('section')
    section.className = 'peaks-section'
    const h = document.createElement('h2')
    h.className = 'peaks-section__heading'
    h.textContent = `${heading} (${rows.length})`
    section.append(h)
    if (note) {
      const p = document.createElement('p')
      p.className = 'peaks-section__note'
      p.textContent = note
      section.append(p)
    }

    const table = document.createElement('table')
    table.className = 'peaks'
    const thead = document.createElement('thead')
    const hrow = document.createElement('tr')
    // "Share of signal", never "H". Without an assigned structure there is
    // nothing to normalise a proton count against, so a column headed H would be
    // a number this analysis did not compute.
    // Width is here because two lines closer than the analysis can separate come
    // back as ONE, and the tell is that the signal is wider than its neighbours.
    // Not flagged automatically: on real acquisitions 14% of lines exceed three
    // times the median width and most are broad features or poor fits, so a flag
    // would cry wolf. The number is shown next to the others; a chemist reads it.
    // Signal-to-noise is in the table because it is what decides whether a row
    // is worth reading, and a peak table almost never shows it.
    for (const label of ['', 'Shift (ppm)', 'Pattern', 'Couplings (Hz)', 'Lines', 'Width (Hz)', 'S/N', 'Share of signal']) {
      const th = document.createElement('th')
      th.textContent = label
      hrow.append(th)
    }
    thead.append(hrow); table.append(thead)

    const tbody = document.createElement('tbody')
    for (const m of rows) {
      const tr = document.createElement('tr')
      const cells = [
        m.name,
        m.center_ppm.toFixed(3),
        // Empty below the limit of quantitation: the service withholds the
        // pattern and the couplings there rather than blanking them here, so an
        // em dash means "not claimed", not "not applicable".
        m.multiplicity || '—',
        m.j_couplings_hz.length ? m.j_couplings_hz.map((j) => j.toFixed(1)).join(', ') : '—',
        // "1 (2 fitted)" where a deconvolution finds more lines in the window
        // than the detector reported as maxima. Shown in the Lines column rather
        // than as a separate one: it is the same quantity, read two ways.
        m.resolved_lines > m.line_count
          ? `${m.line_count} (${m.resolved_lines} fitted)`
          : String(m.line_count),
        Number.isFinite(m.width_hz) && m.width_hz > 0 ? m.width_hz.toFixed(1) : '—',
        fmtSnr(m.snr),
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
    section.append(table)
    return section
  }

  await render()
  // The service starts alongside the window, so the first render happens before
  // it is up. Re-render when the main process says something changed, rather
  // than polling or delaying the window.
  window.moltrace.onChanged(() => { render() })
})()
