"""Political Tracker Flask blueprint."""

from flask import Blueprint

bp = Blueprint(
    "political_tracker",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/political_tracker/static",
)

# Import routes to register them on the blueprint
from political_tracker.routes import *  # noqa: E402,F403,F401