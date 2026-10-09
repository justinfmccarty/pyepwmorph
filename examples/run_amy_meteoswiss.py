"""Example: build an actual meteorological year (AMY) EPW from MeteoSwiss station data.

An AMY is one real calendar year of measurements, used to calibrate building
energy models. Run from the repo root:

    uv run python examples/run_amy_meteoswiss.py [data_directory]

Download these from MeteoSwiss open data (https://opendatadocs.meteoswiss.ch/,
dataset "ogd-smn", automatic stations) into ``examples/amy_data/`` (or pass
another directory):

    ogd-smn_sma_t_historical_2020-2029.csv   10-minute data of Zuerich/Fluntern
    ogd-smn_meta_stations.csv                 station metadata (coordinates, elevation)

The hourly file (``ogd-smn_sma_h_historical_2020-2029.csv``) works too; the
10-minute file gives a better diffuse/direct split because it carries the
variability within each hour. The file has to cover the whole year; the decade
file 2020-2029 holds 2025.

Needs no internet connection. The EPW is written to ``examples/amy_result/``.
Neither Zuerich/Fluntern nor most stations measure diffuse radiation, so
direct and diffuse irradiance and sky cover are derived; the printed report
and the EPW header say how. For another network, build a table with the
columns listed by ``amy.describe_columns()`` and call
``amy.build_amy_dataframe`` the same way (``amy.station_table_to_epw`` does
both steps in one call).
"""

import logging
import sys
from pathlib import Path

from pyepwmorph.tools import amy, amy_meteoswiss

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

HERE = Path(__file__).parent
DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "amy_data"
OUTPUT_DIR = HERE / "amy_result"

STATION = "SMA"                                              # Zuerich / Fluntern
YEAR = 2025
MEASUREMENTS = DATA_DIR / "ogd-smn_sma_t_historical_2020-2029.csv"
STATIONS = DATA_DIR / "ogd-smn_meta_stations.csv"

# UTC timestamps that mark the end of each interval, columns renamed to the AMY contract
table = amy_meteoswiss.read_meteoswiss_ogd(str(MEASUREMENTS))
# coordinates and elevation from the metadata; standard time UTC+1 (no daylight saving)
location = amy_meteoswiss.meteoswiss_location(str(STATIONS), STATION)

OUTPUT_DIR.mkdir(exist_ok=True)
output_file = OUTPUT_DIR / f"{STATION.lower()}_{YEAR}_amy.epw"

epw, report = amy.build_amy_dataframe(
    table,
    location,
    YEAR,
    max_gap_hours=6,       # longer gaps in temperature, humidity, wind or radiation raise an error
)
amy.write_amy_epw(
    str(output_file),
    epw,
    location,
    report,
    source_name=f"MeteoSwiss {location['site']} ({STATION})",
    attribution=amy_meteoswiss.ATTRIBUTION,
)

print(report.to_text())
print(f"\nDone. Output written to: {output_file}")
print(f"Mean dry-bulb temperature: {epw['drybulb_C'].mean():.2f} °C")
print(f"Global horizontal radiation: {epw['glohorrad_Whm2'].sum() / 1000:.0f} kWh/m2")
print(f"Diffuse share of global radiation: {epw['difhorrad_Whm2'].sum() / epw['glohorrad_Whm2'].sum():.2f}")
