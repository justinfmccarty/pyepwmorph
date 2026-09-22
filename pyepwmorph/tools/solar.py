"""
General utility scripts used throughout the package specifically for dealing with solar positions
"""
import datetime

import numpy as np
import pandas as pd
import pvlib

from pyepwmorph.tools import utilities as morph_utils

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"

__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

#: Year used to build solar geometry when the caller does not supply one.
DEFAULT_SOLAR_YEAR = 2023


def fixed_offset(utc_offset):
    """
    Build a fixed-offset timezone from an EPW UTC offset.

    EPW files are always recorded against local *standard* time, so a fixed
    offset is the correct timezone.  Using a named IANA zone instead would
    introduce daylight saving jumps that the weather data does not contain.

    Parameters
    ----------
    utc_offset : float
        the difference in hours between Coordinated Universal Time and local
        standard time, as given on the EPW LOCATION line

    Returns
    -------
    datetime.timezone
    """
    return datetime.timezone(datetime.timedelta(hours=float(utc_offset)))


def calc_local_time_meridian(utc_offset):
    """
    The local standard time meridian, measured in degrees, which runs through the center of each time zone

    Parameters
    ----------
    utc_offset : float
        the difference in hours and minutes between Coordinated Universal Time (UTC) and local solar time

    Returns
    -------
    float
        local time meridian in degrees
    """
    # requires the utc offset for local time zone
    # https://en.wikipedia.org/wiki/List_of_UTC_time_offsets
    return 15 * utc_offset


def calc_time_correction(longitude, local_time_meridian, equation_of_time):
    """
    accounts for the variation of the Local Solar Time (LST) within a given time zone due to the
            longitude variations within the time zone

    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)
    local_time_meridian : float
        the differences in hours from Greenwich Mean Time multiplied by 15 degrees per hour
    equation_of_time : float
        an empirical equation that corrects for the eccentricity of the Earth's orbit and the Earth's axial tilt

    Returns
    -------
    float
    """
    return 4 * (longitude - local_time_meridian) + equation_of_time


def calc_local_solar_time(local_time, time_correction):
    """
    the time according to the position of the sun in the sky relative to one specific location on the
        ground

    Parameters
    ----------
    local_time : float
         Local time (LT) usually varies from LST because of the eccentricity of the Earth's orbit, and because
            of human adjustments such as time zones and daylight saving.
    time_correction : float
        accounts for the variation of the Local Solar Time (LST) within a given time zone due to the
            longitude variations within the time zone

    Returns
    -------
    float
    """
    return local_time + (time_correction / 60)


def solar_geometry(longitude, latitude, utc_offset, year=DEFAULT_SOLAR_YEAR):
    """
    creates a pandas Dataframe object contianing (for each hour of the year) various important solar
        position parameters

    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)
    latitude : float
        latitude (-90 to 90)
    utc_offset : float
        the difference in hours between Coordinated Universal Time (UTC) and local standard time
    year : int
        the year to build the solar geometry for, normally the year of the EPW data

    Returns
    -------
    pd.DataFrame
        dataframe indexed by a timezone datetime index for each hour of the year with columns for various solar
            position parameters
    """
    times = morph_utils.ts_8760(year=year, tz=fixed_offset(utc_offset))
    solar_df = pvlib.solarposition.get_solarposition(times, latitude, longitude)

    day_of_year = times.dayofyear.to_numpy()
    solar_df['hour'] = times.hour
    solar_df['doy'] = day_of_year
    solar_df['equation_of_time'] = pvlib.solarposition.equation_of_time_spencer71(day_of_year)
    solar_df['local_time_meridian'] = calc_local_time_meridian(utc_offset)
    solar_df['time_correction'] = calc_time_correction(
        longitude, solar_df['local_time_meridian'], solar_df['equation_of_time'],
    )
    solar_df['local_solar_time'] = calc_local_solar_time(
        solar_df['hour'], solar_df['time_correction'],
    )
    return solar_df


def calc_solar_alt(zenith):
    """
    calculates solar altitude from the zenith

    Parameters
    ----------
    zenith : float
        solar zenith

    Returns
    -------
    float
    """
    return 90 - zenith


