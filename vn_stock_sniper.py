"""
=============================================================================
VIETNAM STOCK BUFFETT SNIPER & 5% CASH VAULT - FORWARD TESTING SYSTEM
Hệ Thống Forward Test Thực Chiến Cổ Phiếu Việt Nam (Định lượng Giá trị & Két Tiền Mặt 5%)
=============================================================================
"""

import os
import sys
import time
import json
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))

def get_vn_time():
    return datetime.now(VN_TZ)

def get_vn_time_str(fmt="%H:%M:%S %d/%m/%Y"):
    return get_vn_time().strftime(fmt)

# Cấu hình Môi trường & Credentials cho 3 Bot Telegram Cổ Phiếu Riêng Biệt
# 1. BOT WARREN BUFFETT VALUE / MOAT (@Warrenbvaluebot)
VALUE_TELEGRAM_BOT_TOKEN = os.getenv("VALUE_TELEGRAM_BOT_TOKEN", os.getenv("VN_STOCK_TELEGRAM_BOT_TOKEN", "8786802235:AAEGZ03axxEsPuY4_hcIVp-3HVmtVhp0RVw")).strip()
VALUE_TELEGRAM_CHAT_ID = os.getenv("VALUE_TELEGRAM_CHAT_ID", os.getenv("VN_STOCK_TELEGRAM_CHAT_ID", "7189062506")).strip()

# 2. BOT CIGAR BUTT / LAST SMOKE (@Lastsmokewbbot)
CIGAR_TELEGRAM_BOT_TOKEN = os.getenv("CIGAR_TELEGRAM_BOT_TOKEN", "8897938954:AAHg5IcxV_L-C0jHm82TWnue2zrlW47qdqk").strip()
CIGAR_TELEGRAM_CHAT_ID = os.getenv("CIGAR_TELEGRAM_CHAT_ID", "7189062506").strip()

# 3. BOT QUANTAMENTAL 3-TRANCHE SNIPER (@Vipvltradebot - Xịn nhất trái đất)
QUANT_TELEGRAM_BOT_TOKEN = os.getenv("QUANT_TELEGRAM_BOT_TOKEN", "8976230480:AAEsltaLwK8KNNNEOdyphZA5QxNHLzKB98I").strip()
QUANT_TELEGRAM_CHAT_ID = os.getenv("QUANT_TELEGRAM_CHAT_ID", "7189062506").strip()

INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "1000000000.0"))  # 1 Tỷ VNĐ Vốn ban đầu
VAULT_ANNUAL_RATE = float(os.getenv("VAULT_ANNUAL_RATE", "0.05"))     # 5.0% Lãi suất Két tiền mặt/năm
MAX_ALLOC_PER_STOCK_PCT = float(os.getenv("MAX_ALLOC_PER_STOCK_PCT", "0.08")) # Tối đa 8% NAV / 1 mã (80 triệu/mã)
MAX_HOLDINGS_COUNT = int(os.getenv("MAX_HOLDINGS_COUNT", "10"))       # Phân bổ từ 8 đến 10 mã
PORT = int(os.getenv("VN_STOCK_PORT", os.getenv("PORT", "10001")))
SCAN_INTERVAL_SECS = int(os.getenv("SCAN_INTERVAL_SECS", "300"))      # Quét thị trường mỗi 5 phút

LEDGER_FILE = "vn_portfolio_ledger.json"

# 1. Danh sách Watchlist Doanh Nghiệp Vĩ Đại (Quality Moat - HOSE Bluechips)
QUALITY_MOAT_TICKERS = [
    "FPT", "VNM", "HPG", "DGC", "PNJ", 
    "MWG", "ACB", "CTR", "VCB", "REE", 
    "MBB", "TCB", "VHC", "BMP", "GMD"
]

# 2. Danh sách Watchlist Mẩu Tàn Xì Gà (Cigar Butt & Net-Net Săn Cổ Tức - UPCoM / HNX)
CIGAR_BUTT_TICKERS = [
    "CAP", "CLC", "WCS", "TCT", "SMB", 
    "DHA", "NNC", "VFG", "PAC", "D2D", 
    "THG", "DAD", "CAN", "SAV", "LAF"
]

WATCHLIST_TICKERS = QUALITY_MOAT_TICKERS + CIGAR_BUTT_TICKERS

