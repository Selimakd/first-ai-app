#!/usr/bin/env bash
# Tüm testleri tek komutla koşturur:
#   - Önce hızlı unit testler
#   - Sonra ekran görüntüsü e2e testleri (slow)
#
# Kullanım (proje kökünden):
#   bash tools/run_tests.sh

set -u

PY=${PY:-venv/bin/python}
if [ ! -x "$PY" ]; then
    echo "[uyarı] $PY bulunamadı; sistem python3 denenecek"
    PY=python3
fi

echo "=== Hızlı unit testler ==="
"$PY" -m pytest -v --tb=short
rc_unit=$?

echo
echo "=== E2E ekran görüntüsü testleri (slow) ==="
"$PY" -m pytest -v -m slow --tb=short
rc_slow=$?

echo
echo "==================================="
echo "Özet:"
echo "  Unit testler:  exit=$rc_unit"
echo "  Slow testler:  exit=$rc_slow"
echo "==================================="

exit $(( rc_unit | rc_slow ))
