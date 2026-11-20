
import asyncio
import random
from datetime import datetime

import flet as ft

from engine import (
    JournalManager,
    LocalAuthManager,
    RiskManager,
    StrategyManager,
    build_ai_explanation,
    full_market_analysis,
    run_backtest,
)
from demo_mt5 import DemoMT5


APP_NAME = "CYBERBOT MT5 PRO v4.0 ULTIMATE AI"

BG = "#05070D"
PANEL = "#101827"
PANEL2 = "#151D30"
PURPLE = "#A855F7"
CYAN = "#00F5D4"
GREEN = "#00FF9C"
RED = "#FF3864"
GOLD = "#FFD700"
WHITE = "#F2F5FF"
MUTED = "#8995AD"


class CyberApp:
    def __init__(self):
        self.auth = LocalAuthManager()
        self.journal = JournalManager()
        self.risk = RiskManager()
        self.strategies = StrategyManager()
        self.demo = DemoMT5(10000)

        self.symbol = "XAUUSD"
        self.timeframe = "M5"
        self.running = False
        self.auto_mode = False

        self.candles = {}
        self.analysis = None
        self.logs = []
        self.page = None
        self.content = None
        self.current_tab = "dashboard"

        self.balance_text = None
        self.equity_text = None
        self.profit_text = None
        self.connection_text = None
        self.positions_view = None
        self.logs_view = None
        self.analysis_view = None
        self.symbol_select = None
        self.timeframe_select = None
        self.lot_field = None
        self.sl_field = None
        self.tp_field = None
        self.login_message = None

    def log(self, message):
        self.logs.insert(
            0,
            f"{datetime.now().strftime('%H:%M:%S')} | {message}"
        )
        self.logs = self.logs[:60]
        if self.logs_view:
            self.update_logs()

    def make_candles(self, symbol, count=100):
        bases = {
            "XAUUSD": 2650,
            "EURUSD": 1.08,
            "GBPUSD": 1.27,
            "BTCUSD": 95000,
            "US30": 43000,
        }

        price = bases.get(symbol, 100)
        result = []

        for _ in range(count):
            change = random.uniform(-0.002, 0.002)
            open_price = price
            close_price = max(0.0001, price * (1 + change))

            result.append({
                "open": open_price,
                "high": max(open_price, close_price) * 1.0005,
                "low": min(open_price, close_price) * 0.9995,
                "close": close_price,
                "volume": random.randint(100, 1000),
            })

            price = close_price

        return result

    def market_data(self):
        self.candles[self.symbol] = self.make_candles(self.symbol)
        return self.candles[self.symbol]

    def get_price(self):
        candles = self.candles.get(self.symbol)
        if not candles:
            candles = self.market_data()
        return float(candles[-1]["close"])

    def open_trade(self, side):
        try:
            lot = float(self.lot_field.value or "0.01")
            sl = float(self.sl_field.value or "0")
            tp = float(self.tp_field.value or "0")

            if lot <= 0 or lot > 1:
                self.show_message("حجم الصفقة يجب أن يكون بين 0 و1")
                return

            price = self.get_price()

            if side == "BUY":
                result = self.demo.buy(
                    self.symbol, lot, price, sl, tp
                )
            else:
                result = self.demo.sell(
                    self.symbol, lot, price, sl, tp
                )

            if result["success"]:
                self.log(
                    f"فتح {side} تجريبي على {self.symbol} "
                    f"بسعر {price}"
                )
            else:
                self.log(result.get("error", "فشل فتح الصفقة"))

            self.refresh_dashboard()

        except (ValueError, TypeError):
            self.show_message("تحقق من قيم حجم الصفقة ووقف الخسارة والهدف")

    def close_trade(self, ticket):
        result = self.demo.close(ticket)

        if result["success"]:
            self.log(f"تم إغلاق الصفقة التجريبية رقم {ticket}")
        else:
            self.log("تعذر إغلاق الصفقة")

        self.refresh_dashboard()

    def close_all(self, e=None):
        self.demo.close_all()
        self.log("تم إغلاق جميع الصفقات التجريبية")
        self.refresh_dashboard()

    def refresh_positions(self):
        if not self.positions_view:
            return

        self.positions_view.controls.clear()

        positions = self.demo.get_positions()

        if not positions:
            self.positions_view.controls.append(
                ft.Text(
                    "لا توجد صفقات مفتوحة",
                    color=MUTED
                )
            )
        else:
            for p in positions:
                color = GREEN if p["type"] == "BUY" else RED

                self.positions_view.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Text(
                                    p["symbol"],
                                    color=WHITE,
                                    weight=ft.FontWeight.BOLD
                                ),
                                ft.Text(
                                    p["type"],
                                    color=color,
                                    weight=ft.FontWeight.BOLD
                                ),
                                ft.Text(
                                    f"#{p['ticket']}",
                                    color=MUTED
                                ),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                            ft.Text(
                                f"الدخول: {p['open_price']:.5f}",
                                color=WHITE
                            ),

                            ft.Text(
                                f"السعر الحالي: {p['current_price']:.5f}",
                                color=CYAN
                            ),

                            ft.Text(
                                f"الربح التجريبي: {p['profit']:.2f}",
                                color=GREEN if p["profit"] >= 0 else RED
                            ),

                            ft.ElevatedButton(
                                "إغلاق الصفقة",
                                icon=ft.Icons.CLOSE,
                                on_click=lambda e, ticket=p["ticket"]:
                                    self.close_trade(ticket),
                                bgcolor=RED,
                                color=WHITE,
                            ),
                        ], spacing=8),
                        bgcolor=PANEL2,
                        padding=12,
                        border_radius=12,
                    )
                )

        self.page.update()

    def update_logs(self):
        if not self.logs_view:
            return

        self.logs_view.controls.clear()

        for item in self.logs[:15]:
            self.logs_view.controls.append(
                ft.Text(item, color=CYAN, size=11)
            )

    def refresh_dashboard(self):
        info = self.demo.account_info()

        if self.balance_text:
            self.balance_text.value = f"${info['balance']:,.2f}"

        if self.equity_text:
            self.equity_text.value = f"${info['equity']:,.2f}"

        if self.profit_text:
            self.profit_text.value = f"${info['profit']:,.2f}"

        if self.connection_text:
            self.connection_text.value = "DEMO SIMULATION CONNECTED"

        self.refresh_positions()
        self.update_logs()
        self.page.update()

    def show_message(self, message):
        self.page.open(
            ft.SnackBar(content=ft.Text(message))
        )

    def card(self, title, content, color=PURPLE):
        return ft.Container(
            content=ft.Column([
                ft.Text(
                    title,
                    color=color,
                    size=15,
                    weight=ft.FontWeight.BOLD
                ),
                content,
            ], spacing=12),
            bgcolor=PANEL,
            padding=16,
            border_radius=16,
            border=ft.border.all(1, "#29344A"),
        )

    def stat(self, title, value, color=CYAN):
        return ft.Container(
            content=ft.Column([
                ft.Text(title, color=MUTED, size=12),
                value,
            ], spacing=5),
            bgcolor=PANEL2,
            padding=13,
            border_radius=12,
            expand=True,
        )

    def build_dashboard(self):
        self.balance_text = ft.Text(
            "$10,000.00",
            color=GREEN,
            size=22,
            weight=ft.FontWeight.BOLD
        )
        self.equity_text = ft.Text(
            "$10,000.00",
            color=CYAN,
            size=22,
            weight=ft.FontWeight.BOLD
        )
        self.profit_text = ft.Text(
            "$0.00",
            color=GOLD,
            size=22,
            weight=ft.FontWeight.BOLD
        )

        self.connection_text = ft.Text(
            "DEMO SIMULATION CONNECTED",
            color=GREEN,
            size=12
        )

        self.symbol_select = ft.Dropdown(
            label="الأصل",
            value=self.symbol,
            options=[
                ft.dropdown.Option(s) for s in
                ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "US30"]
            ],
            on_change=self.change_symbol,
            expand=True,
        )

        self.timeframe_select = ft.Dropdown(
            label="الإطار الزمني",
            value=self.timeframe,
            options=[
                ft.dropdown.Option(t) for t in
                ["M1", "M5", "M15", "M30", "H1", "H4"]
            ],
            on_change=self.change_timeframe,
            expand=True,
        )

        self.lot_field = ft.TextField(
            label="حجم الصفقة التجريبية",
            value="0.01",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )

        self.sl_field = ft.TextField(
            label="وقف الخسارة",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )

        self.tp_field = ft.TextField(
            label="جني الأرباح",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )

        self.positions_view = ft.Column(spacing=10)
        self.logs_view = ft.Column(spacing=6)

        self.market_data()

        return ft.Column([
            ft.Text(
                "لوحة التحكم الرئيسية",
                size=23,
                color=WHITE,
                weight=ft.FontWeight.BOLD
            ),

            ft.Text(
                "CYBER NEON TRADING TERMINAL",
                color=CYAN,
                size=11
            ),

            self.card(
                "حالة المحرك",
                self.connection_text,
                GREEN
            ),

            ft.Row([
                self.stat("الرصيد", self.balance_text, GREEN),
                self.stat("حقوق الملكية", self.equity_text, CYAN),
            ]),

            ft.Row([
                self.stat("الربح العائم", self.profit_text, GOLD),
            ]),

            self.card(
                "إعدادات السوق",
                ft.Column([
                    self.symbol_select,
                    self.timeframe_select,
                ])
            ),

            self.card(
                "تنفيذ أوامر المحاكاة",
                ft.Column([
                    self.lot_field,
                    ft.Row([self.sl_field, self.tp_field]),
                    ft.Row([
                        ft.ElevatedButton(
                            "BUY DEMO",
                            icon=ft.Icons.TRENDING_UP,
                            bgcolor=GREEN,
                            color=BG,
                            expand=True,
                            on_click=lambda e: self.open_trade("BUY")
                        ),
                        ft.ElevatedButton(
                            "SELL DEMO",
                            icon=ft.Icons.TRENDING_DOWN,
                            bgcolor=RED,
                            color=WHITE,
                            expand=True,
                            on_click=lambda e: self.open_trade("SELL")
                        ),
                    ]),
                    ft.ElevatedButton(
                        "إغلاق جميع الصفقات",
                        icon=ft.Icons.CLOSE,
                        bgcolor="#4B2330",
                        color=WHITE,
                        expand=True,
                        on_click=self.close_all,
                    ),
                ])
            ),

            self.card(
                "الصفقات المفتوحة",
                self.positions_view,
                CYAN
            ),

            self.card(
                "سجل النظام",
                self.logs_view,
                GOLD
            ),

        ], spacing=14)

    def change_symbol(self, e):
        self.symbol = e.control.value
        self.market_data()
        self.log(f"تغيير الأصل إلى {self.symbol}")
        self.refresh_dashboard()

    def change_timeframe(self, e):
        self.timeframe = e.control.value
        self.log(f"الإطار الزمني: {self.timeframe}")
        self.page.update()

    def build_analysis(self):
        output = ft.Text(
            "اضغط على زر تحليل السوق لبدء التحليل.",
            color=WHITE,
            selectable=True
        )

        def analyze(e):
            candles = self.market_data()

            try:
                result = full_market_analysis(
                    candles,
                    self.symbol,
                    self.strategies
                )
                self.analysis = result

                explanation = build_ai_explanation(result)

                output.value = (
                    f"الأصل: {self.symbol}\n\n"
                    f"نتيجة التحليل:\n{result}\n\n"
                    f"التفسير:\n{explanation}"
                )

                self.log(f"اكتمل تحليل {self.symbol}")

            except Exception as ex:
                output.value = f"تعذر التحليل: {ex}"

            self.page.update()

        return ft.Column([
            ft.Text("تحليل السوق", size=23, color=WHITE),
            self.card(
                "محرك التحليل",
                ft.Column([
                    ft.Text(
                        "تحليل فني تعليمي باستخدام بيانات المحاكاة.",
                        color=MUTED
                    ),
                    ft.ElevatedButton(
                        "تحليل الآن",
                        icon=ft.Icons.ANALYTICS,
                        bgcolor=PURPLE,
                        color=WHITE,
                        on_click=analyze,
                    ),
                    output,
                ])
            )
        ], spacing=14)

    def build_risk(self):
        risk_value = ft.Text("1%", color=CYAN, size=18)
        loss_value = ft.Text("5%", color=GOLD, size=18)

        risk_slider = ft.Slider(
            min=0.1,
            max=2,
            divisions=19,
            value=1,
            label="{value}%",
            on_change=lambda e: setattr(
                risk_value, "value", f"{e.control.value:.1f}%"
            ),
        )

        loss_slider = ft.Slider(
            min=1,
            max=10,
            divisions=9,
            value=5,
            label="{value}%",
            on_change=lambda e: setattr(
                loss_value, "value", f"{e.control.value:.0f}%"
            ),
        )

        return ft.Column([
            ft.Text("إدارة المخاطر", size=23, color=WHITE),
            self.card(
                "إعدادات المخاطر التعليمية",
                ft.Column([
                    ft.Text("نسبة المخاطرة", color=WHITE),
                    risk_value,
                    risk_slider,
                    ft.Text("حد الخسارة اليومي", color=WHITE),
                    loss_value,
                    loss_slider,
                    ft.Text(
                        "هذه القيم تعليمية ولا تضمن نتائج التداول.",
                        color=MUTED
                    )
                ])
            )
        ], spacing=14)

    def build_backtest(self):
        output = ft.Text(
            "لم يتم تشغيل الاختبار بعد.",
            color=WHITE,
            selectable=True
        )

        def run_test(e):
            try:
                candles = self.make_candles(self.symbol, 300)
                result = run_backtest(candles, self.strategies)
                output.value = str(result)
                self.log("اكتمل الاختبار التاريخي التعليمي")
            except Exception as ex:
                output.value = f"خطأ الاختبار: {ex}"

            self.page.update()

        return ft.Column([
            ft.Text("اختبار الاستراتيجيات", size=23, color=WHITE),
            self.card(
                "Backtesting",
                ft.Column([
                    ft.Text(
                        "اختبر الاستراتيجيات على بيانات مولدة للمحاكاة.",
                        color=MUTED
                    ),
                    ft.ElevatedButton(
                        "بدء الاختبار",
                        icon=ft.Icons.PLAY_ARROW,
                        bgcolor=PURPLE,
                        color=WHITE,
                        on_click=run_test
                    ),
                    output,
                ])
            )
        ], spacing=14)

    def build_journal(self):
        rows = []

        for p in self.demo.get_history():
            rows.append(
                ft.Container(
                    bgcolor=PANEL2,
                    padding=12,
                    border_radius=10,
                    content=ft.Text(
                        f"{p['symbol']} | {p['side']} | "
                        f"النتيجة: {p['profit']:.2f}",
                        color=WHITE
                    )
                )
            )

        if not rows:
            rows.append(
                ft.Text("لا يوجد سجل صفقات بعد.", color=MUTED)
            )

        return ft.Column([
            ft.Text("سجل الصفقات", size=23, color=WHITE),
            self.card("العمليات المغلقة", ft.Column(rows))
        ], spacing=14)

    def build_account(self, page):
        return ft.Column([
            ft.Text("الحساب", size=23, color=WHITE),
            self.card(
                "حساب المحاكاة",
                ft.Column([
                    ft.Text("CYBERBOT DEMO ACCOUNT", color=CYAN),
                    ft.Text("الرصيد الابتدائي: 10,000", color=WHITE),
                    ft.Text("لا يوجد اتصال بحساب تداول حقيقي.", color=MUTED),
                    ft.ElevatedButton(
                        "تسجيل الخروج",
                        icon=ft.Icons.LOGOUT,
                        bgcolor=RED,
                        color=WHITE,
                        on_click=lambda e: self.show_login(page),
                    )
                ])
            )
        ], spacing=14)

    def show_tab(self, tab):
        self.current_tab = tab

        builders = {
            "dashboard": self.build_dashboard,
            "analysis": self.build_analysis,
            "risk": self.build_risk,
            "backtest": self.build_backtest,
            "journal": self.build_journal,
            "account": lambda: self.build_account(self.page),
        }

        self.content.controls.clear()
        self.content.controls.append(builders[tab]())
        self.page.update()

    def build_main(self, page):
        self.page = page
        self.content = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
        )

        navigation = ft.Row(
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.TextButton(
                    "الرئيسية",
                    on_click=lambda e: self.show_tab("dashboard")
                ),
                ft.TextButton(
                    "التحليل",
                    on_click=lambda e: self.show_tab("analysis")
                ),
                ft.TextButton(
                    "المخاطر",
                    on_click=lambda e: self.show_tab("risk")
                ),
                ft.TextButton(
                    "الاختبار",
                    on_click=lambda e: self.show_tab("backtest")
                ),
                ft.TextButton(
                    "السجل",
                    on_click=lambda e: self.show_tab("journal")
                ),
                ft.TextButton(
                    "الحساب",
                    on_click=lambda e: self.show_tab("account")
                ),
            ],
        )

        page.controls.clear()
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(
                            "CYBERBOT",
                            color=CYAN,
                            size=22,
                            weight=ft.FontWeight.BOLD
                        ),
                        ft.Text("v4.0", color=PURPLE)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                    navigation,
                    ft.Divider(color="#29344A"),
                    self.content,
                ], expand=True, spacing=14),
                bgcolor=BG,
                padding=14,
                expand=True,
            )
        )

        self.show_tab("dashboard")
        self.log("تم تشغيل محرك المحاكاة")
        self.refresh_dashboard()

    def show_login(self, page):
        self.page = page
        page.controls.clear()

        username = ft.TextField(
            label="اسم المستخدم",
            border_color=PURPLE,
        )

        password = ft.TextField(
            label="كلمة المرور",
            password=True,
            can_reveal_password=True,
            border_color=PURPLE,
        )

        message = ft.Text("", color=RED)

        def login(e):
            try:
                result = self.auth.login(
                    username.value.strip(),
                    password.value
                )

                if result:
                    self.build_main(page)
                else:
                    message.value = "بيانات الدخول غير صحيحة"
                    page.update()

            except Exception as ex:
                message.value = str(ex)
                page.update()

        def register(e):
            try:
                result = self.auth.register(
                    username.value.strip(),
                    password.value,
                    "1234"
                )

                if result:
                    message.value = "تم إنشاء الحساب. سجل الدخول الآن."
                    message.color = GREEN
                else:
                    message.value = "تعذر إنشاء الحساب"

            except Exception as ex:
                message.value = str(ex)

            page.update()

        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Text("CYBERBOT", size=32, color=CYAN,
                            weight=ft.FontWeight.BOLD),
                    ft.Text("MT5 PRO ULTIMATE AI", color=PURPLE),
                    ft.Divider(color="#29344A"),
                    ft.Text("تسجيل الدخول", size=23, color=WHITE),
                    username,
                    password,
                    message,
                    ft.ElevatedButton(
                        "دخول",
                        icon=ft.Icons.LOGIN,
                        bgcolor=PURPLE,
                        color=WHITE,
                        expand=True,
                        on_click=login,
                    ),
                    ft.OutlinedButton(
                        "إنشاء حساب",
                        on_click=register,
                    ),
                    ft.Text(
                        "محاكاة تعليمية فقط — لا توجد صفقات حقيقية",
                        color=MUTED,
                        size=11
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   spacing=15),
                padding=25,
                bgcolor=BG,
                expand=True,
                alignment=ft.alignment.center,
            )
        )

        page.update()

    async def splash(self, page):
        page.controls.clear()

        title = ft.Text(
            "CYBERBOT",
            size=35,
            color=CYAN,
            weight=ft.FontWeight.BOLD
        )

        status = ft.Text(
            "INITIALIZING AI ENGINE...",
            color=PURPLE,
            size=12
        )

        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Icon(
                        ft.Icons.SMART_TOY,
                        size=95,
                        color=CYAN
                    ),
                    title,
                    ft.Text(
                        "MT5 PRO v4.0 ULTIMATE AI",
                        color=WHITE,
                        size=14
                    ),
                    ft.ProgressBar(
                        color=CYAN,
                        bgcolor=PANEL2,
                        width=220
                    ),
                    status,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   alignment=ft.MainAxisAlignment.CENTER,
                   spacing=20),
                bgcolor=BG,
                expand=True,
                alignment=ft.alignment.center,
            )
        )

        page.update()
        await asyncio.sleep(8)
        self.show_login(page)


def main(page: ft.Page):
    page.title = APP_NAME
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.window_width = 430
    page.window_min_width = 320
    page.window_height = 850

    app = CyberApp()

    async def start():
        await app.splash(page)

    page.run_task(start)


if __name__ == "__main__":
    ft.run(main)
