import nmrcheck.cli as cli


def test_cli_exposes_main_and_dev_db_reset() -> None:
    assert callable(cli.main)
    assert callable(cli.reset_dev_db)
