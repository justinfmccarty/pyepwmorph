# coding=utf-8
"""
General utility scripts used throughout the package
"""
import math

import numpy as np
import pandas as pd
import calendar
import warnings

warnings.filterwarnings("ignore")

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023"
__credits__ = ["Justin McCarty"]
__license__ = "GPLv3"
__version__ = "0.1"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"


def min_max_mean_means(timeseries, first_resample="D", second_resample="M"):
    """
    Given a timeseries, resample to the max, the min, and the mean along a dimension.
        Then resample again at a coarser resolution to get the mean
    Parameters
    ----------
    timeseries : pd.Series with a datetime index
        a timeseries, likely annual hourly (8760,), of values that you want statistics for
    first_resample : string (default: 'D')
        the first resample resolution to operate at
    second_resample : string (default: 'M')
        the second resample resolution to operate at

    Returns
    -------
    tupple of three pd.Series with datetime index
        the max, min, and mean

    Examples
    --------
    >>> min_max_mean_means(data_series, first_resample="D", second_resample="M")
    """
    series_max = timeseries.resample(first_resample).max().resample(second_resample).mean().reset_index(drop=True)
    series_min = timeseries.resample(first_resample).min().resample(second_resample).mean().reset_index(drop=True)
    series_mean = timeseries.resample(first_resample).mean().resample(second_resample).mean().reset_index(drop=True)
    return series_max, series_min, series_mean


def absolute_delta(future, historical):
    """
    A very simple function for calculating the absolute delta but sometimes I get confused about if
        I put future in front historical or the other way around
    Parameters
    ----------
    future : numerical
        future value(s)
    historical : numerical
        historical value(s)

    Returns
    -------
    numerical
        the difference between the two

    Examples
    --------
    >>> absolute_delta(np.array([6,7,8]),np.array([10,4,9]))
    """
    return future - historical

def relative_delta(future, historical):
    """
    A very simple function for calcualting the relative (fractional) delta but sometimes I get confused about if
        I put future in front historical or the other way around
    Parameters
    ----------
    future : numerical
        future value(s)
    historical : numerical
        historical value(s)

    Returns
    -------
    numerical
        the difference between the two

    Examples
    --------
    >>> relative_delta(np.array([6,7,8]),np.array([10,4,9]))
    """
    return future / historical

def pandas_slice_year(data, start_year, end_year):

    """
    A very simple function but sometimes I get confused about if
        I put future in front historical or the other way around
    Parameters
    ----------
    data : pandas.Series
        a pandas Series with a datetime index
    start_year : int
        the year to start the slice with (inclusive)
    end_year : int
        the year to end the slice after (inclusive)

    Returns
    -------
    numerical
        the difference between the two

    Examples
    --------
    >>> import pandas as pd
    >>> import numpy as np
    >>> baseline_period = (1960,1990)
    >>> future_period = (2050,2060)
    >>> values = np.linspace(0,1799,150*12,dtype=int)
    >>> all_months = pd.date_range("01 January 1951",end="01 January 2101",freq='M')
    >>> climate_data = pd.Series(values,index=all_months)
    >>> historical_data = pandas_slice_year(climate_data, baseline_period[0], baseline_period[1])
    """
    return data[(data.index.year >= start_year) & (data.index.year <= end_year)]

def monthly_means(data):
    """
    For a multi-year monthly dataset group by month and take the mean for each month
    Parameters
    ----------
    data : pandas.Series
        a pandas Series with a datetime index

    Returns
    -------
    pd.Series
        a Series of 12 values which represent the mean for each month
    """
    return data.groupby(data.index.month).mean()

def zip_month_data(data):
    """
    creates an array (12,) int (1-12) and zips it to an input array of data

    Parameters
    ----------
    data : list, np.ndarray, or pd.Series
        an array of data with one value for each month of the year

    Returns
    -------
    dict
        keys are the months of the year in int form with the data set to each value

    Examples
    --------
    >>> zip_month_data(np.ones(12))
    """
    months = list(range(1, 12 + 1, 1))
    if type(data) is list:
        pass
    elif type(data) is np.ndarray:
        data = data.tolist()
    elif type(data) is pd.core.series.Series:
        data = data.tolist()
    else:
        print("Data must be in list, np.ndarray, or pd.Series format. shape==(12,). Attempting process")

    return dict(zip(months, data))




def zip_day_data(data):
    """
    creates an array (365,) int (1-365) and zips it to an input array of data

    Parameters
    ----------
    data : list, np.ndarray, or pd.Series
        an array of data with one value for each month of the year

    Returns
    -------
    dict
        keys are the days of the year in int form with the data set to each value

    Examples
    --------
    >>> zip_day_data(np.ones(365))
    """
    days = list(range(1, 365 + 1, 1))
    if type(data) is list:
        pass
    elif type(data) is np.ndarray:
        data = data.tolist()
    elif type(data) is pd.core.series.Series:
        data = data.tolist()
    else:
        print("Data must be in list, np.ndarray, or pd.Series format. shape==(365,). Attempting process")

    return dict(zip(days, data))

