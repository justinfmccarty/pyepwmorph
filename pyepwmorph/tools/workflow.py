"""High-level workflows for compiling climate data and morphing EPW files.

Supports both CMIP6 (Pangeo) and custom CSV-based climate model data.
"""

import copy
import datetime
import logging
import os

from pyepwmorph.models import access, assemble, ch2025, coordinate, custom
from pyepwmorph.morph import procedures
from pyepwmorph.tools import cache
from pyepwmorph.tools import configuration as morph_config
from pyepwmorph.tools import io as morph_io
from pyepwmorph.tools import utilities as morph_utils

logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"


# ---------------------------------------------------------------------------
# CMIP6 data compilation
# ---------------------------------------------------------------------------

def compile_climate_model_data(model_sources, pathway, variable, longitude, latitude, percentiles,
                               time_slices=None):
    """Fetch, spatially select, and ensemble CMIP6 data for one pathway + variable.

    The location-specific result is cached, and the cache is consulted before
    the remote catalogue is opened so that a hit costs no network traffic.

    Returns
    -------
    pd.DataFrame
        Columns keyed by percentile, rows are the monthly time series.
    """
    datasets = cache.get_cached_coordinate_data(
        latitude=latitude,
        longitude=longitude,
        pathway=pathway,
        variable=variable,
        source_id=model_sources,
        time_slices=time_slices,
    )

    if datasets is None:
        dataset_dict = access.access_cmip6_data(model_sources, pathway, variable)
        datasets = coordinate.coordinate_cmip6_data(
            latitude, longitude, pathway, variable, dataset_dict, time_slices=time_slices,
        )
        cache.save_coordinate_to_cache(
            data=datasets,
            latitude=latitude,
            longitude=longitude,
            pathway=pathway,
            variable=variable,
            source_id=model_sources,
            time_slices=time_slices,
        )

    return assemble.build_cmip6_ensemble(percentiles, variable, datasets)


def iterate_compile_model_data(pathways, variables, model_sources, longitude, latitude, percentiles,
                               time_slices=None):
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
                    time_slices=time_slices,
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


