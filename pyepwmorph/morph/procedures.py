# coding=utf-8
"""
Container for all of the individual morphing calculations which can be traced back to:

    Belcher S, Hacker J and Powell D 2005 Building Services Engineering Research and Technology
        26 49–61 ISSN 0143-6244 publisher: SAGE Publications Ltd STM URL https://doi.org/10.1191/0143624405bt112oa
    Jentsch M F, James P A B, Bourikas L and Bahaj A S 2013 Renewable Energy
        55 514–524 ISSN 0960-1481 URL https://www.sciencedirect.com/science/article/pii/S0960148113000232

"""
import math

import numpy as np
import pandas as pd
import pvlib
from meteocalc import dew_point as calcdewpt

from pyepwmorph.tools import utilities as morph_utils
from pyepwmorph.tools import solar as morph_solar_utils
import warnings

warnings.filterwarnings("ignore")


def shift(present, delta):
    return present + delta


def stretch(present, stretch_factor):
    return present * stretch_factor


def shift_stretch(present, delta, scaling_factor, temporal_mean):
    """
    This is a combined shift and stretch that is only applied in the case of DBT but was funcationalised for formality

    Parameters
    ----------
    present : float
        the present day value
    delta : float
        the absolute change in the monthly mean value of the variable for the month (future - historical)
    scaling_factor : float
        the scaling factor to be applied, in th case of temperature it is -
         (absolute_delta of tasmax for a temporal slice - absolute_delta of tasmin for a temporal slice)
         ----------------------------------------------------------------------------
         (present dat tasmax for a tmepral slice - present dat tasmin for a tmepral slice)
    temporal_mean : float
        the mean of the present day values for a given temporal slice (typically monthly)

    Returns
    -------


    Examples
    --------
    >>> shift_stretch(1.2, 2.4, 1.7, 4.4)
    """

    return present + delta + scaling_factor * (present - temporal_mean)


def morph_dbt_year(present_dbt, future_tas, baseline_tas, future_tasmax, baseline_tasmax, future_tasmin, baseline_tasmin):
    """
    Drybulb temperature morph requires a combination of shift and stretch

    Parameters
    ----------
    present_dbt : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day drybulb temperatures 
            and a datetime index (this typically comes from the EPW)
    
    future_tas : pd.Series
        an annual monthly climatology (12,) pandas series with the future DBT values
        this is typically from assemble.calc_model_climatologies function

    baseline_tas : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline DBT values
        this is typically from assemble.calc_model_climatologies function

    future_tasmax : pd.Series
        an annual monthly climatology (12,) pandas series with the future DBT max values
        this is typically from assemble.calc_model_climatologies function

    baseline_tasmax : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline DBT max values
        this is typically from assemble.calc_model_climatologies function

    future_tasmin : pd.Series
        an annual monthly climatology (12,) pandas series with the future DBT min values
        this is typically from assemble.calc_model_climatologies function

    baseline_tasmin : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline DBT min values
        this is typically from assemble.calc_model_climatologies function
    

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input

    Examples
    --------
    >>> morph_dbt()
    """
    dbt_max_mean, dbt_min_mean, dbt_mean = morph_utils.min_max_mean_means(present_dbt)
    tas_delta = morph_utils.absolute_delta(future_tas, baseline_tas).values
    tasmin_delta = morph_utils.absolute_delta(future_tasmin, baseline_tasmin).values
    tasmax_delta = morph_utils.absolute_delta(future_tasmax, baseline_tasmax).values

    dbt_delta = morph_utils.zip_month_data(tas_delta)

    dbt_scale = (tasmax_delta - tasmin_delta) / (dbt_max_mean - dbt_min_mean)
    dbt_scale = morph_utils.zip_month_data(dbt_scale)
    dbt_mean = morph_utils.zip_month_data(dbt_mean)

    df = pd.DataFrame(present_dbt.rename("drybulb_C"))
    df['month'] = df.index.month

    morphed_dbt = df.apply(lambda x: shift_stretch(x['drybulb_C'],
                                                   dbt_delta[x['month']],
                                                   dbt_scale[x['month']],
                                                   dbt_mean[x['month']]),
                           axis=1).astype(float)
    return round(morphed_dbt, 2).rename("drybulb_C")


