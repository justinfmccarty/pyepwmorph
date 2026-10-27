"""Coordinate CMIP6 model data into a standard grid and time system.

Climate model data comes in varied grid systems and temporal indices.
These functions spatially select and temporally slice the data before
it is fed to the morphing algorithm.
"""

import logging
import math

import dask
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

DEFAULT_TIME_SLICES = {
    'historical': ('1960', '2014'),
}
DEFAULT_SSP_SLICE = ('2015', '2100')

EARTH_RADIUS_KM = 6371.0


def wrapped_longitude_difference(grid_longitudes, longitude):
    """Signed longitude difference in degrees, wrapped to [-180, 180).

    Works whatever convention the grid uses (0..360 or -180..180), so a site
    at -74 deg finds the cell at 286 deg, and a site at -0.2 deg finds the
    cell at 0 deg across the seam.
    """
    return (np.asarray(grid_longitudes, dtype=float) - float(longitude) + 180.0) % 360.0 - 180.0


def nearest_cell_indices(grid_latitudes, grid_longitudes, latitude, longitude):
    """Indices of the grid cell nearest to a site on a regular lat/lon grid.

    Latitude is matched directly. Longitude is matched on the circular
    distance, because EPW longitudes run -180..180 while many CMIP6 grids
    run 0..360 (``ds.sel(..., method='nearest')`` would snap every
    western-hemisphere site to the cell at 0 deg).

    Returns
    -------
    tuple[int, int]
        ``(lat_index, lon_index)``
    """
    lat_index = int(np.argmin(np.abs(np.asarray(grid_latitudes, dtype=float) - float(latitude))))
    lon_index = int(np.argmin(np.abs(wrapped_longitude_difference(grid_longitudes, longitude))))
    return lat_index, lon_index


def great_circle_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points given in degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlam = math.radians(float(wrapped_longitude_difference([lon2], lon1)[0]))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def select_nearest_cell(ds, latitude, longitude):
    """Select the grid cell nearest to a site, wrapping longitude correctly."""
    lat_index, lon_index = nearest_cell_indices(ds['lat'].values, ds['lon'].values, latitude, longitude)
    return ds.isel(lat=lat_index, lon=lon_index)


def source_label(name):
    """Short model label for a dataset key.

    Keys are intake-esm group names (``activity.institution.source.experiment.table.grid``)
    or zarr store URLs (``gs://cmip6/CMIP6/<activity>/<institution>/<source>/...``,
    as used by the Boundary Conditions app). Unknown shapes are returned as they are.
    """
    text = str(name)
    if "/" in text:
        parts = [part for part in text.split("/") if part]
        if "CMIP6" in parts:
            index = parts.index("CMIP6")
            if len(parts) > index + 3:
                return parts[index + 3]
        return text
    parts = text.split(".")
    return parts[2] if len(parts) >= 3 else text


def cell_summary(datasets, latitude, longitude):
    """Describe the grid cell each model's data came from.

    Parameters
    ----------
    datasets : dict
        Output of ``coordinate_cmip6_data`` (one dataset per model store),
        each still carrying scalar ``lat``/``lon`` coordinates.
    latitude, longitude : float
        The site.

    Returns
    -------
    dict
        ``{name: {"lat": ..., "lon": ..., "distance_km": ...}}`` with ``lon``
        in -180..180. Datasets without scalar coordinates (for example cache
        entries from older releases) are skipped.
    """
    cells = {}
    for name, ds in datasets.items():
        try:
            cell_lat = float(ds['lat'].values)
            cell_lon = float(ds['lon'].values)
        except (KeyError, TypeError, ValueError):
            continue
        cell_lon = (cell_lon + 180.0) % 360.0 - 180.0
        cells[name] = {
            "lat": round(cell_lat, 3),
            "lon": round(cell_lon, 3),
            "distance_km": round(great_circle_km(latitude, longitude, cell_lat, cell_lon), 1),
        }
    return cells


def coordinate_cmip6_data(
    latitude,
    longitude,
    pathway,
    variable,
    dset_dict,
    time_slices=None,
):
    """Spatially select and temporally slice CMIP6 data for a location.

    Parameters
    ----------
    latitude : float
        Latitude of the location.
    longitude : float
        Longitude of the location.
    pathway : str
        Experiment / scenario ID (e.g. ``'historical'``, ``'ssp245'``).
    variable : str
        Climate variable being processed.
    dset_dict : dict
        Dictionary of xarray Datasets from ``access.access_cmip6_data``.
    time_slices : dict or None
        Optional override for temporal slicing.  Keys are pathway names,
        values are ``(start, end)`` string tuples.  Any pathway not in
        the dict falls back to ``DEFAULT_SSP_SLICE``.

    Returns
    -------
    dict
        Dictionary of computed xarray Datasets keyed by source name.

    Notes
    -----
    Caching lives in ``workflow.compile_climate_model_data`` so that a cache
    hit avoids opening the remote catalogue at all.  Calling this function
    directly always recomputes.
    """
    slices = {**DEFAULT_TIME_SLICES}
    if time_slices:
        slices.update(time_slices)

    time_start, time_end = slices.get(pathway, DEFAULT_SSP_SLICE)

    ds_dict = {}
    for name, ds in dset_dict.items():
        if ('longitude' in ds.dims) and ('latitude' in ds.dims):
            ds = ds.rename({'longitude': 'lon', 'latitude': 'lat'})

        ds = xr.decode_cf(ds)
        ds = ds.sel(time=slice(time_start, time_end))
        ds = select_nearest_cell(ds, latitude, longitude)

        for coord in list(ds.coords):
            if coord not in ['lat', 'lon', 'time']:
                ds = ds.drop_vars(coord)

        ds.coords['year'] = ds.time.dt.year
        ds.coords['time'] = xr.date_range(
            start=str(ds.time.dt.year.values[0]),
            periods=len(ds.time.dt.year.values),
            freq="MS",
            calendar="standard",
            use_cftime=False,
        )

        for d in ds.dims:
            if d != 'time':
                ds[variable] = ds[variable].sel({f'{d}': 0}, drop=True)

        ds_dict[name] = ds

    return dask.compute(ds_dict)[0]
