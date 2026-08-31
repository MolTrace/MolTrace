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
        // "NMR MS structure" is the WEB module's subtitle and it was copied
        // verbatim onto a section marked `local: true`, which reads as a promise
        // that all three run on this computer. Mass spectrometry does not: the
        // local service exposes six operations and none of them takes MS peaks,
        // so the verifier's `ms_molecule_match` test abstains on every check here.
        // The section says what this installation actually does.
        { id: 'spectracheck', name: 'SpectraCheck', sub: 'NMR \u00b7 structure', icon: 'spectra', rail: 'var(--mt-teal)', local: true },
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
    candidate: '',
    verdicts: [],
    ranking: null,
    similar: null,
    similarError: null,
    similarBusy: false,
    ranking_error: null,
    rankingBusy: false,
    verdictError: null,
    checking: false,
  }

  // EVERY field derived from the open spectrum, named once.
  //
  // openSpectrum() cleared four of these by hand and missed `similarError` and
  // `ranking_error`, so a refusal computed against the PREVIOUS sample stayed on
  // screen underneath the new one -- "none of these structures matched any of the
  // 2 measured 1H signals" is a claim about a specific spectrum, and a chemist
  // would act on it by re-typing structures that were never tested against this
  // one. Adding two more assignments would leave the next field to be forgotten
  // the same way; a list the resetters share cannot drift from itself.
  const DERIVED_FROM_SPECTRUM = [
    'verdicts', 'verdictError', 'ranking', 'ranking_error', 'similar', 'similarError',
  ]
  const EMPTY_DERIVED = { verdicts: [] }

  function clearDerived(keys) {
    for (const k of (keys || DERIVED_FROM_SPECTRUM)) {
      state[k] = Object.prototype.hasOwnProperty.call(EMPTY_DERIVED, k) ? EMPTY_DERIVED[k] : null
    }
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

  /** A column header that announces itself: no <th> here is decorative. */
  function colHead(label) {
    const th = node('th', null, label)
    th.setAttribute('scope', 'col')
    return th
  }

  /** Machine-written text, kept reachable without putting it in the reading path. */
  function rawText(label, text) {
    const d = document.createElement('details')
    d.className = 'rawtext'
    const sm = document.createElement('summary')
    sm.textContent = label
    d.append(sm, node('p', 'rawtext__body', text))
    return d
  }

  function alert(kind, title, body) {
    const a = node('aside', 'alert alert--' + kind)
    a.append(node('p', 'alert__title', title))
    a.append(node('p', 'alert__body', body))
    return a
  }

  // ---- sidebar -------------------------------------------------------------
  function brandMark(size, cls) {
    const s = document.createElementNS(SVG, 'svg')
    s.setAttribute('viewBox', '0 0 64 64')
    s.setAttribute('aria-hidden', 'true')
    // `.empty__mark` exists to hold the empty-state logo back to half opacity so
    // it reads as a placeholder rather than a second brand lockup. Nothing ever
    // set the class, so the rule matched nothing and it rendered at full weight.
    if (cls) s.setAttribute('class', cls)
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
        b.dataset.focusKey = 'nav:' + item.id
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
    collapse.dataset.focusKey = 'collapse'
    collapse.addEventListener('click', () => { state.collapsed = !state.collapsed; render() })
    bar.append(collapse)

    const here = byId(state.section)
    bar.append(node('strong', null, here ? here.name : ''))

    const theme = node('button', 'iconbutton')
    theme.type = 'button'
    theme.setAttribute('aria-label', state.dark ? 'Switch to light appearance' : 'Switch to dark appearance')
    theme.append(icon(state.dark ? 'sun' : 'moon'))
    theme.dataset.focusKey = 'theme'
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
    // Both this line and the alert below were written when the page ONLY
    // measured a spectrum, and three model-backed steps were added between them
    // without either being re-read. "Nothing here is checked against a proposed
    // structure" sat above a section that checks structures; "every number below
    // is a measurement, not an interpretation" sat above a confidence and a DP4
    // share, which are interpretations. Each says the page is one kind of thing;
    // it is two, and the split is the useful fact.
    head.append(node('p', 'page__sub',
      'Read a spectrum from this computer, measure it, and check structures against it. The '
      + 'measurements come from the spectrum alone; anything about a structure is a separate '
      + 'judgement made from them.'))
    page.append(head)

    page.append(alert('warn', 'Human review required \u00b7 local analysis',
      'The peak table is measured from the spectrum. Everything about a structure \u2014 the '
      + 'confidence, the ranking, the library matches \u2014 is a model\u2019s judgement built on '
      + 'those measurements, and can be wrong where the measurement is right. A chemist has to '
      + 'read both before either goes into a report, and nothing here is stored for regulated use.'))

    // Step 1 -- the product's own three-card rhythm: Setup, Run, Results.
    const setup = card('Open a spectrum', null, 'var(--mt-teal)')
    setup.insertBefore(eyebrow('Step 1 \u00b7 Setup'), setup.firstChild)
    // NOT A DROP TARGET, so it does not dress as one. A dashed box invites a drag,
    // and dropping here does nothing: a dropped file hands the RENDERER a path,
    // and the whole point of `openSpectrum` taking no arguments is that a page
    // which could name a path could ask this service to read anything the user
    // can read. Drag-and-drop needs that rule revisited, not a CSS border.
    const zone = node('div', 'chooser')
    zone.append(node('p', null, 'Choose a Bruker or Agilent/Varian acquisition, or a JCAMP-DX file.'))
    zone.append(node('p', 'chooser__hint',
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
    open.dataset.focusKey = 'open-spectrum'
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
      empty.append(brandMark(46, 'empty__mark'))
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
      // 0.00 MHz is a REAL reader output, not a placeholder: the FID reader
      // returns 0.0 when none of SFO1/BF1/sfrq/reffrq is present. The chip below
      // guards on exactly this and prints "not stated"; this line did not, so the
      // same spectrum was headed "at 0.00 MHz" three rows above a field reading
      // "not stated". Same guard, same wording.
      s.file_name + ' \u2014 ' + s.nucleus
      + (Number.isFinite(s.field_mhz) && s.field_mhz > 0
        ? ' at ' + s.field_mhz.toFixed(2) + ' MHz'
        : ' \u2014 frequency not stated')))

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
      ['Solvent', (s.solvent || 'not stated in the file')
        + (s.solvent_detected && s.solvent && s.solvent_detected.toLowerCase() !== s.solvent.toLowerCase()
          ? ' (peaks look like ' + s.solvent_detected + ')' : '')],
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
      ['From the compound', String(s.multiplets.filter((m) => m.category === 'compound').length),
        'the rest are solvent, impurity or artifact'],
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

    page.append(structureSection())
    page.append(rankingSection())
    const similar = similarSection()
    if (similar) page.append(similar)

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

  // ---- structure check ------------------------------------------------------
  // The deterministic verifier, run locally. It is the platform's stated sole
  // arbiter of correctness and it needs no server -- but the shift PREDICTION it
  // consumes is much weaker offline, and that caveat leads here rather than
  // trailing a list, because a confidence read without it is a number a chemist
  // could act on and should not.
  function structureSection() {
    const c = card('Check a structure against this spectrum', null, 'var(--mt-teal)')
    c.insertBefore(eyebrow('Step 3 \u00b7 Structure'), c.firstChild)
    c.append(node('p', 'card__desc',
      'Type a candidate as SMILES. It is checked against the measurements above by the same '
      + 'deterministic tests the platform uses everywhere \u2014 on this computer, and the '
      + 'structure never leaves it.'))

    const row = node('div', 'formrow')
    const input = node('input', 'input')
    input.type = 'text'
    input.placeholder = 'CCO'
    input.value = state.candidate
    input.setAttribute('aria-label', 'Candidate structure as SMILES')
    input.dataset.focusKey = 'candidate'
    input.addEventListener('input', (e) => { state.candidate = e.target.value })
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') checkStructure() })

    const go = node('button', 'btn')
    go.type = 'button'
    go.append(document.createTextNode(state.checking ? 'Checking\u2026' : 'Check structure'))
    go.disabled = state.checking || !(state.service && state.service.running)
    go.dataset.focusKey = 'check-structure'
    go.addEventListener('click', checkStructure)

    row.append(input, go)
    c.append(row)

    if (state.verdictError) c.append(alert('warn', 'That structure was not checked', state.verdictError))

    // SIDE BY SIDE, WITH THE HIT RATE. Measured on this build's own corpus, the
    // true structure scored highest in 9 of 12 carbon spectra and 3 of 8 proton
    // ones. That is useful and it is not an ordering to trust: a sorted list says
    // the top is the answer, and one carbon spectrum in four it is not. So the
    // candidates are shown together, sorted for reading, with how often this has
    // been right printed next to them.
    if (state.verdicts.length > 1) {
      const said = accuracySentence(state.verdicts[0], (state.spectrum || {}).nucleus)
      if (said) c.append(alert('info', 'How often this has been right', said))
    }

    // ONCE, NOT ONCE PER CANDIDATE. Which knowledge base answered, what predicted
    // the shifts, and that a person must read the result are facts about this
    // BUILD -- identical for every structure checked against it. Emitted inside
    // the loop they repeated byte-for-byte per candidate, so checking three
    // structures printed nine caveat blocks, and text a reader has already
    // skipped twice is text they stop reading.
    const first = state.verdicts[0] || {}
    const fkb = first.knowledge_base || {}
    if (first.prediction_coverage || first.predictor_note) {
      c.append(alert('warn', 'Read these confidences with their prediction quality',
        [first.predictor_note, first.prediction_coverage].filter(Boolean).join(' ')))
    }
    if (first.comparable_between_candidates === false) {
      // Measured: on the seed table this same path scored ethanol 0.623 against
      // ethylene glycol's own 0.556 -- the wrong molecule above the right one.
      c.append(alert('warn', 'Do not compare these numbers between structures',
        'This build is answering from a ' + (fkb.reference_count || 0).toLocaleString()
        + '-atom fallback table, and on a known spectrum that ranked a wrong structure above '
        + 'the right one. Use a number to find contradictions in one proposal, never to '
        + 'pick a winner between two \u2014 the list below is in the order you entered them.'))
    } else {
      c.append(node('p', 'tablenote',
        'Shifts predicted from the reference table shipped with this build \u2014 '
        + (fkb.reference_count || 0).toLocaleString() + ' assigned atoms from NMRShiftDB2, '
        + 'which is CC BY-SA. Predictions are a model, not a measurement.'))
    }
    if (first.human_review_required) {
      c.append(node('p', 'tablenote',
        'These are measurements combined by a stated model, not decisions. A chemist has to '
        + 'read them before they go into a report.'))
    }

    for (const v of state.verdicts) {
      const verdict = node('div', 'verdict')
      verdict.append(node('code', 'verdict__smiles', v.smiles))
      verdict.append(node('div', 'verdict__word', String(v.verdict).replace(/_/g, ' ')))
      verdict.append(node('div', 'verdict__conf',
        (v.confidence * 100).toFixed(0) + '% confidence, from a starting point of '
        + (v.prior * 100).toFixed(0) + '%'))
      c.append(verdict)
      c.append(node('p', 'card__desc', v.summary))
      if (v.summary_diagnostic) c.append(rawText('Show the engine\u2019s own words', v.summary_diagnostic))

      const table = node('table', 'peaks')
      const thead = node('thead'); const hr = node('tr')
      for (const label of ['Test', 'Applied', 'What it found']) hr.append(colHead(label))
      thead.append(hr); table.append(thead)
      const tb = node('tbody')
      for (const t of v.tests) {
        const tr = node('tr')
        tr.append(node('td', null, t.label))
        // "Not applicable" is not a failure and must not read as one: a test that
        // abstained had no data, and it did not move the confidence either way.
        //
        // NEITHER DID A TEST THAT RAN AND CARRIED NO WEIGHT. This column's own
        // reason for existing is whether the test moved the verdict, and it read
        // "yes" for a test with significance exactly 0.0 -- which moved it by
        // nothing, the same as an abstention, while looking like evidence. The
        // three states are distinct and the reader needs all three.
        tr.append(node('td', null,
          !t.applicable ? 'no data' : (t.significance > 0 ? 'yes' : 'ran, no weight')))
        // Structured first, the engine's own line one click away. `finding` is
        // built from the same fields the engine scored on; `diagnostic` is what
        // it wrote for itself.
        const found = node('td')
        found.append(node('span', null, t.finding || t.diagnostic))
        if (t.finding && t.diagnostic) found.append(rawText('engine detail', t.diagnostic))
        tr.append(found)
        tb.append(tr)
      }
      table.append(tb)
      c.append(table)

    }
    return c
  }

  function accuracySentence(v, nucleus) {
    const a = v.ranking_accuracy
    if (!a) return null
    const band = a[nucleus] || null
    if (!band) return a.note
    return 'On this build\u2019s own reference corpus the true structure scored highest in '
      + band.first + ' of ' + band.of + ' ' + nucleus + ' spectra. Read these side by side; '
      + 'the highest number is not the answer.'
  }

  // DP4, and only from the second candidate on. Its probabilities are normalised
  // across the candidates supplied and sum to one, so a DP4 figure for a single
  // structure is 1.0 and says nothing at all -- offering it for one would be
  // offering a number that cannot be wrong.
  //
  // A SECOND, INDEPENDENT reading beside the confidence above: the verifier
  // combines four tests through a Bayesian update; DP4 asks one narrower question
  // under Smith & Goodman's error model. Two methods agreeing is worth more than
  // either alone, and two disagreeing is worth knowing.
  function rankingSection() {
    const c = card('Rank these candidates by shift agreement', null, 'var(--mt-teal)')
    c.insertBefore(eyebrow('Step 4 \u00b7 Candidate ranking'), c.firstChild)

    // SHOWN EVEN WHEN IT CANNOT RUN, because hiding it made the page jump from
    // Step 3 to Step 5 and a numbered sequence with a hole in it reads as broken
    // -- the first question it drew was "what happened to 4?", which is a
    // question the page should have answered itself.
    //
    // The explanation is the real one: DP4 normalises across the candidates
    // supplied and its shares sum to one, so a ranking of one structure is 100%
    // and says nothing.
    if (state.verdicts.length < 2) {
      c.append(node('p', 'card__desc',
        'Ranking compares candidates against each other, so it needs at least two. '
        + (state.verdicts.length === 1
          ? 'Check a second structure above and this will rank them.'
          : 'Check two or more structures above and this will rank them.')))
      return c
    }

    const go = node('button', 'btn btn--secondary rank__run')
    go.type = 'button'
    go.append(document.createTextNode(state.rankingBusy ? 'Ranking\u2026' : 'Rank ' + state.verdicts.length + ' candidates'))
    go.disabled = state.rankingBusy || !(state.service && state.service.running)
    go.dataset.focusKey = 'rank'
    go.addEventListener('click', rankStructures)
    c.append(go)

    if (state.ranking_error) c.append(alert('warn', 'These were not ranked', state.ranking_error))

    const r = state.ranking
    if (!r) return c

    // NOT A PROBABILITY, and said before the numbers rather than under them.
    const basis = (r.rows[0] || {}).probability_basis
    if (!(r.rows[0] || {}).probability_is_calibrated) {
      c.append(alert('warn', 'A ranking, not a probability', basis
        + ' Errors are computed over matched peaks only, so read every error against the '
        + 'coverage beside it.'))
    }

    // WHEN THE ORDERING DOES NOT SURVIVE THE MEASUREMENT, say so above it. The
    // shares are resampled within the spectrum's own resolution; if the gap
    // between the top two ever closes to nothing, the order is an artefact of
    // how precisely the shifts happen to be known and must not be read as a
    // result.
    // THE SAME STARVED PREDICTOR RANKS THIS TABLE. Step 3 warns, on a seed
    // knowledge base, that its confidence must never pick a winner between two
    // structures -- and this card then presented a ranked table with a #1 built
    // on that identical predictor, because it never read the knowledge base the
    // service already returns beside the rows. A warning the next card silently
    // overrides is worse than no warning.
    const rkb = r.knowledge_base || {}
    if (rkb.source && rkb.source !== 'nmrshiftdb2') {
      c.append(alert('warn', 'This ranking rests on the same fallback table',
        'The shifts behind these rows come from a ' + (rkb.reference_count || 0).toLocaleString()
        + '-atom fallback table, the one Step 3 says cannot pick a winner between two structures. '
        + 'It cannot do so here either. Read the rows for contradictions, not for a first place.'))
    }

    const sep = r.separation || {}
    if (sep.checked === false && sep.unchecked_reason) {
      // Both branches below test `checked`, so an unchecked ranking rendered
      // NOTHING here -- and silence after a ranking reads as "it held".
      c.append(alert('warn', 'Whether this order survives the measurement was not tested',
        'The check re-measures the shifts within the spectrum\u2019s own resolution and watches '
        + 'whether the leader holds, but ' + sep.unchecked_reason + '. Read the order below as '
        + 'untested rather than as stable.'))
    } else if (sep.no_contest) {
      // NOT a near-tie, and it must not read like one. Only one candidate
      // matched any measured signal, so the others scored zero by having
      // nothing to score -- the gap is structural, not evidence. Saying "the
      // top two are not separated" here would understate it: there was no
      // comparison at all.
      c.append(alert('warn', 'Only one of these could be compared to this spectrum',
        'The other ' + (Math.max(0, (r.rows || []).length - 1)) + ' matched none of the measured '
        + 'signals, so they score zero for want of anything to compare, not because they were '
        + 'ruled out. A single candidate cannot be ranked \u2014 check the structures, or that '
        + 'this is the spectrum you think it is.'))
    } else if (sep.checked && !sep.separated) {
      c.append(alert('warn', 'This ranking does not separate the top two',
        'Re-measured ' + sep.resamples + ' times within this spectrum\u2019s own resolution ('
        + Number(sep.shift_uncertainty_ppm).toFixed(3) + ' ppm), '
        + (sep.leader_changed
          ? 'a different candidate comes out on top depending on the measurement. '
          : 'the gap between the leading two candidates closes to nothing. ')
        + 'The order below is not evidence for one over the other.'))
    } else if (sep.checked && sep.separated) {
      // A margin under 0.05 points prints as "0.0", so the sentence would read
      // "stayed ahead by at least 0.0 points" -- a contradiction the reader has
      // to resolve. Say "less than 0.1" instead of a rounded zero.
      const pts = Number(sep.narrowest_margin) * 100
      c.append(node('p', 'tablenote',
        'The same candidate led every one of ' + sep.resamples + ' re-measurements within this '
        + 'spectrum\u2019s own resolution, by '
        + (pts < 0.05 ? 'less than 0.1 points' : 'at least ' + pts.toFixed(1) + ' points') + '.'))
    }

    const table = node('table', 'peaks rank__table')
    const thead = node('thead'); const hr = node('tr')
    for (const label of ['#', 'Structure', 'Share', 'Matched', 'Mean error (ppm)', 'RMS (ppm)'])
      hr.append(colHead(label))
    thead.append(hr); table.append(thead)
    const tb = node('tbody')
    r.rows.forEach((row, i) => {
      const tr = node('tr')
      const structure = node('td', 'rank__smiles', row.smiles)
      structure.title = row.smiles
      const cells = [
        String(i + 1),
        structure,
        (row.probability * 100).toFixed(1) + '%',
        row.matched_peaks + ' of ' + row.observed_peaks + (row.low_coverage ? ' \u00b7 low' : ''),
        row.mean_abs_error_ppm.toFixed(2),
        row.rms_error_ppm.toFixed(2),
      ]
      for (const cell of cells) {
        tr.append(typeof cell === 'string' ? node('td', null, cell) : cell)
      }
      tb.append(tr)
    })
    table.append(tb)
    c.append(table)
    c.append(node('p', 'tablenote',
      'Ranked over the ' + r.observed_peaks + ' ' + r.nucleus + ' signals strong enough to measure '
      + 'and attributable to the compound \u2014 solvent, impurities and satellites are excluded, '
      + 'because a correct structure should not be penalised for the sample being real.'))
    return c
  }

  async function rankStructures() {
    state.rankingBusy = true; state.ranking_error = null; render()
    try {
      const out = await window.moltrace.analysis.rankStructures(state.verdicts.map((v) => v.smiles))
      if (out && out.ok) { state.ranking = out.result }
      else { state.ranking = null; state.ranking_error = (out && out.reason) || 'these could not be ranked' }
    } catch (e) {
      state.ranking = null
      state.ranking_error = (e && e.message) || 'these could not be ranked'
    } finally {
      state.rankingBusy = false; render()
    }
  }

  // A LOOKUP, NEVER AN IDENTIFICATION. Measured the way it is actually used --
  // querying with a real acquisition's measured signals, over cases where the
  // compound is in the library at all: first in 3 of 15, inside the top five in
  // 4 of 15. A lead worth following and never an answer, so the rate is printed
  // with the results rather than kept in a comment.
  //
  // This comment said 48%/63% for a while after the constant was corrected. That
  // figure came from a record-against-record leave-one-out, which is a different
  // task; the value and the rendered sentence were fixed and the PROSE around
  // them was not grepped.
  function similarSection() {
    if (!state.spectrum) return null
    const c = card('Reference spectra that look like this one', null, 'var(--mt-cyan)')
    c.insertBefore(eyebrow('Step 5 \u00b7 Library lookup'), c.firstChild)

    const go = node('button', 'btn btn--secondary similar__run')
    go.type = 'button'
    go.append(document.createTextNode(state.similarBusy ? 'Searching\u2026' : 'Find similar spectra'))
    go.disabled = state.similarBusy || !(state.service && state.service.running)
    go.dataset.focusKey = 'find-similar'
    go.addEventListener('click', findSimilar)
    c.append(go)

    if (state.similarError) c.append(alert('warn', 'No lookup was made', state.similarError))

    const r = state.similar
    if (!r) return c

    const a = r.accuracy || {}
    c.append(alert('info', 'What this is, and how often it has been right',
      'The closest of ' + r.library_size.toLocaleString() + ' reference ' + r.nucleus
      + ' spectra shipped with this build. Measured the way you are using it \u2014 a real '
      + 'acquisition\u2019s measured signals against this library, counting only cases where the '
      + 'compound is in it \u2014 the right compound came back first in ' + (a.first || 0) + ' of '
      + (a.of || 0) + ' and was inside the top five in ' + (a.top5 || 0) + ' of ' + (a.of || 0)
      + '. So most of the time it is not here. A lead to follow, never an identification, and a '
      + 'compound absent from the library still gets its five nearest neighbours back.'))

    const table = node('table', 'peaks similar__table')
    const thead = node('thead'); const hr = node('tr')
    for (const label of ['#', 'Structure', 'Reference', 'Distance', 'Lines'])
      hr.append(colHead(label))
    thead.append(hr); table.append(thead)
    const tb = node('tbody')
    r.matches.forEach((m, i) => {
      const tr = node('tr')
      // THE STRUCTURE FIRST. This showed the library's own record id -- reading
      // "DB_ID=20181476" to a chemist tells them nothing about what was matched.
      // The SMILES carry explicit hydrogens and run long, so the cell is clipped
      // and the whole string is on the element for a reader who wants it.
      const structure = node('td', 'similar__smiles', m.smiles)
      structure.title = m.smiles
      tr.append(node('td', null, String(i + 1)))
      tr.append(structure)
      tr.append(node('td', null, m.name || '\u2014'))
      // DISTANCE, and the header says so: L2 in the encoding, where lower is
      // closer. Printing it as a similarity would read backwards.
      tr.append(node('td', null, m.distance.toFixed(3)))
      tr.append(node('td', null, String(m.reference_peaks)))
      tb.append(tr)
    })
    table.append(tb)
    c.append(table)
    c.append(node('p', 'tablenote',
      'Lower distance is closer. Reference spectra from ' + (r.library_source || 'the shipped library')
      + (r.library_license ? ', ' + r.library_license : '') + '.'))
    return c
  }

  async function findSimilar() {
    state.similarBusy = true; state.similarError = null; render()
    try {
      const out = await window.moltrace.analysis.findSimilar()
      if (out && out.ok) { state.similar = out.result }
      else { state.similar = null; state.similarError = (out && out.reason) || 'no lookup could be made' }
    } catch (e) {
      state.similar = null
      state.similarError = (e && e.message) || 'no lookup could be made'
    } finally {
      state.similarBusy = false; render()
    }
  }

  async function checkStructure() {
    if (!state.candidate.trim()) {
      state.verdictError = 'Type a structure to check it against this spectrum.'
      return render()
    }
    state.checking = true; state.verdictError = null; render()
    try {
      const out = await window.moltrace.analysis.verifyStructure(state.candidate)
      if (out && out.ok) {
        // Replace a re-check of the same structure rather than stacking duplicates.
        state.verdicts = state.verdicts.filter((x) => x.smiles !== out.result.smiles)
        state.verdicts.push(out.result)
        // DO NOT ORDER BY A NUMBER THE PAGE DISOWNS. On a seed knowledge base
        // the card below says this confidence must never be used to pick a
        // winner between two structures -- and this line then ranked them by
        // exactly that, so the strongest warning on the page was contradicted by
        // the list underneath it. Measured on the seed table: ethanol 0.623 above
        // ethylene glycol's own 0.556, the wrong molecule first. When the number
        // cannot rank, the order a chemist typed them in claims nothing.
        if (state.verdicts.every((x) => x.comparable_between_candidates !== false)) {
          state.verdicts.sort((a, b) => b.confidence - a.confidence)
        }
        // The ranking is over a SET; adding a candidate changes it.
        clearDerived(['ranking', 'ranking_error'])
        state.candidate = ''
      } else {
        state.verdictError = (out && out.reason) || 'that structure could not be checked'
      }
    } catch (e) {
      state.verdictError = (e && e.message) || 'that structure could not be checked'
    } finally {
      state.checking = false; render()
    }
  }

  async function openSpectrum() {
    state.busy = true; state.error = null; render()
    try {
      const out = await window.moltrace.analysis.openSpectrum()
      if (out && out.ok) {
        state.spectrum = out.summary
        // A verdict belongs to the spectrum it was computed against.
        clearDerived()
      }
      else if (out && !out.cancelled) { state.error = out.reason || 'that spectrum could not be read' }
    } catch (e) {
      state.error = (e && e.message) || 'that spectrum could not be read'
    } finally {
      state.busy = false; render()
    }
  }

  //: Which section the DOM currently shows, so a re-render can tell a state
  //: change apart from a navigation.
  let _renderedSection = null
  // Survives the frames in which the focused control is disabled. See render().
  let _pendingFocus = null

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

    // A PREVIEW BUILD SAYS SO BEFORE ANYTHING ELSE. Someone evaluating this needs
    // to know that what unlocked these capabilities was a declaration in a build,
    // not a verified licence -- and to know it BEFORE they read any numbers. This
    // was in the previous shell and I dropped it rewriting the page; the sidebar
    // saying "MolTrace Preview" is a name, not a disclosure.
    if (Array.isArray(state.readout) && state.readout.some((c) => c.preview)) {
      main.append(node('p', 'previewbanner',
        'Preview build. Entitlement has not been verified \u2014 what this build offers is '
        + 'declared by the build itself, not confirmed by a licence.'))
    }

    const item = byId(state.section)
    if (!item) main.append(node('div', 'page'))
    else if (item.id === 'spectracheck') main.append(spectraCheckPage())
    else if (item.id === 'settings') main.append(settingsPage())
    else main.append(gatedPage(item))

    shell.append(main)

    // EVERY RENDER REPLACES THE WHOLE TREE, so without this the page jumps to the
    // top on any click -- a nav item, a theme toggle, checking a structure -- and
    // the element you just pressed loses focus. Reported as "clicking anything
    // jumps to the top and will not stay stable", which is exactly what a full
    // rebuild does: the new nodes have no scroll offset and no focus.
    //
    // Both scrollers are captured, because the sidebar has its own and a long
    // section list scrolls independently of the page.
    const previous = root.firstElementChild
    const keepScroll = previous
      ? {
          main: (previous.querySelector('.main') || {}).scrollTop || 0,
          sidebar: (previous.querySelector('.sidebar') || {}).scrollTop || 0,
        }
      : { main: 0, sidebar: 0 }
    // FOCUS INTENT MUST OUTLIVE THE DISABLED FRAME, which is why this is
    // remembered rather than re-read each time.
    //
    // Reading `activeElement` alone looks right and cannot work: a primary action
    // sets its busy flag and re-renders, the rebuilt button comes back
    // `disabled`, and `.focus()` on a disabled element is a no-op -- so focus
    // lands on <body>. When the operation settles and render() runs again,
    // <body> has no focusKey, so there is nothing left to restore and the key is
    // gone for good. The restore block ran on both renders and returned the
    // keyboard to nobody, which is the exact failure it was added to fix.
    const active = document.activeElement
    const activeKey = active && active.dataset ? active.dataset.focusKey || null : null
    if (activeKey) _pendingFocus = activeKey
    else if (active && active !== document.body) _pendingFocus = null  // the user moved on
    const focusKey = _pendingFocus
    const caret = document.activeElement && document.activeElement.tagName === 'INPUT'
      ? document.activeElement.selectionStart
      : null

    root.replaceChildren(shell)

    const mainEl = shell.querySelector('.main')
    const sideEl = shell.querySelector('.sidebar')
    // A DIFFERENT SECTION STARTS AT THE TOP. Keeping the offset across a section
    // change would drop the reader into the middle of content they have not seen,
    // which is the opposite failure to the one this fixes. The sidebar keeps its
    // own offset either way -- it did not change.
    if (mainEl) mainEl.scrollTop = state.section === _renderedSection ? keepScroll.main : 0
    _renderedSection = state.section
    if (sideEl) sideEl.scrollTop = keepScroll.sidebar
    if (focusKey) {
      const again = shell.querySelector('[data-focus-key="' + focusKey + '"]')
      // Held until it actually lands. A disabled button silently refuses focus,
      // so "we called .focus()" is not evidence the keyboard went anywhere --
      // only activeElement is.
      if (again && !again.disabled) {
        again.focus({ preventScroll: true })
        if (document.activeElement === again) _pendingFocus = null
        // A caret at position 0 after every keystroke would be worse than losing
        // focus, so it is restored where the field is still the same one.
        if (caret != null && again.tagName === 'INPUT') {
          try { again.setSelectionRange(caret, caret) } catch { /* not a text input */ }
        }
      }
    }
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

  // The engine's own category names, humanised. `13C_satellite` and
  // `residual_solvent` are exact and correct and are not what a person says.
  const CATEGORY_WORDS = {
    compound: 'compound',
    solvent: 'solvent',
    residual_solvent: 'residual solvent',
    impurity: 'impurity',
    '13C_satellite': '13C satellite',
    artifact: 'artifact',
  }
  const readableCategory = (c) => CATEGORY_WORDS[c] || String(c).replace(/_/g, ' ')

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
    // "Looks like" is what the engine already knew and never said: the compound,
    // the solvent, its residual proton, an impurity, a 13C satellite. A chemist
    // picks these out by eye on every spectrum they read.
    // THE FIRST COLUMN HAD NO NAME. It holds the signal's label -- the cell that
    // says which row you are on -- and its header was an empty string, so a
    // screen-reader user moving cell by cell heard a column name for every
    // column except the one that identifies the row. `scope="col"` is set on all
    // of them so each data cell is announced with its heading.
    for (const label of ['Signal', 'Shift (ppm)', 'Looks like', 'Pattern', 'Couplings (Hz)', 'Lines', 'Width (Hz)', 'S/N', 'Share of signal']) {
      const th = document.createElement('th')
      th.textContent = label
      th.setAttribute('scope', 'col')
      hrow.append(th)
    }
    thead.append(hrow); table.append(thead)

    const tbody = document.createElement('tbody')
    for (const m of rows) {
      const tr = document.createElement('tr')
      const cells = [
        m.name,
        m.center_ppm.toFixed(3),
        // The call and how sure it is, together. A bare label reads as certain,
        // and these run from 0.38 to 0.79 on real data. An em dash means the
        // engine did not place this line at all, which is a state, not a guess.
        m.category
          ? readableCategory(m.category) + (m.category_confidence
              ? ' (' + Math.round(m.category_confidence * 100) + '%)' : '')
          : '\u2014',
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
