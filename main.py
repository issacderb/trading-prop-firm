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

# =============================================================================
# CẤU HÌNH — KHÔNG hard-code secret. Bắt buộc lấy từ biến môi trường.
# =============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("[CẢNH BÁO] Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. "
          "Bot vẫn chạy nhưng chỉ log ra stdout, không gửi Telegram.")

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "5m")
INTERVAL_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600}.get(INTERVAL, 300)

RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.005"))   # 0.5% rủi ro/lệnh
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100000.0"))      # $100,000 Prop Firm base
PORT = int(os.getenv("PORT", "10000"))

# --- MÔ HÌNH CHI PHÍ THỰC TẾ (trước đây giả định 0.02R => thấp hơn thực tế 10-25 lần) ---
# Binance USDⓈ-M Futures: taker 0.04%/chiều. Slippage market order trên M5 ~1-2 bps/chiều.
TAKER_FEE_RATE = float(os.getenv("TAKER_FEE_RATE", "0.0004"))          # mỗi chiều
SLIPPAGE_RATE = float(os.getenv("SLIPPAGE_RATE", "0.0001"))            # mỗi chiều
# Đệm trượt giá thêm khi chạm SL (gap qua stop trên M5 là chuyện thường)
STOP_SLIPPAGE_RATE = float(os.getenv("STOP_SLIPPAGE_RATE", "0.0003"))

# --- THAM SỐ CHIẾN LƯỢC (khai báo tập trung để test độ nhạy) ---
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.2"))
RR_TARGET = float(os.getenv("RR_TARGET", "1.35"))
VOL_SPIKE_MULT = float(os.getenv("VOL_SPIKE_MULT", "1.3"))
BOX_ATR_MULT = float(os.getenv("BOX_ATR_MULT", "1.5"))
BREAKOUT_LOOKBACK = int(os.getenv("BREAKOUT_LOOKBACK", "10"))

# --- LUẬT PROP FIRM (trước đây hoàn toàn không có) ---
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.05"))   # 5%/ngày
MAX_TOTAL_DD_PCT = float(os.getenv("MAX_TOTAL_DD_PCT", "0.10"))          # 10% tổng
MIN_STOP_PCT = float(os.getenv("MIN_STOP_PCT", "0.0015"))  # stop < 0.15% giá thì phí ăn hết edge -> bỏ lệnh

# --- CHỐNG LOOK-AHEAD ---
# Tín hiệu chỉ hợp lệ nếu nến vừa đóng chưa quá ngưỡng này. Trước đây bot có thể
# vào lệnh bằng giá close của nến đã đóng 5 phút trước rồi so SL/TP với giá live
# => ghi nhận lệnh thắng ở mức giá chưa bao giờ khớp được (phantom fill).
MAX_SIGNAL_AGE_SEC = int(os.getenv("MAX_SIGNAL_AGE_SEC", "90"))
MAX_ENTRY_DEVIATION = float(os.getenv("MAX_ENTRY_DEVIATION", "0.0015"))  # giá live lệch >0.15% so với close -> bỏ

