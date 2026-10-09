"""Tests for the deprecated AMY builder (moved to weather-file-builder). Fully offline, synthetic data."""

import importlib
import warnings

import numpy as np
import pandas as pd
import pvlib
import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from pyepwmorph.tools import amy, amy_meteoswiss
from pyepwmorph.tools.io import EPW_COLUMN_NAMES, Epw, epw_baseline_range, read_epw_string

LOCATION = dict(
    site="Testville", province="ZH", country_code="CHE", type="synthetic", usaf="000000",
    latitude=47.38, longitude=8.57, elevation=600.0, utc_offset=1.0,
)


def _hourly_table(year, with_sunshine=True, label="end"):
    """A full synthetic year of hourly data on a UTC clock.

    With ``label="end"`` the first row is labelled ``year-01-01 00:00``, the end of the hour
    23:00-24:00 UTC, which is the first hour of the year in local standard time (UTC+1).
    """
    start = pd.Timestamp(f"{year}-01-01 00:00") - pd.Timedelta(hours=0 if label == "end" else 1)
    n = 8784 if pd.Timestamp(f"{year}-12-31").dayofyear == 366 else 8760
    index = pd.date_range(start, periods=n, freq="h")
    # solar position at the middle of each interval, in UTC
    mid = (index - pd.Timedelta(minutes=30) if label == "end" else index + pd.Timedelta(minutes=30)).tz_localize("UTC")
    loc = pvlib.location.Location(LOCATION["latitude"], LOCATION["longitude"], altitude=LOCATION["elevation"])
    clear = loc.get_clearsky(mid)["ghi"].to_numpy()
    day = np.arange(n) / 24.0
    cloud = 0.55 + 0.35 * np.sin(day * 0.9)
    ghi = clear * np.clip(cloud, 0.1, 1.0)
    temp = 10.0 + 12.0 * np.sin((day - 110) / 365.25 * 2 * np.pi) + 4.0 * np.sin((np.arange(n) % 24 - 9) / 24 * 2 * np.pi)
    table = pd.DataFrame(
        {
            "temp_C": temp,
            "rh_pct": np.clip(75 - 20 * np.sin((np.arange(n) % 24 - 9) / 24 * 2 * np.pi), 20, 100),
            "ghi_Wm2": ghi,
            "wind_speed_ms": 2.0 + np.abs(np.sin(day)),
            "wind_dir_deg": (200 + 60 * np.sin(day / 3)) % 360,
            "precip_mm": np.where(np.arange(n) % 37 == 0, 1.2, 0.0),
        },
        index=index,
    )
    if with_sunshine:
        table["sunshine_min"] = np.clip((cloud - 0.35) / 0.4, 0, 1) * 60 * (ghi > 20)
    return table


@pytest.fixture(scope="module")
def built():
    table = _hourly_table(2025)
    epw, report = amy.build_amy_dataframe(table, LOCATION, 2025)
    return table, epw, report


def test_describe_columns_lists_required_inputs():
    spec = amy.describe_columns()
    assert {"temp_C", "ghi_Wm2", "wind_speed_ms", "wind_dir_deg"} <= set(spec.index)
    assert spec.loc["temp_C", "required"] is True
    assert spec.loc["precip_mm", "aggregation"] == "sum"


def test_output_has_epw_shape(built):
    _, epw, report = built
    assert list(epw.columns) == EPW_COLUMN_NAMES
    assert len(epw) == 8760
    assert epw["hour"].min() == 1 and epw["hour"].max() == 24
    assert set(epw["year"]) == {2025}
    assert not ((epw["month"] == 2) & (epw["day"] == 29)).any()
    assert report.year == 2025
    assert epw.iloc[0][["month", "day", "hour"]].tolist() == [1, 1, 1]
    assert epw.iloc[-1][["month", "day", "hour"]].tolist() == [12, 31, 24]


