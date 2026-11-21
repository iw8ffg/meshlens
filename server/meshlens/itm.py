"""Irregular Terrain Model (Longley-Rice), modo punto-punto con variabilita' TLS.

Derivato da NTIA ITM (github.com/NTIA/itm, commit `183ad95bd813a8be11009df396e1c631356864b2`).
Modificato da MeshLens il 2026-11-21: porting in Python del solo modo punto-punto TLS.

Il software originale e' stato sviluppato da dipendenti della NTIA (National
Telecommunications and Information Administration, Governo federale USA) e non e'
soggetto a copyright negli Stati Uniti (17 U.S.C. 105); fuori dagli USA la NTIA
concede il diritto di creare e distribuire opere derivate. Il porting segue i file
sorgente C++ funzione per funzione, con gli stessi nomi in snake_case. Le chiamate
sono scalari: si usano solo `math` e `cmath` (numpy qui rallenterebbe).

`pfl` e' nel formato NTIA: `[n_punti - 1, passo_m, z0, z1, ...]`.
"""
from __future__ import annotations

import cmath
import math
from collections.abc import Sequence
from dataclasses import dataclass

# --- Costanti (itm.h, Enums.h) ---
A_0__METER = 6370e3
A_9000__METER = 9000e3
THIRD = 1.0 / 3.0
SQRT2 = math.sqrt(2.0)

MODE__P2P = 0

POLARIZATION__HORIZONTAL = 0
POLARIZATION__VERTICAL = 1

MODE__NOT_SET = 0
MODE__LINE_OF_SIGHT = 1
MODE__DIFFRACTION = 2
MODE__TROPOSCATTER = 3

SINGLE_MESSAGE_MODE = 0
ACCIDENTAL_MODE = 1
MOBILE_MODE = 2
BROADCAST_MODE = 3

# --- Codici d'errore (Errors.h) ---
ERROR__TX_TERMINAL_HEIGHT = 1000
ERROR__RX_TERMINAL_HEIGHT = 1001
ERROR__INVALID_RADIO_CLIMATE = 1002
ERROR__INVALID_TIME = 1003
ERROR__INVALID_LOCATION = 1004
ERROR__INVALID_SITUATION = 1005
ERROR__REFRACTIVITY = 1008
ERROR__FREQUENCY = 1009
ERROR__POLARIZATION = 1010
ERROR__EPSILON = 1011
ERROR__SIGMA = 1012
ERROR__GROUND_IMPEDANCE = 1013
ERROR__MDVAR = 1014
ERROR__EFFECTIVE_EARTH = 1016
ERROR__SURFACE_REFRACTIVITY_SMALL = 1021
ERROR__SURFACE_REFRACTIVITY_LARGE = 1022

# --- Avvisi (Warnings.h) ---
WARN__TX_TERMINAL_HEIGHT = 0x0001
WARN__RX_TERMINAL_HEIGHT = 0x0002
WARN__FREQUENCY = 0x0004
WARN__PATH_DISTANCE_TOO_BIG_1 = 0x0008
WARN__PATH_DISTANCE_TOO_BIG_2 = 0x0010
WARN__PATH_DISTANCE_TOO_SMALL_1 = 0x0020
WARN__PATH_DISTANCE_TOO_SMALL_2 = 0x0040
WARN__TX_HORIZON_ANGLE = 0x0080
WARN__RX_HORIZON_ANGLE = 0x0100
WARN__TX_HORIZON_DISTANCE_1 = 0x0200
WARN__RX_HORIZON_DISTANCE_1 = 0x0400
WARN__TX_HORIZON_DISTANCE_2 = 0x0800
WARN__RX_HORIZON_DISTANCE_2 = 0x1000
WARN__EXTREME_VARIABILITIES = 0x2000
WARN__SURFACE_REFRACTIVITY = 0x4000


@dataclass
class ItmResult:
    loss_db: float
    warnings: int
    mode: int  # 1 visibilita', 2 diffrazione, 3 troposcatter


class ItmError(Exception):
    def __init__(self, code: int):
        super().__init__(f"ITM: errore {code}")
        self.code = code


def _fdim(x: float, y: float) -> float:
    return x - y if x > y else 0.0


# --- itm_p2p.cpp ---

def itm_p2p_loss(h_tx_m: float, h_rx_m: float, pfl: Sequence[float], climate: int = 5,
                 n0: float = 301.0, f_mhz: float = 869.525, pol: int = 1,
                 epsilon: float = 15.0, sigma: float = 0.005, mdvar: int = 12,
                 time: float = 50.0, location: float = 50.0,
                 situation: float = 50.0) -> ItmResult:
    """ITM_P2P_TLS: perdita di trasmissione di base in dB. Solleva `ItmError`."""
    warnings = validate_inputs(h_tx_m, h_rx_m, climate, time, location, situation,
                               n0, f_mhz, pol, epsilon, sigma, mdvar)

    np_ = int(pfl[0])
    p10 = int(0.1 * np_)
    h_sys__meter = 0.0
    for i in range(p10, np_ - p10 + 1):
        h_sys__meter += pfl[i + 2]
    h_sys__meter = h_sys__meter / (np_ - 2 * p10 + 1)

    z_g, gamma_e, n_s = initialize_point_to_point(f_mhz, h_sys__meter, n0, pol, epsilon, sigma)

    h__meter = (h_tx_m, h_rx_m)
    theta_hzn, d_hzn__meter, h_e__meter, delta_h__meter, d__meter = quick_pfl(pfl, gamma_e, h__meter)

    a_ref__db, warnings, propmode = longley_rice(
        theta_hzn, f_mhz, z_g, d_hzn__meter, h_e__meter, gamma_e, n_s, delta_h__meter,
        h__meter, d__meter, MODE__P2P, warnings)

    a_fs__db = free_space_loss(d__meter, f_mhz)
    var_db, warnings = variability(time, location, situation, h_e__meter, delta_h__meter,
                                   f_mhz, d__meter, a_ref__db, climate, mdvar, warnings)
    return ItmResult(loss_db=var_db + a_fs__db, warnings=warnings, mode=propmode)


