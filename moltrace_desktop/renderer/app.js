'use strict'
// Renderer. No Node reach by construction -- everything native comes through the
// single contextBridge surface in preload.js.
//
// THE SHELL IS THE PRODUCT'S OWN, not a second design. The sidebar groups, the
// module names and colours, the ModuleCard rhythm and the mono/uppercase eyebrow
// are ported from moltrace_frontend/components/app/app-sidebar.tsx and
// components/spectracheck/, so a chemist who has used the web product recognises
// this one. Where a section cannot run on this computer it is still SHOWN, with a
// true sentence about why -- a serious desktop application does not hide half of
// itself, and a missing section reads as a missing feature.

;(async () => {
  const root = document.getElementById('root')
  const SVG = 'http://www.w3.org/2000/svg'

  // ---- icons -------------------------------------------------------------
  // Drawn here rather than pulled from a library: the renderer ships no
  // dependencies and the CSP forbids remote assets. Each is a 24-unit stroke
  // glyph, matching the weight the web nav uses.
  const ICONS = {
    spectra: 'M3 12h3l2-7 4 14 3-9 2 4h4',
    shield: 'M12 3l7 3v6c0 4-3 7-7 8-4-1-7-4-7-8V6z',
    flask: 'M9 3h6M10 3v6L5 19a2 2 0 002 2h10a2 2 0 002-2l-5-10V3',
    dashboard: 'M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z',
    folder: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z',
    boxes: 'M3 8l9-5 9 5-9 5zM3 8v8l9 5 9-5V8',
    clipboard: 'M9 4h6v3H9zM7 5H5v16h14V5h-2M9 12h6M9 16h4',
    check: 'M9 4h6v3H9zM7 5H5v16h14V5h-2M8.5 13.5l2.5 2.5 4.5-5',
    file: 'M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zM14 3v5h5',
    signature: 'M4 17c3 0 3-8 6-8s3 8 6 8c2 0 3-1 4-2M4 21h16',
    package: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9',
    bot: 'M8 7h8a3 3 0 013 3v5a3 3 0 01-3 3H8a3 3 0 01-3-3v-5a3 3 0 013-3zM12 3v4M9 13h.01M15 13h.01',
    cpu: 'M7 7h10v10H7zM4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3',
    library: 'M4 4h4v16H4zM10 4h4v16h-4zM17 5l3 15',
    report: 'M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zM14 3v5h5M9 13h6M9 17h4',
    chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
    users: 'M16 19v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M9.5 9a3 3 0 100-6 3 3 0 000 6M21 19v-2a4 4 0 00-3-3.9',
    settings: 'M12 15a3 3 0 100-6 3 3 0 000 6M19 12l2-1-2-4-2 1a7 7 0 00-2-1V5h-4v2a7 7 0 00-2 1L7 7 5 11l2 1a7 7 0 000 2l-2 1 2 4 2-1a7 7 0 002 1v2h4v-2a7 7 0 002-1l2 1 2-4-2-1a7 7 0 000-2z',
    sliders: 'M4 6h16M4 12h16M4 18h16M9 4v4M15 10v4M7 16v4',
    lock: 'M7 11V8a5 5 0 0110 0v3M5 11h14v10H5z',
    panel: 'M4 5h16v14H4zM9 5v14',
    sun: 'M12 8a4 4 0 100 8 4 4 0 000-8M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
    moon: 'M20 14a8 8 0 01-10-10 8 8 0 1010 10z',
    open: 'M4 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2z',
  }

  function icon(name, cls) {
    const s = document.createElementNS(SVG, 'svg')
    s.setAttribute('viewBox', '0 0 24 24')
    s.setAttribute('fill', 'none')
    s.setAttribute('stroke', 'currentColor')
    s.setAttribute('stroke-width', '1.8')
    s.setAttribute('stroke-linecap', 'round')
    s.setAttribute('stroke-linejoin', 'round')
    s.setAttribute('aria-hidden', 'true')
    if (cls) s.setAttribute('class', cls)
    const p = document.createElementNS(SVG, 'path')
    p.setAttribute('d', ICONS[name] || ICONS.panel)
    s.append(p)
    return s
  }

  // ---- information architecture -------------------------------------------
  // The same six groups and the same order as the web sidebar. `offline` is the
  // honest statement for a section this installation cannot run: not an apology
  // and not a promise, just what is true and what to do instead. The three
  // module colours are the platform's -- teal spectroscopy, cyan regulatory,
  // violet optimization.
  const WEB = 'Sign in to MolTrace on the web to use it.'
  const GROUPS = [
    {
      label: 'Modules',
      items: [
        { id: 'spectracheck', name: 'SpectraCheck', sub: 'NMR \u00b7 MS \u00b7 structure', icon: 'spectra', rail: 'var(--mt-teal)', local: true },
        { id: 'regentry', name: 'Regentry', sub: 'Dossiers & submissions', icon: 'shield', rail: 'var(--mt-cyan)',
          offline: 'Impurity limits, dossiers and submission work are not part of this installation \u2014 the rule engine is not on this computer. ' + WEB },
        { id: 'repho', name: 'Repho', sub: 'Reaction optimization', icon: 'flask', rail: 'var(--mt-violet)',
          offline: 'Reaction campaigns and optimization runs are not part of this installation. ' + WEB },
      ],
    },
    {
      label: 'Workspace',
      items: [
        { id: 'dashboard', name: 'Dashboard', icon: 'dashboard', offline: 'The dashboard summarises work saved to your account. ' + WEB },
        { id: 'projects', name: 'Projects', icon: 'folder', offline: 'Projects live in your workspace, not on this computer. ' + WEB },
        { id: 'compounds', name: 'Compounds & Batches', icon: 'boxes', offline: 'The compound and batch registry lives in your workspace. ' + WEB },
        { id: 'actions', name: 'Action Queue', icon: 'clipboard', offline: 'The action queue is shared with your team, so it needs your workspace. ' + WEB },
        { id: 'review', name: 'Review', icon: 'check', offline: 'Review and sign-off are recorded against your account. ' + WEB },
      ],
    },
    {
      label: 'Validation Center',
      items: [
        { id: 'validation', name: 'Overview', icon: 'file', offline: 'Validation records are kept in your workspace so they can be audited. ' + WEB },
        { id: 'records', name: 'Controlled Records', icon: 'file', offline: 'Controlled records are kept in your workspace so they can be audited. ' + WEB },
        { id: 'esign', name: 'e-Signatures', icon: 'signature', offline: 'Electronic signatures are applied by the server, never by this application. ' + WEB },
        { id: 'releases', name: 'System Releases', icon: 'package', offline: 'Release records belong to the installation you signed in to. ' + WEB },
      ],
    },
    {
      label: 'AI / ML',
      items: [
        { id: 'ai', name: 'AI Services', icon: 'bot', offline: 'AI services run on the model servers, not on this computer. ' + WEB },
        { id: 'ml', name: 'Model Factory', icon: 'cpu', offline: 'Training and deployment run on the model servers. ' + WEB },
      ],
    },
    {
      label: 'Knowledge & Analytics',
      items: [
        { id: 'knowledge', name: 'Knowledge Library', icon: 'library', offline: 'The knowledge corpus is not bundled with this installation. ' + WEB },
        { id: 'reports', name: 'Reports', icon: 'report', offline: 'Reports are assembled from work saved to your account. ' + WEB },
        { id: 'roi', name: 'Automation ROI', icon: 'chart', offline: 'ROI is measured across your whole workspace, not one computer. ' + WEB },
      ],
    },
    {
      label: 'Team & Settings',
      items: [
        { id: 'team', name: 'Team', icon: 'users', offline: 'Team membership is managed in your workspace. ' + WEB },
        { id: 'settings', name: 'Settings', icon: 'settings', local: true },
        { id: 'admin', name: 'Admin', icon: 'sliders', offline: 'Administration is available to administrators of your workspace. ' + WEB },
      ],
    },
  ]
  const ITEMS = GROUPS.flatMap((g) => g.items)
  const byId = (id) => ITEMS.find((i) => i.id === id)

  // ---- state ---------------------------------------------------------------
  const state = {
    section: 'spectracheck',
    collapsed: false,
    dark: false,
    service: null,
    readout: null,
    spectrum: null,
    error: null,
    busy: false,
    everRan: false,
  }

  // ---- small builders ------------------------------------------------------
  const node = (tag, cls, text) => {
    const n = document.createElement(tag)
    if (cls) n.className = cls
    if (text != null) n.textContent = text
    return n
  }

  function card(title, desc, accent) {
    const c = node('section', 'card')
    if (accent) c.style.setProperty('--card-accent', accent)
    if (title) c.append(node('h2', 'card__title', title))
    if (desc) c.append(node('p', 'card__desc', desc))
    return c
  }

  function eyebrow(text) { return node('p', 'eyebrow', text) }

  function alert(kind, title, body) {
    const a = node('aside', 'alert alert--' + kind)
    a.append(node('p', 'alert__title', title))
    a.append(node('p', 'alert__body', body))
    return a
  }

  // ---- sidebar -------------------------------------------------------------
  function brandMark(size) {
    const s = document.createElementNS(SVG, 'svg')
    s.setAttribute('viewBox', '0 0 64 64')
    s.setAttribute('aria-hidden', 'true')
    s.setAttribute('width', String(size))
    s.setAttribute('height', String(size))
    const pts = '17.75,3.5 46.25,3.5 60.5,32 46.25,60.5 17.75,60.5 3.5,32'
    const body = document.createElementNS(SVG, 'polygon')
    body.setAttribute('points', pts); body.setAttribute('fill', '#051f3a')
    const rim = document.createElementNS(SVG, 'polygon')
    rim.setAttribute('points', pts); rim.setAttribute('fill', 'none')
    rim.setAttribute('stroke', '#26C6FF'); rim.setAttribute('stroke-width', '3')
    const m = document.createElementNS(SVG, 'text')
    m.setAttribute('x', '32'); m.setAttribute('y', '32'); m.setAttribute('dy', '0.33em')
    m.setAttribute('text-anchor', 'middle'); m.setAttribute('font-size', '34')
    m.setAttribute('font-weight', '900'); m.setAttribute('fill', '#ffffff')
    m.setAttribute('font-family', 'system-ui, sans-serif')
    m.textContent = 'm'
    s.append(body, rim, m)
    return s
  }

  function sidebar() {
    const aside = node('nav', 'sidebar')
    aside.setAttribute('aria-label', 'Sections')

    const brand = node('div', 'brand')
    brand.append(brandMark(26))
    const txt = node('div', 'brand__text')
    txt.append(node('div', 'brand__name', productName()))
    txt.append(node('div', 'brand__tag', 'Desktop'))
    brand.append(txt)
    aside.append(brand)

    for (const group of GROUPS) {
      const g = node('div', 'navgroup')
      g.append(node('div', 'navgroup__label', group.label))
      for (const item of group.items) {
        const b = node('button', 'navitem')
        b.type = 'button'
        if (item.rail) b.style.setProperty('--accent-rail', item.rail)
        if (state.section === item.id) b.setAttribute('aria-current', 'page')
        b.append(icon(item.icon, 'navitem__icon'))
        const t = node('span', 'navitem__text')
        t.append(document.createTextNode(item.name))
        if (item.sub) t.append(node('span', 'navitem__sub', item.sub))
        b.append(t)
        // A padlock, not a hidden row. Showing the whole structure and marking
        // what this installation does not carry is the honest shape: a section
        // that vanishes reads as a feature the product does not have.
        if (!item.local) b.append(icon('lock', 'navitem__lock'))
        b.title = item.name + (item.local ? '' : ' \u2014 not in this installation')
        b.addEventListener('click', () => { state.section = item.id; render() })
        g.append(b)
      }
      aside.append(g)
    }
    return aside
  }

  function productName() {
    const r = state.readout
    return (r && r.productName) || document.title || 'MolTrace'
  }

  // ---- topbar --------------------------------------------------------------
  function topbar() {
    const bar = node('header', 'topbar')

    const collapse = node('button', 'iconbutton')
    collapse.type = 'button'
    collapse.setAttribute('aria-label', state.collapsed ? 'Expand sidebar' : 'Collapse sidebar')
    collapse.append(icon('panel'))
    collapse.addEventListener('click', () => { state.collapsed = !state.collapsed; render() })
    bar.append(collapse)

    const here = byId(state.section)
    bar.append(node('strong', null, here ? here.name : ''))

    const theme = node('button', 'iconbutton')
    theme.type = 'button'
    theme.setAttribute('aria-label', state.dark ? 'Switch to light appearance' : 'Switch to dark appearance')
    theme.append(icon(state.dark ? 'sun' : 'moon'))
    theme.addEventListener('click', () => {
      state.dark = !state.dark
      document.documentElement.classList.toggle('dark', state.dark)
      render()
    })

    const pill = node('div', 'statuspill')
    const dot = node('span', 'statusdot')
    // THE BRIDGE'S OWN SHAPE IS {running, headline, detail}. I read `reachable`
    // here once by mistake -- that is the shape `describeFailure` builds INSIDE
    // the main process, not the shape that crosses the bridge -- and the pill
    // then said the service was unavailable while it was running perfectly.
    // `undefined` is falsy, so nothing threw and nothing looked wrong.
    //
    // THREE STATES, not two. Before this the first paint declared the app not set
    // up for the 2-3 seconds the service takes to come up, so a tester's first
    // impression of a working application was a broken one.
    const svc = state.service
    const st = svc == null ? 'starting'
      : svc.running ? 'ok'
      : (state.everRan ? 'down' : 'starting')
    dot.setAttribute('data-state', st)
    pill.append(dot)
    pill.append(node('span', null,
      st === 'starting' ? 'Starting analysis service'
        : st === 'ok' ? 'Analysis service running'
        : (svc && svc.headline) || 'Analysis service unavailable'))
    if (svc && svc.detail) pill.title = svc.detail
    bar.append(pill)
    bar.append(theme)
    return bar
  }

  // ---- pages ---------------------------------------------------------------
  function gatedPage(item) {
    const page = node('div', 'page')
    const head = node('div', 'page__head')
    head.append(eyebrow('MolTrace \u00b7 ' + item.name))
    head.append(node('h1', 'page__title', item.name))
    page.append(head)

    const c = card(null, null, item.rail || 'var(--mt-slate)')
    const wrap = node('div', 'gated')
    wrap.append(node('p', null, item.offline))
    wrap.append(node('p', 'gated__where',
      'This computer runs the analysis service and nothing else. Spectra you open here are read '
      + 'and measured locally, and never leave the machine.'))
    c.append(wrap)
    page.append(c)
    return page
  }

  function settingsPage() {
    const page = node('div', 'page')
    const head = node('div', 'page__head')
    head.append(eyebrow('MolTrace \u00b7 Settings'))
    head.append(node('h1', 'page__title', 'Settings'))
    head.append(node('p', 'page__sub', 'What this installation is, and what it can reach.'))
    page.append(head)

    const c = card('This installation', null, 'var(--mt-slate)')
    const meta = node('div', 'meta')
    const svc = state.service
    const rows = [
      ['Build', productName()],
      ['Analysis service', svc == null ? 'starting' : (svc.running ? 'running' : 'not running')],
      ['Appearance', state.dark ? 'dark' : 'light'],
    ]
    for (const [k, v] of rows) {
      const item = node('span', 'meta__item')
      item.append(node('span', 'meta__key', k + ' '))
      item.append(document.createTextNode(v))
      meta.append(item)
    }
    c.append(meta)
    if (svc && !svc.running && svc.detail) c.append(node('p', 'card__desc', svc.detail))
    page.append(c)
    return page
  }

  function spectraCheckPage() {
    const page = node('div', 'page')
    const head = node('div', 'page__head')
    head.append(eyebrow('MolTrace \u00b7 SpectraCheck'))
    head.append(node('h1', 'page__title', 'SpectraCheck'))
    head.append(node('p', 'page__sub',
      'Read a spectrum from this computer and measure it. Shifts, multiplicities and couplings '
      + 'are measured from the spectrum alone \u2014 nothing here is checked against a proposed structure.'))
    page.append(head)

    page.append(alert('warn', 'Human review required \u00b7 local analysis',
      'Every number below is a measurement, not an interpretation. A chemist has to read it before '
      + 'it goes into a report, and nothing here is stored for regulated use.'))

    // Step 1 -- the product's own three-card rhythm: Setup, Run, Results.
    const setup = card('Open a spectrum', null, 'var(--mt-teal)')
    setup.insertBefore(eyebrow('Step 1 \u00b7 Setup'), setup.firstChild)
    const zone = node('div', 'dropzone')
    zone.append(node('p', null, 'Choose a Bruker or Agilent/Varian acquisition, or a JCAMP-DX file.'))
    zone.append(node('p', 'dropzone__hint',
      'A Bruker acquisition is a folder; a processed spectrum may be its pdata folder on its own. '
      + 'JCAMP-DX is a single file.'))
    // `analysis__open` is kept as a hook: the end-to-end round trip clicks it and
    // then asserts fifteen product invariants through the DOM. Renaming it would
    // have turned that suite into a SKIP, which asserts nothing at all.
    const open = node('button', 'btn analysis__open')
    open.type = 'button'
    open.append(icon('open'))
    open.append(document.createTextNode(state.busy ? 'Reading\u2026' : 'Choose a spectrum'))
    open.disabled = state.busy || !(state.service && state.service.running)
    open.addEventListener('click', openSpectrum)
    zone.append(open)
    setup.append(zone)
    page.append(setup)

    if (state.error) {
      const a = alert('warn', 'That spectrum was not read', state.error)
      a.querySelector('.alert__body').classList.add('analysis__error')
      page.append(a)
    }

    const s = state.spectrum
    if (!s) {
      const empty = node('div', 'empty')
      empty.append(brandMark(46))
      empty.append(node('p', null, 'No spectrum open yet.'))
      empty.append(node('p', null, 'Open one above and its measurements appear here.'))
      const c = card(null, null, 'var(--mt-slate)')
      c.append(empty)
      page.append(c)
      return page
    }

    const results = card(null, null, 'var(--mt-teal)')
    results.insertBefore(eyebrow('Step 2 \u00b7 Results'), results.firstChild)

    // No file path on screen. The name is what the scientist chose; the path is
    // machine detail and can carry a compound name into a screenshot.
    results.append(node('h2', 'card__title result__head',
      s.file_name + ' \u2014 ' + s.nucleus + ' at ' + s.field_mhz.toFixed(2) + ' MHz'))

    // Where the numbers came from changes what they mean, so it sits WITH them
    // rather than in the caveats underneath. Three cases, not two: "your
    // instrument produced no processed spectrum" is false when it produced one
    // that could not be trusted, and sends the reader to the wrong place.
    results.append(node('p', 'card__desc result__counts',
      s.multiplets.length + ' signals resolved from ' + s.peak_count + ' fitted lines across '
      + Number(s.points).toLocaleString() + ' points. '
      + (s.processing === 'instrument'
        ? 'Read from the spectrum your instrument produced.'
        : s.processed_spectrum_rejected
          ? 'Computed here from the raw measurement \u2014 the processed spectrum in this acquisition could not be used.'
          : 'Computed here from the raw measurement \u2014 your instrument produced no processed spectrum.')))

    // ACQUISITION CONTEXT FIRST. A shift cannot be interpreted without the
    // solvent it was referenced in -- the same proton moves more than a ppm
    // between CDCl3 and DMSO-d6 -- and the reader has always parsed it.
    const meta = node('div', 'meta')
    const bits = [
      ['File', s.file_name],
      ['Nucleus', s.nucleus],
      ['Solvent', s.solvent || 'not stated in the file'],
      ['Field', Number.isFinite(s.field_mhz) && s.field_mhz > 0 ? s.field_mhz.toFixed(2) + ' MHz' : 'not stated'],
      ['Resolution', Number.isFinite(s.resolution_hz) ? s.resolution_hz.toFixed(2) + ' Hz/point' : '\u2014'],
      ['Acquired', s.acquired_at ? String(s.acquired_at).slice(0, 10) : 'not stated'],
      ['Source', s.processing === 'instrument' ? 'the instrument\u2019s own spectrum' : 'computed here from the raw measurement'],
    ]
    for (const [k, v] of bits) {
      const item = node('span', 'meta__item')
      item.append(node('span', 'meta__key', k + ' '))
      item.append(document.createTextNode(String(v)))
      meta.append(item)
    }
    results.append(meta)

    const quantifiable = s.multiplets.filter((m) => m.quantifiable)
    const detectedOnly = s.multiplets.filter((m) => !m.quantifiable)

    const kpis = node('div', 'kpis')
    const tiles = [
      ['Signals', String(s.multiplets.length), 'grouped from ' + s.peak_count + ' fitted lines'],
      ['Measurable', String(quantifiable.length), 'at or above 10x the baseline noise'],
      ['Detected only', String(detectedOnly.length), 'seen, but not strong enough to measure'],
      ['Points', Number(s.points).toLocaleString(), 'in the acquisition'],
    ]
    for (const [label, value, sub] of tiles) {
      const k = node('div', 'kpi')
      k.append(node('div', 'kpi__label', label))
      k.append(node('div', 'kpi__value', value))
      k.append(node('div', 'kpi__sub', sub))
      kpis.append(k)
    }
    results.append(kpis)
    results.append(spectrumView(s))
    page.append(results)

    if (quantifiable.length) {
      const c = card(null, null, 'var(--mt-teal)')
      c.append(peakTable(quantifiable, s, 'Signals you can measure', null))
      page.append(c)
    }
    if (detectedOnly.length) {
      const c = card(null, null, 'var(--mt-amber)')
      c.append(peakTable(detectedOnly, s, 'Detected, but not strong enough to measure',
        'These stand between ' + fmtSnr(Math.min.apply(null, detectedOnly.map((m) => m.snr)))
        + ' and ' + fmtSnr(Math.max.apply(null, detectedOnly.map((m) => m.snr)))
        + ' times the baseline noise. Real enough to see, not strong enough to read numbers off: '
        + 'a shift or an integral taken from one of these is not a measurement.'))
      page.append(c)
    }

    // The limits travel WITH the numbers and are rendered every time. A caveat
    // behind a disclosure control is a caveat most readers never see, and this
    // table is exactly the kind of thing that gets screenshotted into a slide.
    if (s.limits && s.limits.length) {
      const c = card('What this analysis cannot tell you', null, 'var(--mt-slate)')
      const ul = node('ul', 'limits result__limits')
      for (const line of s.limits) ul.append(node('li', null, line))
      c.append(ul)
      page.append(c)
    }
    return page
  }

  async function openSpectrum() {
    state.busy = true; state.error = null; render()
    try {
      const out = await window.moltrace.analysis.openSpectrum()
      if (out && out.ok) { state.spectrum = out.summary }
      else if (out && !out.cancelled) { state.error = out.reason || 'that spectrum could not be read' }
    } catch (e) {
      state.error = (e && e.message) || 'that spectrum could not be read'
    } finally {
      state.busy = false; render()
    }
  }

  // ---- render --------------------------------------------------------------
  async function render() {
    try {
      state.service = await window.moltrace.service.read()
      if (state.service && state.service.running) state.everRan = true
    } catch { /* keep the last reading rather than blanking the pill */ }
    try { state.readout = await window.moltrace.capabilities.read() } catch { /* optional */ }

    const shell = node('div', 'shell' + (state.collapsed ? ' collapsed' : ''))
    shell.append(sidebar())
    const main = node('main', 'main')
    main.append(topbar())

    const item = byId(state.section)
    if (!item) main.append(node('div', 'page'))
    else if (item.id === 'spectracheck') main.append(spectraCheckPage())
    else if (item.id === 'settings') main.append(settingsPage())
    else main.append(gatedPage(item))

    shell.append(main)
    root.replaceChildren(shell)
  }

  // Namespaced element builder. SVG nodes MUST be created in the SVG namespace or
  // the browser makes unknown HTML elements that lay out but never paint.
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
