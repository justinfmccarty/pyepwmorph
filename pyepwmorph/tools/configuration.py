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

    def __init__(self, project_name, epw_fp, model_sources, user_variables, user_pathways, percentiles, output_directory):
        self.project_name = project_name
        self.epw = morpher_io.Epw(epw_fp)
        self.model_sources = model_sources
        self.user_variables = user_variables
        self.user_pathways = user_pathways
        self.percentiles = percentiles

        self.location = {'latitude': None,
                         'longitude': None,
                         'elevation': None,
                         'utc_offset': None}
        self.baseline_range = ()
        self.model_pathways = []
        self.future_years = []
        self.future_ranges = []
        self.model_variables = []

        self.output_directory = output_directory

        self.assign_from_epw()
        self.assign_model_variables()
        self.assign_model_pathways()

    def assign_from_epw(self):

        self.location['latitude'] = self.epw.location['latitude']
        self.location['longitude'] = self.epw.location['longitude']
        self.location['elevation'] = self.epw.location['elevation']
        self.location['utc_offset'] = self.epw.location['utc_offset']
        self.baseline_range = self.epw.detect_baseline_range()

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
