# 🏛 Hệ Thống Định Lượng & Forward Test Thực Chiến

> ⚠️ **ĐỌC `AUDIT.md` TRƯỚC KHI TIN BẤT KỲ CON SỐ NÀO.**
> Hệ thống này **chưa có backtest, chưa có out-of-sample validation**. Đây là forward
> test thuần. Mọi chỉ số hiệu suất chỉ có ý nghĩa sau tối thiểu ~100 lệnh đã đóng.

Dự án gồm 2 engine định lượng độc lập:

1. **[🇻🇳 CHỨNG KHOÁN VN] Value Sniper & Cash Vault (`vn_stock_sniper.py`)**
   * Quét định giá theo heuristic `target_PE = f(ROE)` + biên an toàn (MoS) 20%.
   * Bộ lọc chất lượng: ROE ≥ 15%, P/E ≤ 25, P/B ≤ 4, thanh khoản ≥ 100k cp/phiên.
   * Két tiền mặt sinh lãi 5%/năm, cộng dồn theo số ngày thực tế.
   * Mô phỏng đầy đủ ràng buộc TTCK VN: giờ phiên, lô 100, phí 0.15%/chiều,
     thuế bán 0.1%, thanh toán T+2.5.
   * Kỷ luật danh mục: ≤1 lệnh mua/ngày, ≤15% NAV/mã, sàn tiền mặt 20% NAV.
   * Có luật bán: chốt lời khi giá vượt giá trị hợp lý.

2. **[🤖 CRYPTO] Dual-Engine Quant Bot (`main.py`)**
   * London Judas Asian Sweep + ORB / Block Momentum Breakout trên Binance Futures M5.
   * Mô hình chi phí thật: taker 0.04%/chiều + slippage, PnL tính từ giá thoát thực tế.
   * Luật prop firm: dừng giao dịch khi lỗ ngày 5% hoặc max drawdown 10%.
   * Chống phantom fill: bỏ tín hiệu nếu nến đã đóng > 90s hoặc giá đã chạy > 0.15%.

---

## ⚠️ Giới hạn phương pháp đã biết (chưa khắc phục được bằng code)

| Vấn đề | Trạng thái |
|---|---|
| Không có backtest / walk-forward / OOS | ❌ Chưa có — đây là hạn chế lớn nhất |
| ~13 tham số magic number chưa test độ nhạy | ❌ Chưa validate |
| Watchlist VN chọn bằng hindsight (survivorship bias) | ❌ Cần universe cơ học theo thời điểm |
| Chưa so sánh với benchmark (VN-Index / BTC buy&hold) | ❌ Chưa có, nên chưa đo được alpha |
| `target_PE = ROE × 0.55` là heuristic, không phải DCF | ⚠️ Đã ghi rõ cảnh báo, chưa thay thế |
| EPS trailing chưa normalize chu kỳ | ⚠️ Rủi ro bẫy định giá với mã chu kỳ |
| Lịch nghỉ lễ TTCK VN | ⚠️ Chưa có, mới chặn T7/CN |
| Cỡ mẫu | ❌ Cần ≥100 lệnh mới có ý nghĩa thống kê |

Xem `AUDIT.md` để biết chi tiết từng lỗi và lộ trình xử lý.

---

## 🧪 Chạy self-test

```bash
pip install -r requirements.txt
python selftest.py
```

39 test khoá lại các bất biến quan trọng: bảo toàn NAV, phí/thuế, T+, giờ phiên,
trần tỷ trọng, chống look-ahead, luật dừng lỗ, không có secret hard-code.

---

## 🔐 Biến môi trường

**Bắt buộc** (không còn giá trị mặc định hard-code — bot sẽ chỉ log ra stdout nếu thiếu):

| Biến | Mô tả |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Bot Telegram cho engine Crypto |
| `VN_STOCK_TELEGRAM_BOT_TOKEN` / `VN_STOCK_TELEGRAM_CHAT_ID` | Bot Telegram cho engine Cổ phiếu VN |

**Quan trọng về lưu trữ:**

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `DATA_DIR` | `.` | **Nên trỏ tới persistent disk.** Trên Render free tier, disk container là ephemeral → mỗi lần restart sẽ mất toàn bộ lịch sử giao dịch, làm đường vốn hiển thị không đúng thực tế. |

**Tuỳ chỉnh chiến lược & chi phí** (đều có mặc định hợp lý):

```
# Crypto
SYMBOL, INTERVAL, RISK_PER_TRADE_PCT, INITIAL_BALANCE
TAKER_FEE_RATE=0.0004, SLIPPAGE_RATE=0.0001, STOP_SLIPPAGE_RATE=0.0003
SL_ATR_MULT=1.2, RR_TARGET=1.35, VOL_SPIKE_MULT=1.3, MIN_STOP_PCT=0.0015
DAILY_LOSS_LIMIT_PCT=0.05, MAX_TOTAL_DD_PCT=0.10
MAX_SIGNAL_AGE_SEC=90, MAX_ENTRY_DEVIATION=0.0015

# Cổ phiếu VN
INITIAL_CAPITAL=1000000000, VAULT_ANNUAL_RATE=0.05
BROKER_FEE_RATE=0.0015, SELL_TAX_RATE=0.001, SETTLEMENT_DAYS=3
MIN_ROE=15, MAX_PE=25, MAX_PB=4, MIN_LIQUIDITY_SHARES=100000, MOS_RATE=0.20
MIN_CASH_FLOOR_PCT=0.20, MAX_POSITION_WEIGHT=0.15, MAX_BUYS_PER_DAY=1
```

> 🔑 Nếu bạn từng deploy bản trước: **token cũ đã bị lộ trong Git history — hãy
> revoke qua @BotFather và tạo token mới.** Xoá dòng code không đủ, token vẫn nằm
> trong commit cũ.

---

## 🚀 Deploy lên Render.com

1. **New +** → **Web Service**, kết nối GitHub repo.
2. **Start Command:** `python -u run_all.py` (chạy cả 2 engine trên 1 service).
3. Thêm các biến môi trường ở bảng trên vào phần **Environment**.
4. **Khuyến nghị mạnh:** gắn Persistent Disk và set `DATA_DIR=/var/data`, nếu không
   sổ cái sẽ bị reset mỗi lần container restart.

## 💻 Chạy trên máy cá nhân

```bash
pip install -r requirements.txt

python selftest.py            # kiểm tra bất biến trước
python vn_stock_sniper.py     # engine cổ phiếu VN
python main.py                # engine crypto
python run_all.py             # cả hai + dashboard tổng hợp
```