def calc_clearness(glohor, exthor, index=None):
    """
    calculates clearness for each hour and for each day and output them both as annual hourly timeseries

    Parameters
    ----------
    glohor : list, pd.Series or np.ndarray
        global horizontal radiation
    exthor : list, pd.Series or np.ndarray
        extraterrestrial horizontal radiation
    index : pd.DatetimeIndex or None
        the annual hourly index the data belongs to.  Defaults to a generic
        8760 index, which is enough to group the hours into days.

    Returns
    -------
    tuple
        an (8760,) array of hourly clearness and a dict of daily clearness
            keyed by day of year
    """
    ghi = np.asarray(glohor, dtype=float).ravel()
    eth = np.asarray(exthor, dtype=float).ravel()

    hourly = np.divide(ghi, eth, out=np.zeros_like(ghi), where=eth != 0)

    if index is None:
        index = morph_utils.ts_8760()
    daily_totals = pd.DataFrame({'glohor': ghi, 'exthor': eth}, index=index).resample('D').sum()
    daily_ghi = daily_totals['glohor'].to_numpy()
    daily_eth = daily_totals['exthor'].to_numpy()
    daily = np.divide(daily_ghi, daily_eth, out=np.zeros_like(daily_ghi), where=daily_eth != 0)

    return hourly, morph_utils.zip_day_data(daily)


def build_sunrise_sunset(longitude, latitude, utc_offset=0, year=DEFAULT_SOLAR_YEAR):
    """
    creates an annual hourly series in which sunrise and sunset hours are indicated as int values
        specifcally for use in the persistence calcuation

    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)
    latitude : float
        latitude (-90 to 90)
    utc_offset : float
        the difference in hours between Coordinated Universal Time (UTC) and local standard time
    year : int
        the year to build the series for, normally the year of the EPW data

    Returns
    -------
    np.ndarray
        an array (8760,) in which sunrise is indicated as value 2, sunset as 3, the first hour of the
            year as 1, the last hour of the year as 4, and all else as 0
    """
    times = morph_utils.ts_8760(year=year, tz=fixed_offset(utc_offset))
    rise_set = pvlib.solarposition.sun_rise_set_transit_spa(times, latitude, longitude)

    hours = np.asarray(times.hour)
    # Polar day and polar night give NaT, which can never match an hour.
    sunrise_hour = rise_set['sunrise'].dt.hour.fillna(-1).to_numpy()
    sunset_hour = rise_set['sunset'].dt.hour.fillna(-1).to_numpy()

    sunrise_sunset = np.where(hours == sunrise_hour, 2, 0) + np.where(hours == sunset_hour, 3, 0)
    # first hour is keyed to 1
    sunrise_sunset[0] = 1
    # last hour is keyed to 4
    sunrise_sunset[-1] = 4
    return sunrise_sunset


def persistence(hourly_clearness, sunrise_sunset):
    """
    get the mean of clearness for the previous and next hour to enter as persistence of clearness for use
        in calculating diffuse horizontal radiation

    Sunrise hours take the following hour, sunset hours take the preceding
    hour, and the first and last hours of the year take their own value.

    Parameters
    ----------
    hourly_clearness : pd.Series, np.ndarray, or list
        an (8760,) array of hourly clearness
    sunrise_sunset : np.ndarray
        an array (8760,) in which sunrise is indicated as value 2, sunset as 3, the first hour of the
                year as 1, the last hour of the year as 4, and all else as 0

    Returns
    -------
    np.ndarray
        persistence array
    """
    clearness = np.asarray(hourly_clearness, dtype=float).ravel()
    flags = np.asarray(sunrise_sunset).ravel()

    preceding = np.roll(clearness, 1)
    preceding[0] = clearness[0]
    following = np.roll(clearness, -1)
    following[-1] = clearness[-1]

    result = (preceding + following) / 2
    result = np.where(flags == 2, following, result)
    result = np.where(flags == 3, preceding, result)
    result = np.where((flags == 1) | (flags == 4), clearness, result)
    return result
