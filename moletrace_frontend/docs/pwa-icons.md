# PWA Icon Handoff

The PWA manifest is configured in `src/app/manifest.ts` and currently references icon files that are not yet present in `public/icons`.

Add the following files to enable installability across browsers:

- `public/icons/icon-192.png` (192x192)
- `public/icons/icon-512.png` (512x512)
- `public/icons/maskable-icon-512.png` (512x512, maskable-safe artwork)

Notes:

- Keep artwork brand-aligned with existing MolTrace assets.
- Avoid embedding sensitive or environment-specific data in image metadata.
- Maskable icon should include adequate safe padding for Android adaptive icon cropping.
