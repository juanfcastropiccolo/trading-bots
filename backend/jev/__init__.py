"""POC de market making con Jev (TypeSafe AI, modelo "System One") como capa de juicio.

Implementa la arquitectura del paper "How to Build a One-Person HFT Hedge Fund
on Jev That Fires Calibrated Trades on Every Block 24/7" (sep-2026):

  código calcula el estado  →  Jev interpreta el estado  →  código aplica la
  política  →  el motor de ejecución coloca la orden.

Módulos:
  state        motor de estado determinístico (snapshot de 7 familias, < 400 tokens)
  battery      batería de 6 preguntas tipadas + jueces (Jev real, reglas, oráculo calibrado)
  policy       compose() con vetos primero, Kelly fraccional, precios Avellaneda-Stoikov
  risk         límites duros que el modelo nunca puede anular
  venue        venue de papel: órdenes post-only, cola, fills contra prints, gas y fees
  loop         el loop por bloque con deadline, escalera de fallback y log de calibración
  calibration  Brier, ECE, curva de confiabilidad, Platt
  feeds        mercado sintético con latentes conocidos + grabador/replay de datos reales

Nada acá tiene edge por sí mismo: el paper es explícito en que Jev "no crea
edge; hace decisiones rápidas y baratas, pero una estrategia sin edge pierde
más rápido, no menos".
"""
