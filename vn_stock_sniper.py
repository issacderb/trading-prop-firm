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

# =============================================================================
# CẤU HÌNH — KHÔNG hard-code secret.
# =============================================================================
VN_TELEGRAM_BOT_TOKEN = os.getenv("VN_STOCK_TELEGRAM_BOT_TOKEN", "").strip()
VN_TELEGRAM_CHAT_ID = os.getenv("VN_STOCK_TELEGRAM_CHAT_ID", "").strip()

if not VN_TELEGRAM_BOT_TOKEN or not VN_TELEGRAM_CHAT_ID:
    print("[CẢNH BÁO] Chưa cấu hình VN_STOCK_TELEGRAM_BOT_TOKEN / VN_STOCK_TELEGRAM_CHAT_ID. "
          "Bot vẫn chạy nhưng chỉ log ra stdout.")

INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "1000000000.0"))  # 1 Tỷ VNĐ
VAULT_ANNUAL_RATE = float(os.getenv("VAULT_ANNUAL_RATE", "0.05"))     # 5.0%/năm
PORT = int(os.getenv("VN_STOCK_PORT", os.getenv("PORT", "10001")))
SCAN_INTERVAL_SECS = int(os.getenv("SCAN_INTERVAL_SECS", "300"))

# --- CHI PHÍ GIAO DỊCH THỰC TẾ TTCK VN (trước đây bằng 0) ---
BROKER_FEE_RATE = float(os.getenv("BROKER_FEE_RATE", "0.0015"))   # phí môi giới 0.15%/chiều
SELL_TAX_RATE = float(os.getenv("SELL_TAX_RATE", "0.001"))        # thuế TNCN 0.1% khi bán
SETTLEMENT_DAYS = int(os.getenv("SETTLEMENT_DAYS", "3"))          # T+2.5 -> chặn bán 3 ngày làm việc

# --- LUẬT QUẢN TRỊ DANH MỤC ---
MIN_CASH_FLOOR_PCT = float(os.getenv("MIN_CASH_FLOOR_PCT", "0.20"))  # luôn giữ >=20% NAV tiền mặt
MAX_POSITION_WEIGHT = float(os.getenv("MAX_POSITION_WEIGHT", "0.15"))  # <=15% NAV/mã
MAX_BUYS_PER_DAY = int(os.getenv("MAX_BUYS_PER_DAY", "1"))          # chống giải ngân ồ ạt 1 lần
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "8"))
ALLOC_PCT_OF_CASH = float(os.getenv("ALLOC_PCT_OF_CASH", "0.15"))
MAX_ALLOC_VND = float(os.getenv("MAX_ALLOC_VND", "100000000.0"))

# --- BỘ LỌC CHẤT LƯỢNG (README hứa nhưng code cũ không hề có) ---
MIN_ROE = float(os.getenv("MIN_ROE", "15.0"))                      # ROE >= 15%
MAX_PE = float(os.getenv("MAX_PE", "25.0"))
MAX_PB = float(os.getenv("MAX_PB", "4.0"))
MIN_LIQUIDITY_SHARES = float(os.getenv("MIN_LIQUIDITY_SHARES", "100000"))  # KLTB 10 phiên
MOS_RATE = float(os.getenv("MOS_RATE", "0.20"))                    # biên an toàn 20%
SELL_PREMIUM = float(os.getenv("SELL_PREMIUM", "1.0"))             # bán khi giá >= fair_value * hệ số

# --- DỮ LIỆU ---
MAX_PRICE_STALE_MINUTES = int(os.getenv("MAX_PRICE_STALE_MINUTES", "60"))

DATA_DIR = os.getenv("DATA_DIR", ".")
if DATA_DIR and not os.path.isdir(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
LEDGER_FILE = os.path.join(DATA_DIR, "vn_portfolio_ledger.json")

# Danh sách theo dõi.
# ⚠️ LƯU Ý BIAS: đây là các mã được CHỌN BẰNG HINDSIGHT (những cái tên đã thắng của
# TTCK VN). Mọi kết quả đo trên universe này đều nhiễm survivorship/selection bias.
# Muốn đánh giá đúng phải chọn universe bằng luật cơ học tại thời điểm quá khứ
# (ví dụ: top 100 vốn hoá tại T-0), không phải danh sách đẹp của hôm nay.
WATCHLIST_TICKERS = [
    "FPT", "VNM", "HPG", "DGC", "PNJ",
    "MWG", "ACB", "CTR", "VCB", "REE",
    "MBB", "TCB", "VHC", "BMP", "GMD",
    "FRT", "SAB", "DHG", "VSC", "MSN"
]


def is_trading_session(now=None) -> bool:
    """HOSE/HNX: T2-T6, sáng 09:00-11:30, chiều 13:00-14:45 (gồm ATC).

    Code cũ quét và 'khớp lệnh' 24/7 kể cả đêm và cuối tuần.
    Lưu ý: hàm này chưa có lịch nghỉ lễ VN — cần bổ sung nếu chạy thật.
    """
    now = now or get_vn_time()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 14 * 60 + 45)


def business_days_between(d1: str, d2: str) -> int:
    """Số ngày làm việc giữa 2 chuỗi YYYY-MM-DD (dùng cho T+)."""
    try:
        a = datetime.strptime(d1, "%Y-%m-%d").date()
        b = datetime.strptime(d2, "%Y-%m-%d").date()
    except Exception:
        return 999
    if b <= a:
        return 0
    days = 0
    cur = a
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


