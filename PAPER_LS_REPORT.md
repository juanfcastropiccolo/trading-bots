# Momentum Long/Short (perpetuos) — Paper Trading

_Fase 3 de PLAN_FUTUROS.md. Actualizado: 2026-07-17 (tick automático vía GitHub Actions). Pesos con signo (− = short), funding real, costos 0.05% por lado, palanca 1x._

> **Disciplina de decisión:** el pase a real se evalúa contra los criterios
> pre-fijados de VALIDACION_LS.md tras 4-6 semanas de paper — NO contra cuál
> estrategia rindió más en esta muestra corta.

## V4 + voltarget (candidata principal — pasó los criterios ex-ante)

- **Equity:** $100.00 (+0.00% desde los $100 iniciales)
- **Posiciones:** BTC -0.25
- **Días corriendo:** 1 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-07-17 | $100.00 | BTC -0.25 |

## V4 + ensemble (experimento secundario — falló criterio (c))

- **Equity:** $100.00 (+0.00% desde los $100 iniciales)
- **Posiciones:** BTC -0.25, ETH -0.25
- **Días corriendo:** 1 (desde 2026-07-17)

| Fecha | Equity | Posiciones |
|-------|--------|------------|
| 2026-07-17 | $100.00 | BTC -0.25, ETH -0.25 |

## Regla vigente

Gate de régimen: BTC>SMA-200 → top-2 de 10 majors por momentum sobre SMA-100,
long 0.5 c/u; BTC<SMA-200 → short BTC/ETH (−0.25 c/u) solo si bajo SMA-100 y
momentum negativo, resto cash. Rebalanceo semanal (lunes UTC). v4_voltarget
escala cada posición por min(1, 50%/vol anualizada 30d); v4_ensemble usa
momentum promedio 15/30/60/90d en lugar de 30d.
