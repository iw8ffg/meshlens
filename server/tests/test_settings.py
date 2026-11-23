import pytest

from meshlens.db import connect
from meshlens.settings import DEFAULTS, export_settings, load_settings, prepare_import, save_settings


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


def test_mqtt_channels_default_and_validation(conn):
    assert load_settings(conn)["mqtt_channels"] == []
    assert save_settings(conn, {"mqtt_channels": ["LongFast", "Custom"]})["mqtt_channels"] == [
        "LongFast", "Custom"]
    for bad in ("LongFast", [""], ["a" * 33], [1], [f"c{i}" for i in range(21)], None):
        with pytest.raises(ValueError):
            save_settings(conn, {"mqtt_channels": bad})
    save_settings(conn, {"mqtt_channels": ["x" * 32] * 1})


def test_topics_without_wildcard_get_hash():
    from meshlens.settings import normalize_topic
    assert normalize_topic("msh/EU_868/IT") == "msh/EU_868/IT/#"
    assert normalize_topic(" msh/EU_868/IT/ ") == "msh/EU_868/IT/#"
    assert normalize_topic("msh/EU_868/#") == "msh/EU_868/#"
    assert normalize_topic("msh/+/2/e/LongFast/#") == "msh/+/2/e/LongFast/#"
    assert normalize_topic("  ") == ""


def test_load_normalizes_saved_topics(tmp_path):
    import json
    from meshlens.db import connect
    from meshlens.settings import load_settings
    conn = connect(tmp_path / "t.db")
    conn.execute("INSERT INTO settings(key, value) VALUES('mqtt', ?)", (json.dumps({"topics": ["msh/EU_868/IT"]}),))
    assert load_settings(conn)["mqtt"]["topics"] == ["msh/EU_868/IT/#"]


def test_lan_https_setting_validation(conn):
    assert load_settings(conn)["lan_https"] is False
    assert save_settings(conn, {"lan_https": True})["lan_https"] is True
    for bad in (1, "true", None):
        with pytest.raises(ValueError):
            save_settings(conn, {"lan_https": bad})
    assert load_settings(conn)["lan_https"] is True


def test_notify_settings_validation(conn):
    import json
    from meshlens.settings import MASK, mask_secrets, prepare_import
    s = load_settings(conn)
    assert (s["notify_toast"], s["notify_telegram"], s["notify_mine_status"],
            s["notify_new_node"]) == (True, False, True, False)
    assert s["telegram_token"] == "" and s["telegram_chat_id"] == "" and s["notify_keywords"] == []
    for bad in ({"telegram_chat_id": "abc"}, {"telegram_chat_id": "1" * 21},
                {"telegram_chat_id": 42}, {"notify_keywords": [f"p{i:02d}" for i in range(21)]},
                {"notify_keywords": ["a"]}, {"notify_keywords": ["x" * 33]},
                {"notify_keywords": [" sp"]}, {"notify_keywords": "parola"},
                {"notify_toast": 1}, {"notify_new_node": None}, {"telegram_token": 5}, {"telegram_token": "123:ABCdef"}):
        with pytest.raises(ValueError):
            save_settings(conn, bad)
    out = save_settings(conn, {"telegram_chat_id": "-1001234", "telegram_token": "123456789:AAH_secret-token-abcdefghijklmnopqrstu",
                               "notify_keywords": ["aiuto", "perché"], "notify_telegram": True})
    assert out["telegram_chat_id"] == "-1001234" and out["notify_keywords"] == ["aiuto", "perché"]
    raw = conn.execute("SELECT value FROM settings WHERE key='telegram_token'").fetchone()["value"]
    assert "abcdefghij" not in json.loads(raw)  # salvato cifrato
    assert load_settings(conn)["telegram_token"] == "123456789:AAH_secret-token-abcdefghijklmnopqrstu"
    assert mask_secrets(load_settings(conn))["telegram_token"] == MASK
    changes, skipped = prepare_import({"format": 1, "settings": {"telegram_token": MASK,
                                                                 "notify_toast": False}})
    assert "telegram_token" not in changes and "telegram_token" in skipped
    assert changes["notify_toast"] is False


