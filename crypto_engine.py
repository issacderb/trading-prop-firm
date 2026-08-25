"""
=============================================================================
PROP FIRM DUAL-ENGINE LIVE FORWARD TEST BOT & PROFESSIONAL QUANT JOURNAL
=============================================================================
"""

import os
import sys
import time
import json
import threading
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Vietnam Timezone (UTC+7)
VN_TZ = timezone(timedelta(hours=7))

def get_vn_time_str(fmt="%H:%M:%S %d/%m/%Y"):
    return datetime.now(VN_TZ).strftime(fmt)

# Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8759863642:AAHkemnfZf44nzDdj5WTa_Ll6m4zcMJaFnc").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7189062506").strip()

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "5m")
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.005")) # 0.5% risk
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100000.0"))   # $100,000 Prop Firm base
PORT = int(os.getenv("PORT", "10000"))

LEDGER_FILE = "forward_test_ledger.json"

# Seed default historical trades so Render container restarts never lose ledger history
SEED_HISTORY = [
    {
        "trade_id": 1,
        "symbol": "BTCUSDT",
        "direction": "SHORT",
        "setup": "London Judas Asian Sweep Reversal",
        "entry_time": "17:55:16 24/08",
        "entry_price": 77623.10,
        "sl_price": 77817.47,
        "tp_price": 77360.70,
        "exit_time": "18:20:10 24/08",
        "exit_price": 77817.47,
        "hold_time_mins": 25,
        "outcome": "LOSS (Stop-Loss Hit)",
        "pnl_r": -1.02,
        "dollar_pnl": -510.00,
        "balance_after": 99490.00
    },
    {
        "trade_id": 2,
        "symbol": "BTCUSDT",
        "direction": "SHORT",
        "setup": "ORB / Block Momentum Breakout",
        "entry_time": "20:35:05 24/08",
        "entry_price": 79250.00,
        "sl_price": 79445.20,
        "tp_price": 78980.50,
        "exit_time": "21:10:45 24/08",
        "exit_price": 79445.20,
        "hold_time_mins": 35,
        "outcome": "LOSS (Stop-Loss Hit)",
        "pnl_r": -1.02,
        "dollar_pnl": -507.40,
        "balance_after": 98982.60
    }
]

GLOBAL_STATE = {
    "status": "ONLINE",
    "last_scan_time": "Chưa có",
    "current_price": 0.0,
    "last_signal": "Đang theo dõi thị trường...",
    "active_position": None,
    "ledger": {
        "account_balance": 98982.60,
        "peak_balance": 100000.0,
        "max_drawdown_pct": 1.02,
        "total_trades": 2,
        "wins": 0,
        "losses": 2,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "expectancy_r": -1.02,
        "history": list(SEED_HISTORY)
    }
}

# -----------------------------------------------------------------------------
# Telegram Notification Helpers
# -----------------------------------------------------------------------------
def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] Token or Chat ID not configured.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False

# -----------------------------------------------------------------------------
# Ledger Management
# -----------------------------------------------------------------------------
def load_ledger():
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, "r") as f:
                data = json.load(f)
                GLOBAL_STATE["ledger"] = data
                return
        except Exception as e:
            print(f"[LEDGER] Load error: {e}")
    # Save default seed
    save_ledger()

def save_ledger():
    try:
        with open(LEDGER_FILE, "w") as f:
            json.dump(GLOBAL_STATE["ledger"], f, indent=2)
    except Exception as e:
        print(f"[LEDGER] Save error: {e}")

def recalculate_metrics():
    ledger = GLOBAL_STATE["ledger"]
    history = ledger["history"]
    if not history:
        return

    wins = [t for t in history if "WIN" in t["outcome"]]
    losses = [t for t in history if "LOSS" in t["outcome"]]

    ledger["total_trades"] = len(history)
    ledger["wins"] = len(wins)
    ledger["losses"] = len(losses)
    ledger["win_rate"] = (len(wins) / len(history)) * 100 if history else 0.0

    total_win_dollars = sum(t["dollar_pnl"] for t in wins)
    total_loss_dollars = abs(sum(t["dollar_pnl"] for t in losses))
    ledger["profit_factor"] = (total_win_dollars / total_loss_dollars) if total_loss_dollars > 0 else (99.0 if total_win_dollars > 0 else 0.0)

    total_r = sum(t["pnl_r"] for t in history)
    ledger["expectancy_r"] = total_r / len(history) if history else 0.0

    running_balance = INITIAL_BALANCE
    peak = INITIAL_BALANCE
    max_dd = 0.0
    for t in history:
        running_balance = t["balance_after"]
        if running_balance > peak:
            peak = running_balance
        dd = ((peak - running_balance) / peak) * 100
        if dd > max_dd:
            max_dd = dd

    ledger["account_balance"] = history[-1]["balance_after"] if history else INITIAL_BALANCE
    ledger["peak_balance"] = peak
    ledger["max_drawdown_pct"] = max_dd
    save_ledger()

