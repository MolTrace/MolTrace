# Landing Spectroscopy explore carousel smoke — 2026-05-12T01:46:17.197Z

- Pass: 69
- Fail: 0

| Check | Status | Detail |
|---|---|---|
| Landing page loads (?autoplay=0) | ✓ |  |
| ¹H NMR slide HIDDEN by default on Spectroscopy panel | ✓ |  |
| Default Spectroscopy view still renders Capabilities card | ✓ |  |
| Explore headline HIDDEN by default | ✓ |  |
| Click 'Explore Module' on Spectroscopy | ✓ |  |
| Headline 'Uncover the Ground Truth in Your Data.' rendered | ✓ |  |
| Eyebrow 'Spectroscopy Intelligence · Live preview' rendered | ✓ |  |
| Short framing 'Three spectra, one continuous picture of your molecule.' | ✓ |  |
| Legacy long framing sentence is GONE (regression guard) | ✓ |  |
| Hint row advertises auto-advance behavior | ✓ |  |
| Carousel container rendered (role=region + aria-roledescription) | ✓ |  |
| Auto-play DISABLED by ?autoplay=0 (data-autoplay-state=stopped) | ✓ |  |
| Slide 01: 'Resolved ¹H NMR' title rendered | ✓ |  |
| Slide 01: '1' rendered as <sup> superscript inside title | ✓ |  |
| Slide 01: eyebrow with '01 / 03' counter rendered | ✓ |  |
| Slide 01: 'CDCl₃ · 400 MHz' subtitle rendered | ✓ |  |
| Slide 01 bullet: deconvolution / quartet under residual solvent | ✓ |  |
| Slide 01 bullet: 'apodization, zero-filling, phase correction' | ✓ |  |
| Slide 01 bullet: auto-referencing / re-derivable shifts | ✓ |  |
| Slide 01 bullet: USP <761>-ready integrations | ✓ |  |
| Slide 01 footer: 'SNR 240' badge rendered | ✓ |  |
| Slide 01: ¹H NMR SVG figure rendered with role=img | ✓ |  |
| Slide 02: 'Decoupled ¹³C NMR' title rendered | ✓ |  |
| Slide 02: '13' rendered as <sup> superscript inside title | ✓ |  |
| Slide 02: eyebrow with '02 / 03' counter rendered | ✓ |  |
| Slide 02: 'WALTZ-16 decoupled' subtitle rendered | ✓ |  |
| Slide 02 bullet uses 'peak' (not 'stick'): single sharp peak per carbon | ✓ |  |
| Slide 02 bullet: CDCl₃ triplet @ δ 77.0 anchor (real-¹³C signature) | ✓ |  |
| Slide 02 bullet: DEPT-135 multiplicity confirmation | ✓ |  |
| Slide 02 footer: 'DEPT confirmed' badge rendered | ✓ |  |
| Slide 02: 13C SVG aria-label no longer uses 'stick spectrum' | ✓ |  |
| Slide 02: 13C NMR SVG figure rendered with role=img | ✓ |  |
| Slide 02: 13C SVG aria-label mentions 'CDCl3 triplet 77' | ✓ |  |
| Slide 02: 13C peak label "δ 205.3 / C=O" rendered | ✓ |  |
| Slide 02: 13C peak label "δ 170.2 / COOR" rendered | ✓ |  |
| Slide 02: 13C peak label "δ 77.0 / CDCl₃" rendered | ✓ |  |
| Slide 02: 13C peak label "δ 22.1 / CH₃" rendered | ✓ |  |
| Slide 03: 'LC-MS chromatogram (TIC)' title rendered | ✓ |  |
| Slide 03: eyebrow with '03 / 03' counter rendered | ✓ |  |
| Slide 03: 'ESI+ · 30 min gradient' subtitle rendered | ✓ |  |
| Slide 03 bullet: TIC over 30-min gradient | ✓ |  |
| Slide 03 bullet uses 'peak' (not 'stick'): retention-time peak m/z-annotated | ✓ |  |
| Slide 03 bullet: MS² fragmentation library matching | ✓ |  |
| Slide 03 bullet: five features → regulatory dossier | ✓ |  |
| Slide 03: LC-MS SVG aria-label no longer uses 'stick plot' | ✓ |  |
| Slide 03: LC-MS chromatogram SVG rendered with role=img | ✓ |  |
| Slide 03: LC-MS peak label "m/z 195" rendered | ✓ |  |
| Slide 03: LC-MS peak label "m/z 251" rendered | ✓ |  |
| Slide 03: LC-MS peak label "m/z 412" rendered | ✓ |  |
| Exactly 3 spectrum SVG figures rendered (one per carousel slide) | ✓ |  |
| Pagination: 'Previous spectrum' arrow rendered | ✓ |  |
| Pagination: 'Next spectrum' arrow rendered | ✓ |  |
| Pagination: 3 indicator pills rendered | ✓ |  |
| First load: Previous arrow disabled (carousel starts at slide 01) | ✓ |  |
| First load: indicator 01 selected (aria-selected=true) | ✓ |  |
| Click 'Next spectrum' advances to slide 02 (¹³C NMR) | ✓ |  |
| Click indicator 03 jumps to LC-MS slide (Next disabled at end) | ✓ |  |
| Close (X) button collapses the overlay | ✓ |  |
| After close: Capabilities card restored | ✓ |  |
| Re-open explore overlay | ✓ |  |
| Switching to Module 02 hides explore overlay (useEffect cleanup) | ✓ |  |
| Module 02 still renders 'Regulatory Intelligence Hub' | ✓ |  |
| Switching back to Module 01 returns to default view (overlay closed) | ✓ |  |
| Phase B: reload landing page (autoplay enabled) | ✓ |  |
| Phase B: open explore overlay | ✓ |  |
| Phase B: auto-play active by default (data-autoplay-state=playing) | ✓ |  |
| Phase B: auto-advance to slide 02 within 12s | ✓ |  |
| Phase B: manual nav permanently stops auto-play (data-autoplay-state=stopped) | ✓ |  |
| Phase B: carousel stays put after auto-play stopped (no further auto-advance) | ✓ |  |
