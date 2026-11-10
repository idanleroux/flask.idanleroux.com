from datetime import datetime
from flask import Flask, render_template

from political_tracker import bp as political_tracker_bp

app = Flask(__name__)

# Add now() to Jinja globals for templates
app.jinja_env.globals['now'] = datetime.utcnow

# Register Political Tracker blueprint at root (no prefix)
app.register_blueprint(political_tracker_bp)


@app.get("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)