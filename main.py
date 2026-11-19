import asyncio
import os
from datetime import datetime
import flet as ft
from metaapi_cloud_sdk import MetaApi

# ==================== الثوابت والهوية البصرية ====================
BG = "#0A0D14"
PURPLE = "#8A2BE2"
CYAN = "#00F5D4"
GOLD = "#FFD700"
RED = "#FF3B5C"
GREEN = "#00FF9C"
GLASS = "#1A1F2E"
GLASS_ALPHA = "#8C1A1F2E"
BORDER = "#2A3145"
WHITE = "#FFFFFF"
WHITE_70 = "#B3FFFFFF"
WHITE_54 = "#8AFFFFFF"

METAAPI_TOKEN = os.getenv("METAAPI_TOKEN", "ضع_التوكن_هنا")


# ==================== دوال المؤشرات الفنية ====================
async def calc_ema(closes, period):
    if len(closes) < period:
        return 0.0
    mult = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * mult + ema
    return ema


async def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period or 1e-9
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


async def calc_macd(closes):
    ema12 = await calc_ema(closes, 12)
    ema26 = await calc_ema(closes, 26)
    return ema12 - ema26


async def analyze_signal(closes):
    """محرك التحليل: RSI + MACD + EMA50/200"""
    if len(closes) < 50:
        return "NEUTRAL", 0
    rsi = await calc_rsi(closes)
    macd = await calc_macd(closes)
    ema50 = await calc_ema(closes, 50)
    ema200 = await calc_ema(closes, min(200, len(closes)))
    price = closes[-1]

    score = 0
    if rsi < 35:
        score += 25
    if macd > 0:
        score += 25
    if price > ema50:
        score += 25
    if ema50 > ema200:
        score += 25

    if rsi > 65:
        score -= 25
    if macd < 0:
        score -= 25
    if price < ema50:
        score -= 25
    if ema50 < ema200:
        score -= 25

    if score >= 50:
        return "BUY", min(95, 50 + score)
    elif score <= -50:
        return "SELL", min(95, 50 + abs(score))
    return "NEUTRAL", 50


# ==================== حالة التطبيق ====================
class AppState:
    def __init__(self):
        self.api = None
        self.account = None
        self.connection = None
        self.running = False
        self.symbol = "BTCUSD"
        self.timeframe = "15m"
        self.lot = 0.01
        self.logs = []
        self.page = None
        self.log_list = None


state = AppState()


# ==================== دوال مساعدة للواجهة ====================
def glass_card(content, padding=16, border_color=BORDER):
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=GLASS_ALPHA,
        border=ft.Border.all(1, border_color),
        border_radius=18,
        blur=ft.Blur(10, 10, ft.BlurStyle.NORMAL),
        shadow=ft.BoxShadow(
            blur_radius=18,
            color=PURPLE,
            offset=ft.Offset(0, 0),
            spread_radius=1,
        ),
    )


def neon_button(text, color, on_click, width=140, height=52):
    return ft.Container(
        content=ft.Text(text, color=BG, weight=ft.FontWeight.BOLD, size=15),
        width=width,
        height=height,
        alignment=ft.Alignment(0, 0),
        bgcolor=color,
        border_radius=14,
        shadow=ft.BoxShadow(blur_radius=20, color=color, spread_radius=2),
        on_click=on_click,
        animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
        ink=True,
    )


def add_log(msg):
    stamp = datetime.now().strftime("%H:%M:%S")
    state.logs.insert(0, f"[{stamp}] {msg}")
    if len(state.logs) > 50:
        state.logs.pop()

    if state.log_list is not None:
        state.log_list.controls = [
            ft.Text(item, size=11, color=WHITE_70) for item in state.logs
        ]
        if state.page is not None:
            state.page.update()


# ==================== منطق MetaApi ====================
async def connect_mt5(account_id, password, server):
    try:
        if not METAAPI_TOKEN or METAAPI_TOKEN == "ضع_التوكن_هنا":
            add_log("❌ يرجى ضبط متغير البيئة METAAPI_TOKEN أولاً")
            return False

        state.api = MetaApi(METAAPI_TOKEN)
        state.account = await state.api.metatrader_account_api.create_account(
            {
                "name": f"CyberBot-{account_id}",
                "type": "cloud",
                "login": str(account_id).strip(),
                "password": password,
                "server": server,
                "platform": "mt5",
                "magic": 202500,
            }
        )
        await state.account.deploy()
        state.connection = state.account.get_streaming_connection()
        await state.connection.connect()
        await state.connection.wait_synchronized()
        add_log(f"✅ تم الاتصال بالحساب {account_id} على {server}")
        return True
    except Exception as e:
        add_log(f"❌ فشل الاتصال: {e}")
        return False