# --- ValidateInputs.cpp ---

def validate_inputs(h_tx__meter: float, h_rx__meter: float, climate: int, time: float,
                    location: float, situation: float, n_0: float, f__mhz: float, pol: int,
                    epsilon: float, sigma: float, mdvar: int) -> int:
    warnings = 0
    if h_tx__meter < 1.0 or h_tx__meter > 1000.0:
        warnings |= WARN__TX_TERMINAL_HEIGHT
    if h_tx__meter < 0.5 or h_tx__meter > 3000.0:
        raise ItmError(ERROR__TX_TERMINAL_HEIGHT)
    if h_rx__meter < 1.0 or h_rx__meter > 1000.0:
        warnings |= WARN__RX_TERMINAL_HEIGHT
    if h_rx__meter < 0.5 or h_rx__meter > 3000.0:
        raise ItmError(ERROR__RX_TERMINAL_HEIGHT)
    if climate not in (1, 2, 3, 4, 5, 6, 7):
        raise ItmError(ERROR__INVALID_RADIO_CLIMATE)
    if n_0 < 250 or n_0 > 400:
        raise ItmError(ERROR__REFRACTIVITY)
    if f__mhz < 40.0 or f__mhz > 10000.0:
        warnings |= WARN__FREQUENCY
    if f__mhz < 20 or f__mhz > 20000:
        raise ItmError(ERROR__FREQUENCY)
    if pol not in (POLARIZATION__HORIZONTAL, POLARIZATION__VERTICAL):
        raise ItmError(ERROR__POLARIZATION)
    if epsilon < 1:
        raise ItmError(ERROR__EPSILON)
    if sigma <= 0:
        raise ItmError(ERROR__SIGMA)
    if (mdvar < 0 or 3 < mdvar < 10 or 13 < mdvar < 20 or 23 < mdvar < 30 or mdvar > 33):
        raise ItmError(ERROR__MDVAR)
    if situation <= 0 or situation >= 100:
        raise ItmError(ERROR__INVALID_SITUATION)
    if time <= 0 or time >= 100:
        raise ItmError(ERROR__INVALID_TIME)
    if location <= 0 or location >= 100:
        raise ItmError(ERROR__INVALID_LOCATION)
    return warnings


# --- InitializePointToPoint.cpp ---

def initialize_point_to_point(f__mhz: float, h_sys__meter: float, n_0: float, pol: int,
                              epsilon: float, sigma: float) -> tuple[complex, float, float]:
    """Restituisce (Z_g, gamma_e, N_s)."""
    gamma_a = 157e-9
    if h_sys__meter == 0.0:
        n_s = n_0
    else:
        n_s = n_0 * math.exp(-h_sys__meter / 9460.0)
    gamma_e = gamma_a * (1.0 - 0.04665 * math.exp(n_s / 179.3))
    ep_r = complex(epsilon, 18000 * sigma / f__mhz)
    z_g = cmath.sqrt(ep_r - 1.0)
    if pol == POLARIZATION__VERTICAL:
        z_g = z_g / ep_r
    return z_g, gamma_e, n_s


# --- QuickPfl.cpp ---

def quick_pfl(pfl: Sequence[float], gamma_e: float, h__meter: Sequence[float]):
    """Restituisce (theta_hzn, d_hzn__meter, h_e__meter, delta_h__meter, d__meter)."""
    d__meter = pfl[0] * pfl[1]
    np_ = int(pfl[0])
    a_e__meter = 1 / gamma_e

    theta_hzn, d_hzn__meter = find_horizons(pfl, a_e__meter, h__meter)

    d_start__meter = min(15.0 * h__meter[0], 0.1 * d_hzn__meter[0])
    d_end__meter = d__meter - min(15.0 * h__meter[1], 0.1 * d_hzn__meter[1])

    delta_h__meter = compute_delta_h(pfl, d_start__meter, d_end__meter)

    h_e__meter = [0.0, 0.0]
    if d_hzn__meter[0] + d_hzn__meter[1] > 1.5 * d__meter:
        fit_tx, fit_rx = linear_least_squares_fit(pfl, d_start__meter, d_end__meter)
        h_e__meter[0] = h__meter[0] + _fdim(pfl[2], fit_tx)
        h_e__meter[1] = h__meter[1] + _fdim(pfl[np_ + 2], fit_rx)

        for i in range(2):
            d_hzn__meter[i] = (math.sqrt(2.0 * h_e__meter[i] * a_e__meter)
                               * math.exp(-0.07 * math.sqrt(delta_h__meter / max(h_e__meter[i], 5.0))))

        combined_horizons__meter = d_hzn__meter[0] + d_hzn__meter[1]
        if combined_horizons__meter <= d__meter:
            q = (d__meter / combined_horizons__meter) ** 2
            for i in range(2):
                h_e__meter[i] = h_e__meter[i] * q
                d_hzn__meter[i] = (math.sqrt(2.0 * h_e__meter[i] * a_e__meter)
                                   * math.exp(-0.07 * math.sqrt(delta_h__meter / max(h_e__meter[i], 5.0))))

        for i in range(2):
            q = math.sqrt(2.0 * h_e__meter[i] * a_e__meter)
            theta_hzn[i] = (0.65 * delta_h__meter * (q / d_hzn__meter[i] - 1.0) - 2.0 * h_e__meter[i]) / q
    else:
        fit_tx, _ = linear_least_squares_fit(pfl, d_start__meter, 0.9 * d_hzn__meter[0])
        h_e__meter[0] = h__meter[0] + _fdim(pfl[2], fit_tx)
        _, fit_rx = linear_least_squares_fit(pfl, d__meter - 0.9 * d_hzn__meter[1], d_end__meter)
        h_e__meter[1] = h__meter[1] + _fdim(pfl[np_ + 2], fit_rx)

    return theta_hzn, d_hzn__meter, h_e__meter, delta_h__meter, d__meter


