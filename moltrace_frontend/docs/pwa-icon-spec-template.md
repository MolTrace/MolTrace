# MolTrace PWA Icon Spec (Designer Handoff)

Use this spec to create the three required PWA icons:

- `public/icons/icon-192.png`
- `public/icons/icon-512.png`
- `public/icons/maskable-icon-512.png`

## 1) Required Deliverables

- **Standard icon (small)**: `icon-192.png` at `192x192` px
- **Standard icon (large)**: `icon-512.png` at `512x512` px
- **Maskable icon**: `maskable-icon-512.png` at `512x512` px

All files must be **PNG**, square, and exported at exact pixel size.

## 2) Visual Rules

- Keep the icon style aligned with MolTrace branding.
- Use high contrast so it remains legible on light/dark launch surfaces.
- Avoid tiny text; prioritize symbol/mark readability.
- Do not include screenshots, scientific data, or environment-specific details.

## 3) Safe-Zone Template (Maskable)

For `maskable-icon-512.png`, Android may crop the icon into circles/squircles.

- Canvas: `512x512`
- **Safe zone**: centered `409x409` area (80% of canvas)
- Padding outside safe zone: ~`51px` on each side

Place all critical artwork (logo mark, initials, key shape) **inside the 409x409 safe zone**.
Background can extend to full 512x512.

## 4) Practical Layout Guidance

- Preferred composition:
  - Full-bleed brand background
  - Centered MolTrace mark in safe area
- If including wordmark, keep it large and simple; avoid thin strokes.
- Check legibility at 48px preview size before final export.

## 5) Export Checklist

- [ ] Exact sizes: 192, 512, 512 (maskable)
- [ ] PNG format
- [ ] Clean edges, no unintended transparency artifacts
- [ ] Maskable file keeps critical content within center 80%
- [ ] Filenames exactly match:
  - `icon-192.png`
  - `icon-512.png`
  - `maskable-icon-512.png`

## 6) Placement in Repository

Place files in:

- `moltrace_frontend/public/icons/icon-192.png`
- `moltrace_frontend/public/icons/icon-512.png`
- `moltrace_frontend/public/icons/maskable-icon-512.png`

## 7) Quick Verification

After adding files:

1. Run the app.
2. Open browser DevTools -> **Application** -> **Manifest**.
3. Confirm all icons load with no 404 errors.
