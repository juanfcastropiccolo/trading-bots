Rol: Eres un Staff Full-Stack Engineer y Quantitative Developer experto en Python (FastAPI, CCXT, Google ADK), bases de datos locales (SQLite) y TypeScript (React, Vite, Tailwind).

Objetivo: Construir la Versión 1 (MVP) de un "Crypto Trading Agents Mission Control". Es un sistema local-first de trading algorítmico donde la ejecución es 100% determinística y un LLM actúa únicamente como un asesor/razonador acotado, todo orquestado mediante el Google Agent Development Kit (ADK).

Principios Arquitectónicos (Innegociables):

Local-first: Todo corre en localhost.

Paper Trading ONLY: Esta V1 no se conectará a endpoints de dinero real. Usa datos de mercado reales (Binance Spot) pero simula las ejecuciones localmente.

Ejecución Determinística con ADK: El LLM NUNCA ejecuta trades directamente. El core del loop debe orquestarse con google-adk separando responsabilidades: herramientas/nodos matemáticos (Strategy Engine, Risk Manager) y un LlmAgent secundario solo para "reasoning" y resumen de contexto.

Stack Tecnológico:

Backend: Python 3.11+, FastAPI (REST + WebSockets), SQLite (persistencia), CCXT (para market data de Binance), Pandas/TA-Lib (para features), google-adk (para orquestación y observabilidad del agente).

Frontend: React, TypeScript, Vite, TailwindCSS, Lightweight-charts (dashboard).

Alcance del MVP (V1):

1 Agente operando 1 símbolo (ej. BTC/USDT).

Presupuesto simulado de $100 USD.

1 Estrategia activa: Trend Following simple (Cruces de EMA + filtro RSI).

Loop de 1 minuto orquestado por ADK: Obtener OHLCV -> Calcular Features -> Evaluar Estrategia -> Consultar LLM Reasoner -> Risk Manager -> Simular Trade -> Guardar DB -> Emitir WebSocket.

Plan de Ejecución Paso a Paso:
Implementa esto en los siguientes pasos secuenciales. Espera mi confirmación explícita (diciendo "continúa") antes de avanzar al siguiente paso.

Paso 1: Scaffolding y Base de Datos (SQLite)

Crea la estructura: /backend y /frontend.

Diseña los modelos SQLAlchemy: AgentConfig, MarketSnapshot, Signal, LLMDecision, Order (simulada), Position.

Paso 2: Data Ingestion & Feature Engine (Python)

Servicio con ccxt para descargar velas de 1m de Binance.

Implementa el cálculo de EMA (rápida/lenta) y RSI sobre Pandas.

Paso 3: Orquestación con Google ADK (El Núcleo)

Instala google-adk.

Crea un workflow estructurado (ej. extendiendo BaseAgent o usando un SequentialAgent de ADK) que controle el ciclo de vida del tick.

Integra el StrategyEngine (Cruces EMA + RSI) y el RiskManager (Límite de max $10 USD por trade) como pasos determinísticos en el flujo de ADK.

Usa un LlmAgent de ADK solamente para recibir el snapshot (Precio, EMAs, RSI, Señal generada) y devolver un JSON con un "reasoning" corto (justificación de la acción). Configura el tracing de ADK para auditar esto.

Integra la simulación de la orden actualizando la base de datos SQLite.

Paso 4: FastAPI & WebSockets

Expón endpoints REST para consultar el estado del agente y el PnL.

Crea un WebSocket que emita el estado de cada ciclo orquestado por el agente ADK hacia el frontend.

Paso 5: Mission Control Frontend

Inicia app Vite + React + TS.

Construye el dashboard: Tarjeta de saldo/PnL, gráfico con lightweight-charts y una tabla de "Bitácora" alimentada por los eventos del agente (mostrando métricas y el reasoning del LLM).

¿Entendiste el objetivo y las restricciones? Si es así, responde resumiendo tu enfoque para el Paso 1 y escribe el código de la base de datos para comenzar.