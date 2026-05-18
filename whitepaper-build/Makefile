# MolTrace White-Paper PDF build system.
#
# Default engine: Pandoc + XeLaTeX. Use `make all-typst` for the Typst path.
# All output lands in dist/.

# ────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────
ROOT          := $(abspath $(CURDIR)/..)
DIST          := dist
PANDOC_DIR    := pandoc
TYPST_DIR     := typst

HYBRID_MD     := $(ROOT)/MolTrace_White_Paper.md
SALES_MD      := $(ROOT)/MolTrace_White_Paper_Sales.md
TECH_MD       := $(ROOT)/MolTrace_White_Paper_Technical.md
ONEPAGER_MD   := $(ROOT)/MolTrace_Executive_OnePager.md
ROI_MD        := $(ROOT)/MolTrace_ROI_Methodology.md
CRED_MD       := $(ROOT)/MolTrace_Company_Credentials.md

ALL_MD        := $(HYBRID_MD) $(SALES_MD) $(TECH_MD) $(ONEPAGER_MD) $(ROI_MD) $(CRED_MD)

# ────────────────────────────────────────────────────────────────────────
# Pandoc command
# ────────────────────────────────────────────────────────────────────────
PANDOC        ?= pandoc
PANDOC_ENGINE ?= xelatex
PANDOC_OPTS   := \
  --from=markdown+yaml_metadata_block+footnotes+pipe_tables+inline_code_attributes \
  --to=pdf \
  --pdf-engine=$(PANDOC_ENGINE) \
  --include-in-header=$(PANDOC_DIR)/header.tex \
  --variable=geometry:margin=1in \
  --variable=fontsize:11pt \
  --variable=linkcolor:NavyBlue \
  --variable=urlcolor:NavyBlue \
  --variable=toccolor:NavyBlue \
  --variable=documentclass:article \
  --variable=mainfont:"Helvetica Neue" \
  --variable=monofont:"Menlo" \
  --highlight-style=tango \
  --table-of-contents \
  --toc-depth=2 \
  --metadata=lang:en-US

# ────────────────────────────────────────────────────────────────────────
# Typst command
# ────────────────────────────────────────────────────────────────────────
TYPST         ?= typst

# ────────────────────────────────────────────────────────────────────────
# Targets — Pandoc (default)
# ────────────────────────────────────────────────────────────────────────
.PHONY: all all-typst hybrid sales technical onepager roi credentials clean dist-dir

all: dist-dir hybrid sales technical onepager roi credentials
	@echo "✓ All PDFs built via Pandoc → $(DIST)/"
	@ls -lh $(DIST)/*.pdf

hybrid:      dist-dir $(DIST)/MolTrace_White_Paper.pdf
sales:       dist-dir $(DIST)/MolTrace_White_Paper_Sales.pdf
technical:   dist-dir $(DIST)/MolTrace_White_Paper_Technical.pdf
onepager:    dist-dir $(DIST)/MolTrace_Executive_OnePager.pdf
roi:         dist-dir $(DIST)/MolTrace_ROI_Methodology.pdf
credentials: dist-dir $(DIST)/MolTrace_Company_Credentials.pdf

$(DIST)/MolTrace_White_Paper.pdf: $(HYBRID_MD) $(PANDOC_DIR)/header.tex
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

$(DIST)/MolTrace_White_Paper_Sales.pdf: $(SALES_MD) $(PANDOC_DIR)/header.tex
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

$(DIST)/MolTrace_White_Paper_Technical.pdf: $(TECH_MD) $(PANDOC_DIR)/header.tex
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

$(DIST)/MolTrace_Executive_OnePager.pdf: $(ONEPAGER_MD) $(PANDOC_DIR)/header.tex
	$(PANDOC) $(PANDOC_OPTS) --variable=geometry:margin=0.7in -o $@ $<

$(DIST)/MolTrace_ROI_Methodology.pdf: $(ROI_MD) $(PANDOC_DIR)/header.tex
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

$(DIST)/MolTrace_Company_Credentials.pdf: $(CRED_MD) $(PANDOC_DIR)/header.tex
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

# ────────────────────────────────────────────────────────────────────────
# Targets — Typst (modern alternative)
# ────────────────────────────────────────────────────────────────────────
all-typst: dist-dir
	@$(TYPST) --version >/dev/null 2>&1 || \
	  (echo "✗ typst not found — install via 'brew install typst' or https://github.com/typst/typst" && exit 1)
	@for md in $(ALL_MD); do \
	  base=$$(basename $$md .md); \
	  echo "→ Compiling $$base.pdf via Typst..."; \
	  $(TYPST) compile \
	    --root $(ROOT) \
	    --input source=$$md \
	    $(TYPST_DIR)/template.typ \
	    $(DIST)/$$base.pdf \
	    || (echo "✗ Typst build failed for $$base" && exit 1); \
	done
	@echo "✓ All PDFs built via Typst → $(DIST)/"
	@ls -lh $(DIST)/*.pdf

# ────────────────────────────────────────────────────────────────────────
# Housekeeping
# ────────────────────────────────────────────────────────────────────────
dist-dir:
	@mkdir -p $(DIST)

clean:
	@rm -rf $(DIST)/*.pdf $(DIST)/*.log $(DIST)/*.aux
	@echo "✓ Cleaned $(DIST)/"

# ────────────────────────────────────────────────────────────────────────
# Hash manifest (audit trail for the published PDFs)
# ────────────────────────────────────────────────────────────────────────
manifest:
	@cd $(DIST) && shasum -a 256 *.pdf > MANIFEST.sha256 || true
	@echo "✓ Hash manifest → $(DIST)/MANIFEST.sha256"

# ────────────────────────────────────────────────────────────────────────
# Help
# ────────────────────────────────────────────────────────────────────────
help:
	@echo "MolTrace White-Paper PDF Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all          — build every PDF via Pandoc (default)"
	@echo "  all-typst    — build every PDF via Typst"
	@echo "  hybrid       — MolTrace_White_Paper.pdf"
	@echo "  sales        — MolTrace_White_Paper_Sales.pdf"
	@echo "  technical    — MolTrace_White_Paper_Technical.pdf"
	@echo "  onepager     — MolTrace_Executive_OnePager.pdf"
	@echo "  roi          — MolTrace_ROI_Methodology.pdf"
	@echo "  credentials  — MolTrace_Company_Credentials.pdf"
	@echo "  manifest     — write dist/MANIFEST.sha256"
	@echo "  clean        — remove built PDFs"
	@echo ""
	@echo "Environment overrides:"
	@echo "  PANDOC        — pandoc binary (default: pandoc)"
	@echo "  PANDOC_ENGINE — xelatex | lualatex | pdflatex (default: xelatex)"
	@echo "  TYPST         — typst binary (default: typst)"

.DEFAULT_GOAL := help
