"""
=============================================================================
UNIFIED MASTER RUNNER: CRYPTO PROP FIRM & VIETNAM STOCK BUFFETT SNIPER
Chạy song song 2 Hệ thống trên 1 Web Service duy nhất (Tiết kiệm 100% Free Tier Render)
=============================================================================
"""

import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import 2 Engine độc lập
import main as crypto_engine
import vn_stock_sniper as stock_engine

PORT = int(os.getenv("PORT", "10000"))

class UnifiedDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Health check endpoints cho Render & UptimeRobot (Giữ bot online 24/7)
        if self.path in ["/health", "/ping", "/status"]:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK - ALL ENGINES RUNNING")
            return

        # API kích hoạt quét nhanh cổ phiếu
        if self.path == "/api/stock/scan":
            threading.Thread(target=stock_engine.run_market_scan, args=(True,)).start()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "Stock scan triggered"}).encode("utf-8"))
            return

        # Render Unified Master HTML Dashboard
        crypto_ledger = crypto_engine.GLOBAL_STATE["ledger"]
        crypto_active = crypto_engine.GLOBAL_STATE["active_position"]
        stock_summary = stock_engine.LEDGER.get_portfolio_summary()

        html = self._generate_master_dashboard(crypto_ledger, crypto_active, stock_summary)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _generate_master_dashboard(self, c_led: dict, c_act: dict, s_sum: dict) -> str:
        s_pnl_color = "#10b981" if s_sum["total_profit"] >= 0 else "#ef4444"
        s_pnl_sign = "+" if s_sum["total_profit"] >= 0 else ""
        c_pnl_color = "#10b981" if c_led["account_balance"] >= crypto_engine.INITIAL_BALANCE else "#ef4444"

        # Stock Holdings Table
        stock_rows = ""
        for h in s_sum["holdings"]:
            pnl_color = "#10b981" if h["pnl"] >= 0 else "#ef4444"
            pnl_sign = "+" if h["pnl"] >= 0 else ""
            stock_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8;">{h['ticker']}</td>
                <td>{h['shares']:,}</td>
                <td>{h['avg_price']:,.0f} đ</td>
                <td><strong style="color: #f8fafc;">{h['current_price']:,.0f} đ</strong></td>
                <td>{h['market_value']:,.0f} đ</td>
                <td>{('🔒 T+' + str(h['sellable_in_days'])) if h['sellable_in_days'] > 0 else '✓'}</td>
                <td style="font-weight: bold; color: {pnl_color};">{pnl_sign}{h['pnl_pct']}% ({pnl_sign}{h['pnl']:,.0f} đ)</td>
            </tr>
            """

        # Stock Watchlist Table
        stock_wl_rows = ""
        for w in stock_engine.GLOBAL_WATCHLIST_DATA[:8]:
            if "VÙNG MUA" in w["status"]:
                badge_bg, badge_color = "#065f46", "#6ee7b7"
            elif "CHỜ CHỈNH" in w["status"]:
                badge_bg, badge_color = "#854d0e", "#fde047"
            elif "ĐẮT" in w["status"]:
                badge_bg, badge_color = "#991b1b", "#fca5a5"
            else:
                badge_bg, badge_color = "#334155", "#94a3b8"
            stock_wl_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8;">{w['ticker']}</td>
                <td>{w['name']}</td>
                <td><strong>{w['price']:,.0f} đ</strong></td>
                <td style="color: #fbbf24;">{(f"{w['fair_value']:,.0f} đ") if w['fair_value'] > 0 else "—"}</td>
                <td style="color: #34d399; font-weight: bold;">{(f"{w['discount_price']:,.0f} đ") if w['discount_price'] > 0 else "—"}</td>
                <td style="color: #a7f3d0;">{w['roe']:.1f}%</td>
                <td>{w['pe']:.1f}</td>
                <td><span style="background: {badge_bg}; color: {badge_color}; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{w['status']}</span></td>
            </tr>
            """

        # Crypto History Table
        crypto_rows = ""
        for t in reversed(c_led.get("history", [])[-8:]):
            res_color = "#10b981" if t.get("dollar_pnl", 0) > 0 else "#ef4444"
            crypto_rows += f"""
            <tr>
                <td>#{t['trade_id']}</td>
                <td><strong>{t['symbol']}</strong></td>
                <td><span style="color: {'#34d399' if t['direction']=='LONG' else '#f87171'}; font-weight: bold;">{t['direction']}</span></td>
                <td>{t['setup']}</td>
                <td>{t['entry_price']:.2f}</td>
                <td>{t['exit_price']:.2f}</td>
                <td style="color: {res_color}; font-weight: bold;">{t['outcome']}</td>
                <td style="color: {res_color}; font-weight: bold;">{t['pnl_r']:+.2f}R ({t['dollar_pnl']:+,.2f}$)</td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Dual-Quant Terminal: Crypto Prop Firm & VN Stock Buffett</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ font-family: 'Inter', sans-serif; background: #0b0f19; color: #f8fafc; padding: 24px; }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }}
                .title-box h1 {{ font-size: 24px; font-weight: 800; background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
                .badge-online {{ background: #065f46; color: #34d399; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 8px; }}
                .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #34d399; animation: pulse 1.5s infinite; }}
                @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
                .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
                @media(max-width: 1024px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
                .card {{ background: #131d31; border: 1px solid #1e293b; border-radius: 14px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); }}
                .card h2 {{ font-size: 17px; font-weight: 700; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; }}
                .kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-bottom: 16px; }}
                .kpi-mini {{ background: #0b1120; border: 1px solid #1e293b; border-radius: 10px; padding: 12px; }}
                .kpi-mini .lbl {{ font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; }}
                .kpi-mini .val {{ font-size: 18px; font-weight: 700; margin-top: 4px; }}
                table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; margin-top: 10px; }}
                th {{ background: #0b1120; color: #94a3b8; padding: 10px 12px; font-weight: 600; border-bottom: 1px solid #1e293b; }}
                td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; }}
                tr:hover {{ background: #1a2744; }}
                .btn-scan {{ background: #0284c7; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="title-box">
                        <h1>🚀 DUAL-QUANT TERMINAL (24/7 UNIFIED ENGINE)</h1>
                        <p style="color: #94a3b8; font-size: 13px; margin-top: 4px;">Chạy song song Bot Crypto Prop Firm & Hệ Thống Cổ Phiếu Việt Nam trên 1 Container</p>
                    </div>
                    <div>
                        <span class="badge-online"><span class="dot"></span> 2 HỆ THỐNG ĐANG HOẠT ĐỘNG</span>
                    </div>
                </div>

                <div class="grid-2">
                    <!-- KHỐI 1: CỔ PHIẾU VIỆT NAM -->
                    <div class="card" style="border-top: 4px solid #38bdf8;">
                        <h2>
                            <span>🇻🇳 CHỨNG KHOÁN VN (BUFFETT & KÉT 5%)</span>
                            <button class="btn-scan" onclick="triggerStockScan()">⚡ Quét Giá Ngay</button>
                        </h2>
                        <div class="kpi-row">
                            <div class="kpi-mini">
                                <div class="lbl">Tổng Tài Sản (NAV)</div>
                                <div class="val" style="color: #38bdf8;">{s_sum['total_nav']/1e6:,.1f} Tr</div>
                            </div>
                            <div class="kpi-mini">
                                <div class="lbl">Lợi Nhuận NAV</div>
                                <div class="val" style="color: {s_pnl_color};">{s_pnl_sign}{s_sum['total_return_pct']}%</div>
                            </div>
                            <div class="kpi-mini">
                                <div class="lbl">Két Tiền Mặt 5%</div>
                                <div class="val" style="color: #fbbf24;">{s_sum['cash_vault']/1e6:,.1f} Tr</div>
                            </div>
                            <div class="kpi-mini">
                                <div class="lbl">Lãi Két Đã Tích Lũy</div>
                                <div class="val" style="color: #34d399;">+{s_sum['vault_interest_earned']:,.0f} đ</div>
                            </div>
                        </div>

                        <div style="font-size: 13px; font-weight: 600; color: #cbd5e1; margin-top: 14px;">📦 Cổ Phiếu Đang Giữ ({len(s_sum['holdings'])} mã)</div>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead><tr><th>Mã</th><th>SL</th><th>Giá vốn</th><th>Thị giá</th><th>Giá trị</th><th>Thanh toán</th><th>PnL</th></tr></thead>
                                <tbody>{stock_rows}</tbody>
                            </table>
                        </div>

                        <div style="font-size: 13px; font-weight: 600; color: #cbd5e1; margin-top: 18px;">🎯 Top Watchlist Định Giá MoS 20%</div>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead><tr><th>Mã</th><th>Tên</th><th>Thị giá</th><th>Fair Value</th><th>MoS 20%</th><th>ROE</th><th>P/E</th><th>Trạng Thái</th></tr></thead>
                                <tbody>{stock_wl_rows}</tbody>
                            </table>
                        </div>
                    </div>

                    <!-- KHỐI 2: CRYPTO PROP FIRM -->
                    <div class="card" style="border-top: 4px solid #a855f7;">
                        <h2>
                            <span>🤖 CRYPTO PROP FIRM TRADING (BTC 5M)</span>
                            <span style="font-size: 12px; color: #94a3b8;">Binance Futures</span>
                        </h2>
                        <div class="kpi-row">
                            <div class="kpi-mini">
                                <div class="lbl">Số Dư Quỹ</div>
                                <div class="val" style="color: {c_pnl_color};">${c_led['account_balance']:,.2f}</div>
                            </div>
                            <div class="kpi-mini">
                                <div class="lbl">Win Rate</div>
                                <div class="val" style="color: #34d399;">{c_led['win_rate']:.1f}%</div>
                            </div>
                            <div class="kpi-mini">
                                <div class="lbl">Profit Factor</div>
                                <div class="val" style="color: #38bdf8;">{c_led['profit_factor']:.2f}</div>
                            </div>
                            <div class="kpi-mini">
                                <div class="lbl">Max Drawdown</div>
                                <div class="val" style="color: #f87171;">{c_led['max_drawdown_pct']:.2f}%</div>
                            </div>
                        </div>

                        <div style="background: #0b1120; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; margin-top: 14px; font-size: 13px;">
                            <strong>⚡ Vị Thế Hiện Tại:</strong> 
                            {f"<span style='color: #34d399;'>{c_act['direction']} {c_act['symbol']} @ {c_act['entry_price']:.2f}</span> (SL: {c_act['sl_price']:.2f} | TP: {c_act['tp_price']:.2f})" if c_act else "<span style='color: #94a3b8;'>Đang chờ setup London Sweep (14h-18h) / NY Breakout (20h-23h)</span>"}
                        </div>

                        <div style="font-size: 13px; font-weight: 600; color: #cbd5e1; margin-top: 18px;">📜 Nhật Ký Lệnh Gần Nhất</div>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead><tr><th>ID</th><th>Symbol</th><th>Hướng</th><th>Setup</th><th>Giá vào</th><th>Giá đóng</th><th>Kết quả</th><th>PnL</th></tr></thead>
                                <tbody>{crypto_rows}</tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                function triggerStockScan() {{
                    fetch('/api/stock/scan')
                        .then(r => r.json())
                        .then(d => {{
                            alert('Đã kích hoạt quét thị trường Cổ Phiếu VN và gửi bản tin về Telegram!');
                            setTimeout(() => location.reload(), 2000);
                        }});
                }}
                setInterval(() => location.reload(), 30000);
            </script>
        </body>
        </html>
        """

