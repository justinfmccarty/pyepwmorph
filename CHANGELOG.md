# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## 3.4.0

The actual meteorological year (AMY) builder moves to weather-file-builder,
which now builds every weather file from measured or reanalysis records
(typical, extreme and actual years). pyepwmorph keeps morphing and EPW I/O.
Morphing is unchanged.

### Deprecated

- `tools.amy` and `tools.amy_meteoswiss` warn on import
  (`DeprecationWarning`) and will be removed in 4.0. Use
  `weather_file_builder.amy` and `weather_file_builder.amy_meteoswiss`
  (weather-file-builder 2.1). The copies here are frozen; fixes go to
  weather-file-builder only. These are already fixed there:
  - pressure gaps are filled hour by hour (before, any missing hour put the
    whole year on the standard atmosphere);
  - a year with RH but no dew point builds;
  - night sky cover is no longer missing in a year whose longwave record
    starts part-way.

  The same applies to `scripts/build_amy_diffuse_table.py` and
  `pyepwmorph/data/amy_diffuse_table.parquet` (both removed in 4.0).

## 3.3.0

Adds an actual meteorological year (AMY) builder: one real calendar year of
station measurements becomes an EPW, for model calibration. Morphing is
unchanged.

### Added

- `tools.amy`: `build_amy_dataframe`, `write_amy_epw` and `station_table_to_epw`
  turn a table of hourly or 10-minute station data into an 8760-row EPW. The
  input contract (column names, units, hour-ending timestamps and the clock
  they use) is in the module docstring and `describe_columns()`. Short gaps
  are interpolated, long gaps raise. The header records
  `Period of Record=<year>-<year>` and the methods used.
- Direct and diffuse irradiance are derived from measured global irradiance
  when the station has no components. With sunshine duration (and 10-minute
  data) a shipped lookup table (`pyepwmorph/data/amy_diffuse_table.parquet`,
  fitted by `scripts/build_amy_diffuse_table.py` on MeteoSwiss Affoltern and
  Kloten) gives an hourly diffuse error of about 16% (held-out year and
  station), against about 30% for DIRINT/Erbs. Without sunshine duration the
  DIRINT model is used. The tables describe the Swiss Plateau; elsewhere pass
  `decomposition="dirint"` or measured components.
- Total sky cover is derived from the clear-sky index in daylight and from
  downwelling longwave at other times. Opaque sky cover equals total.
- `tools.amy_meteoswiss`: reader for MeteoSwiss ogd-smn station CSVs and a
  station-metadata location helper.

## 3.2.0

Fixes radiation morphs on leap-year EPWs and the baseline fallback, and
tightens the CH2025 baseline checks.

### Fixed

- **Radiation morphs failed on EPWs whose first data row is a leap year**
  (`ValueError: Expected 365 values, got 366`). EPWs have no 29 February, but
  the solar geometry and daily clearness were built for the leap year, which
  added an empty day. A leap year is now replaced by the year before for
  solar calculations. This affected Clouds and Radiation since 3.0.0 and
  Radiation in 3.1.0.
- **The baseline fallback collapsed to a single year.** Without a Period of
  Record in the header, `detect_baseline_range` read the year column after
  `Epw` had set every row to the first year, so it returned e.g.
  `(2011, 2011)` and a CMIP6 morph compared against a one-year model
  baseline. It now spans the years in the data rows. **CMIP6 files morphed
  from EPWs without a Period of Record (for example from weather-file-builder)
  change and should be regenerated.**

### Changed

- CH2025 baseline checks are stricter. A stated Period of Record (or a
  `baseline_range` passed in) must equal 1991-2020 exactly; 3.1.0 accepted
  any range inside it. When the header states no period, a separate warning
  says the period could not be detected, and the mismatch warning still
  fires if the data rows' years fall outside 1991-2020. Each warning is also
  a line in `MorphConfig.ch2025_notes`.

### Added

- `Epw.detect_baseline_period()` returns the baseline years and whether they
  came from the header (`"comments"`) or the data rows (`"data"`);
  `MorphConfig.baseline_source` records it (`"user"` when passed in).
- `tools.io.write_period_of_record(path, start, end)` writes
  `Period of Record=start-end` into COMMENTS 1 without touching the data,
  for files built by tools that do not record their period.

## 3.1.0

Adds Swiss CH2025 warming-level scenarios and a radiation option that leaves
sky cover alone. Existing CMIP6 and custom-data morphs are unchanged.

### Added

