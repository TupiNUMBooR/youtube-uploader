python -m venv .venv
./.venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r ms2-uploader/requirements.txt
python tools/oauth.py
