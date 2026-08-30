'use strict'
// Packaging, for evaluators under NDA. UNSIGNED, deliberately and visibly.
//
// Two things this script will not do, because both have a way of happening by
// accident and neither is recoverable once it ships:
//
//   1. IT NEVER WRITES INTO THE SOURCE TREE. The configured product.json is
//      written by an afterCopy hook, into the COPIED application only. Writing it
//      into src/ and restoring afterwards works right up until the process dies
//      between the two, and what it leaves behind is a configured product.json
//      sitting in a public repository waiting to be committed.
//   2. IT REFUSES TO PACKAGE A BUILD THAT CLAIMS THE BRAND WHILE DECLARING
//      PREVIEW PRODUCTS, and refuses one carrying private key material, by
//      running the same product.validate() the app runs at launch. A packaging
//      script with its own weaker idea of validity is how the two drift.
//
// A preview build needs NO real key material. It verifies no entitlement
// statement — `previewWorld()` returns `entitlement: null` and a named branch in
// assess() handles it — so the root key is never consulted. The placeholder
// below is inert and says so in its own value.
const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { packager } = require('@electron/packager')
const product = require('../src/product.js')

const ROOT = path.join(__dirname, '..')
const FROZEN_SERVICE = path.join(ROOT, '..', 'moltrace_backend', 'dist', 'moltrace-local-service')

// Named once because two refusals below quote it, and a runbook that drifts from
// the command it documents is worse than no runbook.
// THE SHIFT-PREDICTION TABLE RIDES WITH THE SERVICE. Without it the predictor
// answers from a bundled 16-molecule seed, and the difference decides whether the
// product works: median 13C uncertainty ~35 ppm against ~1.9 ppm. Measured on one
// acquisition with four candidate structures, the seed ranked the WRONG molecule
// first (ethanol 0.623 over ethylene glycol's 0.556); with the table the right one
// wins at 0.939 and aspirin is called inconsistent at 0.166.
//
// 14 MB gzipped against a 185 MB artifact, loaded lazily in 1.3 s on the first
// structure check rather than at startup.
const KNOWLEDGE_BASE = path.join(
  require('node:os').homedir(), '.cache', 'moltrace', 'nmrnet', 'hose_index.json.gz',
)

// The reference spectra the library lookup searches. 1.5 MB gzipped for 43,516
// records, shipped as SHIFT LISTS rather than encoded vectors: 45 MB of float32
// would be thirty times the size, and an index cannot detect that the encoder
// changed underneath it while source shifts re-encode correctly whatever it does
// next. Encoded lazily at first lookup, in about a second.
const SPECTRUM_LIBRARY = path.join(
  require('node:os').homedir(), '.cache', 'moltrace', 'nmrnet', 'spectrum_library.json.gz',
)

const REFREEZE_COMMAND =
  '    uv run --with pyinstaller pyinstaller --noconfirm --onedir --name moltrace-local-service \\\n'
  + '      --distpath dist --workpath build/pyi --specpath build/pyi \\\n'
  + '      --collect-submodules nmrcheck --collect-submodules moltrace \\\n'
  + '      --add-data "' + KNOWLEDGE_BASE + ':." \\\n'
  + '      --add-data "' + SPECTRUM_LIBRARY + ':." \\\n'
  // The licence travels WITH the data it covers. A CC BY-SA table redistributed
  // without its attribution is the obligation broken, and a NOTICE that lives
  // only in the source repository does not reach whoever holds the artifact.
  //
  // ABSOLUTE, because PyInstaller resolves a relative --add-data source against
  // the --specpath, not the working directory. A bare 'NOTICE' looked for it in
  // build/pyi/ and logged one ERROR line in a long build that still exited 0.
  + '      --add-data "' + path.join(ROOT, '..', 'moltrace_backend', 'NOTICE') + ':." \\\n'
  + '      --hidden-import uvicorn.protocols.http.h11_impl \\\n'
  + '      --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.loops.asyncio \\\n'
  + '      --console packaging/moltrace_local_service.py'