GLOBAL_MOAT_DATA = []
GLOBAL_CIGAR_DATA = []
GLOBAL_WATCHLIST_DATA = []

# =============================================================================
# 1. DATA CONNECTOR (Lấy Dữ Liệu Thực Tế Thị Trường Việt Nam)
# =============================================================================

def fetch_stock_data(ticker: str, category: str = "MOAT") -> dict:
    """Lấy dữ liệu giá và chỉ số tài chính cơ bản thực tế từ Simplize API"""
    url = f"https://api.simplize.vn/api/company/summary/{ticker.lower()}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                res_json = json.loads(resp.read().decode('utf-8'))
                d = res_json.get("data", {})
                price = float(d.get("priceClose") or d.get("priceReferrance") or 0.0)
                roe = float(d.get("roe") or 0.0)
                pe = float(d.get("peRatio") or 0.0)
                pb = float(d.get("pbRatio") or 0.0)
                eps = float(d.get("epsRatio") or 0.0)
                volume_10d = float(d.get("volume10dAvg") or 0.0)
                name_vi = d.get("nameVi") or ticker
                industry = d.get("industryActivity") or "Doanh nghiệp"

                if category == "CIGAR_BUTT":
                    # ĐỊNH GIÁ MẨU TÀN XÌ GÀ (CIGAR BUTT / NET-NET)
                    book_value = (price / pb) if (pb > 0 and price > 0) else price
                    discount_price = book_value * 0.70  # Vùng mua chiết khấu 30%
                    fair_value = book_value * 1.0       # Giá trị thanh lý 100% NCAV
                    
                    status = "🎯 VÙNG RÌNH (ARMED)" if (price <= discount_price or (pb > 0 and pb <= 0.75)) else ("🟡 THEO DÕI XÌ GÀ" if (pb <= 1.1) else "🔴 HẾT HƠI KHÓI")
                    distance_pct = ((price - discount_price) / discount_price * 100.0) if discount_price > 0 else 0.0
                else:
                    # ĐỊNH GIÁ DOANH NGHIỆP VĨ ĐẠI (QUALITY MOAT)
                    target_pe = min(max(roe * 0.55, 10.0), 22.0) if roe > 0 else 12.0
                    fair_value = eps * target_pe if eps > 0 else (price * 1.1 if price > 0 else 50000.0)
                    
                    if price > 0 and (fair_value > price * 2.0 or fair_value < price * 0.5):
                        fair_value = price * (1.0 + (roe - 15.0) / 100.0) if roe > 15 else price * 0.95

                    discount_price = fair_value * 0.80  # Mua chiết khấu 20% (Margin of Safety)
                    distance_pct = ((price - discount_price) / discount_price * 100.0) if discount_price > 0 else 0.0
                    status = "🎯 VÙNG RÌNH (ARMED)" if price <= discount_price else ("🟡 CHỜ CHỈNH" if price <= fair_value else "🔴 ĐẮT")

                return {
                    "ticker": ticker.upper(),
                    "category": category,
                    "name": name_vi,
                    "industry": industry,
                    "price": price,
                    "roe": roe,
                    "pe": pe,
                    "pb": pb,
                    "eps": eps,
                    "volume_10d": volume_10d,
                    "fair_value": round(fair_value, 0),
                    "discount_price": round(discount_price, 0),
                    "distance_pct": round(distance_pct, 1),
                    "status": status,
                    "updated_at": get_vn_time_str()
                }
    except Exception as e:
        print(f"Lỗi lấy dữ liệu {ticker}: {e}")
    
    return {
        "ticker": ticker.upper(),
        "category": category,
        "name": ticker,
        "industry": "N/A",
        "price": 0.0,
        "roe": 0.0,
        "pe": 0.0,
        "pb": 0.0,
        "eps": 0.0,
        "volume_10d": 0.0,
        "fair_value": 0.0,
        "discount_price": 0.0,
        "distance_pct": 0.0,
        "status": "CHỜ CẬP NHẬT",
        "updated_at": get_vn_time_str()
    }

# =============================================================================
# 2. TELEGRAM DISPATCHERS CHO 2 BOT RIÊNG BIỆT
# =============================================================================

def _send_raw_telegram(token: str, chat_id: str, message: str) -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False

