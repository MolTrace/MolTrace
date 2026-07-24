# Repho Phase C — heavy-ML extras (R12–R15)

**Status:** engines shipped, **all four capabilities default-OFF.** No heavy dependency is added to
`pyproject.toml`, no import of `torch` / `aizynthfinder` / `transformers` / `rxn4chemistry` happens
at module load, and the default CI job is unchanged.

Phase A (R1–R7) and Phase B (R8–R11) are lightweight and CPU-deployable. Phase C deliberately
breaks that: graph neural nets, MCTS retrosynthesis, transformer forward prediction, and robotic
execution. Rather than defer the work until a customer justifies the dependency weight, Phase C
ships the **engines plus the governance seam that keeps them guests** — nothing heavy can activate
implicitly, and everything Phase A/B does today keeps working byte-for-byte when the flags are off.

---

## 1. The one contract: `reaction_ml`

Every Phase-C capability enters the product through `nmrcheck.reaction_ml`. There is no second door.

```python
from nmrcheck import reaction_ml

decision = reaction_ml.resolve_backend("yield_gnn", promotion_evidence=evidence)
decision.backend      # "heavy" | "fallback" | "unavailable"
decision.reason       # human-readable *why*
decision.provenance   # flag value, probe results, evidence reference — persist this
```

Five rules, enforced in code:

| # | Rule | Mechanism |
|---|------|-----------|
| 1 | **Default-off** | Per-capability env flag (`CapabilitySpec.flag_env`), truthy set `{1,true,yes,on}`. |
| 2 | **Probed, never imported** | `importlib.util.find_spec` at decision time — the house pattern of the `rag`/`infra`/`docx` optional groups. |
| 3 | **Gated by promotion evidence** | A capability that *replaces frozen math* additionally needs a recorded R11 benchmark-gate pass. |
| 4 | **Provenance on every decision** | `BackendDecision.provenance` is an auditable record for the caller to persist (the Annex-22 habit, applied to ML enablement). |
| 5 | **Honest fallback** | When off/absent, the decision names the Phase-A/B path that runs instead — or states plainly that there is none. Never a silent degradation, never a crash. |

### Capability registry

| Capability | Flag | Probes | Needs R11 evidence | Fallback when off |
|---|---|---|---|---|
| `yield_gnn` (R12) | `MOLTRACE_REACTION_YIELD_GNN` | `torch` | **yes** | sklearn GP if installed, else the zero-dependency k-NN surrogate — **always available** |
| `retrosynthesis` (R13) | `MOLTRACE_REACTION_RETRO` | `aizynthfinder` | no | none — capability reports unavailable, UI hides the surface |
| `forward_prediction` (R14) | `MOLTRACE_REACTION_FORWARD` | `rxn4chemistry` **or** `transformers` | no | none — capability reports unavailable, UI hides the surface |
| `sdl_execution` (R15) | `MOLTRACE_REACTION_SDL` | *(none — flag + a connected driver)* | no | manual make/test/learn — the R5 half-closed loop, unchanged |

`all_capability_statuses()` renders the whole table at runtime; that is what an ops/admin surface
should show.

### Promotion evidence is strict, and it must be *bound*

`yield_gnn` replaces frozen math, so "installed and flagged on" is not enough — it must have beaten
the incumbent on the frozen, checksummed R11 gold set. `_valid_promotion_evidence` checks **types
before values**, because the failure modes here are quiet:

- `exit_code` must be a real `int`. `exit_code=False` is rejected explicitly — `False == 0` in
  Python, so a mis-mapped "passed" flag whose `False` means *failure* would otherwise read as the
  gate's success code.
- `gold_checksum` must match `sha256:[0-9a-f]{64}` — the exact shape
  `reaction_eval.gold_set_checksum` emits. A truthy string like `"PASSED"` is not evidence.
- `model_version` must be a non-empty string.

**The evidence has exactly one producer.** `reaction_eval.promotion_evidence(outcome, candidate)`
emits it, and `reaction_eval_cli --evidence-out` writes it to disk. This matters more than it
looks: the *gate outcome* carries the exit code while the *evaluated result* carries the gold
checksum and model version, so neither object alone is the record this seam requires. Without a
producer of that union, the only thing that could ever unlock a heavy backend would be a dict an
operator typed by hand — and the "R11 gate pass" recorded in provenance would be a self-attestation
rather than a fact.

