# coding=utf-8
"""
management for the configuration object that is used throughout the package
"""
from pathlib import Path
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
        tools.workflow to automate processing.
    """

    def __init__(self, project_name, epw_fp, user_variables, user_pathways, percentiles, future_years,
                 output_directory, model_sources=None, baseline_range=None):
        if model_sources is None:
            model_sources = ['ACCESS-CM2', 'CanESM5', 'TaiESM1']
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
        self.baseline_range = baseline_range
        self.future_years = future_years

        self.model_pathways = []
        self.model_variables = []
        if output_directory is None:
            pass
        else:
            self.output_directory = output_directory
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)


        self.assign_from_epw()
        self.assign_model_variables()
        self.assign_model_pathways()

    def assign_from_epw(self):

        self.location['latitude'] = self.epw.location['latitude']
        self.location['longitude'] = self.epw.location['longitude']
        self.location['elevation'] = self.epw.location['elevation']
        self.location['utc_offset'] = self.epw.location['utc_offset']
        if self.baseline_range is None:
            self.baseline_range = self.epw.detect_baseline_range()

    def assign_model_variables(self):
        """
        assigns the objects model variables that are used to download the correct climate model data from the
            input variable options
        """

        self.model_variables = []
        for user_var in self.user_variables:
            if user_var == 'Temperature':
                self.model_variables += ['tas', 'tasmax', 'tasmin']
            elif user_var == 'Humidity':
                self.model_variables += ['huss']
                if ('Temperature' in self.user_variables) and ('Pressure' in self.user_variables):
                    pass
                elif ('Temperature' in self.user_variables) and ('Pressure' not in self.user_variables):
                    print('Humidity requires the morphing of Temperature and Pressure. Adding Pressure')
                    self.model_variables += ['psl']
                elif ('Temperature' not in self.user_variables) and ('Pressure' in self.user_variables):
                    print('Humidity requires the morphing of Temperature and Pressure. Adding Temperature')
                    self.model_variables += ['tas', 'tasmax', 'tasmin']
                elif ('Temperature' not in self.user_variables) and ('Pressure' not in self.user_variables):
                    print('Humidity requires the morphing of Temperature and Pressure. Adding both')
                    self.model_variables += ['tas', 'tasmax', 'tasmin', 'psl']
            elif user_var == 'Pressure':
                self.model_variables += ['psl']
            elif user_var == 'Wind':
                self.model_variables += ['uas', 'vas']
            elif user_var == 'Clouds and Radiation':
                self.model_variables += ['clt', 'rsds']
            elif user_var == 'Dew Point':
                if ('Temperature' in self.user_variables) and ('Humidity' in self.user_variables):
                    pass
                elif ('Temperature' in self.user_variables) and ('Humidity' not in self.user_variables):
                    print('Dew Point requires the morphing of Temperature and Humidity. Adding Humidity')
                    self.model_variables += ['huss']
                elif ('Temperature' not in self.user_variables) and ('Humidity' in self.user_variables):
                    print('Dew Point requires the morphing of Temperature and Humidity. Adding Temperature')
                    self.model_variables += ['tas', 'tasmax', 'tasmin']
                elif ('Temperature' not in self.user_variables) and ('Humidity' not in self.user_variables):
                    print('Dew Point requires the morphing of Temperature and Humidity. Adding both')
                    self.model_variables += ['tas', 'tasmax', 'tasmin', 'huss']
            else:
                pass
        print(self.model_variables)
        self.model_variables = list(set(self.model_variables))

    def assign_model_pathways(self):
        """
        assigns the objects model pathways that are used to download the correct climate model data from the
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
        self.model_pathways = list(set(self.model_pathways))
