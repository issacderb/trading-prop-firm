# 🤖 Prop Firm Dual-Engine Quant Trading Bot (Forward Test)

Bot tự động Forward-Test chiến lược Định lượng Thể chế (Dual-Engine: London Judas Asian Range Sweep + 30m ORB / Bob Volman 5m Block Breakout) trên Binance Futures M5 và bắn tín hiệu trực tiếp về Telegram.

---

## 🚀 Hướng Dẫn Deploy Miễn Phí Lên Render.com trong 2 Phút

### Bước 1: Push mã nguồn lên GitHub của bạn
```bash
git add .
git commit -m "Add Prop Firm Dual-Engine Trading Bot"
# Nếu bạn đã có link repo GitHub của mình:
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main
```

### Bước 2: Deploy trên Render.com
1. Đăng nhập [Render.com](https://render.com) (Miễn phí 100%).
2. Chọn **New +** $\to$ **Background Worker** (hoặc **Web Service**).
3. Kết nối với Repository GitHub của bạn.
4. Tại phần **Environment Variables**, thêm 2 biến:
   * `TELEGRAM_BOT_TOKEN`: Token bot bạn lấy từ `@BotFather`
   * `TELEGRAM_CHAT_ID`: ID của bạn lấy từ `@userinfobot`
5. Bấm **Create Background Worker** $\to$ Bot sẽ chạy vĩnh viễn 24/7 và gửi tín hiệu về điện thoại mỗi khi có lệnh!

---

## 💻 Chạy Trực Tiếp Trên Máy Tính Cá Nhân
```bash
pip install -r requirements.txt
python main.py
```
