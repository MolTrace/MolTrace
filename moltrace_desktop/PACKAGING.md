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
  --collect-submodules nmrcheck --collect-submodules moltrace \
  --hidden-import uvicorn.protocols.http.h11_impl \
  --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.loops.asyncio \
  --console packaging/moltrace_local_service.py
```

PyInstaller is pulled in just-in-time with `uv run --with` and is deliberately
absent from `pyproject.toml`, the same as `pytest-split` and `pytest-timeout`.

Roughly 230 MB, and it takes a couple of minutes. Check it refuses correctly
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

The build lands in `out/`, is about 550 MB unzipped, and is **unsigned**.

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

macOS will refuse an unsigned app: **right-click the app, choose Open, then Open
again** in the dialog. Gatekeeper remembers the choice. That warning is about the
absence of a signature, not about the contents.

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
