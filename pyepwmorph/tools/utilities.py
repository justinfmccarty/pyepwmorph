"""
General utility scripts used throughout the package
"""
import calendar
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"

__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

#: Variables required from a climate model for every supported morph.
CMIP6_VARIABLES = ['tas', 'tasmax', 'tasmin', 'clt', 'psl', 'pr', 'huss', 'vas', 'uas', 'rsds']

#: Shared Socioeconomic Pathway experiment IDs supported by the package.
CMIP6_SCENARIOS = ['ssp126', 'ssp245', 'ssp370', 'ssp585']


def min_max_mean_means(timeseries, first_resample="D", second_resample="ME"):
    """
    Given a timeseries, resample to the max, the min, and the mean along a dimension.
        Then resample again at a coarser resolution to get the mean
    Parameters
    ----------
    timeseries : pd.Series with a datetime index
        a timeseries, likely annual hourly (8760,), of values that you want statistics for
    first_resample : string (default: 'D')
        the first resample resolution to operate at
    second_resample : string (default: 'ME')
        the second resample resolution to operate at

    Returns
    -------
    tuple of three pd.Series
        the max, min, and mean

    Examples
    --------
    >>> min_max_mean_means(data_series, first_resample="D", second_resample="ME")
    """
    series_max = timeseries.resample(first_resample).max().resample(second_resample).mean().reset_index(drop=True)
    series_min = timeseries.resample(first_resample).min().resample(second_resample).mean().reset_index(drop=True)
    series_mean = timeseries.resample(first_resample).mean().resample(second_resample).mean().reset_index(drop=True)
    return series_max, series_min, series_mean


def absolute_delta(future, historical):
    """
    Calculate the absolute change between a future and a historical value.

    Parameters
    ----------
    future : numerical
        future value(s)
    historical : numerical
        historical value(s)

    Returns
    -------
    numerical
        ``future - historical``, in the units of the inputs

    Examples
    --------
    >>> absolute_delta(np.array([6,7,8]),np.array([10,4,9]))
    """
    return future - historical


def relative_delta(future, historical):
    """
    Calculate the relative change between a future and a historical value.

    Note that this returns a *ratio*, not a percentage: an unchanged value
    gives 1.0 and a 20% increase gives 1.2.  Morphing stretch factors use
    this ratio directly.

    Parameters
    ----------
    future : numerical
        future value(s)
    historical : numerical
        historical value(s)

    Returns
    -------
    numerical
        ``future / historical``

    Examples
    --------
    >>> relative_delta(np.array([6,7,8]),np.array([10,4,9]))
    """
    return future / historical


