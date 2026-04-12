#!/usr/bin/env python3
"""
Docker entrypoint script for POAFF SIA processing.
Handles input file preparation, encoding conversion, and dynamic configuration.
"""

import os
import sys
import shutil
import zipfile
import re
import tempfile
from pathlib import Path

def main():
    # Define paths
    temp_input = Path(os.environ.get("POAFF_INPUT_DIR", "/tmp/input"))
    sia_input = Path("/app/poaff_bpa/input/SIA")
    sia_src = sia_input / "src"
    poaff_py = Path("/app/poaff_bpa/src/poaff.py")

    # Validate input
    if not temp_input.exists():
        print("ERROR: /tmp/input directory not found. Mount input volume to /tmp/input")
        sys.exit(1)

    zip_files = list(temp_input.glob("*.zip"))
    if not zip_files:
        print("ERROR: No zip file found in /tmp/input")
        sys.exit(1)

    if len(zip_files) > 1:
        print("ERROR: Multiple zip files found. Only one zip file allowed.")
        sys.exit(1)

    zip_file = zip_files[0]
    print(f"Processing zip file: {zip_file.name}")

    # Create SIA directories
    sia_input.mkdir(parents=True, exist_ok=True)
    sia_src.mkdir(parents=True, exist_ok=True)

    # Copy and extract zip
    shutil.copy2(zip_file, sia_input)
    with zipfile.ZipFile(sia_input / zip_file.name, 'r') as zf:
        zf.extractall(sia_src)
    print(f"Extracted {zip_file.name} to {sia_src}")

    # List extracted files
    print("Files in src directory:")
    for file in sia_src.rglob("*"):
        if file.is_file():
            print(f"  {file.relative_to(sia_src)}")

    # List files in sia_input directory
    print("Files in SIA input directory:")
    for file in sia_input.iterdir():
        if file.is_file():
            print(f"  {file.name}")

    # Find and convert XML file
    xml_files = list(sia_src.glob("XML_SIA_*.xml"))
    if xml_files:
        xml_file = xml_files[0]
        print(f"Converting encoding for {xml_file.name}")

        # Read with ISO-8859-1, convert to UTF-8
        with open(xml_file, 'r', encoding='iso-8859-1') as f:
            content = f.read()

        # Update XML declaration
        content = content.replace('encoding="ISO-8859-1"', 'encoding="UTF-8"')

        # Write back as UTF-8
        with open(xml_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"Converted {xml_file.name} to UTF-8")
    else:
        print("WARNING: No XML file found for encoding conversion")

    # Detect filenames using regex - updated for actual SIA naming patterns
    xml_pattern = re.compile(r'XML_SIA_(\d{4}-\d{2}-\d{2})\.xml')
    aixm_pattern = re.compile(r'AIXM4\.5_all_FR_OM_(\d{4}-\d{2}-\d{2})\.xml')

    xml_match = None
    aixm_match = None

    print("Scanning for SIA files with expected naming pattern...")
    for file in sia_src.iterdir():
        if file.is_file():
            print(f"  Checking file: {file.name}")
            if xml_match := xml_pattern.match(file.name):
                xml_filename = file.name
                print(f"    -> Found XML file: {xml_filename}")
            elif aixm_match := aixm_pattern.match(file.name):
                aixm_filename = file.name
                print(f"    -> Found AIXM file: {aixm_filename}")
            else:
                print(f"    -> No match for pattern")

    if not xml_match and not aixm_match:
        print("ERROR: No valid SIA files found with expected naming pattern")
        print("Expected patterns:")
        print("  XML:  XML_SIA_YYYY-MM-DD.xml")
        print("  AIXM: AIXM4.5_all_FR_OM_YYYY-MM-DD.xml")
        sys.exit(1)

    # Build command line arguments for poaff.py
    cmd_args = ["python", "poaff.py"]
    
    if xml_match:
        xml_path = f"../input/SIA/src/{xml_filename}"
        cmd_args.extend(["--sia-xml", xml_path])
        print(f"Will pass --sia-xml {xml_path}")
    
    if aixm_match:
        aixm_path = f"../input/SIA/src/{aixm_filename}"
        cmd_args.extend(["--sia-aixm", aixm_path])
        print(f"Will pass --sia-aixm {aixm_path}")

    # Change to correct working directory and run poaff.py
    os.chdir("/app/poaff_bpa/src")
    print(f"Running: {' '.join(cmd_args)}")
    os.execvp("python", cmd_args)

if __name__ == "__main__":
    main()