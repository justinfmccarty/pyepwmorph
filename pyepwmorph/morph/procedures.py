"""
Container for all of the individual morphing calculations which can be traced back to:

    Belcher S, Hacker J and Powell D 2005 Building Services Engineering Research and Technology
        26 49–61 ISSN 0143-6244 publisher: SAGE Publications Ltd STM URL https://doi.org/10.1191/0143624405bt112oa
    Jentsch M F, James P A B, Bourikas L and Bahaj A S 2013 Renewable Energy
        55 514–524 ISSN 0960-1481 URL https://www.sciencedirect.com/science/article/pii/S0960148113000232

"""
import calendar
import logging

import numpy as np
import pandas as pd

from pyepwmorph.tools import psychrometrics as psych
from pyepwmorph.tools import solar as morph_solar_utils
from pyepwmorph.tools import utilities as morph_utils

logger = logging.getLogger(__name__)

#: Solar altitude (degrees) below which direct normal irradiance is set to zero.
#: Dividing the horizontal beam component by sin(altitude) is numerically
#: unstable near the horizon, so the low sun hours are zeroed instead.
MIN_SOLAR_ALTITUDE = 2.0

#: Solar constant (W/m2), the hard ceiling for direct normal irradiance.
SOLAR_CONSTANT = 1367.0

#: Decimal places kept for morphed sky cover (in tenths). See ``calc_tsc``.
SKY_COVER_DECIMALS = 2

#: Stefan-Boltzmann constant (W/m2/K4).
STEFAN_BOLTZMANN = 5.670374419e-8

#: EPW missing-value marker for horizontal infrared radiation.
IR_MISSING = 9999.0


def _index_of(*candidates):
    """Return the first DatetimeIndex found among the candidate series."""
    for candidate in candidates:
        index = getattr(candidate, "index", None)
        if isinstance(index, pd.DatetimeIndex):
            return index
    return None


def _year_of(index):
    """Return a non-leap year to build solar geometry for the data in *index*.

    EPW files always hold 8760 hours with no 29 February, so their calendar
    is a non-leap year's even when the first data row says 2016. Building
    daily series for a leap year would add an empty 29 February and shift
    every later day by one, so a leap year is replaced by the year before.
    """
    if index is None or len(index) == 0:
        return morph_solar_utils.DEFAULT_SOLAR_YEAR
    year = int(index[0].year)
    return year - 1 if calendar.isleap(year) else year


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


def morph_relhum_direct(present_relhum, future_hurs, baseline_hurs):
    """Stretch relative humidity by the modelled relative-humidity ratio.

    CH2025 provides ``hurs`` directly, so the specific-humidity round trip
    used by ``morph_relhum`` is not needed.

    Parameters
    ----------
    present_relhum : pd.Series
        Hourly present-day relative humidity in percent.
    future_hurs : pd.Series
        Twelve monthly future relative-humidity values.
    baseline_hurs : pd.Series
        Twelve monthly baseline relative-humidity values.

    Returns
    -------
    pd.Series
        Morphed relative humidity, clipped to ``[1, 100]``.
    """
    index = present_relhum.index
    ratio = morph_utils.relative_delta(
        morph_utils.as_array(future_hurs, 12), morph_utils.as_array(baseline_hurs, 12),
    )
    morphed = stretch(present_relhum.to_numpy(dtype=float), morph_utils.month_factors(index, ratio))
    return _as_series(np.clip(morphed, 1, 100), index, "relhum_percent")


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


