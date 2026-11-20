
from datetime import datetime


class DemoMT5:
    """محرك محاكاة تداول تعليمي فقط."""

    def __init__(self, balance=10000):
        self.balance = float(balance)
        self.positions = []
        self.history = []
        self.next_ticket = 1

    def connect(self):
        return {
            "success": True,
            "mode": "DEMO",
            "message": "Demo connected"
        }

    def account_info(self):
        floating = sum(p["profit"] for p in self.positions)
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.balance + floating, 2),
            "profit": round(floating, 2),
            "positions": len(self.positions),
            "mode": "DEMO ONLY"
        }

    def buy(self, symbol, lot, price, sl=0, tp=0):
        return self._open("BUY", symbol, lot, price, sl, tp)

    def sell(self, symbol, lot, price, sl=0, tp=0):
        return self._open("SELL", symbol, lot, price, sl, tp)

    def _open(self, side, symbol, lot, price, sl, tp):
        if lot <= 0 or price <= 0:
            return {"success": False, "error": "Invalid values"}

        position = {
            "ticket": self.next_ticket,
            "side": side,
            "symbol": symbol,
            "lot": float(lot),
            "open_price": float(price),
            "current_price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "profit": 0.0,
            "time": datetime.now().isoformat()
        }

        self.next_ticket += 1
        self.positions.append(position)
        return {"success": True, "position": position.copy()}

    def update_price(self, symbol, price):
        for p in self.positions:
            if p["symbol"] != symbol:
                continue

            difference = price - p["open_price"]
            if p["side"] == "SELL":
                difference *= -1

            p["current_price"] = float(price)
            p["profit"] = round(
                difference * p["lot"] * 10, 2
            )

    def close(self, ticket):
        for p in self.positions[:]:
            if p["ticket"] == ticket:
                self.balance += p["profit"]
                closed = p.copy()
                closed["close_time"] = datetime.now().isoformat()
                self.history.append(closed)
                self.positions.remove(p)
                return {"success": True, "closed": closed}

        return {"success": False, "error": "Position not found"}

    def close_all(self):
        return [
            self.close(p["ticket"])
            for p in self.positions[:]
        ]

    def get_positions(self):
        return [p.copy() for p in self.positions]

    def get_history(self):
        return [p.copy() for p in self.history]
