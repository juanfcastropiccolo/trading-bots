#!/usr/bin/env bash
# Corre las cinco pruebas A-E sobre datos REALES (perps Binance) y genera el
# reporte. Necesita salida de red hacia data.binance.vision la primera vez
# (después queda cacheado en backend/data/cache/).
#
#   bash backend/scripts/run_abcde_real.sh            # desde la raíz del repo
#   PYTHON=.venv/bin/python bash backend/scripts/run_abcde_real.sh
#
# Dependencias: pandas numpy scikit-learn (pip install pandas numpy scikit-learn).
set -euo pipefail
cd "$(dirname "$0")/.."            # backend/
PYTHON="${PYTHON:-python}"

echo "== 1/3 datos reales (klines 1d + funding de perps, bulk mensual Binance) =="
$PYTHON scripts/futures_data.py

echo "== 2/3 cinco pruebas con --source real =="
for s in breakout pairs carry tsmom_vt ml_walkforward; do
  echo "----- validate_$s.py -----"
  $PYTHON "scripts/validate_$s.py" --source real
done

echo "== 3/3 reporte =="
$PYTHON scripts/render_abcde_report.py --source real
echo "Listo: ESTRATEGIAS_ABCDE_REAL.md en la raíz del repo; JSON en backend/data/*_results_real.json"
