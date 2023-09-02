# coding=utf-8
"""
The package was developed to serve two purposes:
    1. develop piecemeal functions for dealing with various EPW morphing tasks
    2. provide succinct workflows of those tools to automate the process of intaking climate data and morphing an EPW file
The second task is dealt with throughout the following scripts
"""
from morpher.models import access, coordinate, assemble

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


def compile_climate_model_data(config_object, pathway, variable):
    """
    Clean up the CMIP6 model data given known inconsistencies
    Additionally this script is necessary to spatially and temproally constrict the files

    Parameters
    ----------
    config_object : object
        a configuration.MorphConfig object with parameters specified
            this script needs pathways, variables, modelsources, location
    pathway : string
        the pathway that is being worked on from ['historical','ssp126','ssp245','ssp585']
    variable : string
        the variable that is being worked on from ['tas','tasmax','tasmin','clt','psl','pr','huss','vas','uas','rsds']

    Returns
    -------
    df
        a pandas dataframe for the variable and pathway
            where columns are percentile and the rows are the timeseries

    Examples
    --------
    >>> compile_climate_model_data(config_object, 'historical', 'tas')
    """

    dataset_dict = access.access_cmip6_data(config_object.modelsources,
                                            pathway,
                                            variable)
    dataset_dict = coordinate.coordinate_cmip6_data(config_object.location['latitude'],
                                                    config_object.location['longitude'],
                                                    pathway,
                                                    dataset_dict)
    return assemble.build_cmip6_ensemble(dataset_dict,
                                         variable,
                                         pathway,
                                         config_object.percentiles)


def iterate_compile_model_data(config_object):
    """
    Clean up the CMIP6 model data given known inconsistencies
    Additionally this script is necessary to spatially and temproally constrict the files

    Parameters
    ----------
    config_object : object
        a configuration.MorphConfig object with parameters specified
            this script needs pathways, variables, modelsources, location

    Returns
    -------
    dict
        a dict of pandas dataframes where pathway is the first key and the child key is variable

    Examples
    --------
    >>> iterate_compile_config_object(config_object)
    """
    model_data_dict = {}

    for pathway in config_object.pathways:
        model_data_dict[pathway] = {}
        for variable in config_object.variables:
            print(f"Compiling model data for '{pathway}'>' and '{variable}'.")
            model_data_dict[pathway][variable] = compile_climate_model_data(config_object, pathway, variable)

    return model_data_dict
