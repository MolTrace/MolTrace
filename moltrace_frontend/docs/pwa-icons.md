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
- Avoid embedding sensitive or environment-specific data in image metadata.
- Maskable icon should include adequate safe padding for Android adaptive icon cropping.
