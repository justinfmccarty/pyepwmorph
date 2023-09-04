# coding=utf-8
"""
The package was developed to serve two purposes:
    1. develop piecemeal functions for dealing with various EPW morphing tasks
    2. provide succinct workflows of those tools to automate the process of intaking climate data and morphing an EPW file
The second task is dealt with throughout the following scripts
"""
import datetime

from pyepwmorph.models import access, coordinate, assemble
from pyepwmorph.morph import procedures
from pyepwmorph.tools import io as morph_io
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


def compile_climate_model_data(model_sources, pathway, variable, longitude, latitude, percentiles):
    """
    Clean up the CMIP6 model data given known inconsistencies
    Additionally this script is necessary to spatially and temproally constrict the files

    Parameters
    ----------
    model_sources : list
        the models from which to pull data
    pathway : string
        the pathway that is being worked on from ['historical','ssp126','ssp245','ssp585']
    variable : string
        the variable that is being worked on from ['tas','tasmax','tasmin','clt','psl','pr','huss','vas','uas','rsds']
    longitude : float
        longitude (-180 to 180)
    latitude : float
        latitude (-180 to 180)
    percentiles : list
        percentiles from which to slice the ensemble of data

    Returns
    -------
    df
        a pandas dataframe for the variable and pathway
            where columns are percentile and the rows are the timeseries
    """

    dataset_dict = access.access_cmip6_data(model_sources,
                                            pathway,
                                            variable)
    dataset_dict = coordinate.coordinate_cmip6_data(latitude,
                                                    longitude,
                                                    pathway,
                                                    variable,
                                                    dataset_dict)
    return assemble.build_cmip6_ensemble(percentiles, variable, dataset_dict)


def iterate_compile_model_data(pathways, variables, model_sources, longitude, latitude, percentiles):
    """
    Clean up the CMIP6 model data given known inconsistencies
    Additionally this script is necessary to spatially and temproally constrict the files

    Parameters
    ----------
    pathways : list
        the pathways to cycle through
    variables : list
        the model variables to cycle through
    model_sources : list
        the models from which to pull data
    longitude : float
        longitude (-180 to 180)
    latitude : float
        latitude (-180 to 180)
    percentiles : list
        percentiles from which to slice the ensemble of data

    Returns
    -------
    dict
        a dict of dicts of pandas dataframes where pathway is the first key is the pathway and the second key is variable
    """
    model_data_dict = {}

    for pathway in pathways:
        model_data_dict[pathway] = {}
        for variable in variables:
            print(f"\nCompiling model data for '{pathway}' and '{variable}'.")
            # model_data_dict[pathway][variable] = variable
            result = compile_climate_model_data(model_sources, pathway, variable,
                                                longitude, latitude, percentiles)
            model_data_dict[pathway][variable] = result

    return model_data_dict


