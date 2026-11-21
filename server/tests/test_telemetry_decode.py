import pytest
from meshtastic.protobuf import telemetry_pb2 as t

from meshlens.telemetry_decode import (
    EmptyTelemetry, UnsupportedTelemetry, parse_telemetry, parse_telemetry_msg,
    telemetry_from_dict,
)


def test_environment_metrics():
    msg = t.Telemetry(environment_metrics=t.EnvironmentMetrics(
        temperature=21.5, relative_humidity=40, barometric_pressure=1013.2))
    d = parse_telemetry(msg.SerializeToString())
    assert d.variant == "environment"
    assert d.metrics == {"temperature": 21.5, "relative_humidity": 40.0,
                         "barometric_pressure": pytest.approx(1013.2)}


def test_local_stats_counts():
    d = parse_telemetry_msg(t.Telemetry(local_stats=t.LocalStats(
        num_packets_rx=100, num_rx_dupe=12, noise_floor=-110)))
    assert d.variant == "local_stats"
    assert d.metrics["num_rx_dupe"] == 12.0 and d.metrics["noise_floor"] == -110.0


def test_air_quality_and_power_and_health():
    aq = parse_telemetry_msg(t.Telemetry(air_quality_metrics=t.AirQualityMetrics(pm25_standard=7)))
    pw = parse_telemetry_msg(t.Telemetry(power_metrics=t.PowerMetrics(ch1_voltage=3.3)))
    hl = parse_telemetry_msg(t.Telemetry(health_metrics=t.HealthMetrics(heart_bpm=60)))
    assert (aq.variant, pw.variant, hl.variant) == ("air_quality", "power", "health")
    assert aq.metrics == {"pm25_standard": 7.0}


def test_nan_dropped_and_empty_raises():
    msg = t.Telemetry(environment_metrics=t.EnvironmentMetrics(temperature=float("nan")))
    with pytest.raises(EmptyTelemetry):
        parse_telemetry_msg(msg)
    msg = t.Telemetry(environment_metrics=t.EnvironmentMetrics(
        temperature=float("inf"), relative_humidity=50))
    assert parse_telemetry_msg(msg).metrics == {"relative_humidity": 50.0}


def test_unsupported_variants():
    with pytest.raises(UnsupportedTelemetry):
        parse_telemetry_msg(t.Telemetry(host_metrics=t.HostMetrics(uptime_seconds=5)))
    with pytest.raises(UnsupportedTelemetry):
        parse_telemetry_msg(t.Telemetry())


def test_device_unchanged():
    d = parse_telemetry_msg(t.Telemetry(
        device_metrics=t.DeviceMetrics(battery_level=87, voltage=4.01)))
    assert d.battery_level == 87 and d.variant == "device" and d.metrics == {}


def test_from_dict_camelcase():
    d = telemetry_from_dict({"environmentMetrics": {"temperature": 20.0,
                                                    "relativeHumidity": 55.0}})
    assert d.metrics == {"temperature": 20.0, "relative_humidity": 55.0}
