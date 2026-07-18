# Validación momentum long/short sobre perpetuos — Resultados

_Fase 2 de PLAN_FUTUROS.md. Datos: perps USDT-M + funding real, 2020-09-23 → 2026-06-30
(2.102 días, 1.089 de bear BTC<SMA200), 8 folds, 12 trials declarados (9 de la lista
cerrada + 3 ablaciones diagnósticas). Costos realista 0.05%/lado (0.15% también corrido)._

## Tabla resumen (L=1, costos 0.05%)

| Config | Ret total | maxDD | Sharpe | Folds+ | PnL pata short* | Liq @1x |
|--------|-----------|-------|--------|--------|------------------|---------|
| long-only baseline (perps) | +61% | 80.7% | 0.46 | 3/8 | — | 0 |
| **V4 gate + voltarget** ✅ | **+244%** | **40.7%** | **0.84** | **6/8** | **+11.2pp** | **0** |
| V4 gate + ensemble | +1.738% | 60.3% | 1.08 | 6/8 | +0.8pp (≈0) | 0 |
| V4 gate (mom-30 puro) | +378% | 59.0% | 0.75 | 5/8 | +16.5pp | 0 |
| V2 TSMOM | +136% | 48.6% | 0.60 | 5/8 | — | 0 |
| V1 espejo alts (control) | +94% | 77.3% | 0.50 | 4/8 | — | **1** ⚠️ |
| V3 mkt-neutral (control) | +22% | 41.0% | 0.27 | 3/8 | — | **1** ⚠️ |
| Ablación gate→cash + voltarget | +220% | 31.3% | 0.83 | 5/8 | (sin shorts) | 0 |
| b&h equiponderado | +1.478% | 79.2% | 1.00 | — | — | — |

_*PnL de la pata short aislado: precio + funding + costos propios, en pp aditivos sobre sus días activos._

## Veredicto contra los criterios ex-ante

**V4 + voltarget** (gate de régimen BTC/SMA-200, shorts solo BTC-ETH a media máquina,
vol targeting 50% anualizado) es la única config que pasa:
- (a) folds ≥6/8 ✓ — (c) pata short rentable neta de funding (+11.2pp; el funding sumó +1.7pp) ✓ —
  (d) maxDD 40.7%, la mitad del baseline ✓ — (e) cero liquidaciones a 1x ✓.
- (b) parcial: en régimen bull la regla es idéntica a la long-only, pero el gate entra tarde
  a los rebotes post-bear (bull-only +280% vs +500% del baseline+voltarget). Es el precio del
  seguro; el Sharpe full-period casi se duplica (0.84 vs 0.56) y el peor día baja de −29% a −13%.
- V4+ensemble rinde más (+1.738%, Sharpe 1.08) pero su pata short es break-even → falla (c);
  su retorno extra viene del momentum multi-lookback en los longs, no de los shorts.

## Hallazgos honestos

1. **Los controles validaron el diseño**: V1 (shorts en alts) sufrió una liquidación simulada
   incluso a palanca 1x — el squeeze de DOGE de ene-2021, tal cual advirtió la teoría. V3
   confirmó que no hay spread cross-sectional rentable entre 10 majors correlacionados.
2. **La palanca 2x no se justifica**: mejora retornos en las configs buenas pero lleva el
   maxDD a 68-88% con 2 liquidaciones simuladas. Queda descartada para cualquier fase real.
3. **El baseline long-only en la ventana extendida es mucho más débil** (3/8 folds, Sharpe
   0.46, bear-only −90%) que en la ventana de 3 años de la validación original. La ventana
   2023-26 era benigna. Implicación: la estrategia en producción depende del gate de régimen
   más de lo que sabíamos — el upgrade tiene valor aunque nunca se operen futuros.
4. **Fold 1 es mayormente warmup** (SMA-200 consume ~200 de sus 263 días): efectivamente son
   7 folds completos + 1 parcial, igual para todas las configs.
5. **Multiplicidad**: 12 trials declarados. El ganador no fue elegido por mejor retorno
   (V4+ensemble rinde 7x más) sino por los criterios pre-fijados — el gate de paper trading
   prospectivo (Fase 3) es el control final contra el overfitting residual.
