# Contexto completo de la sesión — 20 sep 2026

_Resumen para retomar el trabajo en otra sesión o con otro modelo. Rama: `claude/jev-poc-profit-analysis-f3u1h2` en `juanfcastropiccolo/trading-bots`. Todo lo descrito está commiteado y pusheado._

## 0. Estado del repo antes de la sesión

- Paper trading diario de momentum long-only (top-2 de 10 majors por retorno de 30 días, sobre SMA-100) corriendo vía GitHub Actions (`momentum-tick.yml`), equity ~$109 desde $100 el 12-jul-2026. Reporte en `PAPER_REPORT.md`.
- Variante long/short sobre perps validada en `validate_ls_momentum.py` (`PAPER_LS_REPORT.md`, `VALIDACION_LS.md`).
- `PLAN_FUTUROS.md`: criterios de aceptación ex-ante (folds positivos, costos 0.15%/0.05%, funding modelado, sin ML para dirección por la evidencia de arXiv 2606.00060).
- No existía ninguna POC de Jev en el repo (se buscó en todas las ramas e historial).

## 1. Pedido 1 — Analizar el paper/tweet de Jev y ver si "prenderlo" da profit

**Fuentes leídas.** PDF escaneado de 8 páginas ("How to Build a One-Person HFT Hedge Fund on Jev That Fires Calibrated Trades on Every Block 24/7"), leído como imágenes. Tweet de @RohOnChain (2101311813908652069) recuperado por búsqueda web (x.com bloqueado). Repos públicos clonados por git: `jarrodwatts/jev-trader` (el demo del tweet, TypeScript, Kuru MON-USDC en Monad), `justinhe16/trade-jev` (backtest Python con 22.401 respuestas reales de Jev sobre futuros NQ), `buberlo/jev-trader`, `aowang-ai/jev-trade`, `Anil-matcha/awesome-jev-by-typesafe`. SDK oficial `typesafe-sdk` 0.7.0 instalado desde PyPI e inspeccionado (`TypeSafeClient.system_one(state, questions)`, primitivos `Noul/Choice/Score`, base URL api.typesafe.ai).

**Qué es Jev.** Modelo "System One" de TypeSafe AI (lanzado 15-16 sep 2026): no genera texto; recibe un estado JSON y preguntas tipadas y devuelve probabilidades calibradas por RLCD en 70-500 ms, $0.042 por millón de tokens de entrada.

**Conclusión.** No, no valida que dé profit:
1. El paper es de arquitectura; no tiene ni un número de PnL. Dice textualmente que Jev "no crea edge: una estrategia sin edge pierde más rápido, no menos".
2. El demo del tweet pierde por construcción: cotiza $4.5 por bloque y paga gas cada bloque; su README muestra PnL negativo, el SPEC dice "the model is not trying to be profitable", el deploy corre en dry-run con modelo mock.
3. El único backtest con Jev real (`trade-jev`) pierde $128k en 15 días usando cada respuesta; llega a +$20k solo con filtros elegidos entre 1.920 configuraciones sobre los mismos días (sesgo de selección; random también fue positivo en el holdout).
4. Nuestra simulación: con órdenes de $4.5, el gas mata todo (kill switch en cualquier mercado, incluso con un juez del 99.7% de acierto); la política literal del paper nunca superó al piso mecánico de Avellaneda-Stoikov sin modelo.

**Implementado.** Paquete `backend/jev/` siguiendo el paper sección por sección: `state.py` (snapshot de 7 familias, ~115 tokens, causal), `battery.py` (6 preguntas; `JevJudge` real con typesafe-sdk, `RulesJudge`, `OracleJudge` calibrado con informatividad `a`, `DelayedJudge`), `policy.py` (`compose()` literal, Kelly fraccional, A-S, desvío opcional `pull_keep_reducing`), `risk.py`, `venue.py` (post-only con cola, gas, fees, competencia por el interior del spread), `loop.py` (deadline, escalera de fallback, triples de calibración), `calibration.py` (Brier/ECE/Platt), `feeds.py` (sintético `benigno`/`hostil`, grabador ccxt, replay jsonl). Scripts: `validate_jev_mm.py` (grilla → `JEV_REPORT.md`), `jev_record.py`, `jev_replay.py`. Docs: `JEV_ANALISIS.md`, `JEV_REPORT.md`. 22 tests en `backend/tests/test_jev.py`.

**Limitación.** Sin red hacia api.typesafe.ai ni exchanges: no se llamó a Jev real ni se grabaron datos reales. El siguiente paso real es grabar 1-2 h de un venue con `jev_record.py` desde una máquina con red, correr `jev_replay.py --mode always` y recién después `--judge jev` mirando calibración antes que PnL.

## 2. Pedido 2 — Cinco agentes, cinco estrategias (prueba A-E), backtest de cada una

**Restricción clave.** Este entorno bloquea TODOS los exchanges y proveedores de datos (Binance, Kraken, KuCoin, MEXC, Gate, Bybit, OKX, Hyperliquid, CoinGecko, data.binance.vision → 403 en el CONNECT del proxy; allowlist del entorno: solo Anthropic, GitHub y registros de paquetes). No hay cache de OHLCV en el repo. Por eso se construyó un **mercado sintético** (`backend/scripts/synthetic_market.py`: 10 activos, 6 años diarios, factor común tipo BTC con régimen bull/bear/crab, colas gordas, reversión débil de corto plazo, drift idiosincrático AR(1) rho=0.985, 3 pares cointegrados por ECM, funding correlacionado con momentum) y utilidades comunes (`backtest_common.py`: métricas, costos por turnover 0.15%/0.05%, folds contiguos, buy&hold, baseline aleatorio de igual exposición).

