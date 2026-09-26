# Flask Starter

A small Flask website with a reusable Jinja layout, a home page, and local static assets.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:5000>. Flask's debug reloader is enabled for local development.

## Structure

```text
main.py
templates/
  index.html
```