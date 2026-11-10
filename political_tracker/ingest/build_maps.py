"""Map boundary build script — Phase 4.

Downloads boundary files, simplifies, and outputs GeoJSON to static/political_tracker/maps/.
Run once locally, commit the output files.
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent.parent.parent / "political_tracker" / "static" / "political_tracker" / "maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_uk_constituencies():
    """Download ONS Westminster Parliamentary Constituencies (July 2024) and simplify."""
    log.info("Building UK constituencies map...")
    # TODO: Download from ONS, simplify with mapshaper or topojson, output to:
    # OUT_DIR / "uk_constituencies.geojson"
    log.warning("UK map build not implemented yet")


def build_us_states():
    """Download US Census cartographic boundary for states."""
    log.info("Building US states map...")
    # TODO: Download from Census, output to:
    # OUT_DIR / "us_states.geojson"
    log.warning("US states map build not implemented yet")


def build_us_house_districts():
    """Download US Census cartographic boundary for 119th Congress districts."""
    log.info("Building US House districts map...")
    # TODO: Download from Census (119th Congress), output to:
    # OUT_DIR / "us_house_districts.geojson"
    log.warning("US House districts map build not implemented yet")


def run():
    log.info("Building all maps...")
    build_uk_constituencies()
    build_us_states()
    build_us_house_districts()
    log.info("Map build complete. Output in %s", OUT_DIR)


if __name__ == "__main__":
    run()