DATA_DIR = os.getenv("DATA_DIR", ".")
if DATA_DIR and not os.path.isdir(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
LEDGER_FILE = os.path.join(DATA_DIR, "forward_test_ledger.json")


def new_ledger():
    """Sổ cái sạch. KHÔNG seed lịch sử giả — mọi số liệu phải do giao dịch thật sinh ra."""
    return {
        "initial_balance": INITIAL_BALANCE,
        "account_balance": INITIAL_BALANCE,
        "peak_balance": INITIAL_BALANCE,
        "peak_equity": INITIAL_BALANCE,       # đỉnh tính cả PnL đang mở (mark-to-market)
        "max_drawdown_pct": 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "expectancy_r": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "total_fees_paid": 0.0,
        "sum_r": 0.0,
        "day_anchor_date": None,        # ngày UTC đang tính daily loss
        "day_anchor_balance": INITIAL_BALANCE,
        "halted": False,
        "halt_reason": "",
        "active_position": None,
        "history": []
    }


GLOBAL_STATE = {
    "status": "ONLINE",
    "last_scan_time": "Chưa có",
    "current_price": 0.0,
    "last_signal": "Đang theo dõi thị trường...",
    "active_position": None,
    "ledger": new_ledger()
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
                <td style='padding:12px 14px; font-weight:800; color:{res_color};'>{t.get("pnl_r", 0):+.2f}R<br><small>{t.get("dollar_pnl", 0):+,.2f}$</small><br><small style='color:#94a3b8; font-weight:500;'>phí -{t.get("fees", 0):,.2f}$ ({t.get("fees_in_r", 0):.2f}R)</small></td>
                <td style='padding:12px 14px; font-weight:bold; color:#f8fafc;'>${t.get("balance_after", 0):,.2f}</td>
            </tr>
            """
        if not history_rows:
            history_rows = "<tr><td colspan='7' style='text-align:center; padding:32px; color:#64748b;'>Chưa có lệnh nào đóng.</td></tr>"

        # Cảnh báo cỡ mẫu: dưới 100 lệnh thì mọi chỉ số chỉ là nhiễu thống kê.
        n_tr = ledger["total_trades"]
        if n_tr < 100:
            sample_warning = f"""
            <div style='background:#422006; border:1px solid #a16207; border-radius:14px; padding:16px 18px; margin-bottom:20px;'>
                <div style='color:#fbbf24; font-weight:800; font-size:15px;'>⚠️ CẢNH BÁO CỠ MẪU: {n_tr}/100 LỆNH</div>
                <div style='color:#fde68a; font-size:13px; margin-top:6px; line-height:1.6;'>
                    Với RR {RR_TARGET} cần tối thiểu <b>100 lệnh</b> (lý tưởng 150-300) mới phân biệt được edge thật
                    với may mắn. Mọi con số Win Rate / Profit Factor / Expectancy phía trên hiện <b>chưa có ý nghĩa thống kê</b>.
                    Hệ thống cũng <b>chưa có backtest / out-of-sample validation</b> — xem AUDIT.md.
                </div>
            </div>
            """
        else:
            sample_warning = ""

        if ledger.get("halted"):
            halt_html = f"""
            <div style='background:#450a0a; border:1px solid #dc2626; border-radius:14px; padding:16px 18px; margin-bottom:20px;'>
                <div style='color:#f87171; font-weight:800; font-size:15px;'>🛑 BOT ĐANG DỪNG GIAO DỊCH</div>
                <div style='color:#fecaca; font-size:13px; margin-top:6px;'>{ledger.get("halt_reason", "")}</div>
            </div>
            """
        else:
            halt_html = ""

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
                        <p style="margin:4px 0 0 0; color:#94a3b8; font-size:14px;">Rủi ro {RISK_PER_TRADE_PCT*100:.1f}%/lệnh • SL {SL_ATR_MULT}x ATR • TP {RR_TARGET}R • Phí+slippage đã tính vào PnL • Binance Futures Live</p>
                    </div>
                    <div style="text-align:right;">
                        <span class="badge">● LIVE FORWARD TEST (chưa có backtest)</span>
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
                        <small style="color:#94a3b8; font-weight:600;">Mark-to-market • Giới hạn {MAX_TOTAL_DD_PCT*100:.0f}%</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Profit Factor</small>
                        <div style="font-size:24px; font-weight:800; color:#a78bfa; margin-top:4px;">{ledger.get("profit_factor", 0)}</div>
                        <small style="color:#94a3b8;">Lãi gộp ${ledger.get("gross_profit", 0):,.0f} / Lỗ gộp ${ledger.get("gross_loss", 0):,.0f}</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Kỳ Vọng / Lệnh (Expectancy)</small>
                        <div style="font-size:24px; font-weight:800; color:{'#10b981' if ledger.get('expectancy_r', 0) >= 0 else '#ef4444'}; margin-top:4px;">{ledger.get("expectancy_r", 0):+.3f}R</div>
                        <small style="color:#94a3b8;">Tổng {ledger.get("sum_r", 0):+.2f}R qua {ledger["total_trades"]} lệnh</small>
                    </div>
                    <div class="stat-box">
                        <small style="color:#94a3b8;">Tổng Phí + Slippage Đã Trả</small>
                        <div style="font-size:24px; font-weight:800; color:#f87171; margin-top:4px;">-${ledger.get("total_fees_paid", 0):,.2f}</div>
                        <small style="color:#94a3b8;">Taker {TAKER_FEE_RATE*100:.3f}%/chiều — đã tính vào PnL</small>
                    </div>
                </div>

                {sample_warning}
                {halt_html}
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

    # ------------------------------------------------------------------
    # PERSISTENCE
    # ------------------------------------------------------------------
    def load_ledger(self):
        """Nạp sổ cái. Nếu file hỏng -> BÁO LỖI RÕ RÀNG, không âm thầm reset về số liệu giả."""
        if os.path.exists(LEDGER_FILE):
            try:
                with open(LEDGER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                base = new_ledger()
                base.update(data)          # tương thích ngược khi thêm field mới
                return base
            except Exception as e:
                print(f"❌ [LEDGER] File {LEDGER_FILE} hỏng ({e}). "
                      f"Đổi tên file để giữ bằng chứng rồi khởi tạo sổ mới.")
                try:
                    os.rename(LEDGER_FILE, LEDGER_FILE + ".corrupt")
                except Exception:
                    pass
        if DATA_DIR in (".", ""):
            print("⚠️  [LEDGER] Đang lưu sổ cái vào disk của container. "
                  "Trên Render free tier disk là ephemeral -> mất lịch sử mỗi lần restart. "
                  "Hãy set DATA_DIR trỏ tới persistent disk hoặc chuyển sang DB.")
        return new_ledger()

    def save_ledger(self):
        self.ledger["active_position"] = self.active_position
        GLOBAL_STATE["ledger"] = self.ledger
        GLOBAL_STATE["active_position"] = self.active_position
        try:
            tmp = LEDGER_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.ledger, f, indent=2)
            os.replace(tmp, LEDGER_FILE)   # ghi nguyên tử, tránh file hỏng khi bị kill giữa chừng
        except Exception as e:
            print(f"⚠️ [LEDGER] Không lưu được: {e}")

    def send_telegram_alert(self, message):
        if not self.token or not self.chat_id:
            print(f"[LOG ONLY]:\n{message}\n")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print("✅ [TELEGRAM] Message delivered successfully!")
            else:
                print(f"⚠️ [TELEGRAM ERROR]: {r.text}")
        except Exception as e:
            print(f"⚠️ [TELEGRAM ERROR]: {e}")

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------
    def fetch_live_price(self):
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        try:
            r = requests.get(url, params={"symbol": SYMBOL}, timeout=5)
            return float(r.json()["price"])
        except Exception:
            return None

    def fetch_live_m5_data(self, limit=288):
        """limit mặc định 288 nến M5 = 24h.

        Trước đây limit=120 (chỉ 10h) khiến phiên Á (0h-6h UTC) bị cắt cụt khi quét
        lúc 11h UTC => asia_high/asia_low hẹp hơn thực tế => sinh tín hiệu sweep giả.
        """
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": limit}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_vol", "taker_quote_vol", "ignore"
        ])
        # Gắn timezone tường minh: Binance trả về UTC. Trước đây naive -> lẫn lộn với giờ VN.
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["date"] = df["open_time"].dt.date
        df["hour"] = df["open_time"].dt.hour       # LUÔN là giờ UTC
        df["minute"] = df["open_time"].dt.minute

        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(np.abs(df["high"] - df["close"].shift(1)),
                       np.abs(df["low"] - df["close"].shift(1)))
        )
        # KHÔNG dùng .bfill(): bfill kéo giá trị tương lai ngược về quá khứ (look-ahead).
        df["atr"] = tr.rolling(window=ATR_PERIOD).mean()
        # vol_sma phải shift(1) để không so sánh nến với chính nó.
        df["vol_sma"] = df["volume"].rolling(window=20).mean().shift(1)
        df["vol_spike"] = df["volume"] > (VOL_SPIKE_MULT * df["vol_sma"])

        return df

    @staticmethod
    def compute_asia_range(df, ref_time):
        """Biên độ phiên Á 0h-6h UTC của ngày đang xét.

        Trả về (high, low, is_complete). is_complete=False khi cửa sổ dữ liệu không
        phủ đủ phiên Á -> chiến lược sweep phải bỏ qua thay vì dùng mức sai.
        """
        target_date = ref_time.date()
        asia = df[(df["date"] == target_date) & (df["hour"] >= 0) & (df["hour"] < 6)]
        if len(asia) == 0:
            return None, None, False
        expected = 6 * 60 // (INTERVAL_SECONDS // 60)      # số nến lý thuyết của 6 giờ
        # yêu cầu phủ >=90% phiên Á và phiên Á đã kết thúc
        is_complete = (len(asia) >= expected * 0.9) and (ref_time.hour >= 6)
        return asia["high"].max(), asia["low"].min(), is_complete

    @staticmethod
    def ny_open_utc_hour(ts):
        """Giờ UTC của 09:30 New York cho ngày ts — xử lý DST (14:30 mùa đông, 13:30 mùa hè)."""
        try:
            from zoneinfo import ZoneInfo
            ny = ts.astimezone(ZoneInfo("America/New_York"))
            ny_open = ny.replace(hour=9, minute=30, second=0, microsecond=0)
            return ny_open.astimezone(timezone.utc)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # RISK GUARD (luật prop firm — trước đây hoàn toàn không tồn tại)
    # ------------------------------------------------------------------
    def roll_daily_anchor(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.ledger.get("day_anchor_date") != today:
            self.ledger["day_anchor_date"] = today
            self.ledger["day_anchor_balance"] = self.ledger["account_balance"]
            # hết ngày thì gỡ halt do daily loss, nhưng KHÔNG gỡ halt do max DD tổng
            if self.ledger.get("halted") and "NGÀY" in self.ledger.get("halt_reason", ""):
                self.ledger["halted"] = False
                self.ledger["halt_reason"] = ""
            self.save_ledger()

    def check_risk_limits(self):
        """Trả về True nếu được phép mở lệnh mới."""
        self.roll_daily_anchor()
        if self.ledger.get("halted"):
            return False

        anchor = self.ledger.get("day_anchor_balance", INITIAL_BALANCE)
        bal = self.ledger["account_balance"]

        daily_dd = (anchor - bal) / anchor if anchor > 0 else 0.0
        if daily_dd >= DAILY_LOSS_LIMIT_PCT:
            self.ledger["halted"] = True
            self.ledger["halt_reason"] = f"CHẠM GIỚI HẠN LỖ NGÀY {DAILY_LOSS_LIMIT_PCT*100:.0f}% (-{daily_dd*100:.2f}%)"
            self.save_ledger()
            self.send_telegram_alert(
                f"🛑 <b>[DỪNG GIAO DỊCH - LUẬT PROP FIRM]</b>\n\n"
                f"• Lý do: <b>{self.ledger['halt_reason']}</b>\n"
                f"• Số dư đầu ngày: <b>${anchor:,.2f}</b>\n"
                f"• Số dư hiện tại: <b>${bal:,.2f}</b>\n"
                f"• Bot sẽ tự mở khoá vào ngày giao dịch kế tiếp."
            )
            return False

        total_dd = (self.ledger["peak_balance"] - bal) / self.ledger["peak_balance"] if self.ledger["peak_balance"] > 0 else 0.0
        if total_dd >= MAX_TOTAL_DD_PCT:
            self.ledger["halted"] = True
            self.ledger["halt_reason"] = f"CHẠM MAX DRAWDOWN TỔNG {MAX_TOTAL_DD_PCT*100:.0f}% (-{total_dd*100:.2f}%)"
            self.save_ledger()
            self.send_telegram_alert(
                f"🛑 <b>[DỪNG GIAO DỊCH VĨNH VIỄN - VI PHẠM MAX DRAWDOWN]</b>\n\n"
                f"• Lý do: <b>{self.ledger['halt_reason']}</b>\n"
                f"• Đỉnh vốn: <b>${self.ledger['peak_balance']:,.2f}</b>\n"
                f"• Hiện tại: <b>${bal:,.2f}</b>\n"
                f"• Cần review lại chiến lược trước khi chạy tiếp."
            )
            return False

        return True

    def mark_to_market(self, live_price):
        """Cập nhật đỉnh/đáy equity theo giá live, kể cả PnL đang mở.

        Trước đây max_drawdown chỉ tính trên lệnh đã đóng -> báo cáo DD thấp hơn thực tế.
        """
        equity = self.ledger["account_balance"]
        pos = self.active_position
        if pos and live_price:
            sign = 1 if pos["direction"] == "LONG" else -1
            equity += sign * (live_price - pos["entry_price"]) * pos["qty"] - pos.get("est_total_fee", 0.0)

        if equity > self.ledger.get("peak_equity", equity):
            self.ledger["peak_equity"] = equity
        peak = self.ledger.get("peak_equity", equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        if dd > self.ledger["max_drawdown_pct"]:
            self.ledger["max_drawdown_pct"] = round(dd, 2)
        GLOBAL_STATE["current_equity"] = equity
        return equity

    def recompute_stats(self):
        """Tính lại TOÀN BỘ chỉ số từ lịch sử. Trước đây profit_factor và
        expectancy_r không bao giờ được cập nhật mà vẫn hiển thị lên dashboard."""
        hist = self.ledger["history"]
        n = len(hist)
        self.ledger["total_trades"] = n
        if n == 0:
            return
        wins = [t for t in hist if t["dollar_pnl"] > 0]
        losses = [t for t in hist if t["dollar_pnl"] <= 0]
        gross_profit = sum(t["dollar_pnl"] for t in wins)
        gross_loss = abs(sum(t["dollar_pnl"] for t in losses))

        self.ledger["wins"] = len(wins)
        self.ledger["losses"] = len(losses)
        self.ledger["win_rate"] = round(len(wins) / n * 100, 1)
        self.ledger["gross_profit"] = round(gross_profit, 2)
        self.ledger["gross_loss"] = round(gross_loss, 2)
        self.ledger["profit_factor"] = (round(gross_profit / gross_loss, 2) if gross_loss > 0
                                        else (99.99 if gross_profit > 0 else 0.0))
        self.ledger["sum_r"] = round(sum(t["pnl_r"] for t in hist), 3)
        self.ledger["expectancy_r"] = round(self.ledger["sum_r"] / n, 3)
        self.ledger["total_fees_paid"] = round(sum(t.get("fees", 0.0) for t in hist), 2)

    # ------------------------------------------------------------------
    # QUẢN LÝ VỊ THẾ
    # ------------------------------------------------------------------
    def manage_active_position(self, current_live_price):
        if not self.active_position or current_live_price is None:
            return

        pos = self.active_position
        d = pos["direction"]
        entry = pos["entry_price"]
        sl = pos["sl_price"]
        tp = pos["tp_price"]
        qty = pos["qty"]

        closed = False
        outcome = ""
        raw_exit = 0.0

        if d == "LONG":
            if current_live_price <= sl:
                closed, outcome = True, "LOSS (Stop-Loss Hit)"
                # Chạm stop thì khớp XẤU HƠN mức stop (gap/slippage), không khớp đúng SL.
                raw_exit = min(sl, current_live_price) * (1 - STOP_SLIPPAGE_RATE)
            elif current_live_price >= tp:
                closed, outcome = True, "WIN (Take-Profit Hit)"
                raw_exit = tp * (1 - SLIPPAGE_RATE)
        else:
            if current_live_price >= sl:
                closed, outcome = True, "LOSS (Stop-Loss Hit)"
                raw_exit = max(sl, current_live_price) * (1 + STOP_SLIPPAGE_RATE)
            elif current_live_price <= tp:
                closed, outcome = True, "WIN (Take-Profit Hit)"
                raw_exit = tp * (1 + SLIPPAGE_RATE)

        if not closed:
            return

        # PnL tính TỪ GIÁ THOÁT THỰC TẾ, trừ phí theo notional hai chiều.
        # Trước đây pnl_r là hằng số cứng (+1.33 / -1.02) bất kể exit_price.
        sign = 1 if d == "LONG" else -1
        gross_pnl = sign * (raw_exit - entry) * qty
        entry_fee = pos["entry_notional"] * TAKER_FEE_RATE
        exit_fee = abs(raw_exit * qty) * TAKER_FEE_RATE
        fees = entry_fee + exit_fee
        dollar_pnl = gross_pnl - fees

        risk_dollar = pos["risk_amount_dollar"]
        pnl_r = dollar_pnl / risk_dollar if risk_dollar > 0 else 0.0

        self.ledger["account_balance"] += dollar_pnl
        if self.ledger["account_balance"] > self.ledger["peak_balance"]:
            self.ledger["peak_balance"] = self.ledger["account_balance"]

        entry_ts = pos.get("entry_ts") or datetime.now(timezone.utc).timestamp()
        hold_mins = max(0, int((datetime.now(timezone.utc).timestamp() - entry_ts) / 60))

        pos_record = {
            "trade_id": len(self.ledger["history"]) + 1,
            "symbol": pos["symbol"],
            "direction": d,
            "setup": pos["setup"],
            "entry_time": pos["entry_time"],
            "entry_price": round(entry, 2),
            "sl_price": round(sl, 2),
            "tp_price": round(tp, 2),
            "qty": round(qty, 6),
            "exit_time": get_vn_time_str("%H:%M:%S %d/%m"),
            "exit_price": round(raw_exit, 2),
            "hold_time_mins": hold_mins,
            "outcome": outcome,
            "gross_pnl": round(gross_pnl, 2),
            "fees": round(fees, 2),
            "fees_in_r": round(fees / risk_dollar, 3) if risk_dollar > 0 else 0.0,
            "pnl_r": round(pnl_r, 3),
            "dollar_pnl": round(dollar_pnl, 2),
            "balance_after": round(self.ledger["account_balance"], 2)
        }
        self.ledger["history"].append(pos_record)
        self.active_position = None
        self.recompute_stats()
        self.mark_to_market(current_live_price)
        self.save_ledger()

        msg = (
            f"🔔 <b>[LỆNH ĐÃ ĐÓNG - NHẬT KÝ FORWARD TEST]</b>\n\n"
            f"• Lệnh ID: <b>#{pos_record['trade_id']} ({SYMBOL})</b>\n"
            f"• Vị thế: <b>{d}</b>\n"
            f"• Kết quả: <b>{'🟢' if dollar_pnl > 0 else '🔴'} {outcome}</b>\n"
            f"• Giá vào / ra: <b>${entry:,.2f} → ${raw_exit:,.2f}</b>\n"
            f"• PnL gộp: <b>${gross_pnl:+,.2f}</b>\n"
            f"• Phí + slippage: <b>-${fees:,.2f} ({pos_record['fees_in_r']:.2f}R)</b>\n"
            f"• PnL ròng: <b>{'+' if dollar_pnl > 0 else ''}${dollar_pnl:,.2f} ({pnl_r:+.2f}R)</b>\n"
            f"• Số dư Quỹ mới: <b>${self.ledger['account_balance']:,.2f}</b>\n"
            f"• Win Rate: <b>{self.ledger['win_rate']}% ({self.ledger['wins']}W / {self.ledger['losses']}L)</b>\n"
            f"• Profit Factor: <b>{self.ledger['profit_factor']}</b> | Expectancy: <b>{self.ledger['expectancy_r']}R</b>\n"
            f"• Thời gian giữ: <b>{hold_mins} phút</b>"
        )
        self.send_telegram_alert(msg)
        self.check_risk_limits()

    # ------------------------------------------------------------------
    # TÌM TÍN HIỆU
    # ------------------------------------------------------------------
    def scan_for_new_entry(self, df, live_price):
        if self.active_position:
            return
        if not self.check_risk_limits():
            return
        if live_price is None:
            return

        df = df.dropna(subset=["atr", "vol_sma"])
        if len(df) < BREAKOUT_LOOKBACK + 5:
            return

        curr = df.iloc[-2]                     # nến ĐÃ ĐÓNG gần nhất (tránh repaint)
        candle_time = curr["open_time"]
        if self.last_scanned_candle_time == candle_time:
            return
        self.last_scanned_candle_time = candle_time

        # ---- CHỐNG PHANTOM FILL ----
        now_utc = datetime.now(timezone.utc)
        age = (now_utc - curr["close_time"].to_pydatetime()).total_seconds()
        if age > MAX_SIGNAL_AGE_SEC:
            GLOBAL_STATE["last_signal"] = (
                f"Bỏ qua tín hiệu: nến đã đóng {int(age)}s (>{MAX_SIGNAL_AGE_SEC}s) — "
                f"không thể khớp ở giá đó nữa."
            )
            return

        hour = int(curr["hour"])
        minute = int(curr["minute"])
        atr = float(curr["atr"])
        if atr <= 0:
            return

        # ---- Phiên London (UTC) ----
        in_london = (7 <= hour <= 11)
        asia_h, asia_l, asia_ok = self.compute_asia_range(df, curr["open_time"])

        l_eng1 = s_eng1 = False
        if in_london and asia_ok:
            l_eng1 = (curr["low"] < asia_l) and (curr["close"] > asia_l) and (curr["close"] > curr["ema20"])
            s_eng1 = (curr["high"] > asia_h) and (curr["close"] < asia_h) and (curr["close"] < curr["ema20"])

        # ---- Cửa sổ ORB: London open 08:00 UTC + NY open (đã xử lý DST) ----
        ny_open = self.ny_open_utc_hour(curr["open_time"].to_pydatetime())
        in_ny_orb = False
        if ny_open is not None:
            mins_from_ny_open = (curr["open_time"].to_pydatetime() - ny_open).total_seconds() / 60.0
            in_ny_orb = 0 <= mins_from_ny_open < 60
        in_london_orb = (hour == 8 and minute < 60)
        in_orb_window = in_london_orb or in_ny_orb
        # Nhánh tight_box trước đây nối bằng `or` nên chạy 24/7, mâu thuẫn với mô tả
        # "London Judas / ORB". Nay bắt buộc phải nằm trong phiên.
        in_session = in_london or in_orb_window

        lb = BREAKOUT_LOOKBACK
        prior_high = df["high"].iloc[-(lb + 2):-2].max()
        prior_low = df["low"].iloc[-(lb + 2):-2].min()
        tight_box = (prior_high - prior_low) < (atr * BOX_ATR_MULT)
        vol_spike = bool(curr["vol_spike"])

        l_eng2 = in_session and vol_spike and curr["close"] > prior_high and (
            (in_orb_window and curr["close"] > curr["ema50"]) or (tight_box and curr["ema20"] > curr["ema50"])
        )
        s_eng2 = in_session and vol_spike and curr["close"] < prior_low and (
            (in_orb_window and curr["close"] < curr["ema50"]) or (tight_box and curr["ema20"] < curr["ema50"])
        )

        signal, setup_name = 0, ""
        if l_eng1:
            signal, setup_name = 1, "London Judas Asian Sweep Reversal"
        elif s_eng1:
            signal, setup_name = -1, "London Judas Asian Sweep Reversal"
        elif l_eng2:
            signal, setup_name = 1, "ORB / Block Momentum Breakout"
        elif s_eng2:
            signal, setup_name = -1, "ORB / Block Momentum Breakout"

        if signal == 0:
            return

        # ---- Giá vào phải là GIÁ LIVE, không phải close của nến đã đóng ----
        signal_ref_price = float(curr["close"])
        deviation = abs(live_price - signal_ref_price) / signal_ref_price
        if deviation > MAX_ENTRY_DEVIATION:
            GLOBAL_STATE["last_signal"] = (
                f"Bỏ qua {setup_name}: giá đã chạy {deviation*100:.2f}% khỏi mức tín hiệu."
            )
            return

        # slippage vào lệnh (market order luôn khớp xấu hơn)
        entry_price = live_price * (1 + SLIPPAGE_RATE) if signal == 1 else live_price * (1 - SLIPPAGE_RATE)

        sl_dist = atr * SL_ATR_MULT
        # Stop quá hẹp thì phí ăn hết edge -> không vào lệnh.
        if sl_dist / entry_price < MIN_STOP_PCT:
            GLOBAL_STATE["last_signal"] = (
                f"Bỏ qua {setup_name}: stop {sl_dist/entry_price*100:.3f}% quá hẹp, phí sẽ ăn hết lợi thế."
            )
            return

        tp_dist = sl_dist * RR_TARGET
        sl_price = entry_price - sl_dist if signal == 1 else entry_price + sl_dist
        tp_price = entry_price + tp_dist if signal == 1 else entry_price - tp_dist

        risk_dollar = self.ledger["account_balance"] * RISK_PER_TRADE_PCT
        qty = risk_dollar / sl_dist                      # size sao cho chạm SL = mất đúng risk_dollar
        entry_notional = qty * entry_price
        est_total_fee = entry_notional * TAKER_FEE_RATE * 2

        d = "LONG" if signal == 1 else "SHORT"
        self.active_position = {
            "symbol": SYMBOL,
            "direction": d,
            "setup": setup_name,
            "entry_ts": now_utc.timestamp(),
            "entry_time": get_vn_time_str("%H:%M:%S %d/%m"),
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "qty": qty,
            "entry_notional": entry_notional,
            "est_total_fee": est_total_fee,
            "risk_amount_dollar": risk_dollar
        }
        self.save_ledger()

        fee_in_r = est_total_fee / risk_dollar if risk_dollar > 0 else 0
        net_rr = RR_TARGET - fee_in_r
        breakeven_wr = (1 + fee_in_r) / (net_rr + 1 + fee_in_r) * 100 if (net_rr + 1 + fee_in_r) > 0 else 100

        msg = (
            f"🚀 <b>[TÍN HIỆU FORWARD TEST MỚI - PROP FIRM DUAL ENGINE]</b>\n\n"
            f"• Cặp: <b>{SYMBOL} ({INTERVAL}) - Binance USDⓈ-M Futures</b>\n"
            f"• Thiết lập: <b>{setup_name}</b>\n"
            f"• Hướng: <b>{'🟢 MUA (LONG)' if signal == 1 else '🔴 BÁN (SHORT)'}</b>\n"
            f"• Giá vào (live + slippage): <b>${entry_price:,.2f}</b>\n"
            f"• Cắt lỗ: <b>${sl_price:,.2f}</b> ({SL_ATR_MULT}x ATR = {sl_dist/entry_price*100:.3f}%)\n"
            f"• Chốt lời: <b>${tp_price:,.2f}</b> ({RR_TARGET}R)\n"
            f"• Khối lượng: <b>{qty:.5f} {SYMBOL.replace('USDT','')}</b> (notional ${entry_notional:,.0f})\n"
            f"• Rủi ro ({RISK_PER_TRADE_PCT*100:.1f}% Quỹ): <b>${risk_dollar:,.2f}</b>\n"
            f"• Phí ước tính: <b>${est_total_fee:,.2f} = {fee_in_r:.2f}R</b>\n"
            f"• ⚠️ Win-rate hoà vốn thực tế: <b>{breakeven_wr:.1f}%</b>\n"
            f"• Thời gian: <b>{get_vn_time_str()}</b>"
        )
        GLOBAL_STATE["last_signal"] = f"{setup_name} — {d} @ ${entry_price:,.2f}"
        self.send_telegram_alert(msg)

    # ------------------------------------------------------------------
    def start_loop(self):
        print(f"[{get_vn_time_str()}] Live Forward Test Engine active on {SYMBOL} {INTERVAL} (Binance USD-M Futures)...")
        print(f"  Phí: taker {TAKER_FEE_RATE*100:.3f}%/chiều + slippage {SLIPPAGE_RATE*100:.3f}%/chiều")
        print(f"  Luật rủi ro: lỗ ngày tối đa {DAILY_LOSS_LIMIT_PCT*100:.0f}%, max DD {MAX_TOTAL_DD_PCT*100:.0f}%")

        last_bar_fetch = 0.0
        df = None
        while True:
            try:
                live_price = self.fetch_live_price()
                if live_price is not None:
                    GLOBAL_STATE["current_price"] = live_price
                    GLOBAL_STATE["last_scan_time"] = get_vn_time_str("%H:%M:%S")
                    self.mark_to_market(live_price)
                    if self.active_position:
                        self.manage_active_position(live_price)

                # Chỉ gọi klines mỗi 20s (đủ nhanh so với ngưỡng 90s) để đỡ rate limit
                if time.time() - last_bar_fetch > 20:
                    df = self.fetch_live_m5_data()
                    last_bar_fetch = time.time()

                if df is not None:
                    self.scan_for_new_entry(df, live_price)
            except Exception as e:
                print(f"⚠️ Scan error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    t = threading.Thread(target=run_dashboard_server, daemon=True)
    t.start()

    bot = LiveForwardTester()
    bot.start_loop()
