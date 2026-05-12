# Landing Reaction explore overlay smoke — 2026-05-12T02:48:12.719Z

- Pass: 37
- Fail: 0

| Check | Status | Detail |
|---|---|---|
| Landing page loads | ✓ |  |
| Switched to Module 03 (Reaction) | ✓ |  |
| Reaction explore overlay HIDDEN by default on Module 03 | ✓ |  |
| Default Reaction view still renders Capabilities card | ✓ |  |
| Click 'Explore Module' on Reaction → overlay opens | ✓ |  |
| Headline 'Navigate Complex Chemical Space.' rendered | ✓ |  |
| Eyebrow 'Reaction Optimization · Live preview' rendered | ✓ |  |
| Short framing sentence rendered | ✓ |  |
| Body section eyebrow 'LLM-GP hybrid · How it converges' rendered | ✓ |  |
| Body title 'Fewest experiments to peak' rendered | ✓ |  |
| Subtitle 'Bayesian optimization with chemistry-aware priors' rendered | ✓ |  |
| Bullet: LLM proposes + GP quantifies uncertainty | ✓ |  |
| Bullet: Inner-loop refinement of GP, re-prompt LLM | ✓ |  |
| Bullet: Multi-objective acquisition (yield + selectivity + impurity) | ✓ |  |
| Bullet: 8-15 experiments to converge vs 50+ for grid | ✓ |  |
| 3D response surface SVG rendered with role=img + descriptive aria-label | ✓ |  |
| SVG aria-label mentions 94% peak + 6 experiment markers | ✓ |  |
| Card header chip '3D response surface' rendered | ✓ |  |
| Card subtitle 'yield = f(temperature, catalyst loading)' rendered | ✓ |  |
| Card footer '6 experiments mapped · GP posterior shown' rendered | ✓ |  |
| Card footer uncertainty 'σ uncertainty < 1.8%' rendered | ✓ |  |
| Peak callout 'BEST · 94% yield' rendered inside SVG | ✓ |  |
| Color legend header 'YIELD %' rendered | ✓ |  |
| Color legend swatch "35 — low" rendered | ✓ |  |
| Color legend swatch "65 — mid" rendered | ✓ |  |
| Color legend swatch "94 — peak" rendered | ✓ |  |
| Axis label: x — temperature | ✓ |  |
| Axis label: y — catalyst loading | ✓ |  |
| Axis label: z — yield range | ✓ |  |
| Footer stat '6 experiments · 94% yield' rendered | ✓ |  |
| Footer stat 'vs. 50+ for grid' rendered | ✓ |  |
| Close (X) button collapses the overlay | ✓ |  |
| After close: Capabilities card restored | ✓ |  |
| Re-open explore overlay | ✓ |  |
| Switching to Module 01 hides overlay (useEffect cleanup) | ✓ |  |
| Switching to Module 02 hides overlay | ✓ |  |
| Re-open after tab round-trip works | ✓ |  |
