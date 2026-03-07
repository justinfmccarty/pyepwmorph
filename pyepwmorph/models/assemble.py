# coding=utf-8
"""
This module creates ensembles from multiple model inputs downloaded for a single pathway and variable.
This is what enables the slicing of the data from a percentile point of view.
"""
import pandas as pd
import xarray as xr
from pyepwmorph.tools import utilities
import warnings

warnings.filterwarnings("ignore")

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"

__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"


def build_cmip6_ensemble(percentiles, variable, datasets):
    """
    Clean up the CMIP6 model data given known inconsistencies
    Additionally this script is necessary to spatially and temproally constrict the files

    Parameters
    ----------
    percentiles : list of strings
        a dictionary of xarray datasets
        the output of access.access_cmip6_data
    variable : string
        the variable that is being worked on from ['tas','tasmax','tasmin','clt','psl','pr','huss','vas','uas','rsds']
    datasets : dict
        a dictionary of xarray datasets keyed by their name from the input dict

    Returns
    -------
    df
        a pandas dataframe for the variable and pathway
            where columns are percentile and the rows are the timeseries

    Examples
    --------
    >>> build_cmip6_ensemble(['1','50','99'], 'tas', datasets)

    Raises
    ------
    ValueError
        If *datasets* is empty (no model data available).
    """
    if not datasets:
        raise ValueError(
            f"No model datasets available for variable '{variable}'. "
            f"The selected climate models may not provide this variable. "
            f"Try selecting different model sources."
        )
    ens = xr.concat(
        [ds.reset_coords(drop=True) for ds in datasets.values()],
        dim='realization'
    )
    q_values = [int(p) / 100 for p in percentiles]
    ens_perc = ens.quantile(q_values, dim='realization')
    percentile_dict = dict()
    for ptilekey in percentiles:
        q = int(ptilekey) / 100
        percentile_dict[ptilekey] = ens_perc.sel(quantile=q)[variable].to_dataframe()[variable].rename(ptilekey)

    return pd.DataFrame(percentile_dict)


def calc_model_climatologies(baseline_range, future_range, baseline_data, future_data, variable):
    """
    Given the baseline range and the future range in years, calculate the climatology for that period

    Parameters
    ----------
    baseline_range : tuple (int,int)
        the start and stop for the baseline dates to capture the cliamatology for
    future_range : tuple (int,int)
        the start and stop for the future dates to capture the cliamatology for
    baseline_data : pd.Series
        a pandas.Series for the historical data you gathered from a climate model
            the index should be a datetime index and should end where future_data starts
    future_data : pd.Series
        a pandas.Series for the future data you gathered from a climate model
            the index should be a datetime index and should start where historical_data ends
    variable : string
        the variable name for the data being processed. used to rename the output series

    Returns
    -------
    tuple
        two pandas Series, one for the baseline mean climatology and one for the future

    Examples
    --------
    >>>
    """
    # concat baseline and future into a single dataframe
    # this is important in the case that the baseline extends past 2015
    # which is typically considered the dividing point for historic data
    full_data = pd.concat([baseline_data, future_data])

    # split back into the slices
    baseline_data = utilities.pandas_slice_year(full_data, baseline_range[0], baseline_range[1])
    future_data = utilities.pandas_slice_year(full_data, future_range[0], future_range[1])

    baseline_means = utilities.monthly_means(baseline_data).rename(variable)
    future_means = utilities.monthly_means(future_data).rename(variable)


    return baseline_means, future_means