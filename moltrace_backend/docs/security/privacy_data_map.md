# Personal-Data Map & Data-Subject Requests (DSAR / erasure)

**Security Prompt 23.** What personal data MolTrace holds, where, and what can honestly
be done with it when a data subject exercises their rights — plus the **limits**, stated
plainly. The machine-readable source is `DATA_MAP` in
[`privacy.py`](../../src/nmrcheck/privacy.py) (unit-tested); this document renders it.

> **Compliance framing.** These controls are **designed to support** the customer's GDPR
> obligations. MolTrace does **not** claim to *be* GDPR-compliant, and does not guarantee
> erasure. The compliance determination — and the response to the data subject — remain
> the **controller's** (the customer's).

## Roles: MolTrace assists, the controller decides

For customer tenant data MolTrace is a **processor**. Under **Art. 28(3)(e)** it *assists*
the controller by technical and organisational measures; it does **not**:

- verify the requester's identity,
- decide the scope of the request or judge it excessive,
- apply the Art. 15(4) balancing against third parties' rights,
- respond to the data subject directly.

A processor that made those calls would be determining purposes and means and would become
a controller for that processing (Art. 28(10)). What MolTrace supplies is a **discovery
report**, an **export**, the facts only it knows, and an honest **erasure plan**.

## The personal-data map

Disposition legend — **erase** = destroyed outright · **pseudonymise + restrict** =
identifier cleared, record survives (**still personal data**) · **retain (legal
obligation)** = Art. 17(3) retention, restricted not erased · **immutable ledger** =
append-only integrity record, cannot be altered at all.

| Store | Personal data | Disposition | Basis |
|---|---|---|---|
| `users` | email, credential hash, account status | pseudonymise + restrict | Identity of record; email is unique and denormalised across many attribution columns |
| session / refresh / action tokens | session + credential material | **erase** | No evidentiary value; already revocable in place |
| `mfa_*` credentials + challenges | authenticator secrets, public keys, device labels | **erase** | Authenticator material; already hard-deleted by the store |
| `scim_users` | IdP external id, userName, raw IdP profile | **erase** | Per-connection IdP mirror; the IdP is the customer's own system |
| `email_outbox` | recipient, subject/body | **erase** | Transient delivery queue |
| `security_events` | actor email, IP, user agent, metadata | pseudonymise + restrict | No hash chain covers *this table*, so its identity columns can be cleared — **but every security event also writes a paired audit-chain row carrying actor identity + an `entity_id` back-pointer, and that row is immutable, so the subject stays re-attributable.** Pseudonymisation of one copy, never de-identification |
| `usage_events` / `user_feedback_events` | user email | pseudonymise + restrict | Attribution only; aggregates survive |
| `mobile_*` (sessions, prefs, drafts, push, notifications) | email, device label, push endpoint | **erase** | Device/session convenience data |
| collaboration attribution (team members, permissions, reviewers, comments) | email, display name, free-text bodies | pseudonymise + restrict | Workflow attribution; free text may hold third-party data needing controller redaction |
| GxP workflow attribution (reviewer/owner names, executed_by, assigned_to) | actor names, commentary | retain (legal obligation) | Art. 17(3)(b)/(c)/(e) — Part 11 / GxP retention, product safety, legal claims |
| `controlled_records` (locked / retention policy / legal hold) | locked_by, deleted_by, reason_for_change | retain (legal obligation) | Art. 17(3)(b)/(e); a `legal_hold` vetoes erasure outright |
| `raw_archives` + the write-once vault | uploader, original filenames | retain (legal obligation) | Write-once source data under GxP retention |
| `electronic_signature_records` (content-bound) | signer name/email, reason, auth method | **immutable ledger** | The signature digest is computed over the signer identity — altering it invalidates the signature (Part 11 non-repudiation) |
| `pilot_signoff_records` + legacy **unbound** signature rows | signer name/email, rationale | retain (legal obligation) | ⚠️ **Not cryptographically bound** — no digest or chain columns, and the auto-linked signature is created unbound (`record_content_hash` is `None`, so verification reports `bound=False`). Append-only **by policy, not by construction**: an edit here would be undetectable. Never present it to a controller as tamper-evident |
| `audit_events` / `audit_checkpoints` / `audit_chain_head` | actor id, actor email, message, metadata | **immutable ledger** | Append-only SHA-256 chain + HMAC anchors + signed head; see below |

## The honest limit: identity cannot be erased from the audit ledger

