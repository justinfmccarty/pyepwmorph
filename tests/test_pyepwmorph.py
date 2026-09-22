"""Tests for pyepwmorph v2."""

import os
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

TEST_DIR = Path(__file__).parent
TEST_EPW = TEST_DIR / "test.epw"

# The pipeline concatenates the reference and target series before slicing, so
# the two scenarios have to cover different years, exactly as the CMIP6
# historical and scenario experiments do.
REFERENCE_MONTHS = pd.date_range("1950-01-01", "2014-12-01", freq="MS")
TARGET_MONTHS = pd.date_range("2015-01-01", "2100-12-01", freq="MS")

#: A baseline entirely inside the reference period, so the baseline
#: climatology is not contaminated by target-period values.
TEST_BASELINE_RANGE = (1985, 2014)


@pytest.fixture(scope="session")
def epw_path():
    if not TEST_EPW.exists():
        pytest.skip("Test EPW file not found")
    return str(TEST_EPW)


@pytest.fixture
def tmp_output(tmp_path):
    return str(tmp_path)


# ---------------------------------------------------------------------------
# EPW I/O
# ---------------------------------------------------------------------------

class TestEpwIO:

    def test_epw_object_creation(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        assert epw.dataframe is not None
        assert len(epw.dataframe) == 8760

    def test_epw_location_keys(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        for key in ('latitude', 'longitude', 'elevation', 'utc_offset'):
            assert key in epw.location
            assert isinstance(epw.location[key], float)

    def test_epw_location_standalone_matches_class(self, epw_path):
        """epw_location() and Epw._read_location() should agree on lat/lon."""
        from pyepwmorph.tools import io as morph_io
        file_lines = morph_io.read_epw_string(epw_path)
        standalone = morph_io.epw_location(file_lines)
        epw = morph_io.Epw(epw_path)
        assert standalone['latitude'] == epw.location['latitude']
        assert standalone['longitude'] == epw.location['longitude']

    def test_essential_columns_present(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        for col in ('drybulb_C', 'relhum_percent', 'atmos_Pa', 'windspd_ms',
                     'glohorrad_Whm2', 'difhorrad_Whm2', 'dirnorrad_Whm2'):
            assert col in epw.dataframe.columns

    def test_baseline_range_detection(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        br = epw.detect_baseline_range()
        assert isinstance(br, tuple)
        assert len(br) == 2
        assert br[0] <= br[1]

    def test_write_and_reread(self, epw_path, tmp_output):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        original_temp = epw.dataframe['drybulb_C'].copy()
        epw.dataframe['drybulb_C'] = original_temp + 2.0

        out_file = os.path.join(tmp_output, "test_output.epw")
        epw.write_to_file(out_file)
        assert os.path.exists(out_file)

        reread = morph_io.Epw(out_file)
        assert len(reread.dataframe) == 8760
        original_epw = morph_io.Epw(epw_path)
        diff = reread.dataframe['drybulb_C'] - original_epw.dataframe['drybulb_C']
        assert abs(diff.mean() - 2.0) < 0.01

    def test_invalid_path_raises(self):
        from pyepwmorph.tools import io as morph_io
        with pytest.raises(FileNotFoundError):
            morph_io.Epw("/nonexistent/path/fake.epw")

    def test_year_derived_from_data(self, epw_path):
        """The datetime index year should come from the EPW data, not be hardcoded."""
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        index_year = epw.dataframe.index[0].year
        data_year = int(epw.dataframe['year'].iloc[0])
        assert index_year == data_year


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class TestUtilities:

    def test_ts_8760_length(self):
        from pyepwmorph.tools import utilities as morph_utils
        ts = morph_utils.ts_8760()
        assert len(ts) == 8760

    def test_ts_8760_leap_year(self):
        from pyepwmorph.tools import utilities as morph_utils
        ts = morph_utils.ts_8760(year=2024)
        assert len(ts) == 8760

    def test_calc_period(self):
        from pyepwmorph.tools import utilities as morph_utils
        result = morph_utils.calc_period(2050, (1990, 2020))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] < 2050 < result[1]

    def test_min_max_mean_means(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        from pyepwmorph.tools import utilities as morph_utils
        epw = morph_io.Epw(epw_path)
        mx, mn, mean = morph_utils.min_max_mean_means(epw.dataframe['drybulb_C'])
        assert len(mx) == 12
        assert len(mn) == 12
        assert len(mean) == 12

    def test_zip_month_data(self):
        from pyepwmorph.tools import utilities as morph_utils
        data = list(range(1, 13))
        result = morph_utils.zip_month_data(data)
        assert isinstance(result, dict)
        assert len(result) == 12
        assert result[1] == 1
        assert result[12] == 12


# ---------------------------------------------------------------------------
# Morphing procedures
# ---------------------------------------------------------------------------

class TestMorphingProcedures:

    def test_shift(self):
        from pyepwmorph.morph import procedures
        data = np.array([10.0, 20.0, 30.0])
        result = procedures.shift(data, 2.0)
        assert np.allclose(result, data + 2.0)

    def test_stretch(self):
        from pyepwmorph.morph import procedures
        data = np.array([10.0, 20.0, 30.0])
        result = procedures.stretch(data, 1.1)
        assert np.allclose(result, data * 1.1)

    def test_shift_stretch(self):
        from pyepwmorph.morph import procedures
        result = procedures.shift_stretch(
            present=20.0, delta=2.0, scaling_factor=0.5, temporal_mean=18.0,
        )
        expected = 20.0 + 2.0 + 0.5 * (20.0 - 18.0)
        assert abs(result - expected) < 1e-10


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestConfiguration:

    def test_cmip6_config_creation(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        config = morph_config.MorphConfig(
            project_name='test_project',
            epw_fp=epw_path,
            user_variables=['Temperature'],
            user_pathways=['Best Case Scenario'],
            percentiles=[50],
            target_years=[2050],
            output_directory=tmp_output,
        )
        assert config.project_name == 'test_project'
        assert config.epw is not None
        assert config.baseline_range is not None
        assert len(config.model_sources) > 0
        assert 'historical' in config.model_pathways
        assert 'ssp126' in config.model_pathways

    def test_backward_compat_future_years(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = morph_config.MorphConfig(
                project_name='test_compat',
                epw_fp=epw_path,
                user_variables=['Temperature'],
                user_pathways=['Best Case Scenario'],
                percentiles=[50],
                future_years=[2050],
                output_directory=tmp_output,
            )
        assert config.target_years == [2050]
        assert any("future_years is deprecated" in str(warning.message) for warning in w)

    def test_variable_dependencies(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        config = morph_config.MorphConfig(
            project_name='test_deps',
            epw_fp=epw_path,
            user_variables=['Humidity'],
            user_pathways=['Best Case Scenario'],
            percentiles=[50],
            target_years=[2050],
            output_directory=tmp_output,
        )
        assert 'huss' in config.model_variables
        assert 'tas' in config.model_variables
        assert 'psl' in config.model_variables

    def test_custom_data_source_config(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        custom_data = {
            "reference": {"tas": "ref_tas.csv"},
            "target_scenario": {"tas": "target_tas.csv"},
        }
        config = morph_config.MorphConfig(
            project_name='test_custom',
            epw_fp=epw_path,
            user_variables=['Temperature'],
            user_pathways=['target_scenario'],
            percentiles=[50],
            target_years=[1990],
            output_directory=tmp_output,
            data_source="custom",
            custom_data=custom_data,
            reference_scenario="reference",
        )
        assert config.data_source == "custom"
        assert config.reference_scenario == "reference"
        assert "reference" in config.model_pathways
        assert "target_scenario" in config.model_pathways

    def test_custom_config_missing_reference_raises(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        custom_data = {
            "target_scenario": {"tas": "target_tas.csv"},
        }
        with pytest.raises(ValueError, match="Reference scenario"):
            morph_config.MorphConfig(
                project_name='test_missing_ref',
                epw_fp=epw_path,
                user_variables=['Temperature'],
                user_pathways=['target_scenario'],
                percentiles=[50],
                target_years=[1990],
                output_directory=tmp_output,
                data_source="custom",
                custom_data=custom_data,
                reference_scenario="reference",
            )

    def test_invalid_epw_in_config_raises(self, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        with pytest.raises(FileNotFoundError):
            morph_config.MorphConfig(
                project_name='test_bad_epw',
                epw_fp='/nonexistent/fake.epw',
                user_variables=['Temperature'],
                user_pathways=['Best Case Scenario'],
                percentiles=[50],
                target_years=[2050],
                output_directory=tmp_output,
            )

    def test_unknown_pathway_passes_through(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        config = morph_config.MorphConfig(
            project_name='test_passthrough',
            epw_fp=epw_path,
            user_variables=['Temperature'],
            user_pathways=['Some Custom Pathway'],
            percentiles=[50],
            target_years=[2050],
            output_directory=tmp_output,
        )
        assert 'Some Custom Pathway' in config.model_pathways


# ---------------------------------------------------------------------------
# Custom data loader
# ---------------------------------------------------------------------------

class TestCustomDataLoader:

    def test_load_custom_csv(self, tmp_output):
        from pyepwmorph.models.custom import load_custom_csv
        csv_path = os.path.join(tmp_output, "test_tas.csv")
        dates = pd.date_range("1980-01-15", periods=120, freq="MS")
        df = pd.DataFrame({"date": dates, "tas": np.random.normal(280, 5, 120)})
        df.to_csv(csv_path, index=False)

        result = load_custom_csv(csv_path, "tas", percentile=50)
        assert isinstance(result, pd.DataFrame)
        assert 50 in result.columns
        assert len(result) == 120

    def test_load_custom_csv_invalid_variable(self, tmp_output):
        from pyepwmorph.models.custom import load_custom_csv
        csv_path = os.path.join(tmp_output, "test_bad.csv")
        dates = pd.date_range("1980-01-15", periods=12, freq="MS")
        df = pd.DataFrame({"date": dates, "tas": np.random.normal(280, 5, 12)})
        df.to_csv(csv_path, index=False)

        with pytest.raises(ValueError, match="not recognised"):
            load_custom_csv(csv_path, "invalid_var")

    def test_load_custom_csv_missing_column(self, tmp_output):
        from pyepwmorph.models.custom import load_custom_csv
        csv_path = os.path.join(tmp_output, "test_missing.csv")
        dates = pd.date_range("1980-01-15", periods=12, freq="MS")
        df = pd.DataFrame({"date": dates, "other_col": np.ones(12)})
        df.to_csv(csv_path, index=False)

        with pytest.raises(ValueError, match="not found in CSV"):
            load_custom_csv(csv_path, "tas")

    def test_load_custom_scenario(self, tmp_output):
        from pyepwmorph.models.custom import load_custom_scenario
        dates = pd.date_range("1980-01-15", periods=60, freq="MS")
        for var in ("tas", "tasmax"):
            csv_path = os.path.join(tmp_output, f"test_{var}.csv")
            df = pd.DataFrame({"date": dates, var: np.random.normal(280, 5, 60)})
            df.to_csv(csv_path, index=False)

        result = load_custom_scenario(
            {"tas": os.path.join(tmp_output, "test_tas.csv"),
             "tasmax": os.path.join(tmp_output, "test_tasmax.csv")},
            percentile=50,
        )
        assert "tas" in result
        assert "tasmax" in result
        assert isinstance(result["tas"], pd.DataFrame)


# ---------------------------------------------------------------------------
# Version and package metadata
# ---------------------------------------------------------------------------

class TestPackageMetadata:

    def test_version_matches_installed_distribution(self):
        from importlib.metadata import version

        import pyepwmorph
        assert pyepwmorph.__version__ == version("pyepwmorph")

    def test_imports(self):
        from pyepwmorph.models import access, assemble, coordinate, custom  # noqa: F401
        from pyepwmorph.morph import procedures  # noqa: F401
        from pyepwmorph.tools import (
            configuration,  # noqa: F401
            io,  # noqa: F401
            psychrometrics,  # noqa: F401
            solar,  # noqa: F401
            utilities,  # noqa: F401
            workflow,  # noqa: F401
        )


# ---------------------------------------------------------------------------
# Data validation
# ---------------------------------------------------------------------------

class TestDataValidation:

    def test_temperature_range(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        temp = epw.dataframe['drybulb_C']
        assert temp.min() > -60
        assert temp.max() < 60

    def test_humidity_range(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        rh = epw.dataframe['relhum_percent']
        assert rh.min() >= 0
        assert rh.max() <= 100


# ---------------------------------------------------------------------------
# Full workflow (custom data)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def custom_climate_data(tmp_path_factory):
    """Generate synthetic monthly climate CSV files for two scenarios."""
    d = tmp_path_factory.mktemp("climate_data")
    rng = np.random.default_rng(42)

    # reference scenario at baseline values; future scenario 2 °C warmer
    scenarios = {"reference": (0.0, REFERENCE_MONTHS), "future": (2.0, TARGET_MONTHS)}
    csv_map = {}
    for scenario, (offset, dates) in scenarios.items():
        s_dir = d / scenario
        s_dir.mkdir()
        csv_map[scenario] = {}
        for var, base in [("tas", 285.0), ("tasmax", 293.0), ("tasmin", 277.0)]:
            vals = base + offset + rng.normal(0, 0.5, len(dates))
            df = pd.DataFrame({"date": dates, var: vals})
            path = s_dir / f"{var}.csv"
            df.to_csv(path, index=False)
            csv_map[scenario][var] = str(path)
    return csv_map


@pytest.fixture(scope="session")
def full_workflow_result(epw_path, custom_climate_data, tmp_path_factory):
    """Run the morphing workflow once with custom data; share results across tests."""
    from pyepwmorph.tools.workflow import morphing_workflow
    output_dir = tmp_path_factory.mktemp("workflow_output")
    result = morphing_workflow(
        project_name="test_full_workflow",
        epw_file=epw_path,
        user_variables=["Temperature"],
        user_pathways=["future"],
        percentiles=[50],
        target_years=[2030],
        output_directory=str(output_dir),
        data_source="custom",
        custom_data=custom_climate_data,
        reference_scenario="reference",
        baseline_range=TEST_BASELINE_RANGE,
        write_file=True,
    )
    return result, output_dir


class TestFullWorkflow:

    def test_result_has_target_year_key(self, full_workflow_result):
        result, _ = full_workflow_result
        assert "2030" in result

    def test_result_has_pathway_key(self, full_workflow_result):
        result, _ = full_workflow_result
        assert "future" in result["2030"]

    def test_result_has_percentile_key(self, full_workflow_result):
        result, _ = full_workflow_result
        assert "50" in result["2030"]["future"]

    def test_morphed_is_epw_object(self, full_workflow_result):
        from pyepwmorph.tools.io import Epw
        result, _ = full_workflow_result
        morphed = result["2030"]["future"]["50"]
        assert isinstance(morphed, Epw)

    def test_morphed_epw_has_8760_rows(self, full_workflow_result):
        result, _ = full_workflow_result
        morphed = result["2030"]["future"]["50"]
        assert len(morphed.dataframe) == 8760

    def test_morphed_year_updated_in_dataframe(self, full_workflow_result):
        result, _ = full_workflow_result
        morphed = result["2030"]["future"]["50"]
        assert int(morphed.dataframe["year"].iloc[0]) == 2030

    def test_temperature_changed_after_morphing(self, epw_path, full_workflow_result):
        from pyepwmorph.tools.io import Epw
        result, _ = full_workflow_result
        morphed = result["2030"]["future"]["50"]
        original = Epw(epw_path)
        mean_abs_diff = (morphed.dataframe["drybulb_C"] - original.dataframe["drybulb_C"]).abs().mean()
        assert mean_abs_diff > 0.0

    def test_output_file_written_to_disk(self, full_workflow_result):
        result, output_dir = full_workflow_result
        expected = output_dir / "2030_future_50.epw"
        assert expected.exists()

    def test_output_epw_is_readable(self, full_workflow_result):
        from pyepwmorph.tools.io import Epw
        result, output_dir = full_workflow_result
        written = Epw(str(output_dir / "2030_future_50.epw"))
        assert len(written.dataframe) == 8760

    def test_write_file_false_produces_no_files(self, epw_path, custom_climate_data, tmp_path_factory):
        from pyepwmorph.tools.workflow import morphing_workflow
        output_dir = tmp_path_factory.mktemp("no_write_output")
        morphing_workflow(
            project_name="test_no_write",
            epw_file=epw_path,
            user_variables=["Temperature"],
            user_pathways=["future"],
            percentiles=[50],
            target_years=[2030],
            output_directory=str(output_dir),
            data_source="custom",
            custom_data=custom_climate_data,
            reference_scenario="reference",
            baseline_range=TEST_BASELINE_RANGE,
            write_file=False,
        )
        epw_files = list(output_dir.glob("*.epw"))
        assert len(epw_files) == 0

    def test_multiple_target_years(self, epw_path, custom_climate_data, tmp_path_factory):
        from pyepwmorph.tools.workflow import morphing_workflow
        result = morphing_workflow(
            project_name="test_multi_year",
            epw_file=epw_path,
            user_variables=["Temperature"],
            user_pathways=["future"],
            percentiles=[50],
            target_years=[2030, 2040],
            data_source="custom",
            custom_data=custom_climate_data,
            reference_scenario="reference",
            baseline_range=TEST_BASELINE_RANGE,
            write_file=False,
        )
        assert "2030" in result
        assert "2040" in result
        assert result["2030"]["future"]["50"] is not result["2040"]["future"]["50"]


# ---------------------------------------------------------------------------
# Psychrometrics
# ---------------------------------------------------------------------------

class TestPsychrometrics:

    def test_saturation_pressure_at_25c(self):
        from pyepwmorph.tools import psychrometrics as psych
        # ASHRAE Handbook - Fundamentals (2017) table 2: 3169.2 Pa at 25 C
        assert abs(psych.saturated_vapor_pressure(25 + 273.15) - 3169.2) < 1.0

    def test_scalar_input_returns_float(self):
        from pyepwmorph.tools import psychrometrics as psych
        assert isinstance(psych.saturated_vapor_pressure(288.15), float)
        assert isinstance(psych.humid_ratio_from_db_rh(20.0, 50.0), float)

    def test_humidity_round_trip(self):
        from pyepwmorph.tools import psychrometrics as psych
        db = np.array([-10.0, 0.0, 15.0, 25.0, 40.0])
        rh = np.array([30.0, 55.0, 80.0, 60.0, 20.0])
        humid_ratio = psych.humid_ratio_from_db_rh(db, rh, 101325.0)
        assert np.allclose(psych.rel_humid_from_db_hr(db, humid_ratio, 101325.0), rh)

    def test_specific_humidity_round_trip(self):
        from pyepwmorph.tools import psychrometrics as psych
        humid_ratio = np.array([0.001, 0.008, 0.02])
        spec = psych.specific_humidity_from_humid_ratio(humid_ratio)
        assert np.allclose(psych.humid_ratio_from_specific_humidity(spec), humid_ratio)

    def test_dew_point_at_saturation_equals_dry_bulb(self):
        from pyepwmorph.tools import psychrometrics as psych
        db = np.array([-5.0, 10.0, 30.0])
        assert np.allclose(psych.dew_point_from_db_rh(db, 100.0), db, atol=0.1)

    def test_dew_point_known_value(self):
        from pyepwmorph.tools import psychrometrics as psych
        # 25 C at 60% RH has a dew point of roughly 16.7 C
        assert abs(psych.dew_point_from_db_rh(25.0, 60.0) - 16.7) < 0.2

    def test_dew_point_is_never_above_dry_bulb(self):
        from pyepwmorph.tools import psychrometrics as psych
        db = np.linspace(-30, 45, 200)
        rh = np.full_like(db, 95.0)
        assert np.all(psych.dew_point_from_db_rh(db, rh) <= db + 1e-9)


# ---------------------------------------------------------------------------
# Broadcasting helpers
# ---------------------------------------------------------------------------

class TestBroadcastHelpers:

    def test_month_factors_maps_each_month(self):
        from pyepwmorph.tools import utilities as morph_utils
        index = morph_utils.ts_8760(year=2021)
        factors = morph_utils.month_factors(index, list(range(1, 13)))
        assert len(factors) == 8760
        assert factors[0] == 1
        assert factors[-1] == 12
        assert np.all(factors[index.month == 7] == 7)

    def test_day_factors_maps_each_day(self):
        from pyepwmorph.tools import utilities as morph_utils
        index = morph_utils.ts_8760(year=2021)
        factors = morph_utils.day_factors(index, list(range(1, 366)))
        assert len(factors) == 8760
        assert factors[0] == 1
        assert factors[-1] == 365

    def test_as_array_rejects_wrong_length(self):
        from pyepwmorph.tools import utilities as morph_utils
        with pytest.raises(ValueError, match="Expected 12 values"):
            morph_utils.as_array([1, 2, 3], 12)

    def test_ts_8760_with_fixed_offset_timezone(self):
        from pyepwmorph.tools import solar as morph_solar
        from pyepwmorph.tools import utilities as morph_utils
        index = morph_utils.ts_8760(year=2021, tz=morph_solar.fixed_offset(-5))
        assert len(index) == 8760
        assert index.tz is not None
        # a fixed offset never jumps, so every step is exactly one hour
        assert (index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all()

    def test_relative_delta_returns_a_ratio(self):
        from pyepwmorph.tools import utilities as morph_utils
        assert morph_utils.relative_delta(12.0, 10.0) == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# Solar helpers
# ---------------------------------------------------------------------------

class TestSolarHelpers:

    def test_persistence_uses_neighbouring_hours(self):
        from pyepwmorph.tools import solar as morph_solar
        clearness = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        flags = np.array([1, 0, 2, 3, 4])
        result = morph_solar.persistence(clearness, flags)
        assert result[0] == pytest.approx(0.1)   # first hour keeps its own value
        assert result[1] == pytest.approx(0.2)   # mean of 0.1 and 0.3
        assert result[2] == pytest.approx(0.4)   # sunrise takes the following hour
        assert result[3] == pytest.approx(0.3)   # sunset takes the preceding hour
        assert result[4] == pytest.approx(0.5)   # last hour keeps its own value

    def test_clearness_is_zero_where_extraterrestrial_is_zero(self):
        from pyepwmorph.tools import solar as morph_solar
        glohor = np.zeros(8760)
        exthor = np.zeros(8760)
        hourly, daily = morph_solar.calc_clearness(glohor, exthor)
        assert len(hourly) == 8760
        assert len(daily) == 365
        assert not np.isnan(hourly).any()

    def test_solar_geometry_has_no_daylight_saving_jump(self):
        from pyepwmorph.tools import solar as morph_solar
        solar_df = morph_solar.solar_geometry(-76.767, 40.2, -5.0, year=2021)
        assert len(solar_df) == 8760
        assert set(solar_df['hour']) == set(range(24))


# ---------------------------------------------------------------------------
# Regression tests for the morphing procedures
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_climatology():
    return pd.Series(np.ones(12), index=range(1, 13))


class TestMorphingSignalStrength:
    """The modelled change must reach the output at full strength."""

    def test_wind_stretch_applies_the_full_ratio(self, epw_path, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import io as morph_io
        present = morph_io.Epw(epw_path).dataframe['windspd_ms']
        calm = flat_climatology * 0
        morphed = procedures.morph_wspd(
            present, flat_climatology * 1.2, flat_climatology, calm, calm,
        )
        assert morphed.mean() / present.mean() == pytest.approx(1.2, abs=1e-3)

    def test_humidity_stretch_applies_the_full_ratio(self, epw_path, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import io as morph_io
        df = morph_io.Epw(epw_path).dataframe
        baseline = flat_climatology * 0.008
        morphed = procedures.morph_relhum(
            df['relhum_percent'], df['atmos_Pa'], df['drybulb_C'],
            df['atmos_Pa'], df['drybulb_C'],
            baseline * 1.2, baseline,
        )
        ratio = morphed.to_numpy() / df['relhum_percent'].to_numpy()
        # saturated hours cannot rise any further, so compare the median
        assert np.median(ratio) == pytest.approx(1.2, abs=0.01)

    def test_humidity_responds_to_the_direction_of_change(self, epw_path, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import io as morph_io
        df = morph_io.Epw(epw_path).dataframe
        baseline = flat_climatology * 0.008

        def morph(factor):
            return procedures.morph_relhum(
                df['relhum_percent'], df['atmos_Pa'], df['drybulb_C'],
                df['atmos_Pa'], df['drybulb_C'], baseline * factor, baseline,
            )

        assert morph(0.8).mean() < df['relhum_percent'].mean() < morph(1.2).mean()

    def test_humidity_returns_a_datetime_index(self, epw_path, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import io as morph_io
        df = morph_io.Epw(epw_path).dataframe
        baseline = flat_climatology * 0.008
        morphed = procedures.morph_relhum(
            df['relhum_percent'], df['atmos_Pa'], df['drybulb_C'],
            df['atmos_Pa'], df['drybulb_C'], baseline, baseline,
        )
        assert isinstance(morphed.index, pd.DatetimeIndex)
        assert morphed.index.equals(df.index)

    def test_cloud_shift_is_rounded_not_truncated(self, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import utilities as morph_utils
        index = morph_utils.ts_8760(year=2021)
        present = pd.Series(np.full(8760, 5), index=index)
        # a nine percentage point change is 0.9 tenths, which must not vanish
        morphed = procedures.calc_tsc(present, flat_climatology * 9, flat_climatology * 0)
        assert (morphed == 6).all()

    def test_small_cloud_change_rounds_to_no_change(self, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import utilities as morph_utils
        index = morph_utils.ts_8760(year=2021)
        present = pd.Series(np.full(8760, 5), index=index)
        morphed = procedures.calc_tsc(present, flat_climatology * 2, flat_climatology * 0)
        assert (morphed == 5).all()

    def test_cloud_cover_stays_within_tenths(self, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import utilities as morph_utils
        index = morph_utils.ts_8760(year=2021)
        present = pd.Series(np.full(8760, 9), index=index)
        morphed = procedures.calc_tsc(present, flat_climatology * 80, flat_climatology * 0)
        assert morphed.max() == 10
        assert morphed.min() >= 0


class TestRadiationBounds:
    """Recalculated irradiance has to stay physically possible."""

    @pytest.fixture
    def morphed_radiation(self, epw_path, flat_climatology):
        from pyepwmorph.morph import procedures
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        df = epw.dataframe
        lon = epw.location['longitude']
        lat = epw.location['latitude']
        utc = epw.location['utc_offset']
        glohor = procedures.morph_glohor(df['glohorrad_Whm2'], flat_climatology, flat_climatology)
        difhor = procedures.calc_difhor(lon, lat, utc, glohor, df['exthorrad_Whm2'])
        dirnor = procedures.calc_dirnor(
            glohor, difhor, lon, lat, utc, extraterrestrial_dirnor=df['extdirrad_Whm2'],
        )
        return df, glohor, difhor, dirnor

    def test_global_horizontal_is_unchanged_without_a_signal(self, morphed_radiation):
        df, glohor, _, _ = morphed_radiation
        assert np.allclose(glohor.to_numpy(), df['glohorrad_Whm2'].to_numpy())

    def test_direct_normal_never_exceeds_extraterrestrial(self, morphed_radiation):
        df, _, _, dirnor = morphed_radiation
        assert (dirnor.to_numpy() <= df['extdirrad_Whm2'].to_numpy()).all()

    def test_direct_normal_stays_in_a_plausible_range(self, morphed_radiation):
        _, _, _, dirnor = morphed_radiation
        assert dirnor.min() >= 0
        assert dirnor.max() < 1400

    def test_diffuse_never_exceeds_global(self, morphed_radiation):
        _, glohor, difhor, _ = morphed_radiation
        assert (difhor.to_numpy() <= glohor.to_numpy() + 1e-6).all()
        assert difhor.min() >= 0

    def test_annual_totals_stay_close_to_the_original(self, morphed_radiation):
        df, _, difhor, dirnor = morphed_radiation
        assert difhor.sum() / df['difhorrad_Whm2'].sum() == pytest.approx(1.0, abs=0.15)
        assert dirnor.sum() / df['dirnorrad_Whm2'].sum() == pytest.approx(1.0, abs=0.15)


# ---------------------------------------------------------------------------
# Variable dependency ordering
# ---------------------------------------------------------------------------

class TestVariableOrdering:

    def test_dew_point_pulls_in_its_dependencies_in_order(self):
        from pyepwmorph.tools.configuration import resolve_variable_order
        assert resolve_variable_order(['Dew Point']) == [
            'Pressure', 'Temperature', 'Humidity', 'Dew Point',
        ]

    def test_order_is_independent_of_input_order(self):
        from pyepwmorph.tools.configuration import resolve_variable_order
        forwards = resolve_variable_order(['Temperature', 'Wind', 'Humidity'])
        backwards = resolve_variable_order(['Humidity', 'Wind', 'Temperature'])
        assert forwards == backwards == ['Pressure', 'Temperature', 'Humidity', 'Wind']

    def test_duplicates_are_collapsed(self):
        from pyepwmorph.tools.configuration import resolve_variable_order
        assert resolve_variable_order(['Wind', 'Wind']) == ['Wind']

    def test_unsupported_variables_are_dropped(self):
        from pyepwmorph.tools.configuration import resolve_variable_order
        assert resolve_variable_order(['Temperature', 'Precipitation']) == ['Temperature']

    def test_config_exposes_resolved_variables(self, epw_path, tmp_output):
        from pyepwmorph.tools import configuration as morph_config
        config = morph_config.MorphConfig(
            project_name='ordering',
            epw_fp=epw_path,
            user_variables=['Dew Point'],
            user_pathways=['Best Case Scenario'],
            percentiles=[50],
            target_years=[2050],
            output_directory=tmp_output,
        )
        assert config.resolved_variables == ['Pressure', 'Temperature', 'Humidity', 'Dew Point']
        assert set(config.model_variables) == {'psl', 'tas', 'tasmax', 'tasmin', 'huss'}


# ---------------------------------------------------------------------------
# EPW header handling
# ---------------------------------------------------------------------------

class TestEpwComments:

    def test_comment_is_appended(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        before = epw.headers['COMMENTS 2'][0]
        epw.add_comment(" morphed")
        assert epw.headers['COMMENTS 2'][0] == before + " morphed"

    def test_missing_comment_header_is_created_before_data_periods(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        del epw.headers['COMMENTS 2']
        epw.add_comment("added")
        keys = list(epw.headers)
        assert keys.index('COMMENTS 2') < keys.index('DATA PERIODS')
        assert epw.headers['COMMENTS 2'] == ['added']

    def test_empty_comment_header_is_survivable(self, epw_path):
        from pyepwmorph.tools import io as morph_io
        epw = morph_io.Epw(epw_path)
        epw.headers['COMMENTS 2'] = []
        epw.add_comment("added")
        assert epw.headers['COMMENTS 2'] == ['added']


# ---------------------------------------------------------------------------
# Identity morph: an unchanged climate must leave the EPW unchanged
# ---------------------------------------------------------------------------

#: Constant values, so every monthly climatology is identical regardless of
#: which years the baseline and target periods cover.
CONSTANT_CLIMATE = {
    "tas": 285.0, "tasmax": 293.0, "tasmin": 277.0,
    "huss": 0.008, "psl": 101325.0,
    "uas": 2.0, "vas": 3.0,
    "clt": 50.0, "rsds": 150.0,
}

ALL_VARIABLES = [
    "Temperature", "Humidity", "Pressure", "Wind", "Clouds and Radiation", "Dew Point",
]


def _write_scenario(directory, values, months):
    """Write one monthly CSV per variable and return the variable -> path map."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for variable, value in values.items():
        frame = pd.DataFrame({"date": months, variable: np.full(len(months), value)})
        path = directory / f"{variable}.csv"
        frame.to_csv(path, index=False)
        paths[variable] = str(path)
    return paths


@pytest.fixture(scope="session")
def identity_climate_data(tmp_path_factory):
    """Reference and target scenarios holding exactly the same values."""
    root = tmp_path_factory.mktemp("identity_climate")
    return {
        "reference": _write_scenario(root / "reference", CONSTANT_CLIMATE, REFERENCE_MONTHS),
        "target": _write_scenario(root / "target", CONSTANT_CLIMATE, TARGET_MONTHS),
    }


@pytest.fixture(scope="session")
def identity_morph(epw_path, identity_climate_data):
    from pyepwmorph.tools.io import Epw
    from pyepwmorph.tools.workflow import morphing_workflow
    result = morphing_workflow(
        project_name="identity",
        epw_file=epw_path,
        user_variables=ALL_VARIABLES,
        user_pathways=["target"],
        percentiles=[50],
        target_years=[2050],
        data_source="custom",
        custom_data=identity_climate_data,
        reference_scenario="reference",
        baseline_range=TEST_BASELINE_RANGE,
        write_file=False,
    )
    return result["2050"]["target"]["50"], Epw(epw_path)


class TestIdentityMorph:
    """With no climate signal the morph must be a no-op for every shifted or
    stretched variable.  Dew point and the two derived irradiance components
    are recalculated from scratch rather than shifted, so they are only
    required to stay close to the original."""

    @pytest.mark.parametrize("column", [
        "drybulb_C", "atmos_Pa", "relhum_percent", "windspd_ms",
        "glohorrad_Whm2", "totskycvr_tenths", "opaqskycvr_tenths",
    ])
    def test_column_is_unchanged(self, identity_morph, column):
        morphed, original = identity_morph
        assert np.allclose(
            morphed.dataframe[column].to_numpy(dtype=float),
            original.dataframe[column].to_numpy(dtype=float),
            atol=0.01,
        )

    def test_dew_point_is_recovered_within_tolerance(self, identity_morph):
        morphed, original = identity_morph
        difference = (morphed.dataframe['dewpoint_C'] - original.dataframe['dewpoint_C']).abs()
        assert difference.mean() < 0.5

    def test_derived_irradiance_stays_close(self, identity_morph):
        morphed, original = identity_morph
        for column in ("difhorrad_Whm2", "dirnorrad_Whm2"):
            ratio = morphed.dataframe[column].sum() / original.dataframe[column].sum()
            assert ratio == pytest.approx(1.0, abs=0.15)

    def test_all_dependencies_are_recorded_in_the_comment(self, identity_morph):
        morphed, _ = identity_morph
        comment = morphed.headers['COMMENTS 2'][0]
        assert "morphed for target" in comment
        for column in ("atmos_Pa", "drybulb_C", "relhum_percent", "dewpoint_C",
                       "windspd_ms", "glohorrad_Whm2", "totskycvr_tenths"):
            assert column in comment

    def test_comment_survives_a_write_and_reread(self, identity_morph, tmp_path):
        from pyepwmorph.tools.io import Epw
        morphed, _ = identity_morph
        out_file = tmp_path / "comment.epw"
        morphed.write_to_file(str(out_file))
        # the comment must stay in a single header field, not split on commas
        assert Epw(str(out_file)).headers['COMMENTS 2'] == morphed.headers['COMMENTS 2']

    def test_output_is_still_a_valid_epw(self, identity_morph, tmp_path):
        from pyepwmorph.tools.io import Epw
        morphed, _ = identity_morph
        out_file = tmp_path / "identity.epw"
        morphed.write_to_file(str(out_file))
        assert len(Epw(str(out_file)).dataframe) == 8760


# ---------------------------------------------------------------------------
# Signal morph: a known climate signal must reach every variable
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def warmer_climate_data(tmp_path_factory):
    """A target scenario that is warmer, wetter, windier, and cloudier."""
    root = tmp_path_factory.mktemp("warmer_climate")
    warmer = dict(CONSTANT_CLIMATE)
    warmer.update({
        "tas": 287.0, "tasmax": 295.0, "tasmin": 279.0,
        "huss": 0.0088,
        "uas": 2.2, "vas": 3.3,
        "clt": 60.0,
        "rsds": 140.0,
    })
    return {
        "reference": _write_scenario(root / "reference", CONSTANT_CLIMATE, REFERENCE_MONTHS),
        "warmer": _write_scenario(root / "warmer", warmer, TARGET_MONTHS),
    }


@pytest.fixture(scope="session")
def warmer_morph(epw_path, warmer_climate_data):
    from pyepwmorph.tools.io import Epw
    from pyepwmorph.tools.workflow import morphing_workflow
    result = morphing_workflow(
        project_name="warmer",
        epw_file=epw_path,
        user_variables=ALL_VARIABLES,
        user_pathways=["warmer"],
        percentiles=[50],
        target_years=[2050],
        data_source="custom",
        custom_data=warmer_climate_data,
        reference_scenario="reference",
        baseline_range=TEST_BASELINE_RANGE,
        write_file=False,
    )
    return result["2050"]["warmer"]["50"], Epw(epw_path)


class TestSignalMorph:

    def test_temperature_warms_by_the_modelled_delta(self, warmer_morph):
        morphed, original = warmer_morph
        delta = (morphed.dataframe['drybulb_C'] - original.dataframe['drybulb_C']).mean()
        assert delta == pytest.approx(2.0, abs=0.05)

    def test_wind_speeds_up_by_the_modelled_ratio(self, warmer_morph):
        morphed, original = warmer_morph
        ratio = morphed.dataframe['windspd_ms'].mean() / original.dataframe['windspd_ms'].mean()
        assert ratio == pytest.approx(1.1, abs=0.01)

    def test_cloud_cover_increases(self, warmer_morph):
        morphed, original = warmer_morph
        delta = (morphed.dataframe['totskycvr_tenths'] - original.dataframe['totskycvr_tenths']).mean()
        assert delta > 0.3

    def test_global_horizontal_decreases(self, warmer_morph):
        morphed, original = warmer_morph
        assert morphed.dataframe['glohorrad_Whm2'].sum() < original.dataframe['glohorrad_Whm2'].sum()

    def test_derived_irradiance_remains_bounded(self, warmer_morph):
        morphed, _ = warmer_morph
        df = morphed.dataframe
        assert (df['difhorrad_Whm2'] <= df['glohorrad_Whm2'] + 1e-6).all()
        assert (df['dirnorrad_Whm2'] <= df['extdirrad_Whm2']).all()
        assert df['dirnorrad_Whm2'].min() >= 0

    def test_dew_point_follows_temperature_and_humidity(self, warmer_morph):
        morphed, original = warmer_morph
        assert morphed.dataframe['dewpoint_C'].mean() > original.dataframe['dewpoint_C'].mean()

    def test_relative_humidity_stays_in_range(self, warmer_morph):
        morphed, _ = warmer_morph
        rh = morphed.dataframe['relhum_percent']
        assert rh.min() >= 1
        assert rh.max() <= 100

    def test_requesting_only_dew_point_also_writes_its_dependencies(
            self, epw_path, warmer_climate_data):
        from pyepwmorph.tools.io import Epw
        from pyepwmorph.tools.workflow import morphing_workflow
        result = morphing_workflow(
            project_name="dewpoint_only",
            epw_file=epw_path,
            user_variables=["Dew Point"],
            user_pathways=["warmer"],
            percentiles=[50],
            target_years=[2050],
            data_source="custom",
            custom_data=warmer_climate_data,
            reference_scenario="reference",
            baseline_range=TEST_BASELINE_RANGE,
            write_file=False,
        )
        morphed = result["2050"]["warmer"]["50"]
        original = Epw(epw_path)
        for column in ("drybulb_C", "relhum_percent", "dewpoint_C"):
            assert not np.allclose(
                morphed.dataframe[column].to_numpy(dtype=float),
                original.dataframe[column].to_numpy(dtype=float),
            )

    def test_requesting_only_humidity_also_writes_temperature(
            self, epw_path, warmer_climate_data):
        from pyepwmorph.tools.io import Epw
        from pyepwmorph.tools.workflow import morphing_workflow
        result = morphing_workflow(
            project_name="humidity_only",
            epw_file=epw_path,
            user_variables=["Humidity"],
            user_pathways=["warmer"],
            percentiles=[50],
            target_years=[2050],
            data_source="custom",
            custom_data=warmer_climate_data,
            reference_scenario="reference",
            baseline_range=TEST_BASELINE_RANGE,
            write_file=False,
        )
        morphed = result["2050"]["warmer"]["50"].dataframe
        original = Epw(epw_path).dataframe
        assert (morphed['drybulb_C'] - original['drybulb_C']).mean() == pytest.approx(2.0, abs=0.05)


# ---------------------------------------------------------------------------
# Cache keys
# ---------------------------------------------------------------------------

class TestCache:

    def test_cache_directory_honours_the_environment(self, tmp_path, monkeypatch):
        from pyepwmorph.tools import cache
        monkeypatch.setenv(cache.CACHE_DIR_ENV_VAR, str(tmp_path / "cache"))
        assert cache.get_cache_dir() == tmp_path / "cache"

    def test_cache_directory_is_not_a_temp_directory_by_default(self, monkeypatch):
        from pyepwmorph.tools import cache
        monkeypatch.delenv(cache.CACHE_DIR_ENV_VAR, raising=False)
        assert tempfile.gettempdir() not in str(cache.get_cache_dir())

    def test_time_slices_change_the_cache_key(self):
        from pyepwmorph.tools import cache
        without = cache._get_coordinate_cache_key(40.2, -76.8, 'ssp245', 'tas', ['CanESM5'])
        with_slices = cache._get_coordinate_cache_key(
            40.2, -76.8, 'ssp245', 'tas', ['CanESM5'], time_slices={'ssp245': ('2020', '2060')},
        )
        assert without != with_slices

    def test_source_order_does_not_change_the_cache_key(self):
        from pyepwmorph.tools import cache
        first = cache._get_coordinate_cache_key(40.2, -76.8, 'ssp245', 'tas', ['CanESM5', 'TaiESM1'])
        second = cache._get_coordinate_cache_key(40.2, -76.8, 'ssp245', 'tas', ['TaiESM1', 'CanESM5'])
        assert first == second

    def test_cache_round_trip(self, tmp_path, monkeypatch):
        from pyepwmorph.tools import cache
        monkeypatch.setenv(cache.CACHE_DIR_ENV_VAR, str(tmp_path / "cache"))
        payload = {"model": [1, 2, 3]}
        cache.save_coordinate_to_cache(payload, 40.2, -76.8, 'ssp245', 'tas', ['CanESM5'])
        assert cache.get_cached_coordinate_data(40.2, -76.8, 'ssp245', 'tas', ['CanESM5']) == payload
        assert cache.get_cached_coordinate_data(40.2, -76.8, 'ssp585', 'tas', ['CanESM5']) is None

    def test_clear_cache_removes_entries(self, tmp_path, monkeypatch):
        from pyepwmorph.tools import cache
        monkeypatch.setenv(cache.CACHE_DIR_ENV_VAR, str(tmp_path / "cache"))
        cache.save_coordinate_to_cache({"a": 1}, 40.2, -76.8, 'ssp245', 'tas', ['CanESM5'])
        assert cache.get_cache_stats()["total_files"] == 1
        cache.clear_cache()
        assert cache.get_cache_stats()["total_files"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

