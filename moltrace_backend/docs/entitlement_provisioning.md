# Provisioning a deployment to license offline installations

An offline installation cannot call back to ask whether the customer is still entitled, and a
licence that requires a callback is rejected by pharmaceutical IT before the science is ever
evaluated. So a deployment issues a **signed entitlement statement** that the installation
verifies offline, against a certificate chain rooted in a MolTrace root key pinned in the
application.

This runbook is the procedure only. **This repository is public**: it contains no key material,
no deployment identifiers and no customer names, and nothing you produce by following it belongs
in a commit. The provisioning tool writes signing keys with owner-only permissions and the
repository ignores `*.seed`.

## What the two levels are for

MolTrace holds an **offline root** and signs one certificate per deployment. That certificate
binds the deployment's own **issuing sub-key** to its deployment and tenant identifiers, and
carries the ceiling it may not exceed — which products, and which kinds of licence.

The deployment then signs its own statements locally. No call to MolTrace on issuance, and no
availability dependency on MolTrace: a deployment cut off from the vendor keeps entitling its own
installations. That is what makes a perpetual licence survivable rather than a promise.

The issuing key is **generated on the deployment and never leaves it**. The private half then
never travels, so there is no transport to compromise and no copy held at MolTrace to leak or be
compelled. Only the public key and the identifiers are sent for certification.

## Where each key lives

| Key | Where it lives | Never |
|---|---|---|
| MolTrace root private key | An air-gapped machine, in the founder's custody. Used only to sign deployment certificates, one at a time, by a person | Never in this repository. Never in a CI secret. Never in any cloud environment or secret manager. Never on a machine that has been on the network with the seed present |
| MolTrace root public key | Pinned in the desktop application; published in the release evidence and the supplier validation package so a customer can check who signed | — |
| Deployment issuing private key | Generated on the deployment, read through the same secret path as every other secret | Never logged. Never returned by any route, including the authority diagnostic. Never written to an audit record |
| Deployment certificate and its signature | Deployment configuration, not a database row | — |

The certificate is configuration rather than a stored row on purpose: a database restore from
before a withdrawal would otherwise bring a withdrawn certificate back. Configuration changes
deliberately, is visible in the deployment's own change control, and rotates without a migration.

**No signing key of any kind is a repository CI secret.** A workflow on a public repository can
be made to read repository-scoped secrets in configurations that are easy to get wrong, and
exfiltration through public-repository CI is a named threat. Release signing is a separate,
manually triggered pipeline; the entitlement root stays offline entirely.

## The procedure — six steps, two machines

**1. On the deployment** (or on an operator workstation targeting that deployment's secret
store):

```bash
uv run python -m nmrcheck.entitlement_provision generate \
  --deployment-id <id> --tenant-key <key> --workspace-url <url> \
  --licence-classes commercial
```

This writes the issuing key to `entitlement_issuing.seed` with owner-only permissions and prints
a **certification request**. The key itself is printed nowhere. Load it into the deployment's
secret store as `ENTITLEMENT_ISSUING_PRIVATE_KEY`, then delete the file.

**2. Move the certification request to the air-gapped machine** by whatever medium you choose.
It is public material: its integrity matters, its secrecy does not.

**3. On the air-gapped machine**, once ever, create the root:

```bash
uv run python -m nmrcheck.entitlement_provision generate-root
```

Then, for each deployment:

```bash
uv run python -m nmrcheck.entitlement_provision sign-certificate \
  --request <request file> --root-seed-file <root seed> \
  --certificate-id <id> --not-after <ISO 8601 date>
```

This is the only command that reads the root key. It refuses to run on a machine with a network
route unless you pass `--i-accept-this-machine-is-online`, and the refusal says why.

**Choose `--not-after` deliberately.** It is a security parameter, not paperwork: it is the only
control that reaches an installation which never reconnects and never updates. See "the honest
limit" below.

**4. Move the printed values back** and set them in the deployment's secret store:
`ENTITLEMENT_CERTIFICATE`, `ENTITLEMENT_CERTIFICATE_SIGNATURE`, `ENTITLEMENT_ROOT_PUBLIC_KEY`.

**5. Publish the two commercial terms**, which have **no defaults**:

| Setting | What it is |
|---|---|
| `ENTITLEMENT_OFFLINE_PERIOD_DAYS` | How long an installation may keep working after its statement expires |
| `ENTITLEMENT_STATEMENT_VALIDITY_HOURS` | How long a statement lasts before it is refreshed |
| `ENTITLEMENT_LICENCE_CLASS` | Which kind of licence this deployment issues, when its certificate permits more than one |

Neither period has a default because neither has been measured, and a plausible-looking round
number that nobody chose would be inside a signature. A deployment that has not published them
declines to issue and says so, which is deliberate: the missing commercial decision blocks the
release rather than being papered over.

**6. Restart the deployment and verify.** Startup validation self-checks the whole chain, and a
deployment that fails it refuses to issue and names the cause. Then read the entitlement
authority diagnostic as an administrator: it should report the deployment as provisioned, with
its certificate and window. Record the root key id, the issuing key id and the expiry in the
deployment's change control.

## Withdrawing offline use

**The primary control is declining to reissue.** Statements are short-lived and refreshed on
every connection, so setting an installation's device session to *revoked* stops the next
refresh. The refresh then succeeds and returns no entitlement, which the installation treats as
a withdrawal rather than a fault: it keeps the statement it already holds, which runs out on its
own terms, and stops asking.

Either the installation's owner or an administrator can do this, and an administrator can do it
for an installation they do not own — a withdrawal that needed the compromised user's own
cooperation would not be much of a control. An administrator gains nothing else over another
person's installations, and the audit record names who performed the withdrawal, because that is
exactly the event an inspector asks about.

**Certificate-level withdrawal** — for a compromised or retired deployment sub-key — is
published through the security advisory channel and consumed by installations from the
application update, never from the network.

## The honest limit

An installation that never reconnects and never updates will not learn of a certificate
withdrawal. The only controls that reach it are the certificate's own expiry and the statement's
own expiry plus the offline period. **Nothing else does.** This belongs in the supplier
assessment and the risk register phrased as a limit, not as a mitigation.

The same honesty applies to the clock. The installation keeps a high-water mark of the latest
instant it has seen attributed to the deployment, and evaluates expiry against the later of that
mark and its own clock, so setting the clock backwards extends nothing. **That mark cannot be
authenticated.** It lives on hardware the customer controls, and authenticating it would need a
key on that same hardware — a key that verifies is a key that forges. It defeats accidental
clock skew and casual tampering, and nothing more. The real bound on a determined local attacker
is the one above: the deployment declines to reissue, and the statement expires. Offline
entitlement on hardware someone else controls is a time-bounded risk to be sized, not a threat
to be eliminated.

## What never stops

**Reading, exporting and verifying existing records never stops**, whatever the entitlement
state — no licence, no network, expired certificate, withdrawn installation. A customer is not
locked out of their own regulated records by a commercial term. An expired licence that made a
batch record unreadable during an inspection would be a data-integrity failure caused by a
billing system.

What entitlement does govern is *new* work: running a new analysis, and installing a new package
profile. Those stop. Everything already on the machine stays readable, exportable and verifiable
for as long as the installation runs.
