from datetime import datetime
from flask import Flask, render_template

from political_tracker import bp as political_tracker_bp

app = Flask(__name__)

# Party colour map (CSS token colours, hex). Used by templates for party badges.
PARTY_COLOURS = {
    # UK
    'Labour': '#e4003b',
    'Conservative': '#2b9be6',
    'Liberal Democrat': '#faa61a',
    'Liberal Democrats': '#faa61a',
    'SNP': '#f2d03b',
    'Scottish National Party': '#f2d03b',
    'Reform UK': '#12b6cf',
    'Green': '#6ab023',
    'Green Party': '#6ab023',
    'Plaid Cymru': '#2e9e5b',
    # US
    'Democratic': '#4a90e2',
    'Democrat': '#4a90e2',
    'Republican': '#e5484d',
    'GOP': '#e5484d',
    'Independent': '#c9a227',
}
DEFAULT_COLOUR = '#8d98ad'


def party_colour(party):
    """Return the CSS colour hex for a party name, or the default colour."""
    if not party:
        return DEFAULT_COLOUR
    return PARTY_COLOURS.get(party.strip(), DEFAULT_COLOUR)


def merge_args(**overrides):
    """Merge request.args with overrides; overrides win.

    Use this in templates for url_for to avoid duplicate keyword arguments
    when request.args already contains the overridden key (e.g. chamber).
    """
    from flask import request
    args = dict(request.args)
    args.update(overrides)
    return args


app.jinja_env.globals['now'] = datetime.utcnow
app.jinja_env.globals['party_colour'] = party_colour
app.jinja_env.globals['merge_args'] = merge_args

# Register Political Tracker blueprint at root (no prefix)
app.register_blueprint(political_tracker_bp)


@app.get("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)