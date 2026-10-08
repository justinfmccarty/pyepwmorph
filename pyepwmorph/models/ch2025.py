"""Offline access to MeteoSwiss CH2025 station scenarios.

The monthly climatologies in ``pyepwmorph/data`` are reduced from the
DAILY-LOCAL product. Each row is one model chain's mean for a calendar
month, over the 30 synthetic climate years of a reference state or a
global warming level.

CH2025 data © MeteoSwiss & ETH Zurich, licensed CC-BY 4.0.
https://doi.org/10.18751/climate/scenarios/ch2025/data/1.0/
"""

import logging
from functools import lru_cache
from importlib.resources import files

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: (west, south, east, north) of the CH2025 gridded domain, in degrees.
CH2025_BBOX = (5.96, 45.82, 10.49, 47.81)

CH2025_REFERENCE = "ref91-20"
CH2025_BASELINE_RANGE = (1991, 2020)
CH2025_STATES = ("gwl1.5", "gwl2.0", "gwl2.5", "gwl3.0")
CH2025_VARIABLES = frozenset({"tas", "tasmax", "tasmin", "hurs", "rsds", "sfcWind"})

#: Variables whose change is a difference (future - reference). The others
#: (``hurs``, ``rsds``, ``sfcWind``) change as a ratio, matching how the
#: morphing procedures apply them.
CH2025_ADDITIVE_VARIABLES = frozenset({"tas", "tasmax", "tasmin"})

#: Short attribution written into morphed EPW comments. No commas: EPW
#: header fields are comma delimited.
CH2025_CITATION = (
    "CH2025 (c) MeteoSwiss and ETH Zurich CC-BY 4.0 "
    "doi:10.18751/climate/scenarios/ch2025/data/1.0"
)

#: Kilometres of horizontal distance treated as equal to 100 m of elevation,
#: so a station far below or above the site loses to a nearer-altitude one.
DEFAULT_ELEVATION_WEIGHT_KM_PER_100M = 10.0
WARN_DISTANCE_KM = 25.0
WARN_ELEVATION_M = 300.0


def _read_parquet(name: str) -> pd.DataFrame:
    resource = files("pyepwmorph.data").joinpath(name)
    with resource.open("rb") as handle:
        return pd.read_parquet(handle)


@lru_cache(maxsize=1)
def load_table() -> pd.DataFrame:
    """Return the shipped monthly climatology table.

    Columns are ``station_id``, ``variable``, ``state``, ``chain``,
    ``month``, and ``value``. The frame is cached; do not mutate it.
    """
    return _read_parquet("ch2025_monthly.parquet")


@lru_cache(maxsize=1)
def _load_stations() -> pd.DataFrame:
    return _read_parquet("ch2025_stations.parquet")


def available_stations(variables=None) -> pd.DataFrame:
    """Return stations, optionally limited to those carrying every variable.

    Parameters
    ----------
    variables : iterable of str or None
        Model variable ids that a station must provide. ``None`` returns
        every station in the shipped table.
    """
    stations = _load_stations().copy()
    if variables is None:
        return stations.reset_index(drop=True)
    needed = set(variables)
    mask = stations["variables"].map(lambda present: needed <= set(present))
    return stations.loc[mask].reset_index(drop=True)


def reference_key(state: str) -> str:
    """Key under which the reference paired with *state* is stored.

    Each warming level is compared with the reference over the model chains
    the two share, so the reference climatology differs per warming level.
    """
    return f"{CH2025_REFERENCE}|{state}"


def baseline_matches(baseline_range) -> bool:
    """Return whether an EPW baseline is exactly the CH2025 reference period."""
    return tuple(int(year) for year in baseline_range) == CH2025_BASELINE_RANGE


def in_switzerland(latitude: float, longitude: float) -> bool:
    """Return whether a point lies inside the CH2025 domain."""
    west, south, east, north = CH2025_BBOX
    return south <= latitude <= north and west <= longitude <= east


def _haversine_km(latitude, longitude, latitudes, longitudes) -> np.ndarray:
    radius = 6371.0
    lat1 = np.radians(latitude)
    lat2 = np.radians(np.asarray(latitudes, dtype=float))
    dlat = lat2 - lat1
    dlon = np.radians(np.asarray(longitudes, dtype=float) - longitude)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * radius * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def nearest_station(
    latitude: float,
    longitude: float,
    elevation: float,
    variables=None,
    elevation_weight_km_per_100m: float = DEFAULT_ELEVATION_WEIGHT_KM_PER_100M,
) -> pd.Series:
    """Pick the station that best matches a site.

    The score is horizontal distance plus an elevation penalty, so a
    station hundreds of metres higher loses to one farther away at a
    similar altitude. Only stations that carry every requested variable
    are eligible.

    Returns
    -------
    pd.Series
        The station row, with ``distance_km`` and ``elevation_difference_m``.
    """
    candidates = available_stations(variables)
    if candidates.empty:
        needed = ", ".join(sorted(variables or []))
        raise ValueError(f"No CH2025 station provides {needed or 'any variables'}")

    distance = _haversine_km(
        latitude, longitude, candidates["latitude"], candidates["longitude"],
    )
    elevation_difference = candidates["elevation"].to_numpy(dtype=float) - float(elevation)
    penalty = np.abs(elevation_difference) / 100.0 * elevation_weight_km_per_100m
    position = int(np.argmin(distance + penalty))
    chosen = candidates.iloc[position].copy()
    chosen["distance_km"] = float(distance[position])
    chosen["elevation_difference_m"] = float(elevation_difference[position])
    chosen["weak_match"] = bool(
        chosen["distance_km"] > WARN_DISTANCE_KM
        or abs(chosen["elevation_difference_m"]) > WARN_ELEVATION_M
    )

    logger.info(
        "CH2025 station %s (%s): %.1f km away, %+.0f m elevation",
        chosen["station_id"],
        chosen["name"],
        chosen["distance_km"],
        chosen["elevation_difference_m"],
    )
    if chosen["weak_match"]:
        logger.warning(
            "CH2025 station %s is a weak match (%.1f km, %+.0f m). "
            "The morphed file uses that station's climate signal.",
            chosen["station_id"],
            chosen["distance_km"],
            chosen["elevation_difference_m"],
        )
    return chosen


