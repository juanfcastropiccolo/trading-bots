# Momentum Long/Short (perpetuos) — Paper Trading

_Fase 3 de PLAN_FUTUROS.md. Actualizado: 2026-10-20 (tick automático vía GitHub Actions). Pesos con signo (− = short), funding real, costos 0.05% por lado, palanca 1x._

> **Disciplina de decisión:** el pase a real se evalúa contra los criterios
> pre-fijados de VALIDACION_LS.md tras 4-6 semanas de paper — NO contra cuál
> estrategia rindió más en esta muestra corta.

## V4 + voltarget (candidata principal — pasó los criterios ex-ante)

- **Equity:** $93.37 (-6.63% desde los $100 iniciales)
- **Posiciones:** BTC +0.50, LTC +0.34
- **Días corriendo:** 96 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-10-20 | $93.37 | BTC +0.50, LTC +0.34 |
| 2026-10-19 | $91.81 | BTC +0.50, LTC +0.34 |
| 2026-10-18 | $91.89 | AVAX +0.21, LTC +0.31 |
| 2026-10-17 | $91.72 | AVAX +0.21, LTC +0.31 |
| 2026-10-16 | $92.53 | AVAX +0.21, LTC +0.31 |
| 2026-10-15 | $93.33 | AVAX +0.21, LTC +0.31 |
| 2026-10-14 | $92.42 | AVAX +0.21, LTC +0.31 |
| 2026-10-13 | $93.75 | AVAX +0.21, LTC +0.31 |
| 2026-10-12 | $93.53 | AVAX +0.21, LTC +0.31 |
| 2026-10-11 | $97.04 | AVAX +0.22, LTC +0.34 |
| 2026-10-10 | $95.44 | AVAX +0.22, LTC +0.34 |
| 2026-10-09 | $95.12 | AVAX +0.22, LTC +0.34 |
| 2026-10-08 | $94.40 | AVAX +0.22, LTC +0.34 |
| 2026-10-07 | $97.98 | AVAX +0.22, LTC +0.34 |
| 2026-10-06 | $100.35 | AVAX +0.22, LTC +0.34 |
| 2026-10-05 | $99.91 | AVAX +0.22, LTC +0.34 |
| 2026-10-04 | $100.15 | AVAX +0.23, LTC +0.32 |
| 2026-10-03 | $100.01 | AVAX +0.23, LTC +0.32 |
| 2026-10-02 | $99.14 | AVAX +0.23, LTC +0.32 |
| 2026-10-01 | $98.69 | AVAX +0.23, LTC +0.32 |
| 2026-09-30 | $98.20 | AVAX +0.23, LTC +0.32 |
| 2026-09-29 | $99.02 | AVAX +0.23, LTC +0.32 |
| 2026-09-28 | $98.39 | AVAX +0.23, LTC +0.32 |
| 2026-09-27 | $99.94 | AVAX +0.24, SOL +0.34 |
| 2026-09-26 | $99.64 | AVAX +0.24, SOL +0.34 |
| 2026-09-25 | $99.42 | AVAX +0.24, SOL +0.34 |
| 2026-09-24 | $96.95 | AVAX +0.24, SOL +0.34 |
| 2026-09-23 | $96.49 | AVAX +0.24, SOL +0.34 |
| 2026-09-22 | $99.79 | AVAX +0.24, SOL +0.34 |
| 2026-09-21 | $99.73 | AVAX +0.24, SOL +0.34 |

## V4 + ensemble (experimento secundario — falló criterio (c))

- **Equity:** $82.31 (-17.69% desde los $100 iniciales)
- **Posiciones:** AVAX +0.50, LTC +0.50
- **Días corriendo:** 96 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-10-20 | $82.31 | AVAX +0.50, LTC +0.50 |
| 2026-10-19 | $80.45 | AVAX +0.50, LTC +0.50 |
| 2026-10-18 | $81.13 | AVAX +0.50, LINK +0.50 |
| 2026-10-17 | $80.91 | AVAX +0.50, LINK +0.50 |
| 2026-10-16 | $82.92 | AVAX +0.50, LINK +0.50 |
| 2026-10-15 | $83.67 | AVAX +0.50, LINK +0.50 |
| 2026-10-14 | $83.49 | AVAX +0.50, LINK +0.50 |
| 2026-10-13 | $85.87 | AVAX +0.50, LINK +0.50 |
| 2026-10-12 | $84.65 | AVAX +0.50, LINK +0.50 |
| 2026-10-11 | $90.55 | AVAX +0.50, LINK +0.50 |
| 2026-10-10 | $86.86 | AVAX +0.50, LINK +0.50 |
| 2026-10-09 | $86.08 | AVAX +0.50, LINK +0.50 |
| 2026-10-08 | $84.64 | AVAX +0.50, LINK +0.50 |
| 2026-10-07 | $91.05 | AVAX +0.50, LINK +0.50 |
| 2026-10-06 | $95.20 | AVAX +0.50, LINK +0.50 |
| 2026-10-05 | $92.86 | AVAX +0.50, LINK +0.50 |
| 2026-10-04 | $94.19 | AVAX +0.50, LINK +0.50 |
| 2026-10-03 | $93.76 | AVAX +0.50, LINK +0.50 |
| 2026-10-02 | $91.31 | AVAX +0.50, LINK +0.50 |
| 2026-10-01 | $94.06 | AVAX +0.50, LINK +0.50 |
| 2026-09-30 | $93.80 | AVAX +0.50, LINK +0.50 |
| 2026-09-29 | $96.74 | AVAX +0.50, LINK +0.50 |
| 2026-09-28 | $95.65 | AVAX +0.50, LINK +0.50 |
| 2026-09-27 | $98.24 | AVAX +0.50, SOL +0.50 |
| 2026-09-26 | $97.74 | AVAX +0.50, SOL +0.50 |
| 2026-09-25 | $97.17 | AVAX +0.50, SOL +0.50 |
| 2026-09-24 | $93.14 | AVAX +0.50, SOL +0.50 |
| 2026-09-23 | $92.57 | AVAX +0.50, SOL +0.50 |
| 2026-09-22 | $98.65 | AVAX +0.50, SOL +0.50 |
| 2026-09-21 | $98.46 | AVAX +0.50, SOL +0.50 |

## Regla vigente

Gate de régimen: BTC>SMA-200 → top-2 de 10 majors por momentum sobre SMA-100,
long 0.5 c/u; BTC<SMA-200 → short BTC/ETH (−0.25 c/u) solo si bajo SMA-100 y
momentum negativo, resto cash. Rebalanceo semanal (lunes UTC). v4_voltarget
escala cada posición por min(1, 50%/vol anualizada 30d); v4_ensemble usa
momentum promedio 15/30/60/90d en lugar de 30d.
