"""Load custom (non-CMIP6) climate model data from CSV files.

The CSV format expected is:

    date,<variable>
    1980-01-15,273.5
    1980-02-15,274.1
    ...

where ``date`` is parseable by pandas and ``<variable>`` matches a CMIP6
variable name (tas, tasmax, tasmin, huss, psl, uas, vas, clt, rsds).

Rows must be monthly.  For a single model run the data is treated as the
sole ensemble member and assigned to a default percentile (50).
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

VALID_VARIABLES = frozenset(
    ['tas', 'tasmax', 'tasmin', 'huss', 'psl', 'uas', 'vas', 'clt', 'rsds']
)


def load_custom_csv(
    filepath: str,
    variable: str,
    percentile: int = 50,
    date_column: str = "date",
) -> pd.DataFrame:
    """Load a CSV of monthly climate data and return a pipeline-compatible DataFrame.

    Parameters
    ----------
    filepath : str
        Path to the CSV file.
    variable : str
        Climate variable name (must be in VALID_VARIABLES).
    percentile : int
        Percentile label to assign to the single data column.  Defaults to 50.
    date_column : str
        Name of the column containing dates.  Defaults to ``"date"``.

    Returns
    -------
    pd.DataFrame
        DataFrame with a DatetimeIndex (monthly) and one column keyed by
        ``percentile``, matching the shape returned by
        ``assemble.build_cmip6_ensemble``.

    Raises
    ------
    ValueError
        If the variable is not recognised or the CSV cannot be parsed.
    FileNotFoundError
        If the file does not exist.
    """
    if variable not in VALID_VARIABLES:
        raise ValueError(
            f"Variable '{variable}' not recognised. Must be one of {sorted(VALID_VARIABLES)}"
        )

    df = pd.read_csv(filepath, parse_dates=[date_column])
    if variable not in df.columns:
        raise ValueError(
            f"Column '{variable}' not found in CSV. Available columns: {list(df.columns)}"
        )

    df = df.set_index(date_column)
    df.index = pd.DatetimeIndex(df.index)
    df.index.name = "time"

    series = df[variable]
    result = pd.DataFrame({percentile: series})
    result.index.name = "time"

    logger.info(
        "Loaded custom data for '%s' from %s (%d rows, percentile=%s)",
        variable, filepath, len(result), percentile,
    )
    return result


def load_custom_scenario(
    csv_paths: dict[str, str],
    percentile: int = 50,
) -> dict[str, pd.DataFrame]:
    """Load a full scenario (multiple variables) from a dict of CSV paths.

    Parameters
    ----------
    csv_paths : dict[str, str]
        Mapping of variable name -> CSV file path.
        Example: ``{"tas": "data/tas.csv", "tasmax": "data/tasmax.csv", ...}``
    percentile : int
        Percentile label for the single-member data.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of variable name -> DataFrame, ready to slot into the
        ``model_data_dict[scenario]`` level of the morphing pipeline.
    """
    result = {}
    for variable, path in csv_paths.items():
        result[variable] = load_custom_csv(path, variable, percentile=percentile)
    return result