def start_master_web_server():
    server = HTTPServer(("0.0.0.0", PORT), UnifiedDashboardHandler)
    print(f"[UNIFIED MASTER SERVER] Web Dashboard đang chạy tại http://0.0.0.0:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    print("=================================================================")
    print(" KHỞI ĐỘNG HỆ THỐNG KÉP: CRYPTO PROP FIRM & VN STOCK VALUE SNIPER")
    print("=================================================================")

    # 1. Crypto Prop Firm Engine
    # LỖI CŨ: file này gọi crypto_engine.load_ledger() / recalculate_metrics() /
    # main_loop() — cả 3 hàm KHÔNG TỒN TẠI ở module level trong main.py
    # (load_ledger là method, 2 hàm kia chưa từng tồn tại). Vì run_all.py chính là
    # startCommand trong render.yaml nên toàn bộ service crash ngay khi boot với
    # AttributeError. Nay dùng đúng instance của LiveForwardTester.
    crypto_bot = crypto_engine.LiveForwardTester()
    crypto_bot.recompute_stats()
    t_crypto = threading.Thread(target=crypto_bot.start_loop, daemon=True)
    t_crypto.start()
    print("[THREAD 1] Crypto Prop Firm Engine đã kích hoạt.")

    # 2. Vietnam Stock Value Sniper Engine
    t_stock = threading.Thread(target=stock_engine.background_scheduler, daemon=True)
    t_stock.start()
    print("[THREAD 2] Vietnam Stock Value Sniper Engine đã kích hoạt.")

    # 3. Web Dashboard Master
    start_master_web_server()
