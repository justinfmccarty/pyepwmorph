"""Vectorised psychrometric conversions.

The formulas are taken from the ASHRAE Handbook -- Fundamentals (2017),
chapter 1.  The scalar reference implementation is PsychroLib, which is
released under the MIT license:

    Meyer et al. (2019). PsychroLib: a library of psychrometric functions to
    calculate thermodynamic properties of air. Journal of Open Source
    Software, 4(33), 1137. https://doi.org/10.21105/joss.01137
    https://github.com/psychrometrics/psychrolib

Every function accepts scalars, numpy arrays, or pandas Series and returns a
numpy array (or a float, when every input was scalar).
"""

import numpy as np

#: Ratio of the molecular mass of water vapour to that of dry air.
#: ASHRAE Handbook -- Fundamentals (2017) ch. 1.
MW_RATIO = 0.621945

#: Standard atmospheric pressure at sea level (Pa).
STANDARD_PRESSURE = 101325.0


def _scalar_if_scalar(result, *inputs):
    """Return a float when every input was a scalar, otherwise the array."""
    if all(np.ndim(value) == 0 for value in inputs):
        return float(result)
    return result


def saturated_vapor_pressure(t_kelvin):
    """Saturation vapour pressure (Pa) at a given temperature (K).

    Accounts for the different behaviour above and below the freezing point
    of water (ASHRAE Handbook -- Fundamentals 2017, ch. 1 eqn. 5 and 6).

    Parameters
    ----------
    t_kelvin : array_like
        Temperature (K).

    Returns
    -------
    np.ndarray or float
        Saturation vapour pressure (Pa).
    """
    t = np.asarray(t_kelvin, dtype=float)
    ln_t = np.log(t)
    over_ice = (
        -5.6745359e03 / t + 6.3925247 - 9.677843e-03 * t
        + 6.2215701e-07 * t ** 2 + 2.0747825e-09 * t ** 3
        - 9.484024e-13 * t ** 4 + 4.1635019 * ln_t
    )
    over_water = (
        -5.8002206e03 / t + 1.3914993 - 4.8640239e-02 * t
        + 4.1764768e-05 * t ** 2 - 1.4452093e-08 * t ** 3
        + 6.5459673 * ln_t
    )
    return _scalar_if_scalar(np.exp(np.where(t <= 273.15, over_ice, over_water)), t_kelvin)


def _d_ln_p_ws(db_temp):
    """Analytical derivative of ln(saturation vapour pressure) wrt temperature."""
    db = np.asarray(db_temp, dtype=float)
    t = db + 273.15
    over_ice = (
        5.6745359e03 / t ** 2 - 9.677843e-03 + 2 * 6.2215701e-07 * t
        + 3 * 2.0747825e-09 * t ** 2 - 4 * 9.484024e-13 * t ** 3
        + 4.1635019 / t
    )
    over_water = (
        5.8002206e03 / t ** 2 - 4.8640239e-02 + 2 * 4.1764768e-05 * t
        - 3 * 1.4452093e-08 * t ** 2 + 6.5459673 / t
    )
    return np.where(db <= 0.0, over_ice, over_water)


def humid_ratio_from_db_rh(db_temp, rel_humid, b_press=STANDARD_PRESSURE):
    """Humidity ratio (kg water / kg dry air) from dry bulb (C) and RH (%).

    ASHRAE Handbook -- Fundamentals (2017) ch. 1 eqn. 20.

    Parameters
    ----------
    db_temp : array_like
        Dry bulb temperature (C).
    rel_humid : array_like
        Relative humidity (%).
    b_press : array_like
        Atmospheric pressure (Pa).

    Returns
    -------
    np.ndarray or float
        Humidity ratio (kg water / kg dry air).
    """
    db = np.asarray(db_temp, dtype=float)
    rh = np.asarray(rel_humid, dtype=float)
    press = np.asarray(b_press, dtype=float)
    p_w = saturated_vapor_pressure(db + 273.15) * (rh / 100.0)
    result = (p_w * MW_RATIO) / (press - p_w)
    return _scalar_if_scalar(result, db_temp, rel_humid, b_press)


def rel_humid_from_db_hr(db_temp, humid_ratio, b_press=STANDARD_PRESSURE):
    """Relative humidity (%) from dry bulb (C) and humidity ratio.

    Parameters
    ----------
    db_temp : array_like
        Dry bulb temperature (C).
    humid_ratio : array_like
        Humidity ratio (kg water / kg dry air).
    b_press : array_like
        Atmospheric pressure (Pa).

    Returns
    -------
    np.ndarray or float
        Relative humidity (%).
    """
    db = np.asarray(db_temp, dtype=float)
    ratio = np.asarray(humid_ratio, dtype=float)
    press = np.asarray(b_press, dtype=float)
    p_w = (ratio * press) / (MW_RATIO + ratio)
    p_ws = saturated_vapor_pressure(db + 273.15)
    return _scalar_if_scalar((p_w / p_ws) * 100.0, db_temp, humid_ratio, b_press)


def specific_humidity_from_humid_ratio(humid_ratio):
    """Specific humidity (kg water / kg moist air) from humidity ratio."""
    ratio = np.asarray(humid_ratio, dtype=float)
    return _scalar_if_scalar(ratio / (1.0 + ratio), humid_ratio)


def humid_ratio_from_specific_humidity(specific_humidity):
    """Humidity ratio (kg water / kg dry air) from specific humidity."""
    q = np.asarray(specific_humidity, dtype=float)
    return _scalar_if_scalar(q / (1.0 - q), specific_humidity)


def dew_point_from_db_rh(db_temp, rel_humid, tolerance=0.1, max_iter=100):
    """Dew point temperature (C) from dry bulb (C) and relative humidity (%).

    Inverts the saturation vapour pressure curve with Newton-Raphson on the
    logarithm of vapour pressure, which is smooth and converges in three to
    five iterations.  The iteration runs over the whole array at once and
    stops as soon as every element is within *tolerance*.

    Parameters
    ----------
    db_temp : array_like
        Dry bulb temperature (C).
    rel_humid : array_like
        Relative humidity (%).
    tolerance : float
        Convergence tolerance in degrees C.
    max_iter : int
        Maximum Newton-Raphson iterations.

    Returns
    -------
    np.ndarray or float
        Dew point temperature (C).  Returns absolute zero where the relative
        humidity is zero.
    """
    db, rh = np.broadcast_arrays(
        np.asarray(db_temp, dtype=float), np.asarray(rel_humid, dtype=float)
    )
    p_w = saturated_vapor_pressure(db + 273.15) * (rh / 100.0)
    valid = p_w > 0.0

    ln_vp = np.log(np.where(valid, p_w, 1.0))
    dew_point = db.astype(float).copy()
    for _ in range(max_iter):
        previous = dew_point
        ln_vp_iter = np.log(saturated_vapor_pressure(previous + 273.15))
        dew_point = previous - (ln_vp_iter - ln_vp) / _d_ln_p_ws(previous)
        if np.all(np.abs(dew_point - previous) <= tolerance):
            break

    result = np.where(valid, np.minimum(dew_point, db), -273.15)
    return _scalar_if_scalar(result, db_temp, rel_humid)
