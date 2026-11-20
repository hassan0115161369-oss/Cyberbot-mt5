import asyncio
import os
import random
import uuid
from datetime import datetime
import flet as ft
import httpx

from engine import (
    JournalManager,
    LocalAuthManager,
    RiskManager,
    StrategyManager,
    build_ai_explanation,
    full_market_analysis,
    run_backtest,
)

# ==================== الهوية البصرية Cyber Neon ====================
BG_DARK = "#05070D"
BG_GRAD_1 = "#080C18"
BG_GRAD_2 = "#140A28"
NEON_PURPLE = "#A855F7"
NEON_CYAN = "#00F5D4"
NEON_GOLD = "#FFD700"
NEON_RED = "#FF2E63"
NEON_GREEN = "#00FF9C"
NEON_ORANGE = "#FF9F1C"
CARD_BG = "#BF101628"
WHITE = "#FFFFFF"
WHITE_70 = "#B3FFFFFF"
WHITE_54 = "#8AFFFFFF"

DEFAULT_API_KEY = os.getenv("TICKERALL_API_KEY", "")
TICKERALL_BASE_URL = os.getenv("TICKERALL_BASE_URL", "https://api.tickerall.com/v1")

TF_MAP = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4"}

SIM_BASE_PRICES = {
    "XAUUSD": 2650.0,
    "BTCUSD": 92000.0,
    "EURUSD": 1.0850,
    "GBPUSD": 1.2700,
    "US30": 43500.0,
}

# ==================== دعم اللغتين العربية والإنجليزية ====================
TEXTS = {
    "AR": {
        "dashboard": "لوحة التحكم",
        "analysis": "التحليل الذكي",
        "scanner": "فاحص الأصول",
        "risk": "المخاطر",
        "strategy": "الاستراتيجيات",
        "backtest": "الاختبار التاريخي",
        "perf": "الأداء",
        "journal": "السجل",
        "account": "الحساب",
        "connection": "الاتصال",
        "start": "تشغيل البوت",
        "stop": "إيقاف البوت",
        "sim_badge": "وضع المحاكاة (آمن)",
        "live_badge": "وضع التداول الحقيقي ⚠️",
    },
    "EN": {
        "dashboard": "Dashboard",
        "analysis": "AI Analysis",
        "scanner": "Asset Scanner",
        "risk": "Risk Manager",
        "strategy": "Strategy Lab",
        "backtest": "Backtesting",
        "perf": "Analytics",
        "journal": "Trade Journal",
        "account": "Account",
        "connection": "Connection",
        "start": "START BOT",
        "stop": "STOP BOT",
        "sim_badge": "SIMULATION MODE",
        "live_badge": "LIVE TRADING ⚠️",
    },
}


# ==================== عميل TickerAll API (يدعم Headway و MFNT) ====================
class TickerAllClient:
    def __init__(self, api_key: str, base_url: str = TICKERALL_BASE_URL):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.account_id = None
        self.last_creds = None
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=20.0,
        )

    async def connect(self, login: str, password: str, server: str):
        acc_num = int(login) if login.isdigit() else login
        payload = {
            "broker": "mt5",
            "server": server,
            "account": acc_num,
            "password": password,
        }
        resp = await self.client.post("/sessions", json=payload)
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code} | {resp.text}")
        data = resp.json()
        self.account_id = data.get("accountId") or data.get("id")
        if not self.account_id:
            raise ValueError(f"لم يتم استلام accountId من الخادم: {data}")
        self.last_creds = (login, password, server)
        return data

    async def reconnect(self):
        if not self.last_creds:
            return False
        await self.connect(*self.last_creds)
        return True

    async def get_account_info(self):
        resp = await self.client.get(f"/accounts/{self.account_id}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("account", data)

    async def get_candles(self, symbol: str, timeframe: str = "1m", hours: int = 24):
        tf = TF_MAP.get(timeframe, "M1")
        params = {"symbol": symbol, "timeframe": tf, "hours": hours}
        resp = await self.client.get(f"/accounts/{self.account_id}/candles", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("candles", [])

    async def get_positions(self):
        resp = await self.client.get(f"/accounts/{self.account_id}/positions")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("positions", [])

    async def close_position(self, position_id: str):
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        resp = await self.client.delete(
            f"/accounts/{self.account_id}/positions/{position_id}",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json() if resp.text else {"closed": True}

    async def place_order(self, symbol: str, side: str, volume: float, sl: float, tp: float, comment: str):
        payload = {
            "type": "market",
            "symbol": symbol,
            "side": side.lower(),
            "volume": volume,
            "sl": sl,
            "tp": tp,
            "comment": comment,
        }
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        resp = await self.client.post(
            f"/accounts/{self.account_id}/orders",
            json=payload,
            headers=headers,
        )

        # إذا رفض MT5 الأمر بسبب SL/TP (409)، نجرب الفتح بدون SL/TP
        if resp.status_code == 409:
            simple_payload = {
                "type": "market",
                "symbol": symbol,
                "side": side.lower(),
                "volume": volume,
                "comment": comment,
            }
            resp = await self.client.post(
                f"/accounts/{self.account_id}/orders",
                json=simple_payload,
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )

        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code} | {resp.text}")
        return resp.json()


# ==================== حالة التطبيق الشاملة ====================
class AppState:
    def __init__(self):
        self.lang = "AR"
        self.current_user = None
        self.auth = LocalAuthManager()
        self.journal = JournalManager()
        self.strat_mgr = StrategyManager()
        self.risk = RiskManager()
        self.active_strategy = self.strat_mgr.strategies[0]

        self.client: TickerAllClient | None = None
        self.connected = False
        self.live_trading_enabled = False
        self.running = False
        self.bot_task: asyncio.Task | None = None

        self.symbol = "XAUUSD"
        self.timeframe = "1m"
        self.lot = 0.01
        self.watchlist = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "US30"]

        self.balance = 10000.0
        self.equity = 10000.0
        self.free_margin = 10000.0
        self.profit = 0.0

        self.sim_positions = []
        self.sim_candles_cache: dict[str, list[dict]] = {}
        self.last_analysis = {}
        self.last_candles = []
        self.logs = []
        self.page = None
        self.log_list = None


state = AppState()


# ==================== مولّد شموع المحاكاة ====================
def get_simulated_candles(symbol: str, count: int = 80) -> list[dict]:
    base = SIM_BASE_PRICES.get(symbol, 100.0)
    step = base * 0.0008
    candles = state.sim_candles_cache.get(symbol)

    if not candles:
        candles = []
        price = base
        for _ in range(count):
            o = price
            c = o + random.uniform(-step, step)
            h = max(o, c) + random.uniform(0, step * 0.5)
            l = min(o, c) - random.uniform(0, step * 0.5)
            candles.append({"open": o, "high": h, "low": l, "close": c, "volume": random.randint(50, 500)})
            price = c
        state.sim_candles_cache[symbol] = candles
    else:
        last_close = candles[-1]["close"]
        o = last_close
        c = o + random.uniform(-step, step)
        h = max(o, c) + random.uniform(0, step * 0.5)
        l = min(o, c) - random.uniform(0, step * 0.5)
        candles.append({"open": o, "high": h, "low": l, "close": c, "volume": random.randint(50, 500)})
        if len(candles) > 200:
            candles.pop(0)

    return candles


# ==================== عناصر الواجهة المساعدة ====================
def t(key: str) -> str:
    return TEXTS.get(state.lang, TEXTS["AR"]).get(key, key)


def neon_card(content, padding=14, border_color=NEON_PURPLE, glow_color=NEON_PURPLE):
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=CARD_BG,
        border=ft.Border.all(1.5, border_color),
        border_radius=16,
        shadow=ft.BoxShadow(blur_radius=14, color=glow_color, spread_radius=0),
    )


