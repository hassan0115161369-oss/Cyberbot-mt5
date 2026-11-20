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

# أسعار ابتدائية لوضع المحاكاة عند عدم الاتصال بالوسيط
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
        return data if isinstance(data, list) else data.get
