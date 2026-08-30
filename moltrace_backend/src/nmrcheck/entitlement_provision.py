"""Provisioning for the offline entitlement authority — two machines, one command each.

    python -m nmrcheck.entitlement_provision --help

**On the deployment**, ``--generate`` creates that deployment's own issuing sub-key and prints a
*certification request*: public material only, whose integrity matters and whose secrecy does
not. The private half never travels, so there is no transport to compromise and no copy held at
MolTrace to leak or be compelled.

**On the offline root machine**, ``--sign-certificate`` reads the request and signs it with the
MolTrace root seed. That seed lives on an air-gapped machine in the founder's custody, is never
in this repository, never in a CI secret, and never in any cloud environment or secret manager:
this repository is public, and a workflow on a public repository can be made to read
repository-scoped secrets in configurations that are easy to get wrong.

Nothing here writes to a secret store, on purpose: this tool has no credentials for one, and a
tool that quietly acquired them would be a second place a signing key could leak from. It writes
a file with owner-only permissions and the operator loads it, through whatever change control
their deployment already has.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import entitlement_statement as es

REQUEST_SCHEMA = "moltrace.deployment.certification-request/1"


def _write_seed(path: Path, seed_hex: str) -> None:
    """Owner-only, and never over an existing file.

    Overwriting a seed silently orphans every statement signed with it, and the symptom appears
    later, on someone else's machine, as a licence that will not verify.
    """
    if path.exists():
        raise SystemExit(
            f"{path} already exists. Refusing to overwrite a signing key: every licence signed "
            "with the existing key would stop verifying, and nothing would say why."
        )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(seed_hex + "\n")


def _new_seed() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw: bytes = Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return raw.hex()


def _machine_has_a_default_route() -> bool:
    """A cheap, honest check that this is not the air-gapped machine.

    Opening a UDP socket to a public address sends no packet; it only asks the kernel whether a
    route exists. It is not a security control — an operator can pull the cable after the check
    — it is a guard against signing on the wrong machine by habit.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.settimeout(0.2)
        probe.connect(("192.0.2.1", 53))  # TEST-NET-1: routable-looking, never routed to
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _generate(args: argparse.Namespace) -> int:
    seed = _new_seed()
    public_key = es.public_key_hex_from_seed(seed)
    assert public_key is not None
    _write_seed(Path(args.seed_out), seed)

    request = {
        "request_schema": REQUEST_SCHEMA,
        "deployment_id": args.deployment_id,
        "tenant_key": args.tenant_key,
        "workspace_url": args.workspace_url,
        "issuing_public_key": public_key,
        "issuing_key_id": es.public_key_id("d", es.ISSUING_KEY_TAG, public_key),
        "requested_modules": sorted(args.modules or es.ALL_MODULES),
        "requested_licence_classes": sorted(args.licence_classes or ["commercial"]),
    }
    Path(args.request_out).write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")

    print(f"Signing key written to {args.seed_out} (owner-only). It is not printed here and")
    print("must not be copied off this machine: load it into this deployment's secret store as")
    print("ENTITLEMENT_ISSUING_PRIVATE_KEY, then delete the file.")
    print(f"Certification request written to {args.request_out}. It is public material —")
    print("its integrity matters, its secrecy does not. Send it to the offline root machine.")
    print(f"  key id: {request['issuing_key_id']}")
    return 0


def _generate_root(args: argparse.Namespace) -> int:
    if _machine_has_a_default_route() and not args.i_accept_this_machine_is_online:
        raise SystemExit(
            "This machine has a network route. A root signing key generated on a networked "
            "machine has been on the network. Generate it on the air-gapped machine, or pass "
            "--i-accept-this-machine-is-online if you are certain."
        )
    seed = _new_seed()
    public_key = es.public_key_hex_from_seed(seed)
    assert public_key is not None
    _write_seed(Path(args.seed_out), seed)
    print(f"Root signing key written to {args.seed_out} (owner-only). It must never leave this")
    print("machine, and this file is the only copy.")
    print(f"  root public key: {public_key}")
    print(f"  root key id:     {es.public_key_id('r', es.ROOT_KEY_TAG, public_key)}")
    print("Publish the public key and the key id in the release evidence, so a customer can")
    print("check for themselves who signed their authorisation.")
    return 0