# --- FindHorizons.cpp ---

def find_horizons(pfl: Sequence[float], a_e__meter: float, h__meter: Sequence[float]):
    """Restituisce (theta_hzn, d_hzn__meter), liste di 2 elementi."""
    np_ = int(pfl[0])
    xi = pfl[1]
    d__meter = pfl[0] * pfl[1]
    z_tx__meter = pfl[2] + h__meter[0]
    z_rx__meter = pfl[np_ + 2] + h__meter[1]
    two_a = 2 * a_e__meter

    theta_hzn = [(z_rx__meter - z_tx__meter) / d__meter - d__meter / two_a,
                 -(z_rx__meter - z_tx__meter) / d__meter - d__meter / two_a]
    d_hzn__meter = [d__meter, d__meter]

    d_tx__meter = 0.0
    d_rx__meter = d__meter
    for i in range(1, np_):
        d_tx__meter = d_tx__meter + xi
        d_rx__meter = d_rx__meter - xi
        z = pfl[i + 2]
        theta_tx = (z - z_tx__meter) / d_tx__meter - d_tx__meter / two_a
        theta_rx = -(z_rx__meter - z) / d_rx__meter - d_rx__meter / two_a
        if theta_tx > theta_hzn[0]:
            theta_hzn[0] = theta_tx
            d_hzn__meter[0] = d_tx__meter
        if theta_rx > theta_hzn[1]:
            theta_hzn[1] = theta_rx
            d_hzn__meter[1] = d_rx__meter
    return theta_hzn, d_hzn__meter


# --- ComputeDeltaH.cpp ---

def compute_delta_h(pfl: Sequence[float], d_start__meter: float, d_end__meter: float) -> float:
    np_ = int(pfl[0])
    x_start = d_start__meter / pfl[1]
    x_end = d_end__meter / pfl[1]

    if x_end - x_start < 2.0:
        return 0.0

    p10 = int(0.1 * (x_end - x_start + 8.0))
    p10 = min(max(4, p10), 25)
    n = 10 * p10 - 5
    p90 = n - p10

    np_s = float(n - 1)
    s = [0.0] * (n + 2)
    s[0] = np_s
    s[1] = 1.0

    x_end = (x_end - x_start) / np_s
    i = int(x_start)
    x_start -= float(i + 1.0)

    for j in range(n):
        while x_start > 0.0 and (i + 1) < np_:
            x_start -= 1
            i += 1
        s[j + 2] = pfl[i + 3] + (pfl[i + 3] - pfl[i + 2]) * x_start
        x_start += x_end

    fit_y1, fit_y2 = linear_least_squares_fit(s, 0.0, np_s)
    fit_y2 = (fit_y2 - fit_y1) / np_s

    diffs = []
    for j in range(n):
        diffs.append(s[j + 2] - fit_y1)
        fit_y1 += fit_y2

    # nth_element con greater<>: quantili dall'alto
    diffs.sort(reverse=True)
    q10 = diffs[p10 - 1]
    q90 = diffs[p90]

    delta_h_d__meter = q10 - q90
    return delta_h_d__meter / (1.0 - 0.8 * math.exp(-(d_end__meter - d_start__meter) / 50e3))


# --- LinearLeastSquaresFit.cpp ---

def linear_least_squares_fit(pfl: Sequence[float], d_start: float, d_end: float) -> tuple[float, float]:
    """Restituisce (fit_y1, fit_y2)."""
    np_ = int(pfl[0])
    i_start = int(_fdim(d_start / pfl[1], 0.0))
    i_end = np_ - int(_fdim(np_, d_end / pfl[1]))

    if i_end <= i_start:
        i_start = int(_fdim(i_start, 1.0))
        i_end = np_ - int(_fdim(np_, i_end + 1.0))

    x_length = float(i_end - i_start)

    mid_shifted_index = -0.5 * x_length
    mid_shifted_end = i_end + mid_shifted_index

    sum_y = 0.5 * (pfl[i_start + 2] + pfl[i_end + 2])
    scaled_sum_y = 0.5 * (pfl[i_start + 2] - pfl[i_end + 2]) * mid_shifted_index

    i = 2
    while i <= x_length:
        i_start += 1
        mid_shifted_index += 1
        z = pfl[i_start + 2]
        sum_y += z
        scaled_sum_y += z * mid_shifted_index
        i += 1

    sum_y = sum_y / x_length
    scaled_sum_y = scaled_sum_y * 12.0 / ((x_length * x_length + 2.0) * x_length)

    fit_y1 = sum_y - scaled_sum_y * mid_shifted_end
    fit_y2 = sum_y + scaled_sum_y * (np_ - mid_shifted_end)
    return fit_y1, fit_y2