def compile_ch2025_model_data(station_id, pathways, variables, percentiles):
    """Load shipped CH2025 climatologies for one station.

    Each warming level gets its own paired reference, built from the model
    chains it shares with ``ref91-20`` (see
    ``ch2025.build_ch2025_change_ensemble``). The reference is stored under
    ``ch2025.reference_key(state)``; pass that as ``reference_scenario`` to
    ``morph_epw``.

    Parameters
    ----------
    station_id : str
        Lower-case CH2025 station abbreviation.
    pathways : list[str]
        State ids. ``ref91-20`` may be included and is skipped.
    variables : list[str]
        CH2025 variable ids.
    percentiles : list
        Ensemble percentiles.

    Returns
    -------
    dict[str, dict[str, pd.DataFrame]]
        ``model_data_dict[key][variable]`` with percentile columns, where
        *key* is a warming level or its paired reference key.
    """
    model_data_dict = {}
    for pathway in pathways:
        if pathway == ch2025.CH2025_REFERENCE:
            continue
        reference_key = ch2025.reference_key(pathway)
        model_data_dict[pathway] = {}
        model_data_dict[reference_key] = {}
        for variable in variables:
            logger.info("Loading CH2025 data for '%s' / '%s' / '%s'", station_id, pathway, variable)
            reference, future = ch2025.build_ch2025_change_ensemble(
                percentiles, variable, station_id, pathway,
            )
            model_data_dict[reference_key][variable] = reference
            model_data_dict[pathway][variable] = future
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
    data_source="cmip6",
    station_label=None,
):
    """Apply morphing procedures to an EPW file.

    The requested variables are expanded to include their dependencies and
    sorted into a single morphing order (see
    ``configuration.resolve_variable_order``), so every variable is computed
    exactly once and every dependency is already morphed when it is needed.
    All resolved variables are written to the returned EPW, which keeps the
    output file internally consistent.

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
    data_source : str
        ``"cmip6"``, ``"custom"``, or ``"ch2025"``. CH2025 uses warming-level
        climatologies directly and morphs humidity and wind from ``hurs``
        and ``sfcWind``.
    station_label : str or None
        CH2025 station named in the EPW comment.

    Returns
    -------
    Epw
        A deep-copied Epw object with morphed data applied.
    """
    if isinstance(epw_file, str):
        epw_object = morph_io.Epw(epw_file)
    else:
        epw_object = copy.deepcopy(epw_file)

    present = epw_object.dataframe
    location = epw_object.location

    def _get_series(scenario, var):
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
        return model_data_dict[scenario][var][percentile]

    def _climatology(var):
        """Return the (baseline, future) monthly climatologies for a variable."""
        baseline = _get_series(reference_scenario, var)
        future = _get_series(pathway, var)
        if data_source == "ch2025":
            return assemble.calc_gwl_climatologies(baseline, future, var)
        return assemble.calc_model_climatologies(
            baseline_range, target_range, baseline, future, var,
        )

    morphed = {}
    for variable in morph_config.resolve_variable_order(user_variables, data_source):
        if variable == 'Pressure':
            psl_base, psl_future = _climatology('psl')
            morphed['atmos_Pa'] = procedures.morph_psl(
                present['atmos_Pa'], psl_future, psl_base,
            )

        elif variable == 'Temperature':
            tas_base, tas_future = _climatology('tas')
            tasmax_base, tasmax_future = _climatology('tasmax')
            tasmin_base, tasmin_future = _climatology('tasmin')
            morphed['drybulb_C'] = procedures.morph_dbt_year(
                present['drybulb_C'],
                tas_future, tas_base,
                tasmax_future, tasmax_base,
                tasmin_future, tasmin_base,
            )

        elif variable == 'Humidity':
            if data_source == "ch2025":
                hurs_base, hurs_future = _climatology('hurs')
                morphed['relhum_percent'] = procedures.morph_relhum_direct(
                    present['relhum_percent'], hurs_future, hurs_base,
                )
            else:
                huss_base, huss_future = _climatology('huss')
                morphed['relhum_percent'] = procedures.morph_relhum(
                    present['relhum_percent'], present['atmos_Pa'], present['drybulb_C'],
                    morphed['atmos_Pa'], morphed['drybulb_C'],
                    huss_future, huss_base,
                )

        elif variable == 'Dew Point':
            morphed['dewpoint_C'] = procedures.morph_dewpt(
                morphed['drybulb_C'], morphed['relhum_percent'],
            )

        elif variable == 'Wind':
            if data_source == "ch2025":
                wind_base, wind_future = _climatology('sfcWind')
                morphed['windspd_ms'] = procedures.morph_wspd_direct(
                    present['windspd_ms'], wind_future, wind_base,
                )
            else:
                vas_base, vas_future = _climatology('vas')
                uas_base, uas_future = _climatology('uas')
                morphed['windspd_ms'] = procedures.morph_wspd(
                    present['windspd_ms'],
                    vas_future, vas_base,
                    uas_future, uas_base,
                )

        elif variable == 'Radiation':
            rsds_base, rsds_future = _climatology('rsds')
            longitude = location['longitude']
            latitude = location['latitude']
            utc_offset = location['utc_offset']

            glohor = procedures.morph_glohor(
                present['glohorrad_Whm2'], rsds_future, rsds_base,
            )
            difhor = procedures.calc_difhor(
                longitude, latitude, utc_offset, glohor, present['exthorrad_Whm2'],
            )
            dirnor = procedures.calc_dirnor(
                glohor, difhor, longitude, latitude, utc_offset,
                extraterrestrial_dirnor=present['extdirrad_Whm2'],
            )
            morphed['glohorrad_Whm2'] = glohor
            morphed['difhorrad_Whm2'] = difhor
            morphed['dirnorrad_Whm2'] = dirnor

        elif variable == 'Clouds and Radiation':
            rsds_base, rsds_future = _climatology('rsds')
            clt_base, clt_future = _climatology('clt')
            longitude = location['longitude']
            latitude = location['latitude']
            utc_offset = location['utc_offset']

            glohor = procedures.morph_glohor(
                present['glohorrad_Whm2'], rsds_future, rsds_base,
            )
            difhor = procedures.calc_difhor(
                longitude, latitude, utc_offset, glohor, present['exthorrad_Whm2'],
            )
            dirnor = procedures.calc_dirnor(
                glohor, difhor, longitude, latitude, utc_offset,
                extraterrestrial_dirnor=present['extdirrad_Whm2'],
            )
            totskycvr = procedures.calc_tsc(
                present['totskycvr_tenths'], clt_future, clt_base,
            )
            opaqskycvr = procedures.calc_osc(
                totskycvr, present['opaqskycvr_tenths'], present['totskycvr_tenths'],
            )

            morphed['glohorrad_Whm2'] = glohor
            morphed['difhorrad_Whm2'] = difhor
            morphed['dirnorrad_Whm2'] = dirnor
            morphed['totskycvr_tenths'] = totskycvr
            morphed['opaqskycvr_tenths'] = opaqskycvr

    if morphed:
        for column, values in morphed.items():
            epw_object.dataframe[column] = values
        # EPW headers are comma delimited, so the comment itself must not
        # contain commas or it will be split across fields on the next read
        sky_note = ""
        if "Radiation" in morph_config.resolve_variable_order(user_variables, data_source):
            sky_note = " [sky cover left unmorphed]"
        if data_source == "ch2025":
            station_note = f" station {station_label}" if station_label else ""
            comment = (
                f" morphed for {pathway} with CH2025{station_note} with pyepwmorph"
                f" on {datetime.datetime.now().isoformat()} [{' '.join(morphed)}]{sky_note}"
                f" {ch2025.CH2025_CITATION}"
            )
        else:
            comment = (
                f" morphed for {pathway} ({target_range[0]}-{target_range[1]}) with pyepwmorph"
                f" on {datetime.datetime.now().isoformat()} [{' '.join(morphed)}]{sky_note}"
            )
        epw_object.add_comment(comment)

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
    time_slices=None,
    ch2025_full_coverage=False,
    # backward-compat alias
    future_years=None,
):
    """Run the full morphing pipeline.

    Supports CMIP6 (``data_source="cmip6"``), custom CSV data
    (``data_source="custom"``), and Swiss CH2025 warming levels
    (``data_source="ch2025"``).

    Parameters
    ----------
    project_name : str
        Project label.
    epw_file : str
        Path to the base EPW file.
    user_variables : list[str]
        Variables to morph.  Dependencies are added automatically.
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
        ``"cmip6"``, ``"custom"``, or ``"ch2025"``. CH2025 does not use
        ``target_years``; pathways are warming levels such as ``"gwl2.0"``.
    custom_data : dict or None
        Nested dict for custom data (see ``MorphConfig``).
    reference_scenario : str or None
        Baseline scenario key.
    time_slices : dict or None
        Optional per-pathway ``(start, end)`` temporal bounds for CMIP6 data.
    ch2025_full_coverage : bool
        CH2025 only. Match the site only against stations that carry every
        CH2025 variable (see ``MorphConfig``).
    future_years : list[int] or None
        Deprecated alias for *target_years*.

    Returns
    -------
    dict
        For CMIP6 and custom data, ``result_data[year][pathway][percentile]``.
        For CH2025, ``result_data[warming_level][percentile]``.
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
        ch2025_full_coverage=ch2025_full_coverage,
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
    elif config_object.data_source == "ch2025":
        station = config_object.ch2025_station
        year_model_dict = compile_ch2025_model_data(
            station["station_id"],
            config_object.model_pathways,
            config_object.model_variables,
            config_object.percentiles,
        )
    else:
        year_model_dict = iterate_compile_model_data(
            config_object.model_pathways,
            config_object.model_variables,
            config_object.model_sources,
            config_object.epw.location['longitude'],
            config_object.epw.location['latitude'],
            config_object.percentiles,
            time_slices=time_slices,
        )

    # --- Morph for each target year x pathway x percentile ---
    target_pathways = [p for p in config_object.model_pathways if p != ref_scenario]
    result_data = {}

    if "Radiation" in config_object.resolved_variables:
        logger.warning(
            "Radiation morphs shortwave radiation while leaving sky cover at "
            "baseline values. EnergyPlus derives sky temperature from opaque "
            "sky cover when horizontal infrared is absent, so the longwave "
            "side of this file does not follow the shortwave change."
        )

    if config_object.data_source == "ch2025":
        station = config_object.ch2025_station
        station_label = f"{station['station_id']} {station['name']}".replace(",", " ")
        for pathway in target_pathways:
            result_data[pathway] = {}
            for percentile in config_object.percentiles:
                percentile_key = str(percentile)
                morphed_data = morph_epw(
                    config_object.epw,
                    config_object.resolved_variables,
                    config_object.baseline_range,
                    ch2025.CH2025_BASELINE_RANGE,
                    year_model_dict,
                    pathway,
                    percentile,
                    reference_scenario=ch2025.reference_key(pathway),
                    data_source="ch2025",
                    station_label=station_label,
                )
                result_data[pathway][percentile_key] = morphed_data
                if write_file and config_object.output_directory:
                    morphed_data.write_to_file(
                        os.path.join(
                            config_object.output_directory,
                            f"{pathway}_{percentile_key}.epw",
                        )
                    )
        return result_data

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
                    config_object.resolved_variables,
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
