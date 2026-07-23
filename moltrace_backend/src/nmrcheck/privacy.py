"""DSAR + right-to-erasure planner and personal-data map (Security Prompt 23).

Assists the **controller** (the customer) in answering a data-subject request against a
MolTrace tenant: it produces an Art. 15 **discovery report**, an Art. 17 **erasure plan**
with an honest per-store disposition, and the Art. 12(3) **response deadlines**.

Three things this module deliberately does **not** do:

* **It does not adjudicate.** Under Art. 28(3)(e) a processor *assists* the controller
  "by appropriate technical and organisational measures"; it does not verify the
  requester's identity, decide scope, judge a request excessive, or apply the Art. 15(4)
  balancing against third-party rights. Those are controller determinations — a
  processor that made them would be determining purposes and means (Art. 28(10)).
* **It does not execute deletions.** It plans. Execution happens on documented controller
  instruction (Art. 28(3)(a)); the executable seam is noted per store.
* **It never calls pseudonymisation "erasure."** Replacing a name with a token, a user id
  or a hash is pseudonymisation (Art. 4(5)); under Recital 26 the record is *still
  personal data* while re-attribution remains reasonably possible, so it is reported as
  **retained and restricted**, never as deleted. A SHA-256 of an email is a pseudonym,
  not anonymisation — the preimage space is trivially enumerable.

**The immutable-ledger limit (stated honestly).** MolTrace's audit ledger is an
append-only SHA-256 hash chain whose canonical payload covers ``actor_user_id``,
``actor_email``, ``message`` and ``metadata_json``, sealed by HMAC anchors and a signed
high-water mark. Rewriting or deleting a row changes that row's ``entry_hash``, breaks
every following ``prev_hash`` link, and is indistinguishable from tampering to both the
verifier and a GxP inspector — and deleting audit content is itself a data-integrity
violation (Part 11 §11.10(e) requires audit trails be retained at least as long as the
records they cover). **Identity therefore cannot be removed from the ledger today.** The
architectural change that *would* permit it — envelope-encrypting identity attributes
under a per-subject key so the chain hashes *ciphertext*, then destroying the key
("crypto-shredding", NIST SP 800-88 cryptographic erase) — is a documented seam, not a
shipped capability. See docs/security/privacy_data_map.md.

Compliance framing: these controls are **designed to support** the customer's GDPR
obligations. MolTrace does not claim to *be* GDPR-compliant or to *guarantee* erasure;
the compliance determination remains the controller's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

# Art. 12(3): respond without undue delay and in any event within one month of receipt;
# extendable by two further months where necessary given complexity/number — but the
# controller must tell the subject about the extension, with reasons, inside month one.
#
# These are CALENDAR months, not fixed day counts: GDPR periods run under Reg. (EEC,
# Euratom) 1182/71, so a month ends on the same date of the following month. Using 30/90
# days computes a LATE deadline for short months (31 Jan + 1 month is 28 Feb, not 2 Mar).
RESPONSE_MONTHS = 1
EXTENSION_MONTHS = 2

Disposition = Literal[
    "erase",  # can be destroyed outright — no evidentiary or retention value
    "pseudonymise_restrict",  # identity cleared, row survives — STILL personal data
    "retain_legal_obligation",  # Art. 17(3)(b)/(c)/(e) retention — restricted, not erased
    "immutable_ledger",  # append-only integrity record — cannot be rewritten at all
]

#: Dispositions whose result is still personal data under Recital 26 — must never be
#: reported to a data subject as "erased".
_STILL_PERSONAL = frozenset(
    {"pseudonymise_restrict", "retain_legal_obligation", "immutable_ledger"}
)


def _add_months(moment: datetime, months: int) -> datetime:
    """Add calendar months, clamping to the last valid day (31 Jan + 1 = 28/29 Feb)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    # Days in the target month (works for Dec via the year rollover).
    if month == 12:
        last_day = 31
    else:
        last_day = (datetime(year, month + 1, 1, tzinfo=moment.tzinfo) - timedelta(days=1)).day
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


_VALID_DISPOSITIONS = frozenset(
    {"erase", "pseudonymise_restrict", "retain_legal_obligation", "immutable_ledger"}
)


@dataclass(frozen=True)
class StoreDisposition:
    """One personal-data store and what can honestly be done with it."""

    store: str
    data_classes: tuple[str, ...]
    disposition: Disposition
    basis: str
    note: str = ""

    def __post_init__(self) -> None:
        # Guard against a typo'd/unknown disposition silently reading as neither
        # erasable nor still-personal-data (which would defeat the honesty checks).
        if self.disposition not in _VALID_DISPOSITIONS:
            raise ValueError(f"{self.store}: unknown disposition {self.disposition!r}")

    @property
    def still_personal_data(self) -> bool:
        return self.disposition in _STILL_PERSONAL

    @property
    def erasable(self) -> bool:
        return self.disposition == "erase"