def neon_btn(text, icon, color, on_click, width=None, height=48, expand=False):
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, color=BG_DARK, size=20),
                ft.Text(text, color=BG_DARK, weight=ft.FontWeight.BOLD, size=13),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        ),
        width=width,
        height=height,
        expand=expand,
        alignment=ft.Alignment(0, 0),
        bgcolor=color,
        border_radius=12,
        shadow=ft.BoxShadow(blur_radius=14, color=color, spread_radius=1),
        on_click=on_click,
        ink=True,
    )


def build_neon_chart(values: list[float], title_prefix="السعر"):
    if not values or len(values) < 2:
        return ft.Container(
            height=105,
            alignment=ft.Alignment(0, 0),
            content=ft.Text("لا توجد بيانات شارت بعد...", color=WHITE_54, size=12),
        )
    data = values[-24:]
    min_p, max_p = min(data), max(data)
    span = (max_p - min_p) or 1e-6
    bars = []
    for i, val in enumerate(data):
        prev = data[i - 1] if i > 0 else val
        c = NEON_GREEN if val >= prev else NEON_RED
        h = int(10 + ((val - min_p) / span) * 76)
        bars.append(ft.Container(width=7, height=h, bgcolor=c, border_radius=3))
    digits = 2 if max_p > 50 else 5
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Text(f"H: {max_p:.{digits}f}", size=11, color=NEON_GREEN),
                    ft.Text(f"{title_prefix}: {data[-1]:.{digits}f}", size=12, color=NEON_GOLD, weight=ft.FontWeight.BOLD),
                    ft.Text(f"L: {min_p:.{digits}f}", size=11, color=NEON_RED),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Container(
                height=90,
                content=ft.Row(bars, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.END),
            ),
        ],
        spacing=4,
    )


def add_log(msg: str):
    stamp = datetime.now().strftime("%H:%M:%S")
    state.logs.insert(0, f"[{stamp}] {msg}")
    if len(state.logs) > 80:
        state.logs.pop()
    if state.log_list is not None:
        state.log_list.controls = [ft.Text(item, size=11, color=WHITE_70) for item in state.logs]
        if state.page:
            state.page.update()