def morph_wspd_direct(present_wspd, future_sfcwind, baseline_sfcwind):
    """Stretch wind speed by a scalar surface-wind ratio.

    Parameters
    ----------
    present_wspd : pd.Series
        Hourly present-day wind speed in m/s.
    future_sfcwind : pd.Series
        Twelve monthly future surface wind speeds.
    baseline_sfcwind : pd.Series
        Twelve monthly baseline surface wind speeds.

    Returns
    -------
    pd.Series
        Morphed wind speed, clipped at zero.
    """
    index = present_wspd.index
    ratio = morph_utils.relative_delta(
        morph_utils.as_array(future_sfcwind, 12), morph_utils.as_array(baseline_sfcwind, 12),
    )
    morphed = stretch(present_wspd.to_numpy(dtype=float), morph_utils.month_factors(index, ratio))
    return _as_series(np.clip(morphed, 0, None), index, "windspd_ms")


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


def _radiation_geometry(longitude, latitude, utc_offset, index):
    """Solar geometry at the middle of each hour-ending EPW row."""
    return morph_solar_utils.solar_geometry(
        longitude, latitude, utc_offset, year=_year_of(index),
        offset_minutes=morph_solar_utils.HOUR_MIDPOINT_MINUTES,
    )


def column_is_empty(column):
    """True when an EPW column is missing or holds no positive value."""
    if column is None:
        return True
    values = np.asarray(column, dtype=float)
    return values.size == 0 or not np.any(np.nan_to_num(values, nan=0.0) > 0)


def extraterrestrial_or_computed(present_exthor, present_extdirnor, longitude, latitude, utc_offset, index=None):
    """
    Return the EPW's extraterrestrial horizontal and direct normal columns, or compute them if empty

    Some EPW writers leave both columns at 0 (weather-file-builder before 2.3.1).
    The radiation morph needs them for the clearness index and as the ceiling on
    direct normal; with zeros it returned diffuse only and no direct normal.
    A column is replaced only when it holds no positive value at all.

    Parameters
    ----------
    present_exthor, present_extdirnor : pd.Series or None
        the EPW's ``exthorrad_Whm2`` and ``extdirrad_Whm2`` columns
    longitude, latitude, utc_offset : float
        site location and the fixed UTC offset of the EPW
    index : pd.DatetimeIndex or None
        the EPW's index, used for the year and to label the result

    Returns
    -------
    tuple of pd.Series
        (exthor, extdirnor)
    """
    index = index if index is not None else _index_of(present_exthor, present_extdirnor)
    if index is None:
        index = morph_utils.ts_8760()
    if not (column_is_empty(present_exthor) or column_is_empty(present_extdirnor)):
        return (pd.Series(np.asarray(present_exthor, dtype=float), index=index),
                pd.Series(np.asarray(present_extdirnor, dtype=float), index=index))
    exthor, extdirnor = morph_solar_utils.extraterrestrial_radiation(
        longitude, latitude, utc_offset, year=_year_of(index),
    )
    computed = []
    for name, column, values in (("exthorrad_Whm2", present_exthor, exthor),
                                 ("extdirrad_Whm2", present_extdirnor, extdirnor)):
        if column_is_empty(column):
            logger.warning(
                "EPW column %s is empty; computed it from the solar position for the radiation morph", name,
            )
            computed.append(pd.Series(values, index=index))
        else:
            computed.append(pd.Series(np.asarray(column, dtype=float), index=index))
    return computed[0], computed[1]


