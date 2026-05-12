# Landing Regulatory explore overlay smoke — 2026-05-12T02:46:33.864Z

- Pass: 31
- Fail: 0

| Check | Status | Detail |
|---|---|---|
| Landing page loads | ✓ |  |
| Switched to Module 02 (Regulatory) | ✓ |  |
| Regulatory explore overlay HIDDEN by default on Module 02 | ✓ |  |
| Default Regulatory view still renders Capabilities card | ✓ |  |
| Click 'Explore Module' on Regulatory → overlay opens | ✓ |  |
| Headline 'Built-in Compliance and Safety.' rendered | ✓ |  |
| Eyebrow 'Regulatory Intelligence Hub · Live preview' rendered | ✓ |  |
| Short framing sentence rendered | ✓ |  |
| Body section eyebrow 'QA-RAG · How it works' rendered | ✓ |  |
| Body title 'Grounded in citations' rendered | ✓ |  |
| Subtitle lists corpora (EPA · FDA · ICH · EMA · REACH) | ✓ |  |
| Bullet: ICH/EPA/FDA/REACH/SOPs corpus | ✓ |  |
| Bullet: RAG grounding (no hallucinated regs) | ✓ |  |
| Bullet: Jurisdiction-aware risk thresholds | ✓ |  |
| Bullet: Human reviewer gate for flagged findings | ✓ |  |
| QA-RAG chat snippet rendered with role=img + descriptive aria-label | ✓ |  |
| Snippet header chip 'QA-RAG · Live answer' rendered | ✓ |  |
| User question bubble: NDMA 110 ng/day in generic API | ✓ |  |
| Flagged toxicity warning: 'Flagged · Class 1 mutagen' rendered | ✓ |  |
| Verdict cites NDMA cap at 96 ng/day per ICH M7 | ✓ |  |
| Citation chip "ICH M7(R2) §6.3" rendered | ✓ |  |
| Citation chip "FDA Guidance 2021" rendered | ✓ |  |
| Citation chip "EMA/CHMP/428592/2019" rendered | ✓ |  |
| Reviewer gate 'Requires reviewer sign-off' rendered | ✓ |  |
| Reviewer gate status 'PENDING' badge rendered | ✓ |  |
| Close (X) button collapses the overlay | ✓ |  |
| After close: Capabilities card restored | ✓ |  |
| Re-open explore overlay | ✓ |  |
| Switching to Module 01 hides overlay (useEffect cleanup) | ✓ |  |
| Switching to Module 03 hides overlay | ✓ |  |
| Re-open after tab round-trip works | ✓ |  |