def morph_relhum(present_relhum, future_huss, baseline_huss):
    """
    Relative humidity morph requires a stretch

    Parameters
    ----------
    present_relhum : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day relative humidity as perecentage (75.1)
            and a datetime index (this typically comes from the EPW)

    future_huss : pd.Series
        an annual monthly climatology (12,) pandas series with the future specific humidity as perecentage (75.1)
            this is typically from assemble.calc_model_climatologies function

    baseline_huss : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline specific humidity as perecentage (75.1)
            this is typically from assemble.calc_model_climatologies function

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    # requires future_ and historical_ inputs to be monthly climatologies
    relhum_stretch = morph_utils.relative_delta(future_huss, baseline_huss).values
    relhum_change = morph_utils.zip_month_data(relhum_stretch)

    df = pd.DataFrame(present_relhum.rename("relhum_percent"))
    df['month'] = df.index.month

    morphed_relhum = df.apply(lambda x: stretch(x['relhum_percent'],
                                              relhum_change[x['month']]),
                              axis=1).astype(float)
    morphed_relhum = pd.Series(np.clip(morphed_relhum.values, 1, 100))
    return round(morphed_relhum, 2).rename("relhum_percent")


def morph_psl(present_psl, future_psl, baseline_psl):
    """
    Pressure at sea level morph requires a shift

    Parameters
    ----------
    present_psl : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day atmospheric pressure
            and a datetime index (this typically comes from the EPW)

    future_psl : pd.Series
        an annual monthly climatology (12,) pandas series with the future atmospheric pressure
            this is typically from assemble.calc_model_climatologies function

    baseline_psl : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline atmospheric pressure
            this is typically from assemble.calc_model_climatologies function

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    # requires fut_ and hist_ inputs to be monthly climatologies
    psl_delta = morph_utils.absolute_delta(future_psl, baseline_psl)
    psl_change = morph_utils.zip_month_data(psl_delta)

    df = pd.DataFrame(present_psl.rename("atmos_Pa"))
    df['month'] = df.index.month

    morphed_psl = df.apply(lambda x: shift(x['atmos_Pa'],
                                           psl_change[x['month']]),
                           axis=1).astype(float)

    return round(morphed_psl, 2).rename("atmos_Pa")