The artifact is written for **every** outcome, not only a pass: a blocked run's evidence carries
its non-zero exit code, which the seam then correctly refuses. (Writing only on success would leave
a stale passing artifact from an earlier run as the newest thing on disk.) It ties the record to a
gate run that actually happened; it is not a signature, and it does not defend against an operator
who edits the file afterwards — protect it the way the rest of your release evidence is protected.

Callers that know what they are activating should also **bind** the evidence:

```python
evidence = json.loads(Path("evidence.json").read_text())   # from --evidence-out
predictor, decision = select_yield_predictor(
    promotion_evidence=evidence,
    expected_gold_checksum=reaction_eval.gold_set_checksum(gold),   # this benchmark
    expected_model_version=meta["model_version"],                    # this checkpoint
)
```

Without the binding, a *genuine* gate pass earned by some other model on some other gold set would
still unlock the heavy path. With it, the evidence, the benchmark, and the weights are one unit.

---

## 2. R12 — yield/selectivity GNN (`reaction_yield_models`)

Three predictors behind one interface (`fit` / `predict` → `YieldPrediction(mean, std, backend,
n_samples)`), chosen by `select_yield_predictor`:

- **`KNNSurrogatePredictor`** — zero dependencies, always installable, deterministic tie-break on
  `(distance, target, index)`. This is the terminal fallback: Repho never has *no* surrogate.
- **`SklearnSurrogatePredictor`** — GP with a `WhiteKernel` noise term and a `std_floor`, so the
  posterior can never claim zero uncertainty and degenerate the calibration metric.
- **`TorchMPNNPredictor`** — message-passing net over RDKit molecular graphs, MC-Dropout for
  epistemic uncertainty, reproducible per-sample seeds.

All three share `_validated_examples()`, so a NaN target or an unparseable SMILES is refused at the
same boundary regardless of backend.

`ConditionFeaturizer` reports **everything the fitted layout cannot represent** — an unseen
categorical value, an absent key, a non-numeric value in a numeric column — in
`last_unknowns`, which surfaces on every prediction's `warnings`. Disclosure matters more on the
numeric side than the categorical one: `0.0` is a legitimate value (0 °C), so an imputed missing
temperature is indistinguishable from a real observation and can collide with genuine training
rows — earning a near-perfect MAE for a run whose condition was never recorded.

### Checkpoints are sealed, and never enter git

`save()` writes `mpnn.pt` (weights) plus `meta.json` (featurizer vocabulary, feature order,
`model_version`, `weight_sha256`) — and seals `meta.json` itself with `meta_sha256`. An unsealed
sidecar would let an edited vocabulary or a swapped weight digest pass a weights-only integrity
check.

`load()` refuses on a meta digest mismatch, a weight SHA mismatch, or a `model_version` that is not
the promoted one.

`save()` also drops a self-ignoring `.gitignore` (`*`) into the checkpoint directory — the
pip/poetry convention. The directory is caller-chosen, so a repo-root pattern cannot reliably cover
it; `moltrace_backend/.gitignore` covers the conventional locations as well.

### Metrics are not activation evidence

`benchmark_yield_predictor` reports MAE and expected calibration error;
`compare_yield_models` puts two predictors side by side. These feed the **model card** — they are
*predictor-level* numbers. Activation still requires the full-loop R11 gate, which includes the
blocking safety-recall dimension. A model with a better MAE and a worse safety recall does not ship.

---

## 3. R13 — retrosynthesis (`reaction_retro`)