#: The personal-data map: every store group that can hold data about a natural person,
#: with its honest disposition. This IS the machine-readable data-classification map
#: rendered in docs/security/privacy_data_map.md.
DATA_MAP: tuple[StoreDisposition, ...] = (
    StoreDisposition(
        store="users",
        data_classes=("email", "password hash", "account status/timestamps"),
        disposition="pseudonymise_restrict",
        basis="Identity of record; email is UNIQUE and denormalised into many attribution columns.",
        note=(
            "Tombstone the email to a non-routable value and scramble the credential; the "
            "row must survive so historical attribution keys do not dangle. Still personal "
            "data while the tombstone remains linkable."
        ),
    ),
    StoreDisposition(
        store="session_tokens / session_families / refresh_tokens / user_action_tokens",
        data_classes=("session + credential material", "device fingerprint hash"),
        disposition="erase",
        basis="Credential material with no evidentiary value; already revocable in place.",
        note="Executable today via database.revoke_all_user_tokens + row deletion.",
    ),
    StoreDisposition(
        store="mfa_* (TOTP / WebAuthn credentials + challenges / recovery codes)",
        data_classes=("authenticator secrets", "public keys", "device labels"),
        disposition="erase",
        basis="Authenticator material; the store already hard-deletes these rows.",
    ),
    StoreDisposition(
        store="scim_users",
        data_classes=("IdP external id", "userName/email", "raw IdP profile attributes"),
        disposition="erase",
        basis="Per-connection IdP mirror; deprovisioning soft-disables, hard-delete exists.",
        note="The upstream IdP is the customer's own controller-side system.",
    ),
    StoreDisposition(
        store="email_outbox",
        data_classes=("recipient address", "subject/body (may embed reset links)"),
        disposition="erase",
        basis="Transient delivery queue; no retention value once delivered.",
    ),
    StoreDisposition(
        store="security_events",
        data_classes=("actor email", "IP address", "user agent", "metadata"),
        disposition="pseudonymise_restrict",
        basis=(
            "Separate table — NO hash chain covers it, so identity columns can be cleared "
            "without breaking integrity. Kept for security-monitoring necessity."
        ),
        note=(
            "Clearing actor_email/ip_address/user_agent removes the identifier FROM THIS "
            "TABLE ONLY. Each security event also writes a paired audit-chain row carrying "
            "actor identity and an entity_id back-pointer — that row is immutable, so the "
            "subject remains re-attributable. This is pseudonymisation of one copy, never "
            "de-identification. The same caveat applies to any store whose writer also "
            "emits an audit row."
        ),
    ),
    StoreDisposition(
        store="usage_events / user_feedback_events",
        data_classes=("user email (attribution only)",),
        disposition="pseudonymise_restrict",
        basis="Analytics attribution; aggregates survive without the identifier.",
    ),
    StoreDisposition(
        store="mobile_* (device sessions, preferences, drafts, push subscriptions, notifications)",
        data_classes=("user email", "device label/type", "push endpoint (device identifier)"),
        disposition="erase",
        basis="Device/session convenience data with no evidentiary or retention value.",
    ),
    StoreDisposition(
        store="collaboration attribution (team members, permissions, reviewers, comments)",
        data_classes=("email", "display name", "free-text comment bodies"),
        disposition="pseudonymise_restrict",
        basis="Workflow attribution; comment bodies may carry third-party data needing redaction.",
        note="Third-party personal data in free text is a controller redaction decision.",
    ),
    StoreDisposition(
        store="GxP workflow attribution (reviewer/owner names, executed_by, assigned_to)",
        data_classes=("actor names", "reviewer commentary"),
        disposition="retain_legal_obligation",
        basis=(
            "Art. 17(3)(b)/(c)/(e): attribution on regulated records under Part 11 / GxP "
            "retention, product-safety and legal-claims exposure."
        ),
        note="Restricted, not erased, for the retention period; then re-assess.",
    ),
    StoreDisposition(
        store="controlled_records (locked / under a retention policy or legal hold)",
        data_classes=("locked_by", "deleted_by", "reason_for_change"),
        disposition="retain_legal_obligation",
        basis="Art. 17(3)(b)/(e); a retention policy carrying legal_hold vetoes erasure outright.",
        note="Already has ALCOA+ soft-delete semantics (reversible, attributed, reasoned).",
    ),
    StoreDisposition(
        store="raw_archives / the write-once raw-data vault",
        data_classes=("uploader id", "original filenames (may embed names or lot ids)"),
        disposition="retain_legal_obligation",
        basis="Write-once source data under GxP retention; the vault is immutable by construction.",
    ),
    StoreDisposition(
        store="electronic_signature_records (content-bound)",
        data_classes=("signer name", "signer email", "signing reason", "auth method"),
        disposition="immutable_ledger",
        basis=(
            "21 CFR Part 11 non-repudiation: the signature digest is computed over the "
            "signer identity, so altering it invalidates the signature."
        ),
        note="Erasing identity here would destroy the very thing the signature attests.",
    ),
    StoreDisposition(
        store="pilot_signoff_records + legacy unbound signature rows",
        data_classes=("signer name", "signer email", "decision rationale"),
        disposition="retain_legal_obligation",
        basis=(
            "Countersigned acceptance records retained under Art. 17(3)(b)/(e). NOT "
            "cryptographically bound: these rows carry no digest or chain columns, and the "
            "auto-linked signature is created unbound (record_content_hash is None), so "
            "verification reports bound=False."
        ),
        note=(
            "Treated as append-only by policy, not by construction — an edit here would be "
            "undetectable. Do not present it to a controller as tamper-evident."
        ),
    ),
    StoreDisposition(
        store="audit_events / audit_checkpoints / audit_chain_head",
        data_classes=("actor user id", "actor email", "message", "metadata"),
        disposition="immutable_ledger",
        basis=(
            "Append-only SHA-256 hash chain + HMAC anchors + signed high-water mark; the "
            "canonical payload covers the identity fields, so any edit or delete breaks "
            "verification and is indistinguishable from tampering. Part 11 §11.10(e) "
            "requires the trail be retained at least as long as the records it covers."
        ),
        note=(
            "NOT erasable today. The enabling change is crypto-shredding: encrypt identity "
            "under a per-subject key so the chain hashes ciphertext, then destroy the key. "
            "Documented as a seam, not a shipped capability."
        ),
    ),
)


