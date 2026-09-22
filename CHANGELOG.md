# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

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
- The test suite grew from 42 to 103 tests, including an identity-morph suite
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