def uas_vas_2_sfcwind(uas, vas, calm_wind_thresh=0.5, out='SPD'):
    """
    Converts the UAS (eastward) and VAS (northward) wind vectors into surface wind speed
        adapated from xclim[1] to not take xarrays
        [1]https://xclim.readthedocs.io/en/stable/_modules/xclim/indices/_conversion.html#uas_vas_2_sfcwind

    Parameters
    ----------
    uas : tuple (int,int)
        Eastward wind activity
    vas : tuple (int,int)
        Northward wind activity
    calm_wind_thresh : float (Default: o.5)
        The threshold under which winds are considered "calm" and for which the direction
            is set to 0. On the Beaufort scale, calm winds are defined as < 0.5 m/s.
    out : string (Default: 'SPD')
        control statement for directing the output, either wind spped ('SPD') or wind direction ('DIR')
            we assume direction to never change

    Returns
    -------
    float
        calculated wind speed (m s-1) or wind direction (degrees)
            Direction from which the wind blows, following the meteorological convention where
            360 stands for North and 0 for calm winds.

    Examples
    --------
    >>>
    """
    #
    # adapted for no xarray

    # Wind speed is the hypotenuse of "uas" and "vas"
    wind = np.hypot(uas, vas)

    # Calculate the angle
    windfromdir_math = np.degrees(np.arctan2(vas, uas))

    # Convert the angle from the mathematical standard to the meteorological standard
    windfromdir = (270 - windfromdir_math) % 360.0

    # According to the meteorological standard, calm winds must have a direction of 0°
    # while northerly winds have a direction of 360°
    # On the Beaufort scale, calm winds are defined as < 0.5 m/s
    windfromdir = np.where(windfromdir.round() == 0, 360, windfromdir)
    windfromdir = np.where(wind < calm_wind_thresh, 0, windfromdir)
    if out == 'SPD':
        return wind
    elif out == 'DIR':
        return windfromdir


def ts_8760(year=2023, tz=None):
    """
    Uses pandas to create an annual hourly datetime series with or without timezone

    Parameters
    ----------
    year : int (Default: 2023)
        the year for your datetime index
    tz : str (Default: None)
        a timezone to match your datetime to

    Returns
    -------
    pd.Series
        datetime series for hourly annual
    """

    if tz is None:
        index = pd.date_range(start=f"01-01-{year} 00:00", end=f"12-31-{year} 23:00", freq="h")
    else:
        index = pd.date_range(start=f"01-01-2022 00:30", end=f"12-31-2022 23:30", freq="h", tz=tz)
    if calendar.isleap(year):
        index = index[~((index.month == 2) & (index.day == 29))]
    return index

def calc_period(year, period):
    extent = int(period[1]) - int(period[0])
    return int(year - (extent/2)), int(year + (extent/2))
