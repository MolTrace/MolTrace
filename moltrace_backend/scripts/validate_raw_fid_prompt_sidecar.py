#!/usr/bin/env python
"""CLI wrapper for raw-FID Prompt 1/2 fixture validation."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nmrcheck.raw_fid_prompt_validation import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