def send_telegram_value(message: str) -> bool:
    """Gửi tin nhắn riêng về Bot @Warrenbvaluebot (Quality Moat)"""
    return _send_raw_telegram(VALUE_TELEGRAM_BOT_TOKEN, VALUE_TELEGRAM_CHAT_ID, message)

def send_telegram_cigar(message: str) -> bool:
    """Gửi tin nhắn riêng về Bot @Lastsmokewbbot (Cigar Butt)"""
    return _send_raw_telegram(CIGAR_TELEGRAM_BOT_TOKEN, CIGAR_TELEGRAM_CHAT_ID, message)

def send_telegram_quant(message: str) -> bool:
    """Gửi tin nhắn riêng về Bot @Vipvltradebot (Quantamental 3-Tranche Sniper)"""
    return _send_raw_telegram(QUANT_TELEGRAM_BOT_TOKEN, QUANT_TELEGRAM_CHAT_ID, message)

def send_telegram(message: str) -> bool:
    """Mặc định gửi cho tất cả các bot nếu là thông báo chung"""
    send_telegram_value(message)
    send_telegram_cigar(message)
    send_telegram_quant(message)
    return True

# =============================================================================
# 3. PORTFOLIO & CASH VAULT LEDGER (SỔ CÁI QUẢN LÝ VỐN)
# =============================================================================

