"""MeteoSwiss open data (ogd-smn) adapter for :mod:`pyepwmorph.tools.amy`.

Reads the automatic station files that MeteoSwiss publishes at
https://opendatadocs.meteoswiss.ch/ (10-minute ``..._t_...`` and hourly
``..._h_...`` CSVs, semicolon separated) and renames their parameter codes to
the columns :func:`pyepwmorph.tools.amy.build_amy_dataframe` expects. The
station table is the ``ogd-smn_meta_stations.csv`` file.

MeteoSwiss timestamps (``reference_timestamp``, ``DD.MM.YYYY HH:MM``) are UTC
and mark the *end* of the averaging interval, which is what the defaults of
``build_amy_dataframe`` assume.

Data: Source MeteoSwiss, open government data (check the current terms for
attribution wording).
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

#: Attribution line for the EPW header.
ATTRIBUTION = "Source: MeteoSwiss (Federal Office of Meteorology and Climatology), open government data"

#: Parameter code -> (amy column, multiplier). 10-minute files (``z``/``s`` suffixes).
MAPPING_10MIN = {
    "tre200s0": ("temp_C", 1.0),
    "tde200s0": ("dewpoint_C", 1.0),
    "ure200s0": ("rh_pct", 1.0),
    "prestas0": ("pressure_Pa", 100.0),
    "fkl010z0": ("wind_speed_ms", 1.0),
    "dkl010z0": ("wind_dir_deg", 1.0),
    "gre000z0": ("ghi_Wm2", 1.0),
    "ods000z0": ("dhi_Wm2", 1.0),
    "oli000z0": ("lw_down_Wm2", 1.0),
    "sre000z0": ("sunshine_min", 1.0),
    "rre150z0": ("precip_mm", 1.0),
    "htoauts0": ("snow_depth_cm", 1.0),
}

#: Hourly files (``h`` suffix).
MAPPING_HOURLY = {
    "tre200h0": ("temp_C", 1.0),
    "tde200h0": ("dewpoint_C", 1.0),
    "ure200h0": ("rh_pct", 1.0),
    "prestah0": ("pressure_Pa", 100.0),
    "fkl010h0": ("wind_speed_ms", 1.0),
    "dkl010h0": ("wind_dir_deg", 1.0),
    "gre000h0": ("ghi_Wm2", 1.0),
    "ods000h0": ("dhi_Wm2", 1.0),
    "oli000h0": ("lw_down_Wm2", 1.0),
    "sre000h0": ("sunshine_min", 1.0),
    "rre150h0": ("precip_mm", 1.0),
    "htoauths": ("snow_depth_cm", 1.0),
}

_TIMESTAMP_FORMAT = "%d.%m.%Y %H:%M"


def read_meteoswiss_ogd(path: str, station: Optional[str] = None) -> pd.DataFrame:
    """Read a MeteoSwiss ogd-smn station CSV into the AMY input table.

    Parameters
    ----------
    path : str
        A 10-minute or hourly station file (decade files such as
        ``ogd-smn_sma_t_historical_2020-2029.csv`` work; so do the ``recent`` files).
    station : str, optional
        Station abbreviation to keep if the file holds several.

    Returns
    -------
    pd.DataFrame
        Tz-naive UTC timestamps marking the end of each interval, columns named
        as in :data:`pyepwmorph.tools.amy.COLUMN_SPEC` with units converted
        (pressure in Pa).
    """
    raw = pd.read_csv(path, sep=";", encoding="latin-1")
    if "reference_timestamp" not in raw.columns:
        raise ValueError(f"{path} has no 'reference_timestamp' column; is it a MeteoSwiss ogd-smn file?")
    if station is not None and "station_abbr" in raw.columns:
        raw = raw[raw["station_abbr"] == station]
    if any(c in raw.columns for c in MAPPING_10MIN):
        mapping = MAPPING_10MIN
    elif any(c in raw.columns for c in MAPPING_HOURLY):
        mapping = MAPPING_HOURLY
    else:
        raise ValueError(f"{path} has none of the expected MeteoSwiss parameter codes")
    index = pd.to_datetime(raw["reference_timestamp"], format=_TIMESTAMP_FORMAT)
    out = pd.DataFrame(index=index)
    for code, (name, factor) in mapping.items():
        if code in raw.columns:
            out[name] = pd.to_numeric(raw[code], errors="coerce").to_numpy() * factor
    out.index.name = "timestamp_utc_end"
    return out


def meteoswiss_location(stations_csv: str, station: str, utc_offset: float = 1.0) -> dict:
    """EPW location for a station from ``ogd-smn_meta_stations.csv``.

    ``utc_offset`` is the standard-time offset (1.0 for Switzerland; the data
    stay in fixed standard time, without daylight saving).
    """
    meta = pd.read_csv(stations_csv, sep=";", encoding="latin-1")
    row = meta[meta["station_abbr"] == station]
    if row.empty:
        raise ValueError(f"station '{station}' not found in {stations_csv}")
    row = row.iloc[0]
    wigos = str(row.get("station_wigos_id", ""))
    wmo = wigos.split("-")[-1] if wigos else "999999"
    return dict(
        site=str(row["station_name"]).replace(" / ", "-"),
        province=str(row["station_canton"]),
        country_code="CHE",
        type=f"MeteoSwiss-{station}",
        usaf=wmo,
        latitude=float(row["station_coordinates_wgs84_lat"]),
        longitude=float(row["station_coordinates_wgs84_lon"]),
        utc_offset=float(utc_offset),
        elevation=float(row["station_height_masl"]),
    )
