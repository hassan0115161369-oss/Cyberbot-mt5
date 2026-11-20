import hashlib
import json
import math
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.getenv("CYBERBOT_DATA_DIR", ".cyberbot_data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
JOURNAL_FILE = DATA_DIR / "trade_journal.json"
STRATEGIES_FILE = DATA_DIR / "strategies.json"


# ==================== التخزين المحلي الآمن ====================
def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_secret(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


class LocalAuthManager:
    def __init__(self):
        self.users = _load_json(USERS_FILE, {})

    def register(self, username: str, password: str, recovery_pin: str):
        u = username.strip().lower()
        if len(u) < 3 or len(password) < 4 or len(recovery_pin) < 4:
            return False, "اسم المستخدم (3+ أحرف) وكلمة المرور ورمز الاستعادة (4+ أحرف) مطلوبة."
        if u in self.users:
            return False, "اسم المستخدم مسجل مسبقاً."
        self.users[u] = {
            "username": username.strip(),
            "password_hash": hash_secret(password),
            "pin_hash": hash_secret(recovery_pin),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _save_json(USERS_FILE, self.users)
        return True, "تم إنشاء الحساب بنجاح."

    def login(self, username: str, password: str):
        u = username.strip().lower()
        if u not in self.users:
            return False, "المستخدم غير موجود."
        if self.users[u]["password_hash"] != hash_secret(password):
            return False, "كلمة المرور غير صحيحة."
        return True, self.users[u]

    def recover_password(self, username: str, recovery_pin: str, new_password: str):
        u = username.strip().lower()
        if u not in self.users:
            return False, "المستخدم غير موجود."
        if self.users[u]["pin_hash"] != hash_secret(recovery_pin):
            return False, "رمز الاستعادة غير صحيح."
        if len(new_password) < 4:
            return False, "كلمة المرور الجديدة قصيرة جداً."
        self.users[u]["password_hash"] = hash_secret(new_password)
        _save_json(USERS_FILE, self.users)
        return True, "تم تحديث كلمة المرور بنجاح."


class JournalManager:
    def __init__(self):
        self.entries = _load_json(JOURNAL_FILE, [])

    def add_trade(self, trade: dict):
        trade["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.entries.insert(0, trade)
        self.entries = self.entries[:200]
        _save_json(JOURNAL_FILE, self.entries)

    def get_stats(self):
        closed = [t for t in self.entries if "profit" in t]
        if not closed:
            return {"total": 0, "wins": 0, "win_rate": 0.0, "net_pl": 0.0, "profit_factor": 0.0}
        wins = [t["profit"] for t in closed if t["profit"] > 0]
        losses = [abs(t["profit"]) for t in closed if t["profit"] < 0]
        gross_win = sum(wins)
        gross_loss = sum(losses) or 1e-9
        return {
            "total": len(closed),
            "wins": len(wins),
            "win_rate": round((len(wins) / len(closed)) * 100, 1),
            "net_pl": round(sum(t["profit"] for t in closed), 2),
            "profit_factor": round(gross_win / gross_loss, 2),
        }


class StrategyManager:
    DEFAULT_STRATEGIES = [
        {
            "name": "Cyber Scalper Pro",
            "ema_fast": 9,
            "ema_slow": 21,
            "rsi_buy": 35,
            "rsi_sell": 65,
            "min_conf": 65,
            "sl_atr": 1.8,
            "tp_atr": 3.2,
        },
        {
            "name": "Trend Hunter SMC",
            "ema_fast": 21,
            "ema_slow": 50,
            "rsi_buy": 40,
            "rsi_sell": 60,
            "min_conf": 70,
            "sl_atr": 2.0,
            "tp_atr": 4.0,
        },
    ]

    def __init__(self):
        self.strategies = _load_json(STRATEGIES_FILE, self.DEFAULT_STRATEGIES)

    def save_strategy(self, strat: dict):
        self.strategies = [s for s in self.strategies if s["name"] != strat["name"]]
        self.strategies.insert(0, strat)
        _save_json(STRATEGIES_FILE, self.strategies)
        return self.strategies


# ==================== المؤشرات الفنية الحقيقية (OHLC) ====================
def normalize_candles(raw_candles: list) -> list[dict]:
    out = []
    for c in raw_candles:
        if "close" not in c:
            continue
        close = float(c["close"])
        op = float(c.get("open", close))
        hi = float(c.get("high", max(op, close)))
        lo = float(c.get("low", min(op, close)))
        out.append({"open": op, "high": hi, "low": lo, "close": close, "time": c.get("time", "")})
    return out


def calc_ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    mult = 2 / (period + 1)
    ema = values[0]
    series = [ema]
    for v in values[1:]:
        ema = (v - ema) * mult + ema
        series.append(ema)
    return series


def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period or 1e-9
    rs = avg_g / avg_l
    return round(100 - (100 / (1 + rs)), 2)


def calc_macd(closes: list[float]):
    if len(closes) < 26:
        return 0.0, 0.0, 0.0
    ema12 = calc_ema_series(closes, 12)
    ema26 = calc_ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal_line = calc_ema_series(macd_line, 9)
    hist = macd_line[-1] - signal_line[-1]
    return round(macd_line[-1], 5), round(signal_line[-1], 5), round(hist, 5)


def calc_true_atr(candles: list[dict], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if not trs:
        return 0.0
    n = min(period, len(trs))
    return sum(trs[-n:]) / n


def calc_bollinger(closes: list[float], period: int = 20, mult: float = 2.0):
    if len(closes) < period:
        p = closes[-1] if closes else 0.0
        return p, p, p
    window = closes[-period:]
    mid = sum(window) / period
    var = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(var)
    return round(mid + mult * std, 5), round(mid, 5), round(mid - mult * std, 5)


def calc_stochastic(candles: list[dict], period: int = 14):
    if len(candles) < period:
        return 50.0
    window = candles[-period:]
    hi = max(c["high"] for c in window)
    lo = min(c["low"] for c in window)
    if hi == lo:
        return 50.0
    return round(((candles[-1]["close"] - lo) / (hi - lo)) * 100, 2)


def calc_adx(candles: list[dict], period: int = 14) -> float:
    if len(candles) < period + 2:
        return 20.0
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(candles)):
        up = candles[i]["high"] - candles[i - 1]["high"]
        down = candles[i - 1]["low"] - candles[i]["low"]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)) or 1e-9)
    tr_sum = sum(trs[-period:]) or 1e-9
    pdi = 100 * (sum(plus_dm[-period:]) / tr_sum)
    mdi = 100 * (sum(minus_dm[-period:]) / tr_sum)
    denom = (pdi + mdi) or 1e-9
    return round(100 * abs(pdi - mdi) / denom, 2)


def detect_candlestick_pattern(candles: list[dict]) -> str:
    if len(candles) < 2:
        return "None"
    c, p = candles[-1], candles[-2]
    body = abs(c["close"] - c["open"])
    rng = (c["high"] - c["low"]) or 1e-9
    upper_wick = c["high"] - max(c["open"], c["close"])
    lower_wick = min(c["open"], c["close"]) - c["low"]

    if body / rng < 0.12:
        return "Doji"
    if lower_wick > body * 2 and upper_wick < body:
        return "Hammer (Bullish)"
    if upper_wick > body * 2 and lower_wick < body:
        return "Shooting Star (Bearish)"
    if p["close"] < p["open"] and c["close"] > c["open"] and c["close"] > p["open"] and c["open"] < p["close"]:
        return "Bullish Engulfing"
    if p["close"] > p["open"] and c["close"] < c["open"] and c["close"] < p["open"] and c["open"] > p["close"]:
        return "Bearish Engulfing"
    return "Standard"


def detect_structure_smc(candles: list[dict]):
    if len(candles) < 25:
        return {"sr": (0.0, 0.0), "structure": "RANGING", "ob": "None", "fib": {}}
    recent = candles[-25:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    swing_high = max(highs[:-3])
    swing_low = min(lows[:-3])
    last_close = recent[-1]["close"]

    structure = "RANGING"
    if last_close > swing_high:
        structure = "BOS Bullish"
    elif last_close < swing_low:
        structure = "BOS Bearish"
    elif last_close > (swing_high + swing_low) / 2 and recent[-3]["close"] < (swing_high + swing_low) / 2:
        structure = "CHOCH Bullish"
    elif last_close < (swing_high + swing_low) / 2 and recent[-3]["close"] > (swing_high + swing_low) / 2:
        structure = "CHOCH Bearish"

    # Order Block مبسط: آخر شمعة معاكسة قبل الاندفاع
    ob = "None"
    if "Bullish" in structure:
        for c in reversed(recent[:-1]):
            if c["close"] < c["open"]:
                ob = f"Bullish OB ({c['low']:.2f} - {c['high']:.2f})"
                break
    elif "Bearish" in structure:
        for c in reversed(recent[:-1]):
            if c["close"] > c["open"]:
                ob = f"Bearish OB ({c['low']:.2f} - {c['high']:.2f})"
                break

    diff = swing_high - swing_low
    fib = {
        "0.382": round(swing_high - diff * 0.382, 4),
        "0.500": round(swing_high - diff * 0.500, 4),
        "0.618": round(swing_high - diff * 0.618, 4),
    }
    return {
        "sr": (round(swing_low, 4), round(swing_high, 4)),
        "supply": round(swing_high, 4),
        "demand": round(swing_low, 4),
        "structure": structure,
        "ob": ob,
        "fib": fib,
    }


# ==================== محرك التحليل الشامل ====================
def full_market_analysis(raw_candles: list, strategy: dict | None = None) -> dict:
    candles = normalize_candles(raw_candles)
    if len(candles) < 30:
        return {
            "signal": "NEUTRAL",
            "confidence": 50,
            "price": candles[-1]["close"] if candles else 0.0,
            "atr": 0.0,
            "rsi": 50.0,
            "adx": 0.0,
            "stoch": 50.0,
            "pattern": "None",
            "structure": "WAIT",
            "ob": "None",
            "reasons": ["البيانات غير كافية بعد (أقل من 30 شمعة)."],
            "conflicts": [],
            "alert": "⏳ جاري تجميع بيانات كافية للتحليل...",
            "alert_type": "info",
            "closes": [c["close"] for c in candles],
        }

    strat = strategy or StrategyManager.DEFAULT_STRATEGIES[0]
    closes = [c["close"] for c in candles]
    price = closes[-1]

    ema9 = calc_ema_series(closes, int(strat.get("ema_fast", 9)))[-1]
    ema21 = calc_ema_series(closes, int(strat.get("ema_slow", 21)))[-1]
    ema50 = calc_ema_series(closes, 50)[-1]
    ema200 = calc_ema_series(closes, min(200, len(closes)))[-1]
    rsi = calc_rsi(closes, 14)
    macd_val, macd_sig, macd_hist = calc_macd(closes)
    atr = calc_true_atr(candles, 14)
    bb_up, bb_mid, bb_lo = calc_bollinger(closes, 20, 2.0)
    stoch = calc_stochastic(candles, 14)
    adx = calc_adx(candles, 14)
    pattern = detect_candlestick_pattern(candles)
    smc = detect_structure_smc(candles)

    score = 0
    reasons = []
    conflicts = []

    if ema9 > ema21:
        score += 20
        reasons.append(f"تقاطع إيجابي EMA{strat.get('ema_fast', 9)} > EMA{strat.get('ema_slow', 21)}")
    else:
        score -= 20
        reasons.append(f"تقاطع سلبي EMA{strat.get('ema_fast', 9)} < EMA{strat.get('ema_slow', 21)}")

    if price > ema50 and ema50 >= ema200:
        score += 15
        reasons.append("الاتجاه العام صاعد (فوق EMA50 وEMA200)")
    elif price < ema50 and ema50 <= ema200:
        score -= 15
        reasons.append("الاتجاه العام هابط (تحت EMA50 وEMA200)")
    else:
        conflicts.append("تعارض بين السعر والمتوسطات الكبرى EMA50/200")

    if macd_hist > 0:
        score += 15
        reasons.append("زخم MACD إيجابي")
    else:
        score -= 15
        reasons.append("زخم MACD سلبي")

    if rsi <= float(strat.get("rsi_buy", 35)):
        score += 15
        reasons.append(f"RSI ({rsi}) في منطقة تشبع بيعي")
    elif rsi >= float(strat.get("rsi_sell", 65)):
        score -= 15
        reasons.append(f"RSI ({rsi}) في منطقة تشبع شرائي")

    if stoch < 25:
        score += 10
        reasons.append(f"Stochastic ({stoch}) يدعم الارتداد الصاعد")
    elif stoch > 75:
        score -= 10
        reasons.append(f"Stochastic ({stoch}) يدعم التصحيح الهابط")

    if "Bullish" in smc["structure"]:
        score += 15
        reasons.append(f"هيكل السوق: {smc['structure']}")
    elif "Bearish" in smc["structure"]:
        score -= 15
        reasons.append(f"هيكل السوق: {smc['structure']}")

    if "Bullish" in pattern or "Hammer" in pattern:
        score += 10
        reasons.append(f"نموذج شمعة: {pattern}")
    elif "Bearish" in pattern or "Shooting" in pattern:
        score -= 10
        reasons.append(f"نموذج شمعة: {pattern}")

    # كشف التذبذب وحالة السوق
    if adx < 18:
        alert = "⚠️ السعر متذبذب (ADX منخفض) — يُنصح بالحذر"
        alert_type = "warn"
        conflicts.append(f"ضعف الاتجاه: ADX = {adx}")
    elif price >= bb_up:
        alert = "🔥 السعر عند الحد العلوي لبولينجر — احتمال تصحيح"
        alert_type = "sell"
    elif price <= bb_lo:
        alert = "💎 السعر عند الحد السفلي لبولينجر — احتمال ارتداد"
        alert_type = "buy"
    elif score >= 35:
        alert = "🚀 زخم صاعد قوي ومتوافق"
        alert_type = "buy"
    elif score <= -35:
        alert = "🔻 زخم هابط قوي ومتوافق"
        alert_type = "sell"
    else:
        alert = "🔍 السوق متوازن — بانتظار تأكيد أوضح"
        alert_type = "info"

    confidence = min(96, 50 + abs(score) // 2)
    signal = "BUY" if score >= 35 else "SELL" if score <= -35 else "NEUTRAL"

    return {
        "signal": signal,
        "confidence": confidence,
        "price": price,
        "ema9": round(ema9, 4),
        "ema21": round(ema21, 4),
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4),
        "rsi": rsi,
        "macd": macd_val,
        "atr": round(atr, 5),
        "bb": (bb_up, bb_mid, bb_lo),
        "stoch": stoch,
        "adx": adx,
        "pattern": pattern,
        "structure": smc["structure"],
        "ob": smc["ob"],
        "sr": smc["sr"],
        "fib": smc["fib"],
        "reasons": reasons,
        "conflicts": conflicts,
        "alert": alert,
        "alert_type": alert_type,
        "closes": closes,
    }


# ==================== إدارة المخاطر ====================
class RiskManager:
    def __init__(self):
        self.risk_percent = 1.0
        self.max_daily_loss_pct = 5.0
        self.max_drawdown_pct = 10.0
        self.daily_loss = 0.0
        self.peak_equity = 0.0
        self.halted = False
        self.halt_reason = ""

    def calculate_lot(self, balance: float, sl_distance: float, pip_value: float = 10.0) -> float:
        if balance <= 0 or sl_distance <= 0:
            return 0.01
        risk_amount = balance * (self.risk_percent / 100.0)
        raw_lot = risk_amount / max(sl_distance * pip_value, 1e-6)
        return round(max(0.01, min(raw_lot, 5.0)), 2)

    def validate_trade(self, balance: float, equity: float, free_margin: float) -> tuple[bool, str]:
        if equity > self.peak_equity:
            self.peak_equity = equity
        if self.peak_equity > 0:
            dd_pct = ((self.peak_equity - equity) / self.peak_equity) * 100
            if dd_pct >= self.max_drawdown_pct:
                self.halted = True
                self.halt_reason = f"تجاوز حد التراجع الأقصى ({dd_pct:.1f}%)"
                return False, self.halt_reason
        if balance > 0 and (abs(self.daily_loss) / balance) * 100 >= self.max_daily_loss_pct:
            self.halted = True
            self.halt_reason = "تجاوز الحد الأقصى للخسارة اليومية"
            return False, self.halt_reason
        if free_margin > 0 and free_margin < balance * 0.15:
            return False, "الهامش المتاح منخفض جداً"
        return True, "OK"


# ==================== نظام Backtesting ====================
def run_backtest(
    raw_candles: list,
    strategy: dict,
    initial_balance: float = 1000.0,
    spread: float = 0.2,
    commission: float = 0.5,
    slippage: float = 0.1,
) -> dict:
    candles = normalize_candles(raw_candles)
    if len(candles) < 40:
        return {"error": "عدد الشموع غير كافٍ للاختبار (مطلوب 40 شمعة على الأقل)."}

    balance = initial_balance
    peak = initial_balance
    max_dd = 0.0
    equity_curve = [balance]
    wins, losses = [], []

    position = None
    for i in range(30, len(candles)):
        sub = candles[: i + 1]
        res = full_market_analysis(sub, strategy)
        price = sub[-1]["close"]
        atr = res["atr"] or (price * 0.002)

        if position:
            side, entry, sl, tp = position
            hit_tp = (side == "BUY" and price >= tp) or (side == "SELL" and price <= tp)
            hit_sl = (side == "BUY" and price <= sl) or (side == "SELL" and price >= sl)
            reverse = (side == "BUY" and res["signal"] == "SELL") or (side == "SELL" and res["signal"] == "BUY")

            if hit_tp or hit_sl or reverse:
                raw_pl = (price - entry) if side == "BUY" else (entry - price)
                net_pl = (raw_pl * 10.0) - spread - commission - slippage
                balance += net_pl
                (wins if net_pl > 0 else losses).append(net_pl)
                position = None
                peak = max(peak, balance)
                dd = ((peak - balance) / peak) * 100 if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                equity_curve.append(round(balance, 2))
        else:
            if res["signal"] in ("BUY", "SELL") and res["confidence"] >= strategy.get("min_conf", 65):
                sl_dist = atr * float(strategy.get("sl_atr", 1.8))
                tp_dist = atr * float(strategy.get("tp_atr", 3.2))
                if res["signal"] == "BUY":
                    position = ("BUY", price + slippage, price - sl_dist, price + tp_dist)
                else:
                    position = ("SELL", price - slippage, price + sl_dist, price - tp_dist)

    total = len(wins) + len(losses)
    win_rate = round((len(wins) / total) * 100, 1) if total else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) or 1e-9
    return {
        "total_trades": total,
        "win_rate": win_rate,
        "net_pl": round(balance - initial_balance, 2),
        "final_balance": round(balance, 2),
        "profit_factor": round(gross_win / gross_loss, 2),
        "max_drawdown": round(max_dd, 2),
        "equity_curve": equity_curve,
    }


# ==================== مساعد الذكاء الاصطناعي التحليلي ====================
def build_ai_explanation(symbol: str, analysis: dict, risk_ok: bool, risk_msg: str) -> str:
    if not analysis or analysis.get("price", 0) == 0:
        return "لا توجد بيانات سوق فعلية بعد. يرجى الاتصال بالوسيط وتحديث الشارت أولاً."

    reasons_txt = "\n".join(f"• {r}" for r in analysis.get("reasons", []))
    conflicts_txt = (
        "\n".join(f"⚠️ {c}" for c in analysis.get("conflicts", []))
        if analysis.get("conflicts")
        else "✅ لا توجد تعارضات جوهرية بين المؤشرات."
    )
    risk_txt = "✅ المخاطر ضمن الحدود الآمنة." if risk_ok else f"🛑 تحذير مخاطر: {risk_msg}"

    return (
        f"📊 التقرير الذكي للأصل {symbol} (السعر الفعلي: {analysis['price']}):\n"
        f"• الإشارة: {analysis['signal']} (درجة التوافق: {analysis['confidence']}% — ليست ضماناً للربح)\n"
        f"• هيكل السوق: {analysis['structure']} | Order Block: {analysis['ob']}\n"
        f"• المؤشرات: RSI={analysis['rsi']} | ADX={analysis['adx']} | Stoch={analysis['stoch']} | ATR={analysis['atr']}\n"
        f"• نموذج الشمعة: {analysis['pattern']}\n\n"
        f"🔎 أسباب الإشارة:\n{reasons_txt}\n\n"
        f"⚖️ تعارض المؤشرات:\n{conflicts_txt}\n\n"
        f"🛡️ تقييم المخاطر:\n{risk_txt}"
    )
