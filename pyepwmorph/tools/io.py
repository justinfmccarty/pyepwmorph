# -*- coding: utf-8 -*-
"""EPW file reading and writing with validation."""

import csv
import logging
import os
import re
import warnings

import numpy as np
import pandas as pd

from pyepwmorph.tools import utilities as morph_utils

logger = logging.getLogger(__name__)

EPW_COLUMN_NAMES = [
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

EPW_EXPECTED_COLS = len(EPW_COLUMN_NAMES)  # 35
EPW_EXPECTED_ROWS = 8760

# EPW LOCATION header field order per the EnergyPlus Auxiliary Programs docs:
# LOCATION,City,State/Province,Country,Data Source,WMO#,Latitude,Longitude,TimeZone,Elevation
EPW_LOCATION_KEYS = [
    'title', 'site', 'province', 'country_code', 'type',
    'usaf', 'latitude', 'longitude', 'utc_offset', 'elevation'
]


def _parse_location_line(line: str) -> dict:
    """Parse the first (LOCATION) line of an EPW file into a dict.

    The EPW spec defines the field order as:
    LOCATION, City, State, Country, Source, WMO, Latitude, Longitude, TZ, Elevation
    """
    fields = line.replace("\n", "").split(",")
    if len(fields) < 10:
        raise ValueError(
            f"EPW LOCATION line has {len(fields)} fields, expected at least 10"
        )
    location_dict = dict(zip(EPW_LOCATION_KEYS, fields))
    for numeric_key in ('latitude', 'longitude', 'elevation', 'utc_offset'):
        try:
            location_dict[numeric_key] = float(location_dict[numeric_key])
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"Cannot parse '{numeric_key}' from LOCATION line: {exc}"
            ) from exc
    return location_dict


def _find_header_length(lines: list[str]) -> int:
    """Return the number of header lines before the first data row."""
    csvreader = csv.reader(lines, delimiter=',', quotechar='"')
    for i, row in enumerate(csvreader):
        if row and row[0].isdigit():
            return i
    raise ValueError("No data rows found in EPW file (no row starts with a digit)")


def read_epw_string(filepath: str) -> list[str]:
    """Read an EPW file and return its raw lines."""
    with open(filepath, "r", encoding="utf-8") as fh:
        return fh.readlines()


def read_epw_header(file_content: list[str]) -> dict:
    """Parse EPW header lines into a dict keyed by header type."""
    header_len = _find_header_length(file_content)
    d: dict[str, list[str]] = {}
    csvreader = csv.reader(file_content, delimiter=',', quotechar='"')
    for n, row in enumerate(csvreader):
        if n >= header_len:
            break
        key = row[0]
        if key in d:
            warnings.warn(f"Duplicate EPW header key '{key}'; later value overwrites earlier")
        d[key] = row[1:]
    return d


def epw_location(file_content: list[str]) -> dict:
    """Extract location metadata from raw EPW file lines."""
    return _parse_location_line(file_content[0])


def epw_baseline_range(file_content: list[str]) -> tuple[int, int]:
    """Extract the baseline year range from the EPW comments."""
    matches = [line for line in file_content if "Period of Record" in line]
    if not matches:
        raise ValueError("No 'Period of Record' found in EPW header")
    subl = matches[0].replace("\n", "").split("Period of Record")[
        -1].replace("=", " ").replace(";", " ").replace("-", " ")
    years = np.array(list(set(int(y) for y in re.findall(r'\d{4}', subl))))
    if len(years) == 0:
        raise ValueError("Could not parse years from 'Period of Record' line")
    return (int(years.min()), int(years.max()))


def read_epw_dataframe(filepath: str) -> pd.DataFrame:
    """Read an EPW file into a pandas DataFrame with an 8760-hour index.

    The year used for the datetime index is derived from the first data row
    of the EPW file itself.
    """
    file_content = read_epw_string(filepath)
    header_len = _find_header_length(file_content)

    df = pd.read_csv(
        filepath,
        skiprows=header_len,
        header=None,
        index_col=False,
        usecols=list(range(0, EPW_EXPECTED_COLS)),
        names=EPW_COLUMN_NAMES,
    )

    _validate_dataframe(df, filepath)

    df['hour'] = df['hour'].astype(int)
    if df['hour'].iloc[0] == 1:
        logger.info("TMY file hours reduced from 1-24h to 0-23h")
        df['hour'] = df['hour'] - 1
    else:
        logger.debug("TMY file hours already 0-23h")
    df['minute'] = 0

    year = int(df['year'].iloc[0])
    df.set_index(morph_utils.ts_8760(year=year), inplace=True)
    return df


def _validate_dataframe(df: pd.DataFrame, source: str = "<unknown>") -> None:
    """Validate that a DataFrame looks like valid EPW data."""
    if len(df) != EPW_EXPECTED_ROWS:
        raise ValueError(
            f"EPW file '{source}' has {len(df)} data rows, expected {EPW_EXPECTED_ROWS}"
        )
    if len(df.columns) != EPW_EXPECTED_COLS:
        raise ValueError(
            f"EPW file '{source}' has {len(df.columns)} columns, expected {EPW_EXPECTED_COLS}"
        )


class Epw:
    """Represents an EnergyPlus Weather (EPW) file.

    Handles reading, modifying, and writing EPW data while preserving
    the original header structure.
    """

    def __init__(self, filepath: str):
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"EPW file not found: {filepath}")
        self.fp = filepath
        self.headers: dict[str, list[str]] = {}
        self.dataframe: pd.DataFrame = pd.DataFrame()
        self.string: list[str] = []
        self.location: dict = {}
        self.read()

    def read(self):
        """Read and parse all sections of the EPW file."""
        self._read_string()
        self._read_headers()
        self._read_data()
        self._read_location()

    def _read_string(self):
        with open(self.fp, "r", encoding="utf-8") as fh:
            self.string = fh.readlines()

    def _read_location(self):
        self.location = _parse_location_line(self.string[0])

    def _read_headers(self):
        self.headers = read_epw_header(self.string)

    def _read_data(self):
        first_row = _find_header_length(self.string)
        df = pd.read_csv(
            self.fp,
            skiprows=first_row,
            header=None,
            names=EPW_COLUMN_NAMES,
        )

        _validate_dataframe(df, self.fp)

        year = int(df['year'].iloc[0])
        df.set_index(morph_utils.ts_8760(year=year), inplace=True)
        df['year'] = year
        self.dataframe = df

    def build_header_string(self) -> list[str]:
        header_lines = []
        for k, v in self.headers.items():
            header_lines.append(f"{k},{','.join(v)}\n")
        return header_lines

    def build_data_string(self) -> list[str]:
        data_lines = []
        for _idx, row in self.dataframe.reset_index(drop=True).iterrows():
            data_lines.append(",".join(row.astype(str).tolist()) + "\n")
        return data_lines

    def make_epw_string(self) -> str:
        return "".join(self.build_header_string() + self.build_data_string())

    def write_to_file(self, filepath: str):
        """Write the EPW data to a file, creating directories as needed."""
        directory_path = os.path.dirname(filepath)
        if directory_path and not os.path.exists(directory_path):
            os.makedirs(directory_path)
            logger.info("Directory created: %s", directory_path)

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(self.make_epw_string())

    def detect_baseline_range(self) -> tuple[int, int]:
        """Detect the baseline year range from EPW comments or data."""
        try:
            return epw_baseline_range(self.string)
        except (ValueError, IndexError):
            years = self.dataframe['year'].to_numpy()
            return (int(years.min()), int(years.max()))