# --- LongleyRice.cpp ---

def longley_rice(theta_hzn: Sequence[float], f__mhz: float, z_g: complex,
                 d_hzn__meter: Sequence[float], h_e__meter: Sequence[float], gamma_e: float,
                 n_s: float, delta_h__meter: float, h__meter: Sequence[float], d__meter: float,
                 mode: int, warnings: int) -> tuple[float, int, int]:
    """Restituisce (A_ref__db, warnings, propmode). Solleva `ItmError`."""
    a_e__meter = 1 / gamma_e

    d_hzn_s__meter = [math.sqrt(2.0 * h_e__meter[i] * a_e__meter) for i in range(2)]
    d_sml__meter = d_hzn_s__meter[0] + d_hzn_s__meter[1]
    d_ml__meter = d_hzn__meter[0] + d_hzn__meter[1]
    theta_los = -max(theta_hzn[0] + theta_hzn[1], -d_ml__meter / a_e__meter)

    if abs(theta_hzn[0]) > 200e-3:
        warnings |= WARN__TX_HORIZON_ANGLE
    if abs(theta_hzn[1]) > 200e-3:
        warnings |= WARN__RX_HORIZON_ANGLE
    if d_hzn__meter[0] < 0.1 * d_hzn_s__meter[0]:
        warnings |= WARN__TX_HORIZON_DISTANCE_1
    if d_hzn__meter[1] < 0.1 * d_hzn_s__meter[1]:
        warnings |= WARN__RX_HORIZON_DISTANCE_1
    if d_hzn__meter[0] > 3.0 * d_hzn_s__meter[0]:
        warnings |= WARN__TX_HORIZON_DISTANCE_2
    if d_hzn__meter[1] > 3.0 * d_hzn_s__meter[1]:
        warnings |= WARN__RX_HORIZON_DISTANCE_2

    if n_s < 150:
        raise ItmError(ERROR__SURFACE_REFRACTIVITY_SMALL)
    if n_s > 400:
        raise ItmError(ERROR__SURFACE_REFRACTIVITY_LARGE)
    if n_s < 250:
        warnings |= WARN__SURFACE_REFRACTIVITY

    if a_e__meter < 4000000 or a_e__meter > 13333333:
        raise ItmError(ERROR__EFFECTIVE_EARTH)

    if z_g.real <= abs(z_g.imag):
        raise ItmError(ERROR__GROUND_IMPEDANCE)

    scale = (a_e__meter ** 2 / f__mhz) ** (1.0 / 3.0)
    d_3__meter = max(d_sml__meter, d_ml__meter + 5.0 * scale)
    d_4__meter = d_3__meter + 10.0 * scale

    a_3__db = diffraction_loss(d_3__meter, d_hzn__meter, h_e__meter, z_g, a_e__meter, delta_h__meter,
                               h__meter, mode, theta_los, d_sml__meter, f__mhz)
    a_4__db = diffraction_loss(d_4__meter, d_hzn__meter, h_e__meter, z_g, a_e__meter, delta_h__meter,
                               h__meter, mode, theta_los, d_sml__meter, f__mhz)

    m_d = (a_4__db - a_3__db) / (d_4__meter - d_3__meter)
    a_d0__db = a_3__db - m_d * d_3__meter

    d_min__meter = abs(h_e__meter[0] - h_e__meter[1]) / 200e-3
    if d__meter < d_min__meter:
        warnings |= WARN__PATH_DISTANCE_TOO_SMALL_1
    if d__meter < 1e3:
        warnings |= WARN__PATH_DISTANCE_TOO_SMALL_2
    if d__meter > 1000e3:
        warnings |= WARN__PATH_DISTANCE_TOO_BIG_1
    if d__meter > 2000e3:
        warnings |= WARN__PATH_DISTANCE_TOO_BIG_2

    if d__meter < d_sml__meter:
        a_sml__db = d_sml__meter * m_d + a_d0__db
        d_0__meter = 0.04 * f__mhz * h_e__meter[0] * h_e__meter[1]
        if a_d0__db >= 0.0:
            d_0__meter = min(d_0__meter, 0.5 * d_ml__meter)
            d_1__meter = d_0__meter + 0.25 * (d_ml__meter - d_0__meter)
        else:
            d_1__meter = max(-a_d0__db / m_d, 0.25 * d_ml__meter)

        a_1__db = line_of_sight_loss(d_1__meter, h_e__meter, z_g, delta_h__meter, m_d, a_d0__db,
                                     d_sml__meter, f__mhz)

        flag = False
        khat_1 = 0.0
        khat_2 = 0.0

        if d_0__meter < d_1__meter:
            a_0__db = line_of_sight_loss(d_0__meter, h_e__meter, z_g, delta_h__meter, m_d, a_d0__db,
                                         d_sml__meter, f__mhz)
            q = math.log(d_sml__meter / d_0__meter)
            khat_2 = max(0.0, ((d_sml__meter - d_0__meter) * (a_1__db - a_0__db)
                               - (d_1__meter - d_0__meter) * (a_sml__db - a_0__db))
                         / ((d_sml__meter - d_0__meter) * math.log(d_1__meter / d_0__meter)
                            - (d_1__meter - d_0__meter) * q))
            flag = a_d0__db > 0.0 or khat_2 > 0.0
            if flag:
                khat_1 = (a_sml__db - a_0__db - khat_2 * q) / (d_sml__meter - d_0__meter)
                if khat_1 < 0.0:
                    khat_1 = 0.0
                    khat_2 = _fdim(a_sml__db, a_0__db) / q
                    if khat_2 == 0.0:
                        khat_1 = m_d

        if not flag:
            khat_1 = _fdim(a_sml__db, a_1__db) / (d_sml__meter - d_1__meter)
            khat_2 = 0.0
            if khat_1 == 0.0:
                khat_1 = m_d

        a_o__db = a_sml__db - khat_1 * d_sml__meter - khat_2 * math.log(d_sml__meter)
        a_ref__db = a_o__db + khat_1 * d__meter + khat_2 * math.log(d__meter)
        propmode = MODE__LINE_OF_SIGHT
    else:
        d_5__meter = d_ml__meter + 200e3
        d_6__meter = d_ml__meter + 400e3

        h0 = [-1.0]  # condiviso tra le due chiamate, come il puntatore del C++
        a_6__db = troposcatter_loss(d_6__meter, theta_hzn, d_hzn__meter, h_e__meter, a_e__meter,
                                    n_s, f__mhz, theta_los, h0)
        a_5__db = troposcatter_loss(d_5__meter, theta_hzn, d_hzn__meter, h_e__meter, a_e__meter,
                                    n_s, f__mhz, theta_los, h0)

        if a_5__db < 1000.0:
            m_s = (a_6__db - a_5__db) / 200e3
            d_x__meter = max(max(d_sml__meter,
                                 d_ml__meter + 1.088 * scale * math.log(f__mhz)),
                             (a_5__db - a_d0__db - m_s * d_5__meter) / (m_d - m_s))
            a_s0__db = (m_d - m_s) * d_x__meter + a_d0__db
        else:
            m_s = m_d
            a_s0__db = a_d0__db
            d_x__meter = 10e6

        if d__meter > d_x__meter:
            a_ref__db = m_s * d__meter + a_s0__db
            propmode = MODE__TROPOSCATTER
        else:
            a_ref__db = m_d * d__meter + a_d0__db
            propmode = MODE__DIFFRACTION

    a_ref__db = max(a_ref__db, 0.0)
    return a_ref__db, warnings, propmode


