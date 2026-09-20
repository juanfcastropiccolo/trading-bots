# Jev como capa de juicio en un market maker por bloque: análisis e implementación

_20 sep 2026. Fuentes: el paper adjunto ("How to Build a One-Person HFT Hedge Fund on Jev That Fires Calibrated Trades on Every Block 24/7", 8 págs., escaneado), el tweet de @RohOnChain que lo difunde, el repo `jarrodwatts/jev-trader` (el demo del tweet), el backtest público `justinhe16/trade-jev` con respuestas reales de Jev, y el SDK oficial `typesafe-sdk` 0.7.0. La red del entorno bloquea x.com, docs.typesafe.ai y api.typesafe.ai; lo que no pude verificar de primera mano está marcado._

## Respuesta corta

**No, esto no valida que "prenderlo" dé profit.** Ni el paper ni el demo del tweet ni el único backtest público con Jev real muestran una estrategia rentable después de costos:

1. **El paper no tiene ni un número de PnL.** Es un paper de arquitectura (cómo dividir el sistema en cómputo determinístico y juicio probabilístico). Su propia conclusión lo dice: Jev "no crea edge: toma decisiones rápidas y baratas, pero una estrategia sin edge pierde más rápido, no menos" (Sección VIII.C).
2. **El demo del tweet pierde por construcción.** `jev-trader` cotiza una orden de 200 MON (~$4.5) por bloque y paga gas en cada bloque. Su propio README muestra `pnlUsd: -0.003` a los 3 bloques, el SPEC dice "el modelo no intenta ser rentable", y el issue #1 de un fork lo resume: "pierde una fracción de fee/spread en cada trade y se acumula". La versión desplegada corre en dry-run con el modelo *mock*, no con Jev.
3. **El único backtest con Jev real** (`trade-jev`, futuros NQ, 22.401 llamadas, 15 días) dice: actuando sobre cada respuesta, Jev pierde $128k en 15 días (peor que random). Con filtros elegidos entre **1.920 configuraciones probadas sobre los mismos 15 días** llega a +$20k; el propio autor lo llama "una pista para probar en datos nuevos, no un edge probado". En el holdout de 6 días, la política random también fue positiva (+$11k): fueron días de tendencia.
4. **Nuestra simulación** (abajo) muestra que con el tamaño de orden del demo el gas por transacción supera lo que captura un fill, y que la política literal del paper nunca superó al piso mecánico (Avellaneda-Stoikov sin juicio) en ninguno de los mercados sintéticos probados, ni siquiera con un juez casi perfecto.

Lo que sí es cierto y útil: Jev existe (TypeSafe AI, lanzado el 15-16 sep 2026), el SDK es real y barato ($0.042 por millón de tokens de entrada, salida gratis), y la arquitectura del paper (código calcula, modelo juzga, código veta) es la forma correcta de meter un modelo en un loop de trading. Eso es lo que implementé.

## 1. Qué dice el paper (y qué no)

| Sección | Contenido | Verificable |
|---|---|---|
| I-II | Jev es un "System One model": no genera texto; recibe un estado JSON y preguntas tipadas (Noul → probabilidad, Choice → distribución sobre ≤255 opciones, Score → nivel en rúbrica de 2-10) y devuelve todas las respuestas en un solo forward pass, 70-500 ms, con probabilidades calibradas por RLCD (Reinforcement Learning for Calibrated Decisions). | Sí: el SDK expone exactamente `Noul/Choice/Score` y `client.system_one(state, questions)`. La latencia y la calibración no las pude medir (API bloqueada). |
| III | Principio de división: mid, microprice, spread, imbalance, vol, inventario, drawdown y el precio de reserva de A-S son aritmética → código. Régimen, toxicidad del flujo, calidad del setup → juicio. Preguntas atómicas compuestas en código; se cambia un coeficiente, no un prompt. | Es una decisión de diseño, no un resultado. |
| IV | Motor de estado: snapshot de 7 familias, < 400 tokens, causal estricto (eq. 6), cada snapshot logueado con decisión y resultado. | Implementado; nuestro snapshot mide ~115 tokens. |
| V | Batería de 6 preguntas (regime, direction, toxic_flow, liquidity_stressed, quote_env, inventory_pressure) y `compose()`: vetos primero (drawdown → KILL, toxic > 0.6 → PULL, liquidez > 0.7 → WIDEN), después gate por confianza (quote_env ≥ 2 y conf > 0.8 → cotizar ambos lados), Kelly fraccional f = 0.25·max(0, 2p−1). | Implementado literalmente. |
| VI | Loop por bloque, precios A-S (eq. 8-9), regla de deadline (respuesta tardía → HOLD), escalera de fallback (Tabla V), restricción de gas ("cuando el costo por bloque supera el spread capturado, el loop está técnicamente vivo y económicamente muerto"). | Implementado. La restricción de gas es el punto que el demo del tweet viola. |
| VII | Riesgo con vetos duros; calibración con Brier/ECE (eq. 10-11), Platt; evaluación de 4 baselines (reglas / LLM / Jev / Jev + gate). | Implementado. |
| VIII | Costo: $10-25/mes de Jev + $15/mes de AgenKit. "Jev no crea edge". | A 240 tokens por llamada y una llamada por bloque 24/7 me da ~$3/día ($87/mes), no $10-25: el paper asume menos llamadas o snapshots más chicos. |

