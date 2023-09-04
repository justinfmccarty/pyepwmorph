# -*- coding: utf-8 -*-

import csv
import re
import datetime
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

    df.set_index(morph_utils.ts_8760(), inplace=True)
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
                     'usaf', 'longitude', 'latitude', 'utc_offset', 'elevation']
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


class Epw():
    """
    A class which represents an EnergyPlus weather (epw) file
    Thanks: https://github.com/building-energy/epw

    Used mostly for writing epw files.
    """

    def __init__(self, filepath):
        """
        """
        self.fp = filepath
        self.read()

    def read(self):
        """Reads an epw file

        Arguments:
            - fp (str): the file path of the epw file

        """

        self._read_headers()
        self._read_data()
        self._read_string()
        self._read_location()

    def _read_string(self):
        with open(self.fp, "r") as fp:
            file_content = fp.readlines()
        self.string = file_content

    def _read_location(self):
        location_line = self.string[0].replace("\n", "").split(",")
        location_keys = ['title', 'site', 'province', 'country_code', 'type',
                         'usaf', 'longitude', 'latitude', 'utc_offset', 'elevation']
        location_dict = dict(zip(location_keys, location_line))
        location_dict['longitude'] = float(location_dict['longitude'])
        location_dict['latitude'] = float(location_dict['latitude'])
        location_dict['elevation'] = float(location_dict['elevation'])
        location_dict['utc_offset'] = float(location_dict['utc_offset'])
        self.location = location_dict

    def _read_headers(self):
        """Reads the headers of an epw file

        Arguments:
            - fp (str): the file path of the epw file

        Return value:
            - d (dict): a dictionary containing the header rows

        """

        d = {}
        with open(self.fp, newline='') as csvfile:
            csvreader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in csvreader:
                if row[0].isdigit():
                    break
                else:
                    d[row[0]] = row[1:]
        self.headers = d

    def _read_data(self):
        """Reads the climate data of an epw file

        Arguments:
            - fp (str): the file path of the epw file

        Return value:
            - df (pd.DataFrame): a DataFrame comtaining the climate data

        """

        names = ['year',
                 'month',
                 'day',
                 'hour',
                 'minute',
                 'datasource',
                 'drybulb_C',
                 'dewpoint_C',
                 'relhum_percent',
                 'atmos_Pa',
                 'exthorrad_Whm2',
                 'extdirrad_Whm2',
                 'horirsky_Whm2',
                 'glohorrad_Whm2',
                 'dirnorrad_Whm2',
                 'difhorrad_Whm2',
                 'glohorillum_lux',
                 'dirnorillum_lux',
                 'difhorillum_lux',
                 'zenlum_lux',
                 'winddir_deg',
                 'windspd_ms',
                 'totskycvr_tenths',
                 'opaqskycvr_tenths',
                 'visibility_km',
                 'ceiling_hgt_m',
                 'presweathobs',
                 'presweathcodes',
                 'precip_wtr_mm',
                 'aerosol_opt_thousandths',
                 'snowdepth_cm',
                 'days_last_snow',
                 'Albedo',
                 'liq_precip_depth_mm',
                 'liq_precip_rate_Hour']

        first_row = self._first_row_with_climate_data()
        df = pd.read_csv(self.fp,
                         skiprows=first_row,
                         header=None,
                         names=names)

        df.set_index(morph_utils.ts_8760(year=datetime.datetime.now().year), inplace=True)
        self.dataframe = df

    def _first_row_with_climate_data(self):
        """Finds the first row with the climate data of an epw file

        Arguments:
            - fp (str): the file path of the epw file

        Return value:
            - i (int): the row number

        """

        with open(self.fp, newline='') as csvfile:
            csvreader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for i, row in enumerate(csvreader):
                if row[0].isdigit():
                    break
        return i

    def build_header_string(self):
        header_lines = []

        for k, v in self.headers.items():
            header_lines.append(f"{k},{','.join(v)}" + "\n")

        return header_lines

    def build_data_string(self):
        data_lines = []

        for row in self.dataframe.reset_index(drop=True).iterrows():
            data_lines.append(",".join(row[1].astype(str).tolist()) + "\n")

        return data_lines

    def make_epw_string(self):
        header_list = self.build_header_string()
        data_list = self.build_data_string()
        return "".join(header_list + data_list)

    def write_to_file(self, fp):
        """Writes an epw file

        Arguments:
            - fp (str): the file path of the new epw file

        """

        # with open(fp, 'w', newline='') as csvfile:
        #     csvwriter = csv.writer(csvfile, delimiter=',',
        #                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
        #     for k, v in self.headers.items():
        #         csvwriter.writerow([k] + v)
        #     for row in self.dataframe.itertuples(index=False):
        #         csvwriter.writerow(i for i in row)
        #
        with open(fp, "w") as fp:
            fp.write(self.make_epw_string())

    def detect_baseline_range(self):
        subl = [l for l in self.string if "Period of Record" in l][0].replace("\n", "").split("Period of Record")[
            -1].replace("=", " ").replace(";", " ").replace("-", " ")
        years = np.array(list(set([int(y) for y in re.findall(r'\d{4}', subl)])))
        return (years.min(), years.max())
