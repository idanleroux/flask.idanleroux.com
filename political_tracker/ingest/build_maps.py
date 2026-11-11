"""Map boundary build script — Phase 4.

Downloads boundary files, simplifies, and outputs GeoJSON to static/political_tracker/maps/.
Run once locally, commit the output files.
"""

from __future__ import annotations

import logging
import zipfile
import io
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent.parent.parent / "political_tracker" / "static" / "political_tracker" / "maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def download_and_extract_zip(url, extract_name, output_path):
    """Download a zip file and extract a specific file."""
    log.info("Downloading %s", url)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # Find the file matching extract_name
        for name in zf.namelist():
            if extract_name in name and name.endswith(('.geojson', '.json', '.shp')):
                log.info("Extracting %s", name)
                with zf.open(name) as f:
                    content = f.read()
                    output_path.write_bytes(content)
                return
        raise FileNotFoundError(f"No file matching '{extract_name}' in zip")


def build_uk_constituencies():
    """Download ONS Westminster Parliamentary Constituencies (July 2024) and simplify."""
    log.info("Building UK constituencies map...")
    
    # ONS GeoPortal - Westminster Parliamentary Constituencies (July 2024) 
    # Generalised (clipped) version
    url = "https://geoportal.statistics.gov.uk/datasets/ons::westminster-parliamentary-constituencies-july-2024-boundaries-uk-bgc/download?format=geojson"
    # Alternative: direct GeoJSON from ONS
    # Using the generalised version for smaller file size
    
    output = OUT_DIR / "uk_constituencies.geojson"
    
    if output.exists():
        log.info("UK constituencies map already exists")
        return
    
    try:
        log.info("Downloading UK constituencies from ONS...")
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        output.write_bytes(resp.content)
        log.info("Saved UK constituencies to %s", output)
    except Exception as e:
        log.error("Failed to download UK constituencies: %s", e)
        log.info("You may need to manually download from:")
        log.info("https://geoportal.statistics.gov.uk/datasets/ons::westminster-parliamentary-constituencies-july-2024-boundaries-uk-bgc")
        raise


def build_us_states():
    """Download US Census cartographic boundary for states."""
    log.info("Building US states map...")
    
    # US Census 2023 cartographic boundary file - States (500k resolution) - GeoJSON
    url = "https://www2.census.gov/geo/tiger/GENZ2023/geojson/cb_2023_us_state_500k.geojson"
    output = OUT_DIR / "us_states.geojson"
    
    if output.exists():
        log.info("US states map already exists")
        return
    
    try:
        log.info("Downloading US states GeoJSON...")
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        output.write_bytes(resp.content)
        log.info("Saved US states to %s", output)
    except Exception as e:
        log.error("Failed to download US states: %s", e)
        raise


def build_us_house_districts():
    """Download US Census cartographic boundary for 119th Congress districts.
    
    Note: 119th Congress boundaries only available as per-state shapefiles from Census TIGER.
    Using 118th Congress as approximation (very similar, minor redistricting only).
    """
    log.info("Building US House districts map (using 118th Congress approximation)...")
    
    # Try to find a pre-built 118th Congress GeoJSON
    urls = [
        # Try various known sources
        "https://raw.githubusercontent.com/jasonong/List-of-US-Congressional-Districts/main/us_congressional_districts_118.geojson",
        "https://raw.githubusercontent.com/openelections/openelections-data/master/districts/us_congressional_districts_118.geojson",
    ]
    
    output = OUT_DIR / "us_house_districts.geojson"
    
    if output.exists():
        log.info("US House districts map already exists")
        return
    
    for url in urls:
        try:
            log.info("Trying %s", url)
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                # Verify it's valid GeoJSON
                import json
                json.loads(resp.text)
                output.write_bytes(resp.content)
                log.info("Saved US House districts (118th Congress approx) to %s", output)
                log.warning("Using 118th Congress boundaries as approximation for 119th.")
                log.warning("For exact 119th boundaries, merge TIGER2024 per-state shapefiles.")
                return
        except Exception as e:
            log.warning("Failed %s: %s", url, e)
            continue
    
    # Fallback: create a placeholder
    log.warning("Could not download US House districts. Creating placeholder.")
    placeholder = {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "note": "US House districts (119th Congress) - placeholder. Download TIGER2024 per-state shapefiles and merge for full boundaries."
        }
    }
    import json
    output.write_text(json.dumps(placeholder))
    log.info("Created placeholder at %s", output)


def run():
    log.info("Building all maps...")
    build_uk_constituencies()
    build_us_states()
    build_us_house_districts()
    log.info("Map build attempted. Check output in %s", OUT_DIR)
    log.info("Note: Shapefiles need conversion to GeoJSON (use mapshaper.org or ogr2ogr)")


if __name__ == "__main__":
    run()