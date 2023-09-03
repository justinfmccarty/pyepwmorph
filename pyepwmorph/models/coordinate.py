# coding=utf-8
"""
climate model data comes in a variety of shapes forms and sizes (grid systems, temporal indices, etc.)
these scripts provide help to coordinate them into a standard system before being processed by the algorithm,
"""
import xarray as xr
import warnings
import dask
warnings.filterwarnings("ignore")

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023"
__credits__ = ["Justin McCarty"]
__license__ = "GPLv3"
__version__ = "0.1"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

def coordinate_cmip6_data(latitude, longitude, pathway, variable, dset_dict):
    """
    Clean up the CMIP6 model data given known inconsistencies
    Additionally this script is necessary to spatially and temproally constrict the files

    Parameters
    ----------
    latitude : float
        the latitude of the location
    longitude : float
        the longitude of the location
    pathway : string
        the pathway that is being worked on from ['historical','ssp126','ssp245','ssp585']
    dset_dict : dict
        a dictionary of xarray datasets
        the output of access.access_cmip6_data

    Returns
    -------
    dict
        a dictionary of xarray datasets keyed by their name from the input dict

    Examples
    --------
    >>> coordinate_cmip6_data(49.267, -122.301, 'ssp126', 'tas', dset_dict)
    """

    # set the blank dict for the datasets to be placed in keyed by source_id
    ds_dict = {}
    for name, ds in dset_dict.items():
        print(name)
        # rename spatial dimensions if necessary
        if ('longitude' in ds.dims) and ('latitude' in ds.dims):
            ds = ds.rename({'longitude': 'lon', 'latitude': 'lat'})  # some models labelled dimensions differently...

        # temporary hack, not sure why I need this but has to do with calendar-aware metadata on the time variable
        ds = xr.decode_cf(ds)

        # cosntrict the bounds of the file based on pathway or historical
        if 'historical' in pathway:
            ds = ds.sel(time=slice('1960', '2014'))
        else:
            ds = ds.sel(time=slice('2015', '2100'))

        # select the spatially relevant data
        ds = ds.sel(lat=latitude, lon=longitude, method='nearest')

        # drop redundant variables (like "height: 2m")
        for coord in ds.coords:
            if coord not in ['lat', 'lon', 'time']:
                ds = ds.drop_vars(coord)

        # formalize the index datatypes
        ds.coords['year'] = ds.time.dt.year
        ds.coords['time'] = xr.date_range(start=str(ds.time.dt.year.values[0]),
                                            periods=len(ds.time.dt.year.values),
                                            freq="MS", calendar="standard",
                                            use_cftime=False)

        # Add variable array to dictionary
        for d in ds.dims:
            if d == 'time':
                pass
            else:
                ds[variable] = ds[variable].sel({f'{d}': 0}, drop=True)

        ds_dict[name] = ds

    datasets = dask.compute(ds_dict)[0]

    return datasets


