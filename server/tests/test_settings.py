import pytest

from meshlens.db import connect
from meshlens.settings import DEFAULTS, load_settings, save_settings


@pytest.fixture
def conn():
    return connect(":memory:")


def test_defaults_on_empty_db(conn):
    assert load_settings(conn) == DEFAULTS


def test_save_and_reload(conn):
    out = save_settings(conn, {"saved_countries": ["IT", "SE"], "lan_access": True})
    assert out["saved_countries"] == ["IT", "SE"]
    assert load_settings(conn)["lan_access"] is True


def test_lowercase_country_rejected(conn):
    with pytest.raises(ValueError):
        save_settings(conn, {"saved_countries": ["it"]})


def test_invalid_extra_key_rejected(conn):
    with pytest.raises(ValueError):
        save_settings(conn, {"mqtt": {"extra_keys": ["abc"]}})


def test_partial_mqtt_keeps_other_keys(conn):
    out = save_settings(conn, {"mqtt": {"host": "broker.local"}})
    assert out["mqtt"]["host"] == "broker.local"
    assert out["mqtt"]["port"] == 1883
    assert out["mqtt"]["topics"] == ["msh/EU_868/#"]
    assert load_settings(conn)["mqtt"]["username"] == "meshdev"


def test_valid_extra_key_and_type_errors(conn):
    assert save_settings(conn, {"mqtt": {"extra_keys": ["AQ=="]}})["mqtt"]["extra_keys"] == ["AQ=="]
    with pytest.raises(ValueError):
        save_settings(conn, {"retention_messages_days": "90"})
    with pytest.raises(ValueError):
        save_settings(conn, {"mqtt": {"port": 70000}})
    with pytest.raises(ValueError):
        save_settings(conn, {"nope": 1})


def test_invalid_save_changes_nothing(conn):
    with pytest.raises(ValueError):
        save_settings(conn, {"lan_access": True, "saved_countries": ["x"]})
    assert load_settings(conn)["lan_access"] is False


def test_alert_settings_defaults_and_validation(conn):
    s = load_settings(conn)
    assert s["battery_alert_pct"] == 20 and s["silent_alert_hours"] == 6
    assert save_settings(conn, {"battery_alert_pct": 30})["battery_alert_pct"] == 30
    for bad in ({"battery_alert_pct": 0}, {"battery_alert_pct": 100},
                {"silent_alert_hours": 200}, {"silent_alert_hours": 0},
                {"battery_alert_pct": "20"}):
        with pytest.raises(ValueError):
            save_settings(conn, bad)