// What the frozen entry point actually pulls in: packaging/moltrace_local_service.py
// -> nmrcheck.local_service_main -> nmrcheck.local_science -> moltrace.spectroscopy.
// Scoped to exactly that, because gating on all of moltrace_backend/src would demand
// a re-freeze for an api.py edit that cannot change a single number a tester sees —
// and an obstructive gate is one that gets bypassed.
const FROZEN_SCIENCE_SURFACE = [
  'moltrace_backend/src/nmrcheck/local_service_main.py',
  'moltrace_backend/src/nmrcheck/local_science.py',
  'moltrace_backend/src/moltrace/spectroscopy',
]

const PREVIEW_CONFIG = {
  _comment:
    'PREVIEW BUILD — not a licensed installation. Generated at package time and never committed. '
    + 'The entitlement root key below is an inert placeholder: a preview build verifies no statement, '
    + 'so nothing consults it. A real installation carries a real one and does not carry previewModules.',
  productName: 'MolTrace Preview',
  workspaceUrl: 'https://moltrace.co',
  entitlementRootPublicKey: 'ed25519:0000000000000000000000000000000000000000000000000000000000000000',
  entitlementRootKeyId: 'mtroot1:preview-placeholder',
  previewModules: ['spectracheck'],
}

function refuse(why) {
  console.error('\nRefusing to package — ' + why)
  process.exit(1)
}

// The freeze is built by hand, so nothing forces it to be newer than the science it
// claims to contain. That gap is not theoretical: the preview zip written at 07:49 on
// 2026-08-29 carried a freeze from 07:48, and `fix(gsd): a fitted line may refine its
// position, not walk onto its neighbour` landed at 09:56 — its hunks inside
// `gsd_peak_pick` itself, which local_science.py calls directly. So the artifact
// reported peak positions from before the fix, and nothing in it said so.
//
// The comparison is exact rather than a tolerance: a freeze older than the source it
// packages IS stale, so there is no window to choose and no round number to defend.
function scienceNewerThanFreeze(frozenBinary) {
  const repo = path.join(ROOT, '..')
  const frozenAt = Math.floor(fs.statSync(frozenBinary).mtimeMs / 1000)
  const git = (args) => execFileSync('git', args, { cwd: repo, encoding: 'utf8' })
  // WHAT MAKES A FREEZE STALE IS THE SOURCE ON DISK, NOT WHEN SOMEONE TYPED
  // `git commit`. This asked git for commits DATED after the freeze, which meant
  // the natural order -- freeze, verify, commit -- always tripped it: the freeze
  // built at 11:42 from the tree that became a commit at 11:45 was reported as
  // three minutes behind code it already contained. That is a gate that cries
  // wolf, and a gate that cries wolf gets bypassed.
  //
  // So the verdict is now the file mtimes, which is the question that was always
  // being asked. Commits are still listed, but only the ones whose files are
  // ACTUALLY newer on disk, so the refusal names something real.
  const changed = []
  const walk = (rel) => {
    const abs = path.join(repo, rel)
    let stat
    try { stat = fs.statSync(abs) } catch { return }
    if (stat.isDirectory()) {
      for (const entry of fs.readdirSync(abs)) {
        if (entry === '__pycache__' || entry.startsWith('.')) continue
        walk(path.join(rel, entry))
      }
      return
    }
    if (!/\.(py|json|gz)$/.test(rel)) return
    if (stat.mtimeMs / 1000 > frozenAt) changed.push(rel)
  }
  for (const rel of FROZEN_SCIENCE_SURFACE) walk(rel)

  let commits = []
  try {
    if (changed.length) {
      commits = git(['log', `--since=@${frozenAt}`, '--format=%h %ad %s',
        '--date=format-local:%Y-%m-%d %H:%M', '--', ...FROZEN_SCIENCE_SURFACE])
        .split('\n').map((l) => l.trim()).filter(Boolean)
    } else {
      // Proves git answers here, so an unreadable repository still fails closed
      // rather than reporting a fresh freeze it never checked.
      git(['rev-parse', 'HEAD'])
    }
  } catch (err) {
    return { checked: false, why: String(err.message).trim().split('\n')[0] }
  }
  // A tracked file edited but not yet committed is exactly as stale, and in a worktree
  // shared with other sessions that is the ordinary case rather than the exotic one.
  let dirty = []
  try {
    dirty = git(['diff', '--name-only', 'HEAD', '--', ...FROZEN_SCIENCE_SURFACE])
      .split('\n').map((l) => l.trim()).filter(Boolean)
      .filter((rel) => {
        try { return fs.statSync(path.join(repo, rel)).mtimeMs / 1000 > frozenAt } catch { return false }
      })
  } catch { /* the commit query already proved git answers here */ }
  return { checked: true, frozenAt, commits, dirty, changed }
}

