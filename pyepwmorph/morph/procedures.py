"""
Container for all of the individual morphing calculations which can be traced back to:

    Belcher S, Hacker J and Powell D 2005 Building Services Engineering Research and Technology
        26 49–61 ISSN 0143-6244 publisher: SAGE Publications Ltd STM URL https://doi.org/10.1191/0143624405bt112oa
    Jentsch M F, James P A B, Bourikas L and Bahaj A S 2013 Renewable Energy
        55 514–524 ISSN 0960-1481 URL https://www.sciencedirect.com/science/article/pii/S0960148113000232

"""
import numpy as np
import pandas as pd

from pyepwmorph.tools import psychrometrics as psych
from pyepwmorph.tools import solar as morph_solar_utils
from pyepwmorph.tools import utilities as morph_utils

#: Solar altitude (degrees) below which direct normal irradiance is set to zero.
#: Dividing the horizontal beam component by sin(altitude) is numerically
#: unstable near the horizon, so the low sun hours are zeroed instead.
MIN_SOLAR_ALTITUDE = 2.0

#: Solar constant (W/m2), the hard ceiling for direct normal irradiance.
SOLAR_CONSTANT = 1367.0


def _index_of(*candidates):
    """Return the first DatetimeIndex found among the candidate series."""
    for candidate in candidates:
        index = getattr(candidate, "index", None)
        if isinstance(index, pd.DatetimeIndex):
            return index
    return None


def _year_of(index):
    """Return the year of a DatetimeIndex, or the default solar year."""
    if index is None or len(index) == 0:
        return morph_solar_utils.DEFAULT_SOLAR_YEAR
    return int(index[0].year)


def _as_series(values, index, name, decimals=2):
    """Round an array and wrap it in a named Series carrying *index*."""
    rounded = np.round(np.asarray(values, dtype=float), decimals)
    return pd.Series(rounded, index=index, name=name)


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
        the scaling factor to be applied, in the case of temperature it is -
         (absolute_delta of tasmax for a temporal slice - absolute_delta of tasmin for a temporal slice)
         ----------------------------------------------------------------------------
         (present day tasmax for a temporal slice - present day tasmin for a temporal slice)
    temporal_mean : float
        the mean of the present day values for a given temporal slice (typically monthly)

    Returns
    -------
    float
        the morphed value

    Examples
    --------
    >>> shift_stretch(1.2, 2.4, 1.7, 4.4)
    """

    return present + delta + scaling_factor * (present - temporal_mean)


def morph_dbt_year(present_dbt, future_tas, baseline_tas, future_tasmax, baseline_tasmax, future_tasmin,
                   baseline_tasmin):
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
    >>> morph_dbt_year(present_dbt, future_tas, baseline_tas, future_tasmax, baseline_tasmax, future_tasmin, baseline_tasmin)
    """
    index = present_dbt.index

    dbt_max_mean, dbt_min_mean, dbt_mean = (
        morph_utils.as_array(series, 12) for series in morph_utils.min_max_mean_means(present_dbt)
    )
    tas_delta = morph_utils.absolute_delta(
        morph_utils.as_array(future_tas, 12), morph_utils.as_array(baseline_tas, 12),
    )
    tasmin_delta = morph_utils.absolute_delta(
        morph_utils.as_array(future_tasmin, 12), morph_utils.as_array(baseline_tasmin, 12),
    )
    tasmax_delta = morph_utils.absolute_delta(
        morph_utils.as_array(future_tasmax, 12), morph_utils.as_array(baseline_tasmax, 12),
    )

    diurnal_range = dbt_max_mean - dbt_min_mean
    monthly_scale = np.divide(
        tasmax_delta - tasmin_delta, diurnal_range,
        out=np.zeros_like(diurnal_range), where=diurnal_range != 0,
    )

    delta = morph_utils.month_factors(index, tas_delta)
    scale = morph_utils.month_factors(index, monthly_scale)
    mean = morph_utils.month_factors(index, dbt_mean)

    morphed_dbt = shift_stretch(present_dbt.to_numpy(dtype=float), delta, scale, mean)
    return _as_series(morphed_dbt, index, "drybulb_C")


