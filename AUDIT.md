# 🔍 AUDIT: Kiểm tra tính đúng đắn của phương pháp (Overfit / Look-ahead / Lỗi logic)

Phạm vi: `main.py` (Crypto Prop Firm Dual-Engine), `vn_stock_sniper.py` (VN Buffett Sniper + Két 5%), `run_all.py`, `vn_portfolio_ledger.json`.

---

## 📊 TRẠNG THÁI XỬ LÝ (cập nhật sau khi sửa)

**Đã sửa trong code: 24/29 vấn đề.** Chạy `python selftest.py` → **39/39 test PASS**.

| # | Vấn đề | Trạng thái |
|---|---|---|
| 1 | Token Telegram hard-code | ✅ Đã bỏ khỏi source — ⚠️ **bạn vẫn phải tự revoke qua @BotFather** vì token còn trong Git history |
| 2 | `SEED_HISTORY` lệnh bịa | ✅ Xoá sạch, sổ cái bắt đầu từ 0 lệnh |
| 3 | Holdings VN + cổ tức bịa | ✅ Bắt đầu 100% tiền mặt |
| 4 | NAV thủng 41.25tr | ✅ Bảo toàn tuyệt đối (có test) |
| 5 | Cổ tức lệch NAV vs PnL | ✅ Bỏ cổ tức khỏi PnL chưa thực hiện |
| 6 | **Phantom fill (look-ahead)** | ✅ Entry = giá live + chặn nến cũ >90s + chặn lệch giá >0.15% |
| 7 | `.bfill()` ATR/vol_sma | ✅ Đổi sang `dropna()` + `shift(1)` |
| 8 | Asia range bị cắt cụt | ✅ `limit` 120 → 288, thêm kiểm tra phủ đủ phiên |
| 9 | Nhầm UTC vs UTC+7, không xử lý DST | ✅ Chuẩn hoá UTC tường minh + `zoneinfo` cho NY open |
| 10 | `tight_box` chạy 24/7 | ✅ Bắt buộc nằm trong phiên |
| 11 | `vol_spike` tự tham chiếu | ✅ Thêm `shift(1)` |
| 12 | **Chi phí 0.02R (sai 10-25 lần)** | ✅ Phí theo notional + slippage. WR hoà vốn thật: **59.6%** ở stop 0.20% |
| 13 | PnL không theo giá thoát | ✅ Tính từ `exit_price` thực + slippage khi chạm stop |
| 14 | Không có luật prop firm | ✅ Daily loss 5% + max DD 10% + tự halt/unhalt |
| 15 | PF/Expectancy không cập nhật | ✅ `recompute_stats()` sau mỗi lệnh |
| 16 | **Định giá circular** | ✅ Bỏ nhánh neo fair value vào giá — mã nào không định giá được thì **bỏ qua** |
| 17 | README ≠ code (ROE, FCF) | ✅ Đã thêm bộ lọc ROE/PE/PB/thanh khoản + sửa README |
| 18 | Survivorship bias watchlist | ⚠️ **Chưa sửa** — đã ghi cảnh báo rõ trong code + dashboard |
| 19 | Không có luật bán | ✅ Chốt lời khi giá ≥ giá trị hợp lý |
| 20 | Fill giả ngoài giờ | ✅ Chặn theo phiên HOSE + phí 0.15% + thuế 0.1% + T+2.5 |
| 21 | **Két cạn trong 13 giây** | ✅ Sửa race condition + sàn tiền mặt 20% + ≤1 lệnh/ngày |
| 22 | Lãi két mất ngày khi offline | ✅ Cộng dồn theo số ngày thực tế |
| 23 | `execute_buy` có thể âm tiền | ✅ Vòng lặp giảm lô + kiểm tra cuối |
| 24 | Cỡ mẫu = 0 | ⚠️ Không sửa được bằng code — đã thêm banner cảnh báo `<100 lệnh` |
| 25 | Không có backtest/OOS | ❌ **Chưa làm** — hạn chế lớn nhất còn lại |
| 26 | Không có benchmark | ⚠️ Đã lưu `nav_history` làm nền, chưa nối VN-Index |
| 27 | API không fallback, dữ liệu cũ | ✅ Đánh dấu `stale` + hiển thị cảnh báo trên dashboard |
| 28 | `except: pass` nuốt lỗi, không test | ✅ Báo lỗi rõ + giữ file `.corrupt` + ghi file nguyên tử + `selftest.py` |
| 29 | **`run_all.py` crash ngay khi boot** | ✅ Xem bên dưới |

