# Momentum Long/Short (perpetuos) — Paper Trading

_Fase 3 de PLAN_FUTUROS.md. Actualizado: 2026-11-26 (tick automático vía GitHub Actions). Pesos con signo (− = short), funding real, costos 0.05% por lado, palanca 1x._

> **Disciplina de decisión:** el pase a real se evalúa contra los criterios
> pre-fijados de VALIDACION_LS.md tras 4-6 semanas de paper — NO contra cuál
> estrategia rindió más en esta muestra corta.

## V4 + voltarget (candidata principal — pasó los criterios ex-ante)

- **Equity:** $86.40 (-13.60% desde los $100 iniciales)
- **Posiciones:** BTC -0.25, ETH -0.19
- **Días corriendo:** 133 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-11-26 | $86.40 | BTC -0.25, ETH -0.19 |
| 2026-11-25 | $86.40 | BTC -0.25, ETH -0.19 |
| 2026-11-24 | $86.75 | BTC -0.25, ETH -0.19 |
| 2026-11-23 | $85.94 | BTC -0.25, ETH -0.19 |
| 2026-11-22 | $85.80 | BTC -0.25, ETH -0.21 |
| 2026-11-21 | $86.61 | BTC -0.25, ETH -0.21 |
| 2026-11-20 | $87.82 | BTC -0.25, ETH -0.21 |
| 2026-11-19 | $85.37 | BTC -0.25, ETH -0.21 |
| 2026-11-18 | $84.80 | BTC -0.25, ETH -0.21 |
| 2026-11-17 | $83.72 | BTC -0.25, ETH -0.21 |
| 2026-11-16 | $83.79 | BTC -0.25, ETH -0.21 |
| 2026-11-15 | $83.81 | cash |
| 2026-11-14 | $83.81 | cash |
| 2026-11-13 | $83.81 | cash |
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

## V4 + ensemble (experimento secundario — falló criterio (c))

- **Equity:** $66.77 (-33.23% desde los $100 iniciales)
- **Posiciones:** BTC -0.25, ETH -0.25
- **Días corriendo:** 133 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-11-26 | $66.77 | BTC -0.25, ETH -0.25 |
| 2026-11-25 | $66.77 | BTC -0.25, ETH -0.25 |
| 2026-11-24 | $67.07 | BTC -0.25, ETH -0.25 |
| 2026-11-23 | $66.38 | BTC -0.25, ETH -0.25 |
| 2026-11-22 | $66.25 | BTC -0.25, ETH -0.25 |
| 2026-11-21 | $66.92 | BTC -0.25, ETH -0.25 |
| 2026-11-20 | $67.95 | BTC -0.25, ETH -0.25 |
| 2026-11-19 | $65.88 | BTC -0.25, ETH -0.25 |
| 2026-11-18 | $65.42 | BTC -0.25, ETH -0.25 |
| 2026-11-17 | $64.53 | BTC -0.25, ETH -0.25 |
| 2026-11-16 | $64.59 | BTC -0.25, ETH -0.25 |
| 2026-11-15 | $65.46 | AVAX +0.50 |
| 2026-11-14 | $64.50 | AVAX +0.50 |
| 2026-11-13 | $69.27 | AVAX +0.50 |
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

## Regla vigente

Gate de régimen: BTC>SMA-200 → top-2 de 10 majors por momentum sobre SMA-100,
long 0.5 c/u; BTC<SMA-200 → short BTC/ETH (−0.25 c/u) solo si bajo SMA-100 y
momentum negativo, resto cash. Rebalanceo semanal (lunes UTC). v4_voltarget
escala cada posición por min(1, 50%/vol anualizada 30d); v4_ensemble usa
momentum promedio 15/30/60/90d en lugar de 30d.
