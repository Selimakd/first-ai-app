#!/usr/bin/env bash
# Streamlit, ~/.streamlit yazmak ister; Cursor sandbox / kısıtlı ortamlarda bu başarısız
# olup tarayıcıda "Connection lost" görülebilir. HOME'u proje içine alarak kaçınırız.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/.streamlit_home"
export HOME="$ROOT/.streamlit_home"
PY="$ROOT/venv/bin/python3.14"
if [[ ! -x "$PY" ]]; then
  PY="$ROOT/venv/bin/python3"
fi
exec "$PY" -m streamlit run "$ROOT/app.py" "$@"
