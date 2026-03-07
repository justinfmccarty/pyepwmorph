# coding=utf-8
"""
Cache Management tab for viewing and managing CMIP6 data cache
"""

from tkinter import ttk, messagebox
import threading

from pyepwmorph.models import access


class CacheTab:
    """Tab for cache management operations"""
    
    def __init__(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Main container
        main_container = ttk.Frame(self.frame)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Create widgets
        self.create_widgets(main_container)
        
        # Auto-load stats on init
        self.refresh_stats()
        
    def create_widgets(self, parent):
        """Create all widgets for cache tab"""
        
        # ===== HEADER =====
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 20))
        
        ttk.Label(header_frame, text="CMIP6 Cache Management", 
                 font=("Arial", 14, "bold")).pack(side="left")
        
        ttk.Button(header_frame, text="Refresh", 
                  command=self.refresh_stats).pack(side="right", padx=5)
        
        # ===== CACHE OVERVIEW =====
        overview_frame = ttk.LabelFrame(parent, text="Cache Overview", padding=15)
        overview_frame.pack(fill="x", pady=(0, 15))
        
        # Grid for stats
        stats_grid = ttk.Frame(overview_frame)
        stats_grid.pack(fill="x")
        
        # Cache directory
        ttk.Label(stats_grid, text="Cache Directory:", 
                 font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.cache_dir_label = ttk.Label(stats_grid, text="", foreground="blue")
        self.cache_dir_label.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        # Total files
        ttk.Label(stats_grid, text="Total Files:", 
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        self.total_files_label = ttk.Label(stats_grid, text="")
        self.total_files_label.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # Total size
        ttk.Label(stats_grid, text="Total Size:", 
                 font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=5)
        self.total_size_label = ttk.Label(stats_grid, text="")
        self.total_size_label.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        # Usage
        ttk.Label(stats_grid, text="Cache Usage:", 
                 font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", pady=5)
        usage_frame = ttk.Frame(stats_grid)
        usage_frame.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        self.usage_progress = ttk.Progressbar(usage_frame, length=300, mode='determinate')
        self.usage_progress.pack(side="left", padx=(0, 10))
        self.usage_label = ttk.Label(usage_frame, text="")
        self.usage_label.pack(side="left")
        
        # Max size info
        ttk.Label(stats_grid, text="Max Cache Size:", 
                 font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=5)
        self.max_size_label = ttk.Label(stats_grid, text="")
        self.max_size_label.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        
        # ===== CACHE ACTIONS =====
        actions_frame = ttk.LabelFrame(parent, text="Cache Actions", padding=15)
        actions_frame.pack(fill="x", pady=(0, 15))
        
        actions_grid = ttk.Frame(actions_frame)
        actions_grid.pack()
        
        ttk.Button(actions_grid, text="Clear Cache", 
                  command=self.clear_cache_confirm, 
                  width=20).grid(row=0, column=0, padx=10, pady=5)
        
        ttk.Label(actions_grid, text="Remove all cached climate model data", 
                 foreground="gray").grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Button(actions_grid, text="View Cache Location", 
                  command=self.open_cache_location, 
                  width=20).grid(row=1, column=0, padx=10, pady=5)
        
        ttk.Label(actions_grid, text="Open cache directory in file explorer", 
                 foreground="gray").grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # ===== CACHE DETAILS =====
        details_frame = ttk.LabelFrame(parent, text="Cached Files", padding=15)
        details_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Create treeview for file listing
        tree_scroll = ttk.Scrollbar(details_frame)
        tree_scroll.pack(side="right", fill="y")
        
        self.file_tree = ttk.Treeview(details_frame, 
                                      columns=("Size", "Modified", "Description"),
                                      show="tree headings",
                                      yscrollcommand=tree_scroll.set,
                                      height=15)
        tree_scroll.config(command=self.file_tree.yview)
        self.file_tree.pack(side="left", fill="both", expand=True)
        
        # Configure columns
        self.file_tree.heading("#0", text="Filename")
        self.file_tree.heading("Size", text="Size (MB)")
        self.file_tree.heading("Modified", text="Last Modified")
        self.file_tree.heading("Description", text="Description")
        
        self.file_tree.column("#0", width=400)
        self.file_tree.column("Size", width=100, anchor="e")
        self.file_tree.column("Modified", width=150)
        self.file_tree.column("Description", width=300)
        
        # ===== INFO SECTION =====
        info_frame = ttk.LabelFrame(parent, text="About Cache", padding=15)
        info_frame.pack(fill="x")
        
        info_text = (
            "The cache stores processed climate model data after spatial selection and coordinate transformation. "
            "This significantly speeds up repeated morphing operations for the same location. "
            "Cache files are automatically managed and old files are removed when the cache exceeds its size limit.\n\n"
            "Cache Structure:\n"
            "• Data is cached AFTER coordinate transformation (location-specific)\n"
            "• Each cache entry includes: latitude, longitude, pathway, variable, and model sources\n"
            "• Cache automatically cleans up oldest files when limit is exceeded"
        )
        
        ttk.Label(info_frame, text=info_text, 
                 wraplength=900, justify="left", 
                 foreground="gray").pack()
        
    def refresh_stats(self):
        """Refresh cache statistics"""
        try:
            stats = access.get_cmip6_cache_stats()
            
            # Update labels
            self.cache_dir_label.config(text=stats['cache_directory'])
            self.total_files_label.config(text=str(stats['total_files']))
            self.total_size_label.config(text=f"{stats['total_size_mb']} MB")
            self.max_size_label.config(text=f"{stats['max_size_mb']} MB")
            
            # Update progress bar
            usage_percent = stats.get('usage_percent', 0)
            self.usage_progress['value'] = usage_percent
            self.usage_label.config(text=f"{usage_percent}%")
            
            # Update file tree
            self.file_tree.delete(*self.file_tree.get_children())
            
            for file_info in stats['files']:
                filename = file_info['filename']
                size_mb = file_info['size_mb']
                modified = file_info['modified']
                
                # Parse filename to create description
                description = self.parse_cache_filename(filename)
                
                self.file_tree.insert("", "end", text=filename,
                                     values=(size_mb, modified, description))
                
        except (IOError, KeyError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to refresh cache stats: {str(e)}")
    
    def parse_cache_filename(self, filename):
        """Parse cache filename to extract readable description"""
        try:
            # Remove .pkl extension
            name = filename.replace('.pkl', '')
            parts = name.split('__')
            
            description_parts = []
            for part in parts:
                if part.startswith('lat_'):
                    lat = part.replace('lat_', '').replace('p', '.').replace('n', '-')
                    description_parts.append(f"Lat: {lat}")
                elif part.startswith('lon_'):
                    lon = part.replace('lon_', '').replace('p', '.').replace('n', '-')
                    description_parts.append(f"Lon: {lon}")
                elif part.startswith('pathway_'):
                    pathway = part.replace('pathway_', '')
                    description_parts.append(f"Path: {pathway}")
                elif part.startswith('variable_'):
                    var = part.replace('variable_', '')
                    description_parts.append(f"Var: {var}")
                elif part.startswith('sources_'):
                    # Don't show sources in description to save space
                    pass
                elif part == 'coordinate':
                    description_parts.append("Location data")
            
            return " | ".join(description_parts) if description_parts else "Climate model data"
            
        except (ValueError, KeyError):
            return "Climate model data"
    
    def clear_cache_confirm(self):
        """Confirm and clear cache"""
        stats = access.get_cmip6_cache_stats()
        
        result = messagebox.askyesno(
            "Clear Cache",
            f"This will delete all {stats['total_files']} cached files ({stats['total_size_mb']} MB).\n\n"
            "The cache will be rebuilt as needed when you run morphing operations.\n\n"
            "Are you sure you want to continue?"
        )
        
        if result:
            thread = threading.Thread(target=self.clear_cache)
            thread.daemon = True
            thread.start()
    
    def clear_cache(self):
        """Clear all cache files"""
        try:
            access.clear_cmip6_cache()
            self.frame.after(0, self.refresh_stats)
            self.frame.after(0, lambda: messagebox.showinfo(
                "Cache Cleared",
                "All cache files have been removed successfully."
            ))
        except (IOError, OSError) as e:
            self.frame.after(0, lambda: messagebox.showerror(
                "Error",
                f"Failed to clear cache: {str(e)}"
            ))
    
    def open_cache_location(self):
        """Open cache directory in file explorer"""
        import subprocess
        import platform
        
        stats = access.get_cmip6_cache_stats()
        cache_dir = stats['cache_directory']
        
        try:
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', cache_dir], check=False)
            elif platform.system() == 'Windows':
                subprocess.run(['explorer', cache_dir], check=False)
            else:  # Linux
                subprocess.run(['xdg-open', cache_dir], check=False)
        except (subprocess.SubprocessError, OSError, IOError) as e:
            messagebox.showerror("Error", f"Failed to open cache location: {str(e)}")

