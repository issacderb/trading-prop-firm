"""
=============================================================================
UNIFIED MASTER RUNNER: CRYPTO PROP FIRM & VIETNAM STOCK BUFFETT SNIPER
Chạy song song 2 Hệ thống trên 1 Web Service duy nhất (Tiết kiệm 100% Free Tier Render)
=============================================================================
"""

import os
import sys
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Import 2 Engine độc lập
import crypto_engine
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

        # Render Unified Master HTML Dashboard with Tab Switching
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
        c_wr_color = "#10b981" if c_led["win_rate"] >= 50 else "#f59e0b"

        # Stock Holdings Table
        stock_rows = ""
        if len(s_sum["holdings"]) == 0:
            stock_rows = """
            <tr>
                <td colspan="8" style="text-align: center; color: #94a3b8; padding: 24px;">
                    🏖️ Danh mục hiện đang giữ <strong>100% Tiền Mặt trong Két 5%</strong> để ăn lãi hàng ngày.<br>
                    Bot đang rình quét thị trường, khi có cổ phiếu rơi vào <strong>Vùng Mua Chiết Khấu MoS</strong> hoặc <strong>Mẩu Xì Gà P/B &le; 0.70</strong> sẽ tự động giải ngân và ghi nhận vào đây!
                </td>
            </tr>
            """
        else:
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
                    <td>{h['dividends']:,.0f} đ</td>
                    <td style="font-weight: bold; color: {pnl_color};">{pnl_sign}{h['pnl_pct']}% ({pnl_sign}{h['pnl']:,.0f} đ)</td>
                    <td style="color: #94a3b8; font-size: 12px;">{h['notes']}</td>
                </tr>
                """

        # 1. Quality Moat Table
        moat_rows = ""
        for w in (stock_engine.GLOBAL_MOAT_DATA or stock_engine.GLOBAL_WATCHLIST_DATA[:15]):
            badge_bg = "#065f46" if "VÙNG MUA" in w["status"] else ("#854d0e" if "CHỜ CHỈNH" in w["status"] else "#991b1b")
            badge_color = "#6ee7b7" if "VÙNG MUA" in w["status"] else ("#fde047" if "CHỜ CHỈNH" in w["status"] else "#fca5a5")
            moat_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #38bdf8; font-size: 14px;">{w['ticker']}</td>
                <td>{w['name']}</td>
                <td><strong style="color: #f8fafc;">{w['price']:,.0f} đ</strong></td>
                <td style="color: #fbbf24;">{w['fair_value']:,.0f} đ</td>
                <td style="color: #34d399; font-weight: bold;">{w['discount_price']:,.0f} đ</td>
                <td style="color: #a7f3d0;">{w['roe']}%</td>
                <td>{w['pe']}</td>
                <td><span style="background: {badge_bg}; color: {badge_color}; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold;">{w['status']}</span></td>
            </tr>
            """

        # 2. Cigar Butt Table (UPCoM / HNX Deep Value)
        cigar_rows = ""
        for w in (stock_engine.GLOBAL_CIGAR_DATA or stock_engine.GLOBAL_WATCHLIST_DATA[15:]):
            badge_bg = "#065f46" if "VÙNG MUA" in w["status"] else ("#854d0e" if "THEO DÕI" in w["status"] else "#991b1b")
            badge_color = "#6ee7b7" if "VÙNG MUA" in w["status"] else ("#fde047" if "THEO DÕI" in w["status"] else "#fca5a5")
            cigar_rows += f"""
            <tr>
                <td style="font-weight: bold; color: #fbbf24; font-size: 14px;">{w['ticker']}</td>
                <td>{w['name']}</td>
                <td><strong style="color: #f8fafc;">{w['price']:,.0f} đ</strong></td>
                <td style="color: #38bdf8; font-weight: bold;">{w['pb']}x</td>
                <td style="color: #34d399; font-weight: bold;">{w['fair_value']:,.0f} đ</td>
                <td style="color: #a7f3d0;">{w['roe']}%</td>
                <td><span style="background: {badge_bg}; color: {badge_color}; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold;">{w['status']}</span></td>
            </tr>
            """

        # Stock Trade History Table
        stock_hist_rows = ""
        for t in s_sum.get("trade_history", [])[:10]:
            action_color = "#34d399" if "BUY" in t["action"] or "DEPOSIT" in t["action"] else "#f87171"
            stock_hist_rows += f"""
            <tr>
                <td style="color: #94a3b8; font-size: 12px;">{t['timestamp']}</td>
                <td style="font-weight: bold; color: #38bdf8;">{t['ticker']}</td>
                <td style="color: {action_color}; font-weight: bold;">{t['action']}</td>
                <td>{t['shares']:,}</td>
                <td>{t['price']:,.0f} đ</td>
                <td>{t['amount']:,.0f} đ</td>
                <td style="color: #cbd5e1; font-size: 13px;">{t['reason']}</td>
            </tr>
            """

        # Crypto History Table
        crypto_rows = ""
        for t in reversed(c_led.get("history", [])[-15:]):
            res_color = "#10b981" if "WIN" in t["outcome"] else "#ef4444"
            crypto_rows += f"""
            <tr>
                <td>#{t['trade_id']}</td>
                <td><strong>{t['symbol']}</strong></td>
                <td><span style="color: {'#34d399' if t['direction']=='LONG' else '#f87171'}; font-weight: bold;">{t['direction']}</span></td>
                <td>{t['setup']}</td>
                <td>{t['entry_time']}</td>
                <td>{t['entry_price']:.2f}</td>
                <td>{t['exit_price']:.2f}</td>
                <td style="color: {res_color}; font-weight: bold;">{t['outcome']}</td>
                <td style="color: {res_color}; font-weight: bold;">{t['pnl_r']:+.2f}R</td>
                <td style="color: {res_color}; font-weight: bold;">${t['dollar_pnl']:+,.2f}</td>
                <td>${t['balance_after']:,.2f}</td>
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
                body {{ font-family: 'Inter', sans-serif; background: #0b0f19; color: #f8fafc; padding: 20px; }}
                .container {{ max-width: 1440px; margin: 0 auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 16px; }}
                .title-box h1 {{ font-size: 22px; font-weight: 800; background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
                .badge-online {{ background: #065f46; color: #34d399; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 8px; }}
                .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #34d399; animation: pulse 1.5s infinite; }}
                @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
                
                /* TAB NAVIGATION */
                .tab-nav {{ display: flex; gap: 10px; margin-bottom: 24px; border-bottom: 1px solid #1e293b; padding-bottom: 12px; }}
                .tab-btn {{ background: #131d31; color: #94a3b8; border: 1px solid #1e293b; padding: 10px 20px; border-radius: 10px; font-weight: 700; font-size: 14px; cursor: pointer; transition: 0.2s; display: flex; align-items: center; gap: 8px; }}
                .tab-btn:hover {{ background: #1e293b; color: #f8fafc; }}
                .tab-btn.active {{ background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; border-color: #38bdf8; box-shadow: 0 4px 12px rgba(37,99,235,0.3); }}
                
                .tab-content {{ display: none; }}
                .tab-content.active {{ display: block; }}

                .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
                .kpi-card {{ background: #131d31; border: 1px solid #1e293b; border-radius: 12px; padding: 18px; }}
                .kpi-card .lbl {{ font-size: 12px; color: #94a3b8; font-weight: 600; text-transform: uppercase; }}
                .kpi-card .val {{ font-size: 22px; font-weight: 700; margin-top: 6px; }}
                .kpi-card .sub {{ font-size: 13px; margin-top: 4px; color: #64748b; }}

                .card {{ background: #131d31; border: 1px solid #1e293b; border-radius: 14px; padding: 20px; margin-bottom: 24px; }}
                .card h2 {{ font-size: 17px; font-weight: 700; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; }}
                table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13.5px; }}
                th {{ background: #0b1120; color: #94a3b8; padding: 12px 14px; font-weight: 600; border-bottom: 1px solid #1e293b; }}
                td {{ padding: 12px 14px; border-bottom: 1px solid #1e293b; }}
                tr:hover {{ background: #1a2744; }}
                .btn-scan {{ background: #0284c7; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 13px; }}
                .btn-scan:hover {{ opacity: 0.9; }}
                .grid-split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
                @media(max-width: 1024px) {{ .grid-split {{ grid-template-columns: 1fr; }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="title-box">
                        <h1>🚀 DUAL-QUANT MASTER TERMINAL</h1>
                        <p style="color: #94a3b8; font-size: 13px; margin-top: 4px;">Hệ Thống Forward Test 2 Trong 1: Crypto Prop Firm & Cổ Phiếu Việt Nam (Buffett Moat + Cigar Butt)</p>
                    </div>
                    <div>
                        <span class="badge-online"><span class="dot"></span> CẢ 2 ENGINE ĐANG CHẠY 24/7</span>
                    </div>
                </div>

                <!-- TAB SWITCHER -->
                <div class="tab-nav">
                    <button id="btn-tab-stock" class="tab-btn active" onclick="switchTab('tab-stock', this)">🇻🇳 CHỨNG KHOÁN VIỆT NAM (MOAT & CIGAR BUTT)</button>
                    <button id="btn-tab-crypto" class="tab-btn" onclick="switchTab('tab-crypto', this)">🤖 CRYPTO PROP FIRM (BINANCE M5)</button>
                    <button id="btn-tab-split" class="tab-btn" onclick="switchTab('tab-split', this)">📊 XEM SONG SONG CẢ HAI</button>
                </div>

                <!-- TAB 1: CHỨNG KHOÁN VIỆT NAM -->
                <div id="tab-stock" class="tab-content active">
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="lbl">Tổng Tài Sản (NAV)</div>
                            <div class="val" style="color: #38bdf8;">{s_sum['total_nav']:,.0f} đ</div>
                            <div class="sub">Vốn gốc: {s_sum['initial_capital']:,.0f} đ</div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Lợi Nhuận Tích Lũy</div>
                            <div class="val" style="color: {s_pnl_color};">{s_pnl_sign}{s_sum['total_profit']:,.0f} đ</div>
                            <div class="sub" style="color: {s_pnl_color}; font-weight: 600;">{s_pnl_sign}{s_sum['total_return_pct']}% PnL</div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Két Tiền Mặt 5%/Năm (T+0)</div>
                            <div class="val" style="color: #fbbf24;">{s_sum['cash_vault']:,.0f} đ</div>
                            <div class="sub">Tỷ trọng: <strong>{s_sum['cash_pct']}%</strong> • Lãi đã đẻ: <strong>+{s_sum['vault_interest_earned']:,.0f} đ</strong></div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Cổ Phiếu Nắm Giữ</div>
                            <div class="val" style="color: #a78bfa;">{s_sum['stock_value']:,.0f} đ</div>
                            <div class="sub">Tỷ trọng: <strong>{s_sum['equity_pct']}%</strong> ({len(s_sum['holdings'])} mã)</div>
                        </div>
                    </div>

                    <div class="card">
                        <h2>
                            <span>📦 Danh Mục Cổ Phiếu Đang Nắm Giữ</span>
                            <button class="btn-scan" onclick="triggerStockScan()">⚡ Quét Giá Ngay & Bắn Telegram</button>
                        </h2>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Mã CP</th><th>Số lượng</th><th>Giá vốn TB</th><th>Thị giá hiện tại</th><th>Giá trị thị trường</th><th>Cổ tức đã nhận</th><th>Lợi nhuận (PnL)</th><th>Luận điểm đầu tư</th>
                                    </tr>
                                </thead>
                                <tbody>{stock_rows}</tbody>
                            </table>
                        </div>
                    </div>

                    <!-- BẢNG 1: DOANH NGHIỆP VĨ ĐẠI -->
                    <div class="card" style="border-top: 3px solid #38bdf8;">
                        <h2>🏰 Bảng 1: Top Doanh Nghiệp Vĩ Đại (Quality Moat - HOSE Bluechips)</h2>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Mã CP</th><th>Tên Doanh Nghiệp</th><th>Thị giá</th><th>Giá trị Hợp lý</th><th>Vùng Mua MoS 20%</th><th>ROE (%)</th><th>P/E</th><th>Trạng Thái</th>
                                    </tr>
                                </thead>
                                <tbody>{moat_rows}</tbody>
                            </table>
                        </div>
                    </div>

                    <!-- BẢNG 2: MẨU TÀN XÌ GÀ -->
                    <div class="card" style="border-top: 3px solid #fbbf24;">
                        <h2>🚬 Bảng 2: Săn Mẩu Tàn Xì Gà Siêu Rẻ & Cổ Tức (Cigar Butt / Net-Net UPCoM/HNX)</h2>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Mã CP</th><th>Tên Doanh Nghiệp</th><th>Thị giá</th><th>Định giá P/B</th><th>Mục tiêu Thanh lý (100% NCAV)</th><th>ROE (%)</th><th>Trạng Thái</th>
                                    </tr>
                                </thead>
                                <tbody>{cigar_rows}</tbody>
                            </table>
                        </div>
                    </div>

                    <div class="card">
                        <h2>📜 Nhật Ký Lệnh Giải Ngân & Két Tiền Mặt</h2>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Thời gian</th><th>Mã CP</th><th>Hành động</th><th>Số lượng</th><th>Giá khớp</th><th>Tổng giá trị</th><th>Lý do giải ngân / Két tiền mặt</th>
                                    </tr>
                                </thead>
                                <tbody>{stock_hist_rows}</tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- TAB 2: CRYPTO PROP FIRM -->
                <div id="tab-crypto" class="tab-content">
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="lbl">Số Dư Quỹ (Balance)</div>
                            <div class="val" style="color: {c_pnl_color};">${c_led['account_balance']:,.2f}</div>
                            <div class="sub">Vốn ban đầu: ${crypto_engine.INITIAL_BALANCE:,.2f}</div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Tỷ Lệ Thắng (Win Rate)</div>
                            <div class="val" style="color: {c_wr_color};">{c_led['win_rate']:.1f}%</div>
                            <div class="sub">{c_led['wins']} Thắng / {c_led['losses']} Thua</div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Profit Factor</div>
                            <div class="val" style="color: #38bdf8;">{c_led['profit_factor']:.2f}</div>
                            <div class="sub">Tổng lệnh: {c_led['total_trades']}</div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Kỳ Vọng R (Expectancy)</div>
                            <div class="val" style="color: #a78bfa;">{c_led['expectancy_r']:+.2f}R</div>
                            <div class="sub">Risk/Trade: {crypto_engine.RISK_PER_TRADE_PCT*100}%</div>
                        </div>
                        <div class="kpi-card">
                            <div class="lbl">Max Drawdown</div>
                            <div class="val" style="color: #f87171;">{c_led['max_drawdown_pct']:.2f}%</div>
                            <div class="sub">Giới hạn Prop Firm: 10%</div>
                        </div>
                    </div>

                    <div class="card" style="border-left: 4px solid #38bdf8;">
                        <h2>⚡ Trạng Thái Vị Thế Hiện Tại ({crypto_engine.SYMBOL} - 5m)</h2>
                        <div style="padding: 8px 0; font-size: 14px;">
                            {f"<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px;'><div><strong>Setup:</strong> {c_act['setup']}</div><div><strong>Hướng:</strong> <span style='color: #34d399; font-weight: bold;'>{c_act['direction']}</span></div><div><strong>Giá vào:</strong> {c_act['entry_price']:.2f}</div><div><strong>Stop-Loss:</strong> {c_act['sl_price']:.2f}</div><div><strong>Take-Profit:</strong> {c_act['tp_price']:.2f}</div><div><strong>Rủi ro:</strong> ${c_act['risk_dollar']:,.2f}</div></div>" if c_act else "<p style='color: #94a3b8;'>💤 Hiện không có vị thế nào đang mở. Bot đang quét thị trường theo nến 5m (Phiên London 14h-18h & Phiên NY 20h-23h30).</p>"}
                        </div>
                    </div>

                    <div class="card">
                        <h2>📜 Sổ Cái Lệnh Đã Đóng (Institutional Trading Journal)</h2>
                        <div style="overflow-x: auto;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>ID</th><th>Symbol</th><th>Hướng</th><th>Chiến Lược</th><th>Thời Gian Vào</th><th>Giá Vào</th><th>Giá Đóng</th><th>Kết Quả</th><th>PnL (R)</th><th>Lãi/Lỗ ($)</th><th>Số Dư</th>
                                    </tr>
                                </thead>
                                <tbody>{crypto_rows}</tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- TAB 3: XEM SONG SONG -->
                <div id="tab-split" class="tab-content">
                    <div class="grid-split">
                        <div class="card" style="border-top: 4px solid #38bdf8;">
                            <h2><span>🇻🇳 CHỨNG KHOÁN VN (NAV: {s_sum['total_nav']/1e6:,.1f}Tr)</span></h2>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">Két 5%: <strong>{s_sum['cash_vault']/1e6:,.1f}Tr</strong> • Cổ phiếu: <strong>{len(s_sum['holdings'])} mã</strong></p>
                            <div style="overflow-x: auto;">
                                <table>
                                    <thead><tr><th>Mã CP</th><th>Thị giá</th><th>MoS 20%</th><th>Trạng thái</th></tr></thead>
                                    <tbody>{moat_rows[:1500]}</tbody>
                                </table>
                            </div>
                        </div>
                        <div class="card" style="border-top: 4px solid #a855f7;">
                            <h2><span>🤖 CRYPTO PROP FIRM (${c_led['account_balance']:,.2f})</span></h2>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">Win Rate: <strong>{c_led['win_rate']:.1f}%</strong> • Profit Factor: <strong>{c_led['profit_factor']:.2f}</strong></p>
                            <div style="overflow-x: auto;">
                                <table>
                                    <thead><tr><th>ID</th><th>Setup</th><th>Kết quả</th><th>PnL</th></tr></thead>
                                    <tbody>{crypto_rows[:1500]}</tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                function switchTab(tabId, el) {{
                    document.querySelectorAll('.tab-btn').forEach(function(btn) {{
                        btn.classList.remove('active');
                    }});
                    document.querySelectorAll('.tab-content').forEach(function(content) {{
                        content.classList.remove('active');
                    }});
                    
                    var target = document.getElementById(tabId);
                    if (target) target.classList.add('active');
                    if (el) {{
                        el.classList.add('active');
                    }} else {{
                        var b = document.getElementById('btn-' + tabId);
                        if (b) b.classList.add('active');
                    }}
                }}

                // Check URL params on load
                window.addEventListener('DOMContentLoaded', function() {{
                    var urlParams = new URLSearchParams(window.location.search);
                    var tab = urlParams.get('tab');
                    if (tab === 'crypto') switchTab('tab-crypto');
                    else if (tab === 'split') switchTab('tab-split');
                    else if (tab === 'stock') switchTab('tab-stock');
                }});

                function triggerStockScan() {{
                    fetch('/api/stock/scan')
                        .then(function(r) {{ return r.json(); }})
                        .then(function(d) {{
                            alert('Đã kích hoạt quét thị trường Cổ Phiếu VN và gửi bản tin về Telegram @Lastsmokewbbot!');
                            setTimeout(function() {{ location.reload(); }}, 2000);
                        }});
                }}

                // Tự động làm mới trang mỗi 30 giây
                setInterval(function() {{ location.reload(); }}, 30000);
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
    print(" KHỞI ĐỘNG HỆ THỐNG KÉP: CRYPTO PROP FIRM & VN STOCK BUFFETT SNIPER")
    print("=================================================================")

    # 1. Khởi chạy luồng Crypto Prop Firm Engine
    crypto_engine.load_ledger()
    crypto_engine.recalculate_metrics()
    t_crypto = threading.Thread(target=crypto_engine.main_loop, daemon=True)
    t_crypto.start()
    print("[THREAD 1] Crypto Prop Firm Engine đã kích hoạt.")

    # 2. Khởi chạy luồng Vietnam Stock Buffett Sniper Engine
    t_stock = threading.Thread(target=stock_engine.background_scheduler, daemon=True)
    t_stock.start()
    print("[THREAD 2] Vietnam Stock Buffett Sniper Engine đã kích hoạt.")

    # 3. Khởi chạy luồng Web Dashboard Master
    start_master_web_server()
