import csv
import re

import numpy as np
import pandas as pd

from pyepwmorph.tools import utilities as morph_utils

def read_epw_dataframe(filepath):
    tmy_labels = [
        'year', 'month', 'day', 'hour', 'minute', 'datasource', 'drybulb_C',
        'dewpoint_C', 'relhum_percent', 'atmos_Pa', 'exthorrad_Whm2',
        'extdirrad_Whm2', 'horirsky_Whm2', 'glohorrad_Whm2', 'dirnorrad_Whm2',
        'difhorrad_Whm2', 'glohorillum_lux', 'dirnorillum_lux',
        'difhorillum_lux', 'zenlum_lux', 'winddir_deg', 'windspd_ms',
        'totskycvr_tenths', 'opaqskycvr_tenths', 'visibility_km',
        'ceiling_hgt_m', 'presweathobs', 'presweathcodes', 'precip_wtr_mm',
        'aerosol_opt_thousandths', 'snowdepth_cm', 'days_last_snow', 'Albedo',
        'liq_precip_depth_mm', 'liq_precip_rate_Hour'
    ]


    df = pd.read_csv(filepath,
                     skiprows=epw_find_header_length(read_epw_string(filepath)),
                     header=None,
                     index_col=False,
                     usecols=list(range(0, 35)),
                     names=tmy_labels)

    df['hour'] = df['hour'].astype(int)
    if df['hour'][0] == 1:
        print('TMY file hours reduced from 1-24h to 0-23h')
        df['hour'] = df['hour'] - 1
    else:
        print('TMY file hours maintained at 0-23hr')
    df['minute'] = 0

    df.set_index(morph_utils.ts_8760(),inplace=True)
    return df


def read_epw_string(filepath):
    with open(filepath, "r") as fp:
        file_content = fp.readlines()
    return file_content


def epw_find_header_length(file_content):
    csvreader = csv.reader(file_content, delimiter=',', quotechar='"')
    for i, row in enumerate(csvreader):
        if row[0].isdigit():
            break
    return i


def read_epw_header(file_content):
    d = {}
    csvreader = csv.reader(file_content, delimiter=',', quotechar='"')
    for n, row in enumerate(csvreader):
        if n == epw_find_header_length(file_content):
            break
        else:
            d[row[0]] = row[1:]

    return d


def epw_location(file_content):
    location_line = file_content[0].replace("\n", "").split(",")
    location_keys = ['title', 'site', 'province', 'country_code', 'type',
                     'usaf', 'longitude', 'latitude', 'utc_offset','elevation']
    location_dict = dict(zip(location_keys, location_line))
    location_dict['longitude'] = float(location_dict['longitude'])
    location_dict['latitude'] = float(location_dict['latitude'])
    location_dict['elevation'] = float(location_dict['elevation'])
    location_dict['utc_offset'] = float(location_dict['utc_offset'])
    return location_dict

def epw_baseline_range(file_content):
    subl = [l for l in file_content if "Period of Record" in l][0].replace("\n", "").split("Period of Record")[
        -1].replace("=", " ").replace(";", " ").replace("-", " ")
    years = np.array(list(set([int(y) for y in re.findall(r'\d{4}', subl)])))
    return (years.min(), years.max())