# --- DiffractionLoss.cpp ---

def diffraction_loss(d__meter: float, d_hzn__meter: Sequence[float], h_e__meter: Sequence[float],
                     z_g: complex, a_e__meter: float, delta_h__meter: float,
                     h__meter: Sequence[float], mode: int, theta_los: float,
                     d_sml__meter: float, f__mhz: float) -> float:
    a_k__db = knife_edge_diffraction(d__meter, f__mhz, a_e__meter, theta_los, d_hzn__meter)
    a_se__db = smooth_earth_diffraction(d__meter, f__mhz, a_e__meter, theta_los, d_hzn__meter,
                                        h_e__meter, z_g)

    delta_h_dsml__meter = terrain_roughness(d_sml__meter, delta_h__meter)
    sigma_h_d__meter = sigma_h_function(delta_h_dsml__meter)

    a_fo__db = min(15.0, 5 * math.log10(1.0 + 1e-5 * h__meter[0] * h__meter[1] * f__mhz * sigma_h_d__meter))

    delta_h_d__meter = terrain_roughness(d__meter, delta_h__meter)

    q = h__meter[0] * h__meter[1]
    qk = h_e__meter[0] * h_e__meter[1] - q

    if mode == MODE__P2P:
        q += 10.0

    term1 = math.sqrt(1.0 + qk / q)
    d_ml__meter = d_hzn__meter[0] + d_hzn__meter[1]

    q = (term1 + (-theta_los * a_e__meter + d_ml__meter) / d__meter) * min(delta_h_d__meter * f__mhz / 47.7, 6283.2)

    w = 25.1 / (25.1 + math.sqrt(q))
    return w * a_se__db + (1.0 - w) * a_k__db + a_fo__db


# --- KnifeEdgeDiffraction.cpp ---

def knife_edge_diffraction(d__meter: float, f__mhz: float, a_e__meter: float, theta_los: float,
                           d_hzn__meter: Sequence[float]) -> float:
    d_ml__meter = d_hzn__meter[0] + d_hzn__meter[1]
    theta_nlos = d__meter / a_e__meter - theta_los
    d_nlos__meter = d__meter - d_ml__meter

    k = 0.0795775 * (f__mhz / 47.7) * theta_nlos ** 2
    v_1 = k * d_hzn__meter[0] * d_nlos__meter / (d_nlos__meter + d_hzn__meter[0])
    v_2 = k * d_hzn__meter[1] * d_nlos__meter / (d_nlos__meter + d_hzn__meter[1])
    return fresnel_integral(v_1) + fresnel_integral(v_2)


# --- SmoothEarthDiffraction.cpp ---

