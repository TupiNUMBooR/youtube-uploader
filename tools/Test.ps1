$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1

pip install -r requirements-dev.txt

python -m compileall -q app tests

coverage run -m pytest -q
coverage report
