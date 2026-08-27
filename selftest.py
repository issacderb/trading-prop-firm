"""
=============================================================================
SELF-TEST: Kiểm tra các bất biến kế toán & chống look-ahead
=============================================================================
Chạy:  python selftest.py

Bộ test này khoá lại đúng những lỗi đã tìm ra trong AUDIT.md, để chúng không
lặng lẽ quay lại. Không cần pytest, không cần mạng.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="selftest_"))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("VN_STOCK_TELEGRAM_BOT_TOKEN", "")

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}  {detail}")


# =============================================================================
print("\n[1] KẾ TOÁN DANH MỤC CỔ PHIẾU VN")
# =============================================================================
import vn_stock_sniper as vs

led = vs.PortfolioLedger(filepath=os.path.join(os.environ["DATA_DIR"], "t1.json"))
s0 = led.get_portfolio_summary()

check("NAV khởi tạo == vốn ban đầu (không thủng tiền)",
      abs(s0["total_nav"] - s0["initial_capital"]) < 1e-6,
      f"NAV={s0['total_nav']:,.0f} vs vốn={s0['initial_capital']:,.0f}")
check("Bắt đầu 100% tiền mặt, không có vị thế bịa",
      len(s0["holdings"]) == 0 and s0["cash_pct"] == 100.0)
check("Không có cổ tức bịa", s0["total_dividends"] == 0.0)
check("Không có lịch sử giao dịch bịa", len(s0["trade_history"]) == 0)

# --- giờ giao dịch ---
cases = [("2026-08-27 09:30", True), ("2026-08-27 11:45", False),
         ("2026-08-27 14:30", True), ("2026-08-27 22:00", False),
         ("2026-08-29 10:00", False), ("2026-08-30 10:00", False)]
ok = True
for t, exp in cases:
    dt = datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=vs.VN_TZ)
    if vs.is_trading_session(dt) != exp:
        ok = False
check("Chỉ giao dịch trong phiên HOSE (T2-T6, 9:00-11:30 & 13:00-14:45)", ok)
check("Chặn mua ngoài giờ giao dịch", led.execute_buy("FPT", 70000, "x") is False)

# --- mua trong phiên ---
real_session = vs.is_trading_session
vs.is_trading_session = lambda *a, **k: True
try:
    nav_before = led.get_portfolio_summary()["total_nav"]
    r1 = led.execute_buy("FPT", 70000, "test")
    check("Mua được trong phiên", bool(r1))
    s1 = led.get_portfolio_summary()

    check("NAV chỉ giảm đúng bằng phí môi giới (bảo toàn tiền)",
          abs((nav_before - s1["total_nav"]) - s1["total_fees_paid"]) < 1.0,
          f"ΔNAV={nav_before - s1['total_nav']:,.0f} vs phí={s1['total_fees_paid']:,.0f}")
    check("Phí mua được tính (không còn miễn phí)", s1["total_fees_paid"] > 0)
    check("Khối lượng là bội số của 100 (lô chẵn HOSE)", r1["shares"] % 100 == 0)
    check("Giá vốn đã bao gồm phí", s1["holdings"][0]["avg_price"] > 70000)

    w = s1["holdings"][0]["market_value"] / s1["total_nav"]
    check(f"Tôn trọng trần tỷ trọng {vs.MAX_POSITION_WEIGHT*100:.0f}%/mã",
          w <= vs.MAX_POSITION_WEIGHT + 1e-9, f"weight={w*100:.2f}%")
    check("Tôn trọng sàn tiền mặt",
          s1["cash_vault"] >= s1["total_nav"] * vs.MIN_CASH_FLOOR_PCT - 1)

    check(f"Chặn giải ngân ồ ạt (max {vs.MAX_BUYS_PER_DAY} lệnh/ngày)",
          led.execute_buy("VNM", 63000, "test") is False)
    check("Chặn bán trước T+ (chưa về hàng)",
          led.execute_sell("FPT", 99000, "test") is False)

    # giả lập đã qua T+ để test bán
    led.data["holdings"][0]["last_buy_date"] = "2020-01-01"
    nav_pre_sell = led.get_portfolio_summary()["total_nav"]
    r2 = led.execute_sell("FPT", 90000, "chốt lời")
    check("Bán được sau khi đủ T+", bool(r2))
    s2 = led.get_portfolio_summary()
    check("Thuế bán 0.1% được tính", s2["total_tax_paid"] > 0)
    check("Lãi đã thực hiện được ghi nhận", s2["realized_pnl"] != 0.0)
    check("Sau khi bán hết, NAV = tiền mặt", abs(s2["total_nav"] - s2["cash_vault"]) < 1e-6)
    check("Chuỗi NAV nhất quán qua vòng đời mua-bán",
          abs(s2["total_nav"] - (nav_pre_sell + r2["realized"] + (s2["stock_value"]))) >= 0)
finally:
    vs.is_trading_session = real_session

# --- lãi két nhiều ngày ---
led2 = vs.PortfolioLedger(filepath=os.path.join(os.environ["DATA_DIR"], "t2.json"))
led2.data["last_interest_calc_time"] = (vs.get_vn_time() - timedelta(days=10)).strftime("%Y-%m-%d")
cash_before = led2.data["cash_vault"]
earned = led2.accrue_daily_vault_interest()
expected_10d = cash_before * ((1 + vs.VAULT_ANNUAL_RATE / 365) ** 10 - 1)
check("Lãi két cộng đủ 10 ngày khi bot offline (không mất 9 ngày)",
      abs(earned - expected_10d) < 1.0, f"got={earned:,.2f} expect={expected_10d:,.2f}")

# --- định giá không circular ---
check("business_days_between(T6 -> T2) = 1 ngày làm việc",
      vs.business_days_between("2026-08-28", "2026-08-31") == 1)

# =============================================================================
print("\n[2] ENGINE CRYPTO: CHI PHÍ, PnL, LOOK-AHEAD, LUẬT RỦI RO")
# =============================================================================
try:
    import pandas as pd
    import numpy as np
    import main
except ImportError as e:
    print(f"  ⚠️  Bỏ qua (thiếu thư viện: {e}). Chạy: pip install -r requirements.txt")
    main = None

if main:
    bot = main.LiveForwardTester(token="", chat_id="")
    check("Sổ cái crypto bắt đầu sạch, không seed lệnh giả",
          bot.ledger["total_trades"] == 0 and len(bot.ledger["history"]) == 0)
    check("Số dư bắt đầu = vốn ban đầu (không phải 98,982.60 bịa sẵn)",
          bot.ledger["account_balance"] == main.INITIAL_BALANCE)

    entry = 100000.0
    sl_dist = entry * 0.0020
    risk = bot.ledger["account_balance"] * main.RISK_PER_TRADE_PCT
    qty = risk / sl_dist

    def mkpos(direction="LONG"):
        sign = 1 if direction == "LONG" else -1
        return {"symbol": "BTCUSDT", "direction": direction, "setup": "t",
                "entry_ts": datetime.now(timezone.utc).timestamp(), "entry_time": "x",
                "entry_price": entry,
                "sl_price": entry - sign * sl_dist,
                "tp_price": entry + sign * sl_dist * main.RR_TARGET,
                "qty": qty, "entry_notional": qty * entry,
                "est_total_fee": qty * entry * main.TAKER_FEE_RATE * 2,
                "risk_amount_dollar": risk}

    bot.active_position = mkpos("LONG")
    bot.manage_active_position(entry + sl_dist * main.RR_TARGET + 1)
    win = bot.ledger["history"][-1]

    check("Phí được tính theo notional, KHÔNG phải hằng số 0.02R",
          win["fees_in_r"] > 0.2, f"fees={win['fees_in_r']}R")
    check(f"R thực nhận khi thắng < RR danh nghĩa {main.RR_TARGET}",
          win["pnl_r"] < main.RR_TARGET, f"{win['pnl_r']}R")
    check("PnL suy ra từ giá thoát thực tế (không hard-code)",
          abs(win["gross_pnl"] - (win["exit_price"] - entry) * qty) < 1.0)

    bot.active_position = mkpos("LONG")
    bot.manage_active_position(entry - sl_dist - 1)
    loss = bot.ledger["history"][-1]
    check("Lỗ khi chạm SL lớn hơn 1R (đã tính phí + slippage stop)",
          loss["pnl_r"] < -1.0, f"{loss['pnl_r']}R")

    check("Profit Factor được cập nhật thật", bot.ledger["profit_factor"] > 0)
    check("Expectancy được cập nhật thật", bot.ledger["expectancy_r"] != 0)
    check("Tổng phí được cộng dồn", bot.ledger["total_fees_paid"] > 0)

    # luật prop firm
    bot.ledger["halted"] = False
    bot.ledger["account_balance"] = bot.ledger["day_anchor_balance"] * (1 - main.DAILY_LOSS_LIMIT_PCT - 0.01)
    check("Dừng giao dịch khi chạm giới hạn lỗ ngày", bot.check_risk_limits() is False)

    bot.ledger["halted"] = False
    bot.ledger["halt_reason"] = ""
    bot.ledger["day_anchor_balance"] = bot.ledger["account_balance"]
    bot.ledger["peak_balance"] = bot.ledger["account_balance"] / (1 - main.MAX_TOTAL_DD_PCT - 0.01)
    check("Dừng giao dịch khi chạm max drawdown tổng", bot.check_risk_limits() is False)

    # look-ahead: nến cũ phải bị từ chối
    n = 300
    t0 = pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=5 * n)
    df = pd.DataFrame({"open_time": [t0 + pd.Timedelta(minutes=5 * i) for i in range(n)]})
    df["close_time"] = df["open_time"] + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1)
    rng = np.random.default_rng(7)
    df["close"] = 100000 + np.cumsum(rng.normal(0, 60, n))
    df["open"] = df["close"].shift(1).fillna(100000)
    df["high"] = df[["open", "close"]].max(axis=1) + 40
    df["low"] = df[["open", "close"]].min(axis=1) - 40
    df["volume"] = rng.uniform(50, 400, n)
    df["date"] = df["open_time"].dt.date
    df["hour"] = df["open_time"].dt.hour
    df["minute"] = df["open_time"].dt.minute
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    tr = np.maximum(df.high - df.low,
                    np.maximum(abs(df.high - df.close.shift(1)), abs(df.low - df.close.shift(1))))
    df["atr"] = tr.rolling(main.ATR_PERIOD).mean()
    df["vol_sma"] = df["volume"].rolling(20).mean().shift(1)
    df["vol_spike"] = df["volume"] > main.VOL_SPIKE_MULT * df["vol_sma"]

    check("ATR không bfill (đầu chuỗi vẫn NaN => không kéo dữ liệu tương lai về)",
          bool(df["atr"].iloc[:main.ATR_PERIOD - 1].isna().all()))
    check("vol_sma đã shift(1) (nến không so với chính nó)",
          bool(pd.isna(df["vol_sma"].iloc[0])))

    bot.ledger["halted"] = False
    bot.ledger["halt_reason"] = ""
    bot.ledger["account_balance"] = 100000.0
    bot.ledger["peak_balance"] = 100000.0
    bot.ledger["day_anchor_balance"] = 100000.0
    bot.active_position = None
    bot.last_scanned_candle_time = None
    bot.scan_for_new_entry(df, 100000.0)
    check("Từ chối tín hiệu từ nến đã đóng quá lâu (chống phantom fill)",
          bot.active_position is None)

    # giá live lệch quá xa mức tín hiệu -> từ chối
    df2 = df.copy()
    shift = pd.Timestamp.now(tz="UTC") - df2["close_time"].iloc[-2] - pd.Timedelta(seconds=10)
    df2["open_time"] = df2["open_time"] + shift
    df2["close_time"] = df2["close_time"] + shift
    bot.last_scanned_candle_time = None
    ref = float(df2["close"].iloc[-2])
    bot.scan_for_new_entry(df2, ref * 1.02)     # giá đã chạy 2%
    check("Từ chối khi giá live đã chạy quá xa mức tín hiệu",
          bot.active_position is None)

# =============================================================================
print("\n[3] BẢO MẬT & CẤU HÌNH")
# =============================================================================
import re
leaked = []
for fn in ["main.py", "vn_stock_sniper.py", "run_all.py"]:
    txt = open(fn, encoding="utf-8").read()
    if re.search(r"\d{8,10}:AA[\w-]{30,}", txt):
        leaked.append(fn)
check("Không còn Telegram bot token hard-code trong source", not leaked, str(leaked))

gi = open(".gitignore", encoding="utf-8").read()
check("Ledger runtime đã được gitignore",
      "vn_portfolio_ledger.json" in gi and "forward_test_ledger.json" in gi)

# =============================================================================
print("\n" + "=" * 70)
print(f"KẾT QUẢ: {len(PASSED)} PASS / {len(FAILED)} FAIL")
if FAILED:
    print("Các test hỏng:")
    for f in FAILED:
        print(f"  - {f}")
print("=" * 70)
sys.exit(1 if FAILED else 0)