Provider-agnostic route model (`RouteNode`) with adapters: `route_from_dict` (native) and
`route_from_aizynth_dict` (AiZynthFinder's nested `children` shape). `propose_routes` takes an
injectable `_search`, so route scoring is fully testable with no heavy dependency installed.

`score_route` overlays the **frozen** Phase-A engines onto a proposed route:

- **Safety** — screens every molecule *and every reagent* through `reaction_safety.screen_reaction`.
  A hazardous reagent is exactly the thing retrosynthesis planners hide; scoring only the molecules
  would miss it.
- **Green** — step count, longest linear sequence, atom economy. AE **refuses** rather than guessing
  when any reagent's molecular weight is unweighable, and an AE above 100% is surfaced as a warning
  and excluded rather than silently clamped to 100 (it means the input is wrong, not that the route
  is perfect).

Risk vocabulary is the canonical `reaction_safety` one — `low / medium / high / critical` — and an
**unrecognised** level ranks *worse than critical*. An earlier draft omitted `critical` entirely,
which made the worst hazard score as `low`; the fail-safe ordering makes that class of bug
impossible rather than merely fixed.

`to_mermaid` renders a route for the UI; `route_similarity` supports dedup and diversity.
`ROUTE_DISCLAIMER` is decision-support language and ships verbatim.

---

## 4. R14 — forward prediction (`reaction_forward`)

`predict_forward` (injectable `_backend`; `rxn4chemistry` and `transformers` adapters behind
`_resolve_live_backend`) returns `ForwardPrediction`, then **`cross_check_prediction` runs the
frozen safety and green engines against the predicted product before anything reaches a chemist.**
A transformer's confident product prediction is not a safety opinion; the frozen engines are.

`_aggregate_screens` folds multiple screens with the same fail-safe rank as R13 — `unknown`
outranks `critical`.

`topk_accuracy` is the honest evaluator: canonical-SMILES matching (RDKit when available, reported
raw-string fallback otherwise), an unparseable *truth* invalidates the row rather than scoring it
either way, and empty/whitespace SMILES are refused before RDKit sees them — `MolFromSmiles("")`
returns an *empty mol*, not `None`, which would otherwise let a blank prediction "match" a blank
truth and inflate top-1.

One asymmetry is worth stating plainly: the frozen `reaction_safety.screen_reaction` drops
`unknown` species risks before aggregating and falls back to `low` when nothing is left, so a
reactant RDKit cannot parse disappears from its `overall_risk` as long as one sibling parses.
`_aggregate_screens` re-reads the per-species records directly so an unreadable structure cannot be
laundered into a clean verdict. The frozen engine is left untouched — the strengthening belongs in
the overlay that consumes it, not in the Phase-A math other modules already depend on.

---

## 5. R15 — self-driving lab (`reaction_sdl`)

Hardware-abstraction layer (`InstrumentDriver` Protocol + `SimulatedDriver`) with `SDLController`
in front of it. Three modes; **`manual` is the default everywhere.**

Interlocks, all enforced before a driver is ever touched:

- **Arm / heartbeat / disarm.** A step cannot run unarmed or on a stale heartbeat. Heartbeats and
  steps share **one** monotonic timeline (`_last_seen_at`), which is the whole point: an
  unvalidated heartbeat is a hole straight through the watchdog, because a single future-dated
  beat makes `now - last_heartbeat` negative forever after and the watchdog can never expire again
  no matter how long the operator is actually gone. Sharing the clock means a future-dated beat
  instead makes every genuinely-timed step non-monotonic — loud and fail-closed.
- **`ExecutionEnvelope`.** Both the declared caps *and* every step parameter are screened for
  finiteness before any comparison. Ordering checks alone are not a screen in either direction:
  `NaN <= 0` is False, so a NaN cap passes a bounds-only `validate()`, and `value > NaN` is also
  False, so that cap then silently disables its own bound. Guarding the parameters and not the
  envelope leaves the identical hole on the other side.
- **`abort()` records and disarms BEFORE calling `driver.abort()`,** and wraps a driver that raises.
  The controller must reach the safe state even when the hardware does not respond.
- **`run_step` guards both driver failure modes.** An exception is journaled and aborts, never
  propagating as an unrecorded failure — and a driver that *returns garbage instead of raising* is
  treated just as seriously, because the step already ran on real hardware. A malformed result is
  shape-checked, journaled, and aborted rather than surfacing as an `AttributeError` that would
  leave the controller armed and the executed step unrecorded.
- **Tamper-evident journal.** Hash-chained from a fixed genesis; payloads are deep-copied on entry
  so a caller cannot mutate history through a retained reference. `verify_journal(expected_entry_count=…,
  expected_head_hash=…)` checks the chain *and* that it is the expected length and head — a valid
  chain that is simply shorter than it should be is a truncation attack, not a pass.

`sdl_site_enabled` is the site-level gate. `SDL_DISCLAIMER` ships verbatim.

---

## 6. Data governance (`reaction_data_pipeline`)

Heavy models need data, and reaction data is where the license landmines are. The pipeline refuses
by default: an **unregistered dataset cannot be ingested at all.**

`LICENSE_REGISTRY` classifies each source as `training_and_benchmark`, `benchmark_only`, or
`prohibited`:

- Usable: Open Reaction Database (CC-BY-SA), USPTO-50k / USPTO-full, NIST WebBook.
- **Benchmark-only:** Buchwald–Hartwig HTE, Suzuki–Miyaura HTE. Held out of training on purpose.
- **Prohibited — never ingest, never bundle:** Reaxys, Pistachio, Bretherick's.

`assert_usage_allowed(dataset, purpose)` is called *per record* inside `validate_records(...,
purpose="training")`, so the license check cannot be skipped by calling the validator directly.

Splits are content-addressed and reproducible: `assign_splits` coerces the seed to `int` before
hashing and uses a stable digest (never `hash()`, which is `PYTHONHASHSEED`-dependent across
processes). `verify_manifest` re-derives the checksum; `assert_no_benchmark_leakage` and
`training_ids(manifest, train_split=…)` — which raises on an unknown split rather than returning an
empty list — keep the R11 gold set out of every training path.

**Standing rule: the R11 gold set is never trained on.** It is hash-excluded, and the leakage
assertion is the tripwire.

---

## 7. Enabling a capability

Nothing below happens by default. Each step is deliberate.

```bash
# 1. Install the extra (site-installed; never a core dependency)
pip install torch

# 2. Earn promotion evidence — the R11 gate: candidate vs. incumbent on the frozen gold set.
#    --evidence-out writes the machine-readable record the capability seam requires.
python -m nmrcheck.reaction_eval_cli \
  --gold tests/fixtures/reaction_eval/gold_set_v1.json \
  --candidate gnn_result.json \
  --incumbent current_result.json \
  --evidence-out evidence.json

# 3. Flag it on, bound to the evidence you just earned
export MOLTRACE_REACTION_YIELD_GNN=1
```

Then confirm what the system actually decided — and persist it:

```python
from nmrcheck import reaction_ml

for status in reaction_ml.all_capability_statuses():
    print(status.name, status.active, status.reason)
```

To turn a capability off, unset the flag. Nothing else in Repho changes: the fallback named in
`BackendDecision.fallback` is the path that was already running.

---

## 8. Testing

Phase C adds 129 tests across six files. They run in the **default** environment with **no heavy
dependency installed** — probes and env are injectable everywhere, and the two skips are the
genuinely torch-only paths (`pytest.importorskip`, the house pattern).

```bash
cd moltrace_backend
.venv/bin/python -m pytest tests/test_reaction_ml.py tests/test_reaction_data_pipeline.py \
  tests/test_reaction_yield_models.py tests/test_reaction_retro.py \
  tests/test_reaction_forward.py tests/test_reaction_sdl.py -q
```

---

## 9. What Phase C is *not*

- **Not an autopilot.** R13/R14/R15 are decision-support. Routes are proposals, forward predictions
  are cross-checked against frozen safety, and SDL execution requires an armed controller, a live
  heartbeat, and a human-approved envelope.
- **Not a compliance claim.** Nothing here changes MolTrace's "designed to support" framing.
- **Not a full HTTP surface.** The lightweight halves ARE wired (owner-scoped, per project):
  `POST/GET …/yield-predictions` (surrogate fit on the project's own experiments),
  `POST/GET …/route-scores` (frozen-engine overlay on a supplied route),
  `POST/GET …/forward-checks` (frozen-engine cross-check of a supplied prediction), plus the
  global `GET /reaction-capabilities` readout and the read-only `GET /reaction-sdl/status`.
  The **generative heavy paths stay unwired** — AiZynth route proposal, RXN/transformers forward
  prediction, torch GNN training, and every SDL execution route — because the extras are absent
  in all current deployments and there is no background worker to host them; wiring them now
  would ship endpoints that 503 for every customer. The capability readout is their honest face
  until that changes. See `docs/fe_handoff_reaction_phase_c.md`.