Nada en el paper es un resultado empírico de trading. No hay backtest, no hay track record, no hay tabla de PnL, no hay días de operación reportados. Las referencias [1]-[3] son el vendor; [9] es el repo del demo.

## 2. El tweet y el demo

Tweet (RohOnChain, 2101311813908652069): "Jev is the FASTEST AI model ever built for trading. It makes calibrated buy/sell decisions in under 100 ms. That is one real decision on every single block, 24/7. In this article I've shown EXACTLY how to build HFT trading system with Jev (from scratch)". El artículo es el PDF adjunto. La afirmación de velocidad es cierta (el demo mide p50 ≈ 100 ms de loop completo, 80 ms de inferencia); la de "HFT" es marketing: es market making a cadencia de bloque (300 ms), no HFT de microsegundos, y el propio paper lo aclara.

`jarrodwatts/jev-trader` (1.4k estrellas, TypeScript): cada bloque pregunta una sola cosa (Choice buy/sell sobre el movimiento a 100 bloques), postea una post-only de 200 MON un tick adentro del touch y cancela la anterior, en una transacción por bloque. Costos reales del evento de ejemplo del README: gas 0.0357 MON ≈ $0.0008 por tx, ~$10/hora si se transacciona cada bloque; Jev $0.000004 por decisión. Con órdenes de $4.5 el gas por transacción es 1.8 bps y la captura de spread por fill (spread 7 bps, un tick adentro) es de ~2.6 bps como máximo: hace falta casi un fill por transacción para empatar, y el demo se llena en una fracción chica de los bloques. El SPEC del repo lo declara: "Every block trades, so spread and gas bleed are visible", "the model is not trying to be profitable".

## 3. Evidencia externa con Jev real

`justinhe16/trade-jev` publica 22.401 respuestas reales de Jev (`results/*/answers.jsonl`) sobre el libro L10 de NQ:

| Configuración | PnL 15 días | Días positivos | Trades |
|---|---|---|---|
| Jev, cada respuesta | −$128.590 | 3/15 | 6.941 |
| Random | −$11.230 | 6/15 | — |
| Imbalance rule | −$21.820 | 4/15 | — |
| Jev + filtros (elegidos entre 1.920 combinaciones sobre esos mismos 15 días) | +$20.795 | 12/15 | 178 |

En la corrida "holdout11" (11 días, gate conf ≥ 0.5, 2 respuestas coincidentes, 120 s de hold): dev −$6.420 (Sharpe −3.2), holdout +$14.255, pero random en el mismo holdout +$11.445. Es ruido con sesgo de selección; el autor lo admite. Es exactamente el patrón que documentamos en `PLAN_FUTUROS.md` (Bailey-López de Prado): con N configuraciones, el mejor resultado esperado por azar crece con √ln N.

## 4. Qué implementé (`backend/jev/`)

Antes de esta sesión no había ninguna POC de Jev en el repo (busqué en todas las ramas y en el historial). Lo construí siguiendo el paper sección por sección, en Python, con la misma disciplina que los validadores de momentum:

