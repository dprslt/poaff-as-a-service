⚠️ **IMPORTANT**: Only official data must be used for air navigation. The processed data provided by this tool is for informational purposes.

# POAFF As A Service

This repository wraps the POAFF project and its dependencies to create Docker images for automated and browser-based use.

The published images are:

- `dprslt/poaff` for the CLI or headless processing workflow, built from `Dockerfile`
- `dprslt/poaff-web` for the web interface, built from `Dockerfile.web`

CI behavior is explicit:

- Pull requests build both images for validation but do not push them to Docker Hub
- Pushes to `main` and version tags matching `v*.*.*` build and publish both images to Docker Hub

This repo currently only support the SIA AIXM4.5 files workflow.

## Quick Start

### Option A – Web Interface (recommended)

The web interface is the easiest way to use this tool. Upload a zip, watch the
logs, then download the archive or publish a GitHub release directly from the
browser.

**With Docker Compose:**

```bash
git clone https://github.com/dprslt/poaff-as-a-service.git
cd poaff-as-a-service
docker compose up --build
```

Open **http://localhost:5000** in your browser.

This starts the web image locally from `Dockerfile.web`. In CI, the same image is published as `dprslt/poaff-web`.

**With plain Docker:**

```bash
docker build -f Dockerfile.web -t dprslt/poaff-web .
docker run --rm -p 5000:5000 dprslt/poaff-web
```

### Web Interface Workflow

1. **Upload** – drag-and-drop (or browse) your SIA `.zip` file and optionally
   enter a release prefix (e.g. `sia0226-1902-1803`).
2. **Process** – click *Start processing*; live logs appear in the browser.
3. **Download** – once done, click *Download results* to get a zip of all
   generated files.
4. **Publish** – optionally click *Create GitHub release* and fill in your
   GitHub token, repository, tag and release details. Only the airspace output
   files (`.geojson` and `.txt` matching the `*@airspaces-*` pattern) are
   uploaded as release assets — log files and catalogues are excluded.

### Auto‑release (GitHub)

If you run behind a secured proxy and want the entire E2E workflow to be fully
automatic, set these environment variables:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | GitHub personal access token with `repo` scope |
| `GITHUB_REPO` | Target repository in `owner/repo` format |
| `AUTO_RELEASE` | Set to `true` to publish a release **automatically** after each successful processing run |

When `AUTO_RELEASE=true`, the web server will:

1. Detect the filename format `export_xml_bd_sia_YYYY-MM-DD-vXX.zip`
2. Derive the AIRAC cycle number from the date in the filename
3. Create a GitHub release with the correct tag (`aip-XX-YY`), title (`AIP XX/YY`),
   and description (`En vigueur du … au … inclus`)
4. Mark it as **latest** if the cycle is still current or upcoming
5. Upload all airspace output files (`.geojson`, `.txt`) as release assets

No manual token entry, tag selection, or form filling is needed — everything
flows from the filename.

> **Note:** The legacy manual release form is still available when env vars are
> not set, and the fields are pre‑filled when an AIRAC filename is detected.

### Option B – CLI / Docker (headless)

The headless image is built from `Dockerfile` and published by CI as `dprslt/poaff`.

#### Prerequisites

- Docker installed and running
- SIA airspace data zip file (see Input Data section)

#### Basic Usage

1. **Prepare input data**:
   - Download SIA airspace data from [SIA website](https://www.sia.aviation-civile.gouv.fr/produits-numeriques-en-libre-disposition/les-bases-de-donnees-sia.html)
   - Place the zip file in a dedicated input directory

2. **Run the processing**:

   ```bash
   docker run --rm \
     -v /path/to/input:/tmp/input:ro \
     -v /path/to/output:/app/poaff_bpa/output \
     dprslt/poaff
   ```

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


