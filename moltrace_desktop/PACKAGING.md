# Packaging the desktop app

Produces an **unsigned** build for evaluators under NDA. Two commands, in order,
and the second refuses to run if the first has not been done.

## 1. Freeze the local science service

The desktop spawns a packaged copy of the science service and talks to it over a
Unix socket. A development checkout runs it from source through `uv`; a packaged
build ships a frozen copy beside the app, because a tester has no checkout.

From `moltrace_backend/`:

```
uv run --with pyinstaller pyinstaller --noconfirm --onedir --name moltrace-local-service \
  --distpath dist --workpath build/pyi --specpath build/pyi \
  --exclude-module mypy --exclude-module pytest --exclude-module IPython \
  --exclude-module tkinter --exclude-module matplotlib \
  --hidden-import uvicorn.protocols.http.h11_impl \
  --hidden-import uvicorn.protocols.websockets.wsproto_impl \
  --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.loops.asyncio \
  --console packaging/moltrace_local_service.py
```

PyInstaller is pulled in just-in-time with `uv run --with` and is deliberately
absent from `pyproject.toml`, the same as `pytest-split` and `pytest-timeout`.

**Do NOT add `--collect-submodules nmrcheck --collect-submodules moltrace`.** It was there and it
force-included every module in both packages rather than the ones actually reachable from the
entry point — 280 of our modules instead of 58, among them the whole `moltrace.regulatory` rule
engine and `nmrcheck.api`. An evaluator would have received the regulatory engine as bytecode in
order to run a peak picker. Let PyInstaller follow the imports; add a `--hidden-import` for
anything it provably misses.

Roughly 170 MB, and it takes a couple of minutes. Check it refuses correctly
before going further — started without a socket it must name the cause and exit
78 rather than opening a port:

```
./dist/moltrace-local-service/moltrace-local-service
```

## 2. Package the app

From `moltrace_desktop/`:

```
npm run package
```

The build lands in `out/` as both the `.app` and the archive a tester actually
receives — `MolTrace-Preview-macos-<arch>.zip`, about 470 MB unpacked and **181 MB
zipped**. The archive is produced by the same command, deliberately: it used to be
made by hand with no record of how, so the deliverable could sit next to a build it
did not come from. It is written with `ditto`, not `zip`, because a macOS bundle
carries symlinks and extended attributes that a plain `zip` flattens — which
invalidates the seal — and packaging unpacks the archive again and re-verifies the
signature before reporting success.

The build is **ad-hoc sealed, not notarized**.

Pass `--config=<path>` to supply a real configuration. With no argument it builds
a **preview**: named "MolTrace Preview", declaring `previewModules`, carrying an
inert placeholder for the entitlement root key. That placeholder is honest rather
than sloppy — a preview build verifies no entitlement statement, so nothing ever
consults the key.

Two things the script will not do:

- **It never writes into the source tree.** The configured `product.json` is
  written by an `afterCopy` hook into the copied application. Writing it into
  `src/` and restoring afterwards works right up until the process dies between
  the two, and what it leaves behind is a configured `product.json` in a public
  repository waiting to be committed. It also re-checks that the file in the tree
  is still inert before finishing.
- **It will not package a build that claims the brand while declaring preview
  products**, or one carrying private key material. It runs the same
  `product.validate()` the app runs at launch, so the two cannot drift.

## What a tester does on first launch

macOS will refuse an unsigned app: open **System Settings > Privacy & Security**,
find the blocked app near the bottom of that pane, and choose **Open Anyway**.
macOS remembers the choice. That refusal is about the absence of a *trusted*
signature, not about the contents.

This used to say "right-click, choose Open". That instruction did not work, and
the reason is worth recording. `@electron/packager` renames the `Electron` binary
and rewrites `Info.plist` after the prebuilt binary was linker-signed, which
invalidates the signature the bundle inherited: it shipped with
`Identifier=Electron`, no `Contents/_CodeSignature` at all, and `codesign -v`
answering *"code has no resources but signature indicates they must be present"* —
an error, not a policy verdict. macOS reads that as a damaged app, and the
right-click route never reaches a dialog with an Open button in it. Packaging now
re-seals each bundle ad-hoc (`signAdHoc` in `scripts/package.js`), which restores
a valid seal and moves the refusal back to the ordinary untrusted-developer case
the step above clears. Ad-hoc is **not** distribution signing and does not make
macOS trust the build; `osxSign` stays `false`, so switching on real signing
remains a visible change to that one line.

The window says **"Preview build. Entitlement has not been verified"** and shows
one capability available and one locked. That is correct: a preview build
declares no reference data, so the regulated path stays gated on a rule pack it
genuinely does not have.

Analysis runs entirely on the tester's machine. Nothing about reading a spectrum
reaches the network.

## What is not covered

The build is unsigned and not notarized, so it cannot be distributed outside a
group willing to click through Gatekeeper. There is no updater — the update feed
is `null` in every build from this repository. Only macOS arm64 has been built
and run; the packager takes `--platform`/`--arch`, but nothing else has been
tested.
