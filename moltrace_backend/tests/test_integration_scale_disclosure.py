"""Every path that can produce an ungrounded spectrum has to say so.

The disclosure itself is exercised end-to-end in
``test_fid_process_without_structure.py``. What this file guards is *coverage*:
that no new caller of the two spectrum producers quietly reintroduces an
undisclosed relative scale.

Why a source-level guard rather than a runtime one. The natural home for this is
inside ``spectrum.parse_processed_spectrum`` and ``fid.process_bruker_1d_zip``,
where it could not be bypassed at all. Both files were carrying ~400 lines of
unrelated staged work when this landed, so the disclosure was attached at the
call sites instead and this test stands in for the enforcement the producers
would otherwise give for free. **If the disclosure is ever moved into those two
functions, delete this file** -- it is scaffolding for a workaround, not a
permanent invariant.

The rule each caller must satisfy is one of:

* it passes ``expected_total_h=`` (a structure may ground the budget), or
* it routes the result through ``disclose_relative_integrals``.

A caller doing neither is reporting ratios as proton counts with nothing saying
so, which is exactly what shipped on the orchestration artifact and QC
assessment paths before this.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "nmrcheck"

PRODUCERS = {"parse_processed_spectrum", "process_bruker_1d_zip"}

# The producers themselves, and the module holding the helper.
#
# ``api.py`` is exempt for a different reason and gets its own test below: it
# rebinds both producer names to local wrappers that always disclose, so every
# one of its ~10 call sites is covered by construction. Applying the generic
# rule there would flag calls that are in fact already disclosed.
EXEMPT_MODULES = {"spectrum.py", "fid.py", "integration_scale.py", "api.py"}

# The aliases api.py imports the real producers under. They must appear only
# inside the wrappers -- a call to an alias anywhere else skips the disclosure.
API_UPSTREAM_ALIASES = {
    "_parse_processed_spectrum_upstream": "parse_processed_spectrum",
    "_process_bruker_1d_zip_upstream": "process_bruker_1d_zip",
}


def _producer_calls(tree: ast.AST) -> list[ast.Call]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name in PRODUCERS or (
            name is not None and name.strip("_").removesuffix("_upstream") in PRODUCERS
        ):
            found.append(node)
    return found


def _is_disclosed(call: ast.Call, tree: ast.AST) -> bool:
    """True if the call supplies a budget or is wrapped by the discloser."""
    if any(kw.arg == "expected_total_h" for kw in call.keywords):
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "disclose_relative_integrals":
            continue
        if any(arg is call for arg in ast.walk(node) if isinstance(arg, ast.Call)):
            return True
    return False


def _modules() -> list[Path]:
    return sorted(p for p in SRC.glob("*.py") if p.name not in EXEMPT_MODULES)


@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
def test_every_spectrum_producer_call_declares_its_scale(module: Path) -> None:
    tree = ast.parse(module.read_text())
    offenders = [
        f"{module.name}:{call.lineno}"
        for call in _producer_calls(tree)
        if not _is_disclosed(call, tree)
    ]
    assert not offenders, (
        f"{offenders} call a spectrum producer without passing expected_total_h "
        "and without routing the result through disclose_relative_integrals, so "
        "the integrals are reported as proton counts on a scale anchored to the "
        "smallest signal. Wrap the call: "
        "disclose_relative_integrals(<call>, expected_total_h=<budget or None>)."
    )


def test_the_api_wrappers_are_the_only_users_of_the_raw_producers() -> None:
    """api.py's coverage rests entirely on the rebinding, so verify the rebinding.

    Every route calls the local ``parse_processed_spectrum`` /
    ``process_bruker_1d_zip``, which disclose. That holds only while the
    ``_upstream`` aliases stay inside those two wrappers -- one call to an alias
    elsewhere is a silent bypass that the generic rule above cannot see.
    """
    tree = ast.parse((SRC / "api.py").read_text())
    wrappers = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in PRODUCERS
    }
    assert wrappers.keys() == PRODUCERS, (
        f"api.py no longer defines disclosing wrappers for {PRODUCERS - wrappers.keys()}; "
        "its call sites are now undisclosed. Remove api.py from EXEMPT_MODULES."
    )

    for alias, wrapper_name in API_UPSTREAM_ALIASES.items():
        inside = {
            node.lineno
            for node in ast.walk(wrappers[wrapper_name])
            if isinstance(node, ast.Name) and node.id == alias
        }
        everywhere = {
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == alias
        }
        assert everywhere == inside, (
            f"{alias} is used at api.py:{sorted(everywhere - inside)}, outside "
            f"{wrapper_name}(). That call bypasses the scale disclosure -- call "
            f"{wrapper_name}() instead."
        )


def test_the_guard_can_actually_fail() -> None:
    """A guard that cannot fail is decoration.

    Verifies the detector on a synthetic bypass rather than trusting that a
    green run means it looked at anything.
    """
    tree = ast.parse("preview = parse_processed_spectrum(filename='x', content=b'')")
    calls = _producer_calls(tree)
    assert len(calls) == 1
    assert not _is_disclosed(calls[0], tree)


def test_the_guard_accepts_both_permitted_forms() -> None:
    grounded = ast.parse("p = parse_processed_spectrum(content=b'', expected_total_h=6)")
    assert _is_disclosed(_producer_calls(grounded)[0], grounded)

    wrapped = ast.parse(
        "p = disclose_relative_integrals(\n"
        "    parse_processed_spectrum(content=b''), expected_total_h=None\n"
        ")"
    )
    assert _is_disclosed(_producer_calls(wrapped)[0], wrapped)
