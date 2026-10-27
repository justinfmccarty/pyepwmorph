"""CMIP6 grid-cell selection: longitude conventions and the cell record (3.6.0, issue #3)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from pyepwmorph.models import coordinate


def _grid(lon_values, lat_values=None, variable="tas"):
    """Monthly dataset whose value encodes the cell: 1000 * lat index + lon index."""
    lat_values = np.arange(-88.75, 90, 2.5) if lat_values is None else lat_values
    time = pd.date_range("2015-01-01", periods=24, freq="MS")
    lat_index, lon_index = np.meshgrid(np.arange(len(lat_values)), np.arange(len(lon_values)), indexing="ij")
    code = 1000.0 * lat_index + lon_index
    values = np.broadcast_to(code, (len(time),) + code.shape).copy()
    return xr.Dataset(
        {variable: (("time", "lat", "lon"), values)},
        coords={"time": time, "lat": lat_values, "lon": np.asarray(lon_values, dtype=float)},
    )


GRID_360 = np.arange(0.0, 360.0, 2.5)
GRID_180 = np.arange(-180.0, 180.0, 2.5)


@pytest.mark.parametrize("longitude", [-74.0, -122.4, -0.2, 0.3, 8.5, 139.7, 179.9, -179.9])
def test_same_physical_cell_on_both_conventions(longitude):
    lat_360, lon_360 = coordinate.nearest_cell_indices(np.arange(-88.75, 90, 2.5), GRID_360, 40.7, longitude)
    lat_180, lon_180 = coordinate.nearest_cell_indices(np.arange(-88.75, 90, 2.5), GRID_180, 40.7, longitude)
    assert lat_360 == lat_180
    cell_360 = (GRID_360[lon_360] + 180) % 360 - 180
    cell_180 = (GRID_180[lon_180] + 180) % 360 - 180
    assert cell_360 == pytest.approx(cell_180)
    assert abs(coordinate.wrapped_longitude_difference([cell_360], longitude)[0]) <= 1.25


def test_western_site_does_not_snap_to_greenwich():
    _, lon_index = coordinate.nearest_cell_indices([40.0], GRID_360, 40.7, -74.0)
    assert GRID_360[lon_index] == pytest.approx(285.0)


def test_seam_site_picks_the_zero_cell():
    _, lon_index = coordinate.nearest_cell_indices([40.0], GRID_360, 51.5, -0.2)
    assert GRID_360[lon_index] == pytest.approx(0.0)
    # just west of the seam, but nearer 357.5 than 0
    _, lon_index = coordinate.nearest_cell_indices([40.0], GRID_360, 51.5, -1.5)
    assert GRID_360[lon_index] == pytest.approx(357.5)


def test_coordinate_cmip6_data_selects_the_wrapped_cell():
    datasets = {"CMIP.X.ModelA.ssp245.Amon.gn": _grid(GRID_360), "CMIP.Y.ModelB.ssp245.Amon.gn": _grid(GRID_180)}
    result = coordinate.coordinate_cmip6_data(40.7, -74.0, "ssp245", "tas", datasets)
    for ds in result.values():
        assert float(ds["lat"]) == pytest.approx(41.25)
        assert (float(ds["lon"]) + 180) % 360 - 180 == pytest.approx(-75.0)
        assert ds["tas"].dims == ("time",)


def test_cell_summary_reports_distance_and_signed_longitude():
    datasets = {"gs://cmip6/CMIP6/ScenarioMIP/NCAR/CESM2/ssp245/r4i1p1f1/Amon/tas/gn/v20200528/": _grid(GRID_360)}
    selected = coordinate.coordinate_cmip6_data(40.7, -74.0, "ssp245", "tas", datasets)
    cells = coordinate.cell_summary(selected, 40.7, -74.0)
    (name, cell), = cells.items()
    assert coordinate.source_label(name) == "CESM2"
    assert cell["lon"] == pytest.approx(-75.0)
    assert cell["lat"] == pytest.approx(41.25)
    # about 1 deg of longitude and 0.55 deg of latitude at 41 N
    assert 90 < cell["distance_km"] < 110


@pytest.mark.parametrize("name, label", [
    ("ScenarioMIP.NCAR.CESM2.ssp245.Amon.gn", "CESM2"),
    ("gs://cmip6/CMIP6/CMIP/MIROC/MIROC6/historical/r1i1p1f1/Amon/tas/gn/v20181212/", "MIROC6"),
    ("custom", "custom"),
])
def test_source_label(name, label):
    assert coordinate.source_label(name) == label


def test_cell_summary_skips_datasets_without_scalar_coordinates():
    assert coordinate.cell_summary({"a": _grid(GRID_360)}, 40.0, 0.0) == {}


def test_great_circle_wraps_the_dateline():
    assert coordinate.great_circle_km(0.0, 179.9, 0.0, -179.9) == pytest.approx(22.2, abs=0.2)


def test_cache_schema_was_bumped_for_the_wrap_fix():
    from pyepwmorph.tools import cache
    assert cache.CACHE_SCHEMA_VERSION >= 3
    assert cache._get_coordinate_cache_key(40.2, -76.8, "ssp245", "tas", ["CanESM5"]).startswith("v3__")


def test_compile_records_cells_and_morph_names_them(monkeypatch, tmp_path):
    """The cells reach the ensemble's attrs and the morphed EPW's COMMENTS 2."""
    from pathlib import Path

    from pyepwmorph.tools import io as morph_io
    from pyepwmorph.tools import workflow

    monkeypatch.setenv("PYEPWMORPH_CACHE_DIR", str(tmp_path / "cache"))

    def fake_access(models, pathway, variable):
        start = "1950-01-01" if pathway == "historical" else "2015-01-01"
        periods = 65 * 12 if pathway == "historical" else 86 * 12
        time = pd.date_range(start, periods=periods, freq="MS")
        offset = 0.0 if pathway == "historical" else 2.0
        base = {"tas": 285.0, "tasmax": 293.0, "tasmin": 277.0}[variable] + offset
        data = np.full((len(time), len(np.arange(-88.75, 90, 2.5)), len(GRID_360)), base)
        ds = xr.Dataset(
            {variable: (("time", "lat", "lon"), data)},
            coords={"time": time, "lat": np.arange(-88.75, 90, 2.5), "lon": GRID_360},
        )
        return {f"CMIP.X.ModelA.{pathway}.Amon.gn": ds}

    monkeypatch.setattr(workflow.access, "access_cmip6_data", fake_access)
    epw = morph_io.Epw(str(Path(__file__).parent / "test.epw"))
    lat, lon = epw.location["latitude"], epw.location["longitude"]
    model_data = {
        pathway: {
            variable: workflow.compile_climate_model_data(["ModelA"], pathway, variable, lon, lat, [50])
            for variable in ("tas", "tasmax", "tasmin")
        }
        for pathway in ("historical", "ssp245")
    }
    assert "ModelA" in model_data["ssp245"]["tas"].attrs["grid_cells"]
    morphed = workflow.morph_epw(epw, ["Temperature"], (1985, 2014), (2036, 2065), model_data, "ssp245", 50)
    comment = morphed.headers["COMMENTS 2"][0]
    assert "CMIP6 grid cells" in comment and "ModelA" in comment
    assert "," not in comment.split("CMIP6 grid cells")[1]