- **CH2025 station scenarios** (`data_source="ch2025"`). MeteoSwiss CH2025
  monthly climatologies for 86 Swiss stations ship with the package
  (`pyepwmorph/data/*.parquet`, about 3 MB), so the morph runs offline.
  Pathways are global warming levels, `"GWL 1.5"`, `"GWL 2.0"`,
  `"GWL 2.5"` and `"GWL 3.0"` (or `gwl1.5` ... `gwl3.0`), relative to
  1991-2020. There is no target year; outputs are named
  `{warming_level}_{percentile}.epw` and `morphing_workflow` returns
  `result[warming_level][percentile]`.
- CH2025 supports Temperature, Humidity (relative humidity stretched
  directly), Wind (scalar surface wind), Radiation and Dew Point. Pressure
  and Clouds and Radiation raise a `ValueError`, as does an EPW outside the
  CH2025 domain.
- The site is matched to the nearest station with an elevation penalty.
  `ch2025_full_coverage=True` (on `MorphConfig` and `morphing_workflow`)
  restricts the match to stations that carry every CH2025 variable.
- Percentiles come from each model chain's own change, over the chains that
  reach the warming level. Differencing separately reduced states mixes
  chains and, at the 10th and 90th percentiles, can change the size and even
  the sign of the signal.
- `MorphConfig.ch2025_station` (with `distance_km`,
  `elevation_difference_m`, `weak_match`) and `MorphConfig.ch2025_notes`
  (plain-language caveats) for callers that show results to users.
- A `UserWarning` when the EPW's years fall outside 1991-2020, recommending
  a TMY built from 1991-2020 data.
- Morphed EPW comments name the CH2025 station and carry the CC-BY 4.0
  attribution.
- **`Radiation` variable** for every data source: morphs global, diffuse and
  direct radiation from `rsds` and leaves sky cover at baseline values. The
  EPW comment and a log warning note that longwave sky temperature will not
  follow the shortwave change.
- `scripts/build_ch2025_table.py` rebuilds the shipped tables from MeteoSwiss.

### Changed

- `VARIABLE_MAPPING` gains `"Radiation": ["rsds"]` and `MORPH_ORDER` gains
  `"Radiation"`. Code that copies these tables should add the entry.
- `resolve_variable_order` and `morph_epw` take an optional `data_source`
  argument (default `"cmip6"`); `morph_epw` also takes `station_label`.
- The wheel build includes `pyepwmorph/data/*.parquet`.

## 3.0.0

This release corrects several morphing calculations. **Morphed humidity, dew
point, wind speed, cloud cover, and direct and diffuse radiation all change**,
so files produced by earlier versions should be regenerated. Dry bulb
temperature, pressure, and global horizontal radiation are unaffected.

### Fixed

- **Relative humidity was inflated even with no climate signal.** `morph_relhum`
  evaluated the psychrometer equation at the dry bulb temperature instead of the
  wet bulb temperature, which overstated vapour pressure. Morphing an EPW with an
  unchanged specific humidity raised relative humidity by a median of 21% and
  pushed hundreds of hours to saturation. The conversion now goes through the
  humidity ratio directly and round-trips exactly.
- **The humidity climate signal was almost entirely discarded.**
  `utilities.relative_delta` returns a ratio, but `morph_relhum` treated it as a
  percentage twice over, turning a 20% change in specific humidity into 1%. A
  +20% and a -20% projection produced identical output. The full ratio is now
  applied.
- **The wind climate signal was almost entirely discarded.** `morph_wspd` had the
  same ratio-as-percentage bug: a 20% modelled increase in wind speed morphed to
  1.2%.
- **Direct normal irradiance could reach physically impossible values.**
  `calc_dirnor` divided the horizontal beam component by the sine of the solar
  altitude with no lower bound, producing values up to 62,000 W/m2 near the
  horizon. Hours below a 2 degree solar altitude are now zeroed and the result is
  capped at the extraterrestrial direct normal irradiance recorded in the EPW.
- **Cloud cover changes below 10 percentage points vanished.** `calc_tsc`
  truncated the shift to an integer before applying it, so a 9 percentage point
  change in cloud fraction became zero tenths. The shift is now carried as a float
  and rounded once, at the end.
- **Diffuse horizontal irradiance is bounded.** The Ridley diffuse fraction is
  clipped to [0, 1] and the result can no longer exceed global horizontal.
- `morph_relhum` now returns a `DatetimeIndex` like every other procedure, instead
  of a `RangeIndex`.
- Appending to the `COMMENTS 2` header no longer raises on EPW files that do not
  carry that line; it is created before `DATA PERIODS` when missing.
- The CMIP6 cache key now includes the `time_slices` argument, so a custom
  temporal slice no longer silently returns data cut to the default bounds.
- `utilities.ts_8760` respects the `year` argument when a timezone is supplied; it
  previously hard-coded 2022.
- `access.build_accessible_data_list` returned `None`; it now returns the list of
  source IDs.

### Changed