### 🔴 #29 — Lỗi mới phát hiện: `run_all.py` chưa từng chạy được

`run_all.py` (chính là `startCommand` trong `render.yaml`) gọi 3 hàm **không tồn tại**:

```python
crypto_engine.load_ledger()        # là method của LiveForwardTester, không phải hàm module
crypto_engine.recalculate_metrics() # CHƯA TỪNG TỒN TẠI
crypto_engine.main_loop()           # CHƯA TỪNG TỒN TẠI (tên thật: start_loop)
```

→ Service crash với `AttributeError` ngay dòng đầu của `__main__`. Nghĩa là bản deploy
"Unified Runner" **không bao giờ khởi động được**. Đã sửa sang dùng instance
`LiveForwardTester` và verify boot thành công.

### Còn lại phải làm (không thể sửa bằng code, cần bạn quyết định)
1. **Revoke 2 Telegram token** — bắt buộc, ngay.
2. **Viết backtest engine + walk-forward + kiểm tra độ nhạy tham số** (mục #25, Bước 4 bên dưới).
3. **Đổi universe VN sang luật cơ học** thay vì danh sách chọn tay (mục #18).
4. **Nối benchmark VN-Index / BTC buy&hold** để đo alpha (mục #26).
5. **Thay heuristic `ROE × 0.55`** bằng mô hình định giá có cơ sở (DCF/Gordon).
6. **Gắn persistent disk** trên Render và set `DATA_DIR` (mục #2).

**Kết luận ngắn gọn:** Phương pháp **chưa đủ tin cậy để kết luận có edge**. Không tồn tại backtest nào trong repo, nên không thể nói "overfit" theo nghĩa cổ điển (fit tham số vào dữ liệu quá khứ) — nhưng có đủ 3 nhóm vấn đề nghiêm trọng hơn: **(1) số liệu hiệu suất bị bịa/seed cứng**, **(2) look-ahead & phantom-fill trong vòng lặp live**, **(3) mô hình chi phí và kế toán NAV sai**. Chi tiết + mức độ + cách sửa bên dưới.

---

## 🔴 P0 — Phải sửa ngay (làm sai lệch kết quả hoặc rủi ro bảo mật)

### 1. Token Telegram bị hard-code trong source & đã nằm trong Git history
`main.py:23-24` và `vn_stock_sniper.py:34-35` chứa bot token + chat ID thật làm giá trị default.
→ **Revoke cả 2 token qua @BotFather ngay**, chuyển sang bắt buộc đọc từ env (fail-fast nếu thiếu). Lưu ý: xoá dòng code thôi **không đủ**, token vẫn còn trong commit `48adf29`.

### 2. Lịch sử giao dịch được "seed" cứng = số liệu bịa (`main.py:36-77`)
`SEED_HISTORY` chứa 2 lệnh BTC với entry/exit/PnL viết tay, và `load_ledger()` (`main.py:293-313`) **ghi đè balance = 98,982.60 và win_rate = 0%** mỗi khi file ledger không tồn tại hoặc `total_trades == 0`.

Hệ quả nặng: Render free tier có **disk ephemeral** → mỗi lần container restart/redeploy, `forward_test_ledger.json` biến mất → equity curve reset về seed. Nghĩa là **mọi chuỗi thua (và thắng) đều bị xoá định kỳ** — đây là survivorship bias ở mức kết quả, đường vốn hiển thị không phải đường vốn thật.

→ Bỏ hoàn toàn `SEED_HISTORY`; bắt đầu từ `total_trades = 0`; lưu ledger ra Postgres/Render Disk/Gist, không dùng file trong container.

### 3. Danh mục VN khởi tạo bằng vị thế & cổ tức bịa (`vn_stock_sniper.py:171-245`)
4 holdings mở sẵn với `current_price > avg_price` (FPT 68,000→71,400; DGC 41,500→44,300; PNJ 39,500→41,700; HPG 21,000→22,050) và `dividends_received` = 5.0M / 6.0M / 3.5M VNĐ viết tay.
→ Đây là **lãi tạo sẵn ngay giây đầu tiên của forward test**. Muốn forward test sạch: bắt đầu 100% tiền mặt, mọi vị thế phải do engine tự vào.

### 4. Kế toán NAV bị thủng 41,250,000 VNĐ (~4.1% vốn)
- `initial_capital` = 1,000,000,000
- `cash_vault` khởi tạo = 40% = 400,000,000 (`vn_stock_sniper.py:167`)
- Giá vốn 4 holdings = 170.0 + 124.5 + 138.25 + 126.0 = **558,750,000**
- Tổng = 958,750,000 → **thiếu 41,250,000 VNĐ không tồn tại ở đâu cả.**

`total_profit = NAV - initial_capital` (`:322`) vì thế mang sẵn khoản lỗ giả -4.1%. Bug này khiến mọi con số "Lợi nhuận ròng" trong Telegram/dashboard đều sai.

### 5. Cổ tức tính vào PnL từng mã nhưng không vào NAV
`get_portfolio_summary()`: `pnl = mkt_val - cost + divs` (`:302`) nhưng `total_nav = stock_value + cash` (`:320`) — cổ tức không được cộng vào `cash_vault`.
→ `sum(holding.pnl)` = +45.4M trong khi `total_profit` = -10.35M. Hai con số trên cùng một dashboard mâu thuẫn nhau.

---

## 🟠 P1 — Look-ahead & bias thực sự trong engine crypto

### 6. Phantom fill: entry giá quá khứ nhưng exit theo giá hiện tại (`main.py:482-555` + `556-570`)
`scan_for_new_entry()` lấy `curr = df.iloc[-2]` (nến đã đóng — điểm này **đúng**, tránh repaint) và đặt `entry_price = curr["close"]`. Nhưng vòng lặp `start_loop()` chạy mỗi 5 giây, và nến đó có thể đã đóng **tới 5 phút trước** (hoặc lâu hơn nếu process bị sleep/spin-down).

Ngay sau đó `manage_active_position(live_price)` so sánh SL/TP với **giá live hiện tại**. Nếu trong 5 phút đó giá đã chạy tới TP, bot **ghi nhận một lệnh thắng với giá vào mà nó chưa bao giờ có thể khớp** → đây chính xác là look-ahead bias, và nó lệch một chiều theo hướng có lợi.

→ Sửa: entry price phải là giá **live tại thời điểm phát tín hiệu** (hoặc open của nến kế tiếp), không phải `close` của nến đã đóng. Và phải kiểm tra khoảng cách thời gian: nếu `now - candle_close > 1` nến thì bỏ tín hiệu.

### 7. `.bfill()` trên ATR và Volume SMA (`main.py:389-390`)
```python
df["atr"] = tr.rolling(window=14).mean().bfill()
df["vol_sma"] = df["volume"].rolling(window=20).mean().bfill()
```
`bfill()` **kéo giá trị tương lai ngược về quá khứ**. Ở chế độ live chỉ dùng `iloc[-2]` nên chưa gây hại, nhưng nếu ai đó tái sử dụng hàm này để backtest thì 14/20 nến đầu mỗi lần fetch sẽ dùng dữ liệu tương lai. Đây là look-ahead đang "ngủ đông". → Dùng `dropna()` thay vì `bfill()`.

### 8. Asia range bị cắt cụt do `limit=120` (`main.py:352, 380-392`)
120 nến M5 = **10 giờ dữ liệu**. Khi bot quét lúc 11:00 UTC, cửa sổ dữ liệu chỉ lùi tới ~01:00 UTC → phiên Á (0h–6h UTC) **mất mất giờ đầu tiên**. `asia_high`/`asia_low` do đó hẹp hơn thực tế một cách hệ thống → **tạo ra nhiều tín hiệu "sweep" giả hơn**. Setup lõi của Engine 1 đang chạy trên một mức tham chiếu sai.
→ `limit` tối thiểu 288 (24h) và kiểm tra rằng khoảng 0h–6h UTC đã đầy đủ trước khi cho phép giao dịch.

### 9. Nhầm lẫn múi giờ UTC vs UTC+7
`df["hour"]` lấy từ `pd.to_datetime(unit="ms")` → **UTC naive**. Nhưng entry/exit time ghi log bằng `get_vn_time_str()` → **UTC+7**. Cùng một lệnh có hai hệ giờ khác nhau trong ledger. Ngoài ra `hour == 13 and minute >= 30` (được ngụ ý là NY open) chỉ đúng vào mùa hè — **không xử lý DST của Mỹ**, mùa đông NY open là 14:30 UTC.

### 10. Nhánh `tight_box` không có bộ lọc phiên (`main.py:507-514`)
```python
l_eng2 = (in_orb_window and ...) or (tight_box and ... )
```
Toán tử `or` khiến nhánh `tight_box` giao dịch **24/7, mọi khung giờ**, mâu thuẫn hoàn toàn với mô tả "London Judas / ORB" trong README. Đây là kiểu điều kiện nới lỏng thường thấy khi tune tay cho "ra nhiều lệnh hơn".

### 11. `vol_spike` tự tham chiếu chính nó
`vol_sma` = SMA20 **bao gồm cả nến đang xét** → ngưỡng `volume > 1.3 * vol_sma` bị pha loãng. Nên dùng `.shift(1)`.

---

## 🟠 P1 — Mô hình chi phí sai nghiêm trọng (đây là chỗ giết edge)

### 12. Chi phí giao dịch giả định 0.02R — thấp hơn thực tế khoảng 10–25 lần
`main.py:414-429`: thắng = `1.35 - 0.02`, thua = `-1.02`. Tức là toàn bộ phí + slippage được giả định = 2% của khoản rủi ro.

Kiểm tra bằng số: stop = `1.2 × ATR14(M5)`. ATR14 M5 của BTCUSDT thường **0.10%–0.25% giá** → stop ≈ **0.12%–0.30%**. Phí taker Binance Futures **0.04% mỗi chiều = 0.08% khứ hồi** (chưa tính funding, chưa tính slippage market order).

| Stop (%) | Phí khứ hồi tính theo R | WR hoà vốn |
|---|---|---|
| 0.30% | **0.27 R** | ~54% |
| 0.20% | **0.40 R** | ~60% |
| 0.12% | **0.67 R** | ~71% |

So với giả định hiện tại (cost 0.02R → WR hoà vốn ~43.4%). Nói cách khác: **bot đang che giấu khoảng 15–28 điểm phần trăm win-rate cần thiết.** Một setup breakout M5 hiếm khi đạt WR 60%+. Đây là lỗi đơn lẻ nghiêm trọng nhất về mặt phương pháp.

→ Bắt buộc: tính PnL từ `exit_price` thực tế, trừ phí theo notional (`qty × price × fee_rate × 2`), cộng slippage giả định ≥ 1 tick + funding nếu giữ qua mốc 8h.

### 13. PnL không dựa trên giá thoát thực tế
`pnl_r` là hằng số cứng (`+1.33` / `-1.02`) bất kể `exit_price`. Không mô hình hoá **gap qua stop** — giả định luôn khớp chính xác tại SL. Trên M5 crypto điều này lạc quan có hệ thống, đặc biệt lúc tin tức.

### 14. Không có bất kỳ luật Prop Firm nào được cài đặt
Dự án tên là "Prop Firm" nhưng không có: daily loss limit (thường 5%), max total drawdown (10%), consistency rule, min trading days. `max_drawdown_pct` chỉ tính trên **closed trades** (`main.py:443-444`), không tính drawdown intra-trade → **báo cáo drawdown thấp hơn thực tế**.

### 15. `profit_factor` và `expectancy_r` không bao giờ được cập nhật
Sau mỗi lệnh đóng, code chỉ cập nhật `win_rate`. Hai chỉ số kia giữ nguyên giá trị seed (`0.0` và `-1.02`) vĩnh viễn nhưng vẫn hiển thị lên dashboard.

---

## 🟠 P1 — Vấn đề phương pháp bên VN Sniper

### 16. Định giá bị **circular** — Fair Value neo vào chính giá thị trường (`vn_stock_sniper.py:77-82`)
```python
target_pe = min(max(roe * 0.55, 10.0), 22.0)
fair_value = eps * target_pe
if fair_value > price * 2.0 or fair_value < price * 0.5:
    fair_value = price * (1.0 + (roe - 15.0)/100.0) if roe > 15 else price * 0.95
discount_price = fair_value * 0.80
```
Ba vấn đề chồng nhau:
1. `target_pe = ROE × 0.55` **không có cơ sở lý thuyết nào**. P/E hợp lý phụ thuộc g, r, payout (Gordon), không phải một hằng số 0.55 và clamp [10, 22] chọn tay. Đây là **overfit bằng trực giác** — 3 magic numbers (0.55, 10, 22) chưa từng được validate trên dữ liệu nào.
2. Nhánh fallback lấy **giá thị trường làm đầu vào cho giá trị nội tại** → "biên an toàn 20%" mất hết ý nghĩa. Tệ hơn, nhánh này khiến điều kiện mua **không bao giờ đúng** (`price ≤ 0.8 × 0.95 × price` là vô lý), nên hệ thống chỉ mua khi nhánh EPS cho ra định giá cao — tức là **thiên lệch chọn đúng những mã mà mô hình sai nhiều nhất về phía lạc quan**.
3. Dùng **EPS trailing** và ROE tại một thời điểm, không normalize chu kỳ. Với HPG, DGC (thép/hoá chất chu kỳ) đây là bẫy kinh điển: EPS đỉnh chu kỳ × PE cao = "rẻ" ngay đúng đỉnh.

### 17. README nói một đằng, code làm một nẻo
README quảng cáo *"Lọc ROE cao, biên an toàn MoS 20%, FCF lớn"*. Trong code: **không có bộ lọc ROE nào** (ROE chỉ dùng để tính target_pe và để sort), **không có FCF ở bất cứ đâu**, không kiểm tra nợ vay, không kiểm tra moat, không kiểm tra thanh khoản (`volume_10d` được fetch nhưng không dùng).

### 18. Survivorship / selection bias ở watchlist
20 mã (`:44-49`) là những cái tên "đã thắng" của thị trường VN được chọn bằng **hindsight của con người**. Bất kỳ kết quả nào của hệ thống đều bị nhiễm bias này. Muốn đánh giá đúng phải chọn universe bằng luật cơ học tại thời điểm quá khứ (ví dụ: top 100 vốn hoá tại T-0), không phải danh sách hôm nay.

### 19. Không có luật bán — hệ thống chỉ mua
Không có exit theo định giá (bán khi price > fair_value), không stop-loss, không rebalance, không xử lý luận điểm hỏng. Nghĩa là **không tồn tại lợi nhuận đã thực hiện**, chỉ có mark-to-market. Không thể đo Sharpe/turnover/PF của một chiến lược một chiều.

### 20. Fill giả: mua tại `priceClose` bất kể giờ giao dịch
`background_scheduler()` gọi `run_market_scan()` **mỗi 5 phút, 24/7** kể cả đêm, cuối tuần, ngày lễ. `execute_sniper_buy()` khớp lệnh **tại đúng giá `priceClose` lấy từ API**, không có:
- phí môi giới VN (0.15–0.35% mỗi chiều) và thuế bán 0.1%
- chu kỳ thanh toán T+2.5 (mua hôm nay không bán được ngay)
- biên độ ±7% HOSE / ±10% HNX, lệnh ATO/ATC
- kiểm tra thanh khoản (khối lượng đặt vs volume trung bình)
- kiểm tra `9:00 ≤ giờ ≤ 14:45` và ngày làm việc

→ Đây là "khớp lệnh trên giá quá khứ", cùng bản chất với lỗi #6.

### 21. Bằng chứng thực tế: két 5% bị rút cạn trong 13 giây
Xem `vn_portfolio_ledger.json` — 4 lệnh SNIPER_BUY lúc **11:48:48 → 11:49:01 cùng ngày 25/08**, tiêu 389.22M/400M. `cash_vault` còn lại **10,780,000 VNĐ (1.1% NAV)**.

Toàn bộ luận điểm "Két tiền mặt linh hoạt 5%/năm để chờ cơ hội" **đã chết ngay ngày đầu tiên**. Nguyên nhân: không có giới hạn số lệnh/ngày, không có sàn tiền mặt tối thiểu, và điều kiện `curr_weight < 15%` được kiểm tra trên `summary` chụp **trước vòng lặp** (`:439-448`) nên 4 lệnh đều thấy cùng một trạng thái cũ → **race condition kinh điển**.

### 22. Lãi két tính sai khi bot offline (`vn_stock_sniper.py:262-280`)
Chỉ cộng **đúng 1 ngày lãi** mỗi lần phát hiện ngày đổi. Nếu container ngủ 5 ngày (Render free tier spin-down) → mất 4 ngày lãi. Nên tính `(today - last_date).days`.

### 23. `execute_sniper_buy` có thể vượt số dư
`:363-373`: nếu `total_cost > cash` thì chỉ trừ **một lần** 100 cổ. Với mã giá cao và cash sát ngưỡng, một lần trừ không đủ → `cash_vault` âm. Nên dùng `while` hoặc tính lại `shares = int(cash / price / 100) * 100`.

---

## 🟡 P2 — Thống kê & quy trình

### 24. Cỡ mẫu bằng 0 — không thể kết luận gì
Crypto: **2 lệnh** (và cả 2 đều là bịa). VN: **0 lệnh bán**. Để phân biệt edge thật với may mắn ở mức RR 1.35 cần cỡ **150–300 lệnh** mới có ý nghĩa thống kê. Bất kỳ con số win-rate nào hiện tại đều là nhiễu thuần tuý.

### 25. Không có backtest, không có OOS, không có walk-forward
Đây là lý do "overfit" chưa đo được — **không có gì để đo**. Nhưng các tham số dưới đây đều là magic numbers chọn tay, chưa qua validation nào:

| Tham số | Giá trị | File |
|---|---|---|
| SL multiplier | 1.2 × ATR | `main.py:518` |
| RR | 1.35 | `main.py:519` |
| Volume spike | 1.3× | `main.py:390` |
| Tight box | < 1.5 × ATR | `main.py:505` |
| Lookback breakout | 10 nến | `main.py:503-504` |
| EMA | 20 / 50 | `main.py:383-384` |
| Giờ London | 7–11 | `main.py:494` |
| Giờ ORB | 7:30 / 13:30 | `main.py:502` |
| target_pe hệ số | 0.55 | `sniper.py:77` |
| PE clamp | [10, 22] | `sniper.py:77` |
| MoS | 20% | `sniper.py:83` |
| Weight cap | 15% | `sniper.py:442` |
| Allocation | 25% cash / 100M | `sniper.py:443` |

**Số bậc tự do ≈ 13 trên 2 lệnh dữ liệu.** Đây là điều kiện lý tưởng cho overfit ngay khi bắt đầu tune.

### 26. Không có benchmark
Không so với buy & hold BTC, không so với VN-Index. Danh mục VN cầm FPT/HPG/PNJ/DGC — 4 mã beta cao; nếu VN-Index +15% mà danh mục +12% thì đó là **alpha âm**, nhưng dashboard sẽ hiển thị "🟢 +12%".

### 27. Phụ thuộc API không chính thức không có fallback
`api.simplize.vn` là endpoint nội bộ, không có hợp đồng SLA. Khi lỗi, `fetch_stock_data` trả về dict `price = 0.0` (`:107-119`) — an toàn ở chỗ không mua, nhưng `update_prices` sẽ giữ giá cũ vô hạn mà **không có cảnh báo dữ liệu cũ (stale)**. NAV có thể đang hiển thị giá của tuần trước.

### 28. Không có test, không có logging có cấu trúc, `except Exception: pass`
`vn_stock_sniper.py:162-168` nuốt lỗi khi load ledger → ledger hỏng sẽ **âm thầm bị reset về state bịa** thay vì báo lỗi. Không có một unit test nào trong repo.

---

## ✅ Lộ trình sửa theo thứ tự ưu tiên

**Bước 0 — bảo mật (hôm nay)**
1. Revoke 2 Telegram token; chuyển sang env bắt buộc.

**Bước 1 — làm cho số liệu trung thực (trước khi chạy tiếp bất cứ giây nào)**
2. Xoá `SEED_HISTORY` và 4 holdings + cổ tức bịa. Bắt đầu 100% tiền mặt, 0 lệnh.
3. Sửa lỗ thủng NAV 41.25M; cộng cổ tức vào `cash_vault`.
4. Ledger ra storage bền (Postgres free tier của Render / Supabase), không dùng file container.
5. Cập nhật `profit_factor`, `expectancy_r`; tính max DD trên equity curve mark-to-market, không chỉ closed trades.

**Bước 2 — sửa look-ahead & chi phí**
6. Entry = giá live tại thời điểm tín hiệu; bỏ tín hiệu nếu nến đã đóng quá 1 chu kỳ.
7. `bfill()` → `dropna()`; `limit` 120 → 288; `vol_sma` thêm `.shift(1)`.
8. Chuẩn hoá toàn bộ về một múi giờ (khuyến nghị UTC nội bộ, chỉ format sang UTC+7 khi hiển thị); xử lý DST cho phiên NY.
9. Thay `pnl_r` hằng số bằng PnL tính từ `exit_price` thực − phí theo notional − slippage. Chạy lại bảng breakeven WR ở mục #12.
10. VN: thêm phí 0.15–0.35% + thuế bán 0.1%, T+2.5, biên độ, kiểm tra giờ phiên và ngày làm việc trước khi ghi nhận fill.

**Bước 3 — sửa logic chiến lược**
11. Fix race condition sniper buy: cập nhật `summary` trong mỗi vòng lặp, thêm sàn tiền mặt tối thiểu (ví dụ ≥ 20% NAV) và max 1 lệnh/mã/ngày.
12. Bỏ nhánh fallback neo fair value vào giá. Nếu mô hình EPS×PE cho kết quả vô lý → **skip mã đó**, không được bịa số.
13. Thêm luật bán (trim khi price > fair_value, cắt khi luận điểm hỏng), thêm bộ lọc ROE/FCF/nợ như README đã hứa — hoặc sửa README cho khớp code.
14. Thêm daily loss limit + max DD của prop firm, dừng bot khi vi phạm.

**Bước 4 — validation thật sự**
15. Viết backtest engine riêng, tách bạch: data → signal (chỉ dùng `t-1`) → execution (fill ở `t+1` open, có phí/slippage) → ledger.
16. Chia in-sample / out-of-sample; walk-forward. Kiểm tra độ nhạy tham số: nếu đổi SL 1.2→1.1 hoặc 1.3 mà kết quả sập → đó là overfit.
17. Deflated Sharpe hoặc White Reality Check để phạt số lần thử tham số.
18. Benchmark: BTC buy&hold cho engine crypto, VN-Index cho engine VN.
19. Chỉ khi backtest sạch có edge → mới chạy forward test, mục tiêu tối thiểu **100 lệnh** trước khi kết luận.

---

## 📌 Trả lời trực tiếp câu hỏi

| Câu hỏi | Trả lời |
|---|---|
| **Có overfit không?** | Chưa đo được vì không có backtest — nhưng có **13 magic numbers chọn tay trên 0 dữ liệu validation**, và các heuristic định giá (`ROE × 0.55`, clamp [10,22]) là overfit trực giác điển hình. Rủi ro overfit: **rất cao**. |
| **Có look-ahead không?** | **Có, 3 chỗ.** (a) Phantom fill: entry giá nến cũ, exit giá live → #6. (b) `.bfill()` trên ATR/vol_sma → #7. (c) VN: khớp lệnh tại `priceClose` ngoài giờ giao dịch → #20. Điểm tốt: `iloc[-2]` tránh được repaint nến chưa đóng. |
| **Còn gì sai nữa?** | Nghiêm trọng hơn cả hai cái trên: **số liệu hiệu suất là bịa** (#2, #3), **NAV thủng 41.25M** (#4), **chi phí giao dịch thấp hơn thực tế 10–25 lần** (#12), **két tiền mặt đã cạn trong 13 giây do race condition** (#21), và **token bị lộ trong Git** (#1). |