MolTrace's audit ledger is an append-only hash chain whose **canonical payload covers the
identity fields** (`actor_user_id`, `actor_email`, `message`, `metadata_json`), sealed by
HMAC anchors and a signed high-water mark.

- An **UPDATE** that clears a name changes that row's `entry_hash`, so every following
  `prev_hash` link fails — verification breaks from that row to the tip.
- A **DELETE** breaks `chain_seq` continuity and drops the live tip below the signed head.

To the verifier — and to a GxP inspector — **an erasure-by-rewrite is indistinguishable
from tampering**. Deleting audit content is itself a data-integrity violation, and 21 CFR
Part 11 §11.10(e) requires the trail be retained at least as long as the records it covers.
So the ledger is not touched, and **the identity in it is not erased today**. We say that
rather than implying otherwise.

### The enabling change (a documented seam, not a shipped capability)

The technique that *would* reconcile the two regimes is **crypto-shredding**: never write
identity to the ledger in plaintext — envelope-encrypt it under a per-subject, per-tenant
key held outside the ledger, and have the chain hash the **ciphertext**. Erasure then
destroys the key: the ciphertext bytes are unchanged, so `entry_hash`, every `prev_hash`,
the anchors and the signed head all still verify — while the plaintext becomes
unrecoverable (NIST SP 800-88 cryptographic erase). It also solves the immutable-backup
problem, which no row-level delete can.

It only holds if **all** of these hold, which is why it is a seam and not a claim:

- the ciphertext is the *only* copy — no plaintext identity in indexes, caches, logs, the
  SIEM pipeline, exports, or notification email;
- the chain hashes ciphertext, never plaintext (a SHA-256 of an email is a **pseudonym**,
  not anonymisation — the preimage space is trivially enumerable);
- key destruction is real: no escrow, no key backup, no DR copy (this deliberately
  conflicts with normal key-recovery policy and must be stated in the DR runbook);
- one key per subject per tenant, never reused.

## Pseudonymisation is not erasure

Replacing a name with a token, a user id, or a hash is **pseudonymisation** (Art. 4(5)).
Under **Recital 26** the record remains **personal data** while re-attribution stays
reasonably possible. So:

- these outcomes are reported as **retained and restricted**, never as "deleted";
- MolTrace's existing ALCOA+ soft-delete (`deleted_at` + `reason_for_change`) is
  *reversible retention*, not erasure — it must never be surfaced as "Erased";
- claiming *anonymisation* of an audit trail in a small tenant is usually not credible —
  a dozen chemists with timestamped actions are often re-identifiable from activity
  patterns alone (singling out / linkability / inference).

## Request workflow

1. **Intake** — the controller receives and *verifies* the request; MolTrace is instructed.
2. **Discovery (Art. 15)** — `privacy.access_report(subject_ref)` enumerates every store
   that may hold the subject's data, *including the ones that cannot be exported or
   erased*, plus the facts only MolTrace knows: actual sub-processor recipients (see the
   [Trust Center](trust_center.md) register), retention windows, the source of data not
   collected from the subject, and the automated-decision position (MolTrace's AI features
   are advisory and human-gated, so they do not produce Art. 22 decisions on their own).
3. **Plan (Art. 17)** — `privacy.erasure_plan(subject_ref, legal_hold=…)` returns the
   per-store disposition and an honest outcome summary. A **legal hold suspends
   destruction for the records it reaches** — but Art. 17(3) bites only "to the extent
   that processing is **necessary**", so a hold does **not** by default sweep in
   credential/transient material (session tokens, authenticator secrets, push endpoints):
   a WebAuthn credential is not necessary to defend a legal claim. Pass `hold_covers` to
   name additional stores the controller's hold explicitly reaches.
4. **Execute** — on documented controller instruction (Art. 28(3)(a)). Execution is
   deliberately *not* automated here; the safe subset (revoke tokens, delete MFA
   credentials, clear `security_events` identity columns) reuses existing helpers.
5. **Respond** — `privacy.response_deadline(received_at)`: **one month** from receipt is
   the backstop ("without undue delay" is the real standard); a **two-month extension**
   must be *notified with reasons inside the first month*.

## Cross-references

[`data_residency.md`](data_residency.md) · [`trust_center.md`](trust_center.md)
(sub-processor register) · [`breach_notification.md`](breach_notification.md) (the
processor/controller split for Art. 33/34) ·
[`compliance_controls_map.md`](compliance_controls_map.md) ·
[`incident_response_plan.md`](incident_response_plan.md)
