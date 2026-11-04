"""Command-line interface: a thin wrapper around ``morphing_workflow``.

Every option maps onto a ``MorphConfig`` / ``morphing_workflow`` parameter of
the same name, so the CLI adds no behaviour of its own. Validation is left to
the library; its errors are reported as a message and exit status 1.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from pyepwmorph import __version__
from pyepwmorph.tools import configuration as morph_config

#: ``morphing_workflow`` parameters with no flag: ``custom_data`` is a nested
#: mapping of scenario to CSV paths that does not fit on a command line, and
#: ``future_years`` is a deprecated alias of ``target_years``. A test keeps this
#: set, the flags and the workflow signature in step.
NOT_EXPOSED = frozenset({"custom_data", "future_years"})

DATA_SOURCES = ("cmip6", "ch2025")

_EPILOG = """\
labels (quote them in the shell):
  variables  {variables}
  CMIP6      {cmip6}
  CH2025     {ch2025}
"""


def _labels(mapping) -> str:
    return ", ".join(f"'{label}'" for label in mapping)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyepwmorph",
        description="Morph an EnergyPlus weather file with climate model data.",
        epilog=_EPILOG.format(
            variables=_labels(morph_config.VARIABLE_MAPPING),
            cmip6=_labels(morph_config.CMIP6_PATHWAY_MAP),
            ch2025=_labels(morph_config.CH2025_PATHWAY_MAP),
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("epw_file", metavar="EPW", help="weather file to morph")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="log progress (-v) or detail (-vv)")

    parser.add_argument("--variables", nargs="+", action="extend", required=True, metavar="NAME",
                        help="variables to morph; dependencies are added")
    parser.add_argument("--pathways", nargs="+", action="extend", required=True, metavar="NAME",
                        help="scenario pathways, or CH2025 warming levels")
    parser.add_argument("--percentiles", nargs="+", action="extend", type=int, metavar="P",
                        help="ensemble percentiles (default: 50)")
    parser.add_argument("--target-years", nargs="+", action="extend", type=int, metavar="YEAR",
                        help="target years (not used by CH2025)")

    parser.add_argument("-o", "--output-directory", metavar="DIR",
                        help="where to write the morphed files")
    parser.add_argument("--no-write", action="store_true",
                        help="morph without writing files")
    parser.add_argument("--project-name", metavar="NAME",
                        help="project label (default: the weather file's name)")

    parser.add_argument("--data-source", choices=DATA_SOURCES, default="cmip6",
                        help="climate data source (default: cmip6)")
    parser.add_argument("--model-sources", nargs="+", action="extend", metavar="MODEL",
                        help="CMIP6 models (default: ACCESS-CM2 CanESM5 TaiESM1)")
    parser.add_argument("--baseline-range", nargs=2, type=int, metavar=("START", "END"),
                        help="baseline years (default: read from the weather file)")
    parser.add_argument("--reference-scenario", metavar="NAME",
                        help="scenario to treat as the baseline climate")
    parser.add_argument("--time-slice", nargs=3, action="append", metavar=("PATHWAY", "START", "END"),
                        help="CMIP6 years to read for a pathway; repeatable")
    parser.add_argument("--ch2025-full-coverage", action="store_true",
                        help="CH2025: match only stations that carry every variable")
    return parser


def _workflow_arguments(args: argparse.Namespace) -> dict:
    time_slices = None
    if args.time_slice:
        time_slices = {name: (start, end) for name, start, end in args.time_slice}
    return {
        "project_name": args.project_name or Path(args.epw_file).stem,
        "epw_file": args.epw_file,
        "user_variables": args.variables,
        "user_pathways": args.pathways,
        "percentiles": args.percentiles or [50],
        "target_years": args.target_years,
        "output_directory": args.output_directory,
        "model_sources": args.model_sources,
        "baseline_range": tuple(args.baseline_range) if args.baseline_range else None,
        "write_file": not args.no_write,
        "data_source": args.data_source,
        "reference_scenario": args.reference_scenario,
        "time_slices": time_slices,
        "ch2025_full_coverage": args.ch2025_full_coverage,
    }


def _written_files(results: dict, output_directory: str, data_source: str) -> List[str]:
    """Paths of the files ``morphing_workflow`` wrote, in result order."""
    paths = []
    for first, inner in results.items():
        if data_source == "ch2025":
            paths += [f"{first}_{percentile}.epw" for percentile in inner]
        else:
            for pathway, percentiles in inner.items():
                paths += [f"{first}_{pathway}_{percentile}.epw" for percentile in percentiles]
    return [os.path.join(output_directory, name) for name in paths]


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.no_write and not args.output_directory:
        parser.error("--output-directory is required unless --no-write is given")

    logging.basicConfig(
        level=(logging.WARNING, logging.INFO, logging.DEBUG)[min(args.verbose, 2)],
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Imported here so --help and --version do not load the CMIP6 stack.
    from pyepwmorph.tools import workflow

    arguments = _workflow_arguments(args)
    try:
        results = workflow.morphing_workflow(**arguments)
    except (ValueError, OSError) as error:
        print(f"pyepwmorph: error: {error}", file=sys.stderr)
        return 1

    if arguments["write_file"]:
        for path in _written_files(results, args.output_directory, args.data_source):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