class PortfolioLedger:
    def __init__(self, filepath=LEDGER_FILE):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        initial_state = {
            "initial_capital": INITIAL_CAPITAL,
            "cash_vault": INITIAL_CAPITAL,  # 100% Vốn gửi Két tiền mặt 5%/năm từ ngày đầu
            "vault_annual_rate": VAULT_ANNUAL_RATE,
            "vault_interest_earned": 0.0,
            "last_interest_calc_time": get_vn_time().strftime("%Y-%m-%d"),
            "holdings": [],
            "trade_history": [
                {
                    "timestamp": get_vn_time_str(),
                    "ticker": "CASH",
                    "action": "DEPOSIT",
                    "shares": 0,
                    "price": 0.0,
                    "amount": INITIAL_CAPITAL,
                    "reason": "Khởi tạo vốn ban đầu 1 Tỷ VNĐ vào Két tiền mặt 5%/năm (Fresh Start)"
                }
            ],
            "created_at": get_vn_time_str()
        }
        self._save(initial_state)
        return initial_state

    def _save(self, data=None):
        if data is None:
            data = self.data
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Lỗi lưu ledger: {e}")

    def accrue_daily_vault_interest(self):
        """Tính lãi Két tiền mặt 5%/năm tự động cộng dồn hàng ngày"""
        with self.lock:
            today_str = get_vn_time().strftime("%Y-%m-%d")
            last_date = self.data.get("last_interest_calc_time", today_str)
            
            if today_str != last_date:
                cash = self.data.get("cash_vault", 0.0)
                rate = self.data.get("vault_annual_rate", VAULT_ANNUAL_RATE)
                daily_interest = (cash * rate) / 365.0
                
                self.data["cash_vault"] += daily_interest
                self.data["vault_interest_earned"] = self.data.get("vault_interest_earned", 0.0) + daily_interest
                self.data["last_interest_calc_time"] = today_str
                self._save()
                
                print(f"[KÉT TIỀN MẶT 5%] Đã cộng lãi ngày: +{daily_interest:,.0f} VNĐ vào số dư két!")
                return daily_interest
        return 0.0

    def update_prices(self, price_map: dict):
        """Cập nhật giá thị trường hiện tại cho các cổ phiếu đang nắm giữ"""
        with self.lock:
            for item in self.data.get("holdings", []):
                t = item["ticker"]
                if t in price_map and price_map[t] > 0:
                    item["current_price"] = price_map[t]
            self._save()

    def get_portfolio_summary(self) -> dict:
        with self.lock:
            cash = self.data.get("cash_vault", 0.0)
            interest = self.data.get("vault_interest_earned", 0.0)
            initial = self.data.get("initial_capital", INITIAL_CAPITAL)
            
            stock_value = 0.0
            total_divs = 0.0
            holdings_detail = []

            for h in self.data.get("holdings", []):
                shares = h.get("shares", 0)
                avg_p = h.get("avg_price", 0.0)
                curr_p = h.get("current_price", avg_p)
                divs = h.get("dividends_received", 0.0)
                
                cost = shares * avg_p
                mkt_val = shares * curr_p
                pnl = mkt_val - cost + divs
                pnl_pct = (pnl / cost * 100.0) if cost > 0 else 0.0
                
                stock_value += mkt_val
                total_divs += divs
                
                holdings_detail.append({
                    "ticker": h["ticker"],
                    "shares": shares,
                    "avg_price": avg_p,
                    "current_price": curr_p,
                    "cost": cost,
                    "market_value": mkt_val,
                    "pnl": pnl,
                    "pnl_pct": round(pnl_pct, 2),
                    "dividends": divs,
                    "notes": h.get("notes", "")
                })

            total_nav = stock_value + cash
            total_profit = total_nav - initial
            total_return_pct = (total_profit / initial * 100.0) if initial > 0 else 0.0
            equity_pct = (stock_value / total_nav * 100.0) if total_nav > 0 else 0.0
            cash_pct = (cash / total_nav * 100.0) if total_nav > 0 else 0.0

            return {
                "total_nav": total_nav,
                "initial_capital": initial,
                "total_profit": total_profit,
                "total_return_pct": round(total_return_pct, 2),
                "stock_value": stock_value,
                "cash_vault": cash,
                "vault_interest_earned": interest,
                "total_dividends": total_divs,
                "equity_pct": round(equity_pct, 1),
                "cash_pct": round(cash_pct, 1),
                "holdings": holdings_detail,
                "trade_history": self.data.get("trade_history", [])
            }

    def execute_staged_buy(self, ticker: str, price: float, tranche_step: int, reason: str, total_target_alloc: float = 80000000.0) -> dict:
        """
        Thực hiện giải ngân từng phần (Staged Scaling-in 3 Nấc):
        - Tổng hạn mức cho 1 mã: Tối đa 8% NAV (80 Triệu VNĐ / Vốn 1 Tỷ)
        - Tranche 1 (Nấc 1 - 35%): Thăm dò ~28 Triệu VNĐ
        - Tranche 2 (Nấc 2 - 35%): Gia tăng ~28 Triệu VNĐ
        - Tranche 3 (Nấc 3 - 30%): Hoàn tất ~24 Triệu VNĐ
        """
        with self.lock:
            cash = self.data.get("cash_vault", 0.0)
            tranche_ratios = {1: 0.35, 2: 0.35, 3: 0.30}
            ratio = tranche_ratios.get(tranche_step, 0.35)
            alloc = total_target_alloc * ratio

            if cash < alloc * 0.8:
                return {"success": False, "msg": "Két tiền mặt không đủ số dư"}

            shares = int((alloc / price) // 100) * 100
            if shares <= 0:
                shares = 100
            
            total_cost = shares * price
            if total_cost > cash:
                shares -= 100
                total_cost = shares * price

            if shares <= 0:
                return {"success": False, "msg": "Không đủ tiền mua lô 100 CP"}

            self.data["cash_vault"] -= total_cost

            found = False
            for h in self.data.get("holdings", []):
                if h["ticker"] == ticker:
                    prev_shares = h["shares"]
                    prev_cost = prev_shares * h["avg_price"]
                    new_shares = prev_shares + shares
                    new_avg = (prev_cost + total_cost) / new_shares
                    h["shares"] = new_shares
                    h["avg_price"] = round(new_avg, 0)
                    h["current_price"] = price
                    h["tranches_filled"] = tranche_step
                    h["notes"] = f"Tranche {tranche_step}/3 ({int(sum(tranche_ratios[i] for i in range(1, tranche_step+1))*100)}% vị thế) - {reason}"
                    found = True
                    break

            if not found:
                self.data["holdings"].append({
                    "ticker": ticker,
                    "shares": shares,
                    "avg_price": price,
                    "current_price": price,
                    "dividends_received": 0.0,
                    "notes": f"Sniper Buy - {reason}"
                })

            self.data["trade_history"].insert(0, {
                "timestamp": get_vn_time_str(),
                "ticker": ticker,
                "action": "SNIPER_BUY",
                "shares": shares,
                "price": price,
                "amount": total_cost,
                "reason": reason
            })

            self._save()
            return True

LEDGER = PortfolioLedger()
GLOBAL_WATCHLIST_DATA = []
GLOBAL_MOAT_DATA = []
GLOBAL_CIGAR_DATA = []
LAST_SCAN_TIME = "Chưa quét"

# =============================================================================
# 4. ENGINE QUÉT THỊ TRƯỜNG & BẮN TÍN HIỆU
# =============================================================================

def run_market_scan(force_notify=False):
    global GLOBAL_WATCHLIST_DATA, GLOBAL_MOAT_DATA, GLOBAL_CIGAR_DATA, LAST_SCAN_TIME
    print(f"[{get_vn_time_str()}] Đang quét thị trường chứng khoán Việt Nam (Moat & Cigar Butt)...")

    moat_results = []
    cigar_results = []
    price_map = {}
    sniper_opportunities = []

    # 1. Quét Nhóm Doanh Nghiệp Vĩ Đại (Quality Moat)
    for ticker in QUALITY_MOAT_TICKERS:
        d = fetch_stock_data(ticker, category="MOAT")
        moat_results.append(d)
        if d["price"] > 0:
            price_map[ticker] = d["price"]
        if "VÙNG RÌNH" in d["status"] and d["price"] > 0:
            sniper_opportunities.append(d)
        time.sleep(0.12)

    # 2. Quét Nhóm Mẩu Tàn Xì Gà (Cigar Butt / Net-Net)
    for ticker in CIGAR_BUTT_TICKERS:
        d = fetch_stock_data(ticker, category="CIGAR_BUTT")
        cigar_results.append(d)
        if d["price"] > 0:
            price_map[ticker] = d["price"]
        if "VÙNG RÌNH" in d["status"] and d["price"] > 0:
            sniper_opportunities.append(d)
        time.sleep(0.12)

    moat_results.sort(key=lambda x: (0 if "VÙNG RÌNH" in x["status"] else (1 if "CHỜ CHỈNH" in x["status"] else 2), -x["roe"]))
    cigar_results.sort(key=lambda x: (0 if "VÙNG RÌNH" in x["status"] else (1 if "THEO DÕI" in x["status"] else 2), x["pb"] if x["pb"]>0 else 99))

    GLOBAL_MOAT_DATA = moat_results
    GLOBAL_CIGAR_DATA = cigar_results
    GLOBAL_WATCHLIST_DATA = moat_results + cigar_results
    LAST_SCAN_TIME = get_vn_time_str()

    LEDGER.update_prices(price_map)
    LEDGER.accrue_daily_vault_interest()
    summary = LEDGER.get_portfolio_summary()

    # Quét thị trường ngầm, chỉ gửi tin nhắn định kỳ hoặc khi có lệnh khớp thật
    if force_notify:
        send_daily_summary_telegram()

def send_daily_summary_telegram():
    summary = LEDGER.get_portfolio_summary()
    
    holdings_text = ""
    if len(summary["holdings"]) == 0:
        holdings_text = "• _Đang giữ 100% Tiền mặt trong Két 5% (Chưa giải ngân mã nào)_\n"
    else:
        for h in summary["holdings"]:
            pnl_emoji = "🟢" if h["pnl"] >= 0 else "🔴"
            tranche_info = h.get("notes", "Nấc 1/3")
            holdings_text += (
                f"• `{h['ticker']:4}` | {h['shares']:>5,d} CP | "
                f"Giá vốn: `{h['avg_price']:>6,.0f}` | TT: `{h['current_price']:>6,.0f}` | "
                f"PnL: {pnl_emoji} `{h['pnl_pct']:>+5.1f}%`\n"
                f"  ↳ _{tranche_info}_\n"
            )

    pnl_sign = "+" if summary["total_profit"] >= 0 else ""

    # =========================================================================
    # 1. BOT WARREN BUFFETT VALUE (@Warrenbvaluebot) - THEO DÕI DOANH NGHIỆP VĨ ĐẠI
    # =========================================================================
    moat_list_text = ""
    for w in GLOBAL_MOAT_DATA[:8]:
        moat_list_text += f"• `{w['ticker']:4}` | Giá: `{w['price']:>7,.0f}` | MoS 20%: `{w['discount_price']:>7,.0f}` | ROE: `{w['roe']:>4.1f}%` | {w['status']}\n"

    msg_value = (
        f"🏰 *[WARREN BUFFETT QUALITY WATCHLIST]*\n"
        f"📅 *Cập nhật:* {get_vn_time_str()}\n\n"
        f"💰 *TỔNG TÀI SẢN (NAV):* `{summary['total_nav']:,.0f} VNĐ`\n"
        f"🏦 *Két Tiền Mặt 5%/năm:* `{summary['cash_vault']:,.0f} VNĐ` (`{summary['cash_pct']}%`)\n"
        f"✨ *Lãi Két 5% tích lũy:* `+{summary['vault_interest_earned']:,.0f} VNĐ`\n\n"
        f"📋 *DANH SÁCH THEO DÕI DOANH NGHIỆP VĨ ĐẠI (HOSE):*\n"
        f"{moat_list_text}\n"
        f"📦 *Danh mục hiện tại:*\n"
        f"{holdings_text}"
    )
    send_telegram_value(msg_value)

    # =========================================================================
    # 2. BOT LAST SMOKE CIGAR BUTT (@Lastsmokewbbot) - THEO DÕI MẨU TÀN XÌ GÀ UPCoM
    # =========================================================================
    cigar_list_text = ""
    for w in GLOBAL_CIGAR_DATA[:8]:
        cigar_list_text += f"• `{w['ticker']:4}` | Giá: `{w['price']:>7,.0f}` | P/B: `{w['pb']:>4.1f}x` | Mục tiêu: `{w['fair_value']:>7,.0f}` | {w['status']}\n"

    msg_cigar = (
        f"🚬 *[LAST SMOKE - CIGAR BUTT WATCHLIST]*\n"
        f"📅 *Cập nhật:* {get_vn_time_str()}\n\n"
        f"💰 *TỔNG TÀI SẢN (NAV):* `{summary['total_nav']:,.0f} VNĐ`\n"
        f"🏦 *Két Tiền Mặt 5%/năm:* `{summary['cash_vault']:,.0f} VNĐ` (`{summary['cash_pct']}%`)\n"
        f"✨ *Lãi Két 5% tích lũy:* `+{summary['vault_interest_earned']:,.0f} VNĐ`\n\n"
        f"📋 *DANH SÁCH THEO DÕI MẨU TÀN XÌ GÀ (UPCoM/HNX):*\n"
        f"{cigar_list_text}\n"
        f"📦 *Danh mục hiện tại:*\n"
        f"{holdings_text}"
    )
    send_telegram_cigar(msg_cigar)

    # =========================================================================
    # 3. BOT QUANTAMENTAL 3-TRANCHE SNIPER (@Vipvltradebot) - TIẾN ĐỘ RÌNH KỸ THUẬT
    # =========================================================================
    armed_list = [w for w in GLOBAL_WATCHLIST_DATA if "VÙNG RÌNH" in w["status"] or "CHỜ CHỈNH" in w["status"] or "THEO DÕI" in w["status"]][:8]
    armed_text = ""
    for w in armed_list:
        armed_text += f"• `{w['ticker']:4}` | Giá: `{w['price']:>7,.0f}` | Vùng Rình: `{w['discount_price']:>7,.0f}` | {w['status']}\n"
    if not armed_text:
        armed_text = "• _Hiện chưa có mã nào chạm vùng rình. 100% tiền nằm Két 5% đẻ lãi._\n"

    msg_quant = (
        f"🎯 *[QUANTAMENTAL 3-TRANCHE SNIPER WATCHLIST]*\n"
        f"📅 *Cập nhật:* {get_vn_time_str()}\n\n"
        f"💰 *TỔNG TÀI SẢN (NAV):* `{summary['total_nav']:,.0f} VNĐ`\n"
        f"🏦 *Két Tiền Mặt 5%/năm:* `{summary['cash_vault']:,.0f} VNĐ` (`{summary['cash_pct']}%` chờ giải ngân)\n"
        f"✨ *Lãi Két 5% tích lũy:* `+{summary['vault_interest_earned']:,.0f} VNĐ`\n\n"
        f"🏹 *DANH SÁCH THEO DÕI RÌNH KỸ THUẬT (ARMED LIST):*\n"
        f"{armed_text}\n"
        f"📦 *Tiến độ các Tranche vị thế:*\n"
        f"{holdings_text}"
    )
    send_telegram_quant(msg_quant)

def background_scheduler():
    time.sleep(2)
    
    startup_msg = (
        f"[🇻🇳 CHỨNG KHOÁN VN] 🚀 *HỆ THỐNG FORWARD TEST CỔ PHIẾU ĐÃ KHỞI ĐỘNG!*\n\n"
        f"🎯 *Chiến lược:* Buffett Value Sniper & Két Tiền Mặt 5%/năm\n"
        f"💵 *Vốn Khởi Điểm:* `{INITIAL_CAPITAL:,.0f} VNĐ`\n"
        f"🏦 *Lãi Suất Két Tiền Mặt:* `{VAULT_ANNUAL_RATE*100:.1f}%/năm (Linh hoạt T+0)`\n"
        f"📡 *Trạng thái:* Sẵn sàng săn cổ phiếu chiết khấu & tích lũy lãi kép\n"
        f"⏰ *Khởi chạy lúc:* {get_vn_time_str()}"
    )
    send_telegram(startup_msg)

    try:
        run_market_scan(force_notify=True)
    except Exception as e:
        print(f"Lỗi lần quét đầu: {e}")

    last_morning_brief = ""
    last_afternoon_brief = ""

    while True:
        try:
            now = get_vn_time()
            today_str = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute

            # Bản tin Sáng 08:45 AM
            if hour == 8 and minute >= 45 and last_morning_brief != today_str:
                last_morning_brief = today_str
                run_market_scan(force_notify=False)
                morning_msg = (
                    f"[🇻🇳 CHỨNG KHOÁN VN] ☀️ *BẢN TIN SÁNG TRƯỚC GIỜ GIAO DỊCH (08:45 AM)*\n"
                    f"📅 Ngày: {now.strftime('%d/%m/%Y')}\n\n"
                    f"🎯 *Hôm nay:* Két tiền mặt 5% sẵn sàng kích hoạt lệnh khi cổ phiếu chạm Vùng Chiết Khấu MoS 20%."
                )
                send_telegram(morning_msg)
                send_daily_summary_telegram()

            # Bản tin Chiều 15:15 PM
            if hour == 15 and minute >= 15 and last_afternoon_brief != today_str:
                last_afternoon_brief = today_str
                run_market_scan(force_notify=False)
                afternoon_msg = (
                    f"[🇻🇳 CHỨNG KHOÁN VN] 🌙 *BẢN TIN ĐÓNG CỬA PHIÊN GIAO DỊCH (15:15 PM)*\n"
                    f"📅 Ngày: {now.strftime('%d/%m/%Y')}\n\n"
                    f"📊 Kết thúc phiên ATC. Báo cáo biến động tài sản & tiền lãi Két hôm nay:"
                )
                send_telegram(afternoon_msg)
                send_daily_summary_telegram()

            run_market_scan(force_notify=False)

        except Exception as e:
            print(f"Lỗi trong vòng lặp nền: {e}")

        time.sleep(SCAN_INTERVAL_SECS)

# =============================================================================
# 5. WEB DASHBOARD HTTP SERVER
# =============================================================================

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if self.path == "/api/scan":
            threading.Thread(target=run_market_scan, args=(True,)).start()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "Scan triggered"}).encode("utf-8"))
            return

        summary = LEDGER.get_portfolio_summary()
        html = self._generate_dashboard_html(summary)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _generate_dashboard_html(self, s: dict) -> str:
        pnl_color = "#10b981" if s["total_profit"] >= 0 else "#ef4444"
        pnl_sign = "+" if s["total_profit"] >= 0 else ""

        holdings_rows = ""
        for h in s["holdings"]:
            h_pnl_color = "#10b981" if h["pnl"] >= 0 else "#ef4444"
            h_pnl_sign = "+" if h["pnl"] >= 0 else ""
            holdings_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8;">{h['ticker']}</td>
                <td>{h['shares']:,}</td>
                <td>{h['avg_price']:,.0f} đ</td>
                <td><strong style="color: #f8fafc;">{h['current_price']:,.0f} đ</strong></td>
                <td>{h['market_value']:,.0f} đ</td>
                <td>{h['dividends']:,.0f} đ</td>
                <td style="font-weight: bold; color: {h_pnl_color};">{h_pnl_sign}{h['pnl_pct']}% ({h_pnl_sign}{h['pnl']:,.0f} đ)</td>
                <td style="color: #94a3b8; font-size: 13px;">{h['notes']}</td>
            </tr>
            """

        watchlist_rows = ""
        for w in GLOBAL_WATCHLIST_DATA:
            badge_bg = "#065f46" if "VÙNG MUA" in w["status"] else ("#854d0e" if "CHỜ CHỈNH" in w["status"] else "#991b1b")
            badge_color = "#6ee7b7" if "VÙNG MUA" in w["status"] else ("#fde047" if "CHỜ CHỈNH" in w["status"] else "#fca5a5")
            watchlist_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8;">{w['ticker']}</td>
                <td>{w['name']}</td>
                <td><strong>{w['price']:,.0f} đ</strong></td>
                <td style="color: #fbbf24;">{w['fair_value']:,.0f} đ</td>
                <td style="color: #34d399; font-weight: bold;">{w['discount_price']:,.0f} đ</td>
                <td style="color: #a7f3d0;">{w['roe']}%</td>
                <td>{w['pe']}</td>
                <td>{w['volume_10d']:,.0f}</td>
                <td><span style="background: {badge_bg}; color: {badge_color}; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold;">{w['status']}</span></td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <title>Vietnam Stock Buffett Sniper & 5% Cash Vault</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; }}
                .container {{ max-width: 1380px; margin: 0 auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
                .title-box h1 {{ font-size: 26px; font-weight: 800; background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
                .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }}
                .kpi-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px; }}
                .kpi-card .label {{ font-size: 13px; color: #94a3b8; font-weight: 500; text-transform: uppercase; }}
                .kpi-card .val {{ font-size: 24px; font-weight: 700; margin-top: 8px; }}
                .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
                table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }}
                th {{ background: #0f172a; color: #94a3b8; padding: 12px 14px; font-weight: 600; border-bottom: 2px solid #334155; }}
                td {{ padding: 12px 14px; border-bottom: 1px solid #334155; }}
                tr:hover {{ background: #243248; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="title-box">
                        <h1>🎯 VIETNAM STOCK BUFFETT SNIPER & 5% CASH VAULT</h1>
                        <p>Hệ Thống Forward Test Định Lượng Cổ Phiếu Việt Nam • Cập nhật: <strong>{LAST_SCAN_TIME}</strong></p>
                    </div>
                </div>

                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="label">Tổng Tài Sản (NAV)</div>
                        <div class="val" style="color: #38bdf8;">{s['total_nav']:,.0f} đ</div>
                    </div>
                    <div class="kpi-card">
                        <div class="label">Lợi Nhuận Tích Lũy</div>
                        <div class="val" style="color: {pnl_color};">{pnl_sign}{s['total_profit']:,.0f} đ ({pnl_sign}{s['total_return_pct']}%)</div>
                    </div>
                    <div class="kpi-card">
                        <div class="label">Két Tiền Mặt 5%/Năm (T+0)</div>
                        <div class="val" style="color: #fbbf24;">{s['cash_vault']:,.0f} đ</div>
                    </div>
                    <div class="kpi-card">
                        <div class="label">Danh Mục Cổ Phiếu</div>
                        <div class="val" style="color: #a78bfa;">{s['stock_value']:,.0f} đ</div>
                    </div>
                </div>

                <div class="card">
                    <h2>📦 Danh Mục Cổ Phiếu Đang Nắm Giữ</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Mã CP</th><th>Số lượng</th><th>Giá vốn</th><th>Thị giá</th><th>Giá trị</th><th>Cổ tức</th><th>Lợi nhuận</th><th>Ghi chú</th>
                            </tr>
                        </thead>
                        <tbody>{holdings_rows}</tbody>
                    </table>
                </div>

                <div class="card">
                    <h2>🎯 Bảng Theo Dõi Định Giá & Vùng Mua Chiết Khấu (MoS 20%)</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Mã CP</th><th>Doanh Nghiệp</th><th>Thị giá</th><th>Giá trị Hợp lý</th><th>Vùng Mua MoS 20%</th><th>ROE</th><th>P/E</th><th>KL 10p</th><th>Trạng Thái</th>
                            </tr>
                        </thead>
                        <tbody>{watchlist_rows}</tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """

def start_server():
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"[VN STOCK SERVER] Web Dashboard đang chạy tại http://0.0.0.0:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    print("=================================================================")
    print(" KHỞI ĐỘNG HỆ THỐNG FORWARD TEST CỔ PHIẾU VIỆT NAM (BUFFETT SNIPER)")
    print("=================================================================")
    web_thread = threading.Thread(target=start_server, daemon=True)
    web_thread.start()
    background_scheduler()