# -----------------------------------------------------------------------------
# Binance Market Data & Indicator Calculation
# -----------------------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="5m", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(VN_TZ)
            return df
    except Exception as e:
        print(f"[DATA ERROR] {e}")
    return None

def compute_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def compute_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# -----------------------------------------------------------------------------
# Dual-Engine Strategy Implementation
# -----------------------------------------------------------------------------
def check_signals(df_5m, df_30m):
    if df_5m is None or len(df_5m) < 30:
        return None

    last_candle = df_5m.iloc[-2]
    current_time = last_candle["time"]
    hour = current_time.hour
    minute = current_time.minute
    close_price = last_candle["close"]
    high_price = last_candle["high"]
    low_price = last_candle["low"]
    open_price = last_candle["open"]

    df_5m['ema20'] = compute_ema(df_5m['close'], 20)
    df_5m['atr14'] = compute_atr(df_5m, 14)
    atr = df_5m['atr14'].iloc[-2]
    ema20 = df_5m['ema20'].iloc[-2]

    # ENGINE 1: LONDON JUDAS ASIAN SWEEP (14:00 - 18:00 VN)
    if 14 <= hour < 18:
        asian_df = df_5m[(df_5m['time'].dt.hour >= 7) & (df_5m['time'].dt.hour < 14)]
        if len(asian_df) >= 12:
            asian_high = asian_df['high'].max()
            asian_low = asian_df['low'].min()

            if high_price > asian_high and close_price < asian_high and close_price < open_price:
                sl = high_price + (atr * 0.2)
                risk = sl - close_price
                if risk > 0:
                    tp = close_price - (risk * 2.0)
                    return {
                        "setup": "London Judas Asian Sweep Reversal",
                        "direction": "SHORT",
                        "entry": close_price,
                        "sl": sl,
                        "tp": tp,
                        "risk_dollar": INITIAL_BALANCE * RISK_PER_TRADE_PCT
                    }

            if low_price < asian_low and close_price > asian_low and close_price > open_price:
                sl = low_price - (atr * 0.2)
                risk = close_price - sl
                if risk > 0:
                    tp = close_price + (risk * 2.0)
                    return {
                        "setup": "London Judas Asian Sweep Reversal",
                        "direction": "LONG",
                        "entry": close_price,
                        "sl": sl,
                        "tp": tp,
                        "risk_dollar": INITIAL_BALANCE * RISK_PER_TRADE_PCT
                    }

    # ENGINE 2: 30m ORB / BLOCK BREAKOUT (20:00 - 23:30 VN)
    if (20 <= hour < 23) or (hour == 23 and minute <= 30):
        recent_4 = df_5m.iloc[-6:-2]
        block_range = recent_4['high'].max() - recent_4['low'].min()
        block_high = recent_4['high'].max()
        block_low = recent_4['low'].min()

        if block_range <= (atr * 1.5):
            if close_price > block_high and close_price > ema20 and (close_price - open_price) > (atr * 0.4):
                sl = block_low - (atr * 0.1)
                risk = close_price - sl
                if risk > 0:
                    tp = close_price + (risk * 2.0)
                    return {
                        "setup": "ORB / Block Momentum Breakout",
                        "direction": "LONG",
                        "entry": close_price,
                        "sl": sl,
                        "tp": tp,
                        "risk_dollar": INITIAL_BALANCE * RISK_PER_TRADE_PCT
                    }

            if close_price < block_low and close_price < ema20 and (open_price - close_price) > (atr * 0.4):
                sl = block_high + (atr * 0.1)
                risk = sl - close_price
                if risk > 0:
                    tp = close_price - (risk * 2.0)
                    return {
                        "setup": "ORB / Block Momentum Breakout",
                        "direction": "SHORT",
                        "entry": close_price,
                        "sl": sl,
                        "tp": tp,
                        "risk_dollar": INITIAL_BALANCE * RISK_PER_TRADE_PCT
                    }

    return None