async def fetch_candles(symbol, timeframe="15m", limit=200):
    if not state.connection:
        return []
    try:
        candles = await state.connection.get_candles(symbol, timeframe, limit)
        return [float(c["close"]) for c in candles if "close" in c]
    except Exception as e:
        add_log(f"⚠️ تعذر جلب الشموع: {e}")
        return []


async def execute_trade(signal, confidence):
    if not state.connection:
        return
    try:
        price_data = await state.connection.get_symbol_price(state.symbol)
        ask = float(price_data.get("ask") or 0.0)
        bid = float(price_data.get("bid") or 0.0)

        if signal == "BUY" and ask > 0:
            await state.connection.create_market_buy_order(
                state.symbol,
                state.lot,
                stop_loss=round(ask * 0.99, 5),
                take_profit=round(ask * 1.02, 5),
                options={"comment": "CyberBot BUY"},
            )
            add_log(f"🟢 شراء {state.symbol} لوت {state.lot} - ثقة {confidence}%")
        elif signal == "SELL" and bid > 0:
            await state.connection.create_market_sell_order(
                state.symbol,
                state.lot,
                stop_loss=round(bid * 1.01, 5),
                take_profit=round(bid * 0.98, 5),
                options={"comment": "CyberBot SELL"},
            )
            add_log(f"🔴 بيع {state.symbol} لوت {state.lot} - ثقة {confidence}%")
    except Exception as e:
        add_log(f"⚠️ فشل تنفيذ الصفقة: {e}")


async def trading_loop(symbol_dd, tf_dd):
    while state.running:
        try:
            state.symbol = symbol_dd.value or "BTCUSD"
            state.timeframe = tf_dd.value or "15m"
            closes = await fetch_candles(state.symbol, state.timeframe)
            if closes:
                signal, confidence = await analyze_signal(closes)
                add_log(f"🔍 فحص {state.symbol} {state.timeframe}: {signal} ({confidence}%)")
                if signal != "NEUTRAL" and confidence >= 70:
                    await execute_trade(signal, confidence)
            await asyncio.sleep(15)
        except Exception as e:
            add_log(f"⚠️ خطأ في الحلقة: {e}")
            await asyncio.sleep(5)


