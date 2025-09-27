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
        
        if isinstance(user_pathways, list):
            self.user_pathways = user_pathways
        else:
            self.user_pathways = [user_pathways]
        
        if isinstance(percentiles, list):
            self.percentiles = percentiles
        else:
            self.percentiles = [percentiles]
            
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

        # Define variable mappings and dependencies
        variable_mapping = {
            'Temperature': ['tas', 'tasmax', 'tasmin'],
            'Humidity': ['huss'],
            'Pressure': ['psl'],
            'Wind': ['uas', 'vas'],
            'Clouds and Radiation': ['clt', 'rsds']
        }
        
        # Variables that require additional dependencies
        dependencies = {
            'Humidity': ['Temperature', 'Pressure'],
            'Dew Point': ['Temperature', 'Humidity', 'Pressure']
        }

        # Start with user variables and add dependencies
        all_required_vars = set(self.user_variables)
        
        # Check for dependencies and add missing ones
        for user_var in self.user_variables:
            if user_var in dependencies:
                missing_deps = set(dependencies[user_var]) - set(self.user_variables)
                if missing_deps:
                    dep_list = ', '.join(missing_deps)
                    print(f'{user_var} requires the morphing of {dep_list}. Adding {dep_list}')
                    all_required_vars.update(missing_deps)

        # Convert to model variables
        self.model_variables = []
        for var in all_required_vars:
            if var in variable_mapping:
                self.model_variables.extend(variable_mapping[var])
        
        # Remove duplicates
        self.model_variables = list(set(self.model_variables))
        print(self.model_variables)

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
            elif user_path == 'Upper Middle Scenario':
                self.model_pathways += ['historical', 'ssp370']
            elif user_path == 'Worst Case Scenario':
                self.model_pathways += ['historical', 'ssp585']
            else:
                pass
        self.model_pathways = list(set(self.model_pathways))