def morph_dewpt(future_dbt, future_relhm):
    """
    Recalculate the dew point from the new DBT and relative humidity using meteocalc

    Parameters
    ----------
    future_dbt : pd.Series
        an hourly annual (8760,) pandas series with the morphed drybulb temperature

    future_relhm : pd.Series
        an hourly annual (8760,) pandas series with the morphed relative humidity

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    df = pd.DataFrame({"drybulb_C": future_dbt,
                       "relhum_percent": np.clip(future_relhm, 1, 100)})
    morphed_dewpt = df.apply(lambda x: calcdewpt(x['drybulb_C'],
                                                 x['relhum_percent']),
                             axis=1).astype(float)
    return round(morphed_dewpt, 2).rename("dewpoint_C")


def morph_wspd(present_wspd, future_vas, baseline_vas, future_uas, baseline_uas):
    """
    Wind speed morph requires a stretch

    Parameters
    ----------
    present_wspd : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day windspeed in m/s
            and a datetime index (this typically comes from the EPW)

    future_vas : pd.Series
        an annual monthly climatology (12,) pandas series with the future wind VAS values
            this is typically from assemble.calc_model_climatologies function

    baseline_vas : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline wind VAS values
            this is typically from assemble.calc_model_climatologies function

    future_uas : pd.Series
        an annual monthly climatology (12,) pandas series with the future wind UAS values
            this is typically from assemble.calc_model_climatologies function

    baseline_uas : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline wind UAS values
            this is typically from assemble.calc_model_climatologies function


    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """

    fut_spd = morph_utils.uas_vas_2_sfcwind(future_vas, future_uas)
    baseline_spd = morph_utils.uas_vas_2_sfcwind(baseline_vas, baseline_uas)

    wspd_delta = morph_utils.relative_delta(fut_spd, baseline_spd)
    wspd_shift = 1 + (wspd_delta / 100)

    scale_factor_wspd = morph_utils.zip_month_data(wspd_shift)

    df = pd.DataFrame(present_wspd.rename("windspd_ms"))
    df['month'] = df.index.month

    morphed_wspd = df.apply(lambda x: stretch(x['windspd_ms'],
                                              scale_factor_wspd[x['month']]),
                            axis=1).astype(float)

    return round(morphed_wspd, 2).rename("windspd_ms")


def morph_glohor(present_glohor, future_glohor, baseline_glohor):
    """
    Global horizontal radiation morph requires a stretch

    Parameters
    ----------
    present_glohor : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day global horizontal radiation (W/m2)
            and a datetime index (this typically comes from the EPW)

    future_glohor : pd.Series
        an annual monthly climatology (12,) pandas series with the future global horizontal radiation
            values this is typically from assemble.calc_model_climatologies function

    baseline_glohor : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline global horizontal radiation
            values this is typically from assemble.calc_model_climatologies function

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    # create a series of ones for each horu of the year
    # this will be resampled later to get hours in a month
    hour_series = pd.Series(np.ones(8760))

    # copy over the timeseries index
    hour_series.index = present_glohor.index

    # resample to get hours for each month and zip into dict with int months
    month_hours = morph_utils.zip_month_data(hour_series.resample("M").sum().tolist())

    # resample glohor to get watt-hours per m2 per month
    month_glohor = morph_utils.zip_month_data(present_glohor.resample('M').sum().tolist())

    # get mean glohor per month
    month_glohor_mean_list = []
    for key, value in month_hours.items():
        mean = month_glohor[key] / month_hours[key]
        month_glohor_mean_list.append(mean)
    month_glohor_mean_list = morph_utils.zip_month_data(month_glohor_mean_list)  # watt per m2

    # get glohor delta form model data
    delta_glohor = morph_utils.absolute_delta(future_glohor, baseline_glohor)
    glohor_change = morph_utils.zip_month_data(delta_glohor)

    # calculate shift factors for each month
    glohor_shift_list = []
    for key in month_glohor_mean_list:
        shift_factor = 1 + (glohor_change[key] / month_glohor_mean_list[key])
        glohor_shift_list.append(shift_factor)
    glohor_shift_factors = morph_utils.zip_month_data(glohor_shift_list)

    # set up df for lambda operation
    df = pd.DataFrame(present_glohor.rename("glohorrad_Whm2"))
    df['month'] = df.index.month

    morphed_glohor = df.apply(lambda x: stretch(x['glohorrad_Whm2'],
                                                glohor_shift_factors[x['month']]),
                              axis=1).astype(float)

    return round(morphed_glohor, 2).rename("atmos_Pa")