def morph_relhum(present_relhum, present_psl, present_dbt, future_psl, future_dbt, future_huss, baseline_huss):
    """
    Relative humidity morph is a stretch applied in specific humidity space

    The present day state is converted to specific humidity, stretched by the
    ratio of future to baseline modelled specific humidity, and converted back
    to relative humidity against the morphed temperature and pressure.

    Parameters
    ----------
    present_relhum : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day relative humidity as percentage (75.1)
            and a datetime index (this typically comes from the EPW)

    present_psl : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day atmospheric pressure in Pa

    present_dbt : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day drybulb temperature in C

    future_psl : array_like
        an hourly annual (8760,) array of the morphed atmospheric pressure in Pa

    future_dbt : array_like
        an hourly annual (8760,) array of the morphed drybulb temperature in C

    future_huss : pd.Series
        an annual monthly climatology (12,) pandas series with the future specific humidity

    baseline_huss : pd.Series
        an annual monthly climatology (12,) pandas series with the baseline specific humidity

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    index = present_relhum.index

    # a ratio, where an unchanged specific humidity gives 1.0
    huss_ratio = morph_utils.relative_delta(
        morph_utils.as_array(future_huss, 12), morph_utils.as_array(baseline_huss, 12),
    )
    stretch_factor = morph_utils.month_factors(index, huss_ratio)

    present_humid_ratio = psych.humid_ratio_from_db_rh(
        present_dbt.to_numpy(dtype=float),
        present_relhum.to_numpy(dtype=float),
        present_psl.to_numpy(dtype=float),
    )
    present_spec_humid = psych.specific_humidity_from_humid_ratio(present_humid_ratio)

    # specific humidity has to stay strictly inside (0, 1) to be invertible
    future_spec_humid = np.clip(stretch(present_spec_humid, stretch_factor), 1e-9, 1 - 1e-9)
    future_humid_ratio = psych.humid_ratio_from_specific_humidity(future_spec_humid)

    morphed_relhum = psych.rel_humid_from_db_hr(
        np.asarray(future_dbt, dtype=float),
        future_humid_ratio,
        np.asarray(future_psl, dtype=float),
    )
    return _as_series(np.clip(morphed_relhum, 1, 100), index, "relhum_percent")


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
    index = present_psl.index
    psl_delta = morph_utils.absolute_delta(
        morph_utils.as_array(future_psl, 12), morph_utils.as_array(baseline_psl, 12),
    )
    psl_change = morph_utils.month_factors(index, psl_delta)

    morphed_psl = shift(present_psl.to_numpy(dtype=float), psl_change)
    return pd.Series(np.rint(morphed_psl).astype(int), index=index, name="atmos_Pa")


def morph_dewpt(future_dbt, future_relhm):
    """
    Recalculate the dew point from the new DBT and relative humidity

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
    index = _index_of(future_dbt, future_relhm)
    morphed_dewpt = psych.dew_point_from_db_rh(
        np.asarray(future_dbt, dtype=float),
        np.clip(np.asarray(future_relhm, dtype=float), 1, 100),
    )
    return _as_series(morphed_dewpt, index, "dewpoint_C")


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
    index = present_wspd.index

    fut_spd = morph_utils.uas_vas_2_sfcwind(
        morph_utils.as_array(future_uas, 12), morph_utils.as_array(future_vas, 12),
    )
    baseline_spd = morph_utils.uas_vas_2_sfcwind(
        morph_utils.as_array(baseline_uas, 12), morph_utils.as_array(baseline_vas, 12),
    )

    # a ratio, where an unchanged wind speed gives 1.0
    wspd_ratio = morph_utils.relative_delta(fut_spd, baseline_spd)
    scale_factor_wspd = morph_utils.month_factors(index, wspd_ratio)

    morphed_wspd = stretch(present_wspd.to_numpy(dtype=float), scale_factor_wspd)
    return _as_series(np.clip(morphed_wspd, 0, None), index, "windspd_ms")


