"""Example: morph an EPW file for temperature using CMIP6 Middle of the Road (SSP2-4.5).

Run from the repo root:
    conda run -n pyepwmorph python examples/run_morph.py

Outputs are written to examples/example_result/ as:
    2050_ssp245_50.epw
"""

from pathlib import Path
from pyepwmorph.tools.workflow import morphing_workflow

HERE = Path(__file__).parent
EPW_FILE = HERE / "example.epw"
OUTPUT_DIR = HERE / "example_result"

result = morphing_workflow(
    project_name="example_temperature_morph",
    epw_file=str(EPW_FILE),
    user_variables=["Temperature"],
    user_pathways=["Middle of the Road"],   # SSP2-4.5
    percentiles=[50],                        # median ensemble member
    target_years=[2050],
    output_directory=str(OUTPUT_DIR),
    write_file=True,
)

morphed_epw = result["2050"]["ssp245"]["50"]
original_mean = morphed_epw.dataframe["drybulb_C"].mean()

print(f"Done. Output written to: {OUTPUT_DIR}")
print(f"Morphed EPW mean dry-bulb temperature: {original_mean:.2f} °C")
print(f"Morphed file: {OUTPUT_DIR / '2050_ssp245_50.epw'}")
