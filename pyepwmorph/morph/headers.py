"""Keep the EPW header blocks consistent with a morphed climate (3.6.0, issue #10).

A morph changes the hourly data but the source file's GROUND TEMPERATURES
and DESIGN CONDITIONS blocks describe the baseline climate. This module

- shifts the ground temperatures by each depth's response to the change in
  monthly mean dry-bulb, using the damping and lag that the source header
  itself implies (first annual harmonic of ground versus air), so the result
  stays consistent with however the source computed them. A source without
  ground temperatures gets them from the morphed monthly air with the
  Kusuda and Achenbach (1965) model;
- replaces DESIGN CONDITIONS with ``0`` (no design conditions), because the
  baseline ASHRAE values no longer describe the file. Recomputing them from
  the morphed hours is a separate piece of work.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

#: Fields per depth in the GROUND TEMPERATURES block: depth, conductivity,
#: density, specific heat, then twelve monthly values.
FIELDS_PER_DEPTH = 16

#: Depths (m) written when the source has no ground temperatures, as the
#: EnergyPlus weather converter does.
DEFAULT_DEPTHS_M = (0.5, 2.0, 4.0)

#: Soil thermal diffusivity (m2/day) for computed ground temperatures; the
#: EnergyPlus weather converter's value (2.3226e-3 m2/h).
DEFAULT_SOIL_DIFFUSIVITY_M2_DAY = 0.0557

#: Below this seasonal air amplitude (K) the header's damping and lag are not
#: well defined; only the annual-mean change is applied.
MIN_AIR_AMPLITUDE_K = 0.1

_OMEGA = 2.0 * math.pi / 12.0


def monthly_means(values, months):
    """Twelve monthly means of an hourly series, given each hour's month (1-12)."""
    values = np.asarray(values, dtype=float)
    months = np.asarray(months, dtype=int)
    return np.array([values[months == month].mean() for month in range(1, 13)])


def annual_harmonic(monthly):
    """``(mean, amplitude, phase)`` with ``x[m] ~ mean + amplitude * cos(w m - phase)``."""
    monthly = np.asarray(monthly, dtype=float)
    m = np.arange(12)
    c = 2.0 / 12.0 * np.sum(monthly * np.cos(_OMEGA * m))
    s = 2.0 / 12.0 * np.sum(monthly * np.sin(_OMEGA * m))
    return float(monthly.mean()), float(math.hypot(c, s)), float(math.atan2(s, c))


def parse_ground_temperatures(fields):
    """Split GROUND TEMPERATURES header fields into depth records.

    Returns
    -------
    list[dict] or None
        ``[{"depth": str, "properties": [str, str, str], "values": np.ndarray}]``,
        or ``None`` when the block is empty or malformed.
    """
    if not fields:
        return None
    try:
        count = int(float(fields[0]))
    except ValueError:
        return None
    if count <= 0 or len(fields) < 1 + count * FIELDS_PER_DEPTH:
        return None
    records = []
    for index in range(count):
        block = fields[1 + index * FIELDS_PER_DEPTH: 1 + (index + 1) * FIELDS_PER_DEPTH]
        try:
            values = np.array([float(value) for value in block[4:16]])
        except ValueError:
            return None
        records.append({"depth": block[0], "properties": list(block[1:4]), "values": values})
    return records


def format_ground_temperatures(records):
    """Header fields for depth records (values to two decimals)."""
    fields = [str(len(records))]
    for record in records:
        fields.append(record["depth"])
        fields.extend(record["properties"])
        fields.extend(f"{value:.2f}" for value in record["values"])
    return fields


def ground_change(present_air, morphed_air, ground):
    """Monthly change in ground temperature for one depth.

    The annual-mean air change passes through in full. The seasonal (first
    harmonic) part of the change is damped and lagged the way this depth's
    ground temperatures are damped and lagged against the present air.
    """
    _, air_amp, air_phase = annual_harmonic(present_air)
    _, ground_amp, ground_phase = annual_harmonic(ground)
    delta_mean, delta_amp, delta_phase = annual_harmonic(np.asarray(morphed_air) - np.asarray(present_air))
    m = np.arange(12)
    if air_amp < MIN_AIR_AMPLITUDE_K:
        return np.full(12, delta_mean)
    damping = min(ground_amp / air_amp, 1.0)
    lag = ground_phase - air_phase
    return delta_mean + damping * delta_amp * np.cos(_OMEGA * m - delta_phase - lag)


def kusuda_ground_temperatures(monthly_air, depths=DEFAULT_DEPTHS_M,
                               diffusivity_m2_day=DEFAULT_SOIL_DIFFUSIVITY_M2_DAY):
    """Monthly undisturbed ground temperatures from monthly air (Kusuda and Achenbach 1965).

    ``T(z, m) = mean + A exp(-z k) cos(w m - phase - z k)`` with
    ``k = sqrt(pi / (365 alpha))``, using the air's first annual harmonic.
    """
    mean, amplitude, phase = annual_harmonic(monthly_air)
    k = math.sqrt(math.pi / (365.0 * diffusivity_m2_day))
    m = np.arange(12)
    records = []
    for depth in depths:
        values = mean + amplitude * math.exp(-depth * k) * np.cos(_OMEGA * m - phase - depth * k)
        records.append({"depth": f"{depth:g}", "properties": ["", "", ""], "values": values})
    return records


def morphed_ground_temperatures(header_fields, present_drybulb, morphed_drybulb, months):
    """New GROUND TEMPERATURES fields for a morphed dry-bulb, or ``None`` if unchanged.

    Parameters
    ----------
    header_fields : list[str] or None
        The source block's fields (after the keyword), or ``None`` if absent.
    present_drybulb, morphed_drybulb : array_like
        Hourly dry-bulb before and after the morph (C).
    months : array_like
        Each hour's month (1-12).

    Returns
    -------
    tuple
        ``(fields, how)`` where *how* is ``"shifted"`` or ``"computed"``, or
        ``(None, None)`` when the change is below 0.005 K everywhere.
    """
    present_air = monthly_means(present_drybulb, months)
    morphed_air = monthly_means(morphed_drybulb, months)
    if np.max(np.abs(morphed_air - present_air)) < 0.005:
        return None, None
    records = parse_ground_temperatures(header_fields)
    if records is None:
        logger.info("The EPW has no ground temperatures; computing them from the morphed air (Kusuda)")
        return format_ground_temperatures(kusuda_ground_temperatures(morphed_air)), "computed"
    for record in records:
        record["values"] = record["values"] + ground_change(present_air, morphed_air, record["values"])
    return format_ground_temperatures(records), "shifted"