def _ridley_diffuse_fraction(longitude, latitude, utc_offset, glohor, exthor, index):
    """Diffuse fraction of global horizontal radiation from the Ridley et al. (2010) BRL model."""
    solar_df = _radiation_geometry(longitude, latitude, utc_offset, index)
    solar_alt = solar_df['elevation'].to_numpy(dtype=float)

    glohor = np.asarray(glohor, dtype=float)
    hourly_clearness, daily_clearness = morph_solar_utils.calc_clearness(
        glohor, exthor, index=solar_df.index,
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
    return np.clip(1.0 / (1.0 + np.exp(exponent)), 0.0, 1.0)


def calc_difhor(longitude, latitude, utc_offset, morphed_glohor, present_exthor):
    """
    Diffuse horizontal radiation recalculated from scratch with the Ridley et al. persistence model [1]

        [1] B. Ridley, J. Boland, and P. Lauret, ‘Modelling of diffuse solar fraction with multiple predictors’,
                Renewable Energy, vol. 35, no. 2, pp. 478–483, Feb. 2010, doi: 10.1016/j.renene.2009.07.018.

    The morph itself uses :func:`morph_radiation_split`, which keeps the EPW's own
    split and applies only the model's change; this function remains for a full
    re-split. Solar geometry is taken at the middle of each hour.

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
    glohor = np.asarray(morphed_glohor, dtype=float)
    diffuse_fraction = _ridley_diffuse_fraction(longitude, latitude, utc_offset, glohor, present_exthor, index)
    morphed_difhor = np.nan_to_num(glohor * diffuse_fraction, nan=0.0)
    return _as_series(np.clip(morphed_difhor, 0, glohor), index, "difhorrad_Whm2")


def calc_dirnor(morphed_glohor, morphed_difhor, longitude, latitude, utc_offset,
                extraterrestrial_dirnor=None, min_solar_altitude=MIN_SOLAR_ALTITUDE):
    """
    Direct normal radiation recalculated from the morphed global and diffuse horizontal

    The beam component on the horizontal is projected onto the normal with the
    sine rule at the middle of each hour.  That projection is unbounded as the
    sun approaches the horizon, so hours below *min_solar_altitude* are set to
    zero and the result is capped at the extraterrestrial direct normal irradiance.

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
    solar_df = _radiation_geometry(longitude, latitude, utc_offset, index)
    solar_alt = solar_df['elevation'].to_numpy(dtype=float)

    glohor = np.asarray(morphed_glohor, dtype=float)
    difhor = np.asarray(morphed_difhor, dtype=float)
    beam_horizontal = glohor - difhor

    sin_alt = np.sin(np.radians(solar_alt))
    usable = (solar_alt >= min_solar_altitude) & (beam_horizontal > 0)
    dirnor = np.divide(beam_horizontal, sin_alt, out=np.zeros_like(beam_horizontal), where=usable)

    dirnor = np.clip(np.nan_to_num(dirnor, nan=0.0, posinf=0.0, neginf=0.0), 0, _ceiling(extraterrestrial_dirnor))
    return _as_series(dirnor, index if index is not None else solar_df.index, "dirnorrad_Whm2")


def _ceiling(extraterrestrial_dirnor):
    if column_is_empty(extraterrestrial_dirnor):
        return SOLAR_CONSTANT
    return np.asarray(extraterrestrial_dirnor, dtype=float)


#: Horizontal beam (W/m2) below which an hour's direct normal is changed by
#: projecting the beam change instead of scaling the EPW's own direct normal.
MIN_BEAM_FOR_SCALING = 10.0


def morph_radiation_split(present_glohor, present_difhor, present_dirnor, morphed_glohor,
                          present_exthor, present_extdirnor, longitude, latitude, utc_offset,
                          min_solar_altitude=MIN_SOLAR_ALTITUDE):
    """
    Morph diffuse horizontal and direct normal radiation, keeping the EPW's own split

    The diffuse fraction is the EPW's own plus the change the Ridley et al. (2010)
    model predicts between the present and the morphed global radiation::

        kd_future = clip(kd_present + kd_model(G_future) - kd_model(G_present), 0, 1)

    bounded so the change never carries the fraction past ``kd_model(G_future)``
    in the direction it moves (where the EPW is already beyond it, the fraction
    stays where it is).
    Direct normal scales the EPW's own value by the change in the horizontal beam,
    so it keeps the file's solar-timing convention. Where the present beam is under
    ``MIN_BEAM_FOR_SCALING`` the beam change is projected with the sine rule at the
    middle of the hour instead. The result is capped at the extraterrestrial direct
    normal. With no change in global radiation both outputs equal the input.

    Re-splitting from scratch (:func:`calc_difhor`) moved diffuse and direct normal
    by about 5% even without a climate signal, because the EPW was split by a
    different model (weather-file-builder uses DIRINT); that error went into every
    future file.

    Parameters
    ----------
    present_glohor, present_difhor, present_dirnor : pd.Series
        the EPW's global horizontal, diffuse horizontal and direct normal radiation
    morphed_glohor : pd.Series
        morphed global horizontal radiation
    present_exthor, present_extdirnor : pd.Series
        extraterrestrial horizontal and direct normal radiation (see
        :func:`extraterrestrial_or_computed`)
    longitude, latitude, utc_offset : float
        site location and the fixed UTC offset of the EPW
    min_solar_altitude : float
        solar altitude in degrees below which a projected beam change is not applied

    Returns
    -------
    tuple of pd.Series
        (difhorrad_Whm2, dirnorrad_Whm2)
    """
    index = _index_of(present_glohor, morphed_glohor, present_exthor)
    g0 = np.asarray(present_glohor, dtype=float)
    d0 = np.clip(np.asarray(present_difhor, dtype=float), 0, None)
    b0 = np.clip(np.asarray(present_dirnor, dtype=float), 0, None)
    g1 = np.asarray(morphed_glohor, dtype=float)

    kd_model_present = _ridley_diffuse_fraction(longitude, latitude, utc_offset, g0, present_exthor, index)
    kd_model_future = _ridley_diffuse_fraction(longitude, latitude, utc_offset, g1, present_exthor, index)
    has_present = g0 > 0
    kd_present = np.divide(d0, g0, out=np.zeros_like(g0), where=has_present)
    change = kd_model_future - kd_model_present
    shifted = np.clip(kd_present + change, 0.0, 1.0)
    # the change may move the fraction towards the model's future value but not past it:
    # a clear hour stretched brighter otherwise lost most of its diffuse (p5 of clear-hour
    # diffuse fell from 97 to 49 W/m2 for a +5% global morph at Zurich)
    shifted = np.where(
        change < 0,
        np.maximum(shifted, np.minimum(kd_present, kd_model_future)),
        np.minimum(shifted, np.maximum(kd_present, kd_model_future)),
    )
    kd_future = np.where(has_present, shifted, kd_model_future)
    d1 = np.clip(np.nan_to_num(g1 * kd_future, nan=0.0), 0, np.clip(g1, 0, None))

    beam0 = g0 - d0
    beam1 = g1 - d1
    solar_alt = _radiation_geometry(longitude, latitude, utc_offset, index)['elevation'].to_numpy(dtype=float)
    sin_alt = np.sin(np.radians(solar_alt))

    scale = beam0 >= MIN_BEAM_FOR_SCALING
    b1 = np.divide(b0 * beam1, beam0, out=b0.copy(), where=scale)
    project = ~scale & (solar_alt >= min_solar_altitude)
    b1 = np.where(project, b0 + np.divide(beam1 - beam0, sin_alt, out=np.zeros_like(g0), where=project), b1)
    # an hour the EPW already has above the ceiling keeps its own value as the limit
    ceiling = np.maximum(_ceiling(present_extdirnor), b0)
    b1 = np.clip(np.nan_to_num(b1, nan=0.0, posinf=0.0, neginf=0.0), 0, ceiling)

    return _as_series(d1, index, "difhorrad_Whm2"), _as_series(b1, index, "dirnorrad_Whm2")


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
    # Kept to two decimals rather than rounded to whole tenths: rounding
    # turned monthly shifts below 0.5 into no change and shifts above 0.5
    # into a full tenth (3.6.0, issue #11). EnergyPlus reads sky cover as a
    # real number (and interpolates it between hours).
    return pd.Series(np.round(morphed_tsc, SKY_COVER_DECIMALS), index=index, name="totskycvr_tenths")


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
    return pd.Series(np.round(morphed_osc, SKY_COVER_DECIMALS), index=index, name="opaqskycvr_tenths")


def sky_emissivity_clark_allen(drybulb_C, dewpoint_C, opaque_sky_cover_tenths):
    """All-sky emissivity, Clark and Allen (1978) with the Walton cloud factor.

    This is EnergyPlus's default sky model (``CalcSkyEmissivity``, Clark-Allen):
    clear-sky emissivity from the dew point (never above dry-bulb), multiplied
    by ``1 + 0.0224 N - 0.0035 N**2 + 0.00028 N**3`` with *N* the opaque sky
    cover in tenths.
    """
    drybulb = np.asarray(drybulb_C, dtype=float)
    dewpoint = np.minimum(np.asarray(dewpoint_C, dtype=float), drybulb)
    cover = np.asarray(opaque_sky_cover_tenths, dtype=float)
    clear = 0.787 + 0.764 * np.log((dewpoint + 273.15) / 273.15)
    return clear * (1.0 + 0.0224 * cover - 0.0035 * cover ** 2 + 0.00028 * cover ** 3)


def modelled_horizontal_ir(drybulb_C, dewpoint_C, opaque_sky_cover_tenths):
    """Downwelling horizontal infrared (W/m2) as EnergyPlus models it: eps_sky * sigma * T**4."""
    drybulb = np.asarray(drybulb_C, dtype=float)
    emissivity = sky_emissivity_clark_allen(drybulb, dewpoint_C, opaque_sky_cover_tenths)
    return emissivity * STEFAN_BOLTZMANN * (drybulb + 273.15) ** 4


def morph_horizontal_ir(present_ir, present_dbt, present_dewpt, present_osc,
                        future_dbt, future_dewpt, future_osc):
    """Scale the EPW's horizontal infrared by the modelled change in longwave.

    Option (a) of issue #9: the file's own value is multiplied by the ratio of
    ``eps_sky * sigma * T**4`` (Clark-Allen, as in EnergyPlus) computed from the
    morphed versus the present dry-bulb, dew point and opaque sky cover. So
    the longwave follows the warming, the humidity change and, when Clouds and
    Radiation is morphed, the cloud change, while each hour keeps the file's
    own level. Works for every data source; it does not see cloud changes
    from sources without cloud data (CH2025).

    Missing hours (9999, or not positive) stay as they are. Missing opaque sky
    cover (99) uses the present value on both sides, so only temperature and
    humidity act on that hour. An unchanged climate returns the input.

    Parameters
    ----------
    present_ir : pd.Series
        Hourly horizontal infrared from the EPW (Wh/m2).
    present_dbt, present_dewpt, present_osc : array_like
        Hourly present dry-bulb (C), dew point (C) and opaque sky cover (tenths).
    future_dbt, future_dewpt, future_osc : array_like
        The same after morphing (pass the present series for unmorphed ones).

    Returns
    -------
    pd.Series
        ``horirsky_Whm2``, rounded to whole Wh/m2.
    """
    index = _index_of(present_ir, present_dbt, future_dbt)
    ir = np.asarray(present_ir, dtype=float)
    osc_now = np.asarray(present_osc, dtype=float)
    osc_future = np.asarray(future_osc, dtype=float)
    cover_missing = (osc_now >= 99) | (osc_future >= 99) | ~np.isfinite(osc_now) | ~np.isfinite(osc_future)
    osc_now = np.where(cover_missing, np.where(osc_now >= 99, 0.0, osc_now), osc_now)
    osc_future = np.where(cover_missing, osc_now, osc_future)

    now = modelled_horizontal_ir(present_dbt, present_dewpt, osc_now)
    future = modelled_horizontal_ir(future_dbt, future_dewpt, osc_future)
    ratio = np.divide(future, now, out=np.ones_like(future), where=now > 0)

    valid = np.isfinite(ir) & (ir > 0) & (ir < IR_MISSING)
    morphed = np.where(valid, np.round(ir * ratio), ir)
    return pd.Series(morphed, index=index, name="horirsky_Whm2")
