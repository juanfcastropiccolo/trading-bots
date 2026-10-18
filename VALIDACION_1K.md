# Validación long-only $1000 — Resultados

_Lista cerrada de 7 trials (ver `backend/scripts/validate_momentum_1k.py`). Datos: kucoin spot 1d, 1902 días comunes (2021-08-04 → 2026-10-18), 6 folds, costos 0.15%/lado. Corrido: 2026-10-18._

## Tabla resumen (capital simulado $1000)

| Config | Ret total | maxDD | Sharpe | Folds+ | Turnover anual | Trades/año | Equity final |
|--------|-----------|-------|--------|--------|----------------|-----------|--------------|
| base_top2 (control) | +15% | 80.5% | 0.35 | 2/6 | 60.4x | 77 | $1,148 |
| top3 | +10% | 76.3% | 0.31 | 2/6 | 54.6x | 100 | $1,105 |
| top2_hyst4 | -40% | 72.2% | 0.11 | 1/6 | 34.2x | 48 | $595 |
| top3_hyst5 | -10% | 74.2% | 0.23 | 2/6 | 31.3x | 64 | $901 |
| top2_vt50 | +65% | 55.2% | 0.45 | 3/6 | 44.9x | 101 | $1,647 |
| top2_ens | -5% | 84.2% | 0.29 | 2/6 | 55.1x | 68 | $949 |
| top3_hyst5_vt50 | +42% | 51.5% | 0.37 | 3/6 | 24.1x | 90 | $1,416 |
| b&h equiponderado | +42% | 79.4% | 0.44 | — | — | — | $1,424 |

## Veredicto contra los criterios ex-ante

| Config | (a) folds≥4/6 | (b) Sharpe≥base+0.05 | (c) maxDD≤base | (d) turnover≤2x | Pasa |
|--------|----|----|----|----|------|
| top3 | ✗ | ✗ | ✓ | ✓ | no |
| top2_hyst4 | ✗ | ✗ | ✓ | ✓ | no |
| top3_hyst5 | ✗ | ✗ | ✓ | ✓ | no |
| top2_vt50 | ✗ | ✓ | ✓ | ✓ | no |
| top2_ens | ✗ | ✗ | ✗ | ✓ | no |
| top3_hyst5_vt50 | ✗ | ✗ | ✓ | ✓ | no |

**Config elegida para la cuenta de $1000: `base_top2`** (ninguna variante superó al baseline en los 4 criterios; se mantiene la regla de producción)

## Detalle por fold

| Config | F1 | F2 | F3 | F4 | F5 | F6 |
|--------|----|----|----|----|----|----|
| base_top2 | -63% | -24% | +200% | +74% | -14% | -8% |
| top3 | -60% | -25% | +195% | +83% | -21% | -14% |
| top2_hyst4 | -57% | -3% | +99% | -4% | -10% | -17% |
| top3_hyst5 | -59% | -19% | +126% | +46% | -13% | -6% |
| top2_vt50 | -41% | -10% | +103% | +34% | +16% | -2% |
| top2_ens | -65% | -27% | +217% | +64% | -16% | -15% |
| top3_hyst5_vt50 | -39% | -10% | +88% | +21% | +17% | -3% |

_Notas: mecánica idéntica a producción (decisión diaria, se opera solo al cambiar el conjunto; voltarget refresca escala los lunes). Pesos constantes entre operaciones, misma aproximación que validate_momentum.py. El fold 1 incluye el warmup de la SMA-100._
