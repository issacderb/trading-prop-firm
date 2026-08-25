# 🏛 Hệ Thống Định Lượng & Forward Test Thực Chiến

Dự án tích hợp 2 hệ thống định lượng độc lập, chuyên biệt:

1. **[🇻🇳 CHỨNG KHOÁN VN] Buffett Value Sniper & 5% Cash Vault Forward-Testing Engine (`vn_stock_sniper.py`)**:
   * Hệ thống tự động Forward-Test chiến lược Giá trị Warren Buffett (Lọc ROE cao, biên an toàn MoS 20%, FCF lớn).
   * Tự động quản lý **Két tiền mặt linh hoạt 5%/năm (T+0)**, tự động cộng dồn lãi kép hàng ngày.
   * Tự động kích hoạt mua gom khi cổ phiếu rơi vào Vùng Mua Chiết Khấu.
   * Báo cáo NAV và biến động qua Telegram & Web Dashboard trực quan.

2. **[🤖 CRYPTO PROP FIRM] Dual-Engine Quant Trading Bot (`main.py`)**:
   * Bot giao dịch định lượng thể chế (London Judas Asian Sweep + 30m ORB / Block Momentum Breakout) trên Binance Futures M5.

---

## 🚀 Hướng Dẫn Deploy Miễn Phí 100% Lên Render.com (Chạy 24/7)

### Bước 1: Tạo Bot Telegram riêng cho Cổ Phiếu (Tránh lẫn với Crypto)
1. Mở Telegram, tìm `@BotFather` $\to$ gửi `/newbot`.
2. Đặt tên bot (Ví dụ: `VN Stock Buffett Sniper`) và username (Ví dụ: `my_vn_stock_buffett_bot`).
3. Copy **HTTP API Token** nhận được (Dạng `123456789:ABCdef...`).
4. Bấm Start bot mới tạo, sau đó vào `@userinfobot` để lấy **Chat ID** của bạn.

---

### Bước 2: Deploy lên Render.com trong 2 Phút
1. Đăng nhập vào [Render.com](https://render.com) (Miễn phí 100%).
2. Chọn **New +** $\to$ **Web Service** (cho Bot Cổ Phiếu) hoặc **Background Worker** (cho Bot Crypto).
3. Kết nối với GitHub Repository của bạn.
4. Tại phần **Settings**:
   * **Start Command:** `python -u vn_stock_sniper.py` (hoặc `python -u main.py` nếu deploy bot Crypto).
5. Tại phần **Environment Variables**, thêm:
   * `VN_STOCK_TELEGRAM_BOT_TOKEN`: Token bot Telegram bạn vừa tạo.
   * `VN_STOCK_TELEGRAM_CHAT_ID`: Chat ID của bạn.
   * `INITIAL_CAPITAL`: `1000000000` (Vốn khởi điểm 1 Tỷ VNĐ).
   * `VAULT_ANNUAL_RATE`: `0.05` (5% Lãi suất Két tiền mặt/năm).
6. Bấm **Create Web Service** $\to$ Hệ thống sẽ tự động khởi chạy 24/7 vĩnh viễn và gửi thông báo trực tiếp về điện thoại!

---

## 💻 Chạy Trực Tiếp Trên Máy Tính Cá Nhân

```bash
# Cài đặt thư viện
pip install -r requirements.txt

# Chạy Bot Cổ Phiếu Việt Nam (Buffett Sniper & Két 5%)
python vn_stock_sniper.py

# Hoặc Chạy Bot Crypto Prop Firm Trading
python main.py
```