// AD-HOC SIGNING IS NOT DISTRIBUTION SIGNING, and `osxSign` below stays false:
// turning real signing on is still a visible change to that one line. This fixes
// a different failure that looks the same from a distance.
//
// @electron/packager renames the `Electron` binary to the product name and
// rewrites Info.plist AFTER the prebuilt binary was linker-signed. That
// invalidates the signature it inherited. The bundle then ships with
// `Identifier=Electron`, no `Contents/_CodeSignature` directory at all, and
// `codesign -v` reporting "code has no resources but signature indicates they
// must be present" — an ERROR, not the ordinary policy verdict. macOS presents
// that as a damaged app, and the right-click-Open route does not recover it: the
// evaluator never reaches a dialog with an Open button in it.
//
// Re-signing ad-hoc restores a valid seal over the renamed bundle. Measured on
// this build: "code has no resources..." before, "valid on disk / satisfies its
// Designated Requirement" after, with `spctl` moving from an error to a plain
// `rejected`. Still untrusted — which is correct for an unsigned NDA preview —
// but now untrusted in the class the tester can actually get past.
function signAdHoc(appPath) {
  execFileSync('codesign', ['--force', '--deep', '--sign', '-', appPath], { stdio: 'pipe' })
  // Prove the seal landed rather than trusting the exit code, in the same spirit
  // as the product.json check above. A signature that did not take is exactly the
  // state this function exists to prevent, so it must not be assumed.
  try {
    execFileSync('codesign', ['--verify', '--deep', appPath], { stdio: 'pipe' })
  } catch (e) {
    throw new Error('the ad-hoc signature did not verify after signing: ' + String(e.stderr || e.message).trim())
  }
}

// THE ARTIFACT A TESTER RECEIVES IS THE ZIP, and nothing here used to produce it.
// The `.app` was rebuilt by this script while the zip beside it was made by hand at
// some earlier point, with no record of how and no relationship between the two --
// so the deliverable could silently lag the build it sits next to. That is the same
// shape as the stale freeze this script already refuses, one level further out.
//
// `ditto`, not `zip`: a macOS bundle carries symlinks (Contents/MacOS ->
// Versions/Current) and extended attributes, and a plain `zip` flattens them, which
// invalidates the seal the step above just applied. `--keepParent` puts the .app at
// the archive root so the tester unzips one obvious thing.
function archiveApp(appPath, outDir, config) {
  const base = String(config.productName).replace(/\s+/g, '-')
  const zipPath = path.join(outDir, `${base}-macos-${process.arch}.zip`)
  fs.rmSync(zipPath, { force: true })
  execFileSync('ditto', ['-c', '-k', '--sequesterRsrc', '--keepParent', appPath, zipPath], {
    stdio: 'pipe',
  })
  // Prove it round-trips WITH its signature intact rather than trusting ditto. An
  // archive that strips the seal recreates exactly the "damaged app" the signing
  // step exists to prevent, and it would not be visible until a tester tried it.
  const check = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'moltrace-zip-'))
  try {
    execFileSync('ditto', ['-x', '-k', zipPath, check], { stdio: 'pipe' })
    const unpacked = path.join(check, path.basename(appPath))
    execFileSync('codesign', ['--verify', '--deep', unpacked], { stdio: 'pipe' })
  } catch (e) {
    throw new Error(
      'the archive did not round-trip with a valid signature: ' + String(e.stderr || e.message).trim(),
    )
  } finally {
    fs.rmSync(check, { recursive: true, force: true })
  }
  return zipPath
}

