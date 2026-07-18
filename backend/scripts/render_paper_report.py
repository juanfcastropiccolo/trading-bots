"""Genera PAPER_REPORT.md (raíz del repo) a partir de backend/data/momentum_state.json.

Determinístico: mismo estado → mismo reporte. Lo corre el workflow de GitHub
Actions después del tick diario (momentum_paper.py).

Uso:  python scripts/render_paper_report.py
"""
import json
import os
from datetime import date

BUDGET = 100.0
START = date(2026, 7, 12)

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_state.json")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "PAPER_REPORT.md")


def fmt_holdings(holdings: dict) -> str:
    return ", ".join(sorted(holdings)) if holdings else "cash"


def build_trades(history: list) -> tuple[list, int, int]:
    """Detecta entradas/salidas comparando holdings día a día.

    Una salida es pegada si el equity al cerrar supera al equity de entrada.
    """
    trades, entry_equity, wins, losses = [], {}, 0, 0
    prev = {}
    for row in history:
        cur = row["holdings"]
        bought = [s for s in cur if s not in prev]
        sold = [s for s in prev if s not in cur]
        for s in sold:
            result = "pegada" if row["equity"] > entry_equity.get(s, BUDGET) else "pérdida"
            if result == "pegada":
                wins += 1
            else:
                losses += 1
            trades.append(f"- **{row['date']}** — SELL {s} ({result}: equity "
                          f"${entry_equity.get(s, BUDGET):.2f} → ${row['equity']:.2f})")
        for s in bought:
            entry_equity[s] = row["equity"]
            trades.append(f"- **{row['date']}** — BUY {s} (equity ${row['equity']:.2f})")
        prev = cur
    return trades, wins, losses


def main():
    with open(STATE_PATH) as f:
        state = json.load(f)
    history = state["history"]
    last = history[-1]
    equity = last["equity"]
    ret = (equity / BUDGET - 1) * 100
    days = (date.fromisoformat(last["date"]) - START).days + 1
    trades, wins, losses = build_trades(history)

    lines = [
        "# Momentum Paper Trader — Reporte",
        "",
        f"_Actualizado: {last['date']} (tick automático vía GitHub Actions)_",
        "",
        "## Estado actual",
        "",
        f"- **Equity:** ${equity:.2f} ({ret:+.2f}% desde los $100 iniciales)",
        f"- **Cash:** ${last['cash']:.2f}",
        f"- **Posiciones abiertas:** {fmt_holdings(last['holdings'])}",
        f"- **Target del día:** {', '.join(last['target']) if last['target'] else 'cash'}",
        f"- **Días corriendo:** {days} (desde {START.isoformat()})",
        f"- **Pegadas / pérdidas:** {wins} / {losses}",
        "",
        "## Historial de equity",
        "",
        "| Fecha | Equity | Posiciones | Target |",
        "|-------|--------|------------|--------|",
    ]
    for row in reversed(history):
        target = ", ".join(row["target"]) if row["target"] else "cash"
        lines.append(f"| {row['date']} | ${row['equity']:.2f} | "
                     f"{fmt_holdings(row['holdings'])} | {target} |")

    lines += ["", "## Operaciones", ""]
    lines += trades if trades else ["Sin operaciones todavía (100% cash desde el inicio)."]

    lines += [
        "",
        "## Regla vigente",
        "",
        "Top-2 de 10 majors por momentum 30d, filtro SMA-100, rebalanceo solo",
        "cuando cambia el target, costos simulados 0.15% por lado.",
        "",
    ]

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"PAPER_REPORT.md regenerado ({last['date']}, equity ${equity:.2f})")


if __name__ == "__main__":
    main()
