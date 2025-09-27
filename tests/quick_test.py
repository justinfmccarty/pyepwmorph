#!/usr/bin/env python3
"""
Quick test runner for pyepwmorph package

This is a simplified test script to validate core functionality of the 
pyepwmorph package without complex test frameworks.

Author: Test Script for pyepwmorph
Date: September 2025
"""

import os
import sys
import tempfile
import shutil
import warnings
from pathlib import Path

# Add the package to path if running locally
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

def find_sample_epw():
    """Find a sample EPW file for testing"""
    test_dir = Path(__file__).parent
    
    # Check examples directory
    examples_dir = test_dir / "examples"
    if examples_dir.exists():
        for epw_file in examples_dir.glob("*.epw"):
            return str(epw_file)
    
    # Check notebooks directory
    notebooks_dir = test_dir / "notebooks"
    if notebooks_dir.exists():
        for epw_file in notebooks_dir.glob("*.epw"):
            return str(epw_file)
    
    return None

def test_basic_imports():
    """Test that all required modules can be imported"""
    print("Testing basic imports...")
    
    try:
        from pyepwmorph.tools import io as morph_io
        from pyepwmorph.tools import utilities as morph_utils
        from pyepwmorph.tools import configuration as morph_config
        from pyepwmorph.models import access, coordinate, assemble
        from pyepwmorph.morph import procedures as morph_proc
        print("✓ All core modules imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_epw_reading():
    """Test EPW file reading"""
    print("\nTesting EPW file reading...")
    
    epw_file = find_sample_epw()
    if not epw_file:
        print("✗ No EPW file found for testing")
        return False
    
    try:
        from pyepwmorph.tools import io as morph_io
        
        epw_obj = morph_io.Epw(epw_file)
        
        # Check basic properties
        if epw_obj.dataframe is None:
            print("✗ EPW dataframe is None")
            return False
            
        if len(epw_obj.dataframe) != 8760:
            print(f"✗ EPW dataframe has {len(epw_obj.dataframe)} rows, expected 8760")
            return False
            
        if epw_obj.location is None:
            print("✗ EPW location data is None")
            return False
            
        if 'latitude' not in epw_obj.location or 'longitude' not in epw_obj.location:
            print("✗ EPW location missing lat/lon")
            return False
            
        print(f"✓ EPW file loaded successfully: {os.path.basename(epw_file)}")
        print(f"  Location: {epw_obj.location['latitude']:.2f}, {epw_obj.location['longitude']:.2f}")
        print(f"  Data rows: {len(epw_obj.dataframe)}")
        return True
        
    except Exception as e:
        print(f"✗ EPW reading error: {e}")
        return False

def test_configuration():
    """Test configuration object"""
    print("\nTesting configuration object...")
    
    epw_file = find_sample_epw()
    if not epw_file:
        print("✗ No EPW file found for testing")
        return False
    
    try:
        from pyepwmorph.tools import configuration as morph_config
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="pyepwmorph_test_")
        
        try:
            config = morph_config.MorphConfig(
                project_name='test_project',
                epw_fp=epw_file,
                user_variables=['Temperature'],
                user_pathways=['Best Case Scenario'],
                percentiles=[50],
                future_years=[2050],
                output_directory=temp_dir
            )
            
            # Check configuration properties
            if config.project_name != 'test_project':
                print("✗ Project name not set correctly")
                return False
                
            if config.epw is None:
                print("✗ EPW object not created")
                return False
                
            if not config.model_sources:
                print("✗ Model sources not set")
                return False
                
            if not config.baseline_range:
                print("✗ Baseline range not set")
                return False
                
            print("✓ Configuration object created successfully")
            print(f"  Project: {config.project_name}")
            print(f"  Model sources: {len(config.model_sources)} models")
            print(f"  Baseline range: {config.baseline_range}")
            return True
            
        finally:
            # Clean up
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False

def test_morphing_procedures():
    """Test basic morphing procedures"""
    print("\nTesting morphing procedures...")
    
    try:
        from pyepwmorph.morph import procedures as morph_proc
        import numpy as np
        
        # Create test data
        test_data = np.array([20.0, 25.0, 30.0, 15.0, 10.0])
        
        # Test shift operation
        shifted = morph_proc.shift(test_data, 2.0)
        expected_shift = test_data + 2.0
        if not np.allclose(shifted, expected_shift):
            print("✗ Shift operation failed")
            return False
            
        # Test stretch operation
        stretched = morph_proc.stretch(test_data, 1.1)
        expected_stretch = test_data * 1.1
        if not np.allclose(stretched, expected_stretch):
            print("✗ Stretch operation failed")
            return False
            
        print("✓ Basic morphing procedures work correctly")
        print(f"  Shift test: {test_data[0]} + 2.0 = {shifted[0]}")
        print(f"  Stretch test: {test_data[0]} * 1.1 = {stretched[0]:.1f}")
        return True
        
    except Exception as e:
        print(f"✗ Morphing procedures error: {e}")
        return False

