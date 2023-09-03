# coding=utf-8
"""
management for the configuration object that is used throughout the package
"""
from pyepwmorph.tools import io as morpher_io

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


class MorphConfig(object):
    """
    Object for setting, holding, and transferring the configuration settings for various morphing scripts
        While the various config parameters are used throughout the package, the object itself is relied on only in
        tools.workflow to automate processing. It is also meant ot be leveraged in apps developed such as MESA.
    """

    def __init__(self, epw_fp):
        self.project_name = None
        self.percentiles = None
        self.output_directory = None
        self.epw_fp = epw_fp
        self.epw_str = morpher_io.read_epw_string(self.epw_fp)
        self.epw_df = morpher_io.read_epw_dataframe(self.epw_fp)
        self.location = {'latitude': None,
                         'longitude': None,
                         'elevation': None,
                         'utcoffset': None}
        self.baselinestart = None
        self.baselineend = None
        self.user_pathways = None
        self.model_pathways = None
        self.yearranges = None
        self.modelsources = None
        self.user_variables = None
        self.model_variables = None

    def assign_from_epw(self):

        dict_epw_location = morpher_io.epw_location(self.epw_str)
        self.location['latitude'] = dict_epw_location['latitude']
        self.location['longitude'] = dict_epw_location['longitude']
        self.location['elevation'] = dict_epw_location['elevation']
        self.location['utcoffset'] = dict_epw_location['utcoffset']

        baseline_range = morpher_io.epw_baseline_range(self.epw_str)
        self.baselinestart = baseline_range[0]
        self.baselineend = baseline_range[0]

    def assign_model_variables(self):
        """
        assigns the objects model variables that are used to downlaod the correct cliamte model data from the
            input variable options
        """

        self.model_variables = []
        for user_var in self.user_variables:
            if user_var == 'Temperature':
                self.model_variables += ['tas', 'tasmax', 'tasmin']
            elif user_var == 'Humidity':
                self.model_variables += ['huss']
            elif user_var == 'Pressure':
                self.model_variables += ['psl']
            elif user_var == 'Wind':
                self.model_variables += ['uas', 'vas']
            elif user_var == 'Clouds and Radiation':
                self.model_variables += ['clt', 'rsds']
            elif user_var == 'Dew Point':
                print('Dew Point requires the morphing of Temperature and Humidity')
                self.model_variables += ['tas', 'tasmax', 'tasmin', 'huss']
            else:
                pass
        self.model_variables = list(set(self.model_variables))

    def assign_model_pathways(self):
        """
        assigns the objects model pathways that are used to downlaod the correct climate model data from the
            input pathway options
        """

        self.model_pathways = []
        for user_path in self.user_pathways:
            if user_path == 'Best Case Scenario':
                self.model_pathways += ['historical', 'ssp126']
            elif user_path == 'Middle of the Road':
                self.model_pathways += ['historical', 'ssp245']
            elif user_path == 'Worst Case Scenario':
                self.model_pathways += ['historical', 'ssp585']
            else:
                pass
        self.model_variables = list(set(self.model_variables))
