# coding=utf-8
"""Coordinate CMIP6 model data into a standard grid and time system.

Climate model data comes in varied grid systems and temporal indices.
These functions spatially select and temporally slice the data before
it is fed to the morphing algorithm.
"""

import logging
import time
import warnings

import dask
import pandas as pd
import xarray as xr

from pyepwmorph.tools import cache

warnings.filterwarnings("ignore")
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
    """
    slices = {**DEFAULT_TIME_SLICES}
    if time_slices:
        slices.update(time_slices)

    source_ids = list(dset_dict.keys())
    model_names = []
    for source_id in source_ids:
        parts = source_id.split('.')
        if len(parts) >= 3:
            model_names.append(parts[2])
        else:
            model_names.append(source_id)

    cached_data = cache.get_cached_coordinate_data(
        latitude=latitude,
        longitude=longitude,
        pathway=pathway,
        variable=variable,
        source_id=model_names,
    )
    if cached_data is not None:
        return cached_data

    time_start, time_end = slices.get(pathway, DEFAULT_SSP_SLICE)

    ds_dict = {}
    for name, ds in dset_dict.items():
        if ('longitude' in ds.dims) and ('latitude' in ds.dims):
            ds = ds.rename({'longitude': 'lon', 'latitude': 'lat'})

        ds = xr.decode_cf(ds)
        ds = ds.sel(time=slice(time_start, time_end))
        ds = ds.sel(lat=latitude, lon=longitude, method='nearest')

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

    datasets = dask.compute(ds_dict)[0]

    cache.save_coordinate_to_cache(
        data=datasets,
        latitude=latitude,
        longitude=longitude,
        pathway=pathway,
        variable=variable,
        source_id=model_names,
    )

    return datasets
