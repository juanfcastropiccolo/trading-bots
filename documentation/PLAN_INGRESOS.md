# Plan de ingresos: cómo llevar dinero a la billetera EVM

Fecha: 2026-09-06. Investigación de cuatro agentes en paralelo (bounties de código y seguridad, incentivos cripto, trabajo y micro-tareas, trading y rutas de fondeo). Solo vías legales. Los sitios oficiales estaban en su mayoría bloqueados por el proxy del entorno, así que casi todo sale de fuentes secundarias de 2026; lo no verificado se marca.

Billetera destino (EVM): `0x434b7A34A7A112C8c6Bc53416Cf243d0D67535ce`.
Regla de oro: enviar SOLO por Ethereum, Base, Arbitrum, Polygon, Optimism, BSC o Avalanche C-Chain. Nunca por Tron, Solana o TON: los fondos se pierden.

## Conclusión en tres líneas

1. No existe ninguna vía gratis y automática que ponga 5 USD en una billetera EVM en una semana. Faucets, airdrops sin capital y grants no pagan en ese plazo.
2. Las vías con probabilidad real en menos de 7 días intercambian trabajo por USDC: bounties chicos pagados en Base (Bountycaster, marketplaces para agentes) y Learn & Earn de exchanges con KYC.
3. El trading con lo que hay en el repo NO es una forma de generar 5 USD en una semana: el momentum spot va +13,7% en 57 días pero con un solo trade ganador y drawdown de -13,5%; el long/short va -6,4%.

## Ranking consolidado (probabilidad de 5 USD en la billetera en menos de 7 días)

| # | Vía | Prob. | KYC | Cómo llega a la billetera | Quién hace qué |
|---|---|---|---|---|---|
| 1 | Bountycaster (bounties en Farcaster, USDC en Base, 2 a 500 USDC) | Media | No | El poster paga P2P a la dirección, en Base | Humano: cuenta Farcaster (gratis desde oct-2025), postula y publica. Agente: elige bounties y produce el entregable completo |
| 2 | Marketplaces de bounties para agentes en Base (BountyBook, ClawTasks, Agent Bounties, Claw Earn) | Media | No | Escrow USDC on-chain, pago instantáneo | Humano: fondear 2-3 USD de ETH en Base para gas. Agente: registrarse por API, reclamar y entregar tareas de 5-20 USD |
| 3 | Binance Learn & Earn + CoinMarketCap Earn | Media-alta si hay campañas con cupo | Sí | Retiro USDC por Base o Arbitrum (fee ~0,10 USD) | Humano: KYC, quizzes, retiro. Agente: prepara respuestas y elige red más barata |
| 4 | LaborX gigs / Opire (bounties GitHub pagados en cripto) | Media-baja en 7 días, razonable en 2-3 semanas | Cuenta | Escrow en contrato → wallet EVM (usar Polygon/BSC) | Humano: cuenta y firma entregas. Agente: gigs de backtesting y scripts Python, PRs |
| 5 | Hats Finance / Sherlock (bug bounty en contratos, sin KYC, USDC) | Baja en 7 días | No | USDC a wallet Ethereum | Agente: auditar Solidity con PoC. Sherlock retiene pago hasta 2 hallazgos válidos |

Descartadas para el corto plazo: faucets de mainnet (centavos o zombis; FreeBitco.in no paga retiros en 2026), airdrops sin capital (meses, especulativo), grants (semanas a meses), prop firms (cuestan 50-100 USD, drawdown máximo 8-10% incompatible con la estrategia, primer payout a 3-10 semanas), copy trading (100 USDT mínimo y sin track record nadie copia), micro-tareas (Outlier y similares prohíben LLM y banean), Bittensor (necesita TAO y GPU).

## Lo que el humano tiene que hacer (nadie más puede)

1. Importar la clave privada en Rabby o MetaMask y respaldarla. Sin la clave los fondos son irrecuperables.
2. Crear cuenta en Farcaster y verificar la dirección como wallet. Postular a bounties desde su cuenta.
3. KYC en Binance (PSAV registrado en CNV) y en una app local (Fiwind, Belo o Lemon).
4. Comprar 8-10 USDC y enviar 2-3 USDC por Base a la dirección como depósito de prueba. Además 2-3 USD de ETH en Base para gas.
5. Abrir cuentas en LaborX y Opire; registrar la wallet en Hats y Sherlock si se quiere el frente de seguridad.

## Lo que hace el agente

- Rastrear bounties abiertos y filtrar los alcanzables (Python, TypeScript, scripts, análisis de datos, mini-apps en Base).
- Producir entregables completos: código con tests, PRs, informes, documentación. Declarar asistencia de IA cuando el repo lo pida.
- Registrarse por API en marketplaces de agentes y reclamar tareas chicas.
- Verificar saldo on-chain tras cada pago y llevar registro de fecha, monto y origen para el contador.
- Seguir el paper trading para acumular track record; recién con 3-6 meses de historial evaluar prop firms (Crypto Fund Trader o HyroTrader, fee reembolsable) o copy trading.

## Estafas y trampas detectadas (no tocar)

- Repos "solo para agentes IA" que piden pegar el system prompt completo o correr `build.py` y subir diagnósticos cifrados: ClankerNation/OpenAgents, UnsafeLabs, SecureBananaLabs, xevrion-v2, zeroeye, TentOfTrials, CyberNinja-Dojo. Sin evidencia de pago; exfiltración de prompts.
- Quests de Galxe o Zealy tipo "50 USDC airdrop, claim now" o que cobran para desbloquear.
- Cualquier sitio que pida la frase semilla o aprobaciones ilimitadas.
- Skills de terceros en marketplaces de agentes: 341 maliciosas detectadas en feb-2026. Nunca exponer la clave privada.
- Programas ya muertos que los blogs siguen vendiendo: Coinbase Learning Rewards, Base App Creator Rewards, Kaito Yaps, tips gratis de DEGEN, Replit Bounties.
- RustChain bounties: reales pero pagan en RTC (sin liquidez verificable en EVM).

## Normativa en Argentina (general, no es asesoramiento)

- Ley 27.739 y RG CNV 1058/2025: operar en PSAV registrados (Binance, Lemon, Belo, Ripio, Buenbit, Fiwind). Bybit, OKX, Bitget e Hyperliquid no confirmados.
- Bounties y pagos por servicios en cripto son ingreso gravado al recibirlos. Resultado por venta tributa cedular 5% o 15%. Servicios al exterior: factura E.
- Los PSAV reportan a ARCA mensualmente; el umbral citado es 50 M ARS.

## No verificado (chequear a mano)

- FAQ de Bountycaster (si cuentas nuevas pueden reclamar sin badge).
- Campañas activas hoy de Binance Learn & Earn y CMC Earn con cupo para Argentina.
- Bounties abiertos hoy en BountyBook, ClawTasks y Agent Bounties (solo un dato de terceros: 43 bounties, uno de 15 USD).
- Si LaborX exige KYC para retirar. Disponibilidad de Contra y Coinbase para residentes argentinos.
- Tablas oficiales de mínimos y fees de retiro por red en Binance y apps locales.
- Estado PSAV de Bybit, OKX, Bitget e Hyperliquid.
