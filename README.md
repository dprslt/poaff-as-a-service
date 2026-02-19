⚠️ **IMPORTANT**: Only official data must be used for air navigation. The processed data provided by this tool is for informational purposes.

# POAFF As A Service

This repository Wrap  the POAFF project and it dependencies to create a doker image to ease the use of this tool in automated environments.

The image is pushed to `dprslt/poaff`.

This repo currently only support the SIA AIXM4.5 files workflow.

## Quick Start with Docker

### Prerequisites

- Docker installed and running
- SIA airspace data zip file (see Input Data section)

### Basic Usage

1. **Prepare input data**:
   - Download SIA airspace data from [SIA website](https://www.sia.aviation-civile.gouv.fr/produits-numeriques-en-libre-disposition/les-bases-de-donnees-sia.html)
   - Place the zip file in a dedicated input directory

2. **Run the processing**:

   ```bash
   docker run --rm \
     -v /path/to/input:/tmp/input:ro \
     -v /path/to/output:/app/poaff_bpa/output \
     dprslt/poaff


3. **Access results**:
   - Generated files will be available in your output directory
   - Includes airspace boundaries, frequency data, and various format exports

## Detailed Usage

### Input Data Preparation

POAFF processes SIA (French Civil Aviation Authority) airspace data. The tool expects:

1. **Download SIA Data**:
   - Visit: https://www.sia.aviation-civile.gouv.fr/produits-numeriques-en-libre-disposition/les-bases-de-donnees-sia.html
   - Download the latest AIRAC cycle zip file containing AIXM and XML data

2. **File Structure**:
   The zip should contain:
   - `AIXM4.5_all_FR_OM_YYYY-MM-DD.xml`: Airspace definitions in AIXM format
   - `XML_SIA_YYYY-MM-DD.xml`: Frequency and additional data in XML format

4. **Naming Convention**:
   Files should follow the pattern:
   - XML: `XML_SIA_YYYY-MM-DD.xml`
   - AIXM: `AIXM4.5_all_FR_OM_YYYY-MM-DD.xml`

### Docker Workflow

The Docker container automates the entire processing pipeline:

1. **Input Mounting**: Mount your input directory containing the SIA zip to `/tmp/input`
2. **Automatic Processing**:
   - Extracts the zip file
   - Converts XML encoding from ISO-8859-1 to UTF-8
   - Detects file paths using regex patterns
   - Updates configuration dynamically
   - Runs the airspace processing pipeline
3. **Output Mounting**: Mount an output directory to `/app/poaff_bpa/output` for results

### Output Files

The tool generates several output formats in the mounted output directory:

- **GeoJSON files**: `*_all.geojson`, `*_freeflight.geojson`, etc.
- **OpenAir files**: `*_all.txt`, `*_freeflight.txt`, etc.
- **KML files**: `*_all.kml`, `*_freeflight.kml`, etc.
- **Catalog files**: JSON catalogs of airspace data
- **Log files**: Processing logs and optimization reports

### Configuration Options

The processing can be customized by modifying `poaff_bpa/src/poaff.py`:

- `debugLevel`: Set to 1 for processing reports, 2 for detailed logs
- `epsilonReduce`: Enable/disable geometry optimization
- `geojsonConstruct`, `openairConstruct`, `kmlConstruct`: Enable/disable output formats
- `partialConstruct`: Process only North/South France regions

## Create version


```
python rename_poaff_files.py sia0226-1902-1803
Get-ChildItem -Filter "sia0226-1902-1803@*" | Compress-Archive -DestinationPath "global_files.zip" -Force
```


## Troubleshooting

### Common Issues

**"No zip file found"**
- Ensure your input directory contains exactly one `.zip` file
- Check file permissions and path

**"No valid SIA files found"**
- Verify the zip contains files matching the naming pattern
- Ensure files are named like `XML_SIA_2026-02-19.xml` and `AIXM4.5_all_FR_OM_2026-02-19.xml`

**"Processing failed"**
- Check the container logs with `docker run -it poaff`
- Ensure sufficient disk space in output directory
- Verify input data integrity

**Permission denied**
- On Windows, ensure Docker has access to your directories
- Try running Docker Desktop as administrator

### Debug Mode

For troubleshooting, run with interactive mode:
```bash
docker run -it --rm \
  -v /path/to/input:/tmp/input:ro \
  -v /path/to/output:/app/poaff_bpa/output \
  poaff
```



## Components & Licenses

This project integrates three separate repositories to provide a complete airspace data processing solution:

### aixmParser
**Repository**: [cquest/aixmParser](https://github.com/cquest/aixmParser)  
**Purpose**: Parses AIXM 4.5 (Aeronautical Information Exchange Model) XML files and converts them to GeoJSON, OpenAir, KML, and other formats  
**Original Author**: ([@cquest](https://github.com/cquest))  
**Contributor**:  ([@BPascal-91](https://github.com/BPascal-91))  
**License**: WTFPL (Do What The Fuck You Want To Public License) - See [aixmParser/LICENSE.txt](aixmParser/LICENSE.txt)

Key features:
- Airspace boundary extraction from AIXM data
- Ground height estimation using SRTM elevation data
- Multiple output format support (GeoJSON, OpenAir, KML)
- Geometry optimization using RDP algorithm

### openairParser
**Repository**: [BPascal-91/openairParser](https://github.com/BPascal-91/openairParser)  
**Purpose**: Parses OpenAir format files and converts them to AIXM 4.5 XML  
**Author**: ([@BPascal-91](https://github.com/BPascal-91))  
**License**: WTFPL (Do What The Fuck You Want To Public License) - See [openairParser/LICENSE.txt](openairParser/LICENSE.txt)

Key features:
- Reverse conversion from OpenAir to AIXM
- Support for OpenAir airspace and terrain description language

### poaff_bpa (Main Application)
**Repository**: [BPascal-91/poaff](https://github.com/BPascal-91/poaff)  
**Purpose**: Batch processing system for French airspace data from SIA (Service de l'Information Aéronautique)  
**Author**: ([@BPascal-91](https://github.com/BPascal-91))  
**License**: GNU General Public License v3.0 - See [poaff_bpa/LICENSE.txt](poaff_bpa/LICENSE.txt)

Key features:
- Automated processing of SIA XML frequency data
- SIA AIXM airspace definitions processing
- Eurocontrol data integration
- Regional airspace map generation for paragliding use


