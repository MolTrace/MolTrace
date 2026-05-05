# Week 24.1: Retired MestReNova-Style Locked Spectrum View

The original Week 24.1 display layer has been retired for the main spectrum
preview. Processed spectra and raw-FID-derived ¹H/¹³C spectra now render the
real evidence trace by default.

The retired layer used to:

- estimate a low-intensity linear baseline;
- subtract that display baseline without changing the stored evidence;
- attenuate baseline-band noise;
- apply signed asinh weak-peak gain so small peaks remain visible;
- preserve the original uploaded/transformed spectrum state in metadata.

That behavior is disabled because it made spectra look warped and made
peak-height controls feel like they were changing the data. The current viewer
keeps peak picking, reports, preview points, and evidence scoring on original
intensity values. Weak-peak assistance is available only as a separate
display-only magnifier/inset.