# =============================================================================
# 1. DATA CONNECTOR
# =============================================================================

def fetch_stock_data(ticker: str) -> dict:
    """Lấy giá + chỉ số cơ bản từ Simplize API.

    Thay đổi quan trọng so với bản cũ: KHÔNG còn nhánh fallback neo fair_value vào
    chính giá thị trường. Nhánh đó khiến 'giá trị nội tại' được suy ra từ giá thị
    trường => biên an toàn 20% mất hoàn toàn ý nghĩa (circular reasoning).
    Nay nếu không định giá được thì đánh dấu valuation_valid=False và BỎ QUA mã đó.
    """
    empty = {
        "ticker": ticker.upper(), "name": ticker, "industry": "N/A",
        "price": 0.0, "roe": 0.0, "pe": 0.0, "pb": 0.0, "eps": 0.0, "volume_10d": 0.0,
        "fair_value": 0.0, "discount_price": 0.0, "distance_pct": 0.0,
        "status": "KHÔNG ĐỦ DỮ LIỆU ⚪", "valuation_valid": False,
        "reject_reason": "Không lấy được dữ liệu", "updated_at": get_vn_time_str()
    }

    url = f"https://api.simplize.vn/api/company/summary/{ticker.lower()}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return empty
            d = json.loads(resp.read().decode("utf-8")).get("data", {}) or {}
    except Exception as e:
        print(f"Lỗi lấy dữ liệu {ticker}: {e}")
        return empty

    price = float(d.get("priceClose") or d.get("priceReferrance") or 0.0)
    roe = float(d.get("roe") or 0.0)
    pe = float(d.get("peRatio") or 0.0)
    pb = float(d.get("pbRatio") or 0.0)
    eps = float(d.get("epsRatio") or 0.0)
    volume_10d = float(d.get("volume10dAvg") or 0.0)

    out = dict(empty)
    out.update({
        "name": d.get("nameVi") or ticker,
        "industry": d.get("industryActivity") or "Doanh nghiệp",
        "price": price, "roe": roe, "pe": pe, "pb": pb,
        "eps": eps, "volume_10d": volume_10d,
        "updated_at": get_vn_time_str()
    })

    if price <= 0:
        out["reject_reason"] = "Không có giá"
        return out

    # --- Định giá: chỉ dùng khi EPS dương và hợp lý ---
    # Cảnh báo phương pháp: target_pe = f(ROE) là heuristic, KHÔNG phải mô hình
    # chiết khấu dòng tiền. Các hệ số 0.55 / [10,22] là magic number chưa qua
    # validation. Đây vẫn là điểm yếu lớn nhất còn lại của hệ thống.
    if eps <= 0 or roe <= 0:
        out["reject_reason"] = "EPS hoặc ROE không dương — không định giá được"
        out["status"] = "KHÔNG ĐỊNH GIÁ ⚪"
        return out

    target_pe = min(max(roe * 0.55, 10.0), 22.0)
    fair_value = eps * target_pe

    # Nếu mô hình cho kết quả lệch quá xa thị trường thì mô hình sai, không phải
    # thị trường sai => bỏ mã, KHÔNG bịa lại số theo giá.
    if fair_value > price * 3.0 or fair_value < price * 0.33:
        out["fair_value"] = round(fair_value, 0)
        out["reject_reason"] = (
            f"Định giá lệch phi lý so với thị trường "
            f"({fair_value:,.0f} vs {price:,.0f}) — mô hình không đáng tin cho mã này"
        )
        out["status"] = "ĐỊNH GIÁ KHÔNG TIN CẬY ⚪"
        return out

    discount_price = fair_value * (1.0 - MOS_RATE)
    distance_pct = ((price - discount_price) / discount_price * 100.0) if discount_price > 0 else 0.0

    out["valuation_valid"] = True
    out["fair_value"] = round(fair_value, 0)
    out["discount_price"] = round(discount_price, 0)
    out["distance_pct"] = round(distance_pct, 1)

    # --- Bộ lọc chất lượng (README hứa: ROE cao, thanh khoản) ---
    reasons = []
    if roe < MIN_ROE:
        reasons.append(f"ROE {roe:.1f}% < {MIN_ROE}%")
    if pe > MAX_PE or pe <= 0:
        reasons.append(f"P/E {pe:.1f} ngoài ngưỡng")
    if pb > MAX_PB:
        reasons.append(f"P/B {pb:.1f} > {MAX_PB}")
    if volume_10d < MIN_LIQUIDITY_SHARES:
        reasons.append(f"Thanh khoản {volume_10d:,.0f} < {MIN_LIQUIDITY_SHARES:,.0f}")

    out["reject_reason"] = " | ".join(reasons)
    passes_quality = len(reasons) == 0

    if price <= discount_price and passes_quality:
        out["status"] = "VÙNG MUA 🟢"
    elif price <= discount_price and not passes_quality:
        out["status"] = "RẺ NHƯNG TRƯỢT LỌC ⚪"
    elif price <= fair_value:
        out["status"] = "CHỜ CHỈNH 🟡"
    else:
        out["status"] = "ĐẮT 🔴"

    return out

