# coding=utf-8
"""
EPW Morphing tab with enhanced configuration options
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import traceback

from pyepwmorph.tools import workflow as morph_work
from pyepwmorph.tools import io as morph_io


class MorphTab:
    """Tab for EPW file morphing operations"""
    
    def __init__(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Main container with scrollbar
        self.canvas = tk.Canvas(self.frame)
        self.scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Initialize variables
        self.init_variables()
        
        # Create widgets
        self.create_widgets()
        
    def init_variables(self):
        """Initialize all tkinter variables"""
        # Basic settings
        self.project_name = tk.StringVar()
        self.epw_file_path = tk.StringVar()
        self.epw_full_path = ""
        
        # Baseline period
        self.baseline_start = tk.IntVar(value=1965)
        self.baseline_end = tk.IntVar(value=1995)
        self.detect_baseline = tk.BooleanVar(value=False)
        
        # Future configuration
        self.future_years = tk.StringVar(value="2050,2070")
        
        # Climate pathways
        self.pathway_vars = {
            'Best Case Scenario': tk.BooleanVar(value=False),
            'Middle of the Road': tk.BooleanVar(value=False),
            'Upper Middle Scenario': tk.BooleanVar(value=False),
            'Worst Case Scenario': tk.BooleanVar(value=False)
        }
        
        # Percentiles
        self.percentile_vars = {
            '1st': tk.BooleanVar(value=False),
            '5th': tk.BooleanVar(value=False),
            '10th': tk.BooleanVar(value=False),
            '25th': tk.BooleanVar(value=False),
            '50th': tk.BooleanVar(value=False),
            '75th': tk.BooleanVar(value=False),
            '90th': tk.BooleanVar(value=False),
            '95th': tk.BooleanVar(value=False),
            '99th': tk.BooleanVar(value=False)
        }
        
        # Variables to morph
        self.variable_vars = {
            'Temperature': tk.BooleanVar(value=False),
            'Relative Humidity': tk.BooleanVar(value=False),
            'Wind Speed': tk.BooleanVar(value=False),
            'Clouds & Radiation': tk.BooleanVar(value=False),
            'Pressure': tk.BooleanVar(value=False),
            'Dew Point': tk.BooleanVar(value=False)
        }
        
        # Variable name mapping (GUI name -> internal name)
        self.variable_mapping = {
            'Temperature': 'Temperature',
            'Relative Humidity': 'Humidity',
            'Wind Speed': 'Wind',
            'Clouds & Radiation': 'Clouds and Radiation',
            'Pressure': 'Pressure',
            'Dew Point': 'Dew Point'
        }
        
        # Model sources
        self.model_source_vars = {
            'ACCESS-CM2': tk.BooleanVar(value=True),
            'CanESM5': tk.BooleanVar(value=True),
            'TaiESM1': tk.BooleanVar(value=True),
            'KACE-1-0-G': tk.BooleanVar(value=True),
            'MRI-ESM2-0': tk.BooleanVar(value=True),
            'GFDL-ESM4': tk.BooleanVar(value=True),
            'INM-CM4-8': tk.BooleanVar(value=True),
            'IPSL-CM6A-LR': tk.BooleanVar(value=True),
            'INM-CM5-0': tk.BooleanVar(value=True),
            'MIROC6': tk.BooleanVar(value=True),
            'EC-Earth3-Veg-LR': tk.BooleanVar(value=True),
            'BCC-CSM2-MR': tk.BooleanVar(value=True),
        }
        
        # Output settings
        self.output_dir = tk.StringVar(value=os.path.join(os.getcwd(), "morphing_output"))
        
    def create_widgets(self):
        """Create all GUI widgets"""
        row = 0
        
        # ===== PROJECT CONFIGURATION =====
        self.create_section(self.scrollable_frame, "PROJECT CONFIGURATION", row, is_main=True)
        row += 1
        
        # Project Name
        self.create_label(self.scrollable_frame, "Project Name:", row)
        row += 1
        name_entry = ttk.Entry(self.scrollable_frame, textvariable=self.project_name, width=70)
        name_entry.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 10), sticky="w")
        row += 1
        
        # EPW File
        self.create_label(self.scrollable_frame, "Baseline EPW File:", row)
        row += 1
        file_frame = ttk.Frame(self.scrollable_frame)
        file_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 10), sticky="w")
        ttk.Button(file_frame, text="Choose File", command=self.browse_file).pack(side="left")
        ttk.Label(file_frame, textvariable=self.epw_file_path, foreground="gray").pack(side="left", padx=10)
        row += 1
        
        # Output Directory
        self.create_label(self.scrollable_frame, "Output Directory:", row)
        row += 1
        output_frame = ttk.Frame(self.scrollable_frame)
        output_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="w")
        ttk.Button(output_frame, text="Choose Directory", command=self.browse_output_dir).pack(side="left")
        ttk.Label(output_frame, textvariable=self.output_dir, foreground="gray", wraplength=600).pack(side="left", padx=10)
        row += 1
        
        # ===== BASELINE PERIOD =====
        self.create_section(self.scrollable_frame, "BASELINE PERIOD", row, is_main=True)
        row += 1
        
        baseline_frame = ttk.Frame(self.scrollable_frame)
        baseline_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 10), sticky="w")
        
        # Start year
        ttk.Label(baseline_frame, text="Start Year:").grid(row=0, column=0, sticky="w")
        start_slider = tk.Scale(baseline_frame, from_=1950, to=2000, orient="horizontal",
                               variable=self.baseline_start, length=250)
        start_slider.grid(row=0, column=1, padx=10)
        ttk.Label(baseline_frame, textvariable=self.baseline_start, width=6).grid(row=0, column=2)
        
        # End year
        ttk.Label(baseline_frame, text="End Year:").grid(row=1, column=0, sticky="w", pady=5)
        end_slider = tk.Scale(baseline_frame, from_=1950, to=2020, orient="horizontal",
                             variable=self.baseline_end, length=250)
        end_slider.grid(row=1, column=1, padx=10, pady=5)
        ttk.Label(baseline_frame, textvariable=self.baseline_end, width=6).grid(row=1, column=2, pady=5)
        
        # Detect checkbox
        detect_cb = ttk.Checkbutton(baseline_frame, text="Auto-detect from EPW file",
                                    variable=self.detect_baseline,
                                    command=self.toggle_baseline_detection)
        detect_cb.grid(row=2, column=0, columnspan=3, sticky="w", pady=5)
        row += 1
        
        # ===== CLIMATE MODEL CONFIGURATION =====
        self.create_section(self.scrollable_frame, "CLIMATE MODEL CONFIGURATION", row, is_main=True)
        row += 1
        
        # Model sources
        self.create_label(self.scrollable_frame, "Climate Model Sources (select at least one):", row)
        row += 1
        model_frame = ttk.Frame(self.scrollable_frame)
        model_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 10), sticky="w")
        
        for i, (name, var) in enumerate(self.model_source_vars.items()):
            ttk.Checkbutton(model_frame, text=name, variable=var).grid(row=0, column=i, padx=10, sticky="w")
        row += 1
        
        # Climate Pathways
        self.create_label(self.scrollable_frame, "Climate Pathways (SSP Scenarios):", row)
        row += 1
        pathway_frame = ttk.Frame(self.scrollable_frame)
        pathway_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 10), sticky="w")
        
        pathway_info = [
            ('Best Case Scenario', 'SSP1-2.6: Sustainability path with strong mitigation'),
            ('Middle of the Road', 'SSP2-4.5: Middle-of-the-road development'),
            ('Upper Middle Scenario', 'SSP3-7.0: Regional rivalry with high emissions'),
            ('Worst Case Scenario', 'SSP5-8.5: Fossil-fueled development')
        ]
        
        for i, (name, tooltip) in enumerate(pathway_info):
            cb = ttk.Checkbutton(pathway_frame, text=name, variable=self.pathway_vars[name])
            cb.grid(row=i//2, column=i%2, padx=15, pady=2, sticky="w")
            # Add tooltip label
            ttk.Label(pathway_frame, text=f"  ({tooltip.split(':')[1].strip()})", 
                     foreground="gray", font=("Arial", 8)).grid(row=i//2, column=i%2+2, sticky="w")
        row += 1
        
        # ===== FUTURE PROJECTIONS =====
        self.create_section(self.scrollable_frame, "FUTURE PROJECTIONS", row, is_main=True)
        row += 1
        
        self.create_label(self.scrollable_frame, "Future Years (comma-separated, e.g., 2030,2050,2070):", row)
        row += 1
        years_entry = ttk.Entry(self.scrollable_frame, textvariable=self.future_years, width=70)
        years_entry.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 10), sticky="w")
        row += 1
        
        # Percentiles
        self.create_label(self.scrollable_frame, "Percentiles of Climate Model Ensemble:", row)
        row += 1
        percentile_frame = ttk.Frame(self.scrollable_frame)
        percentile_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="w")
        
        for i, (name, var) in enumerate(self.percentile_vars.items()):
            ttk.Checkbutton(percentile_frame, text=name, variable=var).grid(row=0, column=i, padx=5, sticky="w")
        row += 1
        
        # ===== VARIABLES TO MORPH =====
        self.create_section(self.scrollable_frame, "VARIABLES TO MORPH", row, is_main=True)
        row += 1
        
        self.create_label(self.scrollable_frame, "Select climate variables to modify:", row)
        row += 1
        
        variable_frame = ttk.Frame(self.scrollable_frame)
        variable_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="w")
        
        var_descriptions = {
            'Temperature': 'Dry bulb temperature (requires: tas, tasmax, tasmin)',
            'Relative Humidity': 'Humidity levels (requires: huss, plus Temperature & Pressure)',
            'Wind Speed': 'Wind velocity (requires: uas, vas)',
            'Clouds & Radiation': 'Cloud cover & solar radiation (requires: clt, rsds)',
            'Pressure': 'Atmospheric pressure (requires: psl)',
            'Dew Point': 'Dew point temperature (requires: Temperature & Humidity)'
        }
        
        r, c = 0, 0
        for name, var in self.variable_vars.items():
            cb = ttk.Checkbutton(variable_frame, text=name, variable=var)
            cb.grid(row=r, column=c*2, padx=10, pady=2, sticky="w")
            ttk.Label(variable_frame, text=var_descriptions[name], 
                     foreground="gray", font=("Arial", 8)).grid(row=r, column=c*2+1, sticky="w", padx=5)
            r += 1
            if r >= 3:
                r = 0
                c += 1
        row += 1
        
        # ===== ACTIONS =====
        button_frame = ttk.Frame(self.scrollable_frame)
        button_frame.grid(row=row, column=0, columnspan=3, padx=20, pady=15, sticky="w")
        
        submit_btn = ttk.Button(button_frame, text="  RUN MORPHING  ", command=self.submit)
        submit_btn.grid(row=0, column=0, padx=10)
        
        reset_btn = ttk.Button(button_frame, text="  RESET ALL  ", command=self.reset)
        reset_btn.grid(row=0, column=1, padx=10)
        
        # Quick preset buttons
        ttk.Label(button_frame, text="  |  Quick Presets:", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=10)
        ttk.Button(button_frame, text="Conservative", command=self.preset_conservative).grid(row=0, column=3, padx=5)
        ttk.Button(button_frame, text="Comprehensive", command=self.preset_comprehensive).grid(row=0, column=4, padx=5)
        row += 1
        
        # ===== PROCESSING LOG =====
        self.create_section(self.scrollable_frame, "PROCESSING LOG", row, is_main=True)
        row += 1
        
        self.log_text = scrolledtext.ScrolledText(self.scrollable_frame, height=15, width=120, state='disabled')
        self.log_text.grid(row=row, column=0, columnspan=3, padx=20, pady=(0, 20), sticky="ew")
        
    def create_section(self, parent, title, row, is_main=False):
        """Create a section header"""
        font_style = ("Arial", 12, "bold") if is_main else ("Arial", 10, "bold")
        bg_color = "#e0e0e0" if is_main else None
        
        label = ttk.Label(parent, text=title, font=font_style)
        if bg_color:
            label.configure(background=bg_color)
        label.grid(row=row, column=0, columnspan=3, padx=20, pady=(15, 8), sticky="ew")
        
    def create_label(self, parent, text, row):
        """Create a standard label"""
        label = ttk.Label(parent, text=text, font=("Arial", 10))
        label.grid(row=row, column=0, columnspan=3, padx=20, pady=(5, 2), sticky="w")
        
    def browse_file(self):
        """Open file browser for EPW file"""
        filename = filedialog.askopenfilename(
            title="Select EPW file",
            filetypes=(("EPW files", "*.epw"), ("All files", "*.*"))
        )
        if filename:
            self.epw_file_path.set(os.path.basename(filename))
            self.epw_full_path = filename
            
            if self.detect_baseline.get():
                self.detect_baseline_from_epw()
    
    def browse_output_dir(self):
        """Open directory browser for output directory"""
        dirname = filedialog.askdirectory(title="Select output directory")
        if dirname:
            self.output_dir.set(dirname)
    
    def toggle_baseline_detection(self):
        """Toggle baseline period detection from EPW"""
        if self.detect_baseline.get() and self.epw_full_path:
            self.detect_baseline_from_epw()
    
    def detect_baseline_from_epw(self):
        """Detect baseline period from EPW file"""
        try:
            if self.epw_full_path:
                epw_obj = morph_io.Epw(self.epw_full_path)
                baseline = epw_obj.detect_baseline_range()
                self.baseline_start.set(baseline[0])
                self.baseline_end.set(baseline[1])
                self.log_message(f"✓ Detected baseline period: {baseline[0]} - {baseline[1]}")
        except (IOError, ValueError, KeyError) as e:
            self.log_message(f"✗ Error detecting baseline: {str(e)}")
    
    def preset_conservative(self):
        """Apply conservative preset: middle pathway, 50th percentile, temperature only"""
        # Reset pathways
        for var in self.pathway_vars.values():
            var.set(False)
        self.pathway_vars['Middle of the Road'].set(True)
        
        # Reset percentiles
        for var in self.percentile_vars.values():
            var.set(False)
        self.percentile_vars['50th'].set(True)
        
        # Reset variables
        for var in self.variable_vars.values():
            var.set(False)
        self.variable_vars['Temperature'].set(True)
        
        self.future_years.set("2050")
        self.log_message("Applied Conservative preset: Middle pathway, 50th percentile, Temperature only, Year 2050")
    
    def preset_comprehensive(self):
        """Apply comprehensive preset: all pathways, key percentiles, all variables"""
        # All pathways
        for var in self.pathway_vars.values():
            var.set(True)
        
        # Key percentiles
        for name, var in self.percentile_vars.items():
            if name in ['1st', '50th', '99th']:
                var.set(True)
            else:
                var.set(False)
        
        # All variables
        for var in self.variable_vars.values():
            var.set(True)
        
        self.future_years.set("2050,2070,2090")
        self.log_message("Applied Comprehensive preset: All pathways, 1st/50th/99th percentiles, All variables, Years 2050/2070/2090")
    
    def log_message(self, message):
        """Add message to log output"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.scrollable_frame.update()
    
    def validate_inputs(self):
        """Validate all inputs before processing"""
        errors = []
        
        if not self.project_name.get():
            errors.append("Project name is required")
        
        if not self.epw_full_path:
            errors.append("Please select an EPW file")
        
        if not any(var.get() for var in self.model_source_vars.values()):
            errors.append("Please select at least one climate model source")
        
        if not any(var.get() for var in self.pathway_vars.values()):
            errors.append("Please select at least one climate pathway")
        
        if not self.future_years.get():
            errors.append("Please specify future years")
        
        if not any(var.get() for var in self.percentile_vars.values()):
            errors.append("Please select at least one percentile")
        
        if not any(var.get() for var in self.variable_vars.values()):
            errors.append("Please select at least one variable to morph")
        
        return errors
    
    def submit(self):
        """Process the morphing workflow"""
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return
        
        # Run in separate thread
        thread = threading.Thread(target=self.run_morphing)
        thread.daemon = True
        thread.start()
    
    def run_morphing(self):
        """Execute the morphing workflow"""
        try:
            self.log_message("="*100)
            self.log_message("STARTING MORPHING WORKFLOW")
            self.log_message("="*100)
            
            # Gather inputs
            project_name = self.project_name.get()
            epw_file = self.epw_full_path
            
            # Model sources
            model_sources = [name for name, var in self.model_source_vars.items() if var.get()]
            self.log_message(f"Model sources: {', '.join(model_sources)}")
            
            # Pathways
            user_pathways = [name for name, var in self.pathway_vars.items() if var.get()]
            self.log_message(f"Pathways: {', '.join(user_pathways)}")
            
            # Percentiles
            percentile_map = {
                '1st': 1, '5th': 5, '10th': 10, '25th': 25, '50th': 50,
                '75th': 75, '90th': 90, '95th': 95, '99th': 99
            }
            percentiles = [percentile_map[name] for name, var in self.percentile_vars.items() if var.get()]
            percentiles.sort()
            self.log_message(f"Percentiles: {percentiles}")
            
            # Variables
            user_variables = [self.variable_mapping[name] for name, var in self.variable_vars.items() if var.get()]
            self.log_message(f"Variables: {', '.join(user_variables)}")
            
            # Future years
            future_years = [int(year.strip()) for year in self.future_years.get().split(',')]
            self.log_message(f"Future years: {future_years}")
            
            # Baseline range
            if self.detect_baseline.get():
                epw_obj = morph_io.Epw(epw_file)
                baseline_range = epw_obj.detect_baseline_range()
            else:
                baseline_range = (self.baseline_start.get(), self.baseline_end.get())
            self.log_message(f"Baseline period: {baseline_range[0]}-{baseline_range[1]}")
            
            # Output directory
            output_directory = self.output_dir.get()
            if not os.path.exists(output_directory):
                os.makedirs(output_directory)
                self.log_message(f"Created output directory: {output_directory}")
            
            self.log_message("\n" + "-"*100)
            self.log_message("Downloading and processing climate model data...")
            self.log_message("This may take several minutes depending on your selections and network speed...")
            self.log_message("-"*100 + "\n")
            
            # Run the workflow
            _ = morph_work.morphing_workflow(
                project_name=project_name,
                epw_file=epw_file,
                user_variables=user_variables,
                user_pathways=user_pathways,
                percentiles=percentiles,
                future_years=future_years,
                output_directory=output_directory,
                model_sources=model_sources,
                baseline_range=baseline_range,
                write_file=True
            )
            
            self.log_message("\n" + "="*100)
            self.log_message("✓ MORPHING WORKFLOW COMPLETED SUCCESSFULLY!")
            self.log_message(f"✓ Output files saved to: {output_directory}")
            self.log_message("="*100)
            
            # Count output files
            epw_files = [f for f in os.listdir(output_directory) if f.endswith('.epw')]
            self.log_message(f"✓ Generated {len(epw_files)} morphed EPW files")
            
            # Show completion message
            self.scrollable_frame.after(0, lambda: messagebox.showinfo(
                "Success",
                f"Morphing completed successfully!\n\n"
                f"Generated {len(epw_files)} EPW files\n\n"
                f"Output directory:\n{output_directory}"
            ))
            
        except Exception as e:
            error_msg = f"Error during morphing: {str(e)}"
            tb = traceback.format_exc()
            self.log_message("\n" + "="*100)
            self.log_message(f"✗ {error_msg}")
            self.log_message("-"*100)
            self.log_message(tb)
            self.log_message("="*100)
            self.scrollable_frame.after(0, lambda: messagebox.showerror("Error", error_msg))
    
    def reset(self):
        """Reset all fields to default values"""
        self.project_name.set("")
        self.epw_file_path.set("")
        self.epw_full_path = ""
        self.baseline_start.set(1965)
        self.baseline_end.set(1995)
        self.detect_baseline.set(False)
        self.future_years.set("2050,2070")
        
        for var in self.pathway_vars.values():
            var.set(False)
        for var in self.percentile_vars.values():
            var.set(False)
        for var in self.variable_vars.values():
            var.set(False)
        
        # Reset model sources to defaults
        self.model_source_vars['ACCESS-CM2'].set(True)
        self.model_source_vars['CanESM5'].set(True)
        self.model_source_vars['TaiESM1'].set(True)
        
        self.output_dir.set(os.path.join(os.getcwd(), "morphing_output"))
        
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        self.log_message("All fields have been reset to defaults.")