def _check_variable(variable):
    if variable not in CH2025_VARIABLES:
        raise ValueError(
            f"Variable '{variable}' is not in the CH2025 station table. "
            f"Available: {sorted(CH2025_VARIABLES)}"
        )


def _chains_by_month(station_id, variable, state) -> pd.DataFrame:
    """Return a month x chain table for one station, variable, and state."""
    table = load_table()
    subset = table[
        (table["station_id"] == station_id)
        & (table["variable"] == variable)
        & (table["state"] == state)
    ]
    if subset.empty:
        raise ValueError(
            f"No CH2025 data for station '{station_id}', variable '{variable}', state '{state}'"
        )
    return subset.pivot(index="month", columns="chain", values="value").sort_index()


def build_ch2025_change_ensemble(percentiles, variable, station_id, state):
    """Build reference and warming-level climatologies from paired chain changes.

    Each model chain's change from the reference to *state* is computed
    first, over the chains present in both, and the percentiles are taken
    of those changes. Taking percentiles of each state separately and
    differencing them would mix chains, and at the tails can even flip the
    sign of the change.

    The reference returned is the median of the paired chains, the same for
    every percentile column. The warming-level frame is that reference plus
    the percentile change (temperatures) or times the percentile ratio
    (humidity, radiation, wind), so the morphing procedures recover exactly
    the percentile change.

    Parameters
    ----------
    percentiles : list
        Ensemble percentiles. Column labels match these values.
    variable : str
        One of ``CH2025_VARIABLES``.
    station_id : str
        Lower-case station abbreviation, for example ``"sma"``.
    state : str
        A warming level such as ``"gwl2.0"``.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        ``(reference, future)``, each with twelve rows (months 1-12) and one
        column per percentile. ``attrs["n_chains"]`` on both records how many
        paired chains contributed.
    """
    _check_variable(variable)
    reference = _chains_by_month(station_id, variable, CH2025_REFERENCE)
    future = _chains_by_month(station_id, variable, state)
    common = reference.columns.intersection(future.columns)
    if len(common) == 0:
        raise ValueError(
            f"No CH2025 model chain provides both {CH2025_REFERENCE} and {state} "
            f"for station '{station_id}', variable '{variable}'"
        )
    reference = reference[common]
    future = future[common]
    baseline = reference.median(axis=1)

    if variable in CH2025_ADDITIVE_VARIABLES:
        change = future - reference
    else:
        ref_values = reference.to_numpy(dtype=float)
        change = pd.DataFrame(
            np.divide(
                future.to_numpy(dtype=float), ref_values,
                out=np.ones_like(ref_values), where=ref_values != 0,
            ),
            index=reference.index, columns=reference.columns,
        )

    reference_frame = pd.DataFrame({percentile: baseline for percentile in percentiles})
    future_columns = {}
    for percentile in percentiles:
        quantile = change.quantile(int(percentile) / 100.0, axis=1)
        if variable in CH2025_ADDITIVE_VARIABLES:
            future_columns[percentile] = baseline + quantile
        else:
            future_columns[percentile] = baseline * quantile
    future_frame = pd.DataFrame(future_columns)

    for frame in (reference_frame, future_frame):
        frame.index.name = "month"
        frame.attrs["n_chains"] = int(len(common))
    return reference_frame, future_frame


def build_ch2025_ensemble(percentiles, variable, station_id, state) -> pd.DataFrame:
    """Reduce one station, variable, and state to percentile climatologies.

    Parameters
    ----------
    percentiles : list
        Ensemble percentiles. Column labels match these values, as in
        ``assemble.build_cmip6_ensemble``.
    variable : str
        One of ``CH2025_VARIABLES``.
    station_id : str
        Lower-case station abbreviation, for example ``"sma"``.
    state : str
        ``"ref91-20"`` or a warming level such as ``"gwl2.0"``.

    Returns
    -------
    pd.DataFrame
        Twelve rows (months 1-12) and one column per percentile.
        ``attrs["n_chains"]`` records how many model chains contributed.
        Membership differs by variable and warming level.

    Morphing does not use this: differencing two separately reduced states
    mixes model chains. See ``build_ch2025_change_ensemble``.
    """
    _check_variable(variable)
    wide = _chains_by_month(station_id, variable, state)
    result = pd.DataFrame(
        {percentile: wide.quantile(int(percentile) / 100.0, axis=1) for percentile in percentiles}
    )
    result.index.name = "month"
    result.attrs["n_chains"] = int(wide.shape[1])
    return result