def smooth_earth_diffraction(d__meter: float, f__mhz: float, a_e__meter: float, theta_los: float,
                             d_hzn__meter: Sequence[float], h_e__meter: Sequence[float],
                             z_g: complex) -> float:
    theta_nlos = d__meter / a_e__meter - theta_los
    d_ml__meter = d_hzn__meter[0] + d_hzn__meter[1]

    a__meter = (
        (d__meter - d_ml__meter) / (d__meter / a_e__meter - theta_los),
        0.5 * d_hzn__meter[0] ** 2 / h_e__meter[0],
        0.5 * d_hzn__meter[1] ** 2 / h_e__meter[1],
    )
    d__km = (
        (a__meter[0] * theta_nlos) / 1000.0,
        d_hzn__meter[0] / 1000.0,
        d_hzn__meter[1] / 1000.0,
    )

    abs_z_g = abs(z_g)
    f_m_third = f__mhz ** -THIRD
    f_third = f__mhz ** THIRD
    c_0 = [((4.0 / 3.0) * A_0__METER / a__meter[i]) ** THIRD for i in range(3)]
    k = [0.017778 * c_0[i] * f_m_third / abs_z_g for i in range(3)]
    b_0 = [1.607 - k[i] for i in range(3)]

    x1__km = b_0[1] * c_0[1] ** 2 * f_third * d__km[1]
    x2__km = b_0[2] * c_0[2] ** 2 * f_third * d__km[2]
    x0__km = b_0[0] * c_0[0] ** 2 * f_third * d__km[0] + x1__km + x2__km

    f_x0__db = height_function(x1__km, k[1])
    f_x1__db = height_function(x2__km, k[2])

    g_x__db = 0.05751 * x0__km - 10.0 * math.log10(x0__km)
    return g_x__db - f_x0__db - f_x1__db - 20


def height_function(x__km: float, k: float) -> float:
    if x__km < 200.0:
        w = -math.log(k)
        if k < 1e-5 or x__km * w ** 3 > 5495.0:
            result = -117.0
            if x__km > 1.0:
                result = 17.372 * math.log(x__km) + result
        else:
            result = 2.5e-5 * x__km ** 2 / k - 8.686 * w - 15.0
    else:
        result = 0.05751 * x__km - 4.343 * math.log(x__km)
        if x__km < 2000:
            w = 0.0134 * x__km * math.exp(-0.005 * x__km)
            result = (1.0 - w) * result + w * (17.372 * math.log(x__km) - 117.0)
    return result


# --- LineOfSightLoss.cpp ---

def line_of_sight_loss(d__meter: float, h_e__meter: Sequence[float], z_g: complex,
                       delta_h__meter: float, m_d: float, a_d0: float, d_sml__meter: float,
                       f__mhz: float) -> float:
    delta_h_d__meter = terrain_roughness(d__meter, delta_h__meter)
    sigma_h_d__meter = sigma_h_function(delta_h_d__meter)

    wn = f__mhz / 47.7

    h_sum = h_e__meter[0] + h_e__meter[1]
    sin_psi = h_sum / math.sqrt(d__meter ** 2 + h_sum ** 2)

    r_e = (sin_psi - z_g) / (sin_psi + z_g) * math.exp(-min(10.0, wn * sigma_h_d__meter * sin_psi))

    q = r_e.real ** 2 + r_e.imag ** 2
    if q < 0.25 or q < sin_psi:
        r_e = r_e * math.sqrt(sin_psi / q)

    delta_phi = wn * 2.0 * h_e__meter[0] * h_e__meter[1] / d__meter

    if delta_phi > math.pi / 2.0:
        delta_phi = math.pi - (math.pi / 2.0) ** 2 / delta_phi

    rr = complex(math.cos(delta_phi), -math.sin(delta_phi)) + r_e
    a_t__db = -10 * math.log10(rr.real ** 2 + rr.imag ** 2)

    a_d__db = m_d * d__meter + a_d0

    w = 1 / (1 + f__mhz * delta_h__meter / max(10e3, d_sml__meter))
    return w * a_t__db + (1 - w) * a_d__db


# --- TroposcatterLoss.cpp ---

def f_function(td: float) -> float:
    a = (133.4, 104.6, 71.8)
    b = (0.332e-3, 0.212e-3, 0.157e-3)
    c = (-10, -2.5, 5)
    if td <= 10e3:
        i = 0
    elif td <= 70e3:
        i = 1
    else:
        i = 2
    return a[i] + b[i] * td + c[i] * math.log10(td)


def troposcatter_loss(d__meter: float, theta_hzn: Sequence[float], d_hzn__meter: Sequence[float],
                      h_e__meter: Sequence[float], a_e__meter: float, n_s: float, f__mhz: float,
                      theta_los: float, h0: list[float]) -> float:
    """`h0` e' una lista di un elemento: ingresso/uscita come il `double *h0` del C++."""
    wn = f__mhz / 47.7

    if h0[0] > 15.0:
        h_0 = h0[0]
    else:
        ad = d_hzn__meter[0] - d_hzn__meter[1]
        rr = h_e__meter[1] / h_e__meter[0]

        if ad < 0.0:
            ad = -ad
            rr = 1.0 / rr

        theta = theta_hzn[0] + theta_hzn[1] + d__meter / a_e__meter

        r_1 = 2.0 * wn * theta * h_e__meter[0]
        r_2 = 2.0 * wn * theta * h_e__meter[1]

        if r_1 < 0.2 and r_2 < 0.2:
            return 1001.0

        s = (d__meter - ad) / (d__meter + ad)

        q = min(max(0.1, rr / s), 10.0)
        s = max(0.1, s)

        h_0__meter = (d__meter - ad) * (d__meter + ad) * theta * 0.25 / d__meter

        z_0__meter = 1.7556e3
        z_1__meter = 8.0e3

        eta_s = (h_0__meter / z_0__meter) * (
            1.0 + (0.031 - n_s * 2.32e-3 + n_s ** 2 * 5.67e-6)
            * math.exp(-min(1.7, h_0__meter / z_1__meter) ** 6))

        h_00 = (h0_function(r_1, eta_s) + h0_function(r_2, eta_s)) / 2
        delta_h_0 = min(h_00, 6.0 * (0.6 - math.log10(max(eta_s, 1.0))) * math.log10(s) * math.log10(q))

        h_0 = h_00 + delta_h_0
        h_0 = max(h_0, 0.0)

        if eta_s < 1.0:
            h_0 = eta_s * h_0 + (1.0 - eta_s) * 10 * math.log10(
                ((1.0 + SQRT2 / r_1) * (1.0 + SQRT2 / r_2)) ** 2 * (r_1 + r_2) / (r_1 + r_2 + 2 * SQRT2))

        if h_0 > 15.0 and h0[0] >= 0.0:
            h_0 = h0[0]

    h0[0] = h_0

    th = d__meter / a_e__meter - theta_los

    d_0__meter = 40e3
    h__meter = 47.7

    return (f_function(th * d__meter) + 10 * math.log10(wn * h__meter * th ** 4)
            - 0.1 * (n_s - 301.0) * math.exp(-th * d__meter / d_0__meter) + h_0)


