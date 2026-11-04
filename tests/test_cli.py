"""Tests for the command-line interface."""

import inspect
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from pyepwmorph import cli
from pyepwmorph.tools import configuration as morph_config
from pyepwmorph.tools import workflow
from pyepwmorph.tools.io import Epw

# Read before any test replaces the workflow with a recorder.
WORKFLOW_PARAMETERS = set(inspect.signature(workflow.morphing_workflow).parameters)

MINIMAL = [
    "in.epw",
    "--variables", "Temperature",
    "--pathways", "Middle of the Road",
    "--target-years", "2050",
    "--output-directory", "out",
]


@pytest.fixture
def workflow_calls(monkeypatch):
    """Replace the workflow with a recorder, so no weather file is read."""
    calls = []

    def fake_workflow(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(workflow, "morphing_workflow", fake_workflow)
    return calls


class TestArgumentMapping:

    def test_every_option_reaches_the_workflow(self, workflow_calls):
        status = cli.main([
            "in.epw",
            "--project-name", "plan",
            "--variables", "Temperature", "Humidity",
            "--pathways", "Middle of the Road", "Worst Case Scenario",
            "--percentiles", "10", "50", "90",
            "--target-years", "2050", "2080",
            "--output-directory", "out",
            "--model-sources", "ACCESS-CM2", "CanESM5",
            "--baseline-range", "1991", "2020",
            "--data-source", "cmip6",
            "--reference-scenario", "historical",
            "--time-slice", "historical", "1850", "2014",
            "--ch2025-full-coverage",
        ])
        assert status == 0
        assert workflow_calls == [{
            "project_name": "plan",
            "epw_file": "in.epw",
            "user_variables": ["Temperature", "Humidity"],
            "user_pathways": ["Middle of the Road", "Worst Case Scenario"],
            "percentiles": [10, 50, 90],
            "target_years": [2050, 2080],
            "output_directory": "out",
            "model_sources": ["ACCESS-CM2", "CanESM5"],
            "baseline_range": (1991, 2020),
            "write_file": True,
            "data_source": "cmip6",
            "reference_scenario": "historical",
            "time_slices": {"historical": ("1850", "2014")},
            "ch2025_full_coverage": True,
        }]

    def test_defaults_leave_the_choice_to_the_workflow(self, workflow_calls):
        cli.main(MINIMAL)
        call = workflow_calls[0]
        assert call["percentiles"] == [50]
        assert call["data_source"] == "cmip6"
        assert call["write_file"] is True
        assert call["ch2025_full_coverage"] is False
        for name in ("model_sources", "baseline_range", "reference_scenario", "time_slices"):
            assert call[name] is None

    def test_project_name_defaults_to_the_file_stem(self, workflow_calls):
        cli.main(["archive/zurich_tmy.epw"] + MINIMAL[1:])
        assert workflow_calls[0]["project_name"] == "zurich_tmy"

    def test_list_options_accept_repeated_flags(self, workflow_calls):
        cli.main([
            "in.epw",
            "--variables", "Temperature", "--variables", "Humidity",
            "--pathways", "Best Case Scenario", "--pathways", "Worst Case Scenario",
            "--target-years", "2050", "--target-years", "2080",
            "--percentiles", "10", "--percentiles", "90",
            "-o", "out",
        ])
        call = workflow_calls[0]
        assert call["user_variables"] == ["Temperature", "Humidity"]
        assert call["user_pathways"] == ["Best Case Scenario", "Worst Case Scenario"]
        assert call["target_years"] == [2050, 2080]
        assert call["percentiles"] == [10, 90]

    def test_time_slice_can_be_repeated(self, workflow_calls):
        cli.main(MINIMAL + [
            "--time-slice", "historical", "1850", "2014",
            "--time-slice", "ssp245", "2015", "2100",
        ])
        assert workflow_calls[0]["time_slices"] == {
            "historical": ("1850", "2014"),
            "ssp245": ("2015", "2100"),
        }

    def test_ch2025_needs_no_target_years(self, workflow_calls):
        cli.main([
            "in.epw",
            "--data-source", "ch2025",
            "--variables", "Temperature",
            "--pathways", "GWL 2.0",
            "-o", "out",
        ])
        assert workflow_calls[0]["data_source"] == "ch2025"
        assert workflow_calls[0]["target_years"] is None

    def test_no_write_needs_no_output_directory(self, workflow_calls):
        cli.main(["in.epw", "--variables", "Temperature", "--pathways", "GWL 2.0",
                  "--data-source", "ch2025", "--no-write"])
        assert workflow_calls[0]["write_file"] is False
        assert workflow_calls[0]["output_directory"] is None


class TestRejectedInput:

    @pytest.mark.parametrize("argv", [
        ["in.epw", "--pathways", "Middle of the Road", "--target-years", "2050", "-o", "out"],
        ["in.epw", "--variables", "Temperature", "--target-years", "2050", "-o", "out"],
        ["--variables", "Temperature", "--pathways", "Middle of the Road", "-o", "out"],
    ])
    def test_missing_required_options(self, workflow_calls, argv, capsys):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
        assert exit_info.value.code == 2
        assert workflow_calls == []

    def test_writing_needs_an_output_directory(self, workflow_calls, capsys):
        argv = [a for a in MINIMAL if a not in ("--output-directory", "out")]
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
        assert exit_info.value.code == 2
        assert "--output-directory" in capsys.readouterr().err
        assert workflow_calls == []

    def test_custom_data_is_not_a_cli_source(self, workflow_calls, capsys):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(MINIMAL + ["--data-source", "custom"])
        assert exit_info.value.code == 2
        assert "custom" in capsys.readouterr().err

    def test_workflow_errors_become_a_message_and_status_one(self, monkeypatch, capsys):
        def refuse(**kwargs):
            raise ValueError("Unknown CH2025 warming level 'GWL 9.9'.")

        monkeypatch.setattr(workflow, "morphing_workflow", refuse)
        assert cli.main(MINIMAL) == 1
        captured = capsys.readouterr()
        assert "GWL 9.9" in captured.err
        assert captured.out == ""

    def test_a_missing_weather_file_is_reported_not_raised(self, tmp_path, capsys):
        status = cli.main([
            str(tmp_path / "absent.epw"),
            "--data-source", "ch2025",
            "--variables", "Temperature",
            "--pathways", "GWL 2.0",
            "-o", str(tmp_path / "out"),
        ])
        assert status == 1
        assert "absent.epw" in capsys.readouterr().err


class TestPositionalPlacement:

    def test_epw_may_follow_a_double_dash(self, workflow_calls):
        cli.main(["--variables", "Temperature", "--pathways", "Middle of the Road",
                  "--target-years", "2050", "-o", "out", "--", "in.epw"])
        assert workflow_calls[0]["epw_file"] == "in.epw"

    def test_epw_after_a_multi_value_option_is_a_value_not_the_file(self, workflow_calls, capsys):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["--pathways", "Middle of the Road", "--target-years", "2050", "-o", "out",
                      "--variables", "Temperature", "in.epw"])
        assert exit_info.value.code == 2
        assert "EPW" in capsys.readouterr().err
        assert workflow_calls == []

    def test_help_tells_users_to_give_the_file_first(self, capsys):
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        assert "Give EPW first" in " ".join(capsys.readouterr().out.split())


