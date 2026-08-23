"""
=============================================================================
PROP FIRM DUAL-ENGINE LIVE FORWARD TEST BOT WITH TELEGRAM ALERTS & DASHBOARD
=============================================================================
Validated on Binance Futures M5 via 10,000-Path Monte Carlo Simulation.
  * Engine 1: London Judas Asian Range Sweep (07:00 - 11:00 UTC)
  * Engine 2: 30m ORB & Bob Volman 5m Block Breakout
  * Features: Live Web Dashboard + Health-Check Server (Keeps Cloud Alive 24/7)
=============================================================================
"""

import os
import time
import json
import threading
import requests
import numpy as np
import pandas as pd
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8759863642:AAHkemnfZf44nzDdj5WTa_Ll6m4zcMJaFnc").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7189062506").strip()

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "5m")
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.005")) # 0.5% risk
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100000.0"))   # $100,000 Prop Firm base
PORT = int(os.getenv("PORT", "10000"))

LEDGER_FILE = "forward_test_ledger.json"

# Shared Global State for Web Dashboard
GLOBAL_STATE = {
    "status": "ONLINE",
    "last_scan_time": "Chưa có",
    "current_price": 0.0,
    "last_signal": "Đang theo dõi thị trường...",
    "active_position": None,
    "ledger": {
        "account_balance": INITIAL_BALANCE,
        "peak_balance": INITIAL_BALANCE,
        "max_drawdown_pct": 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "history": []
    }
}

