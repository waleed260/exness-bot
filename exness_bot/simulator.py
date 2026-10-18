"""Deterministic local trading simulator used for safe development and tests."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class SimPosition:
    ticket: int
    side: str
    volume: float
    entry: float
    sl: float
    tp: float
    opened_at: str
    status: str = "open"
    exit: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0


class Simulator:
    """A one-symbol broker-like simulator with persistent restart state."""

    def __init__(self, state_path=None):
        self.state_path = state_path
        self.next_ticket = 1
        self.positions = {}
        self.last_price = None
        self._load()

    def _load(self):
        if not self.state_path or not os.path.exists(self.state_path):
            return
        with open(self.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.next_ticket = int(data.get("next_ticket", 1))
        self.last_price = data.get("last_price")
        self.positions = {int(k): SimPosition(**v) for k, v in data.get("positions", {}).items()}

    def _save(self):
        if not self.state_path:
            return
        directory = os.path.dirname(self.state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="sim-", dir=directory or ".", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"next_ticket": self.next_ticket, "last_price": self.last_price,
                           "positions": {str(k): asdict(v) for k, v in self.positions.items()}}, f)
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def open(self, side, volume, price, sl, tp, opened_at=""):
        if side not in {"buy", "sell"} or volume <= 0:
            raise ValueError("invalid simulated order")
        if side == "buy" and not sl < price < tp:
            raise ValueError("invalid buy stops")
        if side == "sell" and not tp < price < sl:
            raise ValueError("invalid sell stops")
        ticket = self.next_ticket
        self.next_ticket += 1
        self.positions[ticket] = SimPosition(ticket, side, float(volume), float(price),
                                              float(sl), float(tp), opened_at)
        self.last_price = float(price)
        self._save()
        return self.positions[ticket]

    def modify_sl(self, ticket, sl):
        position = self.positions[ticket]
        if position.status != "open":
            return False
        if position.side == "buy" and sl < position.sl:
            return False
        if position.side == "sell" and sl > position.sl:
            return False
        position.sl = float(sl)
        self._save()
        return True

    def close(self, ticket, price, reason="manual"):
        position = self.positions[ticket]
        if position.status != "open":
            return position
        position.exit = float(price)
        position.exit_reason = reason
        position.status = "closed"
        direction = 1 if position.side == "buy" else -1
        position.pnl = (position.exit - position.entry) * direction * position.volume
        self.last_price = position.exit
        self._save()
        return position

    def on_price(self, price):
        price = float(price)
        self.last_price = price
        closed = []
        for position in list(self.positions.values()):
            if position.status != "open":
                continue
            if position.side == "buy":
                if price <= position.sl:
                    closed.append(self.close(position.ticket, position.sl, "stop_loss"))
                elif price >= position.tp:
                    closed.append(self.close(position.ticket, position.tp, "take_profit"))
            else:
                if price >= position.sl:
                    closed.append(self.close(position.ticket, position.sl, "stop_loss"))
                elif price <= position.tp:
                    closed.append(self.close(position.ticket, position.tp, "take_profit"))
        self._save()
        return closed

    def partial_close(self, ticket, price, fraction):
        """Close a fraction of volume; return the closed portion as a SimPosition."""
        position = self.positions[ticket]
        if position.status != "open":
            return position
        close_vol = round(position.volume * fraction, 2)
        if close_vol <= 0:
            return None
        remaining = round(position.volume - close_vol, 2)
        if remaining <= 0:
            return self.close(ticket, price, "partial_close_full")
        direction = 1 if position.side == "buy" else -1
        partial_pnl = (float(price) - position.entry) * direction * close_vol
        closed_part = SimPosition(
            ticket=ticket, side=position.side, volume=close_vol,
            entry=position.entry, sl=position.sl, tp=position.tp,
            opened_at=position.opened_at, status="closed",
            exit=float(price), exit_reason="partial_close", pnl=partial_pnl,
        )
        position.volume = remaining
        self.last_price = float(price)
        self._save()
        return closed_part

    def modify_sl_breakeven(self, ticket, entry_price):
        """Move SL to entry (breakeven) regardless of direction."""
        position = self.positions[ticket]
        if position.status != "open":
            return False
        position.sl = float(entry_price)
        self._save()
        return True

    def reconcile(self, external_positions):
        external_ids = {int(p.ticket) for p in external_positions}
        for ticket, position in self.positions.items():
            if position.status == "open" and ticket not in external_ids:
                position.status = "closed"
                position.exit_reason = "reconciled_missing_external_position"
        self._save()

    def open_positions(self):
        return [p for p in self.positions.values() if p.status == "open"]
