"""Tests for pyepwmorph v2."""

import os
import tempfile
import shutil
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

TEST_DIR = Path(__file__).parent
TEST_EPW = TEST_DIR / "test.epw"


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

    def test_version_accessible(self):
        import pyepwmorph
        assert hasattr(pyepwmorph, '__version__')
        assert pyepwmorph.__version__ == "2.0.0"

    def test_imports(self):
        from pyepwmorph.tools import io
        from pyepwmorph.tools import utilities
        from pyepwmorph.tools import configuration
        from pyepwmorph.tools import workflow
        from pyepwmorph.models import access, coordinate, assemble, custom
        from pyepwmorph.morph import procedures


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
    # Monthly dates from 1980 to 2060 (97 years × 12 months)
    dates = pd.date_range("1980-01-15", periods=97 * 12, freq="MS")
    rng = np.random.default_rng(42)

    # reference scenario at baseline values; future scenario 2 °C warmer
    scenarios = {"reference": 0.0, "future": 2.0}
    csv_map = {}
    for scenario, offset in scenarios.items():
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
        baseline_range=(1990, 2020),
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
            baseline_range=(1990, 2020),
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
            baseline_range=(1990, 2020),
            write_file=False,
        )
        assert "2030" in result
        assert "2040" in result
        assert result["2030"]["future"]["50"] is not result["2040"]["future"]["50"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