def test_hour_ending_utc_maps_to_local_standard_time():
    """UTC label 00:00 ends the interval 23:00-24:00 UTC = 00:00-01:00 local = EPW hour 1."""
    table = _hourly_table(2025)
    table["temp_C"] = np.arange(len(table)) % 100 / 10.0 + 1.0  # the row number is the signal
    epw, _ = amy.build_amy_dataframe(table, LOCATION, 2025)
    # the first EPW row (Jan 1, hour 1) is the table row labelled 2025-01-01 00:00 UTC
    assert epw["drybulb_C"].iloc[0] == round(table["temp_C"].iloc[0], 1)
    # EPW hour h of day D is the UTC label D at (h - 1):00
    assert epw["drybulb_C"].iloc[24 * 40 + 5] == round(table["temp_C"].iloc[24 * 40 + 5], 1)
    assert epw["drybulb_C"].iloc[-1] == round(table["temp_C"].loc["2025-12-31 23:00"], 1)


def test_start_label_gives_the_same_epw():
    end = _hourly_table(2025, label="end")
    start = _hourly_table(2025, label="start")
    start.index = end.index - pd.Timedelta(hours=1)
    a, _ = amy.build_amy_dataframe(end, LOCATION, 2025)
    b, _ = amy.build_amy_dataframe(start, LOCATION, 2025, timestamp_label="start")
    pd.testing.assert_frame_equal(a, b)


def test_table_in_local_standard_time():
    utc = _hourly_table(2025)
    local = utc.copy()
    local.index = local.index + pd.Timedelta(hours=1)
    a, _ = amy.build_amy_dataframe(utc, LOCATION, 2025)
    b, _ = amy.build_amy_dataframe(local, LOCATION, 2025, table_utc_offset=1.0)
    pd.testing.assert_frame_equal(a, b)


def test_leap_year_drops_29_february():
    table = _hourly_table(2024)
    epw, report = amy.build_amy_dataframe(table, LOCATION, 2024)
    assert len(epw) == 8760
    assert not ((epw["month"] == 2) & (epw["day"] == 29)).any()
    assert "29 February dropped" in report.notes
    assert epw[(epw["month"] == 3) & (epw["day"] == 1)]["hour"].tolist() == list(range(1, 25))


def test_irradiance_closes_and_night_is_dark(built):
    _, epw, _ = built
    start = pd.date_range("2025-01-01", periods=8760, freq="h")
    start = start[~((start.month == 2) & (start.day == 29))]
    solar = amy._solar_frame(start, LOCATION)
    cosz = np.cos(np.radians(np.minimum(solar["zenith"].to_numpy(), 89.0)))
    high = solar["zenith"].to_numpy() < 85
    closure = epw["glohorrad_Whm2"].to_numpy() - (epw["dirnorrad_Whm2"].to_numpy() * cosz + epw["difhorrad_Whm2"].to_numpy())
    assert np.abs(closure[high]).max() <= 0.5 * cosz[high].max() + 1.0
    assert (epw["dirnorrad_Whm2"][solar["zenith"].to_numpy() >= 85] == 0).all()
    assert (epw["glohorrad_Whm2"][solar["zenith"].to_numpy() > 100] == 0).all()
    assert (epw["difhorrad_Whm2"] <= epw["glohorrad_Whm2"] + 1).all()
    assert epw["dirnorrad_Whm2"].max() < 1100


def test_decomposition_uses_the_table_with_sunshine_and_dirint_without():
    with_s = _hourly_table(2025, with_sunshine=True)
    _, r1 = amy.build_amy_dataframe(with_s, LOCATION, 2025)
    assert any(k.startswith("table") for k in r1.decomposition)
    without = _hourly_table(2025, with_sunshine=False)
    _, r2 = amy.build_amy_dataframe(without, LOCATION, 2025)
    assert "dirint" in r2.decomposition and not any(k.startswith("table") for k in r2.decomposition)


