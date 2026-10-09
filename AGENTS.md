# pyepwmorph

Python library that morphs EnergyPlus Weather (EPW) files with climate-model
data (Belcher et al. 2005 shift/stretch, Jentsch et al. 2013). Published on
PyPI. Its main consumer is the Boundary Conditions web app
(github.com/justinfmccarty/boundary-conditions), which imports internals as
well as the public workflow. See "Downstream contract" below.

## Commands

- `uv sync --extra dev` — install with dev tools
- `uv run --extra dev pytest` — tests (fully offline; bundled EPWs and synthetic CSVs)
- `uv run --extra dev pytest --cov=pyepwmorph` — with coverage
- `uv run --extra dev ruff check pyepwmorph tests gui` — lint
- `uv build` — wheel + sdist (core metadata pinned to 2.4 for twine)
- `python run_gui.py` — tkinter development GUI (`gui/`)
- `python scripts/build_ch2025_table.py` — rebuild `pyepwmorph/data/ch2025_*.parquet` from MeteoSwiss (network)

CI (`.github/workflows/ci.yml`) runs ruff, pytest on Python 3.9–3.13, and a build + `twine check`.

## Layout

- `pyepwmorph/tools/workflow.py` — entry points: `morphing_workflow`, `morph_epw`,
  `compile_climate_model_data`, `iterate_compile_model_data`,
  `compile_custom_model_data`, `compile_ch2025_model_data`
- `pyepwmorph/tools/configuration.py` — `MorphConfig`, `VARIABLE_MAPPING`,
  `VARIABLE_DEPENDENCIES`, `MORPH_ORDER`, `resolve_variable_order`, CH2025 maps
- `pyepwmorph/tools/io.py` — EPW reader/writer (`Epw`, `read_epw_dataframe`, `epw_location`)
- `pyepwmorph/tools/psychrometrics.py` — vectorised ASHRAE 2017 formulas (PsychroLib reference)
- `pyepwmorph/tools/solar.py`, `utilities.py`, `cache.py`
- `pyepwmorph/tools/amy.py` — station table to EPW (actual meteorological year); input
  column contract in its docstring. `amy_meteoswiss.py` is the MeteoSwiss ogd-smn adapter.
  `scripts/build_amy_diffuse_table.py` refits `pyepwmorph/data/amy_diffuse_table.parquet`
  (needs scikit-learn, not a dependency) using the module's own feature code.
- `pyepwmorph/models/` — `access` (Pangeo catalogue), `coordinate` (grid-cell
  selection), `assemble` (ensembles, climatologies), `custom` (CSV input),
  `ch2025` (Swiss station scenarios, offline)
- `pyepwmorph/morph/procedures.py` — per-variable morphing maths
- `pyepwmorph/data/` — shipped parquet tables: CH2025 and the AMY diffuse table (included in the wheel via `artifacts`)
- `examples/` — Justin's personal dev scripts and outputs; mostly untracked on purpose (listed in `.git/info/exclude` locally). Don't commit or clean them up.

Pipeline: `MorphConfig` (reads the EPW, resolves variables and pathways) →
compile model data per pathway × variable (cache → fetch → coordinate →
percentile ensemble) → `morph_epw` per target year × pathway × percentile →
`{year}_{pathway}_{percentile}.epw`.

## Invariants

- **Identity morph.** An unchanged climate must leave the EPW unchanged for
  every variable. The identity-morph tests in `tests/test_pyepwmorph.py`
  caught all five numerical bugs fixed in 3.0.0. Any change to a procedure
  must keep them passing, and a new variable needs its own identity case.
- `relative_delta` returns a ratio, not a percentage. Apply it as a ratio.
- Dependencies are resolved transitively and written to the output, so a
  morphed EPW stays internally consistent (`MorphConfig.resolved_variables`).
- AMY timestamps are hour-ending; an EPW row of hour `h` is the interval ending `h:00` local
  standard time, and station tables must state their clock (`table_utc_offset`). No daylight saving.
- EPWs have no 29 February. Solar and daily calculations use a non-leap
  year (`procedures._year_of`), whatever year the first data row carries.
- Solar geometry uses the fixed UTC offset from the EPW LOCATION line, never a
  named timezone (no daylight saving in weather data).
