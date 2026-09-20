# Prueba A/B/C/D/E: cinco construcciones de estrategia, un mercado, la misma vara

_20 sep 2026. Cinco agentes en paralelo, cada uno con un eje de estrategia distinto, backtesteados con walk-forward de 6 folds contiguos, 3 semillas, dos regímenes de costo (0.15% conservador / 0.05% realista por lado) y comparados contra buy&hold equiponderado y un baseline aleatorio de igual exposición bruta. Scripts en `backend/scripts/validate_{breakout,pairs,carry,tsmom_vt,ml_walkforward}.py`, 52 tests nuevos en `backend/tests/`, todos en verde (suite completa: 74/74)._

## Antes de leer los números: por qué son sintéticos

Este entorno de ejecución **no tiene salida de red hacia ningún exchange ni proveedor de datos** (Binance, Kraken, KuCoin, MEXC, Gate, Bybit, OKX, Hyperliquid y data.binance.vision devuelven 403 en el proxy de salida). `research.py` y `futures_data.py`, que usa el resto del repo para paper trading real, no pueden correr acá. Por eso las cinco pruebas corren sobre `backend/scripts/synthetic_market.py`, un generador de 10 activos con 6 años de velas diarias, calibrado para tener las propiedades estilizadas de cripto (vol 70-140% anualizada, correlación cruzada 0.5-0.7 vía un factor común tipo "BTC", colas gordas, régimen de tendencia de 130-250 días, reversión débil de corto plazo, 3 pares con spread cointegrado por construcción, funding correlacionado con momentum reciente).

**Esto mide estructura de construcción, no retorno esperado en cripto real.** El mercado sintético tiene un drift idiosincrático AR(1) con rho=0.985 (vida media ~46 días) deliberadamente persistente: es un entorno favorable para estrategias de tendencia y desfavorable para el descubrimiento de pares por correlación cruda, y los propios agentes lo señalan en sus veredictos. Los CAGR de cientos o miles de por ciento anualizado que aparecen abajo son un artefacto de esa calibración, no una proyección. El valor real de este ejercicio es: (a) verificar que cada construcción está bien implementada (sin lookahead, con costos, con walk-forward honesto) y (b) ver qué le pasa a cada una cuando el "juicio" que usa (una señal, un modelo, un filtro estadístico) es puesto a prueba fuera de muestra — la misma disciplina que exige `PLAN_FUTUROS.md` para cualquier estrategia antes de tocarla con plata real.

## Resultado en una tabla (semilla 42, costo realista 0.05%, agregado de los 6 folds)

| # | Construcción | Sharpe agregado | CAGR agregado | Max DD | vs buy&hold | vs random | Veredicto |
|---|---|---|---|---|---|---|---|
| A | Breakout Donchian 20/55 + ATR | **2.45** | +379% | 84.5% | +++ | +++ | Edge estructural real (tendencia), magnitud no creíble |
| B | Pairs trading (screening real) | **-1.62** | -35% | 92.4% | -- | **peor que random** | No encuentra edge; encuentra ruido |
| B' | Pairs trading (oráculo, 3 pares reales) | **+0.83** | +14% | 23.6% | + | + | El edge existe; el método no lo aísla |
| C | Carry de funding, dollar-neutral | **-4.43** | -93% | 100% | -- | -- | Apuesta direccional disfrazada, lo confirma |
| D | TSMOM absoluto + vol targeting (ensemble) | **4.98** | +566% | 33.8% | +++ | +++ | Edge estructural real (tendencia), magnitud no creíble |
| E | ML (logística) walk-forward honesto | **2.92** | +15.3% | 4.1% | + (Sharpe/DD) | +++ | Le gana a "persiste ayer"; contradice el prior de PLAN_FUTUROS **en este mercado estacionario** |
| E | ML (gradient boosting) walk-forward honesto | **2.01** | +13.8% | 6.3% | + (Sharpe/DD) | + | Igual dirección, más ruidoso que la logística |

Consistencia entre semillas (42/7/123, costo realista, Sharpe agregado):

| Construcción | seed 42 | seed 7 | seed 123 |
|---|---|---|---|
| A — Breakout | 2.45 | 2.92 | 3.65 |
| B — Pairs (screening) | -1.62 | -3.14 | -3.26 |
| B' — Pairs (oráculo) | 0.83 | 1.25 | 0.92 |
| C — Carry funding | -4.43 | -3.89 | -4.60 |
| D — TSMOM ensemble | 4.98 | 4.25 | 5.63 |
| E — ML logística | 2.92 | 2.70 | 4.46 |

Signo y orden de magnitud consistentes en las 3 semillas para las 6 filas: ninguna de estas conclusiones depende de una corrida con suerte.

## Qué construyó y qué encontró cada agente

### A — Ruptura de canal (Donchian dual 20/55) + sizing por ATR
Por activo, independiente: sistema dual estilo turtle (entra en ruptura de canal de 20 o 55 días), tamaño de posición = riesgo objetivo / ATR(14), trailing stop de 3×ATR. Bate a buy&hold y al aleatorio por márgenes enormes en las 3 semillas, incluida una (seed 7) donde buy&hold pierde plata y la estrategia igual gana. Los costos casi no importan (turnover bajo, posiciones de ~15-20 días), lo cual el propio agente marca como una prueba débil del edge: "sobrevive a costos" no discrimina mucho acá. El agente fue explícito en que **no optimizó** los parámetros sobre el resultado final (solo verificó a priori que el sizing no saturaba los caps) — es una limitación honesta, no una grilla de sensibilidad completa.