# ==================== التطبيق الرئيسي ====================
async def main(page: ft.Page):
    state.page = page
    page.title = "CYBERBOT MT5 PRO v4.0 ULTIMATE AI"
    page.bgcolor = BG_DARK
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    splash = ft.SafeArea(
        expand=True,
        content=ft.Container(
            expand=True,
            gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1), colors=[BG_GRAD_1, BG_GRAD_2]),
            content=ft.Column(
                [
                    ft.Container(height=90),
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=92, color=NEON_CYAN),
                    ft.Text("CYBERBOT MT5 PRO", size=30, color=NEON_GOLD, weight=ft.FontWeight.BOLD),
                    ft.Text("v4.0 ULTIMATE AI • MFNT & MT5 EDITION", size=13, color=NEON_PURPLE, weight=ft.FontWeight.BOLD),
                    ft.Text("جاري تهيئة المحرك التحليلي ونظام إدارة المخاطر...", size=12, color=WHITE_70),
                    ft.ProgressBar(width=250, color=NEON_CYAN, bgcolor=CARD_BG),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        ),
    )

    async def fetch_market_data(symbol: str, tf: str):
        if state.connected and state.client:
            try:
                hours = 8 if tf in ("1m", "5m") else 72
                return await state.client.get_candles(symbol, tf, hours=hours)
            except Exception as e:
                add_log(f"⚠️ انقطع جلب البيانات ({e}) - جاري إعادة الاتصال...")
                try:
                    await state.client.reconnect()
                except Exception:
                    pass
        return get_simulated_candles(symbol)

    async def execute_trade(side: str, price: float, atr: float, tag: str = "AI"):
        if price <= 0:
            add_log("⚠️ لا يوجد سعر فعلي لتنفيذ الصفقة.")
            return
        ok, risk_msg = state.risk.validate_trade(state.balance, state.equity, state.free_margin)
        if not ok:
            state.running = False
            add_log(f"🛑 تم إيقاف النظام تلقائياً: {risk_msg}")
            return

        sl_dist = max(atr * float(state.active_strategy.get("sl_atr", 1.8)), price * 0.0025)
        tp_dist = max(atr * float(state.active_strategy.get("tp_atr", 3.2)), price * 0.005)
        digits = 2 if price > 50 else 5
        sl = round(price - sl_dist if side == "BUY" else price + sl_dist, digits)
        tp = round(price + tp_dist if side == "BUY" else price - tp_dist, digits)

        if not state.live_trading_enabled:
            pos = {
                "id": f"SIM-{str(uuid.uuid4())[:6]}",
                "symbol": state.symbol,
                "side": side,
                "volume": state.lot,
                "entry": price,
                "sl": sl,
                "tp": tp,
                "profit": 0.0,
                "mode": "SIM",
            }
            state.sim_positions.append(pos)
            add_log(f"🧪 [محاكاة] {side} {state.symbol} لوت {state.lot} @ {price:.{digits}f}")
            return

        if not state.connected or not state.client:
            add_log("⚠️ يرجى الاتصال بالوسيط أولاً لتنفيذ أوامر حقيقية.")
            return
        try:
            await state.client.place_order(state.symbol, side, state.lot, sl, tp, f"CyberBot4 {tag}")
            add_log(f"⚡ [حقيقي] {side} {state.symbol} لوت {state.lot} @ {price:.{digits}f}")
        except Exception as e:
            add_log(f"❌ فشل تنفيذ الأمر الحقيقي: {e}")

    def build_main_app():
        current_tab = {"name": "dashboard"}
        content_holder = ft.Container(expand=True)

        bal_txt = ft.Text(f"${state.balance:,.2f}", size=24, color=NEON_GOLD, weight=ft.FontWeight.BOLD)
        eq_txt = ft.Text(f"${state.equity:,.2f}", size=14, color=NEON_CYAN)
        mg_txt = ft.Text(f"${state.free_margin:,.2f}", size=14, color=NEON_PURPLE)
        pl_txt = ft.Text(f"${state.profit:,.2f}", size=14, color=NEON_GREEN)
        mode_badge = ft.Text(
            t("live_badge") if state.live_trading_enabled else t("sim_badge"),
            size=12,
            color=NEON_RED if state.live_trading_enabled else NEON_GREEN,
            weight=ft.FontWeight.BOLD,
        )
        alert_txt = ft.Text("رادار السوق جاهز", size=12, color=NEON_CYAN, expand=True)
        sig_txt = ft.Text("READY ⚡", size=20, color=NEON_CYAN, weight=ft.FontWeight.BOLD)
        chart_box = ft.Container(content=build_neon_chart([]))
        state.log_list = ft.ListView(expand=True, spacing=4, height=130)

        sym_dd = ft.Dropdown(
            options=[ft.dropdown.Option(s) for s in state.watchlist],
            value=state.symbol,
            bgcolor=BG_GRAD_1,
            border_color=NEON_CYAN,
            color=WHITE,
            label="الأصل",
            expand=True,
        )
        tf_dd = ft.Dropdown(
            options=[ft.dropdown.Option(x) for x in ["1m", "5m", "15m", "30m", "1h", "4h"]],
            value=state.timeframe,
            bgcolor=BG_GRAD_1,
            border_color=NEON_PURPLE,
            color=WHITE,
            label="الفريم",
            width=105,
        )

        async def refresh_all(auto_trade=False):
            state.symbol = sym_dd.value or state.symbol
            state.timeframe = tf_dd.value or state.timeframe

            if state.connected and state.client:
                try:
                    info = await state.client.get_account_info()
                    state.balance = float(info.get("balance", state.balance))
                    state.equity = float(info.get("equity", state.equity))
                    state.free_margin = float(info.get("freeMargin", info.get("marginFree", state.equity)))
                    state.profit = float(info.get("profit", 0.0))
                except Exception:
                    pass

            candles = await fetch_market_data(state.symbol, state.timeframe)
            if candles:
                state.last_candles = candles
                res = full_market_analysis(candles, state.active_strategy)
                state.last_analysis = res
                chart_box.content = build_neon_chart(res["closes"])
                sig_txt.value = f"{res['signal']} {res['confidence']}%"
                sig_txt.color = NEON_GREEN if res["signal"] == "BUY" else NEON_RED if res["signal"] == "SELL" else NEON_CYAN
                alert_txt.value = res["alert"]

                price = res["price"]
                for p in list(state.sim_positions):
                    if p["symbol"] == state.symbol:
                        diff = (price - p["entry"]) if p["side"] == "BUY" else (p["entry"] - price)
                        p["profit"] = round(diff * p["volume"] * 100, 2)
                        if p["profit"] > 2.0 and p["sl"] != p["entry"]:
                            p["sl"] = p["entry"]
                            add_log(f"🛡️ Break-Even مفعل لصفقة {p['id']}")
                        if (p["side"] == "BUY" and res["signal"] == "SELL") or (p["side"] == "SELL" and res["signal"] == "BUY"):
                            state.sim_positions.remove(p)
                            state.balance += p["profit"]
                            state.journal.add_trade(p)
                            add_log(f"⚡ إغلاق فوري عند الانقلاب {p['id']} ({p['profit']:+.2f}$)")

                if not state.connected:
                    state.profit = round(sum(p["profit"] for p in state.sim_positions), 2)
                    state.equity = round(state.balance + state.profit, 2)
                    state.free_margin = state.equity

                if auto_trade and res["signal"] in ("BUY", "SELL") and res["confidence"] >= state.active_strategy.get("min_conf", 65):
                    same = [p for p in state.sim_positions if p["symbol"] == state.symbol and p["side"] == res["signal"]]
                    if not same:
                        await execute_trade(res["signal"], price, res["atr"], tag="AI")

            bal_txt.value = f"${state.balance:,.2f}"
            eq_txt.value = f"${state.equity:,.2f}"
            mg_txt.value = f"${state.free_margin:,.2f}"
            pl_txt.value = f"${state.profit:,.2f}"
            pl_txt.color = NEON_GREEN if state.profit >= 0 else NEON_RED
            page.update()

        async def bot_loop():
            while state.running:
                try:
                    await refresh_all(auto_trade=True)
                    await asyncio.sleep(4)
                except Exception as e:
                    add_log(f"⚠️ خطأ في الحلقة: {e}")
                    await asyncio.sleep(4)

        async def start_bot(e):
            if state.running:
                return
            state.running = True
            add_log(f"🚀 تم تشغيل المحرك على {state.symbol} ({'حقيقي' if state.live_trading_enabled else 'محاكاة'})")
            state.bot_task = asyncio.create_task(bot_loop())

        def stop_bot(e):
            state.running = False
            add_log("⏹️ تم إيقاف المحرك")
            page.update()

        def view_dashboard():
            lot_row = []
            for v in [0.01, 0.05, 0.1, 0.5, 1.0]:
                def _set_lot(ev, val=v):
                    state.lot = val
                    add_log(f"💰 حجم اللوت: {val}")
                    render_tab("dashboard")

                lot_row.append(
                    ft.Container(
                        content=ft.Text(str(v), color=BG_DARK if state.lot == v else WHITE, size=12, weight=ft.FontWeight.BOLD),
                        padding=ft.Padding(left=11, top=7, right=11, bottom=7),
                        bgcolor=NEON_GOLD if state.lot == v else BG_GRAD_1,
                        border=ft.Border.all(1, NEON_GOLD),
                        border_radius=8,
                        on_click=_set_lot,
                    )
                )

            return ft.Column(
                [
                    ft.Row([ft.Text("CYBERBOT v4.0", size=18, color=NEON_CYAN, weight=ft.FontWeight.BOLD), mode_badge], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    neon_card(
                        ft.Column([
                            ft.Text("Balance", size=11, color=WHITE_54),
                            bal_txt,
                            ft.Row([ft.Text("Equity:", size=11, color=WHITE_54), eq_txt, ft.Text("Margin:", size=11, color=WHITE_54), mg_txt, ft.Text("P/L:", size=11, color=WHITE_54), pl_txt], wrap=True, spacing=8),
                        ], spacing=4),
                        border_color=NEON_GOLD,
                    ),
                    neon_card(ft.Row([ft.Icon(ft.Icons.RADAR, color=NEON_CYAN, size=20), alert_txt], spacing=8), padding=10, border_color=NEON_CYAN),
                    ft.Row([sym_dd, tf_dd], spacing=8),
                    neon_card(chart_box, border_color=NEON_CYAN),
                    neon_card(ft.Column([ft.Text(f"حجم اللوت: {state.lot}", size=12, color=NEON_GOLD), ft.Row(lot_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)], spacing=6), padding=10, border_color=NEON_GOLD),
                    neon_card(
                        ft.Column([
                            ft.Row([ft.Text("AI SIGNAL", size=12, color=WHITE_54), sig_txt], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Row([
                                neon_btn(t("start"), ft.Icons.PLAY_ARROW, NEON_GREEN, start_bot, expand=True),
                                neon_btn(t("stop"), ft.Icons.STOP, NEON_RED, stop_bot, expand=True),
                            ], spacing=8),
                            ft.Row([
                                neon_btn("BUY", ft.Icons.TRENDING_UP, NEON_GREEN, lambda e: asyncio.create_task(execute_trade("BUY", state.last_analysis.get("price", 0), state.last_analysis.get("atr", 0), "MANUAL")), height=42, expand=True),
                                neon_btn("SELL", ft.Icons.TRENDING_DOWN, NEON_RED, lambda e: asyncio.create_task(execute_trade("SELL", state.last_analysis.get("price", 0), state.last_analysis.get("atr", 0), "MANUAL")), height=42, expand=True),
                            ], spacing=8),
                        ], spacing=8),
                    ),
                    neon_card(ft.Column([ft.Text("LIVE TERMINAL", size=11, color=WHITE_54), state.log_list], spacing=4), border_color=NEON_CYAN),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_ai_analysis():
            ok, rmsg = state.risk.validate_trade(state.balance, state.equity, state.free_margin)
            report = build_ai_explanation(state.symbol, state.last_analysis, ok, rmsg)
            report_txt = ft.Text(report, size=12, color=WHITE, selectable=True)

            async def _refresh_ai(e):
                await refresh_all(auto_trade=False)
                ok2, rm2 = state.risk.validate_trade(state.balance, state.equity, state.free_margin)
                report_txt.value = build_ai_explanation(state.symbol, state.last_analysis, ok2, rm2)
                page.update()

            return ft.Column(
                [
                    ft.Text("المساعد الذكي والتحليل الشامل", size=18, color=NEON_CYAN, weight=ft.FontWeight.BOLD),
                    neon_btn("تحديث التحليل الفوري", ft.Icons.PSYCHOLOGY, NEON_PURPLE, _refresh_ai),
                    neon_card(report_txt, border_color=NEON_CYAN),
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_scanner():
            search_f = ft.TextField(label="إضافة رمز للبحث/المراقبة (مثل XAUUSDm)", bgcolor=CARD_BG, border_color=NEON_CYAN, color=WHITE)
            results_col = ft.Column(spacing=8)

            def _add_sym(e):
                s = (search_f.value or "").strip()
                if s and s not in state.watchlist:
                    state.watchlist.append(s)
                    sym_dd.options = [ft.dropdown.Option(x) for x in state.watchlist]
                    search_f.value = ""
                    add_log(f"➕ تمت إضافة {s} لقائمة المراقبة")
                    page.update()

            async def _scan_all(e):
                results_col.controls.clear()
                results_col.controls.append(ft.Text("⏳ جاري فحص الأصول...", color=NEON_CYAN))
                page.update()
                ranked = []
                for sym in state.watchlist:
                    c = await fetch_market_data(sym, state.timeframe)
                    if c:
                        r = full_market_analysis(c, state.active_strategy)
                        ranked.append((r["confidence"], sym, r))
                ranked.sort(key=lambda x: x[0], reverse=True)
                results_col.controls.clear()
                for conf, sym, r in ranked:
                    col = NEON_GREEN if r["signal"] == "BUY" else NEON_RED if r["signal"] == "SELL" else NEON_CYAN
                    results_col.controls.append(
                        neon_card(
                            ft.Row([
                                ft.Column([ft.Text(sym, size=15, color=WHITE, weight=ft.FontWeight.BOLD), ft.Text(r["structure"], size=11, color=WHITE_70)]),
                                ft.Text(f"{r['signal']} {conf}%", size=15, color=col, weight=ft.FontWeight.BOLD),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            padding=10,
                            border_color=col,
                        )
                    )
                page.update()

            return ft.Column(
                [
                    ft.Text("محرك فحص الأصول (Asset Scanner)", size=18, color=NEON_CYAN, weight=ft.FontWeight.BOLD),
                    ft.Row([ft.Container(search_f, expand=True), neon_btn("إضافة", ft.Icons.ADD, NEON_GOLD, _add_sym, width=90)]),
                    neon_btn("فحص وترتيب جميع الأصول", ft.Icons.SEARCH, NEON_CYAN, _scan_all),
                    results_col,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_risk():
            rp_f = ft.TextField(label="نسبة المخاطرة لكل صفقة (%)", value=str(state.risk.risk_percent), bgcolor=CARD_BG, border_color=NEON_GOLD, color=WHITE)
            dl_f = ft.TextField(label="الحد الأقصى للخسارة اليومية (%)", value=str(state.risk.max_daily_loss_pct), bgcolor=CARD_BG, border_color=NEON_RED, color=WHITE)
            dd_f = ft.TextField(label="الحد الأقصى للتراجع Max Drawdown (%)", value=str(state.risk.max_drawdown_pct), bgcolor=CARD_BG, border_color=NEON_RED, color=WHITE)
            calc_out = ft.Text("", color=NEON_GREEN, size=13)

            def _save_risk(e):
                try:
                    state.risk.risk_percent = float(rp_f.value)
                    state.risk.max_daily_loss_pct = float(dl_f.value)
                    state.risk.max_drawdown_pct = float(dd_f.value)
                    atr = state.last_analysis.get("atr", 1.0) or 1.0
                    rec_lot = state.risk.calculate_lot(state.balance, atr * 2)
                    state.lot = rec_lot
                    calc_out.value = f"✅ تم الحفظ • اللوت المحسوب وفق مخاطرتك: {rec_lot}"
                    page.update()
                except Exception:
                    calc_out.value = "❌ يرجى إدخال أرقام صحيحة"
                    page.update()

            return ft.Column(
                [
                    ft.Text("إدارة المخاطر (Risk Manager)", size=18, color=NEON_GOLD, weight=ft.FontWeight.BOLD),
                    rp_f, dl_f, dd_f,
                    neon_btn("حفظ وحساب اللوت الآمن", ft.Icons.SHIELD, NEON_GOLD, _save_risk),
                    calc_out,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_strategy():
            s = state.active_strategy
            name_f = ft.TextField(label="اسم الاستراتيجية", value=s["name"], bgcolor=CARD_BG, border_color=NEON_PURPLE, color=WHITE)
            ef_f = ft.TextField(label="EMA السريع", value=str(s["ema_fast"]), bgcolor=CARD_BG, border_color=NEON_CYAN, color=WHITE)
            es_f = ft.TextField(label="EMA البطيء", value=str(s["ema_slow"]), bgcolor=CARD_BG, border_color=NEON_CYAN, color=WHITE)
            mc_f = ft.TextField(label="الحد الأدنى للثقة (%)", value=str(s["min_conf"]), bgcolor=CARD_BG, border_color=NEON_GOLD, color=WHITE)
            st_msg = ft.Text("", color=NEON_GREEN)

            def _save_strat(e):
                try:
                    new_s = {
                        "name": name_f.value.strip() or "Custom AI",
                        "ema_fast": int(ef_f.value),
                        "ema_slow": int(es_f.value),
                        "rsi_buy": 35,
                        "rsi_sell": 65,
                        "min_conf": int(mc_f.value),
                        "sl_atr": 1.8,
                        "tp_atr": 3.2,
                    }
                    state.strat_mgr.save_strategy(new_s)
                    state.active_strategy = new_s
                    st_msg.value = f"✅ تم حفظ وتفعيل الاستراتيجية: {new_s['name']}"
                    page.update()
                except Exception:
                    st_msg.value = "❌ تأكد من صحة الأرقام"
                    page.update()

            return ft.Column(
                [
                    ft.Text("مختبر الاستراتيجيات (Strategy Lab)", size=18, color=NEON_PURPLE, weight=ft.FontWeight.BOLD),
                    name_f, ef_f, es_f, mc_f,
                    neon_btn("حفظ وتفعيل الاستراتيجية", ft.Icons.SCIENCE, NEON_PURPLE, _save_strat),
                    st_msg,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_backtest():
            bt_out = ft.Column(spacing=8)

            async def _run_bt(e):
                bt_out.controls.clear()
                bt_out.controls.append(ft.Text("⏳ جاري تشغيل الاختبار التاريخي...", color=NEON_CYAN))
                page.update()
                candles = state.last_candles or await fetch_market_data(state.symbol, state.timeframe)
                res = run_backtest(candles, state.active_strategy)
                bt_out.controls.clear()
                if "error" in res:
                    bt_out.controls.append(ft.Text(f"⚠️ {res['error']}", color=NEON_ORANGE))
                else:
                    bt_out.controls.append(
                        neon_card(
                            ft.Column([
                                ft.Text(f"عدد الصفقات: {res['total_trades']} | نسبة النجاح: {res['win_rate']}%", color=WHITE),
                                ft.Text(f"صافي الربح: ${res['net_pl']} | Profit Factor: {res['profit_factor']}", color=NEON_GREEN if res["net_pl"] >= 0 else NEON_RED),
                                ft.Text(f"أقصى تراجع (Max DD): {res['max_drawdown']}%", color=NEON_ORANGE),
                                build_neon_chart(res["equity_curve"], title_prefix="الرصيد"),
                            ], spacing=6),
                            border_color=NEON_CYAN,
                        )
                    )
                page.update()

            return ft.Column(
                [
                    ft.Text(f"الاختبار التاريخي ({state.symbol} - {state.timeframe})", size=18, color=NEON_CYAN, weight=ft.FontWeight.BOLD),
                    neon_btn("تشغيل Backtest الآن", ft.Icons.HISTORY, NEON_CYAN, _run_bt),
                    bt_out,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_perf():
            st = state.journal.get_stats()
            return ft.Column(
                [
                    ft.Text("تحليلات الأداء (Performance Analytics)", size=18, color=NEON_GOLD, weight=ft.FontWeight.BOLD),
                    neon_card(
                        ft.Column([
                            ft.Text(f"إجمالي الصفقات المغلقة: {st['total']}", size=14, color=WHITE),
                            ft.Text(f"نسبة النجاح (Win Rate): {st['win_rate']}%", size=14, color=NEON_CYAN),
                            ft.Text(f"صافي الأرباح: ${st['net_pl']}", size=16, color=NEON_GREEN if st["net_pl"] >= 0 else NEON_RED, weight=ft.FontWeight.BOLD),
                            ft.Text(f"معامل الربح (Profit Factor): {st['profit_factor']}", size=14, color=NEON_GOLD),
                        ], spacing=8),
                        border_color=NEON_GOLD,
                    ),
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_journal():
            pos_col = ft.Column(spacing=6)
            for p in state.sim_positions:
                def _close_sim(ev, pid=p["id"]):
                    for x in list(state.sim_positions):
                        if x["id"] == pid:
                            state.sim_positions.remove(x)
                            state.balance += x["profit"]
                            state.journal.add_trade(x)
                            add_log(f"🔒 تم إغلاق {pid} يدوياً ({x['profit']:+.2f}$)")
                    render_tab("journal")

                pos_col.controls.append(
                    neon_card(
                        ft.Row([
                            ft.Text(f"{p['symbol']} {p['side']} ({p['volume']}) | P/L: {p['profit']:+.2f}$", size=12, color=WHITE),
                            neon_btn("إغلاق", ft.Icons.CLOSE, NEON_RED, _close_sim, width=85, height=34),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        padding=8,
                        border_color=NEON_PURPLE,
                    )
                )

            hist_col = ft.Column([
                ft.Text(f"[{j.get('timestamp','')}] {j.get('symbol')} {j.get('side')} | {j.get('profit',0):+.2f}$", size=11, color=WHITE_70)
                for j in state.journal.entries[:20]
            ], spacing=4)

            return ft.Column(
                [
                    ft.Text("الصفقات المفتوحة وسجل الصفقات", size=18, color=NEON_CYAN, weight=ft.FontWeight.BOLD),
                    pos_col if pos_col.controls else ft.Text("لا توجد صفقات مفتوحة حالياً.", color=WHITE_54),
                    neon_card(ft.Column([ft.Text("سجل الصفقات المغلقة:", color=NEON_GOLD), hist_col], spacing=6)),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_account():
            def _toggle_lang(e):
                state.lang = "EN" if state.lang == "AR" else "AR"
                page.controls.clear()
                page.controls.append(build_main_app())
                page.update()

            def _logout(e):
                state.running = False
                state.current_user = None
                page.controls.clear()
                page.controls.append(build_auth_view())
                page.update()

            uname = state.current_user["username"] if state.current_user else "Guest"
            return ft.Column(
                [
                    ft.Text("إعدادات الحساب والملف الشخصي", size=18, color=NEON_PURPLE, weight=ft.FontWeight.BOLD),
                    neon_card(ft.Column([
                        ft.Text(f"المستخدم: {uname}", size=15, color=WHITE, weight=ft.FontWeight.BOLD),
                        ft.Text(f"اللغة الحالية: {state.lang}", size=13, color=NEON_CYAN),
                    ], spacing=6)),
                    neon_btn("تبديل اللغة (AR / EN)", ft.Icons.LANGUAGE, NEON_CYAN, _toggle_lang),
                    neon_btn("تسجيل الخروج", ft.Icons.LOGOUT, NEON_RED, _logout),
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        def view_connection():
            tok_f = ft.TextField(label="TickerAll API Key", value=DEFAULT_API_KEY, password=True, can_reveal_password=True, bgcolor=CARD_BG, border_color=NEON_PURPLE, color=WHITE)
            acc_f = ft.TextField(label="MT5 / MFNT Account ID", bgcolor=CARD_BG, border_color=NEON_CYAN, color=WHITE)
            pwd_f = ft.TextField(label="MT5 Password", password=True, can_reveal_password=True, bgcolor=CARD_BG, border_color=NEON_CYAN, color=WHITE)
            srv_dd = ft.Dropdown(
                label="الخادم (MFNT / Headway / مخصص)",
                options=[
                    ft.dropdown.Option("MFNT-Demo"),
                    ft.dropdown.Option("MFNT-Live"),
                    ft.dropdown.Option("Headway-Demo"),
                    ft.dropdown.Option("Headway-Real"),
                    ft.dropdown.Option("Custom"),
                ],
                value="MFNT-Demo",
                bgcolor=BG_GRAD_1,
                border_color=NEON_CYAN,
                color=WHITE,
            )
            custom_srv = ft.TextField(label="اسم الخادم المخصص (اختياري)", bgcolor=CARD_BG, border_color=NEON_PURPLE, color=WHITE)
            conn_status = ft.Text("✅ متصل" if state.connected else "⚪ غير متصل (وضع المحاكاة يعمل)", color=NEON_GREEN if state.connected else NEON_ORANGE)
            live_sw = ft.Switch(label="تفعيل التداول الحقيقي (تحذير: يرسل أوامر فعلية)", value=state.live_trading_enabled, active_color=NEON_RED)

            def _on_live_toggle(e):
                state.live_trading_enabled = bool(live_sw.value)
                mode_badge.value = t("live_badge") if state.live_trading_enabled else t("sim_badge")
                mode_badge.color = NEON_RED if state.live_trading_enabled else NEON_GREEN
                add_log("⚠️ تم تفعيل التداول الحقيقي!" if state.live_trading_enabled else "🧪 العودة لوضع المحاكاة الآمن")
                page.update()

            live_sw.on_change = _on_live_toggle

            async def _do_connect(e):
                srv = custom_srv.value.strip() if srv_dd.value == "Custom" else srv_dd.value
                conn_status.value = "⏳ جاري اختبار الاتصال بـ TickerAll..."
                page.update()
                try:
                    state.client = TickerAllClient(tok_f.value)
                    await state.client.connect(acc_f.value.strip(), pwd_f.value.strip(), srv)
                    state.connected = True
                    conn_status.value = f"✅ متصل بنجاح بالخادم {srv}"
                    conn_status.color = NEON_GREEN
                    add_log(f"✅ تم الاتصال بالحساب {acc_f.value} على {srv}")
                    await refresh_all(auto_trade=False)
                except Exception as ex:
                    state.connected = False
                    conn_status.value = f"❌ فشل الاتصال: {ex}"
                    conn_status.color = NEON_RED
                page.update()

            return ft.Column(
                [
                    ft.Text("إعدادات الاتصال (MT5 & MFNT)", size=18, color=NEON_CYAN, weight=ft.FontWeight.BOLD),
                    ft.Text("ملاحظة: الاتصال من Android/Termux يتم عبر جسر TickerAll السحابي.", size=11, color=WHITE_70),
                    tok_f, acc_f, pwd_f, srv_dd, custom_srv,
                    neon_btn("اتصال واختبار الخادم", ft.Icons.LINK, NEON_CYAN, _do_connect),
                    conn_status,
                    neon_card(live_sw, padding=10, border_color=NEON_RED),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )

        tabs_map = {
            "dashboard": view_dashboard,
            "analysis": view_ai_analysis,
            "scanner": view_scanner,
            "risk": view_risk,
            "strategy": view_strategy,
            "backtest": view_backtest,
            "perf": view_perf,
            "journal": view_journal,
            "account": view_account,
            "connection": view_connection,
        }

        def render_tab(name: str):
            current_tab["name"] = name
            content_holder.content = tabs_map[name]()
            page.update()

        nav_items = [
            ("dashboard", ft.Icons.DASHBOARD),
            ("analysis", ft.Icons.PSYCHOLOGY),
            ("scanner", ft.Icons.RADAR),
            ("risk", ft.Icons.SHIELD),
            ("strategy", ft.Icons.SCIENCE),
            ("backtest", ft.Icons.HISTORY),
            ("perf", ft.Icons.BAR_CHART),
            ("journal", ft.Icons.RECEIPT_LONG),
            ("connection", ft.Icons.LINK),
            ("account", ft.Icons.PERSON),
        ]

        nav_bar = ft.Row(
            [
                ft.Container(
                    content=ft.Row([ft.Icon(ic, size=16, color=NEON_CYAN), ft.Text(t(k), size=11, color=WHITE)], spacing=4),
                    padding=ft.Padding(left=10, top=8, right=10, bottom=8),
                    bgcolor=CARD_BG,
                    border=ft.Border.all(1, NEON_PURPLE),
                    border_radius=10,
                    on_click=lambda e, key=k: render_tab(key),
                )
                for k, ic in nav_items
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=6,
        )

        render_tab("dashboard")
        asyncio.create_task(refresh_all(auto_trade=False))
        return ft.SafeArea(
            expand=True,
            content=ft.Container(
                expand=True,
                padding=12,
                gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1), colors=[BG_GRAD_1, BG_GRAD_2]),
                content=ft.Column([nav_bar, content_holder], spacing=10, expand=True),
            ),
        )

    def build_auth_view():
        user_f = ft.TextField(label="اسم المستخدم", bgcolor=CARD_BG, border_color=NEON_CYAN, color=WHITE)
        pass_f = ft.TextField(label="كلمة المرور", password=True, can_reveal_password=True, bgcolor=CARD_BG, border_color=NEON_PURPLE, color=WHITE)
        pin_f = ft.TextField(label="رمز الاستعادة (للإنشاء/الاستعادة فقط)", bgcolor=CARD_BG, border_color=NEON_GOLD, color=WHITE)
        msg_txt = ft.Text("", color=NEON_CYAN, size=12)

        def _enter_app(u_obj):
            state.current_user = u_obj
            page.controls.clear()
            page.controls.append(build_main_app())
            page.update()

        def _do_login(e):
            ok, res = state.auth.login(user_f.value or "", pass_f.value or "")
            if ok:
                _enter_app(res)
            else:
                msg_txt.value = f"❌ {res}"
                msg_txt.color = NEON_RED
                page.update()

        def _do_register(e):
            ok, res = state.auth.register(user_f.value or "", pass_f.value or "", pin_f.value or "")
            msg_txt.value = f"{'✅' if ok else '❌'} {res}"
            msg_txt.color = NEON_GREEN if ok else NEON_RED
            page.update()

        def _do_recover(e):
            ok, res = state.auth.recover_password(user_f.value or "", pin_f.value or "", pass_f.value or "")
            msg_txt.value = f"{'✅' if ok else '❌'} {res}"
            msg_txt.color = NEON_GREEN if ok else NEON_RED
            page.update()

        return ft.SafeArea(
            expand=True,
            content=ft.Container(
                expand=True,
                padding=20,
                gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1), colors=[BG_GRAD_1, BG_GRAD_2]),
                content=ft.Column(
                    [
                        ft.Container(height=20),
                        ft.Icon(ft.Icons.SECURITY, size=64, color=NEON_CYAN),
                        ft.Text("CYBERBOT MT5 PRO v4.0", size=24, color=NEON_GOLD, weight=ft.FontWeight.BOLD),
                        ft.Text("تسجيل الدخول الآمن أو إنشاء حساب جديد", size=12, color=WHITE_70),
                        user_f, pass_f, pin_f,
                        neon_btn("تسجيل الدخول", ft.Icons.LOGIN, NEON_CYAN, _do_login),
                        ft.Row([
                            neon_btn("حساب جديد", ft.Icons.PERSON_ADD, NEON_PURPLE, _do_register, expand=True),
                            neon_btn("استعادة", ft.Icons.LOCK_RESET, NEON_GOLD, _do_recover, expand=True),
                        ], spacing=10),
                        neon_btn("دخول سريع (وضع المحاكاة)", ft.Icons.FLASH_ON, NEON_GREEN, lambda e: _enter_app({"username": "Trader"})),
                        msg_txt,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            ),
        )

    page.controls.append(splash)
    page.update()
    await asyncio.sleep(1.8)
    page.controls.clear()
    page.controls.append(build_auth_view())
    page.update()


if __name__ == "__main__":
    ft.run(main)