- Tests never touch the network. Mock or use synthetic data.
- Library code logs through `logging`; no `print`, and no global
  `warnings.filterwarnings`. `DeprecationWarning` from pyepwmorph is an error in tests.
- Python 3.9 is the floor: no `X | Y` type unions, no `match`. Keep
  `typing.Dict/List` where ruff UP006/UP035 are ignored.
- MIT licence. Do not copy code from GPL/AGPL projects (3.0.0 removed one such module).
- CH2025 percentiles are taken of per-chain changes over shared chains
  (`build_ch2025_change_ensemble`), never by differencing two separately
  reduced states.
- Data attribution: CH2025 is CC-BY 4.0 (MeteoSwiss & ETH Zurich); keep the
  citation in `models/ch2025.py` and the README.

## Downstream contract (boundary-conditions backend)

The app depends on `pyepwmorph>=3.2.0` and uses these directly. Changing any
of them is a breaking change for the app: bump accordingly, note it in the
CHANGELOG, and update the app in the same piece of work.

- `tools.io.read_epw_dataframe`, `tools.io.epw_location`; the `Epw` object's
  `.dataframe` and `.write_to_file`
- `tools.psychrometrics.humid_ratio_from_db_rh`, `STANDARD_PRESSURE`
- `tools.configuration.MorphConfig(project_name, epw_fp, user_variables,
  user_pathways, percentiles, target_years, output_directory, model_sources)`
  and attributes `model_sources`, `model_pathways`, `model_variables`,
  `resolved_variables`, `reference_scenario`, `baseline_range`,
  `target_years`, `percentiles`, `output_directory`, `location`, `epw`
- CH2025 (since 3.1.0): `MorphConfig(..., data_source="ch2025",
  ch2025_full_coverage=True)` and its attributes `ch2025_station`
  (`station_id`, `name`, `distance_km`, `elevation_difference_m`,
  `weak_match`) and `ch2025_notes`; `morphing_workflow(...,
  data_source="ch2025", ch2025_full_coverage=True, write_file=True)`
  returning `result[warming_level][percentile]`; pathway labels
  `"GWL 1.5"` ... `"GWL 3.0"` and output names `{gwlX.Y}_{percentile}.epw`;
  `models.ch2025.CH2025_BBOX`
- `tools.io.write_period_of_record(path, start, end)` (since 3.2.0; the app's
  `wfb_task` stamps weather-file-builder output with it)
- `tools.configuration.VARIABLE_MAPPING`, `VARIABLE_DEPENDENCIES` (copied by hand in the app; 3.1.0 added `Radiation`)
- `tools.workflow.compile_climate_model_data(model_sources, pathway, variable,
  longitude, latitude, percentiles, time_slices=None)`
- `tools.workflow.morph_epw(epw, variables, baseline_range, target_range,
  model_data, pathway, percentile, reference_scenario=...)`
- `tools.workflow.morphing_workflow` (fallback path and tests)
- `tools.cache.get_cached_coordinate_data(latitude, longitude, pathway, variable, source_id, time_slices=None)`
- `tools.utilities.calc_period`
- `models.access.access_cmip6_data(models, pathway, variable)` — the app
  replaces it at runtime with an anonymous same-thread zarr open and expects
  a dict of one dataset per catalogue zarr store
- Pathway names ("Best Case Scenario", "Middle of the Road", "Upper Middle
  Scenario", "Worst Case Scenario"), output file naming, and the env vars
  `PYEPWMORPH_CACHE_DIR` / `PYEPWMORPH_CACHE_MAX_MB`

## Releases

1. Add a `## X.Y.Z` section to `CHANGELOG.md` (Keep a Changelog style; call out
   any numerical change that means files should be regenerated).
2. `./release.sh patch|minor|major` — refuses a dirty tree, a branch other than
   `main`, failing lint/tests, or a missing CHANGELOG section; bumps
   `pyproject.toml`, relocks, builds, tags and pushes.
3. `gh release create vX.Y.Z --title "vX.Y.Z" --notes "See CHANGELOG.md."` —
   the GitHub Release triggers `publish.yml` (PyPI trusted publishing).