### B — Relative value / pairs trading, con y sin oráculo
La parte más informativa de las cinco pruebas. El agente construyó un screening walk-forward real (correlación de 250 días + half-life de AR(1) del spread, banda [5,90] días) sobre los 45 pares posibles, sin conocer de antemano cuáles son los 3 pares realmente cointegrados. Resultado: **el screening pierde, y pierde peor que un aleatorio con la misma exposición**. De 18 oportunidades (6 tramos × 3 semillas) encontró como máximo 1 de los 3 pares verdaderos por semilla, en total 3 de 18. La razón que documenta es concreta y trasladable a datos reales: la correlación cruda está dominada por el factor común de mercado (los pares con más beta a "BTC" siempre rankean primero), y el filtro de half-life no distingue una reversión de spread genuina de la deriva idiosincrática que **todos** los activos comparten por construcción. La versión oráculo (mismos 3 pares, sin problema de selección) sí bate a buy&hold en riesgo-ajustado con drawdown contenido (23-25%): el edge existe en el mercado sintético, el método de descubrimiento propuesto no lo aísla del ruido. Es exactamente el tipo de resultado que vale más que un "funciona": muestra dónde específicamente falla un enfoque razonable.

### C — Carry cross-sectional de funding, dollar-neutral
Cartera larga en los 3 activos de funding más negativo, corta en los 3 de funding más positivo, dollar-neutral, rebalanceo semanal. El agente hizo la descomposición correcta (precio vs funding, como `validate_ls_momentum.py`) y encontró algo genuinamente interesante: **el componente de funding es positivo y consistente en las 18 combinaciones fold×semilla** — la mecánica de cobrar funding funciona como debería — pero el componente de precio es negativo, también consistente, y ~3 veces más grande en magnitud. La razón: la señal de funding de 7 días es, en este mercado, un proxy del momentum reciente, y el mercado sintético tiene momentum mucho más persistente que reversión a ese horizonte. El agente verificó con un experimento de control (invertir el signo) que no es un bug de su código. Es la apuesta direccional disfrazada de carry que la prueba estaba diseñada para detectar, y la detectó — con el diagnóstico correcto de qué haría falta para separarla (ventana de funding más larga, o des-sesgar por nivel antes de rankear).

### D — Momentum de series de tiempo absoluto (TSMOM) + vol targeting en dos capas
A diferencia de la rotación top-2 ya validada en el repo, esta construcción invierte en los 10 activos simultáneamente según el signo de su propia tendencia, con vol targeting por activo y de portafolio. Reduce el max drawdown de ~90% (buy&hold) a 22-36% y sube el Sharpe en un orden de magnitud, en las 3 semillas, sin acercarse al cap de apalancamiento bruto (nunca superó 2.96 de un cap de 3.0). El ensemble de lookbacks {20,60,90,120} mejoró el Sharpe de forma consistente pero modesta frente a usar un solo L=90, y no redujo el drawdown de forma consistente — la literatura citada en `PLAN_FUTUROS.md` predice bien la dirección, no tanto la magnitud acá.

### E — Clasificador ML con walk-forward genuinamente expandiente
Logística y gradient boosting sobre un panel pooled de los 10 activos, reentrenado en cada uno de los 6 folds únicamente con historia estrictamente anterior (incluido el ajuste del scaler). Resultado inesperado dado el prior del repo: **ambos modelos le ganan de forma consistente a "persistir el signo de ayer"** (que es sistemáticamente negativo, Sharpe agregado -0.5 a -0.9 en las 3 semillas) y a un aleatorio calibrado a su misma exposición. El agente fue cuidadoso en explicar por qué esto **no contradice** la decisión de `PLAN_FUTUROS.md` de no usar ML en producción: el mercado sintético tiene una reversión de corto plazo y un drift persistente **estacionarios** durante los 6 años completos, justo el patrón lineal y estable que una logística detecta y que sigue vigente fold tras fold — lo que el paper de referencia de `PLAN_FUTUROS.md` (arXiv 2606.00060) documenta ausente en datos reales de perps, con ~2.000 observaciones efectivas y régimen no estacionario. Lo que este resultado confirma es que el pipeline de validación (walk-forward honesto + costos + baselines triviales) funciona y encuentra edge cuando el edge existe y es estable — no que el ML funcionaría igual en cripto real.

## Patrón que atraviesa las cinco pruebas

Las dos construcciones que "ganan" (A, D) explotan directamente la tendencia persistente que el generador sintético mete a propósito. Las dos que "pierden" (B, C) fallan por el mismo motivo en las dos: un filtro/señal calculado sobre un mercado con fuerte factor común y drift persistente termina confundiendo esa estructura de fondo con la señal específica que busca (cointegración genuina en B, carry genuino en C). E es el caso más sutil: gana, pero el propio agente identifica que gana por la razón "equivocada" para trasladar la conclusión a datos reales (estacionariedad que no existe en cripto real). Ninguna de las cinco pruebas debería leerse como "constrúyase esto para operar": la conclusión útil es que las cinco están bien construidas (sin lookahead, con costos, con walk-forward honesto, verificado por 52 tests) y que el proceso de descubrimiento importa tanto o más que la construcción misma — B lo demuestra en carne propia con su comparación oráculo vs. screening real.

## Qué haría falta para que esto responda algo sobre cripto real

Los cinco scripts ya están escritos contra el mismo framework (`backtest_common.py`) que usan `validate_momentum.py` y `validate_ls_momentum.py`. En cuanto el entorno tenga salida de red, correr `research.fetch_history` / `futures_data.build_matrices` en lugar de `synthetic_market.generate_market` y repetir exactamente los mismos folds y comparaciones es directo — ningún script necesita reescribirse, solo la fuente de datos. Ahí, y solo ahí, los números dejarían de ser sobre "qué encuentra la construcción en un mercado con tendencia persistente" para ser sobre "qué encuentra en cripto real".
