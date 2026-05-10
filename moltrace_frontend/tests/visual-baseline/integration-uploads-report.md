# SpectraCheck integration — 2026-05-10T15:32:47.527Z

- Pass: 29
- Fail: 0

| Tab | Check | Status | Detail |
|---|---|---|---|
| Processed | Default nucleus 1H sent on Preview | ✓ |  |
| Processed | Pill switch 1H → 13C reflected in Analyze FormData | ✓ |  |
| Processed | MHz=600 + nucleus=1H both reflected in next FormData | ✓ |  |
| Processed | Background job carries current nucleus + MHz in JSON | ✓ |  |
| Raw FID | Default nucleus=1H vendor=auto on Preview | ✓ |  |
| Raw FID | Pill switch → vendor=bruker + preserve_raw=true in Process FormData | ✓ |  |
| Raw FID | Pill switch → vendor=agilent in Preview FormData | ✓ |  |
| Raw FID | Pills are independent (nucleus=13C vendor=agilent both stick) | ✓ |  |
| Raw FID | BG job JSON: nucleus=13C, vendor=auto, preset=no_baseline_correction, preserve_raw=true | ✓ |  |
| Spectrum | Spectrum extends to full page width (≥70% of main) | ✓ |  |
| Spectrum | Vertical gain rail rendered on right side with vertical slider | ✓ |  |
| Spectrum | Wheel scroll on gain rail adjusts gain (touchpad) | ✓ |  |
| Spectrum | Vertical gain slider responds to keyboard (ArrowUp) | ✓ |  |
| Spectrum | Taller peaks button increases combined gain × yZoom in rail readout | ✓ |  |
| Spectrum | Y-axis range stays anchored when gain increases (peaks grow within fixed axis) | ✓ |  |
| Spectrum | Full spectrum button resets gain + yZoom + xRange | ✓ |  |
| Spectrum | Plotly modebar disabled (custom draggable toolbar replaces it) | ✓ |  |
| Spectrum | Spectrum chart container is position:sticky (stays in view on scroll) | ✓ |  |
| Spectrum | Default gain after Reset is 1× (compact view) | ✓ |  |
| Spectrum | Floating draggable toolbar present with grab cursor handle | ✓ |  |
| Spectrum | Toolbar can be dragged with mouse pointer | ✓ |  |
| Spectrum | Floating toolbar buttons remain functional after dragging | ✓ |  |
| Spectrum | Move mode toggle switches Plotly dragmode to 'pan' (drag = move spectrum) | ✓ |  |
| Spectrum | Full spectrum resets dragmode to 'zoom' (first-preview default) | ✓ |  |
| Spectrum | Use in Unified Evidence → item appears in Evidence Queue tab | ✓ |  |
| Integration | Sidebar Programs link still rendered | ✓ |  |
| Integration | SpectraCheck H1 still rendered | ✓ |  |
| Integration | All 12 SpectraCheck tabs still present | ✓ |  |
| Integration | AI Evidence Queue right-rail integration intact | ✓ |  |