class TestOutputListing:

    def test_cmip6_results_list_year_pathway_percentile_files(self, monkeypatch, capsys):
        monkeypatch.setattr(workflow, "morphing_workflow", lambda **kw: {
            "2050": {"ssp245": {"50": None}},
            "2080": {"ssp245": {"50": None, "90": None}},
        })
        assert cli.main(MINIMAL) == 0
        assert capsys.readouterr().out.splitlines() == [
            "out/2050_ssp245_50.epw",
            "out/2080_ssp245_50.epw",
            "out/2080_ssp245_90.epw",
        ]

    def test_ch2025_results_list_warming_level_files(self, monkeypatch, capsys):
        monkeypatch.setattr(workflow, "morphing_workflow", lambda **kw: {
            "gwl2.0": {"50": object()},
        })
        assert cli.main(MINIMAL + ["--data-source", "ch2025"]) == 0
        assert capsys.readouterr().out.splitlines() == ["out/gwl2.0_50.epw"]

    def test_no_write_lists_nothing(self, monkeypatch, capsys):
        monkeypatch.setattr(workflow, "morphing_workflow", lambda **kw: {
            "2050": {"ssp245": {"50": None}},
        })
        argv = [a for a in MINIMAL if a not in ("--output-directory", "out")]
        assert cli.main(argv + ["--no-write"]) == 0
        assert capsys.readouterr().out == ""


