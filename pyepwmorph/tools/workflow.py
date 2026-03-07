# coding=utf-8
"""High-level workflows for compiling climate data and morphing EPW files.

Supports both CMIP6 (Pangeo) and custom CSV-based climate model data.
"""

import copy
import datetime
import logging
import os
import warnings

from pyepwmorph.models import access, coordinate, assemble, custom
from pyepwmorph.morph import procedures
from pyepwmorph.tools import io as morph_io
from pyepwmorph.tools import utilities as morph_utils
from pyepwmorph.tools import configuration as morph_config

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"


# ---------------------------------------------------------------------------
# CMIP6 data compilation (unchanged from v1)
# ---------------------------------------------------------------------------

def compile_climate_model_data(model_sources, pathway, variable, longitude, latitude, percentiles):
    """Fetch, spatially select, and ensemble CMIP6 data for one pathway + variable.

    Returns
    -------
    pd.DataFrame
        Columns keyed by percentile, rows are the monthly time series.
    """
    dataset_dict = access.access_cmip6_data(model_sources, pathway, variable)
    dataset_dict = coordinate.coordinate_cmip6_data(
        latitude, longitude, pathway, variable, dataset_dict,
    )
    return assemble.build_cmip6_ensemble(percentiles, variable, dataset_dict)


def iterate_compile_model_data(pathways, variables, model_sources, longitude, latitude, percentiles):
    """Iterate over pathways x variables and compile CMIP6 model data.

    Returns
    -------
    dict[str, dict[str, pd.DataFrame]]
        ``model_data_dict[pathway][variable]`` = DataFrame (percentile columns).

    Raises
    ------
    RuntimeError
        If no data could be fetched for any pathway/variable combination.
    """
    model_data_dict = {}
    failed = []
    for pathway in pathways:
        model_data_dict[pathway] = {}
        for variable in variables:
            logger.info("Compiling model data for '%s' / '%s'", pathway, variable)
            try:
                result = compile_climate_model_data(
                    model_sources, pathway, variable, longitude, latitude, percentiles,
                )
                model_data_dict[pathway][variable] = result
            except ValueError as exc:
                logger.warning(
                    "No data for pathway='%s', variable='%s': %s", pathway, variable, exc,
                )
                failed.append((pathway, variable))

    if failed and not any(model_data_dict[p] for p in model_data_dict):
        summary = "; ".join(f"{p}/{v}" for p, v in failed)
        raise RuntimeError(
            f"Could not fetch any climate model data. "
            f"Failed combinations: {summary}. "
            f"Check your network connection and try fewer model sources."
        )

    if failed:
        summary = "; ".join(f"{p}/{v}" for p, v in failed)
        logger.warning("Some data could not be fetched: %s", summary)

    return model_data_dict


# ---------------------------------------------------------------------------
# Custom CSV data compilation
# ---------------------------------------------------------------------------

def compile_custom_model_data(custom_data, variables, percentile=50):
    """Load custom CSV data for all scenarios and variables.

    Parameters
    ----------
    custom_data : dict[str, dict[str, str]]
        ``{scenario_label: {variable: csv_path, ...}, ...}``
    variables : list[str]
        Model variable names to load.
    percentile : int
        Percentile label for single-member data.

    Returns
    -------
    dict[str, dict[str, pd.DataFrame]]
        Same nested structure as ``iterate_compile_model_data`` returns.
    """
    model_data_dict = {}
    for scenario, csv_paths in custom_data.items():
        model_data_dict[scenario] = {}
        for variable in variables:
            if variable not in csv_paths:
                raise ValueError(
                    f"Custom data for scenario '{scenario}' is missing variable '{variable}'"
                )
            logger.info("Loading custom data for '%s' / '%s'", scenario, variable)
            model_data_dict[scenario][variable] = custom.load_custom_csv(
                csv_paths[variable], variable, percentile=percentile,
            )
    return model_data_dict


# ---------------------------------------------------------------------------
# Morphing
# ---------------------------------------------------------------------------