def morph_glohor(present_glohor, future_glohor, baseline_glohor):
    """
    Global horizontal radiation morph requires a stretch

    Parameters
    ----------
    present_glohor : pd.Series with datetimeindex
        an hourly annual (8760,) pandas series with the present day global horizontal radiation (Wh/m2)
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
    index = present_glohor.index

    # model data is a monthly mean flux (W/m2), so compare it against the
    # mean hourly irradiance of each month in the EPW
    month_hours = present_glohor.resample("ME").size().to_numpy(dtype=float)
    month_total = present_glohor.resample("ME").sum().to_numpy(dtype=float)
    month_mean = np.divide(
        month_total, month_hours,
        out=np.zeros(12, dtype=float), where=month_hours != 0,
    )

    delta_glohor = morph_utils.absolute_delta(
        morph_utils.as_array(future_glohor, 12), morph_utils.as_array(baseline_glohor, 12),
    )
    shift_factors = np.divide(
        delta_glohor, month_mean,
        out=np.zeros(12, dtype=float), where=month_mean != 0,
    ) + 1.0

    morphed_glohor = stretch(
        present_glohor.to_numpy(dtype=float), morph_utils.month_factors(index, shift_factors),
    )
    return _as_series(np.clip(morphed_glohor, 0, None), index, "glohorrad_Whm2")


def calc_difhor(longitude, latitude, utc_offset, morphed_glohor, present_exthor):
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
        latitude (-90 to 90)

    utc_offset : float
        the difference in hours between Coordinated Universal Time (UTC) and local standard time

    morphed_glohor : array_like
        an hourly annual (8760,) series with the morphed global horizontal radiation (Wh/m2)

    present_exthor : pd.Series
        an hourly annual (8760,) pandas series with the present day extraterrestrial horizontal radiation

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    index = _index_of(present_exthor, morphed_glohor)
    solar_df = morph_solar_utils.solar_geometry(longitude, latitude, utc_offset, year=_year_of(index))
    solar_alt = solar_df['elevation'].to_numpy(dtype=float)

    glohor = np.asarray(morphed_glohor, dtype=float)
    hourly_clearness, daily_clearness = morph_solar_utils.calc_clearness(
        glohor, present_exthor, index=solar_df.index,
    )
    daily = morph_utils.day_factors(solar_df.index, list(daily_clearness.values()))
    persistence = morph_solar_utils.persistence(
        hourly_clearness,
        morph_solar_utils.build_sunrise_sunset(longitude, latitude, utc_offset, year=_year_of(index)),
    )

    exponent = (
        -5.38
        + 6.63 * hourly_clearness
        + 0.006 * solar_df['local_solar_time'].to_numpy(dtype=float)
        - 0.007 * solar_alt
        + 1.75 * daily
        + 1.31 * persistence
    )
    # the logistic gives the diffuse fraction, which cannot leave [0, 1]
    diffuse_fraction = np.clip(1.0 / (1.0 + np.exp(exponent)), 0.0, 1.0)

    morphed_difhor = np.nan_to_num(glohor * diffuse_fraction, nan=0.0)
    return _as_series(np.clip(morphed_difhor, 0, glohor), index, "difhorrad_Whm2")


def calc_dirnor(morphed_glohor, morphed_difhor, longitude, latitude, utc_offset,
                extraterrestrial_dirnor=None, min_solar_altitude=MIN_SOLAR_ALTITUDE):
    """
    Direct normal radiation morph is a recalculation from the morphed global and diffuse horizontal

    The beam component on the horizontal is projected onto the normal with the
    sine rule.  That projection is unbounded as the sun approaches the horizon,
    so hours below *min_solar_altitude* are set to zero and the result is capped
    at the extraterrestrial direct normal irradiance.

    Parameters
    ----------
    morphed_glohor : array_like
        an hourly annual (8760,) series with the morphed global horizontal radiation (Wh/m2)

    morphed_difhor : array_like
        an hourly annual (8760,) series with the morphed diffuse horizontal radiation (Wh/m2)

    longitude : float
        longitude (-180 to 180)

    latitude : float
        latitude (-90 to 90)

    utc_offset : float
        the difference in hours between Coordinated Universal Time (UTC) and local standard time

    extraterrestrial_dirnor : array_like or None
        an hourly annual (8760,) series of extraterrestrial direct normal radiation, used as the
            physical ceiling.  This is the ``extdirrad_Whm2`` column of the EPW.  When omitted the
            solar constant is used instead.

    min_solar_altitude : float
        solar altitude in degrees below which the direct normal radiation is set to zero

    Returns
    -------
    pd.Series
        a pandas Series of the same shape as present day input
    """
    index = _index_of(extraterrestrial_dirnor, morphed_glohor, morphed_difhor)
    solar_df = morph_solar_utils.solar_geometry(longitude, latitude, utc_offset, year=_year_of(index))
    solar_alt = solar_df['elevation'].to_numpy(dtype=float)

    glohor = np.asarray(morphed_glohor, dtype=float)
    difhor = np.asarray(morphed_difhor, dtype=float)
    beam_horizontal = glohor - difhor

    sin_alt = np.sin(np.radians(solar_alt))
    usable = (solar_alt >= min_solar_altitude) & (beam_horizontal > 0)
    dirnor = np.divide(beam_horizontal, sin_alt, out=np.zeros_like(beam_horizontal), where=usable)

    if extraterrestrial_dirnor is None:
        ceiling = SOLAR_CONSTANT
    else:
        ceiling = np.asarray(extraterrestrial_dirnor, dtype=float)
    dirnor = np.clip(np.nan_to_num(dirnor, nan=0.0, posinf=0.0, neginf=0.0), 0, ceiling)

    return _as_series(dirnor, index, "dirnorrad_Whm2")


def calc_tsc(present_tsc, future_clt, baseline_clt):
    """
    Total sky cover requires a shift

    CMIP6 reports cloud area fraction (clt) as a percentage, while the EPW
    records sky cover in tenths, so the modelled change is divided by ten.

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
    index = present_tsc.index
    clt_delta = morph_utils.absolute_delta(
        morph_utils.as_array(future_clt, 12), morph_utils.as_array(baseline_clt, 12),
    ) / 10.0
    clt_change = morph_utils.month_factors(index, clt_delta)

    morphed_tsc = np.clip(shift(present_tsc.to_numpy(dtype=float), clt_change), 0, 10)
    return pd.Series(np.rint(morphed_tsc).astype(int), index=index, name="totskycvr_tenths")


def calc_osc(morphed_tsc, present_osc, present_tsc):
    """
    Opaque sky cover is derived using the present day ratio of opaque to total multiplied by morphed total

    Parameters
    ----------
    morphed_tsc : array_like
        an hourly annual (8760,) series with the morphed total sky cover in tenths

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
    index = _index_of(present_osc, present_tsc, morphed_tsc)
    opaque = np.asarray(present_osc, dtype=float)
    total = np.asarray(present_tsc, dtype=float)

    osc_tsc_ratio = np.divide(opaque, total, out=np.zeros_like(opaque), where=total != 0)
    morphed_osc = np.clip(osc_tsc_ratio * np.asarray(morphed_tsc, dtype=float), 0, 10)
    return pd.Series(np.rint(morphed_osc).astype(int), index=index, name="opaqskycvr_tenths")
