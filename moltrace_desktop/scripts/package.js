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
const { packager } = require('@electron/packager')
const product = require('../src/product.js')

const ROOT = path.join(__dirname, '..')
const FROZEN_SERVICE = path.join(ROOT, '..', 'moltrace_backend', 'dist', 'moltrace-local-service')

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
  if (!fs.existsSync(path.join(FROZEN_SERVICE, 'moltrace-local-service'))) {
    refuse(
      'the frozen local science service is not built, so the app would ship unable to read a spectrum.\n'
      + '  Build it first, from moltrace_backend:\n'
      + '    uv run --with pyinstaller pyinstaller --noconfirm --onedir --name moltrace-local-service \\\n'
      + '      --distpath dist --workpath build/pyi --specpath build/pyi \\\n'
      + '      --collect-submodules nmrcheck --collect-submodules moltrace \\\n'
      + '      --hidden-import uvicorn.protocols.http.h11_impl \\\n'
      + '      --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.loops.asyncio \\\n'
      + '      --console packaging/moltrace_local_service.py',
    )
  }

  console.log(`Packaging ${config.productName}${isPreview ? ' (PREVIEW — unsigned, unentitled)' : ''}`)

  const appPaths = await packager({
    dir: ROOT,
    out: path.join(ROOT, 'out'),
    overwrite: true,
    // UNSIGNED. Stated rather than left to a default, so that turning it on later
    // is a visible change to this line and not a silent one.
    osxSign: false,
    osxNotarize: false,
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

  for (const p of appPaths) console.log('  built: ' + p)
  console.log(
    '\nUNSIGNED. macOS will refuse it on first open: the evaluator right-clicks the app and chooses\n'
    + 'Open, then Open again in the dialog. Gatekeeper remembers the choice. This is expected for an\n'
    + 'NDA build and is not a warning about the contents.',
  )
}

main().catch((e) => { console.error(e); process.exit(1) })