def manage_active_trade(df_5m):
    active = GLOBAL_STATE["active_position"]
    if not active or df_5m is None:
        return

    current_price = df_5m.iloc[-1]["close"]
    active["current_price"] = current_price
    direction = active["direction"]
    sl = active["sl_price"]
    tp = active["tp_price"]
    entry = active["entry_price"]
    risk_dollar = active["risk_dollar"]

    hit_sl = (current_price <= sl) if direction == "LONG" else (current_price >= sl)
    hit_tp = (current_price >= tp) if direction == "LONG" else (current_price <= tp)

    if hit_sl or hit_tp:
        outcome = "WIN (Take-Profit Hit)" if hit_tp else "LOSS (Stop-Loss Hit)"
        exit_price = tp if hit_tp else sl
        pnl_r = 2.0 if hit_tp else -1.02
        dollar_pnl = (risk_dollar * 2.0) if hit_tp else (-risk_dollar * 1.02)
        new_balance = GLOBAL_STATE["ledger"]["account_balance"] + dollar_pnl

        closed_trade = {
            "trade_id": len(GLOBAL_STATE["ledger"]["history"]) + 1,
            "symbol": active["symbol"],
            "direction": direction,
            "setup": active["setup"],
            "entry_time": active["entry_time"],
            "entry_price": entry,
            "sl_price": sl,
            "tp_price": tp,
            "exit_time": get_vn_time_str("%H:%M:%S %d/%m"),
            "exit_price": exit_price,
            "outcome": outcome,
            "pnl_r": round(pnl_r, 2),
            "dollar_pnl": round(dollar_pnl, 2),
            "balance_after": round(new_balance, 2)
        }

        GLOBAL_STATE["ledger"]["history"].append(closed_trade)
        recalculate_metrics()
        GLOBAL_STATE["active_position"] = None

        status_emoji = "🟢 WIN TAKE-PROFIT" if hit_tp else "🔴 LOSS STOP-LOSS"
        msg = (
            f"{status_emoji} #{closed_trade['trade_id']}\n\n"
            f"🎯 *Setup:* {closed_trade['setup']}\n"
            f"⚡ *Direction:* {direction} {closed_trade['symbol']}\n"
            f"💵 *PnL:* {closed_trade['pnl_r']:+.2f}R ({closed_trade['dollar_pnl']:+,.2f}$)\n"
            f"🏦 *New Balance:* ${closed_trade['balance_after']:,.2f}\n"
            f"📊 *Win Rate:* {GLOBAL_STATE['ledger']['win_rate']:.1f}% | *PF:* {GLOBAL_STATE['ledger']['profit_factor']:.2f}"
        )
        send_telegram(msg)
        print(f"[TRADE CLOSED] {outcome} -> PnL: {dollar_pnl}$")

def main_loop():
    print("=================================================================")
    print(f" PROP FIRM DUAL-ENGINE BOT ONLINE - SYMBOL: {SYMBOL} (5M)")
    print(f" Vietnam Time: {get_vn_time_str()}")
    print("=================================================================")

    load_ledger()
    recalculate_metrics()

    while True:
        try:
            df_5m = fetch_klines(SYMBOL, "5m", 100)
            df_30m = fetch_klines(SYMBOL, "30m", 50)

            if df_5m is not None:
                GLOBAL_STATE["last_scan_time"] = get_vn_time_str()
                GLOBAL_STATE["current_price"] = df_5m.iloc[-1]["close"]

                if GLOBAL_STATE["active_position"]:
                    manage_active_trade(df_5m)
                else:
                    sig = check_signals(df_5m, df_30m)
                    if sig:
                        active_trade = {
                            "symbol": SYMBOL,
                            "direction": sig["direction"],
                            "setup": sig["setup"],
                            "entry_time": get_vn_time_str("%H:%M:%S %d/%m"),
                            "entry_price": sig["entry"],
                            "sl_price": sig["sl"],
                            "tp_price": sig["tp"],
                            "risk_dollar": sig["risk_dollar"],
                            "current_price": sig["entry"]
                        }
                        GLOBAL_STATE["active_position"] = active_trade

                        dir_emoji = "🟢 LONG" if sig["direction"] == "LONG" else "🔴 SHORT"
                        entry_msg = (
                            f"⚡ *NEW INSTITUTIONAL SIGNAL TRIGGERED*\n\n"
                            f"🎯 *Setup:* {sig['setup']}\n"
                            f"📊 *Action:* {dir_emoji} `{SYMBOL}`\n"
                            f"📍 *Entry Price:* `{sig['entry']:.2f}`\n"
                            f"🛑 *Stop-Loss:* `{sig['sl']:.2f}`\n"
                            f"🎯 *Take-Profit:* `{sig['tp']:.2f} (2.0R Target)`\n"
                            f"🛡 *Risk:* `${sig['risk_dollar']:,.2f} ({RISK_PER_TRADE_PCT*100}%)`"
                        )
                        send_telegram(entry_msg)
                        print(f"[SIGNAL TRIGGERED] {sig['setup']} {sig['direction']} @ {sig['entry']}")

        except Exception as e:
            print(f"[CRYPTO MAIN LOOP ERROR] {e}")

        time.sleep(30)
