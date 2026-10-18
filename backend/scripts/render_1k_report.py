"""Genera PAPER_1K_REPORT.md (raíz del repo) a partir de backend/data/momentum_1k_state.json.

Determinístico: mismo estado → mismo reporte. Lo corre el workflow de GitHub
Actions después del tick diario (momentum_1k_paper.py).

Uso:  python scripts/render_1k_report.py
"""
import json
import os
from datetime import date

BUDGET = 1000.0

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_1k_state.json")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "PAPER_1K_REPORT.md")


def real(holdings: dict) -> dict:
    return {s: q for s, q in holdings.items() if q > 0}


def fmt_holdings(holdings: dict) -> str:
    holdings = real(holdings)
    return ", ".join(sorted(holdings)) if holdings else "cash"


def build_trades(history: list) -> tuple[list, int, int]:
    """Detecta entradas/salidas comparando holdings día a día."""
    trades, entry_equity, wins, losses = [], {}, 0, 0
    prev = {}
    for row in history:
        cur = real(row["holdings"])
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
    start = date.fromisoformat(history[0]["date"])
    days = (date.fromisoformat(last["date"]) - start).days + 1
    trades, wins, losses = build_trades(history)

    lines = [
        "# Momentum Paper Trader $1000 — Reporte",
        "",
        f"_Actualizado: {last['date']} (tick automático vía GitHub Actions). "
        "Config `base_top2` elegida por VALIDACION_1K.md (ninguna variante de la "
        "lista cerrada superó al baseline)._",
        "",
        "## Estado actual",
        "",
        f"- **Equity:** ${equity:.2f} ({ret:+.2f}% desde los $1000 iniciales)",
        f"- **Cash:** ${last['cash']:.2f}",
        f"- **Posiciones abiertas:** {fmt_holdings(last['holdings'])}",
        f"- **Target del día:** {', '.join(last['target']) if last['target'] else 'cash'}",
        f"- **Días corriendo:** {days} (desde {start.isoformat()})",
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
        "cuando cambia el target, costos simulados 0.15% por lado, capital $1000",
        "(min notional $5 por orden).",
        "",
    ]

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"PAPER_1K_REPORT.md regenerado ({last['date']}, equity ${equity:.2f})")


if __name__ == "__main__":
    main()