def test_measured_diffuse_is_kept():
    table = _hourly_table(2025)
    table["dhi_Wm2"] = 0.3 * table["ghi_Wm2"]
    epw, report = amy.build_amy_dataframe(table, LOCATION, 2025)
    assert report.decomposition.get("measured", 0) > 1000
    day = epw["glohorrad_Whm2"] > 100
    ratio = epw.loc[day, "difhorrad_Whm2"] / epw.loc[day, "glohorrad_Whm2"]
    assert abs(ratio.median() - 0.3) < 0.02


def test_table_method_needs_sunshine():
    with pytest.raises(ValueError, match="sunshine_min"):
        amy.build_amy_dataframe(_hourly_table(2025, with_sunshine=False), LOCATION, 2025, decomposition="table")


def test_short_gap_is_interpolated_and_reported():
    table = _hourly_table(2025)
    table.loc["2025-06-10 10:00":"2025-06-10 12:00", ["temp_C", "wind_dir_deg", "ghi_Wm2"]] = np.nan
    epw, report = amy.build_amy_dataframe(table, LOCATION, 2025)
    assert report.filled_hours["temp_C"] == 3
    assert report.filled_hours["ghi_Wm2"] == 3
    assert epw["drybulb_C"].notna().all()


def test_long_gap_raises_unless_allowed():
    table = _hourly_table(2025)
    table.loc["2025-03-03 00:00":"2025-03-03 11:00", "temp_C"] = np.nan
    with pytest.raises(ValueError, match="temp_C: 12 h"):
        amy.build_amy_dataframe(table, LOCATION, 2025)
    epw, report = amy.build_amy_dataframe(table, LOCATION, 2025, long_gap="interpolate")
    assert epw["drybulb_C"].notna().all()
    assert any("long gaps" in n for n in report.notes)


def test_too_little_data_for_the_year_raises():
    table = _hourly_table(2025).iloc[:2000]
    with pytest.raises(ValueError, match="covers only"):
        amy.build_amy_dataframe(table, LOCATION, 2025)


def test_missing_required_column_and_fractional_shift():
    table = _hourly_table(2025).drop(columns="wind_speed_ms")
    with pytest.raises(ValueError, match="wind_speed_ms"):
        amy.build_amy_dataframe(table, LOCATION, 2025)
    with pytest.raises(ValueError, match="fractional"):
        amy.build_amy_dataframe(_hourly_table(2025), LOCATION, 2025, table_utc_offset=0.5)


def test_ten_minute_aggregation_rules():
    index = pd.date_range("2025-03-01 00:10", periods=6 * 4, freq="10min")  # hour-ending, UTC
    table = pd.DataFrame(
        {
            "temp_C": np.arange(24, dtype=float),
            "rh_pct": 80.0,
            "ghi_Wm2": 0.0,
            "wind_speed_ms": 2.0,
            "wind_dir_deg": [350.0, 10.0] * 12,
            "precip_mm": 0.1,
            "sunshine_min": 2.0,
        },
        index=index,
    )
    hourly, step = amy.aggregate_to_hourly(table, LOCATION)
    assert step == 10
    # label 01:00 UTC ends the hour 00:00-01:00 UTC, which starts 01:00 local
    assert hourly.index[0] == pd.Timestamp("2025-03-01 01:00")
    assert hourly["temp_C"].iloc[0] == pytest.approx(2.5)
    assert hourly["precip_mm"].iloc[0] == pytest.approx(0.6)
    assert hourly["sunshine_min"].iloc[0] == pytest.approx(12.0)
    direction = hourly["wind_dir_deg"].iloc[0]
    assert min(direction, 360 - direction) < 1.0  # 350 and 10 average to north, not south
    table.iloc[3, table.columns.get_loc("temp_C")] = np.nan
    assert np.isnan(amy.aggregate_to_hourly(table, LOCATION)[0]["temp_C"].iloc[0])