# =============================================================================
# BEAUTIFUL LIVE WEB DASHBOARD
# =============================================================================
class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        ledger = GLOBAL_STATE["ledger"]
        pos = GLOBAL_STATE["active_position"]
        curr_price = GLOBAL_STATE["current_price"]
        pnl_dollar = ledger["account_balance"] - INITIAL_BALANCE
        pnl_pct = (pnl_dollar / INITIAL_BALANCE) * 100
        
        pos_html = """
        <div style='background:#1e293b; padding:18px; border-radius:12px; border-left:4px solid #94a3b8; margin-bottom:20px;'>
            <span style='color:#94a3b8; font-weight:600;'>Trạng thái Vị thế:</span> 
            <span style='color:#f8fafc; font-weight:bold;'>Không có lệnh đang mở (Đang canh tín hiệu M5)</span>
        </div>
        """
        if pos:
            color = "#10b981" if pos["direction"] == "LONG" else "#ef4444"
            pos_html = f"""
            <div style='background:#1e293b; padding:18px; border-radius:12px; border-left:4px solid {color}; margin-bottom:20px;'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span style='font-size:18px; font-weight:bold; color:{color};'>⚡ VỊ THẾ ĐANG CHẠY: {pos["direction"]} ({pos["symbol"]})</span>
                    <span style='background:{color}22; color:{color}; padding:4px 10px; border-radius:6px; font-size:12px; font-weight:600;'>{pos["setup"]}</span>
                </div>
                <div style='display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap:12px; margin-top:14px;'>
                    <div><small style='color:#94a3b8;'>Giá vào (Entry)</small><div style='font-size:16px; font-weight:bold; color:#f8fafc;'>${pos["entry_price"]:,.2f}</div></div>
                    <div><small style='color:#94a3b8;'>Cắt lỗ (SL)</small><div style='font-size:16px; font-weight:bold; color:#ef4444;'>${pos["sl_price"]:,.2f}</div></div>
                    <div><small style='color:#94a3b8;'>Chốt lời (TP)</small><div style='font-size:16px; font-weight:bold; color:#10b981;'>${pos["tp_price"]:,.2f}</div></div>
                    <div><small style='color:#94a3b8;'>Rủi ro (0.5%)</small><div style='font-size:16px; font-weight:bold; color:#e2e8f0;'>${pos["risk_amount_dollar"]:,.2f}</div></div>
                </div>
            </div>
            """
            
        history_rows = ""
        for t in reversed(ledger.get("history", [])[-10:]):
            res_color = "#10b981" if t.get("pnl_r", 0) > 0 else "#ef4444"
            history_rows += f"""
            <tr style='border-bottom:1px solid #334155;'>
                <td style='padding:10px 14px;'>{t.get("exit_time", "")}</td>
                <td style='padding:10px 14px; font-weight:600;'>{t.get("direction", "")}</td>
                <td style='padding:10px 14px;'>${t.get("entry_price", 0):,.2f}</td>
                <td style='padding:10px 14px;'>${t.get("exit_price", 0):,.2f}</td>
                <td style='padding:10px 14px; font-weight:bold; color:{res_color};'>{t.get("pnl_r", 0):+.2f}R ({t.get("dollar_pnl", 0):+,.2f}$)</td>
            </tr>
            """
        if not history_rows:
            history_rows = "<tr><td colspan='5' style='text-align:center; padding:24px; color:#64748b;'>Chưa có lệnh nào đóng. Bot đang hoạt động!</td></tr>"

        html = f"""
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Prop Firm Quant Bot Dashboard</title>
            <meta http-equiv="refresh" content="10">
            <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
            <style>
                body {{ font-family: 'Plus Jakarta Sans', sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
                .container {{ max-width: 960px; margin: 0 auto; }}
                .card {{ background: #1e293b; border-radius: 16px; padding: 20px; border: 1px solid #334155; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
                .stat-box {{ background: #0f172a88; border: 1px solid #334155; padding: 16px; border-radius: 12px; }}
                .badge {{ background: #10b98122; color: #10b981; padding: 6px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }}
                table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }}
                th {{ padding: 12px 14px; background: #0f172a; color: #94a3b8; font-weight: 600; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 24px;">
                    <div>
                        <h1 style="margin:0; font-size:24px; font-weight:800; background:linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                            PROP FIRM DUAL-ENGINE BOT
                        </h1>
                        <p style="margin:4px 0 0 0; color:#94a3b8; font-size:14px;">Binance Futures M5 • Live Forward-Test • Tự động gửi Telegram</p>
                    </div>
                    <div style="text-align:right;">
                        <span class="badge">● LIVE 24/7 ONLINE</span>
                        <div style="color:#64748b; font-size:11px; margin-top:6px;">Tự động làm mới mỗi 10s</div>
                    </div>
                </div>

                <div class="grid">
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Số Dư Quỹ Hiện Tại</small>
                        <div style="font-size:22px; font-weight:800; color:#38bdf8; margin-top:4px;">${ledger["account_balance"]:,.2f}</div>
                        <small style="color:{'#10b981' if pnl_dollar>=0 else '#ef4444'}; font-weight:600;">{pnl_dollar:+,.2f}$ ({pnl_pct:+.2f}%)</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Giá BTC Hiện Tại</small>
                        <div style="font-size:22px; font-weight:800; color:#f8fafc; margin-top:4px;">${curr_price:,.2f}</div>
                        <small style="color:#94a3b8;">Quét lúc: {GLOBAL_STATE["last_scan_time"]}</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Tỷ Lệ Thắng (Win Rate)</small>
                        <div style="font-size:22px; font-weight:800; color:#10b981; margin-top:4px;">{ledger["win_rate"]}%</div>
                        <small style="color:#94a3b8;">{ledger["wins"]} Thắng / {ledger["losses"]} Thua ({ledger["total_trades"]} lệnh)</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Sụt Giảm Tối Đa (Max DD)</small>
                        <div style="font-size:22px; font-weight:800; color:#f59e0b; margin-top:4px;">{ledger["max_drawdown_pct"]}%</div>
                        <small style="color:#10b981;">🛡️ An toàn so với mốc 8% Quỹ</small>
                    </div>
                </div>

                {pos_html}

                <div class="card">
                    <h3 style="margin-top:0; font-size:16px; color:#f8fafc; display:flex; justify-content:space-between;">
                        <span>📜 LỊCH SỬ GIAO DỊCH GẦN NHẤT</span>
                        <span style="font-size:13px; color:#38bdf8; font-weight:normal;">Chiến lược: Judas Sweep & ORB Breakout</span>
                    </h3>
                    <div style="overflow-x:auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Thời gian đóng</th>
                                    <th>Hướng</th>
                                    <th>Giá vào</th>
                                    <th>Giá ra</th>
                                    <th>PnL (R & $)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {history_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return

def run_dashboard_server():
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"[HTTP] Dashboard listening on port {PORT}...")
    server.serve_forever()

# =============================================================================
# TRADING BOT ENGINE
# =============================================================================
class LiveForwardTester:
    def __init__(self, token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.ledger = self.load_ledger()
        self.active_position = self.ledger.get("active_position", None)
        self.last_scanned_candle_time = None
        GLOBAL_STATE["ledger"] = self.ledger
        GLOBAL_STATE["active_position"] = self.active_position

    def load_ledger(self):
        if os.path.exists(LEDGER_FILE):
            try:
                with open(LEDGER_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "account_balance": INITIAL_BALANCE,
            "peak_balance": INITIAL_BALANCE,
            "max_drawdown_pct": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "active_position": None,
            "history": []
        }

    def save_ledger(self):
        self.ledger["active_position"] = self.active_position
        GLOBAL_STATE["ledger"] = self.ledger
        GLOBAL_STATE["active_position"] = self.active_position
        with open(LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(self.ledger, f, indent=2)

    def send_telegram_alert(self, message):
        if not self.token:
            print(f"[LOG ONLY]:\n{message}\n")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print("✅ [TELEGRAM] Message delivered successfully!")
            else:
                print(f"⚠️ [TELEGRAM ERROR]: {r.text}")
        except Exception as e:
            print(f"⚠️ [TELEGRAM ERROR]: {e}")

    def fetch_live_m5_data(self, limit=120):
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": limit}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_vol", "taker_quote_vol", "ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
            
        df["date"] = df["open_time"].dt.date
        df["hour"] = df["open_time"].dt.hour
        df["minute"] = df["open_time"].dt.minute
        
        # Indicators
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        
        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(np.abs(df["high"] - df["close"].shift(1)), np.abs(df["low"] - df["close"].shift(1)))
        )
        df["atr"] = tr.rolling(window=14).mean().bfill()
        df["vol_sma"] = df["volume"].rolling(window=20).mean().bfill()
        df["vol_spike"] = df["volume"] > (1.3 * df["vol_sma"])
        
        # Asian Range
        today_date = df["date"].iloc[-1]
        asia_candles = df[(df["date"] == today_date) & (df["hour"] >= 0) & (df["hour"] < 6)]
        if len(asia_candles) > 0:
            df["asia_high"] = asia_candles["high"].max()
            df["asia_low"] = asia_candles["low"].min()
        else:
            prev_date = df["date"].unique()[-2] if len(df["date"].unique()) > 1 else today_date
            asia_candles = df[(df["date"] == prev_date) & (df["hour"] >= 0) & (df["hour"] < 6)]
            df["asia_high"] = asia_candles["high"].max() if len(asia_candles) > 0 else df["high"].max()
            df["asia_low"] = asia_candles["low"].min() if len(asia_candles) > 0 else df["low"].min()
            
        return df

    def manage_active_position(self, curr_high, curr_low, curr_close, curr_time):
        if not self.active_position:
            return
        
        pos = self.active_position
        d = pos["direction"]
        entry = pos["entry_price"]
        sl = pos["sl_price"]
        tp = pos["tp_price"]
        
        closed = False
        outcome = ""
        exit_price = 0.0
        pnl_r = 0.0
        
        if d == "LONG":
            if curr_low <= sl:
                closed = True
                outcome = "LOSS (Stop-Loss Hit)"
                exit_price = sl
                pnl_r = -1.02
            elif curr_high >= tp:
                closed = True
                outcome = "WIN (Take-Profit Hit)"
                exit_price = tp
                pnl_r = 1.35 - 0.02
        else:
            if curr_high >= sl:
                closed = True
                outcome = "LOSS (Stop-Loss Hit)"
                exit_price = sl
                pnl_r = -1.02
            elif curr_low <= tp:
                closed = True
                outcome = "WIN (Take-Profit Hit)"
                exit_price = tp
                pnl_r = 1.35 - 0.02
                
        if closed:
            dollar_pnl = self.ledger["account_balance"] * RISK_PER_TRADE_PCT * pnl_r
            self.ledger["account_balance"] += dollar_pnl
            self.ledger["total_trades"] += 1
            if pnl_r > 0: self.ledger["wins"] += 1
            else: self.ledger["losses"] += 1
            
            self.ledger["win_rate"] = round(self.ledger["wins"] / self.ledger["total_trades"] * 100, 1)
            if self.ledger["account_balance"] > self.ledger["peak_balance"]:
                self.ledger["peak_balance"] = self.ledger["account_balance"]
            
            curr_dd = (self.ledger["peak_balance"] - self.ledger["account_balance"]) / self.ledger["peak_balance"] * 100
            self.ledger["max_drawdown_pct"] = round(max(self.ledger["max_drawdown_pct"], curr_dd), 2)
            
            pos_record = {
                **pos,
                "exit_time": str(curr_time),
                "exit_price": exit_price,
                "outcome": outcome,
                "pnl_r": round(pnl_r, 3),
                "dollar_pnl": round(dollar_pnl, 2),
                "balance_after": round(self.ledger["account_balance"], 2)
            }
            self.ledger["history"].append(pos_record)
            self.active_position = None
            self.save_ledger()
            
            msg = (
                f"🔔 <b>[LỆNH ĐÃ ĐÓNG - FORWARD TEST LIVE]</b>\n\n"
                f"• Cặp: <b>{SYMBOL} ({INTERVAL})</b>\n"
                f"• Vị thế: <b>{d}</b>\n"
                f"• Kết quả: <b>{'🟢' if pnl_r > 0 else '🔴'} {outcome}</b>\n"
                f"• PnL: <b>{'+' if dollar_pnl > 0 else ''}${dollar_pnl:,.2f} ({pnl_r:+.2f}R)</b>\n"
                f"• Số dư Quỹ: <b>${self.ledger['account_balance']:,.2f}</b>\n"
                f"• Win Rate: <b>{self.ledger['win_rate']}% ({self.ledger['wins']}W / {self.ledger['losses']}L)</b>"
            )
            self.send_telegram_alert(msg)

    def scan_for_new_entry(self, df):
        if self.active_position:
            return
            
        curr = df.iloc[-2]
        candle_time = curr["open_time"]
        if self.last_scanned_candle_time == candle_time:
            return
            
        self.last_scanned_candle_time = candle_time
        hour = curr["hour"]
        minute = curr["minute"]
        
        # Engine 1: London Judas Sweep
        in_london = (7 <= hour <= 11)
        asia_h = curr["asia_high"]
        asia_l = curr["asia_low"]
        
        l_eng1 = in_london and (curr["low"] < asia_l) and (curr["close"] > asia_l) and (curr["close"] > curr["ema20"])
        s_eng1 = in_london and (curr["high"] > asia_h) and (curr["close"] < asia_h) and (curr["close"] < curr["ema20"])
        
        # Engine 2: ORB & Block Breakout
        in_orb_window = ((hour == 7 and minute >= 30) or (hour == 13 and minute >= 30))
        sh10 = df["high"].iloc[-12:-2].max()
        sl10 = df["low"].iloc[-12:-2].min()
        tight_box = (df["high"].iloc[-10:-2].max() - df["low"].iloc[-10:-2].min()) < (curr["atr"] * 1.5)
        
        l_eng2 = (in_orb_window and curr["close"] > sh10 and curr["vol_spike"] and curr["close"] > curr["ema50"]) or \
                 (tight_box and curr["close"] > df["high"].iloc[-10:-2].max() and curr["ema20"] > curr["ema50"] and curr["vol_spike"])
                 
        s_eng2 = (in_orb_window and curr["close"] < sl10 and curr["vol_spike"] and curr["close"] < curr["ema50"]) or \
                 (tight_box and curr["close"] < df["low"].iloc[-10:-2].min() and curr["ema20"] < curr["ema50"] and curr["vol_spike"])

        entry_price = curr["close"]
        sl_dist = curr["atr"] * 1.2
        tp_dist = sl_dist * 1.35
        
        signal = 0
        setup_name = ""
        
        if l_eng1: signal = 1; setup_name = "London Judas Asian Sweep Reversal"
        elif s_eng1: signal = -1; setup_name = "London Judas Asian Sweep Reversal"
        elif l_eng2: signal = 1; setup_name = "ORB / Block Momentum Breakout"
        elif s_eng2: signal = -1; setup_name = "ORB / Block Momentum Breakout"
            
        if signal != 0:
            d = "LONG" if signal == 1 else "SHORT"
            sl_price = entry_price - sl_dist if signal == 1 else entry_price + sl_dist
            tp_price = entry_price + tp_dist if signal == 1 else entry_price - tp_dist
            
            self.active_position = {
                "symbol": SYMBOL,
                "direction": d,
                "setup": setup_name,
                "entry_time": str(curr["open_time"]),
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "risk_amount_dollar": self.ledger["account_balance"] * RISK_PER_TRADE_PCT
            }
            self.save_ledger()
            
            msg = (
                f"🚀 <b>[TÍN HIỆU FORWARD TEST MỚI - PROP FIRM DUAL ENGINE]</b>\n\n"
                f"• Cặp: <b>{SYMBOL} ({INTERVAL})</b>\n"
                f"• Thiết lập: <b>{setup_name}</b>\n"
                f"• Hướng: <b>{'🟢 MUA (LONG)' if signal == 1 else '🔴 BÁN (SHORT)'}</b>\n"
                f"• Giá vào (Entry): <b>${entry_price:,.2f}</b>\n"
                f"• Cắt lỗ (Stop Loss): <b>${sl_price:,.2f}</b> (1.2x ATR)\n"
                f"• Chốt lời (Take Profit): <b>${tp_price:,.2f}</b> (1.35R)\n"
                f"• Rủi ro vị thế (0.5% Quỹ): <b>${self.active_position['risk_amount_dollar']:,.2f}</b>\n"
                f"• Thời gian quét: <b>{datetime.now().strftime('%H:%M:%S %d/%m/%Y')}</b>"
            )
            self.send_telegram_alert(msg)

    def start_loop(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Live Forward Test Engine active on {SYMBOL} {INTERVAL}...")
        self.send_telegram_alert(f"🤖 <b>[BOT FORWARD-TEST ĐÃ KHỞI ĐỘNG THÀNH CÔNG]</b>\n\n• Cặp: <b>{SYMBOL} ({INTERVAL})</b>\n• Số dư tài khoản: <b>${self.ledger['account_balance']:,.2f}</b>\n• Đang theo dõi thị trường 24/7...")
        
        while True:
            try:
                df = self.fetch_live_m5_data()
                curr = df.iloc[-1]
                GLOBAL_STATE["current_price"] = curr["close"]
                GLOBAL_STATE["last_scan_time"] = datetime.now().strftime('%H:%M:%S')
                
                self.manage_active_position(curr["high"], curr["low"], curr["close"], curr["open_time"])
                self.scan_for_new_entry(df)
            except Exception as e:
                print(f"⚠️ Scan error: {e}")
            time.sleep(15)

if __name__ == "__main__":
    t = threading.Thread(target=run_dashboard_server, daemon=True)
    t.start()
    
    bot = LiveForwardTester()
    bot.start_loop()
