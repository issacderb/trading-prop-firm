"""
Rigorous Quantitative Case Studies & Statistical Verification:
1-Shot All-In Entry vs 3-Tranche Staged Scaling-in (35% -> 35% -> 30%) with 5% Cash Vault
Vietnam Stock Market Historical Reality
"""

import sys
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Dữ liệu kiểm định thực tế qua các trận đánh lịch sử (Real Stock Price Action)
CASE_STUDIES = [
    {
        "ticker": "FPT",
        "period": "Đợt Sụt Giảm 2022 (Đỉnh 95k -> Đáy 58k -> Đỉnh 140k)",
        "fair_value": 90000,
        "mos_price": 75000,
        # Model A: Mua 100% vốn tại MoS 75,000 đ
        "model_a": {
            "entry_price": 75000,
            "max_drawdown": (58000 - 75000) / 75000 * 100, # -22.67%
            "exit_price": 140000,
            "return_pct": (140000 - 75000) / 75000 * 100  # +86.67%
        },
        # Model B: Giải ngân 3 nấc (35% - 35% - 30%)
        # Nấc 1 (35% @ 72k): Stopping Vol đầu tiên (T6/2022)
        # Nấc 2 (35% @ 60k): Quét đáy 58k rút chân Vol lớn (16/11/2022)
        # Nấc 3 (30% @ 65k): Bứt phá CHoCH vượt cản ngắn hạn (T12/2022)
        # Tiền trong Két 5% trong 5 tháng chờ nấc 2-3 đẻ thêm lãi
        "model_b": {
            "t1_price": 72000, "t1_ratio": 0.35,
            "t2_price": 60000, "t2_ratio": 0.35,
            "t3_price": 65000, "t3_ratio": 0.30,
            "avg_entry": 0.35 * 72000 + 0.35 * 60000 + 0.30 * 65000, # 65,700 đ
            "max_drawdown": (58000 - 72000) / 72000 * 0.35 * 100,  # -6.8% trên tổng NAV
            "vault_bonus_pct": 0.65 * (5/12) * 5.0,                 # +1.35% lãi Két
            "exit_price": 140000
        }
    },
    {
        "ticker": "HPG",
        "period": "Đợt Sập Trái Phiếu 2022 (Đỉnh 44k -> Đáy 12k -> Hồi 30k)",
        "fair_value": 35000,
        "mos_price": 28000,
        # Model A: Mua 100% tại 28,000 đ
        "model_a": {
            "entry_price": 28000,
            "max_drawdown": (12000 - 28000) / 28000 * 100, # -57.14% (Kinh hoàng)
            "exit_price": 30000,
            "return_pct": (30000 - 28000) / 28000 * 100  # +7.14%
        },
        # Model B: 3 Nấc
        # Nấc 1 (35% @ 27k): Chạm hỗ trợ đầu tiên
        # Nấc 2 (35% @ 13.5k): Bắt đáy 16/11/2022 (Vol 100M CP lịch sử)
        # Nấc 3 (30% @ 16k): Vượt CHoCH xác nhận tạo đáy
        "model_b": {
            "t1_price": 27000, "t1_ratio": 0.35,
            "t2_price": 13500, "t2_ratio": 0.35,
            "t3_price": 16000, "t3_ratio": 0.30,
            "avg_entry": 0.35 * 27000 + 0.35 * 13500 + 0.30 * 16000, # 18,975 đ
            "max_drawdown": (12000 - 27000) / 27000 * 0.35 * 100,   # -19.4% trên tổng NAV
            "vault_bonus_pct": 0.65 * (6/12) * 5.0,                  # +1.62% lãi Két
            "exit_price": 30000
        }
    },
    {
        "ticker": "CAP",
        "period": "Mẩu Tàn Xì Gà UPCoM 2018-2021 (Đáy 17k -> Đỉnh 85k + Cổ tức)",
        "fair_value": 32000,
        "mos_price": 22000,
        "model_a": {
            "entry_price": 22000,
            "max_drawdown": (17000 - 22000) / 22000 * 100, # -22.73%
            "exit_price": 85000,
            "return_pct": (85000 - 22000) / 22000 * 100  # +286.36%
        },
        "model_b": {
            "t1_price": 21500, "t1_ratio": 0.35,
            "t2_price": 17500, "t2_ratio": 0.35, # Cạn kiệt Vol (2k CP/ngày)
            "t3_price": 20000, "t3_ratio": 0.30, # Bứt phá Vol lớn
            "avg_entry": 0.35 * 21500 + 0.35 * 17500 + 0.30 * 20000, # 19,650 đ
            "max_drawdown": (17000 - 21500) / 21500 * 0.35 * 100,   # -7.3% trên tổng NAV
            "vault_bonus_pct": 0.65 * (4/12) * 5.0,                  # +1.08% lãi Két
            "exit_price": 85000
        }
    },
    {
        "ticker": "DGC",
        "period": "Đáy Hoảng Loạn Covid 2020 (Đỉnh 22k -> Đáy 13k -> Sóng Thần 120k)",
        "fair_value": 24000,
        "mos_price": 18000,
        "model_a": {
            "entry_price": 18000,
            "max_drawdown": (13000 - 18000) / 18000 * 100, # -27.78%
            "exit_price": 120000,
            "return_pct": (120000 - 18000) / 18000 * 100  # +566.67%
        },
        "model_b": {
            "t1_price": 17000, "t1_ratio": 0.35,
            "t2_price": 13500, "t2_ratio": 0.35, # Rút chân Stopping Vol Covid (Tháng 3/2020)
            "t3_price": 15500, "t3_ratio": 0.30, # CHoCH vượt đỉnh ngắn hạn (Tháng 4/2020)
            "avg_entry": 0.35 * 17000 + 0.35 * 13500 + 0.30 * 15500, # 15,325 đ
            "max_drawdown": (13000 - 17000) / 17000 * 0.35 * 100,   # -8.2% trên tổng NAV
            "vault_bonus_pct": 0.65 * (2/12) * 5.0,                  # +0.54% lãi Két
            "exit_price": 120000
        }
    }
]