def morph_epw(
    epw_file,
    user_variables,
    baseline_range,
    target_range,
    model_data_dict,
    pathway,
    percentile,
    reference_scenario="historical",
):
    """Apply morphing procedures to an EPW file.

    Parameters
    ----------
    epw_file : str or Epw
        Path to EPW file, or an in-memory ``Epw`` object.
    user_variables : list[str]
        Variables to morph.
    baseline_range : tuple[int, int]
        ``(start_year, end_year)`` for the reference/baseline period.
    target_range : tuple[int, int]
        ``(start_year, end_year)`` for the target period.
    model_data_dict : dict
        Nested dict ``[scenario][variable]`` -> DataFrame with percentile columns.
    pathway : str
        Target scenario key in *model_data_dict*.
    percentile : int
        Percentile column to select from the DataFrames.
    reference_scenario : str
        Key in *model_data_dict* for the baseline/reference data.
        Defaults to ``"historical"``.

    Returns
    -------
    Epw
        A deep-copied Epw object with morphed data applied.
    """
    if isinstance(epw_file, str):
        epw_object = morph_io.Epw(epw_file)
    else:
        epw_object = copy.deepcopy(epw_file)

    ref = reference_scenario
    morphed_dict = {}

    def _get_series(scenario, var, pctile):
        """Retrieve a percentile series from model_data_dict with clear errors."""
        if scenario not in model_data_dict:
            raise KeyError(
                f"Scenario '{scenario}' not found in model data. "
                f"Available scenarios: {list(model_data_dict.keys())}"
            )
        if var not in model_data_dict[scenario]:
            raise KeyError(
                f"Variable '{var}' not found in model data for scenario '{scenario}'. "
                f"Available variables: {list(model_data_dict[scenario].keys())}. "
                f"The selected climate models may not provide this variable."
            )
        return model_data_dict[scenario][var][pctile]

    for variable in user_variables:
        if variable == 'Temperature':
            if 'drybulb_C' in morphed_dict:
                continue
            tas_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'tas', percentile),
                _get_series(pathway, 'tas', percentile), 'tas',
            )
            tmax_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'tasmax', percentile),
                _get_series(pathway, 'tasmax', percentile), 'tasmax',
            )
            tmin_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'tasmin', percentile),
                _get_series(pathway, 'tasmin', percentile), 'tasmin',
            )
            present_dbt = epw_object.dataframe['drybulb_C']
            morphed_dbt = procedures.morph_dbt_year(
                present_dbt,
                tas_climatologies[1], tas_climatologies[0],
                tmax_climatologies[1], tmax_climatologies[0],
                tmin_climatologies[1], tmin_climatologies[0],
            ).values
            morphed_dict['drybulb_C'] = morphed_dbt

        elif variable == 'Humidity':
            if 'relhum_percent' in morphed_dict:
                continue
            relhum_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'huss', percentile),
                _get_series(pathway, 'huss', percentile), 'huss',
            )
            present_relhum = epw_object.dataframe['relhum_percent']
            present_psl = epw_object.dataframe['atmos_Pa']
            present_dbt = epw_object.dataframe['drybulb_C']

            if 'atmos_Pa' in morphed_dict and 'drybulb_C' in morphed_dict:
                morphed_relhum = procedures.morph_relhum(
                    present_relhum, present_psl, present_dbt,
                    morphed_dict['atmos_Pa'], morphed_dict['drybulb_C'],
                    relhum_climatologies[1], relhum_climatologies[0],
                ).values
            else:
                tas_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'tas', percentile),
                    _get_series(pathway, 'tas', percentile), 'tas',
                )
                tmax_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'tasmax', percentile),
                    _get_series(pathway, 'tasmax', percentile), 'tasmax',
                )
                tmin_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'tasmin', percentile),
                    _get_series(pathway, 'tasmin', percentile), 'tasmin',
                )
                morphed_dbt = procedures.morph_dbt_year(
                    present_dbt,
                    tas_climatologies[1], tas_climatologies[0],
                    tmax_climatologies[1], tmax_climatologies[0],
                    tmin_climatologies[1], tmin_climatologies[0],
                ).values

                if 'atmos_Pa' in morphed_dict:
                    morphed_psl = morphed_dict['atmos_Pa']
                else:
                    psl_climatologies = assemble.calc_model_climatologies(
                        baseline_range, target_range,
                        _get_series(ref, 'psl', percentile),
                        _get_series(pathway, 'psl', percentile), 'psl',
                    )
                    morphed_psl = procedures.morph_psl(
                        present_psl, psl_climatologies[1], psl_climatologies[0],
                    ).values
                    if "Pressure" in user_variables:
                        morphed_dict['atmos_Pa'] = morphed_psl

                morphed_relhum = procedures.morph_relhum(
                    present_relhum, present_psl, present_dbt,
                    morphed_psl, morphed_dbt,
                    relhum_climatologies[1], relhum_climatologies[0],
                ).values

            morphed_dict['relhum_percent'] = morphed_relhum

        elif variable == 'Dew Point':
            if 'relhum_percent' in morphed_dict and 'drybulb_C' in morphed_dict:
                morphed_dewpt = procedures.morph_dewpt(
                    morphed_dict['drybulb_C'], morphed_dict['relhum_percent'],
                )
                morphed_dict['dewpoint_C'] = morphed_dewpt.values
            else:
                tas_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'tas', percentile),
                    _get_series(pathway, 'tas', percentile), 'tas',
                )
                tmax_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'tasmax', percentile),
                    _get_series(pathway, 'tasmax', percentile), 'tasmax',
                )
                tmin_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'tasmin', percentile),
                    _get_series(pathway, 'tasmin', percentile), 'tasmin',
                )
                present_dbt = epw_object.dataframe['drybulb_C']
                morphed_dbt = procedures.morph_dbt_year(
                    present_dbt,
                    tas_climatologies[1], tas_climatologies[0],
                    tmax_climatologies[1], tmax_climatologies[0],
                    tmin_climatologies[1], tmin_climatologies[0],
                ).values
                morphed_dict['drybulb_C'] = morphed_dbt

                relhum_climatologies = assemble.calc_model_climatologies(
                    baseline_range, target_range,
                    _get_series(ref, 'huss', percentile),
                    _get_series(pathway, 'huss', percentile), 'huss',
                )
                present_relhum = epw_object.dataframe['relhum_percent']
                present_psl = epw_object.dataframe['atmos_Pa']

                if 'atmos_Pa' in morphed_dict:
                    morphed_psl = morphed_dict['atmos_Pa']
                else:
                    psl_climatologies = assemble.calc_model_climatologies(
                        baseline_range, target_range,
                        _get_series(ref, 'psl', percentile),
                        _get_series(pathway, 'psl', percentile), 'psl',
                    )
                    morphed_psl = procedures.morph_psl(
                        present_psl, psl_climatologies[1], psl_climatologies[0],
                    ).values
                    if "Pressure" in user_variables:
                        morphed_dict['atmos_Pa'] = morphed_psl

                morphed_relhum = procedures.morph_relhum(
                    present_relhum, present_psl, present_dbt,
                    morphed_psl, morphed_dbt,
                    relhum_climatologies[1], relhum_climatologies[0],
                ).values
                morphed_dict['relhum_percent'] = morphed_relhum

                morphed_dewpt = procedures.morph_dewpt(
                    morphed_dict['drybulb_C'], morphed_dict['relhum_percent'],
                )
                morphed_dict['dewpoint_C'] = morphed_dewpt.values

        elif variable == 'Pressure':
            psl_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'psl', percentile),
                _get_series(pathway, 'psl', percentile), 'psl',
            )
            present_psl = epw_object.dataframe['atmos_Pa']
            morphed_psl = procedures.morph_psl(
                present_psl, psl_climatologies[1], psl_climatologies[0],
            ).values
            morphed_dict['atmos_Pa'] = morphed_psl

        elif variable == 'Wind':
            vas_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'vas', percentile),
                _get_series(pathway, 'vas', percentile), 'vas',
            )
            uas_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'uas', percentile),
                _get_series(pathway, 'uas', percentile), 'uas',
            )
            present_wspd = epw_object.dataframe['windspd_ms']
            morphed_wspd = procedures.morph_wspd(
                present_wspd,
                vas_climatologies[1], vas_climatologies[0],
                uas_climatologies[1], uas_climatologies[0],
            ).values
            morphed_dict['windspd_ms'] = morphed_wspd

        elif variable == 'Clouds and Radiation':
            longitude = epw_object.location['longitude']
            latitude = epw_object.location['latitude']
            utc_offset = epw_object.location['utc_offset']

            rsds_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'rsds', percentile),
                _get_series(pathway, 'rsds', percentile), 'rsds',
            )
            clt_climatologies = assemble.calc_model_climatologies(
                baseline_range, target_range,
                _get_series(ref, 'clt', percentile),
                _get_series(pathway, 'clt', percentile), 'clt',
            )

            present_glohor = epw_object.dataframe['glohorrad_Whm2']
            morphed_glohor = procedures.morph_glohor(
                present_glohor, rsds_climatologies[1], rsds_climatologies[0],
            ).values
            morphed_dict['glohorrad_Whm2'] = morphed_glohor

            present_exthor = epw_object.dataframe['exthorrad_Whm2']
            morphed_difhor = procedures.calc_difhor(
                longitude, latitude, utc_offset, morphed_glohor, present_exthor,
            ).values
            morphed_dict['difhorrad_Whm2'] = morphed_difhor

            present_dirnor = epw_object.dataframe['dirnorrad_Whm2']
            morphed_dirnor = procedures.calc_dirnor(
                morphed_glohor, morphed_difhor, present_dirnor,
                longitude, latitude, utc_offset,
            ).values
            morphed_dict['dirnorrad_Whm2'] = morphed_dirnor

            present_tsc = epw_object.dataframe['totskycvr_tenths']
            morphed_tsc = procedures.calc_tsc(
                present_tsc, clt_climatologies[1], clt_climatologies[0],
            ).values
            morphed_dict['totskycvr_tenths'] = morphed_tsc

            present_osc = epw_object.dataframe['opaqskycvr_tenths']
            morphed_osc = procedures.calc_osc(
                morphed_tsc, present_osc, present_tsc,
            ).values
            morphed_dict['opaqskycvr_tenths'] = morphed_osc

    for n, (k, v) in enumerate(morphed_dict.items()):
        epw_object.dataframe[k] = v
        if n == 0:
            epw_object.headers['COMMENTS 2'][0] += (
                f' morphed for {pathway} ({target_range}) with pyepwmorph'
                f' on {datetime.datetime.now().isoformat()}: {k},'
            )
        else:
            epw_object.headers['COMMENTS 2'][0] += f'{k},'

    return epw_object


