from nmrcheck.chemistry import structure_summary_from_smiles


def test_structure_summary_counts_aromatic_and_aliphatic_protons() -> None:
    toluene = structure_summary_from_smiles("Cc1ccccc1")
    ethanol = structure_summary_from_smiles("CCO")

    assert toluene.aromatic_protons == 5
    assert toluene.aliphatic_protons == 3
    assert ethanol.aromatic_protons == 0
    assert ethanol.aliphatic_protons == 5