# ==================== واجهة Flet ====================
async def main(page: ft.Page):
    state.page = page
    page.title = "CyberBot MT5"
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20

    # ---------- شاشة البداية ----------
    splash = ft.Column(
        [
            ft.Container(height=80),
            ft.Icon(ft.Icons.BOLT, size=80, color=GOLD),
            ft.Text("CYBERBOT MT5", size=28, color=CYAN, weight=ft.FontWeight.BOLD),
            ft.Text(
                "جاري الاتصال بخوادم السيولة والذكاء الاصطناعي...",
                size=13,
                color=WHITE_70,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.ProgressBar(width=240, color=CYAN, bgcolor=GLASS),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20,
    )

    # ---------- لوحة التحكم ----------
    balance_txt = ft.Text("$0.00", size=26, color=GOLD, weight=ft.FontWeight.BOLD)
    equity_txt = ft.Text("$0.00", size=16, color=CYAN)
    pl_txt = ft.Text("$0.00", size=16, color=GREEN)
    signal_gauge = ft.Text("NEUTRAL 50%", size=20, color=WHITE_70)
    log_list = ft.ListView(expand=True, spacing=4, height=140)
    state.log_list = log_list

    symbol_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option(s)
            for s in ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "US30"]
        ],
        value="BTCUSD",
        bgcolor=GLASS,
        border_color=PURPLE,
        color=WHITE,
        label="الأصل",
        label_style=ft.TextStyle(color=PURPLE),
        expand=True,
    )

    tf_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option(t)
            for t in ["1m", "15m", "1h", "4h", "1w", "1M"]
        ],
        value="15m",
        bgcolor=GLASS,
        border_color=PURPLE,
        color=WHITE,
        label="الفريم",
        label_style=ft.TextStyle(color=PURPLE),
        expand=True,
    )

    async def refresh_account():
        if state.connection:
            try:
                info = await state.connection.get_account_information()
                balance_txt.value = f"${float(info.get('balance', 0)):,.2f}"
                equity_txt.value = f"${float(info.get('equity', 0)):,.2f}"
                pl = float(info.get("profit", 0))
                pl_txt.value = f"${pl:,.2f}"
                pl_txt.color = GREEN if pl >= 0 else RED
            except Exception as ex:
                add_log(f"⚠️ تعذر تحديث بيانات الحساب: {ex}")
        page.update()

    async def start_bot(e):
        if not state.connection:
            add_log("⚠️ لا يوجد اتصال أولاً")
            return
        if state.running:
            add_log("ℹ️ البوت قيد التشغيل بالفعل")
            return
        state.running = True
        add_log("🚀 تم تفعيل محرك التداول الآلي")
        asyncio.create_task(trading_loop(symbol_dd, tf_dd))

    def stop_bot(e):
        state.running = False
        add_log("⏹️ تم إيقاف البوت")

    async def analyze_now(e):
        state.symbol = symbol_dd.value or "BTCUSD"
        state.timeframe = tf_dd.value or "15m"
        closes = await fetch_candles(state.symbol, state.timeframe)
        if closes:
            sig, conf = await analyze_signal(closes)
            signal_gauge.value = f"{sig} {conf}%"
            signal_gauge.color = GREEN if sig == "BUY" else RED if sig == "SELL" else CYAN
            add_log(f"📊 تحليل فوري ({state.symbol} - {state.timeframe}): {sig} ({conf}%)")
            page.update()

    dashboard_view = ft.Column(
        [
            ft.Container(height=10),
            ft.Text("DASHBOARD", size=18, color=CYAN, weight=ft.FontWeight.BOLD),
            glass_card(
                ft.Column(
                    [
                        ft.Text("Balance", size=12, color=WHITE_54),
                        balance_txt,
                        ft.Row(
                            [
                                ft.Text("Equity", size=12, color=WHITE_54),
                                equity_txt,
                                ft.Text("P/L", size=12, color=WHITE_54),
                                pl_txt,
                            ],
                            spacing=20,
                        ),
                    ],
                    spacing=6,
                )
            ),
            ft.Row([symbol_dd, tf_dd], spacing=12),
            glass_card(
                ft.Column(
                    [
                        ft.Text("AI SIGNAL", size=12, color=WHITE_54),
                        signal_gauge,
                        neon_button("تحليل الآن", CYAN, analyze_now, width=160),
                    ],
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ),
            ft.Row(
                [
                    neon_button("START BOT", GREEN, start_bot, width=140),
                    neon_button("STOP BOT", RED, stop_bot, width=140),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=20,
            ),
            glass_card(
                ft.Column(
                    [
                        ft.Text("LIVE TERMINAL", size=12, color=WHITE_54),
                        log_list,
                    ],
                    spacing=8,
                )
            ),
        ],
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # ---------- شاشة تسجيل الدخول ----------
    acc_field = ft.TextField(
        label="MT5 Account ID",
        bgcolor=GLASS,
        border_color=CYAN,
        color=WHITE,
        label_style=ft.TextStyle(color=CYAN),
    )
    pass_field = ft.TextField(
        label="Password",
        password=True,
        can_reveal_password=True,
        bgcolor=GLASS,
        border_color=CYAN,
        color=WHITE,
        label_style=ft.TextStyle(color=CYAN),
    )
    server_dd = ft.Dropdown(
        label="Server",
        options=[
            ft.dropdown.Option("Headway-Real"),
            ft.dropdown.Option("Headway-Demo"),
            ft.dropdown.Option("Custom Server"),
        ],
        value="Headway-Demo",
        bgcolor=GLASS,
        border_color=CYAN,
        color=WHITE,
        label_style=ft.TextStyle(color=CYAN),
    )
    status_text = ft.Text("", color=CYAN, size=12)

    async def on_connect(e):
        status_text.value = "⏳ جاري الاتصال الآمن..."
        page.update()
        ok = await connect_mt5(acc_field.value, pass_field.value, server_dd.value)
        if ok:
            status_text.value = "✅ متصل"
            page.controls.clear()
            page.controls.append(dashboard_view)
            page.update()
            asyncio.create_task(refresh_account())
        else:
            status_text.value = "❌ تحقق من البيانات أو التوكن"
            page.update()

    login_view = ft.Column(
        [
            ft.Container(height=40),
            ft.Text("SECURE ACCESS", size=22, color=PURPLE, weight=ft.FontWeight.BOLD),
            ft.Text("ربط حساب MetaTrader 5", size=13, color=WHITE_54),
            acc_field,
            pass_field,
            server_dd,
            neon_button("اتصال آمن وتفعيل المحرك", CYAN, on_connect, width=260),
            status_text,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=16,
    )

    # ---------- تشغيل شاشة البداية ثم الدخول ----------
    page.controls.append(splash)
    page.update()

    await asyncio.sleep(2.5)
    page.controls.clear()
    page.controls.append(login_view)
    page.update()


if __name__ == "__main__":
    ft.run(main)
