"""Build an EPW from measured weather station data (an actual meteorological year).

.. deprecated:: 3.4.0
   Moved to ``weather_file_builder.amy`` (weather-file-builder 2.1). This
   copy is frozen and will be removed in pyepwmorph 4.0.

A typical meteorological year stitches months from many years. An *actual*
meteorological year (AMY) is one real calendar year of measurements, which is
what building energy model calibration needs. This module turns a table of
station measurements, hourly or finer, into an EPW file.

Input table
-----------
``table`` is a ``pandas.DataFrame`` with a tz-naive ``DatetimeIndex`` and the
columns below. Column names are fixed (see :data:`COLUMN_SPEC` and
:func:`describe_columns`); an adapter such as
:mod:`pyepwmorph.tools.amy_meteoswiss` renames a network's own columns.
Unknown columns are ignored and columns that are entirely empty are dropped.

=========================  ===========  =====================================================
column                     unit         meaning
=========================  ===========  =====================================================
``temp_C``                 degC         dry-bulb air temperature (required)
``dewpoint_C``             degC         dew point (this or ``rh_pct`` required)
``rh_pct``                 %            relative humidity (this or ``dewpoint_C`` required)
``pressure_Pa``            Pa           station pressure (default: standard atmosphere)
``ghi_Wm2``                W/m2         global horizontal irradiance, interval mean (required)
``dhi_Wm2``, ``dni_Wm2``   W/m2         measured diffuse / direct normal, if the site has them
``lw_down_Wm2``            W/m2         downwelling longwave at the surface, interval mean
``sunshine_min``           minutes      sunshine duration within the interval (WMO, >=120 W/m2)
``wind_speed_ms``          m/s          wind speed, interval mean (required)
``wind_dir_deg``           degrees      direction the wind blows from, 0-360, 0 or 360 = north
``precip_mm``              mm           precipitation depth within the interval
``snow_depth_cm``          cm           snow depth at the end of the interval
``total_sky_cover_tenths`` tenths 0-10  observed sky cover (derived when absent)
``opaque_sky_cover_tenths`` tenths 0-10  observed opaque sky cover (set equal to total when absent)
``visibility_km``          km           visibility
``ceiling_height_m``       m            cloud ceiling height
=========================  ===========  =====================================================

Datetime convention
-------------------
Every value describes an *interval*, not an instant. Say which end of the
interval the index marks with ``timestamp_label`` (``"end"`` or ``"start"``)
and which clock it uses with ``table_utc_offset`` (hours east of UTC, 0 for UTC
timestamps). The EPW is written in local *standard* time, a fixed offset with
no daylight saving, taken from ``location["utc_offset"]``. Whole-hour
differences between the two clocks are handled; fractional shifts are not.
Data finer than an hour (1, 5, 10, 15 or 30 minutes) is aggregated to hours:
means for intensive quantities, sums for ``precip_mm`` and ``sunshine_min``, a
speed-weighted vector mean for wind direction. An hour with any sub-interval
missing is treated as missing.

What is derived
---------------
Direct and diffuse irradiance are rarely measured. When ``dhi_Wm2`` and
``dni_Wm2`` are absent they are derived from the measured global irradiance:

* with ``sunshine_min`` and 10-minute data, from a lookup table of diffuse
  fraction against clearness index, sunshine fraction, sub-hourly clearness
  variability and solar zenith (``"table"``);
* with hourly ``sunshine_min``, the same without the variability term;
* otherwise with the DIRINT model from pvlib (``"dirint"``).

The tables were fitted on MeteoSwiss Swiss Plateau stations; see
``scripts/build_amy_diffuse_table.py``. Outside that climate use ``"dirint"``
or supply measured irradiance components. Total sky cover is derived from the
clear-sky index in daylight and from downwelling longwave (calibrated against
the daylight estimate) at other times. Opaque sky cover equals total sky cover.
Fields that no station measures are written with the EPW missing codes.

Short gaps are interpolated and long gaps raise an error (see
``max_gap_hours`` and ``long_gap``). 29 February is dropped, as in every EPW.
"""

import datetime as _dt
import logging
import unicodedata
import warnings as _warnings
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pvlib

from pyepwmorph.tools import psychrometrics
from pyepwmorph.tools.io import EPW_COLUMN_NAMES

