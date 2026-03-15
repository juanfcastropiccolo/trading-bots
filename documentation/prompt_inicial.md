Spec — Crypto Trading Agents Mission Control (local-first)
1) Objetivo del sistema

Construir un sistema local de trading cripto compuesto por:

un Mission Control accesible desde localhost,

uno o varios agentes de trading autónomos,

un backend en Python,

un frontend en TypeScript,

integración inicial con Binance,

y una capa de razonamiento asistida por LLM bajo control estricto.

El sistema debe permitir arrancar con un solo agente y luego escalar a varios, por ejemplo:

1 agente = 1 activo/mercado,

1 presupuesto acotado por agente, por ejemplo 10 USD,

monitoreo en tiempo real de balance, señales, operaciones, PnL y decisiones,

posibilidad futura de ajustar estrategias desde el Mission Control.

2) Qué problema resuelve

El sistema busca resolver tres problemas al mismo tiempo:

A. Operación autónoma continua

Que el usuario no tenga que estar mirando el mercado todo el día para ejecutar entradas/salidas.

B. Experimentación ordenada

Poder testear hipótesis de trading con capital pequeño, con trazabilidad completa y sin improvisación.

C. Observabilidad total

Tener una interfaz local que permita entender:

qué hizo cada agente,

por qué lo hizo,

cuánto ganó/perdió,

cuánto costó el LLM,

y qué estrategia estaba activa en cada momento.

3) Principios rectores
3.1. Local-first

Todo debe correr en la computadora del usuario en una primera etapa.

Por qué:
Porque el objetivo inicial no es escalar infraestructura sino aprender, iterar rápido, bajar costo y tener control total del sistema.

3.2. Riesgo acotado por diseño

Cada agente debe tener un capital máximo asignado y reglas estrictas de riesgo.

Por qué:
Porque dejar a un LLM operar sin límites es una mala práctica técnica y financiera.

3.3. El LLM no debe tener control irrestricto

El LLM puede ayudar a razonar, resumir contexto, sugerir ajustes o elegir entre estrategias habilitadas, pero la ejecución debe pasar por una capa determinística de validación.

Por qué:
Porque un LLM no es un motor de ejecución confiable por sí mismo. Puede hallucinar, sobreoperar, o ignorar restricciones. La ejecución debe estar gobernada por reglas duras.

3.4. Primero paper trading, luego live opcional

El sistema debe soportar ambos modos, pero el modo por defecto debe ser paper trading.

Por qué:
Porque antes de arriesgar dinero real hay que validar:

latencia,

fees,

slippage,

filtros del exchange,

calidad de estrategia,

y estabilidad del sistema.

3.5. El objetivo no es “maximizar billetera” sin contexto

El objetivo correcto es maximizar retorno ajustado por riesgo dentro de límites claros.

Por qué:
Porque “maximizar la billetera” a secas empuja al sistema a sobreoperar y asumir riesgo excesivo.
El sistema debe optimizar con restricciones, no perseguir crecimiento ciego.

4) Alcance de la primera versión (V1)

La V1 debe incluir:

Funcional

1 a 4 agentes configurables.

Cada agente asociado inicialmente a 1 símbolo.

Presupuesto independiente por agente.

Mission Control local con dashboard en tiempo real.

Streaming de datos de mercado.

Señales basadas en indicadores técnicos.

Bitácora de decisiones.

Modo paper trading.

Modo live deshabilitado por defecto.

Registro de costos de uso del LLM.

Configuración manual de estrategias y parámetros.

No funcional

correr localmente,

tolerancia razonable a reinicios,

logs persistentes,

trazabilidad de toda operación,

capacidad de replay para auditoría.

5) No objetivos de la V1

Esto no debe estar en la primera versión:

optimización automática avanzada por reinforcement learning,

uso de visión para “leer gráficos” como fuente principal de decisión,

estrategias multi-leg complejas,

arbitraje entre exchanges,

hosting cloud,

app mobile,

autoajuste libre del riesgo por parte del LLM,

promesas de rentabilidad.

6) Decisiones de stack y por qué
6.1 Backend: Python
Decisión