def morph_epw(epw_file, user_variables, baseline_range, future_range, model_data_dict, pathway, percentile):
    """
    Wrap around all of the morphing methods to apply directly to the epw

    Parameters
    ----------
    epw_file : string or memory object
        the epw filepath
    user_variables : list of strings
        the variables that are being morphed from ['Temperature','Humidity','Pressure','Wind','Clouds and Radiation', 'Dew Point']
    baseline_range : tuple (int,int)
        the start and stop for the baseline dates to capture the climaatology for
    future_range : tuple (int,int)
        the start and stop for the future dates to capture the climaatology for
    model_data_dict : dict
        a dict of dicts of pandas dataframes where pathway is the first key is the pathway and the second key is variable
    pathway : string
        the pathway that is being is being selected from the model_data_dict - from ['historical','ssp126','ssp245','ssp585']
    percentile : int
        the percentile in int form that is being selected from the model_data_dict

    Returns
    -------
    epw object
        a updated epw object with the morphed data
    """
    # input epw_object.dataframe
    # create blank dict
    # iterate through each if variable statement
    # add to blank dataframe using column names of existing epw
    # at end replace columns in existing with columns in new by iterating through columns in new
    if type(epw_file) == str:
        epw_object = morph_io.Epw(epw_file)
    else:
        epw_object = epw_file

    morphed_dict = {}

    for variable in user_variables:
        if variable == 'Temperature':
            # check to see if dew point was morphed and if it added drybulb to dict
            if 'drybulb_C' in morphed_dict.keys():
                pass
            else:
                tas_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                      model_data_dict['historical']['tas'][percentile],
                                                                      model_data_dict[pathway]['tas'][percentile],
                                                                      'tas')
                tmax_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                       model_data_dict['historical']['tasmax'][
                                                                           percentile],
                                                                       model_data_dict[pathway]['tasmax'][percentile],
                                                                       'tasmax')
                tmin_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                       model_data_dict['historical']['tasmin'][
                                                                           percentile],
                                                                       model_data_dict[pathway]['tasmin'][percentile],
                                                                       'tasmin')
                present_dbt = epw_object.dataframe['drybulb_C']
                morphed_dbt = procedures.morph_dbt_year(present_dbt,
                                                        tas_climatologies[1], tas_climatologies[0],
                                                        tmax_climatologies[1], tmax_climatologies[0],
                                                        tmin_climatologies[1], tmin_climatologies[0]
                                                        ).values
                morphed_dict['drybulb_C'] = morphed_dbt

        elif variable == 'Humidity':
            # check to see if dew point was morphed and if it added relhum to dict
            if 'relhum_percent' in morphed_dict.keys():
                pass
            else:
                relhum_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                         model_data_dict['historical']['huss'][
                                                                             percentile],
                                                                         model_data_dict[pathway]['huss'][percentile],
                                                                         'huss')

                present_relhum = epw_object.dataframe['relhum_percent']
                morphed_relhum = procedures.morph_relhum(present_relhum,
                                                         relhum_climatologies[1], relhum_climatologies[0]
                                                         ).values
                morphed_dict['relhum_percent'] = morphed_relhum

        elif variable == 'Dew Point':
            if ('relhum_percent' in morphed_dict.keys()) & ('drybulb_C' in morphed_dict.keys()):
                morphed_dewpt = procedures.morph_dewpt(morphed_dict['drybulb_C'], morphed_dict['relhum_percent'])
                morphed_dict['dewpoint_C'] = morphed_dewpt.values

            else:
                # TODO add a catch here if the tas, tasmax, tasmin, huss variables have not been downlaoded yet
                # download them here so no error arises

                # morph temp
                tas_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                      model_data_dict['historical']['tas'][percentile],
                                                                      model_data_dict[pathway]['tas'][percentile],
                                                                      'tas')
                tmax_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                       model_data_dict['historical']['tasmax'][
                                                                           percentile],
                                                                       model_data_dict[pathway]['tasmax'][percentile],
                                                                       'tasmax')
                tmin_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                       model_data_dict['historical']['tasmin'][
                                                                           percentile],
                                                                       model_data_dict[pathway]['tasmin'][percentile],
                                                                       'tasmin')
                present_dbt = epw_object.dataframe['drybulb_C']
                morphed_dbt = procedures.morph_dbt_year(present_dbt,
                                                        tas_climatologies[1], tas_climatologies[0],
                                                        tmax_climatologies[1], tmax_climatologies[0],
                                                        tmin_climatologies[1], tmin_climatologies[0]
                                                        ).values

                # morph relhum
                relhum_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                         model_data_dict['historical']['huss'][
                                                                             percentile],
                                                                         model_data_dict[pathway]['huss'][percentile],
                                                                         'huss')

                present_relhum = epw_object.dataframe['relhum_percent']
                morphed_relhum = procedures.morph_relhum(present_relhum,
                                                         relhum_climatologies[1], relhum_climatologies[0]
                                                         ).values
                if "Temperature" in user_variables:
                    morphed_dict['drybulb_C'] = morphed_dbt

                if "Humidity" in user_variables:
                    morphed_dict['relhum_percent'] = morphed_relhum

                morphed_dewpt = procedures.morph_dewpt(morphed_dict['drybulb_C'], morphed_dict['relhum_percent'])
                morphed_dict['dewpoint_C'] = morphed_dewpt.values

        elif variable == 'Pressure':
            psl_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                  model_data_dict['historical']['psl'][percentile],
                                                                  model_data_dict[pathway]['psl'][percentile],
                                                                  'psl')

            present_psl = epw_object.dataframe['atmos_Pa']
            moprhed_psl = procedures.morph_relhum(present_psl,
                                                  psl_climatologies[1], psl_climatologies[0]
                                                  ).values
            morphed_dict['atmos_Pa'] = moprhed_psl

        elif variable == 'Wind':
            vas_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                  model_data_dict['historical']['vas'][percentile],
                                                                  model_data_dict[pathway]['vas'][percentile],
                                                                  'vas')
            uas_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                  model_data_dict['historical']['uas'][percentile],
                                                                  model_data_dict[pathway]['uas'][percentile],
                                                                  'uas')

            present_wspd = epw_object.dataframe['windspd_ms']
            moprhed_wspd = procedures.morph_wspd(present_wspd,
                                                 vas_climatologies[1], vas_climatologies[0],
                                                 uas_climatologies[1], uas_climatologies[0]
                                                 ).values
            morphed_dict['windspd_ms'] = moprhed_wspd

        elif variable == 'Clouds and Radiation':
            # do morphing for glohor, diffhor, dirnor, tsc, osc
            longitude = epw_object.location['longitude']
            latitude = epw_object.location['latitude']
            utc_offset = epw_object.location['utc_offset']

            rsds_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                   model_data_dict['historical']['rsds'][percentile],
                                                                   model_data_dict[pathway]['rsds'][percentile],
                                                                   'rsds')
            clt_climatologies = assemble.calc_model_climatologies(baseline_range, future_range,
                                                                  model_data_dict['historical']['clt'][percentile],
                                                                  model_data_dict[pathway]['clt'][percentile],
                                                                  'clt')

            present_glohor = epw_object.dataframe['glohorrad_Whm2']
            morphed_glohor = procedures.morph_glohor(present_glohor,
                                                     rsds_climatologies[1], rsds_climatologies[0]
                                                     ).values
            morphed_dict['glohorrad_Whm2'] = morphed_glohor

            present_exthor = epw_object.dataframe['exthorrad_Whm2']
            morphed_diffhor = procedures.calc_diffhor(longitude, latitude, utc_offset,
                                                      morphed_glohor, present_exthor
                                                      ).values
            morphed_dict['diffhorrad_Whm2'] = morphed_diffhor
            morphed_dirnor = procedures.calc_dirnor(morphed_glohor,
                                                    longitude, latitude, utc_offset
                                                    ).values
            morphed_dict['dirnorrad_Whm2'] = morphed_dirnor

            present_tsc = epw_object.dataframe['totskycvr_tenths']
            morphed_tsc = procedures.calc_tsc(present_tsc,
                                              clt_climatologies[1], clt_climatologies[0]
                                              ).values
            morphed_dict['totskycvr_tenths'] = morphed_tsc

            present_osc = epw_object.dataframe['opaqskycvr_tenths']
            morphed_osc = procedures.calc_osc(morphed_tsc,
                                              present_osc, present_tsc
                                              ).values
            morphed_dict['opaqskycvr_tenths'] = morphed_osc

    for n, i in enumerate(morphed_dict.items()):
        k = i[0]
        v = i[1]
        epw_object.dataframe[k] = v
        if n == 0:
            epw_object.headers['COMMENTS 2'][
                0] += f'morphed for {pathway} ({future_range}) with pyepwmorph on {datetime.datetime.now().isoformat()}: {k},'
        else:
            epw_object.headers['COMMENTS 2'][0] += f'{k},'

    return epw_object