def test_packet_log_settings_validation(conn):
    assert DEFAULTS["packet_log_mode"] == "archived"
    assert DEFAULTS["retention_packets_hours"] == 48
    save_settings(conn, {"packet_log_mode": "all"})
    assert load_settings(conn)["packet_log_mode"] == "all"
    with pytest.raises(ValueError):
        save_settings(conn, {"packet_log_mode": "tutto"})
    for bad in (0, 169):
        with pytest.raises(ValueError):
            save_settings(conn, {"retention_packets_hours": bad})
    save_settings(conn, {"retention_packets_hours": 168})


def test_backup_retention_days_setting(conn):
    assert DEFAULTS["backup_retention_days"] == 0
    for bad in (-1, 3651, "7", True, 1.5):
        with pytest.raises(ValueError):
            save_settings(conn, {"backup_retention_days": bad})
    save_settings(conn, {"backup_retention_days": 3650})
    assert load_settings(conn)["backup_retention_days"] == 3650
    save_settings(conn, {"backup_retention_days": 0})
    assert export_settings(load_settings(conn), False)["settings"]["backup_retention_days"] == 0
    changes, _ = prepare_import({"format": 1, "settings": {"backup_retention_days": 14}})
    from meshlens.settings import AUTOMATIC_SWITCHES
    assert changes == {"backup_retention_days": 14, **{k: False for k in AUTOMATIC_SWITCHES}}


# ---- 1.6 ----

NEW_DEFAULTS = [
    ("onboarding_done", False), ("quick_replies", []), ("favorites_to_radio", False),
    ("traceroute_auto_enabled", False), ("traceroute_auto_max_per_hour", 6),
    ("bot_enabled", False), ("bot_targets", []), ("bot_commands", ["ping", "info", "time"]),
    ("bot_weather_node", ""), ("bot_replies", []), ("bot_min_interval_s", 30),
    ("bot_max_per_hour", 20), ("bot_node_cooldown_s", 300), ("webhook_enabled", False),
    ("webhook_url", ""), ("webhook_events", ["alert"]), ("update_channel", "stable"),
    ("last_seen_version", ""), ("guest_enabled", False), ("retention_traceroutes_days", 365),
    ("retention_broker_days", {}),
]


def _rejects(conn, key, value):
    with pytest.raises(ValueError):
        save_settings(conn, {key: value})


@pytest.mark.parametrize("key,default", NEW_DEFAULTS)
def test_new_defaults_present(conn, key, default):
    assert load_settings(conn)[key] == default


def test_quick_replies_validation(conn):
    assert save_settings(conn, {"quick_replies": ["Arrivo {ora}", "Tutto ok"]})[
        "quick_replies"] == ["Arrivo {ora}", "Tutto ok"]
    for bad in ([f"r{i}" for i in range(21)], [""], [" x"], ["è" * 101], ["a\nb"],
                ["ok", "ok"], "ok", [3]):
        _rejects(conn, "quick_replies", bad)


def test_bot_targets_validation(conn):
    good = [{"kind": "radio", "radio_id": "r1", "channel_index": 0},
            {"kind": "mqtt", "broker": "default", "channel": "LongFast"}]
    assert save_settings(conn, {"bot_targets": good})["bot_targets"] == good
    radio = {"kind": "radio", "radio_id": "r1", "channel_index": 0}
    mqtt = {"kind": "mqtt", "broker": "default", "channel": "LongFast"}
    for bad in ([{**radio, "channel_index": 8}], [{**radio, "kind": "x"}],
                [{**radio, "extra": 1}], [{**mqtt, "broker": "Bad!"}],
                [{**mqtt, "channel": "a/b"}], [{**mqtt, "channel": "x" * 12}],
                [radio, dict(radio)],
                [{**radio, "radio_id": f"r{i}"} for i in range(17)]):
        _rejects(conn, "bot_targets", bad)