def test_sub_hourly_variability_is_measured():
    index = pd.date_range("2025-06-21 06:10", periods=6 * 3, freq="10min")
    steady = pd.DataFrame({"temp_C": 15.0, "rh_pct": 60.0, "ghi_Wm2": 600.0, "wind_speed_ms": 1.0, "wind_dir_deg": 90.0}, index=index)
    gusty = steady.copy()
    gusty["ghi_Wm2"] = [100.0, 800.0] * 9
    sd_steady = amy.aggregate_to_hourly(steady, LOCATION)[0]["ghi_kt_std"].iloc[0]
    sd_gusty = amy.aggregate_to_hourly(gusty, LOCATION)[0]["ghi_kt_std"].iloc[0]
    assert sd_gusty > 5 * sd_steady


def test_pressure_defaults_to_standard_atmosphere(built):
    _, epw, report = built
    assert any("standard atmosphere" in n for n in report.notes)
    assert 90000 < epw["atmos_Pa"].iloc[0] < 96000


def test_dewpoint_and_rh_are_consistent(built):
    _, epw, _ = built
    assert (epw["dewpoint_C"] <= epw["drybulb_C"] + 1e-9).all()
    assert epw["relhum_percent"].between(0, 100).all()


def test_sky_cover_tenths_and_missing_codes(built):
    _, epw, report = built
    assert epw["totskycvr_tenths"].between(0, 10).all()
    assert (epw["opaqskycvr_tenths"] == epw["totskycvr_tenths"]).all()
    assert report.sky_cover_method
    assert (epw["visibility_km"] == 9999).all() and (epw["ceiling_hgt_m"] == 99999).all()
    assert (epw["horirsky_Whm2"] == 9999).all()  # no longwave in the synthetic table


def test_clear_days_have_less_cloud_than_overcast_days():
    table = _hourly_table(2025)
    clear_day = table.index.dayofyear == 170
    over_day = table.index.dayofyear == 171
    loc = pvlib.location.Location(LOCATION["latitude"], LOCATION["longitude"], altitude=LOCATION["elevation"])
    clear = loc.get_clearsky((table.index - pd.Timedelta(minutes=30)).tz_localize("UTC"))["ghi"].to_numpy()
    table.loc[clear_day, "ghi_Wm2"] = clear[clear_day]
    table.loc[over_day, "ghi_Wm2"] = 0.15 * clear[over_day]
    epw, _ = amy.build_amy_dataframe(table, LOCATION, 2025)
    noon = epw["hour"] == 14
    june19 = (epw["month"] == 6) & (epw["day"] == 19)
    june20 = (epw["month"] == 6) & (epw["day"] == 20)
    assert epw.loc[june19 & noon, "totskycvr_tenths"].iloc[0] <= 2
    assert epw.loc[june20 & noon, "totskycvr_tenths"].iloc[0] >= 8


def test_longwave_fills_horizontal_ir_and_calibrates_night_cover():
    table = _hourly_table(2025)
    n = len(table)
    cover = 0.5 + 0.4 * np.sin(np.arange(n) / 30.0)
    sigma = 5.670374419e-8
    eps_clear = 0.711 + 0.0056 * 5.0
    table["lw_down_Wm2"] = sigma * (table["temp_C"] + 273.15) ** 4 * (eps_clear + (1 - eps_clear) * cover * 0.9)
    epw, report = amy.build_amy_dataframe(table, LOCATION, 2025)
    assert epw["horirsky_Whm2"].between(100, 500).all()
    assert "longwave" in report.sky_cover_method


