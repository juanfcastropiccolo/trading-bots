"""Genera PAPER_LS_REPORT.md a partir de backend/data/momentum_ls_state.json.

Determinístico; lo corre el workflow de GitHub Actions tras el tick L/S.

Uso:  python scripts/render_ls_report.py
"""
import json
import os
from datetime import date

BUDGET = 100.0
START = date(2026, 7, 17)

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_ls_state.json")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "PAPER_LS_REPORT.md")

LABELS = {
    "v4_voltarget": "V4 + voltarget (candidata principal — pasó los criterios ex-ante)",
    "v4_ensemble": "V4 + ensemble (experimento secundario — falló criterio (c))",
}


def fmt_w(weights: dict) -> str:
    if not weights:
        return "cash"
    return ", ".join(f"{s.split('/')[0]} {w:+.2f}" for s, w in sorted(weights.items()))


def main():
    with open(STATE_PATH) as f:
        state = json.load(f)

    lines = [
        "# Momentum Long/Short (perpetuos) — Paper Trading",
        "",
        f"_Fase 3 de PLAN_FUTUROS.md. Actualizado: {state['last_run']} "
        "(tick automático vía GitHub Actions). Pesos con signo (− = short), "
        "funding real, costos 0.05% por lado, palanca 1x._",
        "",
        "> **Disciplina de decisión:** el pase a real se evalúa contra los criterios",
        "> pre-fijados de VALIDACION_LS.md tras 4-6 semanas de paper — NO contra cuál",
        "> estrategia rindió más en esta muestra corta.",
        "",
    ]
    for name, st in state["strategies"].items():
        last = st["history"][-1]
        days = (date.fromisoformat(last["date"]) - START).days + 1
        ret = (st["equity"] / BUDGET - 1) * 100
        lines += [
            f"## {LABELS.get(name, name)}",
            "",
            f"- **Equity:** ${st['equity']:.2f} ({ret:+.2f}% desde los $100 iniciales)",
            f"- **Posiciones:** {fmt_w(st['weights'])}",
            f"- **Días corriendo:** {days} (desde {START.isoformat()})",
            "",
            "| Fecha | Equity | Posiciones |",
            "|-------|--------|------------|",
        ]
        for row in reversed(st["history"][-30:]):
            lines.append(f"| {row['date']} | ${row['equity']:.2f} | {fmt_w(row['weights'])} |")
        lines.append("")

    lines += [
        "## Regla vigente",
        "",
        "Gate de régimen: BTC>SMA-200 → top-2 de 10 majors por momentum sobre SMA-100,",
        "long 0.5 c/u; BTC<SMA-200 → short BTC/ETH (−0.25 c/u) solo si bajo SMA-100 y",
        "momentum negativo, resto cash. Rebalanceo semanal (lunes UTC). v4_voltarget",
        "escala cada posición por min(1, 50%/vol anualizada 30d); v4_ensemble usa",
        "momentum promedio 15/30/60/90d en lugar de 30d.",
        "",
    ]
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"PAPER_LS_REPORT.md regenerado ({state['last_run']})")


if __name__ == "__main__":
    main()
