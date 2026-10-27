import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

import pytest

from packages.shared.incident_validation import parse_csv_rows
from scripts import analyze, check_memory_bank, seed_incidents
from services.api import email, seed

FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "incidents-trackflow.csv"


def test_email_secrets_not_logged_by_default(monkeypatch, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "")
    monkeypatch.delenv("ALLOW_PASSWORD_RESET_CONSOLE_FALLBACK", raising=False)
    with pytest.raises(email.EmailDeliveryError):
        email.send_password_reset_email("private@example.test", "https://example.test/?token=PRIVATE_TOKEN")
    output = capsys.readouterr()
    assert "PRIVATE_TOKEN" not in output.out + output.err
    assert "private@example.test" not in output.out + output.err


def test_console_delivery_requires_explicit_opt_in(monkeypatch, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "")
    monkeypatch.setenv("ALLOW_PASSWORD_RESET_CONSOLE_FALLBACK", "true")
    email.send_password_reset_email("audit@example.test", "https://example.test/?token=DEVELOPMENT_ONLY")
    assert "DEVELOPMENT_ONLY" in capsys.readouterr().err


def test_provider_failure_has_no_automatic_token_output(monkeypatch, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "synthetic-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "audit@example.test")
    monkeypatch.delenv("ALLOW_PASSWORD_RESET_CONSOLE_FALLBACK", raising=False)
    with patch.object(email, "urlopen", side_effect=URLError("PRIVATE_PROVIDER_DATA")):
        with pytest.raises(email.EmailDeliveryError, match="Could not deliver"):
            email.send_password_reset_email("audit@example.test", "https://example.test/?token=PRIVATE_TOKEN")
    assert "PRIVATE_TOKEN" not in capsys.readouterr().err


@pytest.mark.parametrize("text", ["", "wrong,headers\nx,y\n", "date,date\nx,y\n"])
def test_csv_rejects_bad_headers(text):
    with pytest.raises(ValueError):
        parse_csv_rows(text)


def test_analyzer_missing_file_exits_with_stderr(capsys):
    assert analyze.main(["analyze.py", "a-file-that-does-not-exist.csv"]) == 1
    assert "Check" in capsys.readouterr().err


def test_analyzer_export_failure_is_actionable(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    with patch.object(analyze, "export_results_csv", side_effect=PermissionError("PRIVATE_PATH")):
        assert analyze.main(["analyze.py", str(FIXTURE)]) == 1
    output = capsys.readouterr()
    assert "permissions" in output.err
    assert "PRIVATE_PATH" not in output.err


def test_analyzer_eof_skips_optional_export(capsys):
    with patch("builtins.input", side_effect=EOFError):
        assert analyze.main(["analyze.py", str(FIXTURE)]) == 0
    assert "export skipped" in capsys.readouterr().err


def test_seed_storage_error_is_sanitized():
    with patch.object(seed_incidents, "create_incident", side_effect=sqlite3.OperationalError("PRIVATE_PATH")):
        with pytest.raises(seed_incidents.SeedStorageError, match="Check database access") as error:
            seed_incidents.seed_incidents(FIXTURE)
    assert "PRIVATE_PATH" not in str(error.value)


def test_seed_invalid_encoding_is_actionable(tmp_path):
    source = tmp_path / "invalid.csv"
    source.write_bytes(b"\xff\xfe\xff")
    with pytest.raises(seed_incidents.SeedInputError, match="UTF-8"):
        seed_incidents.seed_incidents(source)


def test_supplier_seed_returns_nonzero(capsys):
    with patch.object(seed, "seed_suppliers", side_effect=OSError("PRIVATE_PATH")):
        assert seed.main() == 1
    assert "PRIVATE_PATH" not in capsys.readouterr().err


def test_memory_guard_fails_closed(capsys):
    with patch.object(check_memory_bank.subprocess, "run", return_value=SimpleNamespace(returncode=128, stdout="", stderr="PRIVATE_GIT_DATA")):
        assert check_memory_bank.main() == 1
    assert "PRIVATE_GIT_DATA" not in capsys.readouterr().err