def test_utilities():
    """Test utility functions"""
    print("\nTesting utility functions...")
    
    try:
        from pyepwmorph.tools import utilities as morph_utils
        
        # Test timestamp generation
        ts_8760 = morph_utils.ts_8760()
        if len(ts_8760) != 8760:
            print(f"✗ Timestamp length is {len(ts_8760)}, expected 8760")
            return False
            
        # Test period calculation
        future_range = morph_utils.calc_period(2050, (1990, 2020))
        if not isinstance(future_range, tuple) or len(future_range) != 2:
            print("✗ Period calculation failed")
            return False
            
        print("✓ Utility functions work correctly")
        print(f"  Timestamp length: {len(ts_8760)}")
        print(f"  Future period for 2050: {future_range}")
        return True
        
    except Exception as e:
        print(f"✗ Utilities error: {e}")
        return False

def test_file_operations():
    """Test file reading and writing operations"""
    print("\nTesting file operations...")
    
    epw_file = find_sample_epw()
    if not epw_file:
        print("✗ No EPW file found for testing")
        return False
    
    try:
        from pyepwmorph.tools import io as morph_io
        
        # Read EPW file
        epw_obj = morph_io.Epw(epw_file)
        original_temp = epw_obj.dataframe['drybulb_C'].copy()
        
        # Modify data
        epw_obj.dataframe['drybulb_C'] = original_temp + 2.0
        
        # Write to temporary file
        temp_dir = tempfile.mkdtemp(prefix="pyepwmorph_filetest_")
        output_file = os.path.join(temp_dir, "test_output.epw")
        
        try:
            epw_obj.write_to_file(output_file)
            
            if not os.path.exists(output_file):
                print("✗ Output file was not created")
                return False
                
            # Read the output file back
            output_epw = morph_io.Epw(output_file)
            modified_temp = output_epw.dataframe['drybulb_C']
            
            # Check if modification was preserved
            original_epw = morph_io.Epw(epw_file)
            temp_diff = modified_temp - original_epw.dataframe['drybulb_C']
            
            if not abs(temp_diff.mean() - 2.0) < 0.01:
                print("✗ Temperature modification not preserved")
                return False
                
            file_size = os.path.getsize(output_file)
            
            print("✓ File operations work correctly")
            print(f"  Output file size: {file_size / 1024:.1f} KB")
            print(f"  Temperature increase: +{temp_diff.mean():.1f}°C")
            return True
            
        finally:
            # Clean up
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                
    except Exception as e:
        print(f"✗ File operations error: {e}")
        return False

def main():
    """Main test runner"""
    print("=" * 50)
    print("PYEPWMORPH QUICK TEST SUITE")
    print("=" * 50)
    print("Testing core functionality of climate projection downscaling package")
    print()
    
    # Check if we're in the right directory
    current_dir = Path(__file__).parent
    if not (current_dir / "pyepwmorph").exists():
        print("ERROR: pyepwmorph package directory not found!")
        print(f"Current directory: {current_dir}")
        print("Please run this script from the package root directory")
        return 1
    
    # Run tests
    tests = [
        ("Basic Imports", test_basic_imports),
        ("EPW Reading", test_epw_reading),
        ("Configuration", test_configuration),
        ("Morphing Procedures", test_morphing_procedures),
        ("Utilities", test_utilities),
        ("File Operations", test_file_operations),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n[{passed + 1}/{total}] {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                passed += 1
            else:
                print(f"FAILED: {test_name}")
        except Exception as e:
            print(f"ERROR in {test_name}: {e}")
    
    # Print summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests passed! The package is working correctly.")
        print("\nKey functionality validated:")
        print("✓ Package imports and module structure")
        print("✓ EPW file reading and data validation")
        print("✓ Configuration object management")
        print("✓ Basic morphing procedures")
        print("✓ Utility functions")
        print("✓ File input/output operations")
        print("\nThe package is ready for climate projection downscaling!")
        return 0
    else:
        print(f"\n❌ {total - passed} tests failed. Please review the output above.")
        print("\nTroubleshooting tips:")
        print("- Ensure all dependencies are installed (see requirements.txt)")
        print("- Check that EPW files exist in examples/ or notebooks/ directories")
        print("- Verify package structure is intact")
        return 1

if __name__ == "__main__":
    sys.exit(main())