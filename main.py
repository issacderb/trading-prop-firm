"""
=============================================================================
PROP FIRM DUAL-ENGINE LIVE FORWARD TEST BOT & PROFESSIONAL QUANT JOURNAL
=============================================================================
"""

import os
import time
import json
import threading
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

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

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if self.path == "/export-csv":
            self.send_response(200)
            self.send_header("Content-type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=prop_firm_trade_journal.csv")
            self.end_headers()
            history = GLOBAL_STATE["ledger"].get("history", [])
            df_hist = pd.DataFrame(history) if len(history) > 0 else pd.DataFrame()
            self.wfile.write(df_hist.to_csv(index=False).encode("utf-8"))
            return

        if self.path == "/export-json":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=forward_test_ledger.json")
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_STATE["ledger"], indent=2).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        ledger = GLOBAL_STATE["ledger"]
        pos = GLOBAL_STATE["active_position"]
        curr_price = GLOBAL_STATE["current_price"]
        pnl_dollar = ledger["account_balance"] - INITIAL_BALANCE
        pnl_pct = (pnl_dollar / INITIAL_BALANCE) * 100
        
        pos_html = """
        <div style='background:#1e293b; padding:18px; border-radius:14px; border-left:4px solid #64748b; margin-bottom:20px;'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <span style='color:#94a3b8; font-weight:600;'>Trạng thái Vị thế (Active Position):</span>
                <span style='color:#38bdf8; font-weight:bold; font-size:13px;'>● Đang quét Real-time Binance Futures</span>
            </div>
            <div style='color:#f8fafc; font-weight:600; margin-top:6px;'>Hiện chưa có lệnh nào đang mở. Bot đang chờ tín hiệu chuẩn phiên tiếp theo.</div>
        </div>
        """
        if pos:
            color = "#10b981" if pos["direction"] == "LONG" else "#ef4444"
            pos_html = f"""
            <div style='background:#1e293b; padding:20px; border-radius:14px; border-left:5px solid {color}; margin-bottom:24px; box-shadow:0 10px 25px -5px rgba(0,0,0,0.3);'>
                <div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>
                    <div>
                        <span style='font-size:20px; font-weight:800; color:{color};'>⚡ VỊ THẾ LIVE: {pos["direction"]} ({pos["symbol"]})</span>
                        <div style='color:#94a3b8; font-size:13px; margin-top:2px;'>Vào lúc: {pos.get("entry_time", "")} • {pos["setup"]}</div>
                    </div>
                    <span style='background:{color}22; color:{color}; padding:6px 14px; border-radius:30px; font-size:13px; font-weight:700; border:1px solid {color}44;'>
                        RỦI RO: 0.5% (${pos["risk_amount_dollar"]:,.2f})
                    </span>
                </div>
                <div style='display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:14px; margin-top:16px; background:#0f172a; padding:14px; border-radius:10px;'>
                    <div><small style='color:#94a3b8;'>Giá vào (Entry)</small><div style='font-size:17px; font-weight:bold; color:#f8fafc;'>${pos["entry_price"]:,.2f}</div></div>
                    <div><small style='color:#94a3b8;'>Cắt lỗ (Stop Loss)</small><div style='font-size:17px; font-weight:bold; color:#ef4444;'>${pos["sl_price"]:,.2f}</div></div>
                    <div><small style='color:#94a3b8;'>Chốt lời (Take Profit)</small><div style='font-size:17px; font-weight:bold; color:#10b981;'>${pos["tp_price"]:,.2f}</div></div>
                    <div><small style='color:#94a3b8;'>Giá Live</small><div style='font-size:17px; font-weight:bold; color:#38bdf8;'>${curr_price:,.2f}</div></div>
                </div>
            </div>
            """
            
        history_rows = ""
        for t in reversed(ledger.get("history", [])):
            res_color = "#10b981" if t.get("pnl_r", 0) > 0 else "#ef4444"
            history_rows += f"""
            <tr style='border-bottom:1px solid #334155;'>
                <td style='padding:12px 14px; font-weight:700; color:#38bdf8;'>#{t.get("trade_id", "-")}</td>
                <td style='padding:12px 14px;'><div style='font-weight:600;'>{t.get("direction", "")}</div><small style='color:#94a3b8;'>{t.get("setup", "")}</small></td>
                <td style='padding:12px 14px;'>${t.get("entry_price", 0):,.2f}<br><small style='color:#94a3b8;'>{t.get("entry_time", "")}</small></td>
                <td style='padding:12px 14px;'>${t.get("exit_price", 0):,.2f}<br><small style='color:#94a3b8;'>{t.get("exit_time", "")}</small></td>
                <td style='padding:12px 14px;'>{t.get("hold_time_mins", "-")} phút</td>
                <td style='padding:12px 14px; font-weight:800; color:{res_color};'>{t.get("pnl_r", 0):+.2f}R<br><small>{t.get("dollar_pnl", 0):+,.2f}$</small></td>
                <td style='padding:12px 14px; font-weight:bold; color:#f8fafc;'>${t.get("balance_after", 0):,.2f}</td>
            </tr>
            """
        if not history_rows:
            history_rows = "<tr><td colspan='7' style='text-align:center; padding:32px; color:#64748b;'>Chưa có lệnh nào đóng.</td></tr>"

        html = f"""
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Nhật Ký Giao Dịch Thể Chế - Prop Firm Quant Bot</title>
            <meta http-equiv="refresh" content="10">
            <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
            <style>
                body {{ font-family: 'Plus Jakarta Sans', sans-serif; background: #0b1329; color: #f8fafc; margin: 0; padding: 24px; }}
                .container {{ max-width: 1080px; margin: 0 auto; }}
                .card {{ background: #1e293b; border-radius: 16px; padding: 22px; border: 1px solid #334155; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 24px; }}
                .stat-box {{ background: #0f172a; border: 1px solid #334155; padding: 18px; border-radius: 14px; }}
                .badge {{ background: #10b98122; color: #10b981; padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 13px; border: 1px solid #10b98144; }}
                table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13.5px; }}
                th {{ padding: 14px; background: #0f172a; color: #94a3b8; font-weight: 700; font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.5px; }}
                .btn {{ background: #38bdf8; color: #0f172a; padding: 8px 16px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; }}
                .btn:hover {{ background: #7dd3fc; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 24px; flex-wrap:wrap; gap:12px;">
                    <div>
                        <h1 style="margin:0; font-size:26px; font-weight:800; background:linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                            NHẬT KÝ GIAO DỊCH THỂ CHẾ (PROP FIRM JOURNAL)
                        </h1>
                        <p style="margin:4px 0 0 0; color:#94a3b8; font-size:14px;">Quản trị vốn 0.5% • Cắt lỗ 1.2x ATR • Chốt lời 1.35R • Nguồn Binance Futures Live</p>
                    </div>
                    <div style="text-align:right;">
                        <span class="badge">● LIVE 24/7 CLOUD ONLINE</span>
                        <div style="color:#64748b; font-size:12px; margin-top:6px;">Giờ VN: {get_vn_time_str()}</div>
                    </div>
                </div>

                <div class="grid">
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Số Dư Quỹ Hiện Tại</small>
                        <div style="font-size:24px; font-weight:800; color:#38bdf8; margin-top:4px;">${ledger["account_balance"]:,.2f}</div>
                        <small style="color:{'#10b981' if pnl_dollar>=0 else '#ef4444'}; font-weight:700;">{pnl_dollar:+,.2f}$ ({pnl_pct:+.2f}%)</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Giá BTC Futures Live</small>
                        <div style="font-size:24px; font-weight:800; color:#f8fafc; margin-top:4px;">${curr_price:,.2f}</div>
                        <small style="color:#94a3b8;">Cập nhật lúc: {GLOBAL_STATE["last_scan_time"]}</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Tỷ Lệ Thắng (Win Rate)</small>
                        <div style="font-size:24px; font-weight:800; color:#10b981; margin-top:4px;">{ledger["win_rate"]}%</div>
                        <small style="color:#94a3b8;">{ledger["wins"]} Thắng / {ledger["losses"]} Thua ({ledger["total_trades"]} lệnh)</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Sụt Giảm Tối Đa (Max DD)</small>
                        <div style="font-size:24px; font-weight:800; color:#f59e0b; margin-top:4px;">{ledger["max_drawdown_pct"]}%</div>
                        <small style="color:#10b981; font-weight:600;">🛡️ An toàn (Giới hạn 8% Quỹ)</small>
                    </div>
                </div>

                {pos_html}

                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; flex-wrap:wrap; gap:10px;">
                        <h3 style="margin:0; font-size:17px; color:#f8fafc;">
                            📜 SỔ CÁI LỊCH SỬ GIAO DỊCH CHI TIẾT
                        </h3>
                        <div style="display:flex; gap:10px;">
                            <a href="/export-csv" class="btn">📥 Tải Excel (CSV)</a>
                            <a href="/export-json" class="btn" style="background:#334155; color:#f8fafc;">📄 Tải JSON</a>
                        </div>
                    </div>
                    <div style="overflow-x:auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Thiết lập / Hướng</th>
                                    <th>Giá vào & Giờ vào</th>
                                    <th>Giá ra & Giờ ra</th>
                                    <th>Thời gian giữ</th>
                                    <th>PnL (R & $)</th>
                                    <th>Số dư sau lệnh</th>
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
    print(f"[HTTP] Professional Journal listening on port {PORT}...")
    server.serve_forever()

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
                    data = json.load(f)
                    if data.get("total_trades", 0) > 0:
                        return data
            except Exception:
                pass
        return {
            "account_balance": 98982.60,
            "peak_balance": 100000.0,
            "max_drawdown_pct": 1.02,
            "total_trades": len(SEED_HISTORY),
            "wins": sum(1 for x in SEED_HISTORY if x["pnl_r"] > 0),
            "losses": sum(1 for x in SEED_HISTORY if x["pnl_r"] <= 0),
            "win_rate": round(sum(1 for x in SEED_HISTORY if x["pnl_r"] > 0) / len(SEED_HISTORY) * 100, 1),
            "profit_factor": 0.0,
            "expectancy_r": -1.02,
            "active_position": None,
            "history": list(SEED_HISTORY)
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

    def fetch_live_price(self):
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        params = {"symbol": SYMBOL}
        try:
            r = requests.get(url, params=params, timeout=5)
            data = r.json()
            return float(data["price"])
        except Exception:
            return None

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
        
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        
        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(np.abs(df["high"] - df["close"].shift(1)), np.abs(df["low"] - df["close"].shift(1)))
        )
        df["atr"] = tr.rolling(window=14).mean().bfill()
        df["vol_sma"] = df["volume"].rolling(window=20).mean().bfill()
        df["vol_spike"] = df["volume"] > (1.3 * df["vol_sma"])
        
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

    def manage_active_position(self, current_live_price):
        if not self.active_position or current_live_price is None:
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
            if current_live_price <= sl:
                closed = True
                outcome = "LOSS (Stop-Loss Hit)"
                exit_price = sl
                pnl_r = -1.02
            elif current_live_price >= tp:
                closed = True
                outcome = "WIN (Take-Profit Hit)"
                exit_price = tp
                pnl_r = 1.35 - 0.02
        else:
            if current_live_price >= sl:
                closed = True
                outcome = "LOSS (Stop-Loss Hit)"
                exit_price = sl
                pnl_r = -1.02
            elif current_live_price <= tp:
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
            
            hold_mins = int((datetime.now(VN_TZ).timestamp() - pos.get("entry_ts", datetime.now(VN_TZ).timestamp())) / 60)
            
            pos_record = {
                "trade_id": self.ledger["total_trades"],
                "symbol": pos["symbol"],
                "direction": d,
                "setup": pos["setup"],
                "entry_time": pos["entry_time"],
                "entry_price": entry,
                "sl_price": sl,
                "tp_price": tp,
                "exit_time": get_vn_time_str("%H:%M:%S %d/%m"),
                "exit_price": exit_price,
                "hold_time_mins": max(5, hold_mins),
                "outcome": outcome,
                "pnl_r": round(pnl_r, 3),
                "dollar_pnl": round(dollar_pnl, 2),
                "balance_after": round(self.ledger["account_balance"], 2)
            }
            self.ledger["history"].append(pos_record)
            self.active_position = None
            self.save_ledger()
            
            msg = (
                f"🔔 <b>[LỆNH ĐÃ ĐÓNG - NHẬT KÝ FORWARD TEST]</b>\n\n"
                f"• Lệnh ID: <b>#{pos_record['trade_id']} ({SYMBOL})</b>\n"
                f"• Vị thế: <b>{d}</b>\n"
                f"• Kết quả: <b>{'🟢' if pnl_r > 0 else '🔴'} {outcome}</b>\n"
                f"• PnL: <b>{'+' if dollar_pnl > 0 else ''}${dollar_pnl:,.2f} ({pnl_r:+.2f}R)</b>\n"
                f"• Số dư Quỹ mới: <b>${self.ledger['account_balance']:,.2f}</b>\n"
                f"• Win Rate: <b>{self.ledger['win_rate']}% ({self.ledger['wins']}W / {self.ledger['losses']}L)</b>\n"
                f"• Thời gian giữ: <b>{pos_record['hold_time_mins']} phút</b>\n"
                f"• Nguồn dữ liệu: <b>Binance USDⓈ-M Futures (Live)</b>"
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
        
        in_london = (7 <= hour <= 11)
        asia_h = curr["asia_high"]
        asia_l = curr["asia_low"]
        
        l_eng1 = in_london and (curr["low"] < asia_l) and (curr["close"] > asia_l) and (curr["close"] > curr["ema20"])
        s_eng1 = in_london and (curr["high"] > asia_h) and (curr["close"] < asia_h) and (curr["close"] < curr["ema20"])
        
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
                "entry_ts": datetime.now(VN_TZ).timestamp(),
                "entry_time": get_vn_time_str("%H:%M:%S %d/%m"),
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "risk_amount_dollar": self.ledger["account_balance"] * RISK_PER_TRADE_PCT
            }
            self.save_ledger()
            
            msg = (
                f"🚀 <b>[TÍN HIỆU FORWARD TEST MỚI - PROP FIRM DUAL ENGINE]</b>\n\n"
                f"• Cặp: <b>{SYMBOL} ({INTERVAL}) - Binance USDⓈ-M Futures</b>\n"
                f"• Thiết lập: <b>{setup_name}</b>\n"
                f"• Hướng: <b>{'🟢 MUA (LONG)' if signal == 1 else '🔴 BÁN (SHORT)'}</b>\n"
                f"• Giá vào (Entry): <b>${entry_price:,.2f}</b>\n"
                f"• Cắt lỗ (Stop Loss): <b>${sl_price:,.2f}</b> (1.2x ATR)\n"
                f"• Chốt lời (Take Profit): <b>${tp_price:,.2f}</b> (1.35R)\n"
                f"• Rủi ro vị thế (0.5% Quỹ): <b>${self.active_position['risk_amount_dollar']:,.2f}</b>\n"
                f"• Thời gian quét: <b>{get_vn_time_str()}</b>"
            )
            self.send_telegram_alert(msg)

    def start_loop(self):
        print(f"[{get_vn_time_str()}] Live Forward Test Engine active on {SYMBOL} {INTERVAL} (Binance USD-M Futures)...")
        
        while True:
            try:
                live_price = self.fetch_live_price()
                if live_price is not None:
                    GLOBAL_STATE["current_price"] = live_price
                    GLOBAL_STATE["last_scan_time"] = get_vn_time_str("%H:%M:%S")
                    if self.active_position:
                        self.manage_active_position(live_price)

                df = self.fetch_live_m5_data(limit=120)
                self.scan_for_new_entry(df)
            except Exception as e:
                print(f"⚠️ Scan error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    t = threading.Thread(target=run_dashboard_server, daemon=True)
    t.start()
    
    bot = LiveForwardTester()
    bot.start_loop()