Usar Python como backend principal.

Por qué

Es el lenguaje más natural para:

trading cuantitativo,

data analysis,

indicadores,

backtesting,

integración con librerías de exchange,

y uso de LLMs.

Permite construir rápido sin perder legibilidad.

Tiene ecosistema maduro para series temporales y estrategia.

6.2 API backend: FastAPI
Decisión

Usar FastAPI para exponer APIs y WebSockets al frontend.

Por qué

Es liviano, rápido y muy bueno para servicios locales.

Permite:

endpoints REST,

streaming por WebSocket,

tipado claro,

documentación automática,

y separación limpia entre módulos.

6.3 Frontend: React + TypeScript + Vite
Decisión

Usar React + TypeScript con Vite.

Por qué

El objetivo del front es un dashboard técnico, no una web pública SEO-driven.

Vite reduce complejidad respecto de Next.js en esta etapa.

TypeScript mejora mantenibilidad del panel y del estado en tiempo real.

Permite un desarrollo muy rápido del Mission Control local.

Nota: Next.js puede evaluarse más adelante si el dashboard migra a una versión remota o más producto.

6.4 Visualización de mercado
Decisión

Usar librerías especializadas de charting para velas y series temporales.

Por qué

El humano sí necesita ver gráficos.

Pero el agente no debería razonar sobre screenshots del gráfico.

El backend debe trabajar con datos estructurados e indicadores numéricos.

Principio clave:
los gráficos son para observabilidad humana; las decisiones del sistema deben basarse en features estructuradas.

6.5 Persistencia local
Decisión

Usar una base local liviana, inicialmente SQLite.

Por qué

cero infraestructura,

portable,

suficiente para:

configuraciones,

operaciones,

snapshots,

decisiones,

logs,

métricas,

eventos de agente.

6.6 Orquestación
Decisión

No usar n8n como núcleo del loop de trading.

Por qué

El loop de trading requiere:

estado compartido,

latencia baja,

validaciones internas,

control fino sobre concurrencia y retries.

n8n puede ser útil después para:

alertas,

emails,

Slack,

reporting,

resúmenes periódicos.

Pero el motor central de trading debe vivir en Python.

6.7 Exchange abstraction
Decisión

Diseñar el sistema con una capa de abstracción de exchange desde el día 1.

Por qué

Aunque Binance sea el exchange inicial, el core no debe quedar acoplado a Binance.
Debe existir una interfaz tipo:

get_market_data()

get_balance()

place_order()

cancel_order()

get_open_orders()

get_symbol_filters()

Esto permite cambiar exchange en el futuro sin reescribir todo.

7) Arquitectura conceptual

El sistema debe tener estas piezas:

7.1 Data Ingestion

Responsable de:

obtener OHLCV,

precio actual,

volumen,

order book básico,

estado de cuenta,

historial de órdenes,

y actualizaciones en streaming.

7.2 Feature Engine

Calcula features como:

retornos,

volatilidad,

EMAs,

RSI,

Bollinger Bands,

ATR,

volumen relativo,

momentum,

drawdown reciente.

7.3 Strategy Engine

Genera señales determinísticas a partir de reglas definidas.

Ejemplos de familias iniciales:

trend following,

mean reversion,

breakout.

7.4 LLM Reasoner

No ejecuta directamente.
Su rol es:

sintetizar contexto,

interpretar régimen de mercado,

justificar señales,

elegir entre estrategias preaprobadas,

proponer ajustes acotados,

resumir post-trade lessons.

7.5 Risk Manager

Valida todo antes de ejecutar:

tamaño máximo de posición,

stop loss,

take profit,

drawdown máximo por agente,

número máximo de operaciones,

exposición simultánea,

cooldown entre trades.

7.6 Execution Engine

Convierte decisiones válidas en órdenes concretas.

7.7 Portfolio / Agent Manager

Mantiene el estado de cada agente:

cash disponible,

posición,

equity,

PnL,

estrategia activa,

métricas de performance,

estado operativo.

7.8 Event Store / Audit Log

Registra:

señal generada,

features usadas,

razonamiento del LLM,

validación de riesgo,

orden emitida,