- **Dependencies of a requested variable are now written to the output file.**
  Previously, asking for `Humidity` alone computed a morphed dry bulb temperature
  internally but discarded it, while asking for `Dew Point` alone wrote it. Every
  resolved dependency is now written, which keeps the morphed EPW internally
  consistent. `MorphConfig.resolved_variables` exposes the full ordered list.
- **Solar geometry uses a fixed UTC offset** taken from the EPW `LOCATION` line
  and the year of the EPW data. It previously looked up a named IANA timezone,
  which injected daylight saving shifts into local solar time that the weather
  data does not contain, and hard-coded three different years.
- `procedures.calc_dirnor` signature changed. The unused `present_dirnor`
  argument was removed and `extraterrestrial_dirnor` and `min_solar_altitude`
  were added:
  `calc_dirnor(morphed_glohor, morphed_difhor, longitude, latitude, utc_offset, extraterrestrial_dirnor=None, min_solar_altitude=2.0)`
- `procedures.calc_osc` returns integer tenths, matching `calc_tsc` and the EPW
  field definition, instead of floats.
- The CMIP6 cache moved from the system temp directory to the per-user cache
  directory, so it survives a reboot and is not world-readable on shared hosts.
  The default cap rose from 50 MB to 500 MB. `PYEPWMORPH_CACHE_DIR` and
  `PYEPWMORPH_CACHE_MAX_MB` override both.
- Cache lookups moved from `coordinate.coordinate_cmip6_data` into
  `workflow.compile_climate_model_data`, so a cache hit no longer opens the
  remote catalogue first. Calling `coordinate_cmip6_data` directly always
  recomputes.
- `cache.CACHE_DIR` and `cache.CACHE_MAX_SIZE_MB` were replaced by
  `cache.get_cache_dir()` and `cache.get_cache_max_size_mb()`, which read the
  environment on each call.
- The morphing procedures are vectorised. The per-row `DataFrame.apply` calls
  were replaced with numpy broadcasting, which cuts the radiation chain from
  roughly 1.1 s to a few milliseconds per morph.
- Library modules no longer call `warnings.filterwarnings("ignore")` at import
  time, which used to silence warnings for the whole host process.
- The cache and utility modules log instead of printing.
- Minimum pandas raised to 2.2, which is the real floor for the `"ME"` and
  `"h"` resample aliases already in use.

### Removed

- **`pyepwmorph.tools.ladybug_psychrometrics`**, which was copied from an
  AGPL-3.0 project into an MIT-licensed package. It is replaced by
  `pyepwmorph.tools.psychrometrics`, a vectorised implementation of the same
  ASHRAE Handbook (2017) formulas following the MIT-licensed PsychroLib
  reference.
- Unused dependencies: `meteocalc`, `skyfield`, `ipython`, `lz4`, `distributed`,
  and `timezonefinder`.

### Added

- `pyepwmorph.tools.psychrometrics` with vectorised saturation vapour pressure,
  humidity ratio, relative humidity, specific humidity, and dew point functions.
- `configuration.resolve_variable_order`, which expands variable dependencies
  transitively and returns them in a safe morphing order.
- `Epw.add_comment`, which appends to `COMMENTS 2` and creates the header in the
  correct position when it is absent.
- `utilities.month_factors`, `utilities.day_factors`, and `utilities.as_array`
  for broadcasting monthly and daily climatologies onto an hourly index.
- `solar.fixed_offset` for building a daylight-saving-free timezone from an EPW
  UTC offset.
- `morphing_workflow` accepts `time_slices` and forwards it to the CMIP6 fetch.
- A continuous integration workflow running ruff and the test suite on Python
  3.9 through 3.13.
- The test suite grew from 42 to 104 tests, including an identity-morph suite
  that asserts an unchanged climate leaves the EPW unchanged for every variable.
  That suite alone catches all five numerical bugs fixed in this release.

## 2.2.0

- Maintenance release.

## 2.0.0

- **License changed** from GPL-3.0 to MIT.
- `future_years` renamed to `target_years` across the API. The old name is still
  accepted with a deprecation warning.
- `MorphConfig` accepts `data_source`, `custom_data`, `reference_scenario`, and
  `target_years`.
- EPW I/O (`pyepwmorph.tools.io`) rewritten with stricter validation. Files that
  are not exactly 8760 data rows now raise `ValueError`. The lat/lon parsing bug
  in the standalone `epw_location()` function was fixed.
- `coordinate_cmip6_data` accepts an optional `time_slices` dict for custom
  temporal bounds instead of hard-coded 1960-2014 / 2015-2100 bounds.
- Removed `requirements.txt`, `environment.yml`, and `.bumpversion.cfg`. Use
  `uv sync` or `pip install .` instead.
- Per-module `__version__` strings removed. Use `pyepwmorph.__version__` or
  `importlib.metadata.version("pyepwmorph")`.
