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
        ["watchlist", "--help"],
        ["watchlist", "add", "--help"],
        ["watchlist", "bind", "--help"],
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
    assert "evaluation_mode=fixture_pipeline_acceptance" in result.output
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



def test_watchlist_add_and_bind_registry_source_id_offline(tmp_path):
    env = {"KOL_DB_PATH": str(tmp_path / "radar.db")}

    added = runner.invoke(
        app,
        [
            "watchlist",
            "add",
            "--name",
            "真实公众号",
            "--external-id",
            "MP_REAL",
            "--registry-source-id",
            "src_1234abcd",
        ],
        env=env,
    )
    assert added.exit_code == 0, added.output
    assert "registry=src_1234abcd" in added.output

    listed = runner.invoke(app, ["watchlist", "list"], env=env)
    assert listed.exit_code == 0, listed.output
    assert "registry=src_1234abcd" in listed.output

    rebound = runner.invoke(
        app,
        [
            "watchlist",
            "bind",
            "--source-id",
            "1",
            "--registry-source-id",
            "src_deadbeef",
        ],
        env=env,
    )
    assert rebound.exit_code == 0, rebound.output
    assert "registry=src_deadbeef" in rebound.output


def test_watchlist_rejects_invalid_registry_source_id(tmp_path):
    result = runner.invoke(
        app,
        [
            "watchlist",
            "add",
            "--name",
            "真实公众号",
            "--external-id",
            "MP_REAL",
            "--registry-source-id",
            "not-a-source-id",
        ],
        env={"KOL_DB_PATH": str(tmp_path / "radar.db")},
    )
    assert result.exit_code != 0