| Módulo | Sección del paper | Qué hace |
|---|---|---|
| `state.py` | IV | `StateEngine`: ventanas rodantes O(1), snapshot de 7 familias (~115 tokens), guard de validez (sin warmup, libro vacío, no-finito → no se manda). |
| `battery.py` | V.A | Las 6 preguntas como `Noul/Choice/Score`; `JevJudge` (SDK real, timeout = deadline del bloque, cuenta tokens/costo/tardanzas); `RulesJudge` (heurísticas de libro, baseline y fallback); `OracleJudge` (posterior bayesiano exacto sobre los latentes del sintético, calibrado por construcción, informatividad `a`); `DelayedJudge` (baseline "LLM de frontera": mismo juicio, 3 s tarde). |
| `policy.py` | V.B-C, VI.A | `compose()` literal (vetos → gate → Kelly), modo `argmax` (sin calibración) y `always` (sin juicio); A-S en unidades de tick con inventario normalizado; post-only que nunca cruza el touch. Desvío opcional documentado: `pull_keep_reducing`. |
| `risk.py` | VII.A | Límites duros (posición, orden, pérdida diaria, drawdown, edad del inventario, datos viejos, tasa de errores, latencia). Recorta o veta; el KILL aplana. |
| `venue.py` | VI.B | Venue de papel: cola por nivel, fills contra prints reales, "el libro pasó a través" = nos tomaron, gas por transacción (batch cancel+post), fees maker/taker, competencia opcional por el interior del spread. |
| `loop.py` | VI, VII.C | El `on_block` del paper: fills → estado → snapshot válido → batería → compose → A-S → riesgo → post-only → log de triples con resultado resuelto a 100 bloques. Deadline y escalera de fallback. Descompone el PnL en spread capturado, mark-out a 20 bloques, gas, fees, costo del modelo. |
| `calibration.py` | VII.D | Brier, ECE, curva de confiabilidad, log-loss, Platt. |
| `feeds.py` | — | Mercado sintético (régimen de vol, episodios de flujo informado, prints informados con impacto, estrés de liquidez), presets `benigno` y `hostil`, grabador ccxt y replay jsonl. |

Scripts: `validate_jev_mm.py` (grilla de 4 baselines → `JEV_REPORT.md`), `jev_record.py` (graba libro+trades de un venue real), `jev_replay.py` (corre el loop sobre la grabación con reglas o con Jev real, imprime PnL y calibración, ajusta Platt). Tests: `backend/tests/test_jev.py` (22 tests: causalidad y tamaño del snapshot, vetos antes que señales, Kelly, A-S, post-only con cola, calibración, consistencia outcome/verdad, deadline, kill switch, parser del SDK).

## 5. Resultados de la simulación

Ver `JEV_REPORT.md` para las tablas completas. Resumen:

Corrida de 48.000 bloques (4 h simuladas) por configuración, bankroll $100, órdenes de 200 unidades, inventario máximo 400, 3 semillas para las filas principales.

**Estructura de costos (aritmética, sin simulación).** En Kuru MON-USDC con órdenes de $4.5 el gas es 1.78 bps por transacción y la captura máxima por fill ~2.65 bps: hace falta 0.67 fills por transacción para empatar, y el demo transacciona cada bloque. Con órdenes de $100 el gas cae a 0.08 bps por tx y deja de ser el problema.

**Grilla (PnL neto en 4 h, USD sobre $100).** Columnas: piso mecánico (A-S sin juicio), reglas, LLM tardío, Jev por argmax, Jev con la política del paper (a = 1 / 2 / 4) y la misma política con `pull_keep_reducing` (a = 4).

| Mercado | Venue | always | rules | llm-stale | jev-argmax | jev-gated a=1 / 2 / 4 | jev-gated+r a=4 |
|---|---|---|---|---|---|---|---|
| benigno | ideal | +19.6 | +12.8 | +1.2 | +8.9 | +0.0 / +1.8 / +2.8 | +7.9 |
| benigno | kuru_demo ($4.5, gas real) | −1.9 | −11.8 | −15.0 (kill) | −9.3 | −15.0 / −15.0 / −15.0 (kill) | −15.0 (kill) |
| benigno | kuru_x20 (órdenes 20× más grandes) | +18.5 | +11.6 | +0.1 | +8.0 | −1.2 / +0.7 / +1.9 | +6.7 |
| benigno | perp_cex (maker 1.5 bps) | +9.7 | +5.5 | −0.6 | +3.3 | −1.1 / −0.0 / +0.7 | +3.8 |
| hostil | ideal | −0.6 | −1.8 | −3.9 | −4.2 | −3.0 / −2.3 / −2.0 | −1.1 |
| hostil | kuru_demo | −15.0 (kill) | −15.0 (kill) | −15.0 (kill) | −15.0 (kill) | kill / kill / kill | kill |
| hostil | kuru_x20 | −1.9 | −3.3 | −5.0 | −5.2 | −4.4 / −3.5 / −3.0 | −2.5 |
| hostil | perp_cex | −4.7 | −4.7 | −4.6 | −6.5 | −3.6 / −3.1 / −2.8 | −3.0 |

Variabilidad entre semillas (venue ideal): `always` benigno +17.1 / +19.6 / +23.9, hostil −1.7 / −0.6 / +1.0; `jev-gated(a=2)` benigno +1.8 / +3.3 / +1.8, hostil −2.3 / −2.3 / −2.7. Las diferencias entre políticas son mayores que el ruido entre semillas.

