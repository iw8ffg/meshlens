import csv
import math
import os
import time as _time
from pathlib import Path

import pytest

from meshlens.itm import ItmError, ItmResult, itm_p2p_loss

DATA = Path(__file__).parent / "data"


def _profiles() -> list[list[float]]:
    with open(DATA / "itm_pfls.csv", newline="") as fh:
        return [[float(v) for v in line.strip().split(",") if v.strip()]
                for line in fh if line.strip()]


def _vectors() -> list[dict[str, str]]:
    with open(DATA / "itm_p2p.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def _flat(n_points: int = 101, step_m: float = 20.0, z: float = 100.0) -> list[float]:
    return [n_points - 1, step_m] + [z] * n_points


def test_ntia_vectors():
    vectors = _vectors()
    profiles = _profiles()
    assert len(vectors) == 5 and len(profiles) == 5
    for row, pfl in zip(vectors, profiles):
        res = itm_p2p_loss(
            float(row["h_tx__meter"]), float(row["h_rx__meter"]), pfl,
            climate=int(row["climate"]), n0=float(row["N_0"]), f_mhz=float(row["f__mhz"]),
            pol=int(row["pol"]), epsilon=float(row["epsilon"]), sigma=float(row["sigma"]),
            mdvar=int(row["mdvar"]), time=float(row["time"]),
            location=float(row["location"]), situation=float(row["situation"]))
        assert isinstance(res, ItmResult)
        assert res.mode in (1, 2, 3)
        assert abs(res.loss_db - float(row["A__db"])) <= 0.05, (row, res)


def test_los_flat_close_to_free_space():
    res = itm_p2p_loss(30.0, 30.0, _flat())
    assert res.mode == 1
    fspl = 32.45 + 20 * math.log10(2) + 20 * math.log10(869.525)
    assert abs(res.loss_db - fspl) <= 6


def test_obstacle_increases_loss():
    flat = itm_p2p_loss(30.0, 30.0, _flat())
    # rilievo di 150 m a meta' percorso: collina triangolare larga 400 m alla base
    # (un picco di un solo campione resta fuori dall'intervallo interdecile di delta_h
    # e, sul percorso in visibilita', aggiunge solo ~7 dB: comportamento dell'ITM)
    pfl = _flat()
    for i in range(101):
        pfl[2 + i] += max(0.0, 150.0 * (1 - abs(i - 50) / 10))
    hill = itm_p2p_loss(30.0, 30.0, pfl)
    assert hill.loss_db >= flat.loss_db + 10


def test_invalid_inputs():
    with pytest.raises(ItmError) as exc:
        itm_p2p_loss(0.1, 30.0, _flat())
    assert exc.value.code == 1000
    with pytest.raises(ItmError) as exc:
        itm_p2p_loss(30.0, 30.0, _flat(), f_mhz=10)
    assert exc.value.code == 1009


def test_speed():
    if os.environ.get("CI_SLOW"):
        pytest.skip("misura dei tempi disattivata (CI_SLOW)")
    pfl = [199, 30.0] + [100.0 + 40.0 * math.sin(i / 9.0) for i in range(200)]
    n = 500
    t0 = _time.perf_counter()
    for _ in range(n):
        itm_p2p_loss(10.0, 1.5, pfl)
    avg_ms = (_time.perf_counter() - t0) * 1000 / n
    assert avg_ms < 3.0, f"{avg_ms:.2f} ms per chiamata"