def test_written_file_reads_back(tmp_path, built):
    table, epw, report = built
    path = str(tmp_path / "amy.epw")
    amy.write_amy_epw(path, epw, LOCATION, report, source_name="a synthetic station", attribution="Source: test")
    reread = Epw(path)
    assert len(reread.dataframe) == 8760
    assert list(reread.dataframe.columns) == EPW_COLUMN_NAMES
    assert reread.location["site"] == "Testville"
    assert reread.location["utc_offset"] == 1.0
    assert reread.location["elevation"] == 600.0
    assert epw_baseline_range(read_epw_string(path)) == (2025, 2025)
    assert "DATA PERIODS,1,1,Data,Wednesday,1/1,12/31" in "".join(read_epw_string(path))
    assert reread.dataframe["glohorrad_Whm2"].astype(int).sum() == epw["glohorrad_Whm2"].sum()
    assert reread.dataframe["drybulb_C"].iloc[100] == pytest.approx(epw["drybulb_C"].iloc[100])


def test_header_text_is_plain_ascii(tmp_path, built):
    _, epw, report = built
    location = dict(LOCATION, site="Z\u00fcrich, Fluntern")
    path = str(tmp_path / "ascii.epw")
    amy.write_amy_epw(path, epw, location, report, source_name="Z\u00fcrich station")
    text = open(path, "rb").read()
    text.decode("ascii")  # raises if any accent survived
    assert text.startswith(b"LOCATION,Zurich  Fluntern,")


def test_station_table_to_epw_one_call(tmp_path):
    path = str(tmp_path / "one.epw")
    report = amy.station_table_to_epw(_hourly_table(2025), LOCATION, 2025, path, source_name="synthetic")
    assert isinstance(report, amy.AmyReport)
    assert "AMY 2025" in report.to_text()
    assert len(Epw(path).dataframe) == 8760


def test_meteoswiss_adapter(tmp_path):
    csv = tmp_path / "ogd-smn_xxx_t_historical_2020-2029.csv"
    csv.write_text(
        "station_abbr;reference_timestamp;tre200s0;tde200s0;ure200s0;prestas0;fkl010z0;dkl010z0;gre000z0;ods000z0;sre000z0\n"
        "XXX;01.01.2025 00:00;1.5;0.5;93.0;950.5;2.0;180;0;;0\n"
        "XXX;01.01.2025 00:10;1.4;0.4;93.5;950.4;2.1;190;0;;0\n"
        "XXX;01.01.2025 00:20;1.3;0.3;94.0;950.3;1.9;200;1;;0\n",
        encoding="latin-1",
    )
    table = amy_meteoswiss.read_meteoswiss_ogd(str(csv))
    assert table.index[0] == pd.Timestamp("2025-01-01 00:00")
    assert table["pressure_Pa"].iloc[0] == pytest.approx(95050.0)
    assert table["ghi_Wm2"].tolist() == [0, 0, 1]
    assert {"temp_C", "dewpoint_C", "rh_pct", "wind_speed_ms", "wind_dir_deg", "sunshine_min"} <= set(table.columns)
    assert set(table.columns) <= set(amy.COLUMN_SPEC)

    stations = tmp_path / "stations.csv"
    stations.write_text(
        "station_abbr;station_name;station_canton;station_wigos_id;station_height_masl;"
        "station_coordinates_wgs84_lat;station_coordinates_wgs84_lon\n"
        "XXX;Zürich / Testberg;ZH;0-20000-0-06660;604.0;47.381003;8.567194\n",
        encoding="latin-1",
    )
    location = amy_meteoswiss.meteoswiss_location(str(stations), "XXX")
    assert location["elevation"] == 604.0 and location["utc_offset"] == 1.0
    assert location["usaf"] == "06660" and location["country_code"] == "CHE"
    assert location["site"] == "Zürich-Testberg"
    with pytest.raises(ValueError, match="not found"):
        amy_meteoswiss.meteoswiss_location(str(stations), "NOPE")


@pytest.mark.parametrize("module", [amy, amy_meteoswiss])
def test_import_warns_that_the_module_moved(module):
    with pytest.warns(DeprecationWarning, match="weather-file-builder"):
        importlib.reload(module)
