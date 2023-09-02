# coding=utf-8
"""
management for the configuration object that is used throughout the package
"""
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
    It is also meant ot be leveraged in apps developed such as MESA.
    """

    def __init__(self):
        self.project_name = None
        self.percentiles = None
        self.output_directory = None
        self.epw = None
        self.location = {'latitude':None,
                         'longitude':None,
                         'elevation':None,
                         'utcoffset':None}
        self.baselinestart = None
        self.baselineend = None
        self.pathwaylist = None
        self.yearranges = None
        self.modelsources = None
        self.variables = None


