# coding=utf-8
"""
General utility scripts used throughout the package
"""
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