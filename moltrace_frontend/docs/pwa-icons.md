# PWA Icon Handoff

The PWA manifest is configured in `app/manifest.ts` and references SVG-first MolTrace logo assets with PNG fallbacks.

Current browser assets:

- `public/icon.svg` (root SVG favicon fallback)
- `public/icons/moltrace-mark.svg` (scalable MolTrace mark)
- `public/icons/moltrace-wordmark.svg` (scalable MolTrace wordmark)
- `public/icons/icon-192.png` (192x192)
- `public/icons/icon-512.png` (512x512)
- `public/icons/maskable-icon-512.png` (512x512, maskable-safe artwork)

Notes:

- Keep artwork synchronized with `components/branding/molecule-logo-mark.tsx`.
- Run `node scripts/generate-pwa-icons.mjs` after logo geometry changes.
- **Bump `PWA_ASSET_VERSION` in the same change** — it is declared in *both*
  `app/manifest.ts` and `app/layout.tsx` and must match. It is the `?v=` on every icon
  URL, so new artwork at an unchanged version is served from cache: browsers keep the old
  favicon and an installed PWA keeps the old home-screen icon. A redraw nobody sees is
  the failure mode this exists to prevent.
- Avoid embedding sensitive or environment-specific data in image metadata.
- Maskable icon should include adequate safe padding for Android adaptive icon cropping.