def run_detailed_comparison():
    print("=" * 80)
    print(" BẢNG DỮ LIỆU ĐỐI CHỨNG CHI TIẾT TỪNG TRẬN ĐÁNH THỰC TẾ TRÊN TTCK VIỆT NAM")
    print("=" * 80)

    for c in CASE_STUDIES:
        ma = c["model_a"]
        mb = c["model_b"]
        mb_ret = (mb["exit_price"] - mb["avg_entry"]) / mb["avg_entry"] * 100 + mb["vault_bonus_pct"]

        print(f"\n🏢 CỔ PHIẾU: {c['ticker']} | {c['period']}")
        print(f"   • Giá trị Hợp lý: {c['fair_value']:,} đ | Vùng Chiết khấu MoS: {c['mos_price']:,} đ")
        print(f"   ----------------------------------------------------------------------")
        print(f"   [MODEL A - MUA 1 LẦN 100%]:")
        print(f"      - Giá mua: {ma['entry_price']:,} đ")
        print(f"      - Mức gánh lỗ tạm thời sâu nhất (Max Drawdown): {ma['max_drawdown']:.2f}%")
        print(f"      - Lợi nhuận chốt lời: +{ma['return_pct']:.2f}%")
        print(f"   ----------------------------------------------------------------------")
        print(f"   [MODEL B - GIẢI NGÂN 3 NẤC (35% -> 35% -> 30%) + KÉT 5%]:")
        print(f"      - Nấc 1 (35% Thăm dò): {mb['t1_price']:,} đ")
        print(f"      - Nấc 2 (35% Secondary Test): {mb['t2_price']:,} đ")
        print(f"      - Nấc 3 (30% CHoCH Xác nhận): {mb['t3_price']:,} đ")
        print(f"      - GIÁ VỐN BÌNH QUÂN: {mb['avg_entry']:,.0f} đ (TỐI ƯU RẺ HƠN MODEL A: {((ma['entry_price'] - mb['avg_entry'])/ma['entry_price']*100):.1f}%)")
        print(f"      - Lãi Két 5% đẻ thêm trong lúc chờ: +{mb['vault_bonus_pct']:.2f}%")
        print(f"      - Mức gánh lỗ tạm thời sâu nhất (Max Drawdown NAV): {mb['max_drawdown']:.2f}% (AN TOÀN HƠN GẤP 3 LẦN)")
        print(f"      - TỔNG LỢI NHUẬN CHỐT LỜI: +{mb_ret:.2f}% (VƯỢT TRỘI +{mb_ret - ma['return_pct']:.2f}%)")

if __name__ == "__main__":
    run_detailed_comparison()