def _sign_certificate(args: argparse.Namespace) -> int:
    if _machine_has_a_default_route() and not args.i_accept_this_machine_is_online:
        raise SystemExit(
            "This machine has a network route, and this is the only command that reads the "
            "root signing key. Run it on the air-gapped machine, or pass "
            "--i-accept-this-machine-is-online if you are certain."
        )
    request = json.loads(Path(args.request).read_text())
    if request.get("request_schema") != REQUEST_SCHEMA:
        raise SystemExit("That file is not a certification request this tool recognises.")

    root_seed = Path(args.root_seed_file).read_text().strip()
    root_public = es.public_key_hex_from_seed(root_seed)
    if root_public is None:
        raise SystemExit("The root signing key file is empty.")

    not_before = (
        es.parse_iso(args.not_before) if args.not_before else datetime.now(UTC)
    )
    not_after = es.parse_iso(args.not_after)
    if not_after <= not_before:
        raise SystemExit("The authorisation would expire before it began.")

    issuing_public = str(request["issuing_public_key"])
    certificate = {
        "certificate_schema": es.CERTIFICATE_SCHEMA,
        "certificate_id": args.certificate_id,
        "deployment_id": request["deployment_id"],
        "tenant_key": request["tenant_key"],
        "issuing_public_key": issuing_public,
        "issuing_key_id": es.public_key_id("d", es.ISSUING_KEY_TAG, issuing_public),
        "permitted_modules": sorted(args.modules or request["requested_modules"]),
        "permitted_licence_classes": sorted(
            args.licence_classes or request["requested_licence_classes"]
        ),
        "not_before": es.iso_utc(not_before),
        "not_after": es.iso_utc(not_after),
        "root_key_id": es.public_key_id("r", es.ROOT_KEY_TAG, root_public),
    }
    certificate_bytes = es.canonical_bytes(certificate)
    signature = es.sign_payload(es.CERTIFICATE_DOMAIN, certificate, root_seed)

    print("Set both of these in the deployment's secret store, then restart it:")
    print()
    print(f"ENTITLEMENT_CERTIFICATE={es.b64u_encode(certificate_bytes)}")
    print(f"ENTITLEMENT_CERTIFICATE_SIGNATURE={signature}")
    print(f"ENTITLEMENT_ROOT_PUBLIC_KEY={root_public}")
    print()
    print("Record these in the deployment's change control:")
    print(f"  root key id:     {certificate['root_key_id']}")
    print(f"  issuing key id:  {certificate['issuing_key_id']}")
    print(f"  expires:         {certificate['not_after']}")
    print()
    print("The expiry above is the only control that reaches an installation which never")
    print("reconnects and never updates. Choose it deliberately.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmrcheck.entitlement_provision",
        description=(
            "Provision a deployment to issue offline licences for its own installations."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser(
        "generate",
        help="On the deployment: create its issuing key and a certification request.",
    )
    generate.add_argument("--deployment-id", required=True)
    generate.add_argument("--tenant-key", required=True)
    generate.add_argument("--workspace-url", required=True)
    generate.add_argument("--seed-out", default="entitlement_issuing.seed")
    generate.add_argument("--request-out", default="entitlement_certification_request.json")
    generate.add_argument("--modules", nargs="*", choices=list(es.ALL_MODULES))
    generate.add_argument("--licence-classes", nargs="*", choices=list(es.LICENCE_CLASSES))
    generate.set_defaults(handler=_generate)

    root = sub.add_parser(
        "generate-root", help="On the air-gapped machine: create the MolTrace root key."
    )
    root.add_argument("--seed-out", default="moltrace_entitlement_root.seed")
    root.add_argument("--i-accept-this-machine-is-online", action="store_true")
    root.set_defaults(handler=_generate_root)

    sign = sub.add_parser(
        "sign-certificate",
        help="On the air-gapped machine: authorise one deployment to issue licences.",
    )
    sign.add_argument("--request", required=True)
    sign.add_argument("--root-seed-file", required=True)
    sign.add_argument("--certificate-id", required=True)
    sign.add_argument("--not-before")
    sign.add_argument(
        "--not-after",
        required=True,
        help=(
            "When this deployment's authority to issue ends. A security parameter, not "
            "paperwork: it is the only control that reaches an installation which never "
            "reconnects."
        ),
    )
    sign.add_argument("--modules", nargs="*", choices=list(es.ALL_MODULES))
    sign.add_argument("--licence-classes", nargs="*", choices=list(es.LICENCE_CLASSES))
    sign.add_argument("--i-accept-this-machine-is-online", action="store_true")
    sign.set_defaults(handler=_sign_certificate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = args.handler
    return int(handler(args))


if __name__ == "__main__":  # pragma: no cover - a console entry point
    sys.exit(main())