# --------------------------------------------------------------------------- Art. 15


@dataclass
class AccessReport:
    """The Art. 15 discovery report a processor hands the controller."""

    subject_ref: str
    generated_at: datetime
    stores: tuple[StoreDisposition, ...]
    controller_facts: tuple[str, ...]
    limits: tuple[str, ...]


#: Art. 15(1)(a)-(h) facts only MolTrace can supply; the controller assembles the answer.
_CONTROLLER_FACTS: tuple[str, ...] = (
    "Recipients (Art. 15(1)(c)): the sub-processors listed in docs/security/trust_center.md "
    "— on request the controller may need to name actual recipients, not just categories.",
    "Storage period (Art. 15(1)(d)): regulated records follow the applicable retention "
    "policy (a 7-year default floor); non-regulated stores are kept only as long as needed.",
    "Source (Art. 15(1)(g)): data not collected from the subject typically originate from "
    "the customer's own identity provider via SSO/SCIM.",
    "Automated decision-making (Art. 15(1)(h)): MolTrace's AI features are advisory and "
    "human-gated — a deterministic verifier arbitrates and a human signs off, so they do "
    "not produce decisions with legal or similarly significant effect on their own.",
)


def access_report(subject_ref: str, *, now: datetime | None = None) -> AccessReport:
    """Build the Art. 15 discovery report for a data subject.

    Lists every store that may hold their personal data — **including the ones that
    cannot be exported or erased** — so the controller knows what exists.
    """
    return AccessReport(
        subject_ref=subject_ref,
        generated_at=now or datetime.now(UTC),
        stores=DATA_MAP,
        controller_facts=_CONTROLLER_FACTS,
        limits=(
            "MolTrace acts as a processor and assists only (Art. 28(3)(e)); the controller "
            "verifies identity, decides scope, applies Art. 15(4) third-party balancing, "
            "and responds to the data subject.",
            "Free-text fields (comments, reasons, filenames) may contain third-party "
            "personal data requiring controller redaction before disclosure.",
        ),
    )


# --------------------------------------------------------------------------- Art. 17


