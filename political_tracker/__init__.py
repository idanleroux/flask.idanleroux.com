"""Political Tracker Flask blueprint."""

import os
from flask import Blueprint, send_from_directory

bp = Blueprint(
    "political_tracker",
    __name__,
    template_folder="templates",
    static_folder="static/political_tracker",
    static_url_path="/political_tracker/static",
)

# Explicit static file route (ensures blueprint static files are served correctly)
@bp.route("/political_tracker/static/<path:filename>")
def tracker_static(filename):
    static_dir = os.path.join(bp.root_path, "static")
    return send_from_directory(static_dir, filename)

# Import routes to register them on the blueprint
from political_tracker.routes import *  # noqa: E402,F403,F401