class TestSurface:

    def test_help_names_the_labels_the_library_accepts(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["--help"])
        assert exit_info.value.code == 0
        text = " ".join(capsys.readouterr().out.split())
        labels = (
            list(morph_config.CMIP6_PATHWAY_MAP)
            + list(morph_config.CH2025_PATHWAY_MAP)
            + list(morph_config.VARIABLE_MAPPING)
        )
        for label in labels:
            assert label in text

    def test_version(self, capsys):
        from pyepwmorph import __version__

        with pytest.raises(SystemExit) as exit_info:
            cli.main(["--version"])
        assert exit_info.value.code == 0
        assert __version__ in capsys.readouterr().out

    @pytest.mark.parametrize(("flags", "level"), [
        ([], logging.WARNING),
        (["-v"], logging.INFO),
        (["-vv"], logging.DEBUG),
    ])
    def test_verbosity_sets_the_log_level(self, workflow_calls, monkeypatch, flags, level):
        configured = {}
        monkeypatch.setattr(logging, "basicConfig", lambda **kw: configured.update(kw))
        cli.main(MINIMAL + flags)
        assert configured["level"] == level


class TestStaysInStepWithTheLibrary:
    """The CLI must not drift from ``MorphConfig`` and ``morphing_workflow``."""

    def test_every_parameter_has_a_flag_or_is_deliberately_left_out(self, workflow_calls):
        cli.main(MINIMAL)
        exposed = set(workflow_calls[0])
        assert exposed | cli.NOT_EXPOSED == WORKFLOW_PARAMETERS
        assert not exposed & cli.NOT_EXPOSED

    def test_every_morph_config_parameter_reaches_the_workflow(self, workflow_calls):
        cli.main(MINIMAL)
        config_parameters = set(inspect.signature(morph_config.MorphConfig.__init__).parameters)
        config_parameters -= {"self", "epw_fp"}
        assert config_parameters <= set(workflow_calls[0]) | cli.NOT_EXPOSED


def _swiss_epw(tmp_path):
    """The bundled EPW moved to Zurich, inside the CH2025 coverage."""
    lines = (Path(__file__).parent / "test.epw").read_text(encoding="utf-8").splitlines(keepends=True)
    fields = lines[0].rstrip("\n").split(",")
    fields[6], fields[7], fields[9] = "47.37800", "8.56600", "556.0"
    lines[0] = ",".join(fields) + "\n"
    path = tmp_path / "swiss.epw"
    path.write_text("".join(lines), encoding="utf-8")
    return path


class TestEndToEnd:
    """The real workflow, offline: CH2025 ships with the package."""

    ARGV = ["--data-source", "ch2025", "--variables", "Temperature", "Humidity",
            "--pathways", "GWL 2.0", "--percentiles", "50"]

    def test_writes_the_morphed_file_it_lists(self, tmp_path, capsys):
        source = _swiss_epw(tmp_path)
        out = tmp_path / "out"
        with pytest.warns(UserWarning):
            status = cli.main([str(source)] + self.ARGV + ["-o", str(out)])
        assert status == 0
        written = out / "gwl2.0_50.epw"
        assert capsys.readouterr().out.splitlines() == [str(written)]
        assert written.is_file()

        before = Epw(str(source)).dataframe["drybulb_C"].mean()
        after = Epw(str(written)).dataframe["drybulb_C"].mean()
        assert 0.5 < after - before < 4.0

    def test_no_write_leaves_the_disk_alone(self, tmp_path, capsys):
        source = _swiss_epw(tmp_path)
        before = sorted(tmp_path.iterdir())
        with pytest.warns(UserWarning):
            assert cli.main([str(source)] + self.ARGV + ["--no-write"]) == 0
        assert sorted(tmp_path.iterdir()) == before
        assert capsys.readouterr().out == ""

    def test_an_unknown_warming_level_is_reported(self, tmp_path, capsys):
        source = _swiss_epw(tmp_path)
        argv = ["--data-source", "ch2025", "--variables", "Temperature",
                "--pathways", "GWL 9.9", "--no-write"]
        with pytest.warns(UserWarning):
            assert cli.main([str(source)] + argv) == 1
        assert "GWL 9.9" in capsys.readouterr().err

    def test_runs_as_a_module(self, tmp_path):
        result = subprocess.run(
            [sys.executable, "-m", "pyepwmorph.cli", "--version"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0
        assert "pyepwmorph" in result.stdout