def pandas_slice_year(data, start_year, end_year):
    """
    Slice a datetime-indexed Series to an inclusive range of years.

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
    pandas.Series
        the subset of *data* falling inside the year range

    Examples
    --------
    >>> import pandas as pd
    >>> import numpy as np
    >>> baseline_period = (1960,1990)
    >>> future_period = (2050,2060)
    >>> values = np.linspace(0,1799,150*12,dtype=int)
    >>> all_months = pd.date_range("01 January 1951",end="01 January 2101",freq='MS')
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


def as_array(data, length):
    """
    Coerce list/ndarray/Series input into a flat float array of a known length.

    Parameters
    ----------
    data : list, np.ndarray, or pd.Series
        the values to coerce
    length : int
        the number of values that *data* must contain

    Returns
    -------
    np.ndarray
        a one-dimensional float array of *length* values

    Raises
    ------
    ValueError
        If *data* does not hold exactly *length* values.
    """
    values = np.asarray(data, dtype=float).ravel()
    if values.size != length:
        raise ValueError(f"Expected {length} values, got {values.size}")
    return values


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
    return dict(zip(range(1, 13), as_array(data, 12).tolist()))


def zip_day_data(data):
    """
    creates an array (365,) int (1-365) and zips it to an input array of data

    Parameters
    ----------
    data : list, np.ndarray, or pd.Series
        an array of data with one value for each day of the year

    Returns
    -------
    dict
        keys are the days of the year in int form with the data set to each value

    Examples
    --------
    >>> zip_day_data(np.ones(365))
    """
    return dict(zip(range(1, 366), as_array(data, 365).tolist()))


def month_factors(index, monthly_values):
    """
    Broadcast twelve monthly values onto every timestamp of a datetime index.

    This replaces the per-row lookups that the morphing procedures used to do
    with a single vectorised take.

    Parameters
    ----------
    index : pd.DatetimeIndex
        the index to broadcast onto, typically an annual hourly (8760,) index
    monthly_values : list, np.ndarray, or pd.Series
        twelve values ordered January to December

    Returns
    -------
    np.ndarray
        an array the same length as *index*
    """
    values = as_array(monthly_values, 12)
    return values[np.asarray(index.month) - 1]


def day_factors(index, daily_values):
    """
    Broadcast 365 daily values onto every timestamp of a datetime index.

    Parameters
    ----------
    index : pd.DatetimeIndex
        the index to broadcast onto, typically an annual hourly (8760,) index
    daily_values : list, np.ndarray, or pd.Series
        365 values ordered by day of year

    Returns
    -------
    np.ndarray
        an array the same length as *index*
    """
    values = as_array(daily_values, 365)
    return values[np.asarray(index.dayofyear) - 1]


def uas_vas_2_sfcwind(uas, vas, calm_wind_thresh=0.5, out='SPD'):
    """
    Converts the UAS (eastward) and VAS (northward) wind vectors into surface wind speed
        adapated from xclim[1] to not take xarrays
        [1]https://xclim.readthedocs.io/en/stable/_modules/xclim/indices/_conversion.html#uas_vas_2_sfcwind

    Parameters
    ----------
    uas : numerical
        Eastward wind activity
    vas : numerical
        Northward wind activity
    calm_wind_thresh : float (Default: 0.5)
        The threshold under which winds are considered "calm" and for which the direction
            is set to 0. On the Beaufort scale, calm winds are defined as < 0.5 m/s.
    out : string (Default: 'SPD')
        control statement for directing the output, either wind speed ('SPD') or wind direction ('DIR')
            we assume direction to never change

    Returns
    -------
    float
        calculated wind speed (m s-1) or wind direction (degrees)
            Direction from which the wind blows, following the meteorological convention where
            360 stands for North and 0 for calm winds.
    """
    # Wind speed is the hypotenuse of "uas" and "vas"
    wind = np.hypot(uas, vas)

    if out == 'SPD':
        return wind

    # Calculate the angle
    windfromdir_math = np.degrees(np.arctan2(vas, uas))

    # Convert the angle from the mathematical standard to the meteorological standard
    windfromdir = (270 - windfromdir_math) % 360.0

    # According to the meteorological standard, calm winds must have a direction of 0 degrees
    # while northerly winds have a direction of 360 degrees
    # On the Beaufort scale, calm winds are defined as < 0.5 m/s
    windfromdir = np.where(np.round(windfromdir) == 0, 360, windfromdir)
    return np.where(wind < calm_wind_thresh, 0, windfromdir)


def ts_8760(year=2023, tz=None):
    """
    Uses pandas to create an annual hourly datetime series with or without timezone

    Leap years are handled by dropping 29 February so the index is always
    8760 entries long.

    Parameters
    ----------
    year : int (Default: 2023)
        the year for your datetime index
    tz : str or datetime.tzinfo (Default: None)
        a timezone to localise the index to.  Use a fixed UTC offset rather
        than a named zone to keep the index free of daylight saving jumps.

    Returns
    -------
    pd.DatetimeIndex
        datetime index for hourly annual
    """
    index = pd.date_range(
        start=f"{year}-01-01 00:00", end=f"{year}-12-31 23:00", freq="h", tz=tz,
    )
    if calendar.isleap(year):
        index = index[~((index.month == 2) & (index.day == 29))]
    return index


def calc_period(year, period):
    """
    Centre a period of the same length as *period* on *year*.

    Parameters
    ----------
    year : int
        the target year to centre the period on
    period : tuple (int, int)
        the baseline period whose length should be reused

    Returns
    -------
    tuple (int, int)
        the start and end year of the target period
    """
    extent = int(period[1]) - int(period[0])
    return int(year - (extent / 2)), int(year + (extent / 2))


def available_models(scenarios=None, variables=None):
    """
    List the CMIP6 source IDs that carry every required variable in every scenario.

    Parameters
    ----------
    scenarios : list of str or None
        Experiment IDs to check.  Defaults to the four supported SSPs.
    variables : list of str or None
        Variable IDs that a model must provide.  Defaults to the full set the
        package can morph with.

    Returns
    -------
    list of str
        sorted model source IDs common to all requested scenarios

    Examples
    --------
    >>> available_models()
    """
    import intake

    scenarios = list(scenarios) if scenarios else list(CMIP6_SCENARIOS)
    variables = list(variables) if variables else list(CMIP6_VARIABLES)

    esm_data = intake.open_esm_datastore("https://storage.googleapis.com/cmip6/pangeo-cmip6.json")
    catalog = esm_data.df

    monthly = catalog[
        (catalog['activity_id'] == 'ScenarioMIP')
        & (catalog['member_id'] == 'r1i1p1f1')
        & (catalog['table_id'] == 'Amon')
    ]

    model_sets = []
    for scenario in scenarios:
        scenario_rows = monthly[monthly['experiment_id'] == scenario]
        complete = {
            source
            for source, rows in scenario_rows.groupby('source_id')
            if set(variables).issubset(set(rows['variable_id']))
        }
        model_sets.append(complete)

    common_models = sorted(set.intersection(*model_sets)) if model_sets else []
    logger.info("Models common across %s: %s", scenarios, common_models)
    return common_models
