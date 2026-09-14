# Momentum Long/Short (perpetuos) — Paper Trading

_Fase 3 de PLAN_FUTUROS.md. Actualizado: 2026-09-13 (tick automático vía GitHub Actions). Pesos con signo (− = short), funding real, costos 0.05% por lado, palanca 1x._

> **Disciplina de decisión:** el pase a real se evalúa contra los criterios
> pre-fijados de VALIDACION_LS.md tras 4-6 semanas de paper — NO contra cuál
> estrategia rindió más en esta muestra corta.

## V4 + voltarget (candidata principal — pasó los criterios ex-ante)

- **Equity:** $90.50 (-9.50% desde los $100 iniciales)
- **Posiciones:** LINK +0.31, SOL +0.39
- **Días corriendo:** 59 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-09-13 | $90.50 | LINK +0.31, SOL +0.39 |
| 2026-09-12 | $92.14 | LINK +0.31, SOL +0.39 |
| 2026-09-11 | $92.50 | LINK +0.31, SOL +0.39 |
| 2026-09-10 | $90.91 | LINK +0.31, SOL +0.39 |
| 2026-09-09 | $92.79 | LINK +0.31, SOL +0.39 |
| 2026-09-08 | $95.14 | LINK +0.31, SOL +0.39 |
| 2026-09-07 | $95.83 | LINK +0.31, SOL +0.39 |
| 2026-09-06 | $98.17 | LINK +0.36, SOL +0.41 |
| 2026-09-05 | $93.63 | LINK +0.36, SOL +0.41 |
| 2026-09-04 | $91.99 | LINK +0.36, SOL +0.41 |
| 2026-09-03 | $93.30 | LINK +0.36, SOL +0.41 |
| 2026-09-02 | $89.95 | LINK +0.36, SOL +0.41 |
| 2026-09-01 | $90.12 | LINK +0.36, SOL +0.41 |
| 2026-08-31 | $91.50 | LINK +0.36, SOL +0.41 |
| 2026-08-30 | $90.58 | LINK +0.35, XRP +0.29 |
| 2026-08-29 | $92.24 | LINK +0.35, XRP +0.29 |
| 2026-08-28 | $91.93 | LINK +0.35, XRP +0.29 |
| 2026-08-27 | $94.60 | LINK +0.35, XRP +0.29 |
| 2026-08-26 | $93.20 | LINK +0.35, XRP +0.29 |
| 2026-08-25 | $92.50 | LINK +0.35, XRP +0.29 |
| 2026-08-24 | $94.37 | LINK +0.35, XRP +0.29 |
| 2026-08-23 | $94.78 | BTC -0.25 |
| 2026-08-22 | $94.97 | BTC -0.25 |
| 2026-08-21 | $94.59 | BTC -0.25 |
| 2026-08-20 | $96.34 | BTC -0.25 |
| 2026-08-19 | $97.63 | BTC -0.25 |
| 2026-08-18 | $99.39 | BTC -0.25 |
| 2026-08-17 | $99.47 | BTC -0.25 |
| 2026-08-16 | $99.48 | cash |
| 2026-08-15 | $99.48 | cash |

## V4 + ensemble (experimento secundario — falló criterio (c))

- **Equity:** $84.60 (-15.40% desde los $100 iniciales)
- **Posiciones:** LINK +0.50, SOL +0.50
- **Días corriendo:** 59 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-09-13 | $84.60 | LINK +0.50, SOL +0.50 |
| 2026-09-12 | $86.81 | LINK +0.50, SOL +0.50 |
| 2026-09-11 | $87.28 | LINK +0.50, SOL +0.50 |
| 2026-09-10 | $85.29 | LINK +0.50, SOL +0.50 |
| 2026-09-09 | $87.83 | LINK +0.50, SOL +0.50 |
| 2026-09-08 | $91.24 | LINK +0.50, SOL +0.50 |
| 2026-09-07 | $92.25 | LINK +0.50, SOL +0.50 |
| 2026-09-06 | $93.97 | ETH +0.50, SOL +0.50 |
| 2026-09-05 | $91.85 | ETH +0.50, SOL +0.50 |
| 2026-09-04 | $90.84 | ETH +0.50, SOL +0.50 |
| 2026-09-03 | $92.70 | ETH +0.50, SOL +0.50 |
| 2026-09-02 | $89.01 | ETH +0.50, SOL +0.50 |
| 2026-09-01 | $89.30 | ETH +0.50, SOL +0.50 |
| 2026-08-31 | $91.59 | ETH +0.50, SOL +0.50 |
| 2026-08-30 | $89.97 | ETH +0.50, LINK +0.50 |
| 2026-08-29 | $92.02 | ETH +0.50, LINK +0.50 |
| 2026-08-28 | $91.65 | ETH +0.50, LINK +0.50 |
| 2026-08-27 | $94.89 | ETH +0.50, LINK +0.50 |
| 2026-08-26 | $93.65 | ETH +0.50, LINK +0.50 |
| 2026-08-25 | $91.15 | ETH +0.50, LINK +0.50 |
| 2026-08-24 | $93.27 | ETH +0.50, LINK +0.50 |
| 2026-08-23 | $93.70 | BTC -0.25 |
| 2026-08-22 | $93.88 | BTC -0.25 |
| 2026-08-21 | $93.51 | BTC -0.25 |
| 2026-08-20 | $95.24 | BTC -0.25 |
| 2026-08-19 | $96.52 | BTC -0.25 |
| 2026-08-18 | $98.26 | BTC -0.25 |
| 2026-08-17 | $98.34 | BTC -0.25 |
| 2026-08-16 | $99.48 | BTC -0.25, ETH -0.25 |
| 2026-08-15 | $99.31 | BTC -0.25, ETH -0.25 |

## Regla vigente

Gate de régimen: BTC>SMA-200 → top-2 de 10 majors por momentum sobre SMA-100,
long 0.5 c/u; BTC<SMA-200 → short BTC/ETH (−0.25 c/u) solo si bajo SMA-100 y
momentum negativo, resto cash. Rebalanceo semanal (lunes UTC). v4_voltarget
escala cada posición por min(1, 50%/vol anualizada 30d); v4_ensemble usa
momentum promedio 15/30/60/90d en lugar de 30d.
