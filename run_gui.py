#!/usr/bin/env python3
# coding=utf-8
"""
Launcher script for PyEPWMorph GUI v2.0

This is the main entry point for the enhanced GUI with tabbed interface.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import main

if __name__ == "__main__":
    main()

