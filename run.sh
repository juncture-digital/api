#/bin/zsh

cd "$(dirname "$0")"

source .venv/bin/activate
uvicorn --reload --host 0.0.0.0 --port 8000 src.main:app