_warnings.warn(
    "pyepwmorph.tools.amy is deprecated and will be removed in pyepwmorph 4.0. "
    "It has moved to weather-file-builder (pip install 'weather-file-builder>=2.1'): "
    "use weather_file_builder.amy.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

#: Column contract. ``agg`` is how sub-hourly values become hourly values.
COLUMN_SPEC: Dict[str, Dict[str, object]] = {
    "temp_C": dict(unit="degC", agg="mean", required=True, description="Dry-bulb air temperature at 2 m"),
    "dewpoint_C": dict(unit="degC", agg="mean", required="dewpoint_C or rh_pct", description="Dew point"),
    "rh_pct": dict(unit="%", agg="mean", required="dewpoint_C or rh_pct", description="Relative humidity"),
    "pressure_Pa": dict(unit="Pa", agg="mean", required=False, description="Station pressure"),
    "ghi_Wm2": dict(unit="W/m2", agg="mean", required=True, description="Global horizontal irradiance"),
    "dhi_Wm2": dict(unit="W/m2", agg="mean", required=False, description="Measured diffuse horizontal irradiance"),
    "dni_Wm2": dict(unit="W/m2", agg="mean", required=False, description="Measured direct normal irradiance"),
    "lw_down_Wm2": dict(unit="W/m2", agg="mean", required=False, description="Downwelling longwave radiation"),
    "sunshine_min": dict(unit="minutes", agg="sum", required=False, description="Sunshine duration in the interval"),
    "wind_speed_ms": dict(unit="m/s", agg="mean", required=True, description="Wind speed"),
    "wind_dir_deg": dict(unit="degrees", agg="vector", required=True, description="Direction wind blows from"),
    "precip_mm": dict(unit="mm", agg="sum", required=False, description="Precipitation depth in the interval"),
    "snow_depth_cm": dict(unit="cm", agg="last", required=False, description="Snow depth at the end of the interval"),
    "total_sky_cover_tenths": dict(unit="tenths", agg="mean", required=False, description="Observed total sky cover"),
    "opaque_sky_cover_tenths": dict(unit="tenths", agg="mean", required=False, description="Observed opaque sky cover"),
    "visibility_km": dict(unit="km", agg="mean", required=False, description="Visibility"),
    "ceiling_height_m": dict(unit="m", agg="mean", required=False, description="Cloud ceiling height"),
}

#: Columns whose gaps are interpolated linearly in time.
_LINEAR_COLUMNS = ("temp_C", "dewpoint_C", "rh_pct", "pressure_Pa", "wind_speed_ms", "lw_down_Wm2", "snow_depth_cm")
#: Columns that must have no long gap.
_REQUIRED_FOR_GAPS = ("temp_C", "dewpoint_C", "rh_pct", "ghi_Wm2", "wind_speed_ms", "wind_dir_deg")

#: Largest zenith angle (degrees) at which irradiance is decomposed.
_MAX_DECOMPOSE_ZENITH = 85.0
#: Zenith angle (degrees) beyond which the whole hour is dark and irradiance is set to zero.
_DARK_ZENITH = 98.0
#: Fraction of the extraterrestrial normal irradiance DNI may not exceed.
_MAX_DNI_FRACTION = 0.9

#: EnergyPlus missing codes for the fields this module cannot fill.
_MISSING = dict(
    illuminance=999999, zenith_luminance=9999, visibility=9999.0, ceiling=99999, weather_obs=9,
    weather_codes=999999999, precipitable_water=999, aerosol=0.999, snow_depth=999, days_since_snow=99,
    albedo=999, precip_depth=999, precip_rate=99, horizontal_ir=9999, sky_cover=99,
)

#: Data source and uncertainty flags written to every row.
_DATA_FLAGS = "?9?9?9?9E0?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9*9*9?9?9?9"


def describe_columns() -> pd.DataFrame:
    """Return the input column contract as a table (name, unit, aggregation, required)."""
    rows = [
        dict(column=name, unit=spec["unit"], aggregation=spec["agg"], required=spec["required"],
             description=spec["description"])
        for name, spec in COLUMN_SPEC.items()
    ]
    return pd.DataFrame(rows).set_index("column")


@dataclass
class AmyReport:
    """What was done to build an AMY: filled gaps, methods, caveats."""

    year: int = 0
    source_step_minutes: int = 60
    filled_hours: Dict[str, int] = field(default_factory=dict)
    decomposition: Dict[str, int] = field(default_factory=dict)
    dni_capped_hours: int = 0
    sky_cover_method: str = ""
    sky_cover_calibration: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [f"AMY {self.year}: source resolution {self.source_step_minutes} min"]
        if self.filled_hours:
            lines.append("filled hours: " + ", ".join(f"{k}={v}" for k, v in sorted(self.filled_hours.items())))
        if self.decomposition:
            lines.append("diffuse/direct split (hours): " + ", ".join(f"{k}={v}" for k, v in self.decomposition.items()))
        if self.sky_cover_method:
            lines.append(f"sky cover: {self.sky_cover_method}")
        lines.extend(self.notes)
        return "\n".join(lines)


# --------------------------------------------------------------------------- input handling


def _validate_table(table: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(table.index, pd.DatetimeIndex):
        raise ValueError("table needs a DatetimeIndex (see the module docstring for the datetime convention)")
    t = table.copy()
    if t.index.tz is not None:
        t.index = t.index.tz_convert("UTC").tz_localize(None)
        logger.warning("tz-aware index converted to UTC; pass table_utc_offset=0")
    t = t[~t.index.isna()].sort_index()
    if t.index.has_duplicates:
        logger.warning("duplicate timestamps: keeping the first of each")
        t = t[~t.index.duplicated(keep="first")]
    known = [c for c in t.columns if c in COLUMN_SPEC]
    ignored = [c for c in t.columns if c not in COLUMN_SPEC]
    if ignored:
        logger.info("ignoring unknown columns: %s", ", ".join(map(str, ignored)))
    t = t[known].apply(pd.to_numeric, errors="coerce")
    t = t.loc[:, t.notna().any()]
    for name in ("temp_C", "ghi_Wm2", "wind_speed_ms", "wind_dir_deg"):
        if name not in t.columns:
            raise ValueError(f"required column '{name}' is missing or empty")
    if "dewpoint_C" not in t.columns and "rh_pct" not in t.columns:
        raise ValueError("one of 'dewpoint_C' or 'rh_pct' is required")
    return t


def _infer_step_minutes(index: pd.DatetimeIndex) -> int:
    diffs = pd.Series(index[1:] - index[:-1])
    step = int(round(diffs.mode().iloc[0].total_seconds() / 60))
    if step <= 0 or step > 60 or 60 % step != 0:
        raise ValueError(f"unsupported time step of {step} minutes; use 1, 5, 10, 15, 30 or 60")
    return step


def _vector_mean_direction(speed: Optional[pd.Series], direction: pd.Series, k: int) -> pd.Series:
    """Speed-weighted vector mean of a wind direction over *k* sub-intervals."""
    rad = np.radians(direction)
    weight = speed if speed is not None else pd.Series(1.0, index=direction.index)
    calm = weight == 0
    u = (weight * np.sin(rad)).where(~calm, 0.0).where(direction.notna() | calm)
    v = (weight * np.cos(rad)).where(~calm, 0.0).where(direction.notna() | calm)
    mu = u.rolling(k, min_periods=k).mean()
    mv = v.rolling(k, min_periods=k).mean()
    out = np.degrees(np.arctan2(mu, mv)) % 360.0
    out = out.where(np.hypot(mu, mv) > 1e-9, 0.0)
    return out.where(mu.notna() & mv.notna())


def _subhourly_kt_std(ghi: pd.Series, location: dict, step: int) -> pd.Series:
    """Standard deviation of the clearness index across the sub-intervals of each hour.

    *ghi* is indexed by the interval end in local standard time. The result is
    indexed the same way and is NaN where any sub-interval is missing or the
    sun is low (zenith 85 degrees or more).
    """
    k = 60 // step
    solar = _solar_frame(ghi.index - pd.Timedelta(minutes=step), location, interval_min=step)
    kt = (ghi.clip(lower=0).to_numpy() / (solar["dni_extra"].to_numpy() * solar["cosz"].to_numpy()))
    kt = pd.Series(kt, index=ghi.index).where(solar["zenith"].to_numpy() < _MAX_DECOMPOSE_ZENITH)
    return kt.rolling(k, min_periods=k).std()


def aggregate_to_hourly(
    table: pd.DataFrame,
    location: dict,
    *,
    timestamp_label: str = "end",
    table_utc_offset: float = 0.0,
) -> Tuple[pd.DataFrame, int]:
    """Aggregate a station table to hourly rows labelled by the interval *start* in local standard time.

    Returns the hourly frame and the source time step in minutes. A column
    ``ghi_kt_std`` (sub-hourly clearness variability) is added when the source
    is finer than an hour and has global irradiance.
    """
    if timestamp_label not in ("end", "start"):
        raise ValueError("timestamp_label must be 'end' or 'start'")
    t = _validate_table(table)
    step = _infer_step_minutes(t.index) if len(t) > 1 else 60
    shift = float(location["utc_offset"]) - float(table_utc_offset)
    if abs(shift - round(shift)) > 1e-9:
        raise ValueError(
            "the table's clock and the EPW time zone differ by a fractional number of hours; "
            "convert the table to local standard time first"
        )
    idx = t.index
    if timestamp_label == "start":
        idx = idx + pd.Timedelta(minutes=step)
    t.index = idx + pd.Timedelta(hours=int(round(shift)))
    grid = pd.date_range(t.index.min(), t.index.max(), freq=f"{step}min")
    t = t.reindex(grid)
    if t.index[0].minute != 0 and step == 60:
        raise ValueError("hourly timestamps must fall on the hour")
    k = 60 // step

    if k == 1:
        hourly = t.copy()
    else:
        parts = {}
        speed = t["wind_speed_ms"] if "wind_speed_ms" in t.columns else None
        for name in t.columns:
            how = COLUMN_SPEC[name]["agg"]
            if how == "mean":
                parts[name] = t[name].rolling(k, min_periods=k).mean()
            elif how == "sum":
                parts[name] = t[name].rolling(k, min_periods=k).sum()
            elif how == "vector":
                parts[name] = _vector_mean_direction(speed, t[name], k)
            else:
                parts[name] = t[name]
        hourly = pd.DataFrame(parts)
        if "ghi_Wm2" in t.columns:
            hourly["ghi_kt_std"] = _subhourly_kt_std(t["ghi_Wm2"], location, step)
        hourly = hourly[hourly.index.minute == 0]

    hourly.index = hourly.index - pd.Timedelta(hours=1)
    return hourly, step


# --------------------------------------------------------------------------- solar helpers


def _solar_frame(index_start: pd.DatetimeIndex, location: dict, interval_min: int = 60) -> pd.DataFrame:
    """Solar position and extraterrestrial radiation at the middle of each interval.

    *index_start* holds interval starts as tz-naive local standard time.
    """
    tz = _dt.timezone(_dt.timedelta(hours=float(location["utc_offset"])))
    mid = (index_start + pd.Timedelta(minutes=interval_min / 2.0)).tz_localize(tz)
    pos = pvlib.solarposition.get_solarposition(
        mid, float(location["latitude"]), float(location["longitude"]), altitude=float(location["elevation"])
    )
    dni_extra = np.asarray(pvlib.irradiance.get_extra_radiation(mid), dtype=float)
    zen = pos["zenith"].to_numpy()
    cosz = np.cos(np.radians(np.minimum(zen, 89.0)))
    return pd.DataFrame(
        {
            "zenith": zen,
            "apparent_zenith": pos["apparent_zenith"].to_numpy(),
            "cosz": cosz,
            "dni_extra": dni_extra,
            "ext_hor": dni_extra * np.maximum(np.cos(np.radians(zen)), 0.0),
        },
        index=index_start,
    )


def decomposition_features(
    ghi: pd.Series, sunshine_min: Optional[pd.Series], kt_std: Optional[pd.Series], solar: pd.DataFrame
) -> pd.DataFrame:
    """Hourly features of the diffuse-fraction tables (also used to fit them).

    Columns ``kt`` (clearness index), ``S`` (sunshine fraction of the hour),
    ``sd`` (sub-hourly clearness standard deviation) and ``zen`` (zenith, degrees).
    """
    kt = (ghi.clip(lower=0) / (solar["dni_extra"] * solar["cosz"])).clip(0.0, 1.2)
    feats = pd.DataFrame({"kt": kt, "zen": solar["zenith"]}, index=ghi.index)
    feats["S"] = (sunshine_min / 60.0).clip(0.0, 1.0) if sunshine_min is not None else np.nan
    feats["sd"] = kt_std.clip(0.0, 0.5) if kt_std is not None else np.nan
    return feats[["kt", "S", "sd", "zen"]]


@lru_cache(maxsize=1)
def _load_diffuse_tables() -> Dict[str, Tuple[List[str], list, np.ndarray]]:
    resource = files("pyepwmorph.data").joinpath("amy_diffuse_table.parquet")
    with resource.open("rb") as handle:
        raw = pd.read_parquet(handle)
    tables = {}
    for name, frame in raw.groupby("table"):
        axes_names = ["kt", "S", "sd", "zen"] if name == "kssd" else ["kt", "S", "zen"]
        axes = [np.sort(frame[a].unique()) for a in axes_names]
        frame = frame.sort_values(axes_names)
        values = frame["kd"].to_numpy().reshape([len(a) for a in axes])
        tables[name] = (axes_names, axes, values)
    return tables


def _table_diffuse_fraction(feats: pd.DataFrame, name: str) -> pd.Series:
    from scipy.interpolate import RegularGridInterpolator

    axes_names, axes, values = _load_diffuse_tables()[name]
    interp = RegularGridInterpolator(axes, values, bounds_error=False, fill_value=None)
    pts = np.column_stack([
        feats[a].clip(lower=ax[0], upper=ax[-1]).to_numpy() for a, ax in zip(axes_names, axes)
    ])
    return pd.Series(np.clip(interp(pts), 0.0, 1.0), index=feats.index)


def _decompose(
    ghi: pd.Series,
    hourly: pd.DataFrame,
    solar: pd.DataFrame,
    pressure_pa: pd.Series,
    step: int,
    method: str,
    report: AmyReport,
) -> Tuple[pd.Series, pd.Series]:
    """Return diffuse horizontal and direct normal irradiance (W/m2)."""
    if method not in ("auto", "table", "dirint", "erbs"):
        raise ValueError("decomposition must be 'auto', 'table', 'dirint' or 'erbs'")
    n = len(ghi)
    dhi = pd.Series(np.nan, index=ghi.index)
    how = pd.Series("", index=ghi.index, dtype=object)

    daylight = (solar["zenith"] < _MAX_DECOMPOSE_ZENITH) & (ghi > 10.0)
    dark = ~daylight
    dhi[dark] = ghi[dark]
    how[dark] = "night"

    # measured components first
    cosz = solar["cosz"]
    if "dhi_Wm2" in hourly.columns:
        m = hourly["dhi_Wm2"].notna() & daylight
        dhi[m] = hourly["dhi_Wm2"][m].clip(lower=0).clip(upper=ghi[m])
        how[m] = "measured"
    if "dni_Wm2" in hourly.columns:
        m = hourly["dni_Wm2"].notna() & daylight & dhi.isna()
        dhi[m] = (ghi[m] - hourly["dni_Wm2"][m] * cosz[m]).clip(lower=0).clip(upper=ghi[m])
        how[m] = "measured"

    todo = dhi.isna() & daylight
    sunshine = hourly["sunshine_min"] if "sunshine_min" in hourly.columns else None
    kt_std = hourly["ghi_kt_std"] if "ghi_kt_std" in hourly.columns else None
    feats = decomposition_features(ghi, sunshine, kt_std, solar)

    use_tables = method in ("auto", "table") and sunshine is not None
    if method == "table" and sunshine is None:
        raise ValueError("decomposition='table' needs the 'sunshine_min' column")
    if use_tables:
        has_s = feats["S"].notna()
        if step == 10:
            m = todo & has_s & feats["sd"].notna()
            if m.any():
                dhi[m] = _table_diffuse_fraction(feats[m], "kssd") * ghi[m]
                how[m] = "table (sunshine, variability)"
        m = dhi.isna() & todo & has_s
        if m.any():
            dhi[m] = _table_diffuse_fraction(feats[m], "ks") * ghi[m]
            how[m] = "table (sunshine)"

    todo = dhi.isna() & daylight
    if todo.any():
        times = ghi.index + pd.Timedelta(minutes=30)
        label = "erbs" if method == "erbs" else "dirint"
        if label == "dirint":
            tz = _dt.timezone(_dt.timedelta(hours=0))
            dni = pvlib.irradiance.dirint(
                ghi.to_numpy(), solar["zenith"].to_numpy(), times.tz_localize(tz), pressure=pressure_pa.to_numpy()
            )
            dni = pd.Series(np.asarray(dni, dtype=float), index=ghi.index)
            fallback = (ghi - dni * cosz).clip(lower=0)
            ok = todo & dni.notna()
            dhi[ok] = fallback[ok]
            how[ok] = "dirint"
        todo = dhi.isna() & daylight
        if todo.any():
            er = pvlib.irradiance.erbs(ghi[todo], solar["zenith"][todo], pd.DatetimeIndex(ghi.index[todo]))
            dhi[todo] = er["dhi"].to_numpy()
            how[todo] = "erbs"

    dhi = dhi.clip(lower=0.0)
    dhi = pd.Series(np.minimum(dhi.to_numpy(), ghi.to_numpy()), index=ghi.index)
    low_sun = solar["zenith"] >= _MAX_DECOMPOSE_ZENITH
    dni = pd.Series(0.0, index=ghi.index)
    ok = ~low_sun & (ghi > 0)
    dni[ok] = (ghi[ok] - dhi[ok]) / cosz[ok]
    cap = _MAX_DNI_FRACTION * solar["dni_extra"]
    capped = dni > cap
    report.dni_capped_hours = int(capped.sum())
    if capped.any():
        dni[capped] = cap[capped]
        dhi[capped] = ghi[capped] - dni[capped] * cosz[capped]
    dni = dni.clip(lower=0.0)
    report.decomposition = {k: int(v) for k, v in how.value_counts().items() if k}
    assert n == len(dni)
    return dhi, dni


# --------------------------------------------------------------------------- sky cover


def estimate_sky_cover(
    ghi: pd.Series,
    solar: pd.DataFrame,
    temp_c: pd.Series,
    dewpoint_c: pd.Series,
    lw_down: Optional[pd.Series],
    location: dict,
    report: AmyReport,
) -> pd.Series:
    """Total sky cover as a 0-1 fraction.

    Daylight (zenith below 75 degrees): Kasten and Czeplak (1980) from the
    ratio of measured to Ineichen clear-sky irradiance. Otherwise, from the
    effective sky emissivity of the downwelling longwave: clear-sky emissivity
    from Martin and Berdahl (1984), cloud fraction as the share of the way to
    an overcast sky, then a straight-line fit to the daylight estimate removes
    the site's bias. Without longwave data, night values are carried across
    from daylight by interpolation.
    """
    mid = (ghi.index + pd.Timedelta(minutes=30)).tz_localize(_dt.timezone(_dt.timedelta(hours=float(location["utc_offset"]))))
    try:
        linke = pvlib.clearsky.lookup_linke_turbidity(mid, float(location["latitude"]), float(location["longitude"]))
        linke = np.asarray(linke, dtype=float)
    except Exception as exc:  # the lookup needs pvlib's bundled turbidity file
        logger.warning("Linke turbidity lookup failed (%s); using 3.0", exc)
        linke = np.full(len(mid), 3.0)
    loc = pvlib.location.Location(float(location["latitude"]), float(location["longitude"]),
                                  altitude=float(location["elevation"]))
    clear = loc.get_clearsky(mid, model="ineichen", linke_turbidity=linke)["ghi"].to_numpy()
    day = (solar["zenith"] < 75.0).to_numpy()
    kc = np.where(day & (clear > 50), ghi.clip(lower=0).to_numpy() / np.where(clear > 50, clear, np.nan), np.nan)
    n_ghi = pd.Series(((1.0 - np.clip(kc, None, 1.0)) / 0.75).clip(0, 1) ** (1 / 3.4), index=ghi.index)

    n_lw = None
    if lw_down is not None:
        sigma = 5.670374419e-8
        eps = lw_down / (sigma * (temp_c + 273.15) ** 4)
        solar_hour = ((mid.hour + 0.5).to_numpy() + (float(location["longitude"]) - 15.0 * float(location["utc_offset"])) / 15.0)
        eps_clear = 0.711 + 0.0056 * dewpoint_c + 0.000073 * dewpoint_c ** 2 + 0.013 * np.cos(2 * np.pi * solar_hour / 24.0)
        n_lw = ((eps - eps_clear) / (1.0 - eps_clear)).clip(0, 1)

    cover = n_ghi.copy()
    if n_lw is not None:
        pair = n_ghi.notna() & n_lw.notna() & (solar["zenith"] < 70.0)
        method = "longwave"
        if pair.sum() >= 200 and n_ghi[pair].corr(n_lw[pair]) > 0.5:
            slope, intercept = np.polyfit(n_lw[pair], n_ghi[pair], 1)
            if 0.5 <= slope <= 3.0:
                n_lw = (intercept + slope * n_lw).clip(0, 1)
                method = "longwave calibrated to daylight clear-sky index"
                report.sky_cover_calibration = dict(
                    slope=float(slope), intercept=float(intercept),
                    correlation=float(n_ghi[pair].corr(n_lw[pair])), hours=int(pair.sum()),
                )
        cover = n_ghi.where(n_ghi.notna(), n_lw)
        report.sky_cover_method = f"daylight: clear-sky index (Kasten & Czeplak 1980); otherwise {method} (Martin & Berdahl 1984)"
    else:
        cover = n_ghi.interpolate(limit=24, limit_direction="both")
        report.sky_cover_method = "daylight: clear-sky index (Kasten & Czeplak 1980); night interpolated, no longwave data"
    return cover


# --------------------------------------------------------------------------- gaps


def _runs(mask: pd.Series) -> List[Tuple[pd.Timestamp, int]]:
    """Start and length of each run of True in *mask*."""
    out = []
    values = mask.to_numpy()
    i = 0
    while i < len(values):
        if values[i]:
            j = i
            while j < len(values) and values[j]:
                j += 1
            out.append((mask.index[i], j - i))
            i = j
        else:
            i += 1
    return out


def _fill_gaps(
    hourly: pd.DataFrame, solar: pd.DataFrame, max_gap_hours: int, long_gap: str, report: AmyReport
) -> pd.DataFrame:
    if long_gap not in ("raise", "interpolate"):
        raise ValueError("long_gap must be 'raise' or 'interpolate'")
    h = hourly.copy()
    limit = None if long_gap == "interpolate" else int(max_gap_hours)

    problems = []
    for name in _REQUIRED_FOR_GAPS:
        if name in h.columns:
            for start, length in _runs(h[name].isna()):
                if length > max_gap_hours:
                    problems.append(f"{name}: {length} h from {start:%Y-%m-%d %H:%M}")
    if problems and long_gap == "raise":
        raise ValueError(
            f"gaps longer than {max_gap_hours} h: " + "; ".join(problems[:10])
            + ". Fill them, or pass long_gap='interpolate'."
        )
    if problems:
        report.notes.append("long gaps interpolated: " + "; ".join(problems[:10]))

    for name in _LINEAR_COLUMNS:
        if name in h.columns:
            before = int(h[name].isna().sum())
            h[name] = h[name].interpolate(method="linear", limit=limit, limit_direction="both")
            after = int(h[name].isna().sum())
            if before - after:
                report.filled_hours[name] = before - after

    if "wind_dir_deg" in h.columns:
        rad = np.radians(h["wind_dir_deg"])
        u, v = np.sin(rad), np.cos(rad)
        before = int(h["wind_dir_deg"].isna().sum())
        u = u.interpolate(limit=limit, limit_direction="both")
        v = v.interpolate(limit=limit, limit_direction="both")
        h["wind_dir_deg"] = (np.degrees(np.arctan2(u, v)) % 360.0).where(u.notna() & v.notna())
        if before - int(h["wind_dir_deg"].isna().sum()):
            report.filled_hours["wind_dir_deg"] = before - int(h["wind_dir_deg"].isna().sum())

    # irradiance: interpolate the clearness index so a gap keeps the sun's shape
    ghi = h["ghi_Wm2"].clip(lower=0)
    denom = solar["dni_extra"] * solar["cosz"]
    high_sun = solar["zenith"] < _MAX_DECOMPOSE_ZENITH
    before = int(ghi.isna().sum())
    kt_filled = (ghi / denom).where(high_sun).interpolate(limit=limit, limit_direction="both")
    ghi = (kt_filled * denom).where(high_sun, ghi.interpolate(limit=limit, limit_direction="both"))
    # an hour is dark when the sun stays below the horizon for all of it (the sun moves at most 8 degrees)
    ghi = ghi.where(solar["zenith"] < _DARK_ZENITH, 0.0)
    h["ghi_Wm2"] = ghi
    if before - int(ghi.isna().sum()):
        report.filled_hours["ghi_Wm2"] = before - int(ghi.isna().sum())
    return h


# --------------------------------------------------------------------------- build


def build_amy_dataframe(
    table: pd.DataFrame,
    location: dict,
    year: int,
    *,
    timestamp_label: str = "end",
    table_utc_offset: float = 0.0,
    max_gap_hours: int = 6,
    long_gap: str = "raise",
    decomposition: str = "auto",
) -> Tuple[pd.DataFrame, AmyReport]:
    """Build the 8760 EPW data rows for *year* from a station table.

    Parameters
    ----------
    table : pd.DataFrame
        Station measurements; see the module docstring for columns and units.
    location : dict
        ``latitude``, ``longitude``, ``elevation`` (m) and ``utc_offset``
        (hours east of UTC, standard time), plus optional ``site``, ``province``,
        ``country_code``, ``type`` and ``usaf`` for the EPW header.
    year : int
        The calendar year, in local standard time.
    timestamp_label : {"end", "start"}
        Which end of each averaging interval the index marks.
    table_utc_offset : float
        Hours east of UTC of the table's clock (0 for UTC).
    max_gap_hours : int
        Longest gap that is interpolated.
    long_gap : {"raise", "interpolate"}
        What to do about longer gaps in the required columns.
    decomposition : {"auto", "table", "dirint", "erbs"}
        How to split global irradiance when no components are measured.

    Returns
    -------
    tuple
        A data frame with the 35 EPW columns (``hour`` runs 1-24) and an :class:`AmyReport`.
    """
    for key in ("latitude", "longitude", "elevation", "utc_offset"):
        if key not in location:
            raise ValueError(f"location is missing '{key}'")
    report = AmyReport(year=int(year))
    hourly, step = aggregate_to_hourly(table, location, timestamp_label=timestamp_label, table_utc_offset=table_utc_offset)
    report.source_step_minutes = step

    full = pd.date_range(f"{year}-01-01 00:00", f"{year}-12-31 23:00", freq="h")
    present = hourly.index.intersection(full)
    if len(present) < 0.5 * len(full):
        raise ValueError(f"the table covers only {len(present)} of the {len(full)} hours of {year}")
    hourly = hourly.reindex(full)
    leap_day = (full.month == 2) & (full.day == 29)
    if leap_day.any():
        hourly = hourly[~leap_day]
        report.notes.append("29 February dropped")

    solar = _solar_frame(hourly.index, location)
    hourly = _fill_gaps(hourly, solar, max_gap_hours, long_gap, report)

    for name in ("temp_C", "ghi_Wm2", "wind_speed_ms", "wind_dir_deg"):
        left = int(hourly[name].isna().sum())
        if left:
            raise ValueError(f"{left} hours of '{name}' are still missing after filling")

    temp = hourly["temp_C"]
    if "dewpoint_C" in hourly.columns and "rh_pct" in hourly.columns:
        dew, rh = hourly["dewpoint_C"], hourly["rh_pct"]
    elif "dewpoint_C" in hourly.columns:
        dew = hourly["dewpoint_C"]
        rh = 100.0 * pd.Series(
            psychrometrics.saturated_vapor_pressure(dew + 273.15) / psychrometrics.saturated_vapor_pressure(temp + 273.15),
            index=hourly.index,
        )
    else:
        rh = hourly["rh_pct"].clip(0, 100)
        dew = pd.Series(psychrometrics.dew_point_from_db_rh(temp.to_numpy(), rh.to_numpy()), index=hourly.index)
    if dew.isna().any() or rh.isna().any():
        raise ValueError("humidity is still missing after filling")
    rh = rh.clip(0, 100)
    dew = np.minimum(dew, temp)

    if "pressure_Pa" in hourly.columns and hourly["pressure_Pa"].notna().all():
        pressure = hourly["pressure_Pa"]
    else:
        std = float(pvlib.atmosphere.alt2pres(float(location["elevation"])))
        pressure = pd.Series(std, index=hourly.index)
        report.notes.append("pressure from the standard atmosphere at the station elevation")

    ghi = hourly["ghi_Wm2"].clip(lower=0)
    dhi, dni = _decompose(ghi, hourly, solar, pressure, step, decomposition, report)

    lw = hourly["lw_down_Wm2"] if "lw_down_Wm2" in hourly.columns else None
    if "total_sky_cover_tenths" in hourly.columns and hourly["total_sky_cover_tenths"].notna().any():
        cover = (hourly["total_sky_cover_tenths"] / 10.0).clip(0, 1)
        report.sky_cover_method = "observed"
    else:
        cover = estimate_sky_cover(ghi, solar, temp, dew, lw, location, report)
    tenths = np.rint(cover * 10.0)
    total = tenths.where(tenths.notna(), _MISSING["sky_cover"]).astype(int)
    if "opaque_sky_cover_tenths" in hourly.columns and hourly["opaque_sky_cover_tenths"].notna().all():
        opaque = hourly["opaque_sky_cover_tenths"].round().astype(int)
    else:
        opaque = total

    start = hourly.index
    n = len(hourly)

    def col(name, default):
        if name in hourly.columns:
            return hourly[name].fillna(default)
        return pd.Series(default, index=start)

    wind_speed = hourly["wind_speed_ms"].clip(lower=0)
    wind_dir = hourly["wind_dir_deg"].where(wind_speed > 0, 0.0).round()

    epw = pd.DataFrame(index=start, columns=EPW_COLUMN_NAMES, dtype=object)
    epw["year"] = int(year)
    epw["month"] = start.month
    epw["day"] = start.day
    epw["hour"] = start.hour + 1
    epw["minute"] = 0
    epw["datasource"] = _DATA_FLAGS
    epw["drybulb_C"] = temp.round(1)
    epw["dewpoint_C"] = dew.round(1)
    epw["relhum_percent"] = rh.round(1)
    epw["atmos_Pa"] = pressure.round(0).astype(int)
    epw["exthorrad_Whm2"] = solar["ext_hor"].round(0).astype(int)
    epw["extdirrad_Whm2"] = solar["dni_extra"].round(0).astype(int)
    epw["horirsky_Whm2"] = (
        lw.round(0).astype(int) if lw is not None and lw.notna().all() else _MISSING["horizontal_ir"]
    )
    epw["glohorrad_Whm2"] = ghi.round(0).astype(int)
    epw["dirnorrad_Whm2"] = dni.round(0).astype(int)
    epw["difhorrad_Whm2"] = dhi.round(0).astype(int)
    epw["glohorillum_lux"] = _MISSING["illuminance"]
    epw["dirnorillum_lux"] = _MISSING["illuminance"]
    epw["difhorillum_lux"] = _MISSING["illuminance"]
    epw["zenlum_lux"] = _MISSING["zenith_luminance"]
    epw["winddir_deg"] = wind_dir.astype(int)
    epw["windspd_ms"] = wind_speed.round(1)
    epw["totskycvr_tenths"] = total
    epw["opaqskycvr_tenths"] = opaque
    epw["visibility_km"] = (
        col("visibility_km", _MISSING["visibility"]).round(1) if "visibility_km" in hourly.columns else _MISSING["visibility"]
    )
    epw["ceiling_hgt_m"] = (
        col("ceiling_height_m", _MISSING["ceiling"]).round(0).astype(int)
        if "ceiling_height_m" in hourly.columns else _MISSING["ceiling"]
    )
    epw["presweathobs"] = _MISSING["weather_obs"]
    epw["presweathcodes"] = _MISSING["weather_codes"]
    epw["precip_wtr_mm"] = _MISSING["precipitable_water"]
    epw["aerosol_opt_thousandths"] = _MISSING["aerosol"]
    epw["snowdepth_cm"] = (
        col("snow_depth_cm", _MISSING["snow_depth"]).clip(lower=0).round(0).astype(int)
        if "snow_depth_cm" in hourly.columns else _MISSING["snow_depth"]
    )
    epw["days_last_snow"] = _MISSING["days_since_snow"]
    epw["Albedo"] = _MISSING["albedo"]
    if "precip_mm" in hourly.columns:
        precip = hourly["precip_mm"]
        epw["liq_precip_depth_mm"] = precip.clip(lower=0).round(1).where(precip.notna(), _MISSING["precip_depth"])
        epw["liq_precip_rate_Hour"] = np.where(precip.notna(), 1.0, _MISSING["precip_rate"])
    else:
        epw["liq_precip_depth_mm"] = _MISSING["precip_depth"]
        epw["liq_precip_rate_Hour"] = _MISSING["precip_rate"]
    assert len(epw) == n == 8760
    return epw, report


# --------------------------------------------------------------------------- output

_FORMATS = {
    "year": "{:d}", "month": "{:d}", "day": "{:d}", "hour": "{:d}", "minute": "{:d}",
    "drybulb_C": "{:.1f}", "dewpoint_C": "{:.1f}", "relhum_percent": "{:.1f}", "atmos_Pa": "{:d}",
    "windspd_ms": "{:.1f}", "visibility_km": "{:.1f}", "liq_precip_depth_mm": "{:.1f}",
    "liq_precip_rate_Hour": "{:.1f}", "aerosol_opt_thousandths": "{:.3f}",
}


def _ascii(value) -> str:
    """Plain-ASCII text for header fields (EnergyPlus is happiest without accents)."""
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")


def _format_rows(epw: pd.DataFrame) -> List[str]:
    cols = []
    for name in EPW_COLUMN_NAMES:
        values = epw[name].tolist()
        if name == "datasource":
            cols.append([str(v) for v in values])
            continue
        fmt = _FORMATS.get(name, "{:d}")
        cols.append([fmt.format(float(v) if "f}" in fmt else int(v)) for v in values])
    return [",".join(row) + "\n" for row in zip(*cols)]


def write_amy_epw(
    path: str,
    epw: pd.DataFrame,
    location: dict,
    report: AmyReport,
    *,
    source_name: str = "weather station",
    attribution: Optional[str] = None,
) -> None:
    """Write the data rows from :func:`build_amy_dataframe` to an EPW file.

    The header states the period of record (``Period of Record=<year>-<year>``)
    and the methods used for derived fields, so downstream tools that read the
    baseline period see a single year.
    """
    year = int(epw["year"].iloc[0])
    first = _dt.date(year, 1, 1)
    day_of_week = first.strftime("%A")

    def text(key, default):
        return _ascii(location.get(key, default)).replace(",", " ")

    loc_line = ",".join([
        "LOCATION", text("site", "Unknown"), text("province", "-"), text("country_code", "-"),
        text("type", "Measured"), text("usaf", "999999"),
        f"{float(location['latitude']):.5f}", f"{float(location['longitude']):.5f}",
        f"{float(location['utc_offset']):.1f}", f"{float(location['elevation']):.1f}",
    ])

    methods = []
    if report.decomposition:
        methods.append("direct/diffuse split: " + ", ".join(f"{k} {v} h" for k, v in report.decomposition.items()))
    if report.sky_cover_method:
        methods.append("sky cover: " + report.sky_cover_method)
    if report.filled_hours:
        methods.append("interpolated hours: " + ", ".join(f"{k} {v}" for k, v in sorted(report.filled_hours.items())))
    comments_2 = (
        f"Actual meteorological year {year}; hourly means in local standard time, hour ending; "
        + "; ".join(methods)
        + ("; " + attribution if attribution else "")
    ).replace('"', "'")
    comments_2 = _ascii(comments_2)
    comments_1 = (
        f"Measured data from {source_name}, built with pyepwmorph; Period of Record={year}-{year}"
    ).replace('"', "'")
    comments_1 = _ascii(comments_1)

    header = [
        loc_line,
        "DESIGN CONDITIONS,0",
        "TYPICAL/EXTREME PERIODS,0",
        "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        f'COMMENTS 1,"{comments_1}"',
        f'COMMENTS 2,"{comments_2}"',
        f"DATA PERIODS,1,1,Data,{day_of_week},1/1,12/31",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header) + "\n")
        fh.writelines(_format_rows(epw))


def station_table_to_epw(
    table: pd.DataFrame,
    location: dict,
    year: int,
    output_path: str,
    *,
    source_name: str = "weather station",
    attribution: Optional[str] = None,
    **build_kwargs,
) -> AmyReport:
    """Build an AMY from a station table and write it to *output_path*.

    Keyword arguments other than ``source_name`` and ``attribution`` go to
    :func:`build_amy_dataframe`. Returns the :class:`AmyReport`.
    """
    epw, report = build_amy_dataframe(table, location, year, **build_kwargs)
    write_amy_epw(output_path, epw, location, report, source_name=source_name, attribution=attribution)
    return report
