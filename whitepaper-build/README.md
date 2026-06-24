# MolTrace White-Paper PDF Build System

Converts the markdown white papers at the repo root into PDFs via either **Pandoc** (broad compatibility, LaTeX engine) or **Typst** (modern, fast, dependency-light).

## Repository inputs

Generated PDFs target these source markdown files at the repo root:

```
MolTrace_White_Paper.md              (hybrid, canonical, ~5,700 words)
MolTrace_White_Paper_Sales.md        (sales-led variant, ~4,000 words)
MolTrace_White_Paper_Technical.md    (technical variant, ~7,500 words)
MolTrace_Executive_OnePager.md       (single page, ~500 words)
MolTrace_ROI_Methodology.md          (methodology + template)
MolTrace_Company_Credentials.md      (logo bar + About block)
```

## Quick start

```bash
# From the repo root:
make -C whitepaper-build all              # build every paper via Pandoc
make -C whitepaper-build all-typst        # build every paper via Typst
make -C whitepaper-build clean            # remove dist/

# Or invoke a single document:
make -C whitepaper-build hybrid           # MolTrace_White_Paper.pdf
make -C whitepaper-build sales            # MolTrace_White_Paper_Sales.pdf
make -C whitepaper-build technical        # MolTrace_White_Paper_Technical.pdf
make -C whitepaper-build onepager         # MolTrace_Executive_OnePager.pdf
make -C whitepaper-build roi              # MolTrace_ROI_Methodology.pdf
make -C whitepaper-build credentials      # MolTrace_Company_Credentials.pdf
```

Built PDFs land in `whitepaper-build/dist/`.

## Toolchain options

| Engine | Strengths | Install |
|---|---|---|
| **Pandoc + XeLaTeX** | Footnote-perfect, ~30-year-stable, runs on any CI image | `brew install pandoc basictex` (macOS); `apt-get install pandoc texlive-xetex` (Linux) |
| **Typst** | Modern syntax, fast compile, no LaTeX deps, easy to theme | `brew install typst` (macOS); cargo / GitHub releases otherwise |

Pandoc is the **default** because LaTeX is the lingua franca of scientific publishing and the auditor / reviewer audience expects PDF output that reads like a journal article. Typst is offered as a fast-iteration alternative for branding tweaks.

## Output styling

Both engines emit identical typography targets:

- 11 pt body text on letter-size paper, 1.15 ×-line height
- Section headings in MolTrace teal (`#00B884`)
- Eyebrow labels uppercase, tracking-wide, ~10 pt
- Citations as endnote footnotes with linked back-references
- "Designed to support" posture badges (SOC 2 Type II / ICH Q2(R2) / GDPR / GxP) at the foot of the title page
- Cover page with brand mark, title, subtitle, version, and audience line

The Typst template (`typst/template.typ`) is the canonical source for the typography; the Pandoc workflow consumes a custom `.tex` header (`pandoc/header.tex`) tuned to match.

## Brand assets

Drop the production assets into:

```
whitepaper-build/assets/
  logo.svg          (MolTrace brand mark, 1024×1024 minimum)
  logo-bar.svg      (Partner / customer logo bar — see MolTrace_Company_Credentials.md)
  cover-bg.svg      (Optional title-page background pattern)
```

The build system uses placeholder text when the assets are missing; replace before any external publication.

## Continuous integration

A minimal GitHub Action workflow lives at `.github/workflows/whitepaper-build.yml` (template provided). It runs `make all` on every push that touches a `MolTrace_*.md` file, uploads the resulting PDFs as workflow artifacts, and posts a checksum manifest to the run summary.

## Troubleshooting

**"pandoc: command not found"** — install Pandoc + a LaTeX distribution (see install table above).
**"Missing character: There is no … in font …"** — switch the XeLaTeX `mainfont` in `pandoc/header.tex` to a Unicode-complete font (default: Source Sans 3).
**Typst font fallback warnings** — the template uses Inter + JetBrains Mono. Install both, or override `body_font` and `mono_font` in `typst/template.typ`.

## License

This build system is part of the MolTrace project. Internal use only unless explicitly licensed.
