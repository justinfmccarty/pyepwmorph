# coding=utf-8
"""
General utility scripts used throughout the package specifically for dealing with solar positions
"""
import numpy as np
import pvlib
import pandas as pd
from timezonefinder import TimezoneFinder
from pyepwmorph.tools import utilities as morph_utils
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


def calc_local_time_meridian(utc_offset):
    """
    The local standard time meridian, measured in degrees, which runs through the center of each time zone

    Parameters
    ----------
    utc_offset : int
        the difference in hours and minutes between Coordinated Universal Time (UTC) and local solar time

    Returns
    -------
    float (˚)
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
    equation_of_time : int
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


def solar_geometry(longitude, latitude, utc_offset):
    """
    creates a pandas Dataframe object contianing (for each hour of the year) various important solar
        position parameters

    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)
    latitude : float
        latitude (-180 to 180)
    utc_offset : int
        the difference in hours and minutes between Coordinated Universal Time (UTC) and local solar time

    Returns
    -------
    pd.DataFrame
        dataframe indexed by a timezone datetime index for each hour of the year with columns for various solar
            position parameters
    """

    # use timezonefinder to get the local timezone at the lat and long
    tz = TimezoneFinder().timezone_at(lng=longitude, lat=latitude)
    times = pd.date_range('2019-01-01 00:00:00', periods=8760, freq='H', tz=tz)

    # leverage pvlib to build the basic solar position dataframe
    solar_df = pvlib.solarposition.get_solarposition(times, latitude, longitude)

    # call out some extra details
    solar_df['hour'] = solar_df.index.hour
    solar_df['doy'] = solar_df.index.dayofyear

    solar_df['equation_of_time'] = solar_df.apply(lambda x: pvlib.solarposition.equation_of_time_spencer71(x['doy']),
                                                  axis=1)
    solar_df['local_time_meridian'] = solar_df.apply(lambda x: calc_local_time_meridian(utc_offset), axis=1)
    solar_df['time_correction'] = solar_df.apply(lambda x: calc_time_correction(longitude,
                                                                                x['local_time_meridian'],
                                                                                x['equation_of_time']), axis=1)
    solar_df['local_solar_time'] = solar_df.apply(lambda x: calc_local_solar_time(x['hour'],
                                                                                  x['time_correction']), axis=1)
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


def calc_clearness(glohor, exthor):
    """
    calculates clearness for each hour and for each day and output them both as annual hourly timeseries

    Parameters
    ----------
    glohor : list, pd.Series or np.ndarray
        global horizontal radiation
    exthor : list, pd.Series or np.ndarray
        extraterrestrial horizontal radiation

    Returns
    -------
    int
        clearness ratio
    """

    def divide_clearness(x, y):
        if y == 0:
            return 0
        else:
            return np.divide(x, y)

    def calc_clearness_hourly(df):
        clearness = df.apply(lambda x: divide_clearness(x['glohor'], x['exthor']), axis=1)
        return clearness.values

    def calc_clearness_daily(df):
        daily = df.resample('D').sum()
        clearness_daily = daily.apply(lambda x: divide_clearness(x['glohor'], x['exthor']), axis=1)
        return clearness_daily.values

    df = pd.DataFrame()
    df['exthor'] = exthor
    df['glohor'] = glohor
    df.set_index(morph_utils.ts_8760(), inplace=True, drop=True)

    clearness = calc_clearness_hourly(df)
    clearness_daily = calc_clearness_daily(df)

    clearness_day_list = morph_utils.zip_day_data(clearness_daily.tolist())
    return clearness, clearness_day_list


#
# def calc_rise_set(df, latitude, longitude):
#     PARENT_DIR = Path(__file__).parent.resolve()
#     assets_dir = os.path.join(PARENT_DIR, 'assets')
#
#     ts = api.load.timescale()
#     eph = api.load(os.path.join(assets_dir, 'de421.bsp'))
#
#     location = api.Topos(latitude, longitude)
#
#     year = int(df['year'][0:1].values)
#
#     t0 = ts.utc(year - 1, 12, 31, 0)
#     t1 = ts.utc(year + 1, 1, 2, 0)
#
#     t, y = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(eph, location))
#     times = pd.Series(t.utc_datetime()).rename('datetimes')
#     times = times + timedelta(hours=-8)
#     keys = pd.Series(y).rename('Rise_Set')
#     keys = pd.Series(np.where(keys == 0, 'Sunset', 'Sunrise')).rename('Rise_Set')
#     join = pd.concat([times, keys], axis=1)
#     join.set_index(join['datetimes'], inplace=True)
#     join['year'] = join['datetimes'].dt.year
#     join['month'] = join['datetimes'].dt.month
#     join['day'] = join['datetimes'].dt.day
#     join['hour'] = join['datetimes'].dt.hour
#     join['minute'] = 0
#     join = join[join['year'] == year]
#     join['Timestamp'] = join.apply(lambda row: dt.datetime(row.year, row.month, row.day, row.hour), axis=1)
#     join.set_index('Timestamp', inplace=True)
#     join_sub = pd.DataFrame(join['Rise_Set'])
#     join_sub['dtime'] = join.index
#     df['dtime'] = df.index
#     df = df.merge(join_sub, how='left', left_on='dtime', right_on='dtime')
#     df['Rise_Set'] = df['Rise_Set'].fillna('Neither')
#     df.set_index(df['dtime'], inplace=True)
#
#     return pd.Series(df['Rise_Set'].values)

def build_sunrise_sunset(longitude, latitude):
    """
    creates an annual hourly series in which sunrise and sunset hours are indicated as int values
        specifcally for use in the persistence calcuation

    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)
    latitude : float
        latitude (-180 to 180)

    Returns
    -------
    np.ndarray
        an array (8760,) in which sunrise is indivcated as value 2, sunset as 3, the first hour of the
            year as 1, the last hour of the year as 4, and all else as 0
    """
    tz = TimezoneFinder().timezone_at(lng=longitude, lat=latitude)
    times = morph_utils.ts_8760(year=2023, tz=tz)
    rise_set = pvlib.location.Location(latitude,
                                       longitude,
                                       tz=tz).get_sun_rise_set_transit(times,
                                                                       method='spa')
    sunrise = pd.Series(rise_set.index.hour == pd.to_datetime(rise_set['sunrise']).apply(lambda x: x.hour))
    sunset = pd.Series(rise_set.index.hour == pd.to_datetime(rise_set['sunset']).apply(lambda x: x.hour))

    sunrise = np.where(sunrise == True, 2, 0)
    sunset = np.where(sunset == True, 3, 0)
    # add arrays to align sunrise and sunset keyed as 2 and 3 with non values as 0
    sunrise_sunset = sunrise + sunset
    # first hour is keyed to 1
    sunrise_sunset[0] = 1
    # last hour is keyed to 4
    sunrise_sunset[-1] = 4
    return sunrise_sunset


def persistence_sunrise_sunset(hourly_clearness, sunrise_sunset, row_number):
    """
    get the mean of clearness for the previous and next hour to enter as persistence of clearness for use
        in calculating diffuse horizontal radiation. meant to be applied in a lambda function

    Parameters
    ----------
    hourly_clearness : pd.Series, np.ndarray, or list

    rise_set : np.ndarray
        an array (8760,) in which sunrise is indivcated as value 2, sunset as 3, the first hour of the
                year as 1, the last hour of the year as 4, and all else as 0

    row_number : float
        row number of the index from 0 to 8759

    Returns
    -------
    int
        persistence
    """
    if sunrise_sunset == 4:  # last hour
        return hourly_clearness[row_number]
    elif sunrise_sunset == 2:  # sunset
        return hourly_clearness[row_number + 1]
    elif sunrise_sunset == 3:  # sunset
        return hourly_clearness[row_number - 1]
    elif sunrise_sunset == 1:  # first hour
        return hourly_clearness[row_number]
    else:  # other hours
        return (hourly_clearness[row_number - 1] + hourly_clearness[row_number + 1]) / 2


def persistence(hourly_clearness, sunrise_sunset):
    """
    wrapper to calculate persistence on a whole array

    Parameters
    ----------
    hourly_clearness : pd.Series, np.ndarray, or list

    rise_set : np.ndarray
        an array (8760,) in which sunrise is indivcated as value 2, sunset as 3, the first hour of the
                year as 1, the last hour of the year as 4, and all else as 0

    Returns
    -------
    np.ndarray
        persistence array
    """
    df = pd.DataFrame({"row_number": range(0, 8760),
                       "hourly_clearness": hourly_clearness,
                       "sunrise_sunset": sunrise_sunset})
    df['persistence'] = df.apply(lambda x: persistence_sunrise_sunset(x['hourly_clearness'],
                                                                      x['sunrise_sunset'],
                                                                      x['row_number']),
                                 axis=1)
    return df['persistence'].values