# --- H0Function.cpp ---

_H0_A = (25.0, 80.0, 177.0, 395.0, 705.0)
_H0_B = (24.0, 45.0, 68.0, 80.0, 105.0)


def h0_curve(j: int, r: float) -> float:
    return 10 * math.log10(1 + _H0_A[j] * (1 / r) ** 4 + _H0_B[j] * (1.0 / r) ** 2)


def h0_function(r: float, eta_s: float) -> float:
    eta_s = min(max(eta_s, 1), 5)
    i = int(eta_s)
    q = eta_s - i
    result = h0_curve(i - 1, r)
    if q != 0.0:
        result = (1.0 - q) * result + q * h0_curve(i, r)
    return result


# --- FresnelIntegral.cpp ---

def fresnel_integral(v2: float) -> float:
    if v2 < 5.76:
        return 6.02 + 9.11 * math.sqrt(v2) - 1.27 * v2
    return 12.953 + 10 * math.log10(v2)


# --- FreeSpaceLoss.cpp ---

def free_space_loss(d__meter: float, f__mhz: float) -> float:
    return 32.45 + 20.0 * math.log10(f__mhz) + 20.0 * math.log10(d__meter / 1000.0)


# --- TerrainRoughness.cpp ---

def terrain_roughness(d__meter: float, delta_h__meter: float) -> float:
    return delta_h__meter * (1.0 - 0.8 * math.exp(-d__meter / 50e3))


# --- SigmaHFunction.cpp ---

def sigma_h_function(delta_h__meter: float) -> float:
    return 0.78 * delta_h__meter * math.exp(-0.5 * delta_h__meter ** 0.25)


# --- Variability.cpp ---

_ALL_YEAR = (
    (-9.67, -0.62, 1.26, -9.21, -0.62, -0.39, 3.15),
    (12.7, 9.19, 15.5, 9.05, 9.19, 2.86, 857.9),
    (144.9e3, 228.9e3, 262.6e3, 84.1e3, 228.9e3, 141.7e3, 2222.e3),
    (190.3e3, 205.2e3, 185.2e3, 101.1e3, 205.2e3, 315.9e3, 164.8e3),
    (133.8e3, 143.6e3, 99.8e3, 98.6e3, 143.6e3, 167.4e3, 116.3e3),
)
_BSM1 = (2.13, 2.66, 6.11, 1.98, 2.68, 6.86, 8.51)
_BSM2 = (159.5, 7.67, 6.65, 13.11, 7.16, 10.38, 169.8)
_XSM1 = (762.2e3, 100.4e3, 138.2e3, 139.1e3, 93.7e3, 187.8e3, 609.8e3)
_XSM2 = (123.6e3, 172.5e3, 242.2e3, 132.7e3, 186.8e3, 169.6e3, 119.9e3)
_XSM3 = (94.5e3, 136.4e3, 178.6e3, 193.5e3, 133.5e3, 108.9e3, 106.6e3)
_BSP1 = (2.11, 6.87, 10.08, 3.68, 4.75, 8.58, 8.43)
_BSP2 = (102.3, 15.53, 9.60, 159.3, 8.12, 13.97, 8.19)
_XSP1 = (636.9e3, 138.7e3, 165.3e3, 464.4e3, 93.2e3, 216.0e3, 136.2e3)
_XSP2 = (134.8e3, 143.7e3, 225.7e3, 93.1e3, 135.9e3, 152.0e3, 188.5e3)
_XSP3 = (95.6e3, 98.6e3, 129.7e3, 94.2e3, 113.4e3, 122.7e3, 122.9e3)
_C_D = (1.224, 0.801, 1.380, 1.000, 1.224, 1.518, 1.518)
_Z_D = (1.282, 2.161, 1.282, 20.0, 1.282, 1.282, 1.282)
_BFM1 = (1.0, 1.0, 1.0, 1.0, 0.92, 1.0, 1.0)
_BFM2 = (0.0, 0.0, 0.0, 0.0, 0.25, 0.0, 0.0)
_BFM3 = (0.0, 0.0, 0.0, 0.0, 1.77, 0.0, 0.0)
_BFP1 = (1.0, 0.93, 1.0, 0.93, 0.93, 1.0, 1.0)
_BFP2 = (0.0, 0.31, 0.0, 0.19, 0.31, 0.0, 0.0)
_BFP3 = (0.0, 2.00, 0.0, 1.79, 2.00, 0.0, 0.0)