@dataclass
class ErasurePlan:
    subject_ref: str
    generated_at: datetime
    dispositions: tuple[StoreDisposition, ...]
    legal_hold: bool = False

    @property
    def erasable(self) -> tuple[StoreDisposition, ...]:
        return tuple(d for d in self.dispositions if d.disposition == "erase")

    @property
    def restricted(self) -> tuple[StoreDisposition, ...]:
        """Stores that survive as (still) personal data — pseudonymised or retained."""
        return tuple(d for d in self.dispositions if d.still_personal_data)

    def summary(self) -> str:
        """An honest one-paragraph outcome statement — never calls pseudonymisation erasure."""
        erased = len(self.erasable)
        pseudo = sum(1 for d in self.dispositions if d.disposition == "pseudonymise_restrict")
        retained = sum(1 for d in self.dispositions if d.disposition == "retain_legal_obligation")
        immutable = sum(1 for d in self.dispositions if d.disposition == "immutable_ledger")
        text = (
            f"{erased} store group(s) can be erased outright; {pseudo} can have the "
            f"identifier cleared but the records survive and REMAIN PERSONAL DATA "
            f"(pseudonymisation, not erasure); {retained} are retained under a legal "
            f"obligation (Art. 17(3)) and are restricted rather than erased; {immutable} "
            f"are append-only integrity records that cannot be altered at all."
        )
        if self.legal_hold:
            text += (
                " A LEGAL HOLD is in force: destruction is suspended for the records it "
                "reaches. Credential/transient material is not held by default — Art. 17(3) "
                "applies only to the extent processing is necessary for the ground invoked."
            )
        return text


def erasure_plan(
    subject_ref: str,
    *,
    legal_hold: bool = False,
    hold_covers: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> ErasurePlan:
    """Plan an Art. 17 erasure request across the personal-data map.

    ``legal_hold`` suspends destruction for the **records** the hold reaches. Art. 17(3)
    applies only "to the extent that processing is necessary", so a hold does **not** by
    default sweep in credential/transient material — an authenticator secret or a push
    endpoint is not necessary to defend a legal claim, and treating a hold as a blanket
    veto is exactly the over-broad pattern the necessity limb forbids. Pass ``hold_covers``
    with store names the controller's hold explicitly reaches to widen it.
    """
    covers = set(hold_covers or ())
    dispositions: list[StoreDisposition] = []
    for entry in DATA_MAP:
        reached = entry.disposition != "immutable_ledger" and (
            entry.disposition != "erase" or entry.store in covers
        )
        if legal_hold and reached:
            dispositions.append(
                StoreDisposition(
                    store=entry.store,
                    data_classes=entry.data_classes,
                    disposition="retain_legal_obligation",
                    basis=(
                        "Legal hold in force — destruction suspended (Art. 17(3)(e)) to the "
                        "extent the hold covers this record."
                    ),
                    note=(
                        f"Absent the hold: {entry.disposition}."
                        + (f" {entry.note}" if entry.note else "")
                    ),
                )
            )
        else:
            dispositions.append(entry)
    return ErasurePlan(
        subject_ref=subject_ref,
        generated_at=now or datetime.now(UTC),
        dispositions=tuple(dispositions),
        legal_hold=legal_hold,
    )


# --------------------------------------------------------------------------- Art. 12(3)


@dataclass(frozen=True)
class ResponseDeadline:
    received_at: datetime
    due_at: datetime
    extension_notice_due_at: datetime
    extended_due_at: datetime
    note: str


def response_deadline(received_at: datetime, *, now: datetime | None = None) -> ResponseDeadline:
    """Art. 12(3) deadlines for a data-subject request.

    One month from receipt is the outer backstop — "without undue delay" is the real
    standard. The two-month extension is **not** self-executing: the controller must tell
    the subject about it, with reasons, inside the first month.
    """
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    base = _add_months(received_at, RESPONSE_MONTHS)
    return ResponseDeadline(
        received_at=received_at,
        due_at=base,
        # Art. 12(3) requires the extension to be notified "within one month of receipt" —
        # the same instant as the base deadline. The equality is correct, not redundant.
        extension_notice_due_at=base,
        extended_due_at=_add_months(received_at, RESPONSE_MONTHS + EXTENSION_MONTHS),
        note=(
            "Respond without undue delay; one month is the backstop. Any two-month "
            "extension must be notified to the subject WITH REASONS within the first month."
        ),
    )


# --------------------------------------------------------------------------- invariant


def assert_no_erasure_overclaim(plan: ErasurePlan) -> None:
    """Guard the honesty invariant: nothing that survives as personal data may be
    presented as erased. Raises AssertionError if the map is ever mis-labelled."""
    for entry in plan.dispositions:
        if entry.erasable and entry.still_personal_data:  # pragma: no cover - invariant
            raise AssertionError(f"{entry.store}: cannot be both erasable and still personal data")


@dataclass
class DataMapEntry:
    """Flat rendering of the map for documentation/registers."""

    store: str
    classes: str
    disposition: str
    basis: str
    still_personal_data: bool = field(default=False)


def render_data_map() -> list[DataMapEntry]:
    return [
        DataMapEntry(
            store=d.store,
            classes=", ".join(d.data_classes),
            disposition=d.disposition,
            basis=d.basis,
            still_personal_data=d.still_personal_data,
        )
        for d in DATA_MAP
    ]
