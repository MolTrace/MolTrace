# nmrglue Agilent/Varian fixture

This directory contains the official nmrglue `separate_1d_varian` example
archive. It is an Agilent/Varian arrayed 1D data set with a raw `fid` and
`procpar` under `arrayed_data.dir`.

Source:

- Documentation: https://nmrglue.readthedocs.io/en/latest/examples/separate_1d_varian.html
- Archive: https://storage.googleapis.com/google-code-archive-downloads/v2/code.google.com/nmrglue/example_separate_1d_varian.zip

Archive SHA-256:

`7f45584e03265f565d809d3140286b11f5797ab0cd182c5318ff537292c3f613`

The fixture is intentionally used as a vendor-format regression rather than a
curated chemical-shift reference: the nmrglue example is designed to exercise
Varian/Agilent `procpar` parsing and arrayed FID handling.
