#!/usr/bin/env python3
"""
Main window for PyEPWMorph GUI with tabbed interface
"""

import os
import sys
import tkinter as tk
from tkinter import ttk

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.cache_tab import CacheTab
from gui.morph_tab import MorphTab


class PyEPWMorphGUI:
    """Main application window with tabbed interface"""

    def __init__(self, root):
        self.root = root
        self.root.title("PyEPWMorph - Development GUI v2.0")
        self.root.geometry("1100x950")

        # Create main notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Create tabs
        self.morph_tab = MorphTab(self.notebook)
        self.cache_tab = CacheTab(self.notebook)

        # Add tabs to notebook
        self.notebook.add(self.morph_tab.frame, text="  EPW Morphing  ")
        self.notebook.add(self.cache_tab.frame, text="  Cache Management  ")

        # Status bar at bottom
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def update_status(self, message):
        """Update status bar message"""
        self.status_bar.config(text=message)


def main():
    """Main entry point"""
    root = tk.Tk()
    _ = PyEPWMorphGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