// THE ICON IS BUILT, NOT COMMITTED. It is derived from the product's own masked
// mark in the frontend, so the desktop and the web wear the same face and cannot
// drift into two: a checked-in .icns is a 1.6 MB binary that nothing regenerates
// when the mark changes, and the first person to update the brand would not know
// this file existed.
//
// 512 is the largest MASKED source that exists. The 1024 slot is interpolated
// from it and macOS only reaches it on a Retina 512pt draw. The unmasked 1024
// render is deliberately not used: deriving the hexagon from it leaves the dark
// facets transparent, which is why the repo's own generator constructs the mask
// rather than detecting it.
const ICON_SOURCE = path.join(
  ROOT, '..', 'moltrace_frontend', 'public', 'icons', 'moltrace-mark-3d-hex-512.png',
)
const ICONSET_SIZES = [
  [16, '16x16'], [32, '16x16@2x'], [32, '32x32'], [64, '32x32@2x'],
  [128, '128x128'], [256, '128x128@2x'], [256, '256x256'], [512, '256x256@2x'],
  [512, '512x512'], [1024, '512x512@2x'],
]

function buildIcon() {
  if (process.platform !== 'darwin') return null
  if (!fs.existsSync(ICON_SOURCE)) {
    console.log('  no icon source at ' + ICON_SOURCE + ' — packaging without an icon')
    return null
  }
  const buildDir = path.join(ROOT, 'build')
  const iconset = path.join(buildDir, 'MolTrace.iconset')
  const icns = path.join(buildDir, 'icon.icns')
  // Returned WITHOUT the extension: @electron/packager appends the per-platform
  // one itself, and handing it a path that already ends in .icns made it look for
  // 'icon.icns.icon' and skip the icon with only a warning.
  fs.rmSync(iconset, { recursive: true, force: true })
  fs.mkdirSync(iconset, { recursive: true })
  for (const [px, name] of ICONSET_SIZES) {
    execFileSync('sips', ['-z', String(px), String(px), ICON_SOURCE,
      '--out', path.join(iconset, `icon_${name}.png`)], { stdio: 'pipe' })
  }
  // iconutil refuses the whole set if one required name is missing, so the count
  // is checked here rather than discovered as an opaque "Failed to generate ICNS".
  const written = fs.readdirSync(iconset).filter((n) => n.endsWith('.png')).length
  if (written !== ICONSET_SIZES.length) {
    throw new Error(`icon set has ${written} of ${ICONSET_SIZES.length} sizes`)
  }
  execFileSync('iconutil', ['-c', 'icns', iconset, '-o', icns], { stdio: 'pipe' })
  return path.join(buildDir, 'icon')
}