Lo que muestran los números:

1. **Con el tamaño de orden del demo, todo pierde y el kill switch salta** (drawdown 15%) en las 4 h, en cualquier mercado y con cualquier juez, incluido el casi perfecto (a = 4, 99.7% de acierto en toxicidad). El gas manda: $13-22 de gas contra $1-8 de spread capturado. Es la "restricción de gas" de la Sección VI.E del paper, que el demo del tweet viola.
2. **La política literal del paper nunca superó al piso mecánico**, ni en el mercado benigno (+1.8 vs +19.6) ni en el hostil (−2.3 vs −0.6), con ningún nivel de calidad de juicio. El motivo se ve en la descomposición: la política solo usa el juicio para abstenerse (pull, stand-down, cotizar ancho); abstenerse no genera spread, y "cotizar ancho" (detrás del touch) solo se llena cuando el precio pasa a través, que es exactamente el fill adverso. Además `PULL_QUOTES` saca ambos lados y deja el inventario expuesto durante el episodio tóxico.
3. **El único cambio que ayudó no está en el paper**: mantener el lado que reduce inventario durante el pull (`pull_keep_reducing`) casi cuadruplica el resultado de la política (+1.8 → +7.0 en benigno; −2.3 → −1.6 en hostil), pero sigue por debajo de cotizar siempre.
4. **La calidad del juicio importa poco frente a la estructura de la política**: pasar de a = 1 a a = 4 (de 77% a 99.7% de acierto) mueve el PnL de +0.0 a +2.8 en benigno y de −3.0 a −2.0 en hostil. La calibración se mide bien (ECE del oráculo 0.001-0.005, del juez de reglas 0.16-0.32): el pipeline de la Sección VII funciona y está listo para evaluar un Jev real.
5. **El baseline "LLM tardío" (misma calidad, 3 s tarde) es el peor de los que cotizan** en el mercado hostil (−3.9 vs −2.3 del mismo juicio a tiempo): la latencia sí cuesta, como dice el paper, pero eso no convierte al modelo rápido en rentable.
6. **En el mercado hostil (selección adversa fuerte, competencia por el interior del spread) nada es rentable**, tampoco con fees de CEX (−2.8 a −6.5). Si el venue real se parece a esto, un maker de $100 no tiene lugar; si se parece al benigno, el mejor uso del capital es el A-S sin modelo.

Limitaciones de la simulación, para que nadie lea esto como un PnL esperado: el mercado no reacciona a nuestras órdenes; los prints no informados solo ocurren en el touch; la competencia por el interior del spread es un parámetro, no un mercado; la calidad del juicio es un oráculo sobre latentes que en un venue real no existen como tales. El sentido de estos números es estructural: cuánto cuesta el gas, qué hace la política con un juicio dado, y que la infraestructura de medición funciona.

## 6. Qué haría falta para responder la pregunta de verdad

La simulación no puede decir cuánto gana o pierde esto en un venue real; sí dice qué hay que medir. El camino, en orden y con lo ya implementado:

1. **Grabar datos del venue candidato** (`jev_record.py`, 1-2 horas de libro + prints a 1 s). Sin datos reales ninguna conclusión de PnL vale.
2. **Correr el piso mecánico** sobre la grabación (`jev_replay.py --mode always`) con los costos reales del venue. Si el maker ingenuo pierde antes de costos, el mark-out por fill supera la captura de spread y hay lugar para que un juicio ayude; si gana, cualquier gate solo le quita volumen.
3. **Correr Jev real** sobre la misma grabación (`--judge jev`, ~$0.01 por hora de datos) y mirar primero la calibración por pregunta (Brier/ECE), no el PnL. El paper es explícito: la calibración de RLCD es contra la distribución del vendor; en tu venue hay que verificarla y, si hace falta, ajustar Platt antes de dimensionar.
4. **Comparar las cuatro baselines sobre los mismos datos y costos**, con la lista de configuraciones fijada de antemano (como en `PLAN_FUTUROS.md`). Sin eso se repite el error de `trade-jev`.
5. Recién con eso, paper trading en vivo con kill switch, y recién después capital.

Para nuestro bankroll de $100: el gas de Monad hace inviable el demo tal cual; un perp en un CEX con fee maker (1.5 bps en Hyperliquid) exige capturar más que eso por fill neto de selección adversa, lo que en BTC (spread ~1 bp) es imposible para un maker chico y en pares menos líquidos es una pregunta empírica que solo los datos grabados responden.
