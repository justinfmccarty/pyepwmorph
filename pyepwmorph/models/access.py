# coding=utf-8
"""
various scripts for accessing different flavors of climate models
"""

import gcsfs
import intake
import warnings

from pyepwmorph.tools import cache

warnings.filterwarnings("ignore")

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023"
__credits__ = ["Justin McCarty"]
__license__ = "GPLv3"
__version__ = "0.1"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"


def access_cmip6_data(models, pathway, variable):
    """
    Access the google cloud bucket for CMIP6 models given the pathway (ScenarioMIP), variable, and models.

    Parameters
    ----------
    models : list of strings
        a list of at least one model source
        see tools.model_sources() to learn more
    pathway : string
        the pathway to query from ['historical','ssp126','ssp245','ssp585']
    variable : string
        the variable to query from ['tas','tasmax','tasmin','clt','psl','pr','huss','vas','uas','rsds']

    Returns
    -------
    dict
        a dictionary of xarray datasets

    Examples
    --------
    >>> access_cmip6_data(['ACCESS-CM2', 'CanESM5', 'TaiESM1'], 'ssp126', 'tas')
    """
    # Define search parameters for caching
    table_id = 'Amon'  # atmospheric variables (A) saved at monthly resolution (mon)
    member_id = 'r1i1p1f1'
    
    # Check cache first
    cached_data = cache.get_cached_data(
        experiment_id=pathway,
        table_id=table_id,
        variable_id=variable,
        member_id=member_id,
        source_id=models
    )
    
    if cached_data is not None:
        return cached_data
    
    # Cache miss - fetch from Google Cloud
    gcsfs.GCSFileSystem(token='anon')
    # datastore_json = 'pangeo-cmip6.json'
    esm_data = intake.open_esm_datastore("https://storage.googleapis.com/cmip6/pangeo-cmip6.json")
    model_search = esm_data.search(experiment_id=pathway,
                                   table_id=table_id,
                                   variable_id=variable,
                                   member_id=member_id,
                                   source_id=models)

    # convert data catalog into a dictionary of xarray datasets
    dataset_dict = model_search.to_dataset_dict(zarr_kwargs={'consolidated': True, 'decode_times': False})
    
    # Save to cache before returning
    cache.save_to_cache(
        data=dataset_dict,
        experiment_id=pathway,
        table_id=table_id,
        variable_id=variable,
        member_id=member_id,
        source_id=models
    )
    
    return dataset_dict


def build_accessible_data_list():
    """
    Build a list of accessible models from the google cloud bucket for CMIP6 models

    Returns
    -------
    list
        a list of accessible model source names

    Examples
    --------
    >>> build_accessible_data_list()
    """
    gcsfs.GCSFileSystem(token='anon')
    # datastore_json = 'pangeo-cmip6.json'
    esm_data = intake.open_esm_datastore("https://storage.googleapis.com/cmip6/pangeo-cmip6.json")
    # return esm_data.df['source_id'].unique().tolist()


def clear_cmip6_cache():
    """
    Clear all cached CMIP6 data.
    
    This is useful for development or when you want to free up disk space.
    
    Examples
    --------
    >>> clear_cmip6_cache()
    """
    cache.clear_cache()


def get_cmip6_cache_stats():
    """
    Get statistics about the CMIP6 data cache.
    
    Returns information about cache size, number of files, and individual
    file details for development and monitoring purposes.
    
    Returns
    -------
    dict
        Dictionary containing cache statistics including:
        - cache_directory: Path to cache directory
        - total_files: Number of cached files
        - total_size_mb: Total cache size in MB
        - max_size_mb: Maximum allowed cache size
        - usage_percent: Percentage of max size used
        - files: List of individual file details
    
    Examples
    --------
    >>> stats = get_cmip6_cache_stats()
    >>> print(f"Cache using {stats['total_size_mb']} MB ({stats['usage_percent']}%)")
    """
    return cache.get_cache_stats()