def curve(c1: float, c2: float, x1: float, x2: float, x3: float, d_e__meter: float) -> float:
    r = (d_e__meter / x1) ** 2
    return (c1 + c2 / (1.0 + ((d_e__meter - x2) / x3) ** 2)) * r / (1.0 + r)


def variability(time: float, location: float, situation: float, h_e__meter: Sequence[float],
                delta_h__meter: float, f__mhz: float, d__meter: float, a_ref__db: float,
                climate: int, mdvar: int, warnings: int) -> tuple[float, int]:
    """Restituisce (attenuazione relativa allo spazio libero in dB, warnings)."""
    z_t = inverse_complementary_cumulative_distribution_function(time / 100)
    z_l = inverse_complementary_cumulative_distribution_function(location / 100)
    z_s = inverse_complementary_cumulative_distribution_function(situation / 100)

    c = climate - 1
    wn = f__mhz / 47.7

    d_ex__meter = (math.sqrt(2 * A_9000__METER * h_e__meter[0])
                   + math.sqrt(2 * A_9000__METER * h_e__meter[1])
                   + (575.7e12 / wn) ** THIRD)
    if d__meter < d_ex__meter:
        d_e__meter = 130e3 * d__meter / d_ex__meter
    else:
        d_e__meter = 130e3 + d__meter - d_ex__meter

    mdvar_internal = mdvar
    plus20 = mdvar_internal >= 20
    if plus20:
        mdvar_internal -= 20

    if plus20:
        sigma_s = 0.0
    else:
        sigma_s = 5.0 + 3.0 * math.exp(-d_e__meter / 100e3)

    plus10 = mdvar_internal >= 10
    if plus10:
        mdvar_internal -= 10

    v_med__db = curve(_ALL_YEAR[0][c], _ALL_YEAR[1][c], _ALL_YEAR[2][c], _ALL_YEAR[3][c],
                      _ALL_YEAR[4][c], d_e__meter)

    if mdvar_internal == SINGLE_MESSAGE_MODE:
        z_t = z_s
        z_l = z_s
    elif mdvar_internal == ACCIDENTAL_MODE:
        z_l = z_s
    elif mdvar_internal == MOBILE_MODE:
        z_l = z_t

    if abs(z_t) > 3.10 or abs(z_l) > 3.10 or abs(z_s) > 3.10:
        warnings |= WARN__EXTREME_VARIABILITIES

    if plus10:
        sigma_l = 0.0
    else:
        delta_h_d__meter = terrain_roughness(d__meter, delta_h__meter)
        sigma_l = 10.0 * wn * delta_h_d__meter / (wn * delta_h_d__meter + 13.0)
    y_l = sigma_l * z_l

    q = math.log(0.133 * wn)
    g_minus = _BFM1[c] + _BFM2[c] / ((_BFM3[c] * q) ** 2 + 1.0)
    g_plus = _BFP1[c] + _BFP2[c] / ((_BFP3[c] * q) ** 2 + 1.0)

    sigma_t_minus = curve(_BSM1[c], _BSM2[c], _XSM1[c], _XSM2[c], _XSM3[c], d_e__meter) * g_minus
    sigma_t_plus = curve(_BSP1[c], _BSP2[c], _XSP1[c], _XSP2[c], _XSP3[c], d_e__meter) * g_plus

    sigma_td = _C_D[c] * sigma_t_plus
    tgtd = (sigma_t_plus - sigma_td) * _Z_D[c]

    if z_t < 0.0:
        sigma_t = sigma_t_minus
    elif z_t <= _Z_D[c]:
        sigma_t = sigma_t_plus
    else:
        sigma_t = sigma_td + tgtd / z_t
    y_t = sigma_t * z_t

    y_s_temp = sigma_s ** 2 + y_t ** 2 / (7.8 + z_s ** 2) + y_l ** 2 / (24.0 + z_s ** 2)

    if mdvar_internal == SINGLE_MESSAGE_MODE:
        y_r = 0.0
        y_s = math.sqrt(sigma_t ** 2 + sigma_l ** 2 + y_s_temp) * z_s
    elif mdvar_internal == ACCIDENTAL_MODE:
        y_r = y_t
        y_s = math.sqrt(sigma_l ** 2 + y_s_temp) * z_s
    elif mdvar_internal == MOBILE_MODE:
        y_r = math.sqrt(sigma_t ** 2 + sigma_l ** 2) * z_t
        y_s = math.sqrt(y_s_temp) * z_s
    else:
        y_r = y_t + y_l
        y_s = math.sqrt(y_s_temp) * z_s

    result = a_ref__db - v_med__db - y_r - y_s

    if result < 0.0:
        result = result * (29.0 - result) / (29.0 - 10.0 * result)
    return result, warnings


# --- InverseComplementaryCumulativeDistributionFunction.cpp ---

def inverse_complementary_cumulative_distribution_function(q: float) -> float:
    c_0 = 2.515516
    c_1 = 0.802853
    c_2 = 0.010328
    d_1 = 1.432788
    d_2 = 0.189269
    d_3 = 0.001308

    x = q
    if q > 0.5:
        x = 1.0 - x

    t_x = math.sqrt(-2.0 * math.log(x))
    zeta_x = ((c_2 * t_x + c_1) * t_x + c_0) / (((d_3 * t_x + d_2) * t_x + d_1) * t_x + 1.0)
    q_q = t_x - zeta_x
    if q > 0.5:
        q_q = -q_q
    return q_q