fill,

resultado,

error,

costo del modelo.

7.9 Mission Control API

Expone los datos al frontend.

7.10 Mission Control UI

Permite visualizar y operar el sistema localmente.

8) Modelo operativo de cada agente

Cada agente debe seguir un ciclo claro:

consume market data,

actualiza features,

evalúa señales base,

construye un snapshot estructurado,

opcionalmente consulta al LLM,

pasa por Risk Manager,

ejecuta o rechaza,

persiste todo,

actualiza dashboard,

revisa performance post-trade.

Regla crítica

El agente nunca debe:

inventar activos,

saltarse filtros del exchange,

operar fuera de su presupuesto,

ignorar el Risk Manager.

9) Filosofía de estrategia
9.1 Qué no hacer

No construir desde el inicio un sistema donde el LLM “mira el gráfico y decide”.

Por qué no:

es más caro,

menos reproducible,

menos trazable,

más frágil,

y mucho más difícil de depurar.

9.2 Qué sí hacer

Construir primero una base cuantitativa simple y fuerte.

Estrategias iniciales sugeridas para V1
A. Trend following simple

EMAs de corto y largo plazo,

filtro por RSI,

confirmación por volumen.

B. Mean reversion simple

bandas de Bollinger,

RSI en extremos,

rechazo de trades contra volatilidad extrema.

C. Breakout simple

ruptura de rango,

confirmación por volumen,

stop claro.

Por qué empezar por ahí

Porque permiten:

hipótesis claras,

trazabilidad,

comparación entre agentes,

backtesting simple,

y aprendizaje incremental.

10) Rol correcto del LLM

El LLM no debe ser “el trader” puro.
Debe ser un cerebro asesor acotado.

Funciones permitidas del LLM

resumir el contexto reciente,

describir el régimen del mercado,

priorizar entre estrategias habilitadas,

explicar por qué una señal podría tener más o menos calidad,

ajustar umbrales dentro de rangos permitidos,

redactar reasoning y post-mortems,

detectar patrones narrativos en historial del agente.

Funciones prohibidas del LLM

enviar órdenes sin pasar por validación,

modificar risk limits,

redefinir el capital por agente,

crear estrategias fuera del set permitido,

operar cuando faltan datos,

operar por intuición textual sin respaldo de features.

Por qué esta separación

Porque así el sistema combina:

creatividad contextual del LLM,

con disciplina ejecutiva determinística.

11) Objetivos cuantitativos del sistema

El sistema debe medir performance con métricas serias.

Métricas mínimas por agente

equity actual,

PnL realizado,

PnL no realizado,

win rate,

average win,

average loss,

profit factor,

max drawdown,

número de trades,

average holding time,

fees acumuladas,

costo acumulado de inferencia LLM,

retorno neto luego de fees.

Métricas de sistema

equity agregada,

ranking de agentes,

uptime,

errores por módulo,

latencia de señales,

latencia de ejecución,

costo por decisión del LLM.

Nota importante

El objetivo de “duplicar semanalmente” no debe codificarse como una expectativa del sistema.

Por qué:
Porque no es una meta realista ni estable para ingeniería.
Puede existir como benchmark aspiracional de experimento, pero no como supuesto operativo.

12) Gestión de riesgo

Esto debe ser una parte central, no un agregado.

Reglas mínimas

capital máximo por agente configurable,

tamaño máximo por trade,

máximo porcentaje del capital comprometido por posición,

stop loss obligatorio o criterio equivalente,

take profit o cierre por señal inversa,

límite diario de pérdida,

pausa automática luego de N pérdidas consecutivas,

máximo número de operaciones por ventana temporal,

bloqueo si faltan datos críticos.

Por qué

Porque el valor del sistema no está solo en entrar bien, sino en sobrevivir.

13) Mission Control — funcionalidades
13.1 Vista general

Debe mostrar:

estado de todos los agentes,

símbolo de cada uno,

estrategia activa,

cash,

equity,

PnL diario,

PnL total,

drawdown,

último trade,

estado del loop,

estado del exchange,

gasto del LLM.

13.2 Vista por agente

Debe mostrar:

gráfico del activo,

markers de buy/sell,

posición actual,

historial de trades,

reasoning más reciente,

parámetros activos,

métricas del agente,

eventos recientes,

errores o rechazos de órdenes.

13.3 Laboratorio de estrategia

Debe permitir:

activar/desactivar estrategias habilitadas,

tocar parámetros dentro de rangos,

cambiar timeframe,

cambiar modo paper/live,

resetear agente,

clonar configuración a otro agente.

13.4 Auditoría / eventos

Debe existir una sección de log detallado:

market snapshot,

señal,

reasoning,

validación de riesgo,

orden,

fill,

error,

fallback.

13.5 Observabilidad del LLM

Debe mostrarse:

modelo usado,

cantidad de llamadas,

tokens aproximados,

costo acumulado,

costo por agente,

costo por decisión.

14) Modos de operación
14.1 Paper Mode

Modo default.
No envía órdenes reales.

14.2 Live Mode

Modo manualmente habilitable.
Debe exigir confirmación explícita.

14.3 Replay Mode

Modo para reinyectar historial y revisar decisiones.

Por qué incluir Replay:
Porque acelera debugging, aprendizaje y post-mortem.

15) Diseño de datos mínimos

La persistencia local debe contemplar al menos entidades como:

agents

agent_configs

market_snapshots

features

signals

llm_decisions

risk_checks

orders

fills

positions

portfolio_snapshots

strategy_runs

system_events

model_usage_costs

Cada evento importante debe tener:

timestamp,

agent_id,

symbol,

payload estructurado,

status,

source.

16) Flujo de decisión recomendado
Entrada

precio

OHLCV

volumen

features técnicas

estado del portafolio

contexto reciente del agente

Proceso

strategy engine produce hipótesis de señal,

se arma un resumen estructurado,

el LLM comenta o selecciona entre opciones permitidas,

risk manager aprueba o rechaza,

execution engine ejecuta o simula,

se registra todo,

se actualiza la UI.

Salida

trade ejecutado o rechazado,

reasoning persistido,

dashboard actualizado,

métricas recalculadas.

17) Criterios de calidad para la implementación

La implementación que haga Claude Code debe cumplir con esto:

Claridad

Código modular y fácil de seguir.

Trazabilidad

Ninguna orden sin log asociado.

Separación de responsabilidades

data ingestion ≠ strategy ≠ LLM ≠ risk ≠ execution ≠ UI

Configuración explícita

Todo lo sensible debe estar en config:

capital,

símbolos,

timeframes,

thresholds,

modelo LLM,

frecuencia del loop.

Fail-safe

Ante error:

no operar,

loggear,

exponer error en UI,

permitir retry controlado.

18) Roadmap recomendado
Fase 1 — Núcleo local sin live trading

FastAPI

React + TS + Vite

1 agente

market data

indicadores

señales determinísticas

Mission Control básico

SQLite

paper trading

Fase 2 — LLM acotado

agregar reasoning del LLM,

logs explicativos,

costo por llamada,

selección entre estrategias habilitadas.

Fase 3 — Multi-agent

2 a 4 agentes,

distintos símbolos,

vista comparativa,

presets de configuración.

Fase 4 — Live opcional

sólo luego de pasar validación mínima en paper,

con límites duros y switch manual.

19) Preguntas de diseño que deben guiar el desarrollo

Estas preguntas son importantes porque atacan justamente los “porqués”:

Sobre estrategia

¿Qué hipótesis concreta intenta capturar cada estrategia?

¿En qué régimen de mercado funciona mejor?

¿Qué invalida esa estrategia?

Sobre LLM

¿Qué tarea hace mejor el LLM que una regla fija?

¿Qué tareas jamás debería hacer el LLM?

Sobre riesgo

¿Cuál es el peor comportamiento posible del sistema?

¿Qué guardrails lo bloquean?

Sobre producto

¿Qué información necesita ver el usuario para confiar en el agente?

¿Qué explicaciones necesita para entender un mal trade?

Sobre ingeniería

¿Qué parte debe ser determinística?

¿Qué parte puede ser probabilística?

