"""qNMR purity is reachable over HTTP.

SpectraCheck's headline analytical claim is a qNMR purity determination, and the engine behind it
— internal-standard and PULCON, with GUM uncertainty propagation — was fully implemented and
completely unreachable: no route referenced ``moltrace.spectroscopy.qnmr`` at all. The only qNMR
surface was gated behind a regulatory dossier, which a SpectraCheck-only customer does not have.

These tests pin the arithmetic against a hand-computable case rather than a golden number, so a
regression in the wiring (wrong argument order, dropped factor, swapped analyte/standard) fails
loudly instead of returning a plausible-looking purity.
"""

import pytest


def _internal_standard_body(**overrides):
    # Chosen so the answer is exactly 100%: every ratio is 1 except the integral ratio, which
    # cancels the proton ratio. Purity = (2/1)·(1/2)·(100/100)·(10/10)·100 = 100.
    body = {
        "analyte_integral": 2.0,
        "standard_integral": 1.0,
        "analyte_protons": 2,
        "standard_protons": 1,
        "analyte_molar_mass": 100.0,
        "standard_molar_mass": 100.0,
        "analyte_mass_mg": 10.0,
        "standard_mass_mg": 10.0,
        "standard_purity_percent": 100.0,
    }
    body.update(overrides)
    return body


def test_internal_standard_purity_is_reachable_and_correct(client, api_headers):
    with client:
        res = client.post(
            "/spectrum/qnmr/purity", headers=api_headers, json=_internal_standard_body()
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["method"] == "internal_standard"
    assert body["purity_percent"] == pytest.approx(100.0, abs=1e-9)
    # The uncertainty must be a real propagated number, not zero-by-omission.
    assert body["uncertainty_percent"] > 0
    assert body["relative_uncertainty"] > 0


def test_the_whole_computation_comes_back_with_the_answer(client, api_headers):
    """A purity value a reviewer cannot re-derive is a number to take on trust. Every intermediate
    ratio is returned so the result can be reconstructed from the record alone."""
    with client:
        res = client.post(
            "/spectrum/qnmr/purity", headers=api_headers, json=_internal_standard_body()
        )
    body = res.json()
    assert body["inputs"], "inputs must be echoed for provenance"
    assert body["intermediates"], "intermediates must be returned so the result is re-derivable"
    assert body["notes"], "the result must carry its own decision-support framing"


def test_halving_the_analyte_signal_halves_the_purity(client, api_headers):
    """Directional check: the result must actually track the integrals, so a wiring mistake that
    swapped analyte and standard could not pass."""
    with client:
        full = client.post(
            "/spectrum/qnmr/purity", headers=api_headers, json=_internal_standard_body()
        ).json()
        half = client.post(
            "/spectrum/qnmr/purity",
            headers=api_headers,
            json=_internal_standard_body(analyte_integral=1.0),
        ).json()
    assert half["purity_percent"] == pytest.approx(full["purity_percent"] / 2, rel=1e-9)


def test_a_supplied_uncertainty_is_honoured(client, api_headers):
    """Supplying your own relative uncertainties is what turns the reported figure into your
    laboratory's estimate rather than the engine's default."""
    with client:
        default = client.post(
            "/spectrum/qnmr/purity", headers=api_headers, json=_internal_standard_body()
        ).json()
        tighter = client.post(
            "/spectrum/qnmr/purity",
            headers=api_headers,
            json=_internal_standard_body(integral_rel_u=0.0, mass_rel_u=0.0),
        ).json()
    assert tighter["uncertainty_percent"] < default["uncertainty_percent"]


def test_an_impossible_input_is_a_bad_request_not_a_crash(client, api_headers):
    with client:
        res = client.post(
            "/spectrum/qnmr/purity",
            headers=api_headers,
            json=_internal_standard_body(analyte_integral=0.0),
        )
    # Rejected by the request contract before it ever reaches the engine.
    assert res.status_code == 422, res.text


def test_pulcon_purity_is_reachable(client, api_headers):
    """The external-reference path, for when the standard cannot be co-dissolved."""
    with client:
        res = client.post(
            "/spectrum/qnmr/purity/pulcon",
            headers=api_headers,
            json={
                "analyte_integral": 1.0,
                "analyte_protons": 1,
                "analyte_nominal_concentration": 10.0,
                "reference_integral": 1.0,
                "reference_protons": 1,
                "reference_concentration": 10.0,
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["method"] == "pulcon"
    assert body["purity_percent"] == pytest.approx(100.0, abs=1e-9)


def test_qnmr_purity_needs_no_dossier(client, api_headers):
    """The point of the change. The pre-existing qNMR surface required a regulatory dossier, which
    a SpectraCheck-only customer does not have; this one is stateless."""
    with client:
        res = client.post(
            "/spectrum/qnmr/purity", headers=api_headers, json=_internal_standard_body()
        )
        assert res.status_code == 200
        # Nothing was created to make that work.
        assert client.get("/regulatory/dossiers", headers=api_headers).json() == []