# =============================================================================
# 2. TELEGRAM DISPATCHER
# =============================================================================

def send_telegram(message: str) -> bool:
    if not VN_TELEGRAM_BOT_TOKEN or not VN_TELEGRAM_CHAT_ID:
        print(f"[LOG ONLY]\n{message}\n")
        return False

    url = f"https://api.telegram.org/bot{VN_TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": VN_TELEGRAM_CHAT_ID,
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
        print(f"[VN STOCK TELEGRAM ERROR] {e}")
        return False

# =============================================================================
# 3. PORTFOLIO & CASH VAULT LEDGER
# =============================================================================

class PortfolioLedger:
    def __init__(self, filepath=LEDGER_FILE):
        self.filepath = filepath
        self.lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                base = self._fresh_state()
                base.update(data)
                return base
            except Exception as e:
                # Trước đây `except: pass` nuốt lỗi rồi âm thầm reset về state bịa.
                print(f"❌ [LEDGER] File {self.filepath} hỏng ({e}). Giữ lại bản lỗi, tạo sổ mới.")
                try:
                    os.rename(self.filepath, self.filepath + ".corrupt")
                except Exception:
                    pass

        state = self._fresh_state()
        self._save(state)
        return state

    @staticmethod
    def _fresh_state() -> dict:
        """Forward test SẠCH: bắt đầu 100% tiền mặt.

        Bản cũ khởi tạo sẵn 4 vị thế với current_price > avg_price và cổ tức viết tay
        (5tr/6tr/3.5tr) => tạo lãi giả ngay giây đầu tiên. Đồng thời cash chỉ =40% vốn
        trong khi giá vốn holdings =558.75tr => tổng 958.75tr, thủng 41.25tr so với 1 tỷ.
        """
        return {
            "initial_capital": INITIAL_CAPITAL,
            "cash_vault": INITIAL_CAPITAL,     # 100% tiền mặt, không thủng đồng nào
            "vault_annual_rate": VAULT_ANNUAL_RATE,
            "vault_interest_earned": 0.0,
            "last_interest_calc_time": get_vn_time().strftime("%Y-%m-%d"),
            "holdings": [],
            "trade_history": [],
            "realized_pnl": 0.0,
            "total_fees_paid": 0.0,
            "total_tax_paid": 0.0,
            "dividends_received": 0.0,
            "nav_history": [],
            "peak_nav": INITIAL_CAPITAL,
            "max_drawdown_pct": 0.0,
            "created_at": get_vn_time_str()
        }

    def _save(self, data=None):
        if data is None:
            data = self.data
        try:
            tmp = self.filepath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.filepath)
        except Exception as e:
            print(f"Lỗi lưu ledger: {e}")

    # ------------------------------------------------------------------
    def accrue_daily_vault_interest(self):
        """Lãi két theo SỐ NGÀY thực tế đã trôi qua.

        Bản cũ chỉ cộng đúng 1 ngày mỗi lần phát hiện đổi ngày => container ngủ 5 ngày
        thì mất 4 ngày lãi.
        """
        with self.lock:
            today = get_vn_time().date()
            last_str = self.data.get("last_interest_calc_time")
            try:
                last = datetime.strptime(last_str, "%Y-%m-%d").date()
            except Exception:
                last = today

            days = (today - last).days
            if days <= 0:
                return 0.0

            rate = self.data.get("vault_annual_rate", VAULT_ANNUAL_RATE)
            total = 0.0
            cash = self.data.get("cash_vault", 0.0)
            for _ in range(days):                    # cộng dồn lãi kép từng ngày
                interest = (cash * rate) / 365.0
                cash += interest
                total += interest

            self.data["cash_vault"] = cash
            self.data["vault_interest_earned"] = self.data.get("vault_interest_earned", 0.0) + total
            self.data["last_interest_calc_time"] = today.strftime("%Y-%m-%d")
            self._save()
            print(f"[KÉT TIỀN MẶT] Cộng lãi {days} ngày: +{total:,.0f} VNĐ")
            return total

    def update_prices(self, price_map: dict):
        with self.lock:
            now = get_vn_time_str()
            for item in self.data.get("holdings", []):
                t = item["ticker"]
                if t in price_map and price_map[t] > 0:
                    item["current_price"] = price_map[t]
                    item["price_updated_at"] = now
            self._save()

    def record_nav_point(self):
        """Lưu chuỗi NAV theo ngày để về sau tính được drawdown / Sharpe / so benchmark."""
        with self.lock:
            s = self.get_portfolio_summary()
            today = get_vn_time().strftime("%Y-%m-%d")
            hist = self.data.setdefault("nav_history", [])
            point = {"date": today, "nav": round(s["total_nav"], 0)}
            if hist and hist[-1]["date"] == today:
                hist[-1] = point
            else:
                hist.append(point)

            nav = s["total_nav"]
            if nav > self.data.get("peak_nav", nav):
                self.data["peak_nav"] = nav
            peak = self.data.get("peak_nav", nav)
            dd = (peak - nav) / peak * 100 if peak > 0 else 0.0
            if dd > self.data.get("max_drawdown_pct", 0.0):
                self.data["max_drawdown_pct"] = round(dd, 2)
            self._save()

    def get_portfolio_summary(self) -> dict:
        with self.lock:
            cash = self.data.get("cash_vault", 0.0)
            initial = self.data.get("initial_capital", INITIAL_CAPITAL)

            stock_value = 0.0
            total_cost = 0.0
            holdings_detail = []
            stale_count = 0
            now = get_vn_time()

            for h in self.data.get("holdings", []):
                shares = h.get("shares", 0)
                avg_p = h.get("avg_price", 0.0)      # giá vốn ĐÃ gồm phí mua
                curr_p = h.get("current_price", avg_p)

                cost = shares * avg_p
                mkt_val = shares * curr_p
                # PnL chưa thực hiện KHÔNG cộng cổ tức nữa — cổ tức khi nhận sẽ vào
                # thẳng cash_vault. Bản cũ cộng divs vào pnl từng mã nhưng không cộng
                # vào NAV => sum(holding.pnl) mâu thuẫn với total_profit.
                pnl = mkt_val - cost
                pnl_pct = (pnl / cost * 100.0) if cost > 0 else 0.0

                stock_value += mkt_val
                total_cost += cost

                is_stale = False
                upd = h.get("price_updated_at")
                if upd:
                    try:
                        dt = datetime.strptime(upd, "%H:%M:%S %d/%m/%Y").replace(
                            tzinfo=VN_TZ, year=now.year)
                        is_stale = (now - dt).total_seconds() > MAX_PRICE_STALE_MINUTES * 60
                    except Exception:
                        is_stale = False
                if is_stale:
                    stale_count += 1

                sellable_in = max(0, SETTLEMENT_DAYS - business_days_between(
                    h.get("last_buy_date", "1970-01-01"), now.strftime("%Y-%m-%d")))

                holdings_detail.append({
                    "ticker": h["ticker"],
                    "shares": shares,
                    "avg_price": avg_p,
                    "current_price": curr_p,
                    "cost": cost,
                    "market_value": mkt_val,
                    "pnl": pnl,
                    "pnl_pct": round(pnl_pct, 2),
                    "stale": is_stale,
                    "sellable_in_days": sellable_in,
                    "notes": h.get("notes", "")
                })

            total_nav = stock_value + cash
            total_profit = total_nav - initial
            total_return_pct = (total_profit / initial * 100.0) if initial > 0 else 0.0

            return {
                "total_nav": total_nav,
                "initial_capital": initial,
                "total_profit": total_profit,
                "total_return_pct": round(total_return_pct, 2),
                "stock_value": stock_value,
                "total_cost": total_cost,
                "cash_vault": cash,
                "vault_interest_earned": self.data.get("vault_interest_earned", 0.0),
                "realized_pnl": self.data.get("realized_pnl", 0.0),
                "total_fees_paid": self.data.get("total_fees_paid", 0.0),
                "total_tax_paid": self.data.get("total_tax_paid", 0.0),
                "total_dividends": self.data.get("dividends_received", 0.0),
                "max_drawdown_pct": self.data.get("max_drawdown_pct", 0.0),
                "equity_pct": round(stock_value / total_nav * 100.0, 1) if total_nav > 0 else 0.0,
                "cash_pct": round(cash / total_nav * 100.0, 1) if total_nav > 0 else 0.0,
                "stale_prices": stale_count,
                "holdings": holdings_detail,
                "trade_history": self.data.get("trade_history", [])
            }

    # ------------------------------------------------------------------
    def buys_today(self) -> int:
        today = get_vn_time().strftime("%Y-%m-%d")
        return sum(1 for t in self.data.get("trade_history", [])
                   if t.get("action") == "BUY" and t.get("date") == today)

    def bought_today(self, ticker: str) -> bool:
        today = get_vn_time().strftime("%Y-%m-%d")
        return any(t.get("action") == "BUY" and t.get("ticker") == ticker and t.get("date") == today
                   for t in self.data.get("trade_history", []))

    def execute_buy(self, ticker: str, price: float, reason: str) -> bool:
        """Mua với đầy đủ ràng buộc: giờ phiên, phí, lô 100, sàn tiền mặt, trần tỷ trọng.

        Toàn bộ kiểm tra nằm TRONG lock và dùng summary tính lại tại chỗ — sửa race
        condition khiến bản cũ bắn 4 lệnh trong 13 giây, tiêu 389/400tr của két.
        """
        with self.lock:
            if not is_trading_session():
                print(f"[BỎ QUA] {ticker}: ngoài giờ giao dịch — không thể khớp lệnh.")
                return False
            if price <= 0:
                return False

            if self.buys_today() >= MAX_BUYS_PER_DAY:
                print(f"[BỎ QUA] {ticker}: đã đạt giới hạn {MAX_BUYS_PER_DAY} lệnh mua/ngày.")
                return False
            if self.bought_today(ticker):
                return False

            s = self.get_portfolio_summary()
            nav = s["total_nav"]
            cash = s["cash_vault"]

            if len(s["holdings"]) >= MAX_POSITIONS and not any(h["ticker"] == ticker for h in s["holdings"]):
                return False

            cash_floor = nav * MIN_CASH_FLOOR_PCT
            investable = cash - cash_floor
            if investable <= 0:
                print(f"[BỎ QUA] {ticker}: chạm sàn tiền mặt {MIN_CASH_FLOOR_PCT*100:.0f}% NAV.")
                return False

            curr = next((h for h in s["holdings"] if h["ticker"] == ticker), None)
            curr_val = curr["market_value"] if curr else 0.0
            room_by_weight = nav * MAX_POSITION_WEIGHT - curr_val
            if room_by_weight <= 0:
                return False

            budget = min(investable, room_by_weight, cash * ALLOC_PCT_OF_CASH, MAX_ALLOC_VND)

            # Lô chẵn 100 cp (HOSE), tính CẢ phí mua vào ngân sách.
            shares = int(budget / (price * (1 + BROKER_FEE_RATE)) // 100) * 100
            while shares > 0 and shares * price * (1 + BROKER_FEE_RATE) > min(budget, investable):
                shares -= 100                      # bản cũ chỉ trừ 1 lần -> có thể âm tiền
            if shares <= 0:
                return False

            gross = shares * price
            fee = gross * BROKER_FEE_RATE
            total_cost = gross + fee
            if total_cost > cash:
                return False

            self.data["cash_vault"] -= total_cost
            self.data["total_fees_paid"] = self.data.get("total_fees_paid", 0.0) + fee
            today = get_vn_time().strftime("%Y-%m-%d")

            found = False
            for h in self.data.get("holdings", []):
                if h["ticker"] == ticker:
                    old_cost = h["shares"] * h["avg_price"]
                    new_shares = h["shares"] + shares
                    h["avg_price"] = (old_cost + total_cost) / new_shares  # giá vốn gồm phí
                    h["shares"] = new_shares
                    h["current_price"] = price
                    h["last_buy_date"] = today
                    h["price_updated_at"] = get_vn_time_str()
                    found = True
                    break

            if not found:
                self.data["holdings"].append({
                    "ticker": ticker,
                    "shares": shares,
                    "avg_price": total_cost / shares,
                    "current_price": price,
                    "last_buy_date": today,
                    "price_updated_at": get_vn_time_str(),
                    "notes": reason
                })

            self.data["trade_history"].insert(0, {
                "timestamp": get_vn_time_str(),
                "date": today,
                "ticker": ticker,
                "action": "BUY",
                "shares": shares,
                "price": price,
                "gross": gross,
                "fee": fee,
                "amount": total_cost,
                "reason": reason
            })
            self._save()
            return {"shares": shares, "price": price, "fee": fee, "total": total_cost}

    def execute_sell(self, ticker: str, price: float, reason: str) -> bool:
        """Bán chốt lời khi giá vượt giá trị hợp lý. Bản cũ KHÔNG có luật bán nào —
        danh mục chỉ mua, không bao giờ có lợi nhuận thực hiện."""
        with self.lock:
            if not is_trading_session() or price <= 0:
                return False

            h = next((x for x in self.data.get("holdings", []) if x["ticker"] == ticker), None)
            if not h or h["shares"] <= 0:
                return False

            today = get_vn_time().strftime("%Y-%m-%d")
            # T+2.5: cổ phiếu mua chưa về tài khoản thì không bán được.
            if business_days_between(h.get("last_buy_date", "1970-01-01"), today) < SETTLEMENT_DAYS:
                print(f"[BỎ QUA BÁN] {ticker}: chưa đủ T+{SETTLEMENT_DAYS}.")
                return False

            shares = h["shares"]
            gross = shares * price
            fee = gross * BROKER_FEE_RATE
            tax = gross * SELL_TAX_RATE
            net = gross - fee - tax
            cost = shares * h["avg_price"]
            realized = net - cost

            self.data["cash_vault"] += net
            self.data["realized_pnl"] = self.data.get("realized_pnl", 0.0) + realized
            self.data["total_fees_paid"] = self.data.get("total_fees_paid", 0.0) + fee
            self.data["total_tax_paid"] = self.data.get("total_tax_paid", 0.0) + tax
            self.data["holdings"] = [x for x in self.data["holdings"] if x["ticker"] != ticker]

            self.data["trade_history"].insert(0, {
                "timestamp": get_vn_time_str(),
                "date": today,
                "ticker": ticker,
                "action": "SELL",
                "shares": shares,
                "price": price,
                "gross": gross,
                "fee": fee,
                "tax": tax,
                "amount": net,
                "realized_pnl": realized,
                "reason": reason
            })
            self._save()
            return {"shares": shares, "price": price, "net": net, "realized": realized}


LEDGER = PortfolioLedger()
GLOBAL_WATCHLIST_DATA = []
LAST_SCAN_TIME = "Chưa quét"

# =============================================================================
# 4. ENGINE QUÉT THỊ TRƯỜNG
# =============================================================================

def run_market_scan(force_notify=False):
    global GLOBAL_WATCHLIST_DATA, LAST_SCAN_TIME

    print(f"[{get_vn_time_str()}] Đang quét thị trường chứng khoán Việt Nam...")
    results = []
    price_map = {}

    for ticker in WATCHLIST_TICKERS:
        d = fetch_stock_data(ticker)
        results.append(d)
        if d["price"] > 0:
            price_map[ticker] = d["price"]
        time.sleep(0.15)

    order = {"VÙNG MUA 🟢": 0, "CHỜ CHỈNH 🟡": 1, "ĐẮT 🔴": 2}
    results.sort(key=lambda x: (order.get(x["status"], 3), -x["roe"]))
    GLOBAL_WATCHLIST_DATA = results
    LAST_SCAN_TIME = get_vn_time_str()

    LEDGER.update_prices(price_map)
    LEDGER.accrue_daily_vault_interest()

    tradable = is_trading_session()
    if not tradable:
        print("  → Ngoài giờ giao dịch: chỉ cập nhật định giá, không đặt lệnh.")

    if tradable:
        # ---- LUẬT BÁN: chốt lời khi giá vượt giá trị hợp lý ----
        for h in list(LEDGER.get_portfolio_summary()["holdings"]):
            info = next((r for r in results if r["ticker"] == h["ticker"]), None)
            if not info or not info["valuation_valid"] or info["price"] <= 0:
                continue
            if info["price"] >= info["fair_value"] * SELL_PREMIUM:
                reason = (f"Giá {info['price']:,.0f} ≥ Giá trị hợp lý "
                          f"{info['fair_value']:,.0f} — chốt lời theo định giá")
                res = LEDGER.execute_sell(h["ticker"], info["price"], reason)
                if res:
                    send_telegram(
                        f"[🇻🇳 CHỨNG KHOÁN VN] 💰 *CHỐT LỜI THEO ĐỊNH GIÁ*\n\n"
                        f"🏢 *Mã:* `{h['ticker']}`\n"
                        f"📤 *Bán:* `{res['shares']:,} CP` @ `{res['price']:,.0f} đ`\n"
                        f"💵 *Thực nhận (sau phí + thuế):* `{res['net']:,.0f} đ`\n"
                        f"📊 *Lãi/lỗ đã thực hiện:* `{res['realized']:+,.0f} đ`\n"
                        f"💡 {reason}\n"
                        f"⏰ {get_vn_time_str()}"
                    )

        # ---- LUẬT MUA ----
        # Kiểm tra lại điều kiện TRONG từng vòng lặp (execute_buy tự tính lại summary)
        for opp in [r for r in results if r["status"] == "VÙNG MUA 🟢"]:
            res = LEDGER.execute_buy(opp["ticker"], opp["price"], (
                f"MoS {MOS_RATE*100:.0f}% (Giá {opp['price']:,.0f} ≤ Mục tiêu "
                f"{opp['discount_price']:,.0f}, ROE {opp['roe']:.1f}%)"
            ))
            if res:
                send_telegram(
                    f"[🇻🇳 CHỨNG KHOÁN VN] 🎯 *MUA GIÁ TRỊ (BUFFETT DISCOUNT)*\n\n"
                    f"🏢 *Cổ phiếu:* `{opp['ticker']}` - {opp['name']}\n"
                    f"📥 *Mua:* `{res['shares']:,} CP` @ `{res['price']:,.0f} đ`\n"
                    f"💸 *Phí môi giới {BROKER_FEE_RATE*100:.2f}%:* `{res['fee']:,.0f} đ`\n"
                    f"💵 *Tổng chi:* `{res['total']:,.0f} đ`\n"
                    f"💎 *Giá trị hợp lý:* `{opp['fair_value']:,.0f} đ`\n"
                    f"🎯 *Vùng MoS {MOS_RATE*100:.0f}%:* `{opp['discount_price']:,.0f} đ`\n"
                    f"📊 ROE `{opp['roe']:.1f}%` | P/E `{opp['pe']:.1f}` | P/B `{opp['pb']:.2f}`\n"
                    f"🔒 *Chưa bán được trong T+{SETTLEMENT_DAYS}*\n"
                    f"⏰ {get_vn_time_str()}"
                )

    LEDGER.record_nav_point()

    if force_notify:
        send_daily_summary_telegram()


def send_daily_summary_telegram():
    summary = LEDGER.get_portfolio_summary()

    holdings_text = ""
    for h in summary["holdings"]:
        pnl_emoji = "🟢" if h["pnl"] >= 0 else "🔴"
        flag = " ⚠️cũ" if h["stale"] else ""
        holdings_text += (
            f"• `{h['ticker']:4}` | {h['shares']:>5,d} CP | "
            f"Vốn: `{h['avg_price']:>6,.0f}` | TT: `{h['current_price']:>6,.0f}` | "
            f"{pnl_emoji} `{h['pnl_pct']:>+5.1f}%`{flag}\n"
        )
    if not holdings_text:
        holdings_text = "• _Chưa có vị thế nào — đang chờ cơ hội đạt biên an toàn._\n"

    watchlist_text = ""
    for w in GLOBAL_WATCHLIST_DATA[:5]:
        watchlist_text += (
            f"• `{w['ticker']:4}`: `{w['price']:,.0f}` | "
            f"MoS: `{w['discount_price']:,.0f}` | ROE `{w['roe']:.1f}%` | {w['status']}\n"
        )

    n_trades = len([t for t in summary["trade_history"] if t.get("action") == "SELL"])
    pnl_sign = "+" if summary["total_profit"] >= 0 else ""
    msg = (
        f"[🇻🇳 CHỨNG KHOÁN VN] 📊 *BẢN TIN PORTFOLIO & KÉT TIỀN MẶT*\n"
        f"📅 {get_vn_time_str()}\n\n"
        f"💰 *NAV:* `{summary['total_nav']:,.0f} đ`\n"
        f"📈 *Lãi/lỗ tổng:* `{pnl_sign}{summary['total_profit']:,.0f} đ` (`{pnl_sign}{summary['total_return_pct']}%`)\n"
        f"✅ *Đã thực hiện:* `{summary['realized_pnl']:+,.0f} đ` ({n_trades} lệnh bán)\n"
        f"🏛 *Cổ phiếu:* `{summary['stock_value']:,.0f} đ` (`{summary['equity_pct']}%`)\n"
        f"🏦 *Két tiền mặt:* `{summary['cash_vault']:,.0f} đ` (`{summary['cash_pct']}%`)\n"
        f"✨ *Lãi két tích luỹ:* `+{summary['vault_interest_earned']:,.0f} đ`\n"
        f"💸 *Phí + thuế đã trả:* `-{summary['total_fees_paid'] + summary['total_tax_paid']:,.0f} đ`\n"
        f"📉 *Max Drawdown:* `{summary['max_drawdown_pct']}%`\n\n"
        f"📋 *DANH MỤC:*\n{holdings_text}\n"
        f"🎯 *TOP THEO DÕI:*\n{watchlist_text}\n"
        f"_⚠️ Chưa có backtest/OOS validation. Chưa so với VN-Index nên chưa kết luận được alpha._"
    )
    send_telegram(msg)


def background_scheduler():
    time.sleep(2)

    startup_msg = (
        f"[🇻🇳 CHỨNG KHOÁN VN] 🚀 *HỆ THỐNG FORWARD TEST KHỞI ĐỘNG*\n\n"
        f"🎯 *Chiến lược:* Value Sniper + Két tiền mặt {VAULT_ANNUAL_RATE*100:.1f}%/năm\n"
        f"💵 *Vốn khởi điểm:* `{INITIAL_CAPITAL:,.0f} đ` (100% tiền mặt)\n"
        f"🔍 *Bộ lọc:* ROE ≥ {MIN_ROE}% | P/E ≤ {MAX_PE} | P/B ≤ {MAX_PB} | "
        f"KL ≥ {MIN_LIQUIDITY_SHARES:,.0f}\n"
        f"💸 *Chi phí:* phí {BROKER_FEE_RATE*100:.2f}%/chiều + thuế bán {SELL_TAX_RATE*100:.1f}%\n"
        f"🛡 *Kỷ luật:* ≤{MAX_BUYS_PER_DAY} lệnh/ngày | ≤{MAX_POSITION_WEIGHT*100:.0f}%/mã | "
        f"sàn tiền mặt {MIN_CASH_FLOOR_PCT*100:.0f}% NAV\n"
        f"⏰ {get_vn_time_str()}"
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
            hour, minute = now.hour, now.minute
            is_weekday = now.weekday() < 5

            if is_weekday and hour == 8 and minute >= 45 and last_morning_brief != today_str:
                last_morning_brief = today_str
                run_market_scan(force_notify=False)
                send_telegram(
                    f"[🇻🇳 CHỨNG KHOÁN VN] ☀️ *BẢN TIN TRƯỚC PHIÊN (08:45)*\n"
                    f"📅 {now.strftime('%d/%m/%Y')}\n\n"
                    f"🎯 Két sẵn sàng giải ngân khi có mã đạt MoS {MOS_RATE*100:.0f}% và qua bộ lọc chất lượng."
                )
                send_daily_summary_telegram()

            if is_weekday and hour == 15 and minute >= 15 and last_afternoon_brief != today_str:
                last_afternoon_brief = today_str
                run_market_scan(force_notify=False)
                send_telegram(
                    f"[🇻🇳 CHỨNG KHOÁN VN] 🌙 *ĐÓNG CỬA PHIÊN (15:15)*\n📅 {now.strftime('%d/%m/%Y')}"
                )
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
        n_sells = len([t for t in s["trade_history"] if t.get("action") == "SELL"])
        session_txt = ("🟢 ĐANG TRONG PHIÊN" if is_trading_session()
                       else "⚪ NGOÀI GIỜ — chỉ cập nhật định giá, không đặt lệnh")
        stale_txt = (f" • ⚠️ {s['stale_prices']} mã có giá cũ hơn {MAX_PRICE_STALE_MINUTES} phút"
                     if s["stale_prices"] else "")
        method_banner = f"""
        <div style="background:#422006; border:1px solid #a16207; border-radius:12px; padding:16px 18px; margin-bottom:24px;">
            <div style="color:#fbbf24; font-weight:800; font-size:15px;">⚠️ GIỚI HẠN PHƯƠNG PHÁP — ĐỌC TRƯỚC KHI TIN SỐ LIỆU</div>
            <ul style="color:#fde68a; font-size:13px; margin:8px 0 0 18px; line-height:1.7;">
                <li>Chưa có <b>backtest / out-of-sample validation</b>. Đây là forward test thuần, {n_sells} lệnh đã chốt — chưa đủ cỡ mẫu kết luận.</li>
                <li>Mô hình định giá <code>target_PE = ROE × 0.55</code> clamp [10, 22] là <b>heuristic chưa được kiểm định</b>, không phải DCF.</li>
                <li>Watchlist 20 mã được chọn bằng <b>hindsight</b> → nhiễm survivorship/selection bias.</li>
                <li>Chưa so sánh với <b>VN-Index</b> nên chưa kết luận được có alpha hay không.</li>
                <li>EPS trailing chưa normalize chu kỳ → rủi ro bẫy định giá với mã chu kỳ (thép, hoá chất).</li>
            </ul>
        </div>
        """

        holdings_rows = ""
        for h in s["holdings"]:
            h_pnl_color = "#10b981" if h["pnl"] >= 0 else "#ef4444"
            h_pnl_sign = "+" if h["pnl"] >= 0 else ""
            stale_badge = ' <span style="color:#fbbf24;" title="Giá chưa cập nhật gần đây">⚠️</span>' if h['stale'] else ''
            t_badge = (f'<span style="color:#fbbf24; font-size:12px;">🔒 T+{h["sellable_in_days"]}</span>'
                       if h['sellable_in_days'] > 0 else '<span style="color:#34d399; font-size:12px;">✓ bán được</span>')
            holdings_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8;">{h['ticker']}</td>
                <td>{h['shares']:,}</td>
                <td>{h['avg_price']:,.0f} đ</td>
                <td><strong style="color: #f8fafc;">{h['current_price']:,.0f} đ</strong>{stale_badge}</td>
                <td>{h['market_value']:,.0f} đ</td>
                <td>{t_badge}</td>
                <td style="font-weight: bold; color: {h_pnl_color};">{h_pnl_sign}{h['pnl_pct']}% ({h_pnl_sign}{h['pnl']:,.0f} đ)</td>
                <td style="color: #94a3b8; font-size: 13px;">{h['notes']}</td>
            </tr>
            """
        if not holdings_rows:
            holdings_rows = ('<tr><td colspan="8" style="text-align:center; padding:28px; color:#64748b;">'
                             'Chưa có vị thế nào. Danh mục bắt đầu 100% tiền mặt và chỉ giải ngân khi '
                             'có mã đạt biên an toàn + qua bộ lọc chất lượng.</td></tr>')

        watchlist_rows = ""
        for w in GLOBAL_WATCHLIST_DATA:
            if "VÙNG MUA" in w["status"]:
                badge_bg, badge_color = "#065f46", "#6ee7b7"
            elif "CHỜ CHỈNH" in w["status"]:
                badge_bg, badge_color = "#854d0e", "#fde047"
            elif "ĐẮT" in w["status"]:
                badge_bg, badge_color = "#991b1b", "#fca5a5"
            else:
                badge_bg, badge_color = "#334155", "#94a3b8"
            fv = f"{w['fair_value']:,.0f} đ" if w['fair_value'] > 0 else "—"
            dp = f"{w['discount_price']:,.0f} đ" if w['discount_price'] > 0 else "—"
            watchlist_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8;">{w['ticker']}</td>
                <td>{w['name']}</td>
                <td><strong>{w['price']:,.0f} đ</strong></td>
                <td style="color: #fbbf24;">{fv}</td>
                <td style="color: #34d399; font-weight: bold;">{dp}</td>
                <td style="color: #a7f3d0;">{w['roe']:.1f}%</td>
                <td>{w['pe']:.1f}</td>
                <td>{w['volume_10d']:,.0f}</td>
                <td><span style="background: {badge_bg}; color: {badge_color}; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold;">{w['status']}</span></td>
                <td style="color: #94a3b8; font-size: 12px;">{w.get('reject_reason', '') or '—'}</td>
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
                        <p>Forward Test Định Lượng Cổ Phiếu VN • {session_txt} • Cập nhật: <strong>{LAST_SCAN_TIME}</strong>{stale_txt}</p>
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
                    <div class="kpi-card">
                        <div class="label">Lãi/Lỗ Đã Thực Hiện</div>
                        <div class="val" style="color: {'#10b981' if s['realized_pnl'] >= 0 else '#ef4444'};">{s['realized_pnl']:+,.0f} đ</div>
                        <div style="font-size:12px; color:#94a3b8; margin-top:4px;">{n_sells} lệnh bán đã chốt</div>
                    </div>
                    <div class="kpi-card">
                        <div class="label">Phí + Thuế Đã Trả</div>
                        <div class="val" style="color: #f87171;">-{s['total_fees_paid'] + s['total_tax_paid']:,.0f} đ</div>
                        <div style="font-size:12px; color:#94a3b8; margin-top:4px;">Phí {BROKER_FEE_RATE*100:.2f}%/chiều + thuế bán {SELL_TAX_RATE*100:.1f}%</div>
                    </div>
                    <div class="kpi-card">
                        <div class="label">Max Drawdown</div>
                        <div class="val" style="color: #fbbf24;">{s['max_drawdown_pct']}%</div>
                        <div style="font-size:12px; color:#94a3b8; margin-top:4px;">Trên chuỗi NAV {len(LEDGER.data.get('nav_history', []))} ngày</div>
                    </div>
                </div>

                {method_banner}

                <div class="card">
                    <h2>📦 Danh Mục Cổ Phiếu Đang Nắm Giữ</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Mã CP</th><th>Số lượng</th><th>Giá vốn (gồm phí)</th><th>Thị giá</th><th>Giá trị</th><th>Thanh toán</th><th>Lãi/lỗ chưa TH</th><th>Ghi chú</th>
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
                                <th>Mã CP</th><th>Doanh Nghiệp</th><th>Thị giá</th><th>Giá trị Hợp lý</th><th>Vùng Mua MoS</th><th>ROE</th><th>P/E</th><th>KL 10p</th><th>Trạng Thái</th><th>Ghi chú lọc</th>
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
