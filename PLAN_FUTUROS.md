# Plan: Momentum Long/Short sobre Futuros Perpetuos

_Basado en 3 investigaciones independientes (teoría de perpetuos, diseño determinístico, evaluación de ML) — 18 jul 2026. Estado: **pendiente de aprobación**._

## Decisiones de diseño (y la evidencia que las respalda)

| Decisión | Fundamento |
|----------|------------|
| **Sin ML para predecir dirección** | El único backtest de XGBoost con costos de perps y walk-forward honesto empata con buy&hold (arXiv 2606.00060); los Sharpe altos de la literatura dependen de shorts en microcaps ilíquidas; con ~2.000 observaciones efectivas el edge buscado es menor que el ruido de la validación. ML queda reservado a futuro solo como meta-labeling (sizing), nunca dirección. |
| **Shorts solo en BTC y ETH** | El momentum se concentra en winners y los losers rebotan (SSRN 4675565); squeezes históricos de +17% intradía en BTC y +20-50% en alts; wicks de −40/−80% en alts (oct-2025). Shortear el bottom-2 de alts es la parte frágil de la literatura. |
| **Shorts solo con régimen bajista confirmado (BTC < SMA-200) y a media máquina** | Confina la pata débil al único contexto con sentido a priori; en bull la estrategia es bit-a-bit la long-only ya validada (control interno). |
| **Palanca base 1x; 2x solo como análisis de sensibilidad** | MaxDD histórico ~55%; 2x liquida a ~±49.5% en BTC → un drawdown como el ya visto en backtest sería liquidación. La palanca se gana con evidencia, no se asume. |
| **Funding modelado como costo diario obligatorio** | Rango realista ±11% anual a >100% anualizado en extremos, siempre en contra del lado "obvio". Un backtest de perps sin funding es mentira. Datos verificados: data.binance.vision publica funding histórico de los 10 majors desde ≤ sep-2020, sin API key ni geo-block. |
| **Historia extendida a ~oct-2020 (≈5.7 años, 6-8 folds)** | La ventana actual de 3 años es casi toda alcista → cualquier resultado sobre shorts sería estadísticamente vacío. El bear 2022 tiene que estar dentro de la validación. |
| **Todos los trials se registran ex-ante** | Con N configuraciones probadas, el mejor Sharpe esperado por azar crece con √(ln N) (Bailey-López de Prado). Lista cerrada de variantes antes de correr; nada de iterar hasta que dé lindo. |

## Variantes a validar (lista cerrada)

1. **V4 — Espejo gateado por régimen** *(candidata principal)*: BTC>SMA-200 → estrategia actual intacta (top-2 long sobre SMA-100). BTC<SMA-200 → prohibidos longs; short BTC y/o ETH si están bajo su SMA-100 y ret-30d<0, peso −0.25 c/u; si no, cash.
2. **V2 — TSMOM por activo** *(candidata secundaria)*: por cada major, long 1/10 si ret-30d>0 y sobre SMA-100; short 1/10 **solo BTC/ETH** si ret-30d<0 y bajo SMA-100; flat si mixto.
3. **V1 — Espejo simple** y **V3 — Market-neutral** *(controles, expectativa a priori: fallan)*: corren gratis con el mismo motor; V3 responde si existe spread cross-sectional neto entre 10 majors correlacionados.
4. **Overlays sobre la mejor variante** (y sobre la long-only actual): **vol targeting** (σ_target/σ_realizada-30d, cap 1) y **ensemble de lookbacks** (15/30/60/90d promediados). Evidencia: Barroso-Santa Clara, Moreira-Muir, réplica cripto FRL 2025 (Sharpe 1.12→1.42).

## Criterios de aceptación (fijados antes de correr)

Una variante **pasa** solo si, con funding y costos incluidos (0.15% conservador y 0.05% realista, reportados ambos):
- (a) folds positivos ≥ 6/8 (o ≥ 5/7 según partición final),
- (b) no degrada el Sharpe de la long-only validada en los sub-períodos bull,
- (c) la pata short es rentable **neta de funding** en los sub-períodos bear,
- (d) maxDD ≤ el de la long-only (~55%),
- (e) cero liquidaciones simuladas a palanca 1x.

Si ninguna variante pasa → **la long-only actual sigue siendo la estrategia**, y los overlays (vol targeting / ensemble) se evalúan sobre ella con los mismos criterios. "No encontramos edge en shorts" es un resultado válido y barato comparado con descubrirlo con plata real.

## Fases

- **Fase 0 — Datos** (~1 sesión): descarga y cache de klines de perps USDT-M + funding histórico desde oct-2020 (data.binance.vision bulk, fallback Bybit REST) para los 10 majors. Sanity checks: continuidad, agregación diaria de funding sin asumir 3×8h.
- **Fase 1 — Motor L/S** (~1 sesión): `validate_ls_momentum.py` extendiendo el framework actual: pesos con signo, funding como PnL diario, palanca como parámetro con liquidación simulada vía high/low, descomposición de PnL precio vs funding, exposición neta/gross, peor día.
- **Fase 2 — Validación** (~1 sesión): correr la lista cerrada de variantes + overlays, 6-8 folds, reporte comparativo contra long-only y buy&hold. **Gate: criterios de arriba.**
- **Fase 3 — Paper trading** (4+ semanas, solo si algo pasó el gate): segunda estrategia en el pipeline de GitHub Actions ya montado (tick diario propio, estado y reporte separados), corriendo en paralelo a la long-only. Comparación semanal automática en el informe dominical.
- **Fase 4 — Decisión real** (con el usuario, nunca antes de que Fase 3 valide): venue según mínimos de orden reales con $100 (verificar min notional vigente de Binance perps vs Hyperliquid — los informes difieren y puede haber cambiado), palanca 1x, shorts solo majors, kill-switch documentado.

## Qué NO está en el plan (y por qué)

- Predicción de dirección con XGBoost/ML — evidencia en contra, ver arriba. Revisable recién con 6-12 meses de track record y más capital, y solo como meta-labeling.
- Palanca >2x, shorts en alts, aumentar frecuencia de rebalanceo — cada uno tiene un modo de ruina documentado.
- Basis trade / market making ("lo de las ballenas") — no replicable con $100 (mínimos, latencia, capital dividido).
