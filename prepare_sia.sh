#!/bin/bash
# Script to prepare SIA files based on input-procedure.txt
# This script assumes the SIA zip and xml files are downloaded and placed in poaff_bpa/input/SIA/
# It will unzip the zip to src/, convert the xml_SIA-FR.xml to UTF-8, update encoding declaration, and rename with _BPa

set -e

SIA_DIR="poaff_bpa/input/SIA"
SRC_DIR="$SIA_DIR/src"

echo "Preparing SIA files in $SIA_DIR"

# Create src directory if not exists
mkdir -p "$SRC_DIR"

# Find and unzip the zip file
ZIP_FILE=$(find "$SIA_DIR" -maxdepth 1 -name "*.zip" | head -1)
if [ -n "$ZIP_FILE" ]; then
    echo "Unzipping $ZIP_FILE to $SRC_DIR"
    unzip -o "$ZIP_FILE" -d "$SRC_DIR"
else
    echo "No zip file found in $SIA_DIR"
fi

# Find the xml_SIA-FR.xml file
XML_FILE=$(find "$SIA_DIR" -maxdepth 1 -name "*_xml_SIA-FR.xml" | head -1)
if [ -n "$XML_FILE" ]; then
    echo "Converting $XML_FILE to UTF-8 and renaming"
    # Convert encoding from ISO-8859-1 to UTF-8
    iconv -f ISO-8859-1 -t UTF-8 "$XML_FILE" > "${XML_FILE}.tmp"
    # Update the XML declaration
    sed -i '1s/encoding="ISO-8859-1"/encoding="UTF-8"/' "${XML_FILE}.tmp"
    # Rename with _BPa
    BASENAME=$(basename "$XML_FILE" .xml)
    NEW_NAME="${BASENAME}_BPa.xml"
    mv "${XML_FILE}.tmp" "$SIA_DIR/$NEW_NAME"
    echo "Converted file saved as $SIA_DIR/$NEW_NAME"
else
    echo "No *_xml_SIA-FR.xml file found in $SIA_DIR"
fi

# Assume the aixm file is already renamed to the correct format
echo "Preparation complete. Ensure the aixm file is renamed to the format: YYYYMMDD-YYYYMMDD_AIRAC-XXXX_aixm4.5_SIA-FR.xml"