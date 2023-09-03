# coding=utf-8
"""
various scripts for accessing different flavors of climate models
"""

import gcsfs
import intake
import warnings

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
    gcsfs.GCSFileSystem(token='anon')
    # datastore_json = 'pangeo-cmip6.json'
    esm_data = intake.open_esm_datastore("https://storage.googleapis.com/cmip6/pangeo-cmip6.json")
    model_search = esm_data.search(experiment_id=pathway,
                                   table_id='Amon',  # atmospheric variables (A) saved at monthly resolution (mon)
                                   variable_id=variable,
                                   member_id='r1i1p1f1',
                                   source_id=models)

    # convert data catalog into a dictionary of xarray datasets
    return model_search.to_dataset_dict(zarr_kwargs={'consolidated': True, 'decode_times': False})