def calc_diffhor(longitude, latitude, utc_offset, morphed_glohor, present_exthor):
    """
    Diffuse horizontal radiation morph is a recalculation based on the morphed global horiztonal and the
        persistence method [1] from clearness
        [1] B. Ridley, J. Boland, and P. Lauret, ‘Modelling of diffuse solar fraction with multiple predictors’,
                Renewable Energy, vol. 35, no. 2, pp. 478–483, Feb. 2010, doi: 10.1016/j.renene.2009.07.018.


    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)

    latitude : float
        latitude (-180 to 180)

    utc_offset : int
        the difference in hours and minutes between Coordinated Universal Time (UTC) and local solar time


    morphed_glohor : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the morphed global horizontal radiation (W/m2)
            and a datetime index (this typically comes from the EPW)

    present_exthor : pd.Series
        an annual monthly climatology (12,) pandas series with the present extraterrestrial horizontal radiation
            values this is typically from assemble.calc_model_climatologies function

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """

    # get the solar dataframe
    solar_df = morph_solar_utils.solar_geometry(longitude, latitude, utc_offset)
    solar_df['solar_alt'] = solar_df.apply(lambda x: morph_solar_utils.calc_solar_alt(x['zenith']),
                                           axis=1)
    solar_df['glohorrad_Whm2'] = morphed_glohor.values
    solar_df['glohorrad_Whm2'] = morphed_glohor.values

    # calc clearness from morphed glohor
    hourly_clearness, daily_clearness = morph_solar_utils.calc_clearness(morphed_glohor, present_exthor)
    solar_df['hourly_clearness'] = hourly_clearness
    solar_df['daily_clearness'] = daily_clearness

    # getun sunrise and sunset for persistence
    sunrise_sunset_idx = morph_solar_utils.build_sunrise_sunset(longitude, latitude)

    # calc persistence
    solar_df['persistence'] = morph_solar_utils.persistence(hourly_clearness, sunrise_sunset_idx)
    morphed_diffhor = solar_df.apply(
        lambda x: x['glohorrad_Whm2'] * (1 / (1 + math.exp(-5.38 + 6.63 * x['hourly_clearness'] +
                                                           0.006 * x['local_solar_time'] - 0.007 *
                                                           x['solar_alt'] + 1.75 * x['daily_clearness'] +
                                                           1.31 * x['persistence']))), axis=1).fillna(0).astype(int)

    return round(morphed_diffhor, 2).rename('diffhorrad_Whm2')


def calc_dirnor(morphed_glohor, longitude, latitude, utc_offset):
    """
    Direct normal radiation morph is a recalculation based on the morphed global horizontal
        essentially a wrapper around pvlib's method
    Parameters
    ----------
    longitude : float
        longitude (-180 to 180)

    latitude : float
        latitude (-180 to 180)

    utc_offset : int
        the difference in hours and minutes between Coordinated Universal Time (UTC) and local solar time

    morphed_glohor : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the morphed global horizontal radiation (W/m2)
            and a datetime index (this typically comes from the EPW)

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    solar_df = morph_solar_utils.solar_geometry(longitude, latitude, utc_offset)
    hours = morph_utils.ts_8760()
    return pvlib.irradiance.dirint(morphed_glohor, solar_df['zenith'], hours)



def calc_tsc(present_tsc, future_clt, baseline_clt):
    """
    Total sky cover requires a stretch

    Parameters
    ----------
    present_tsc : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day total sky cover in tenths
            and a datetime index (this typically comes from the EPW)

    future_clt : pd.Series
        an annual monthly climatology (12,) pandas series with the future cloud fraction
            this is typically from assemble.calc_model_climatologies function

    baseline_clt : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline cloud fraction
            this is typically from assemble.calc_model_climatologies function

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    clt_delta = (morph_utils.absolute_delta(future_clt,baseline_clt) / 10).astype(int)
    clt_change = morph_utils.zip_month_data(clt_delta.values.tolist())

    df = pd.DataFrame(present_tsc.rename("totskycvr_tenths"))
    df['month'] = df.index.month

    morphed_tsc = df.apply(lambda x: shift(x['totskycvr_tenths'],
                                              clt_change[x['month']]),
                              axis=1).astype(float)
    morphed_tsc = pd.Series(np.clip(morphed_tsc.values, 0, 10)).astype(int)
    return round(morphed_tsc, 2).rename("totskycvr_tenths")


def calc_osc(morphed_tsc, present_osc, present_tsc):
    """
    Opaque sky cover is derived using the present day ratio of opaque to total multipled by mrophed total

    Parameters
    ----------
    morphed_tsc : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the morphed day total sky cover in tenths
            and a datetime index (this typically comes from the EPW)

    present_osc : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day opaque sky cover in tenths
            and a datetime index (this typically comes from the EPW)

    present_tsc : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day total sky cover in tenths
            and a datetime index (this typically comes from the EPW)

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    osc_tsc_ratio = np.divide(present_osc, present_tsc, out=np.zeros_like(present_osc), where=present_tsc != 0)
    return np.where(osc_tsc_ratio * morphed_tsc)