#
# def saturation_vapor_pressure(present_dbt):
#     """Saturated vapor pressure (Pa) at a given dry bulb temperature (K).
#
#         This function accounts for the different behavior above vs. below
#         the freezing point of water.
#
#         Args:
#             t_kelvin: Dry bulb temperature (K).
#
#         Returns:
#             Saturated vapor pressure (Pa).
#
#         Note:
#             [1] ASHRAE Handbook - Fundamentals (2017) ch. 1 eqn. 5 and 6
#
#             [2] Meyer et al., (2019). PsychroLib: a library of psychrometric
#             functions to calculate thermodynamic properties of air. Journal of
#             Open Source Software, 4(33), 1137, https://doi.org/10.21105/joss.01137
#             https://github.com/psychrometrics/psychrolib/blob/master/src/python/psychrolib.py
#         """
#
#     t_kelvin = present_dbt + 273.15
#     if (t_kelvin <= 273.15):  # saturation vapor pressure below freezing
#         ln_p_ws = -5.6745359E+03 / t_kelvin + 6.3925247 - 9.677843E-03 * t_kelvin + \
#                   6.2215701E-07 * t_kelvin ** 2 + 2.0747825E-09 * math.pow(t_kelvin, 3) - \
#                   9.484024E-13 * math.pow(t_kelvin, 4) + 4.1635019 * math.log(t_kelvin)
#     else:  # saturation vapor pressure above freezing
#         ln_p_ws = -5.8002206E+03 / t_kelvin + 1.3914993 - 4.8640239E-02 * t_kelvin + \
#                   4.1764768E-05 * t_kelvin ** 2 - 1.4452093E-08 * math.pow(t_kelvin, 3) + \
#                   6.5459673 * math.log(t_kelvin)
#     return math.exp(ln_p_ws)
#
# def _d_ln_p_ws(db_temp):
#     """Helper function for the derivative of the log of saturation vapor pressure.
#     # originally implmented in Ladybug
#     # https: // www.ladybug.tools / ladybug / docs / _modules / ladybug / psychrometrics.html
#
#     Args:
#         db_temp : Dry bulb temperature (C).
#
#     Returns:
#         Derivative of natural log of vapor pressure of saturated air in Pa.
#     """
#     T = db_temp + 273.15  # temperature in kelvin
#     if db_temp <= 0.:
#         d_ln_p_ws = 5.6745359E+03 / math.pow(T, 2) - 9.677843E-03 + 2 * \
#             6.2215701E-07 * T + 3 * 2.0747825E-09 * math.pow(T, 2) - 4 * \
#             9.484024E-13 * math.pow(T, 3) + 4.1635019 / T
#     else:
#         d_ln_p_ws = 5.8002206E+03 / math.pow(T, 2) - 4.8640239E-02 + 2 * \
#             4.1764768E-05 * T - 3 * 1.4452093E-08 * math.pow(T, 2) + \
#             6.5459673 / T
#     return d_ln_p_ws
#
# def dew_pt_dbt_rh(dbt, relhum):
#     # originally implmented in Ladybug
#     # https: // www.ladybug.tools / ladybug / docs / _modules / ladybug / psychrometrics.html
#     p_ws = saturation_vapor_pressure(dbt + 273.15)  # saturation pressure
#     p_w = p_ws * (relhum / 100)  # partial pressure
#
#     # We use NR to approximate the solution.
#     td = dbt  # First guess for dew point temperature (solved for iteratively)
#     try:
#         ln_vp = math.log(p_w)  # partial pressure of water vapor in moist air
#     except ValueError:  # relative humidity of 0, return absolute zero
#         return -273.15
#
#     index = 1
#     while True:
#         td_iter = td  # td used in NR calculation
#         ln_vp_iter = math.log(saturation_vapor_pressure(td_iter + 273.15))
#         d_ln_vp = _d_ln_p_ws(td_iter)  # Derivative of function, calculated analytically
#         td = td_iter - (ln_vp_iter - ln_vp) / d_ln_vp  # New estimate
#
#         if ((math.fabs(td - td_iter) <= 0.1)):  # 0.1 is degree C tolerance
#             break  # solution has been found
#         if (index > 100):  # 100 is the max iterations (usually only 3-5 are needed)
#             break  # max number of iterations has been exceeded
#         index = index + 1
#
#     return min(td, dbt)
#
# def wet_bulb_from_db_rh(db_temp, rel_humid, b_press=101325):
#     """Wet bulb temperature (C) from air temperature (C) and relative humidity (%).
#
#     Args:
#         db_temp: Dry bulb temperature (C).
#         rel_humid: Relative humidity (%).
#         b_press: Air pressure (Pa). Default is pressure at sea level (101325 Pa).
#
#     Returns:
#         Wet bulb temperature (C).
#
#     Note:
#         [1] ASHRAE Handbook - Fundamentals (2017) ch. 1 eqn 33 and 35
#
#         [2] Meyer et al., (2019). PsychroLib: a library of psychrometric
#         functions to calculate thermodynamic properties of air. Journal of
#         Open Source Software, 4(33), 1137, https://doi.org/10.21105/joss.01137
#         https://github.com/psychrometrics/psychrolib/blob/master/src/python/psychrolib.py
#     """
#     humid_ratio = humid_ratio_from_db_rh(db_temp, rel_humid, b_press)
#     # Initial guesses
#     wb_temp_sup = db_temp
#     wb_temp_inf = dew_point_from_db_rh(db_temp, rel_humid)
#     wb_temp = (wb_temp_inf + wb_temp_sup) / 2
#
#     index = 1
#     while ((wb_temp_sup - wb_temp_inf) > 0.1):  # 0.1 is degree C tolerance
#         # Compute humidity ratio at temperature Tstar
#         w_star = humid_ratio_from_db_wb(db_temp, wb_temp, b_press)
#         # Get new bounds
#         if w_star > humid_ratio:
#             wb_temp_sup = wb_temp
#         else:
#             wb_temp_inf = wb_temp
#         # New guess of wet bulb temperature
#         wb_temp = (wb_temp_sup + wb_temp_inf) / 2
#         if index >= 100:
#             break  # 100 is the max iterations (usually only 3-5 are needed)
#         index = index + 1
#     return wb_temp