async function main() {
  const overlayPath = process.argv.find((a) => a.startsWith('--config='))
  const config = overlayPath
    ? JSON.parse(fs.readFileSync(overlayPath.slice('--config='.length), 'utf8'))
    : PREVIEW_CONFIG

  // The SAME validation the app runs at launch. A build that would refuse to
  // start should never reach a tester's machine in the first place.
  const verdict = product.validate(config)
  if (verdict.problems.length) refuse('the configuration is not valid:\n  - ' + verdict.problems.join('\n  - '))
  if (!verdict.configured) refuse('the configuration is incomplete and the app would refuse to start: missing ' + verdict.missing.join(', '))

  const isPreview = Array.isArray(config.previewModules) && config.previewModules.length > 0
  if (!isPreview && !overlayPath) refuse('the built-in configuration is a preview and declares no products')

  // A packaged app with no service can start, and can do nothing. That is worse
  // than not shipping: an evaluator reads it as the product being empty.
  const frozenBinary = path.join(FROZEN_SERVICE, 'moltrace-local-service')
  if (!fs.existsSync(frozenBinary)) {
    refuse(
      'the frozen local science service is not built, so the app would ship unable to read a spectrum.\n'
      + '  Build it first, from moltrace_backend:\n'
      + REFREEZE_COMMAND,
    )
  }

  // A FREEZE WITHOUT THE TABLE IS NOT A SMALLER BUILD, IT IS A DIFFERENT PRODUCT.
  // The predictor falls back to a 16-molecule seed and says so only in a warning
  // most readers will not reach, while every structure verdict quietly loses the
  // ability to tell a right answer from a wrong one. Refusing here is the same
  // judgement as refusing a stale freeze: the artifact must not be able to look
  // finished while answering from the wrong table.
  const frozenKb = ['hose_index.json.gz', 'hose_index.json']
    .map((n) => path.join(FROZEN_SERVICE, '_internal', n))
    .find((p) => fs.existsSync(p))
  if (!frozenKb) {
    refuse(
      'the frozen service carries no shift-prediction table, so it would answer every\n'
      + '  structure check from the 16-molecule seed -- which ranked a WRONG molecule first\n'
      + '  on the one acquisition we can check against. Re-freeze with the table:\n'
      + REFREEZE_COMMAND,
    )
  }

  // The attribution must be inside the artifact, not only in the repository: the
  // table is CC BY-SA and the person holding the build is the one who needs the
  // licence terms.
  const frozenLibrary = fs.existsSync(path.join(FROZEN_SERVICE, '_internal', 'spectrum_library.json.gz'))
  if ((frozenKb || frozenLibrary) && !fs.existsSync(path.join(FROZEN_SERVICE, '_internal', 'NOTICE'))) {
    refuse(
      'the frozen service carries NMRShiftDB2-derived data -- the prediction table, the\n'
      + '  reference spectrum library, or both -- but not the\n'
      + '  NOTICE that licenses it. That table is CC BY-SA and redistributing it without\n'
      + '  its attribution breaks the obligation. Re-freeze with the NOTICE:\n'
      + REFREEZE_COMMAND,
    )
  }

  // A freeze that exists is not a freeze that is current. Presence was the only test
  // here, which is how a zip went out carrying peak fitting two commits behind the
  // source beside it — undetectable from inside the artifact, because nothing in the
  // build records which science it holds.
  const freshness = scienceNewerThanFreeze(frozenBinary)
  if (!freshness.checked) {
    // Fail closed. Packaging on an unanswerable check ships science of unknown vintage,
    // which is the exact silence this gate exists to break. The override is deliberately
    // wordy: it should read as a statement someone made, not a flag they reached for.
    if (!process.argv.includes('--allow-unverified-freeze')) {
      refuse(
        'the frozen service could not be checked against the source it packages (' + freshness.why + ').\n'
        + '  Re-run where git can answer, or pass --allow-unverified-freeze to state that you\n'
        + '  accept shipping a freeze of unverified vintage.',
      )
    }
    console.log('WARNING: freeze vintage unverified (' + freshness.why + ') — proceeding as instructed')
  } else if (freshness.changed.length) {
    // Local, to match git's format-local above. Printing the freeze in UTC beside
    // commit times in local time made this refusal read as though the commits came
    // BEFORE the freeze — the gate looked broken at exactly the moment it was right.
    const d = new Date(freshness.frozenAt * 1000)
    const pad = (n) => String(n).padStart(2, '0')
    const frozenAt = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
      + `${pad(d.getHours())}:${pad(d.getMinutes())}`
    const detail = []
    if (freshness.commits.length) {
      detail.push('  committed since the freeze:')
      for (const c of freshness.commits) detail.push('    ' + c)
    }
    if (freshness.dirty.length) {
      detail.push('  uncommitted, and newer than the freeze:')
      for (const f of freshness.dirty) detail.push('    ' + f)
    }
    // No override on this branch, on purpose. An escape hatch on the real condition is
    // the one that gets used reflexively, and shipping stale science is not a judgement
    // call a hurried packaging run should be able to make.
    refuse(
      'the frozen science service is older than the science it would ship.\n'
      + '  frozen at ' + frozenAt + ', and superseded by:\n'
      + detail.join('\n') + '\n'
      + '  A tester cannot tell which of these produced an answer, and neither can their\n'
      + '  bug report. Re-freeze from moltrace_backend:\n'
      + REFREEZE_COMMAND,
    )
  }

  const iconPath = buildIcon()
  if (iconPath) console.log('  icon: built from the product mark')

  console.log(`Packaging ${config.productName}${isPreview ? ' (PREVIEW — unsigned, unentitled)' : ''}`)

  const appPaths = await packager({
    dir: ROOT,
    out: path.join(ROOT, 'out'),
    overwrite: true,
    // UNSIGNED. Stated rather than left to a default, so that turning it on later
    // is a visible change to this line and not a silent one.
    osxSign: false,
    osxNotarize: false,
    // THE APP HAD NO ICON AT ALL, so macOS drew the generic Electron document in
    // the Dock, in Finder and in the switcher -- the first thing a tester sees,
    // and it says "someone's prototype" before the window even opens.
    //
    // Built from the product's own masked mark
    // (moltrace_frontend/public/icons/moltrace-mark-3d-hex-512.png) rather than a
    // redraw, so the desktop and the web wear the same face. 512 is the largest
    // masked source that exists; the 1024 slot is interpolated from it, which
    // macOS only reaches on a Retina 512pt draw. Regenerate with the recipe in
    // PACKAGING.md if the mark ever changes.
    icon: iconPath || undefined,
    name: config.productName,
    appVersion: require('../package.json').version,
    // The frozen service rides in Resources/service/; local-service.js looks for
    // it there and falls back to running from source when it is absent.
    extraResource: [FROZEN_SERVICE],
    // Tests, build scripts and internal documentation are not part of the
    // product. PACKAGING.md in particular is a runbook for whoever builds this,
    // and shipping it inside the artifact it describes is just noise on an
    // evaluator's disk.
    ignore: [
      /^\/out($|\/)/, /^\/test($|\/)/, /^\/scripts($|\/)/,
      /^\/\.git($|\/)/, /^\/\.gitignore$/, /^\/[^/]*\.md$/,
    ],
    afterCopy: [
      // v20 passes ONE options object and awaits the promise — the older
      // (buildPath, version, platform, arch, callback) signature silently yields
      // an undefined buildPath rather than an error you can read.
      async ({ buildPath }) => {
        // Written HERE, into the copy. The source tree is never touched.
        const target = path.join(buildPath, 'src', 'product.json')
        fs.writeFileSync(target, JSON.stringify(config, null, 2) + '\n')
        // Prove it landed rather than trusting the write, and prove the inert
        // one in the repository is still inert.
        const written = JSON.parse(fs.readFileSync(target, 'utf8'))
        if (written.productName !== config.productName) throw new Error('the packaged config did not take')
        const source = JSON.parse(fs.readFileSync(path.join(ROOT, 'src', 'product.json'), 'utf8'))
        if (product.REQUIRED_FOR_LAUNCH.some((k) => source[k] !== null)) {
          throw new Error('the product.json in the SOURCE TREE is no longer inert — refusing to continue')
        }
      },
    ],
  })

  for (const p of appPaths) {
    // macOS only. On other platforms there is nothing to re-seal and codesign
    // does not exist, so asking for it would fail the build for no reason.
    if (process.platform === 'darwin') {
      for (const app of fs.readdirSync(p).filter((n) => n.endsWith('.app'))) {
        signAdHoc(path.join(p, app))
      }
    }
    console.log('  built: ' + p)
    if (process.platform === 'darwin') {
      for (const app of fs.readdirSync(p).filter((n) => n.endsWith('.app'))) {
        const zip = archiveApp(path.join(p, app), path.join(ROOT, 'out'), config)
        const mb = (fs.statSync(zip).size / (1024 * 1024)).toFixed(0)
        console.log(`  archived: ${zip} (${mb} MB)`)
      }
    }
  }
  console.log(
    '\nUNSIGNED — ad-hoc sealed, not notarized. macOS will still refuse it on first open, and that\n'
    + 'refusal is expected for an NDA build rather than a warning about the contents. The evaluator\n'
    + 'opens System Settings > Privacy & Security, finds the blocked app near the bottom, and chooses\n'
    + 'Open Anyway. macOS remembers the choice.',
  )
}

// Exported so the freshness gate can be tested rather than trusted. A guard nobody
// can run both ways is indistinguishable from one that always fires.
module.exports = { scienceNewerThanFreeze, signAdHoc, FROZEN_SCIENCE_SURFACE, FROZEN_SERVICE }

if (require.main === module) {
  main().catch((e) => { console.error(e); process.exit(1) })
}
