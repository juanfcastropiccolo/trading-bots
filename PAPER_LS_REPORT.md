# Momentum Long/Short (perpetuos) — Paper Trading

_Fase 3 de PLAN_FUTUROS.md. Actualizado: 2026-11-12 (tick automático vía GitHub Actions). Pesos con signo (− = short), funding real, costos 0.05% por lado, palanca 1x._

> **Disciplina de decisión:** el pase a real se evalúa contra los criterios
> pre-fijados de VALIDACION_LS.md tras 4-6 semanas de paper — NO contra cuál
> estrategia rindió más en esta muestra corta.

## V4 + voltarget (candidata principal — pasó los criterios ex-ante)

- **Equity:** $83.81 (-16.19% desde los $100 iniciales)
- **Posiciones:** cash
- **Días corriendo:** 119 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-11-12 | $83.81 | cash |
| 2026-11-11 | $83.81 | cash |
| 2026-11-10 | $83.81 | cash |
| 2026-11-09 | $83.81 | cash |
| 2026-11-08 | $83.56 | BTC +0.50 |
| 2026-11-07 | $84.13 | BTC +0.50 |
| 2026-11-06 | $84.12 | BTC +0.50 |
| 2026-11-05 | $84.26 | BTC +0.50 |
| 2026-11-04 | $86.65 | BTC +0.50 |
| 2026-11-03 | $85.00 | BTC +0.50 |
| 2026-11-02 | $84.66 | BTC +0.50 |
| 2026-11-01 | $86.33 | BNB +0.50, BTC +0.50 |
| 2026-10-31 | $85.37 | BNB +0.50, BTC +0.50 |
| 2026-10-30 | $85.27 | BNB +0.50, BTC +0.50 |
| 2026-10-29 | $85.22 | BNB +0.50, BTC +0.50 |
| 2026-10-28 | $90.82 | BNB +0.50, BTC +0.50 |
| 2026-10-27 | $89.71 | BNB +0.50, BTC +0.50 |
| 2026-10-26 | $89.20 | BNB +0.50, BTC +0.50 |
| 2026-10-25 | $89.21 | BTC +0.50, LTC +0.34 |
| 2026-10-24 | $89.80 | BTC +0.50, LTC +0.34 |
| 2026-10-23 | $90.09 | BTC +0.50, LTC +0.34 |
| 2026-10-22 | $91.06 | BTC +0.50, LTC +0.34 |
| 2026-10-21 | $93.95 | BTC +0.50, LTC +0.34 |
| 2026-10-20 | $93.37 | BTC +0.50, LTC +0.34 |
| 2026-10-19 | $91.81 | BTC +0.50, LTC +0.34 |
| 2026-10-18 | $91.89 | AVAX +0.21, LTC +0.31 |
| 2026-10-17 | $91.72 | AVAX +0.21, LTC +0.31 |
| 2026-10-16 | $92.53 | AVAX +0.21, LTC +0.31 |
| 2026-10-15 | $93.33 | AVAX +0.21, LTC +0.31 |
| 2026-10-14 | $92.42 | AVAX +0.21, LTC +0.31 |

## V4 + ensemble (experimento secundario — falló criterio (c))

- **Equity:** $69.78 (-30.22% desde los $100 iniciales)
- **Posiciones:** AVAX +0.50
- **Días corriendo:** 119 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-11-12 | $69.78 | AVAX +0.50 |
| 2026-11-11 | $70.42 | AVAX +0.50 |
| 2026-11-10 | $69.84 | AVAX +0.50 |
| 2026-11-09 | $70.99 | AVAX +0.50 |
| 2026-11-08 | $71.01 | cash |
| 2026-11-07 | $71.01 | cash |
| 2026-11-06 | $71.01 | cash |
| 2026-11-05 | $71.01 | cash |
| 2026-11-04 | $71.01 | cash |
| 2026-11-03 | $71.01 | cash |
| 2026-11-02 | $71.01 | cash |
| 2026-11-01 | $73.03 | AVAX +0.50, BNB +0.50 |
| 2026-10-31 | $72.02 | AVAX +0.50, BNB +0.50 |
| 2026-10-30 | $71.93 | AVAX +0.50, BNB +0.50 |
| 2026-10-29 | $70.47 | AVAX +0.50, BNB +0.50 |
| 2026-10-28 | $76.70 | AVAX +0.50, BNB +0.50 |
| 2026-10-27 | $75.78 | AVAX +0.50, BNB +0.50 |
| 2026-10-26 | $75.77 | AVAX +0.50, BNB +0.50 |
| 2026-10-25 | $75.58 | AVAX +0.50, LTC +0.50 |
| 2026-10-24 | $76.05 | AVAX +0.50, LTC +0.50 |
| 2026-10-23 | $76.48 | AVAX +0.50, LTC +0.50 |
| 2026-10-22 | $77.83 | AVAX +0.50, LTC +0.50 |
| 2026-10-21 | $81.87 | AVAX +0.50, LTC +0.50 |
| 2026-10-20 | $82.31 | AVAX +0.50, LTC +0.50 |
| 2026-10-19 | $80.45 | AVAX +0.50, LTC +0.50 |
| 2026-10-18 | $81.13 | AVAX +0.50, LINK +0.50 |
| 2026-10-17 | $80.91 | AVAX +0.50, LINK +0.50 |
| 2026-10-16 | $82.92 | AVAX +0.50, LINK +0.50 |
| 2026-10-15 | $83.67 | AVAX +0.50, LINK +0.50 |
| 2026-10-14 | $83.49 | AVAX +0.50, LINK +0.50 |

## Regla vigente

Gate de régimen: BTC>SMA-200 → top-2 de 10 majors por momentum sobre SMA-100,
long 0.5 c/u; BTC<SMA-200 → short BTC/ETH (−0.25 c/u) solo si bajo SMA-100 y
momentum negativo, resto cash. Rebalanceo semanal (lunes UTC). v4_voltarget
escala cada posición por min(1, 50%/vol anualizada 30d); v4_ensemble usa
momentum promedio 15/30/60/90d en lugar de 30d.