**Resultados (semilla 42, costo realista, Sharpe agregado; consistentes en 3 semillas):**

| Prueba | Construcción | Sharpe | Veredicto |
|---|---|---|---|
| A | Breakout Donchian 20/55 + ATR (`validate_breakout.py`) | +2.45 | Edge estructural de tendencia; magnitud de CAGR no creíble |
| B | Pairs trading con screening real (`validate_pairs.py`) | −1.62 | Pierde, peor que random: la correlación cruda la domina el factor común; encontró ≤1 de 3 pares verdaderos por semilla |
| B′ | Pairs con oráculo (3 pares reales) | +0.83 | El edge existe; el método de descubrimiento no lo aísla |
| C | Carry de funding dollar-neutral (`validate_carry.py`) | −4.43 | Funding positivo 18/18 folds, pero precio negativo y 3× mayor: apuesta direccional disfrazada |
| D | TSMOM absoluto en 10 activos + vol targeting (`validate_tsmom_vt.py`) | +4.98 | Max DD de ~90% a 22-36%; ensemble mejora Sharpe poco |
| E | ML logística / gboost walk-forward (`validate_ml_walkforward.py`) | +2.92 / +2.01 | Le gana a "persiste el signo de ayer", pero por estacionariedad del sintético; no contradice la política de no usar ML |

**Conclusión honesta.** Los datos fueron inventados (sintéticos). Tres de cinco dan profit en el mercado sintético, pero las que ganan explotan exactamente la tendencia persistente que el generador tiene a propósito. No valida rentabilidad real de ninguna. Lo que sí valida: código sin lookahead, con costos, walk-forward honesto (52 tests nuevos, 80 en total en verde), y un patrón instructivo de por qué fallan B y C. Reporte consolidado: `ESTRATEGIAS_ABCDE.md`.

## 3. Pedido 3 — Rearmar las cinco pruebas para datos reales y dejarlo listo para otro modelo

**Hecho.**
- `backend/scripts/market_data.py`: fuente única `load_market("synthetic"|"real")`, CLI común `--source / --cache-dir / --seeds`, sufijo `_real` en los resultados.
- Datos reales: klines 1d + funding de perpetuos USDT-M de Binance vía `futures_data.py` (bulk mensual de data.binance.vision, desde sep-2020, sin API key, sin geo-block en runners de GitHub), cache en `backend/data/cache/`.
- Los cinco `validate_*.py` aceptan `--source real`. Con real: una sola historia (semilla 42 solo para baseline aleatorio y random_state), la prueba B sin oráculo.
- `render_abcde_report.py --source real` → `ESTRATEGIAS_ABCDE_REAL.md` (consistencia medida por folds con Sharpe > 0).
- `run_abcde_real.sh`: descarga + cinco pruebas + reporte en un comando.
- `.github/workflows/abcde-real.yml` (workflow_dispatch): corre todo en un runner con red y commitea a la rama el cache de datos, los JSON `_real` y el reporte. Con el cache commiteado, cualquier sesión sin red puede re-correr las pruebas.
- `real_cache_fixture.py` + `tests/test_market_data.py`: cache con el formato exacto de `futures_data.py` para probar el camino real sin red. Las cinco pruebas corrieron de punta a punta sobre ese fixture en este entorno. Lo único no ejecutado acá es la descarga.

**Cómo ejecutarlo.**
1. GitHub → Actions → `abcde-real` → Run workflow (sobre esta rama). Recomendado.
2. Sesión de Claude o terminal con red: `pip install pandas numpy scikit-learn && bash backend/scripts/run_abcde_real.sh`.
3. A mano: `python backend/scripts/futures_data.py`, luego `python backend/scripts/validate_<prueba>.py --source real` ×5, luego `python backend/scripts/render_abcde_report.py --source real`.

**Verificación de acceso a APIs (dos veces, última al final de la sesión):** los 10 hosts bloqueados. Para que una sesión de Claude tenga red hay que crear el entorno de Claude Code on the web con acceso a internet habilitado (o allowlist con `data.binance.vision`): https://code.claude.com/docs/en/claude-code-on-the-web.

## 4. Advertencias para quien continúe

- Ningún parámetro de A-E fue optimizado sobre datos; si algo sale bien en real, no ajustar mirando ese resultado; revalidar en meses posteriores.
- Los CSV del cache real, una vez commiteados, no deben regenerarse con el fixture sintético (borrar `backend/data/*_results_real.json` producidos por fixture antes de correr en real; el workflow lo hace desde cero).
- `backend/data/` está en `.gitignore`; el workflow usa `git add -f` para el cache y los JSON `_real`.
- Entorno de desarrollo usado: venv en scratchpad con pandas, numpy, scikit-learn, ccxt, pytest, typesafe-sdk. El `pyproject.toml` tiene el extra opcional `jev` (typesafe-sdk).

## 5. Commits de la sesión (más nuevo arriba)

- `3e96e6a` feat(research): camino de datos reales para las pruebas A-E
- `a53792e` feat(research): prueba E (ML walk-forward) + reporte comparativo A-E
- `00671a4` feat(research): prueba B (pairs trading)
- `94e145a` feat(research): pruebas A, C, D
- `572c419` feat(research): mercado sintético multi-activo y utilidades de backtest
- `bb9ab1f` docs(jev): análisis del paper/tweet de Jev y reporte de la grilla
- `5edf31f` feat(jev): POC de market making con Jev como capa de juicio
