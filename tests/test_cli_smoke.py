import logging

import pytest
from typer.testing import CliRunner

from kol_radar.cli import app
from kol_radar.logging_config import SecretRedactingFilter


runner = CliRunner()


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["ingest-url", "--help"],
        ["sync", "--help"],
        ["query", "--help"],
        ["digest", "--help"],
        ["eval", "--help"],
    ],
)
def test_cli_help_commands_do_not_require_network(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output


def test_watchlist_list_works_offline(tmp_path):
    result = runner.invoke(
        app,
        ["watchlist", "list"],
        env={"KOL_DB_PATH": str(tmp_path / "radar.db")},
    )
    assert result.exit_code == 0, result.output
    assert "Watchlist is empty" in result.output


def test_fixture_eval_has_valid_evidence_and_no_hallucinations():
    result = runner.invoke(app, ["eval", "--fixture"])
    assert result.exit_code == 0, result.output
    assert "evidence_validity=1.0" in result.output
    assert "hallucination_count=0" in result.output


def test_secret_redacting_filter_removes_sensitive_values():
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "api_key=sk-secret token: bearer-secret cookie=session-secret safe=value",
        (),
        None,
    )

    SecretRedactingFilter().filter(record)
    rendered = record.getMessage()

    assert "sk-secret" not in rendered
    assert "bearer-secret" not in rendered
    assert "session-secret" not in rendered
    assert "safe=value" in rendered
