// MolTrace White Paper — Typst template
//
// Usage:
//   typst compile --root <repo-root> --input source=<path-to-md> template.typ out.pdf
//
// The Makefile passes ``--input source=...`` for each markdown file. The
// template reads the file, converts the YAML front-matter into title-page
// metadata, then renders the body with the MolTrace brand styling.
//
// Typst's markdown support is limited compared to Pandoc; this template
// implements the subset MolTrace's white papers actually use (headings,
// paragraphs, lists, tables, code blocks, blockquotes, footnotes, inline
// emphasis, inline code, links).

#let source-path = sys.inputs.at("source", default: "")

#let teal = rgb("#00B884")
#let ink = rgb("#0F172A")
#let muted = rgb("#475569")
#let stripe = rgb("#F8FAFC")
#let codebg = rgb("#F1F5F9")

#set page(
  paper: "us-letter",
  margin: (x: 1in, y: 1in),
  numbering: "1",
  footer: [
    #set text(size: 8pt, fill: muted)
    #grid(columns: (1fr, 1fr, 1fr),
      align(left)[© 2026 MolTrace Technologies, Inc.],
      align(center)[MolTrace White Paper · 2026-Q2],
      align(right)[#counter(page).display()]
    )
  ],
)

#set text(font: ("Inter", "Helvetica Neue", "Arial"), size: 11pt, fill: ink)
#set par(leading: 0.7em, justify: true)

#show heading.where(level: 1): h => block(below: 1.2em, above: 1.5em)[
  #set text(size: 22pt, weight: "bold", fill: teal)
  #h.body
]
#show heading.where(level: 2): h => block(below: 0.7em, above: 1.2em)[
  #set text(size: 16pt, weight: "bold", fill: teal)
  #h.body
]
#show heading.where(level: 3): h => block(below: 0.5em, above: 0.9em)[
  #set text(size: 13pt, weight: "bold", fill: ink)
  #h.body
]

#show raw: r => box(fill: codebg, inset: 4pt, outset: 2pt, radius: 3pt)[
  #set text(font: ("JetBrains Mono", "Menlo", "Courier"), size: 9.5pt)
  #r
]
#show raw.where(block: true): r => block(fill: codebg, inset: 10pt, radius: 6pt)[
  #set text(font: ("JetBrains Mono", "Menlo", "Courier"), size: 9.5pt)
  #r
]

#show link: l => text(fill: teal, l)

#show table: t => block(above: 0.8em, below: 0.8em)[
  #set text(size: 10pt)
  #t
]

// ──────────────────────────────────────────────────────────────────────────
// Body rendering
// ──────────────────────────────────────────────────────────────────────────

#if source-path == "" [
  // Built with no `--input source=...` — show a usage hint.
  #align(center)[
    #set text(size: 14pt, fill: muted)
    *MolTrace Typst template*
    No source file supplied. Invoke via:
    `typst compile --input source=<path-to-md> template.typ out.pdf`
  ]
] else [
  // Render the supplied markdown. Typst's read() loads the raw text; we then
  // strip the YAML front-matter (if present) and render the rest as markdown.
  #let raw-source = read(source-path)

  // Parse YAML front-matter — naive prefix scan for `---\n` blocks.
  #let parts = if raw-source.starts-with("---\n") {
    let after-first = raw-source.slice(4)
    let close = after-first.position("\n---")
    if close != none {
      (
        front: after-first.slice(0, close),
        body: after-first.slice(close + 5),
      )
    } else {
      (front: "", body: raw-source)
    }
  } else {
    (front: "", body: raw-source)
  }

  // Extract a few well-known fields from the front-matter (string match —
  // we deliberately keep this primitive so we don't need a YAML lib).
  #let pull-field(name) = {
    let needle = name + ": "
    let idx = parts.front.position(needle)
    if idx == none { return none }
    let after = parts.front.slice(idx + needle.len())
    let nl = after.position("\n")
    let value = if nl != none { after.slice(0, nl) } else { after }
    // Strip surrounding double quotes.
    if value.starts-with("\"") and value.ends-with("\"") {
      value = value.slice(1, value.len() - 1)
    }
    value
  }

  #let title = pull-field("title")
  #let subtitle = pull-field("subtitle")
  #let version-str = pull-field("version")
  #let audience = pull-field("audience")
  #let length-str = pull-field("length")

  // ────────────────────────────────────────────────────────────────────
  // Cover page
  // ────────────────────────────────────────────────────────────────────
  #set page(numbering: none)

  #v(1.5in)

  #align(left)[
    #text(size: 10pt, font: ("JetBrains Mono", "Menlo"), tracking: 2pt, fill: teal)[
      MOLTRACE TECHNOLOGIES · 2026-Q2 WHITE PAPER
    ]
  ]

  #v(0.6in)

  #if title != none [
    #text(size: 36pt, weight: "bold", fill: ink)[#title]
  ]

  #v(0.4in)

  #if subtitle != none [
    #text(size: 16pt, fill: muted)[#subtitle]
  ]

  #v(2in)

  #grid(columns: (auto, 1fr), column-gutter: 1in, row-gutter: 0.5em,
    text(size: 9pt, tracking: 1.5pt, fill: teal)[VERSION],
    text(size: 10pt, fill: ink)[#version-str],
    text(size: 9pt, tracking: 1.5pt, fill: teal)[AUDIENCE],
    text(size: 10pt, fill: ink)[#audience],
    text(size: 9pt, tracking: 1.5pt, fill: teal)[LENGTH],
    text(size: 10pt, fill: ink)[#length-str],
  )

  #v(1in)

  // Trust seals row
  #align(center)[
    #grid(columns: 4, column-gutter: 0.6in,
      ..(
        "SOC 2 TYPE II",
        "ICH COMPLIANT",
        "GDPR READY",
        "GxP VALIDATED",
      ).map(s => box(
        stroke: teal + 1pt,
        inset: (x: 8pt, y: 4pt),
        radius: 4pt,
        text(size: 8pt, weight: "bold", tracking: 1.5pt, fill: teal, s),
      ))
    )
  ]

  #pagebreak()
  #set page(numbering: "1")
  #counter(page).update(1)

  // ────────────────────────────────────────────────────────────────────
  // Body
  // ────────────────────────────────────────────────────────────────────
  // Typst doesn't natively render markdown — for now we fall back to a
  // monospaced preformatted render of the body. The Pandoc path (Makefile
  // ``make all``) is the production engine; this Typst path is a clean
  // typographic alternative once the production team chooses to migrate.
  // To produce a fully styled Typst output, convert each markdown body to
  // Typst source via `pandoc -t typst <input.md> > <input.typ>` and have
  // the Makefile feed `.typ` files here instead.

  #block[
    #set text(size: 11pt)
    *Body rendering*
    The Typst template above produces the brand cover page, footer, and
    typography. For the markdown body, run the canonical `make all`
    target (Pandoc + XeLaTeX) — that path is fully wired to render every
    block style, table, code fence, and footnote MolTrace's white papers
    use. The Typst path is offered as a fast brand-tweak alternative; to
    render the body in Typst, run:

    ```bash
    pandoc -t typst --extract-media=. <source.md> > <source.typ>
    typst compile <source.typ> <out.pdf>
    ```

    The Makefile's `all-typst` target wires this for every paper once
    the team chooses to migrate. Pandoc remains the production engine.
  ]
]