¿Qué parte debe ser reproducible al 100%?

20) Supuestos explícitos

El sistema correrá localmente.

No se considerará cloud en esta etapa.

El usuario aportará credenciales del exchange y de OpenAI vía variables de entorno.

El capital por agente será pequeño y configurable.

El sistema debe servir primero para aprender, observar y validar, no para prometer rentabilidad inmediata.

La operativa real sólo tendrá sentido después de una etapa de paper trading consistente.

21) Riesgos del proyecto
Riesgos técnicos

latencia,

reconexión de streams,

rate limits,

inconsistencias entre datos y ejecución,

drift de estrategia,

sobrecosto del LLM.

Riesgos de producto

falsa sensación de autonomía,

exceso de confianza en el agente,

dashboards lindos pero poco útiles.

Riesgos financieros

fees y slippage comiéndose el edge,

capital demasiado pequeño para ciertos pares,

sobreoperación,

drawdowns rápidos en mercados altamente volátiles.

22) Definición de éxito de la V1

La V1 será exitosa si logra esto:

correr estable localmente,

mostrar un Mission Control claro,

operar en paper sin romperse,

registrar todas las decisiones,

comparar al menos 2 enfoques de estrategia,

usar el LLM de forma útil pero acotada,

dejar una base limpia para pasar a live luego.

23) Apartado explícito — Investigación externa pendiente

Este bloque queda abierto a completar antes o durante la implementación.

23.1 Binance / exchange

Buscar y validar externamente:

documentación oficial de market data,

documentación oficial de trading,

soporte de testnet / sandbox,

websockets disponibles,

filtros por símbolo:

min qty,

min notional,

tick size,

step size,

fees maker/taker,

límites de rate,

restricciones por IP,

uso de múltiples bots o múltiples API keys,

manejo de reconexiones,

restricciones de ciertas monedas o mercados.

23.2 Librería o integración de exchange

Evaluar externamente:

si conviene usar una librería tipo abstracción de exchange,

o integración directa contra Binance.

Preguntas:

¿qué opción ofrece mejor control?

¿qué opción ofrece mejor velocidad de desarrollo?

¿qué opción simplifica testnet y órdenes?

23.3 Estrategias cuantitativas para cripto

Investigar externamente:

qué estrategias simples tienen mejor sentido para mercados cripto,

en qué timeframes,

cómo afectan fees/slippage,

qué indicadores son más robustos,

cuándo falla trend following,

cuándo falla mean reversion,

cómo detectar regímenes de volatilidad.

23.4 Referentes y fundamentos

Investigar externamente autores/fuentes para construir criterio, no copiar recetas.

Líneas a investigar:

análisis técnico clásico,

microestructura de mercado,

gestión de riesgo,

crypto-specific trading.

23.5 Viabilidad de capital pequeño

Validar externamente:

si 10 USD por agente es viable para los pares elegidos,

cuánto impactan fees y mínimos operativos,

qué símbolos tienen suficiente liquidez para pruebas pequeñas.

23.6 LLM cost control

Investigar externamente:

costo real por decisión según modelo,

frecuencia máxima razonable de consultas,

posibilidad de usar LLM sólo en ciertos eventos,

alternativas más económicas para reasoning liviano.

23.7 Aspectos legales / impositivos

No para resolver ahora, pero sí dejar marcado:

implicancias fiscales,

registro de operaciones,

trazabilidad necesaria si luego escala.

24) Instrucción de implementación para Claude Code

Claude Code debe implementar el sistema respetando estas reglas:

local-first,

paper trading por defecto,

backend Python + FastAPI,

frontend React + TypeScript + Vite,

persistencia local,

Mission Control con métricas y gráficos,

agentes con presupuesto fijo,

LLM acotado por guardrails,

execution separada de reasoning,

logs completos,

arquitectura modular,

diseño preparado para más de un agente.

Además, debe priorizar:

legibilidad,

trazabilidad,

seguridad operativa,

y facilidad para iterar.

Esta spec ya está en un nivel bastante bueno para transformarla en un prompt maestro para Claude Code. En el próximo paso te lo convierto directamente en formato de prompt operativo.