def test_bot_commands_and_replies_validation(conn):
    assert save_settings(conn, {"bot_commands": ["ping", "weather"]})["bot_commands"] == [
        "ping", "weather"]
    _rejects(conn, "bot_commands", ["ping", "ping"])
    _rejects(conn, "bot_commands", ["shell"])
    ok = [{"trigger": "Aiuto", "text": "Scrivi ping"}]
    assert save_settings(conn, {"bot_replies": ok})["bot_replies"] == ok
    _rejects(conn, "bot_replies", [{"trigger": "Aiuto", "text": "a"},
                                   {"trigger": "aiuto", "text": "b"}])
    _rejects(conn, "bot_replies", [{"trigger": "A", "text": "a"}])
    _rejects(conn, "bot_replies", [{"trigger": "Aiuto", "text": ""}])
    _rejects(conn, "bot_weather_node", "abc")
    assert save_settings(conn, {"bot_weather_node": "!0000000a"})["bot_weather_node"] == "!0000000a"


def test_webhook_url_validation(conn):
    from meshlens.settings import MASK
    for good in ("", MASK, "https://example.org/hook?t=abc", "http://127.0.0.1:8080/x",
                 "http://localhost/x"):
        save_settings(conn, {"webhook_url": good})
    for bad in ("http://example.org/x", "ftp://x", "https://", "https://e.org/#f",
                "https://e.org/" + "a" * 2035, 5):
        _rejects(conn, "webhook_url", bad)


def test_webhook_url_is_secret(conn):
    from meshlens.settings import MASK, mask_secrets
    save_settings(conn, {"webhook_url": "https://e.org/h?token=s3cr3t"})
    raw = conn.execute("SELECT value FROM settings WHERE key='webhook_url'").fetchone()[0]
    assert "s3cr3t" not in raw
    s = load_settings(conn)
    assert s["webhook_url"] == "https://e.org/h?token=s3cr3t"
    assert mask_secrets(s)["webhook_url"] == MASK
    assert "s3cr3t" not in str(export_settings(s, include_secrets=False))


def test_ranges_and_enums(conn):
    _rejects(conn, "traceroute_auto_max_per_hour", 0)
    _rejects(conn, "traceroute_auto_max_per_hour", 31)
    save_settings(conn, {"traceroute_auto_max_per_hour": 30})
    _rejects(conn, "bot_min_interval_s", 14)
    _rejects(conn, "update_channel", "nightly")
    save_settings(conn, {"update_channel": "beta"})
    for good in ("1.6.0", "1.6.0-beta.1"):
        save_settings(conn, {"last_seen_version": good})
    _rejects(conn, "last_seen_version", "v1")
    _rejects(conn, "retention_traceroutes_days", 0)
    _rejects(conn, "webhook_events", ["alert", "alert"])
    _rejects(conn, "webhook_events", ["boom"])
    _rejects(conn, "bot_enabled", 1)


def test_retention_broker_days_validation(conn):
    assert save_settings(conn, {"retention_broker_days": {"default": 7}})[
        "retention_broker_days"] == {"default": 7}
    for bad in ({"Bad!": 7}, {"default": 0}, {"default": "7"},
                {f"b{i}": 7 for i in range(9)}, []):
        _rejects(conn, "retention_broker_days", bad)


def test_import_skips_local_only_keys():
    changes, skipped = prepare_import({"format": 1, "settings": {
        "bot_enabled": True, "webhook_enabled": True, "guest_enabled": True,
        "onboarding_done": True, "last_seen_version": "1.6.0", "quick_replies": ["ok"]}})
    # gli interruttori degli invii automatici e dell'ospite si spengono sempre all'importazione
    assert changes == {"quick_replies": ["ok"], "bot_enabled": False, "webhook_enabled": False,
                       "guest_enabled": False, "traceroute_auto_enabled": False}
    assert set(skipped) == {"bot_enabled", "webhook_enabled", "guest_enabled", "onboarding_done",
                            "last_seen_version"}


def test_import_skips_only_local_keys_present():
    changes, skipped = prepare_import({"format": 1, "settings": {"quick_replies": ["ok"]}})
    assert skipped == []


def test_export_has_no_local_only_keys(conn):
    from meshlens.settings import LOCAL_ONLY_KEYS
    doc = export_settings(load_settings(conn), include_secrets=True)
    assert not set(LOCAL_ONLY_KEYS) & set(doc["settings"])
    assert "traceroute_auto_enabled" in LOCAL_ONLY_KEYS
