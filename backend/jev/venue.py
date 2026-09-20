"""Venue de papel: órdenes post-only con posición en cola, fills contra los
prints reales del feed, gas por transacción y fees maker/taker.

Modelo de fill (conservador respecto del demo jev-trader, que llena la orden
con cualquier print que cruce su precio sin mirar la cola):
  - Una orden puesta en el bloque N descansa desde N+1.
  - Entra al final de la cola de su nivel: `queue_ahead` = tamaño visible en
    ese precio al momento de postear (0 si quedó dentro del spread).
  - Un print agresor vendedor a precio ≤ nuestro bid consume primero la cola
    y recién después nos llena (y viceversa para el ask).
  - Si el libro se mueve a través de nuestro precio (mejor ask ≤ nuestro
    bid), alguien nos tomó: se llena el remanente.
  - Cada bloque en que mandamos una transacción (cancel + post en un batch)
    paga `gas_usd_per_tx`, se ejecute o no (Monad cobra el gas limit).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .state import BlockEvent


@dataclass
class Order:
    side: str                 # bid | ask
    price: float
    size: float
    block_posted: int
    queue_ahead: float


@dataclass
class Fill:
    block: int
    side: str                 # bid (compramos) | ask (vendimos)
    price: float
    size: float
    mid_at_fill: float
    maker: bool = True


@dataclass
class VenueCosts:
    name: str = "ideal"
    maker_fee_bps: float = 0.0
    taker_fee_bps: float = 0.0
    gas_usd_per_tx: float = 0.0
    # Competencia por el interior del spread: al postear dentro del spread hay,
    # con prob `inside_queue_p`, otros makers ya ahí (cola media
    # `inside_queue_mean` unidades). Sin esto, quien cotiza adentro recibe TODO
    # el flujo no informado gratis, algo que ningún venue real regala.
    inside_queue_p: float = 0.0
    inside_queue_mean: float = 0.0


@dataclass
class PaperVenue:
    costs: VenueCosts
    tick: float
    bid: Order | None = None
    ask: Order | None = None
    txs: int = 0
    gas_usd: float = 0.0
    fees_usd: float = 0.0
    fills: list[Fill] = field(default_factory=list)
    rejected_post_only: int = 0
    seed: int = 0

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    # ------------------------------------------------------------- órdenes
    def replace(self, block: int, bid: tuple[float, float] | None, ask: tuple[float, float] | None,
                evt: BlockEvent) -> bool:
        """Lleva el libro propio a (bid, ask). Devuelve True si hubo transacción."""
        new_bid = self._mk("bid", bid, block, evt)
        new_ask = self._mk("ask", ask, block, evt)
        changed = not _same(self.bid, new_bid) or not _same(self.ask, new_ask)
        if not changed:
            return False
        if new_bid is not None and not _same(self.bid, new_bid):
            self.bid = new_bid
        elif new_bid is None:
            self.bid = None
        if new_ask is not None and not _same(self.ask, new_ask):
            self.ask = new_ask
        elif new_ask is None:
            self.ask = None
        self.txs += 1
        self.gas_usd += self.costs.gas_usd_per_tx
        return True

    def _mk(self, side: str, o, block: int, evt: BlockEvent) -> Order | None:
        if o is None or o[1] <= 0:
            return None
        px, sz = o
        best_bid, best_ask = evt.bids[0][0], evt.asks[0][0]
        if (side == "bid" and px >= best_ask - 1e-12) or (side == "ask" and px <= best_bid + 1e-12):
            self.rejected_post_only += 1     # cruzaría: el venue rechaza una post-only
            return None
        levels = evt.bids if side == "bid" else evt.asks
        ahead = sum(s for p, s in levels if abs(p - px) < self.tick / 2)
        inside = (side == "bid" and px > best_bid + 1e-12) or (side == "ask" and px < best_ask - 1e-12)
        if inside and self.costs.inside_queue_p > 0 and self._rng.random() < self.costs.inside_queue_p:
            ahead += self._rng.lognormvariate(math.log(self.costs.inside_queue_mean), 0.5)
        return Order(side, px, sz, block, ahead)

    def cancel_all(self, block: int) -> bool:
        if self.bid is None and self.ask is None:
            return False
        self.bid = self.ask = None
        self.txs += 1
        self.gas_usd += self.costs.gas_usd_per_tx
        return True

    # --------------------------------------------------------------- fills
    def on_block(self, evt: BlockEvent) -> list[Fill]:
        """Aplica los prints del bloque a las órdenes que ya descansaban."""
        out: list[Fill] = []
        mid = evt.mid
        for side, o in (("bid", self.bid), ("ask", self.ask)):
            if o is None or evt.block <= o.block_posted:
                continue
            for pside, ppx, psz in evt.prints:
                if o.size <= 0:
                    break
                hit = (side == "bid" and pside == "sell" and ppx <= o.price + 1e-12) or \
                      (side == "ask" and pside == "buy" and ppx >= o.price - 1e-12)
                if not hit:
                    continue
                eat = min(o.queue_ahead, psz)
                o.queue_ahead -= eat
                rem = psz - eat
                if rem <= 0:
                    continue
                q = min(o.size, rem)
                o.size -= q
                out.append(self._fill(evt.block, side, o.price, q, mid))
            # el libro pasó a través de nuestro precio: nos tomaron
            if o.size > 0 and ((side == "bid" and evt.asks[0][0] <= o.price + 1e-12) or
                               (side == "ask" and evt.bids[0][0] >= o.price - 1e-12)):
                out.append(self._fill(evt.block, side, o.price, o.size, mid))
                o.size = 0.0
        if self.bid is not None and self.bid.size <= 0:
            self.bid = None
        if self.ask is not None and self.ask.size <= 0:
            self.ask = None
        return out

    def _fill(self, block: int, side: str, px: float, q: float, mid: float) -> Fill:
        self.fees_usd += px * q * self.costs.maker_fee_bps / 1e4
        f = Fill(block, side, px, q, mid, maker=True)
        self.fills.append(f)
        return f

    def flatten(self, block: int, inventory: float, evt: BlockEvent) -> Fill | None:
        """Cierre por mercado (kill switch / fin de sesión): paga el touch y fee taker."""
        self.cancel_all(block)
        if abs(inventory) < 1e-12:
            return None
        if inventory > 0:
            px, side = evt.bids[0][0], "ask"
        else:
            px, side = evt.asks[0][0], "bid"
        q = abs(inventory)
        self.fees_usd += px * q * self.costs.taker_fee_bps / 1e4
        self.txs += 1
        self.gas_usd += self.costs.gas_usd_per_tx
        f = Fill(block, side, px, q, evt.mid, maker=False)
        self.fills.append(f)
        return f


def _same(a: Order | None, b: Order | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a.price - b.price) < 1e-12 and abs(a.size - b.size) < 1e-12
