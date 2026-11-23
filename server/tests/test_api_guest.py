"""E19: accesso ospite. Allowlist, filtro degli eventi, matrice su tutte le rotte, WebSocket,
rotte dedicate."""
from meshlens import guest


# ---- parte pura ----

def test_guest_paths_union_of_core_and_modules():
    from meshlens import api_data, api_monitor, api_topology
    paths = guest.guest_get_paths()
    assert set(guest.CORE_GUEST_GET_PATHS) <= paths
    assert set(api_data.GUEST_GET_PATHS) <= paths
    assert set(api_monitor.GUEST_GET_PATHS) <= paths
    assert set(api_topology.GUEST_GET_PATHS) <= paths
    # mai messaggi, radio, impostazioni, registro pacchetti
    for bad in ("/api/messages", "/api/messages/history", "/api/conversations", "/api/radios",
                "/api/settings", "/api/packets", "/api/waypoints", "/api/status",
                "/api/version", "/api/messages/search", "/api/search"):
        assert bad not in paths


def test_guest_alerts_drop_rules():
    alerts = [
        {"key": "a", "kind": "battery_low", "node_id": "!00000001", "value": 10},
        {"key": "b", "kind": "rule_keyword", "node_id": "!00000002", "rule_id": 3,
         "detail": {"word": "sos", "text": "aiuto sos"}},
        {"key": "c", "kind": "rule_snr", "node_id": "!00000002", "rule_id": 4},
        {"key": "d", "kind": "sensor_detection", "node_id": "!00000003", "rule_id": None},
    ]
    out = guest.guest_alerts(alerts)
    assert [a["key"] for a in out] == ["a", "d"]
    assert all("rule_id" not in a for a in out)
    assert alerts[3]["rule_id"] is None  # l'originale non cambia


def test_guest_mqtt_status_is_reduced():
    st = {"connected": True, "msgs_per_s": 2.5, "connected_since": 10.0, "last_msg_age_s": 3,
          "last_error": "host.example: rifiutato", "brokers": [{"host": "h.example"}],
          "decoded": 5, "undecodable": 1}
    out = guest.guest_mqtt_status(st)
    assert out == {"connected": True, "msgs_per_s": 2.5, "connected_since": 10.0,
                   "last_msg_age_s": 3, "undecodable": 0}
    assert guest.guest_mqtt_status(None) is None


def test_guest_event_filter():
    ok = [{"type": "nodes", "nodes": []}, {"type": "resync"},
          {"type": "sensor_event", "event": {}}, {"type": "tak_contact", "contact": {}},
          {"type": "traceroute", "result": {"forward": []}}]
    for m in ok:
        assert guest.guest_event(m) == m
    denied = ["message", "message_status", "conv_read", "radios", "config_job", "bot",
              "alert_rules", "trace_targets", "waypoint", "waypoint_deleted", "coverage",
              "update_job", "map_job", "prediction_job", "sf_job", "sf_routers", "x", None]
    for t in denied:
        assert guest.guest_event({"type": t, "message": {"text": "segreto"}}) is None
    st = guest.guest_event({"type": "status", "mqtt": {"connected": False, "msgs_per_s": 0,
                                                      "brokers": [{"host": "h"}]}})
    assert st == {"type": "status", "mqtt": {"connected": False, "msgs_per_s": 0,
                                             "connected_since": None, "last_msg_age_s": None,
                                             "undecodable": 0}}
    al = guest.guest_event({"type": "alerts", "alerts": [
        {"key": "a", "kind": "silent"}, {"key": "b", "kind": "rule_keyword", "detail": {}}]})
    assert al == {"type": "alerts", "alerts": [{"key": "a", "kind": "silent"}]}
