"""Rotte di WP5a: traceroute periodici, bot, webhook."""
import pytest
from fastapi import HTTPException

from meshlens import api_automation, api_maintenance
from meshlens.api import create_app
from test_api import make_ctx


def test_routes_answer_503_without_install():
    with pytest.raises(HTTPException) as e:
        api_automation._ext({}, "bot")
    assert e.value.status_code == 503
    assert e.value.detail == "Automazioni non disponibili"


def test_ext_helper_returns_service():
    class Ctx:
        ext = {"bot": object()}
    assert api_automation._ext(Ctx(), "bot") is Ctx.ext["bot"]


def test_guest_get_paths_empty():
    assert api_automation.GUEST_GET_PATHS == ()
    assert api_maintenance.GUEST_GET_PATHS == ()


def test_maintenance_registered(monkeypatch):
    calls = []
    monkeypatch.setattr(api_maintenance, "register", lambda *a: calls.append(a))
    create_app(make_ctx())
    assert len(calls) == 1