# ---------------------------------------------------------------------------
# Full workflow
# ---------------------------------------------------------------------------

def morphing_workflow(
    project_name,
    epw_file,
    user_variables,
    user_pathways,
    percentiles,
    target_years=None,
    output_directory=None,
    model_sources=None,
    baseline_range=None,
    write_file=True,
    data_source="cmip6",
    custom_data=None,
    reference_scenario=None,
    # backward-compat alias
    future_years=None,
):
    """Run the full morphing pipeline.

    Supports both CMIP6 (``data_source="cmip6"``) and custom CSV data
    (``data_source="custom"``).

    Parameters
    ----------
    project_name : str
        Project label.
    epw_file : str
        Path to the base EPW file.
    user_variables : list[str]
        Variables to morph.
    user_pathways : list[str]
        Scenario labels.
    percentiles : list[int]
        Ensemble percentiles.
    target_years : list[int]
        Target years for morphing.
    output_directory : str or None
        Where to write output EPW files.
    model_sources : list[str] or None
        CMIP6 model IDs (ignored for custom).
    baseline_range : tuple[int, int] or None
        Reference period year range.
    write_file : bool
        Whether to write morphed EPW files to disk.
    data_source : str
        ``"cmip6"`` or ``"custom"``.
    custom_data : dict or None
        Nested dict for custom data (see ``MorphConfig``).
    reference_scenario : str or None
        Baseline scenario key.
    future_years : list[int] or None
        Deprecated alias for *target_years*.

    Returns
    -------
    dict
        Nested ``result_data[year][pathway][percentile]`` -> morphed Epw.
    """
    config_object = morph_config.MorphConfig(
        project_name, epw_file, user_variables, user_pathways, percentiles,
        target_years=target_years,
        output_directory=output_directory,
        model_sources=model_sources,
        baseline_range=baseline_range,
        data_source=data_source,
        custom_data=custom_data,
        reference_scenario=reference_scenario,
        future_years=future_years,
    )

    ref_scenario = config_object.reference_scenario

    # --- Compile climate model data ---
    if config_object.data_source == "custom":
        default_pctile = config_object.percentiles[0] if config_object.percentiles else 50
        year_model_dict = compile_custom_model_data(
            config_object.custom_data,
            config_object.model_variables,
            percentile=default_pctile,
        )
    else:
        year_model_dict = iterate_compile_model_data(
            config_object.model_pathways,
            config_object.model_variables,
            config_object.model_sources,
            config_object.epw.location['longitude'],
            config_object.epw.location['latitude'],
            config_object.percentiles,
        )

    # --- Morph for each target year x pathway x percentile ---
    target_pathways = [p for p in config_object.model_pathways if p != ref_scenario]
    result_data = {}

    for target_year in config_object.target_years:
        year_key = str(target_year)
        result_data[year_key] = {}
        target_range = morph_utils.calc_period(int(target_year), config_object.baseline_range)

        for pathway in target_pathways:
            result_data[year_key][pathway] = {}
            for percentile in config_object.percentiles:
                percentile_key = str(percentile)
                morphed_data = morph_epw(
                    config_object.epw,
                    config_object.user_variables,
                    config_object.baseline_range,
                    target_range,
                    year_model_dict,
                    pathway,
                    percentile,
                    reference_scenario=ref_scenario,
                )
                morphed_data.dataframe['year'] = int(target_year)
                result_data[year_key][pathway][percentile_key] = morphed_data
                if write_file and config_object.output_directory:
                    morphed_data.write_to_file(
                        os.path.join(
                            config_object.output_directory,
                            f"{year_key}_{pathway}_{percentile_key}.epw",
                        )
                    )

    return result_data
