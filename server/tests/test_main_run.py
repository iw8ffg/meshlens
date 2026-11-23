"""meshlens run con la porta gia' occupata: nessun secondo avvio."""
import pytest

from meshlens import __main__ as cli
from meshlens import tray


@pytest.fixture
def no_logs(monkeypatch, tmp_path):
    # niente configurazione globale dei log: resterebbe attiva per i test successivi
    from meshlens import logsetup
    monkeypatch.setattr(cli, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(logsetup, "setup_logging", lambda *_a, **_k: None)


def _no_build(*_a, **_k):
    raise AssertionError("build() non deve partire")


def test_run_opens_browser_when_meshlens_already_running(monkeypatch, tmp_path, no_logs, capsys):
    opened = []
    monkeypatch.setattr(tray, "single_instance", lambda port: "meshlens")
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    monkeypatch.setattr("meshlens.app.build", _no_build)
    assert cli.main(["run", "--data-dir", str(tmp_path), "--port", "8787"]) == 0
    assert opened == ["http://127.0.0.1:8787"]
    assert "già in esecuzione" in capsys.readouterr().out


def test_run_no_browser_flag_respected(monkeypatch, tmp_path, no_logs):
    opened = []
    monkeypatch.setattr(tray, "single_instance", lambda port: "meshlens")
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    assert cli.main(["run", "--data-dir", str(tmp_path), "--port", "8787", "--no-browser"]) == 0
    assert opened == []


def test_run_port_taken_by_other_program(monkeypatch, tmp_path, no_logs, capsys):
    monkeypatch.setattr(tray, "single_instance", lambda port: "other")
    monkeypatch.setattr("meshlens.app.build", _no_build)
    assert cli.main(["run", "--data-dir", str(tmp_path), "--port", "8787"]) == 1
    assert "occupata da un altro programma" in capsys.readouterr().out
