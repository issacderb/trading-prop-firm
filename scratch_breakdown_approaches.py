"""
Breakdown of 3 Distinct Approaches over 21 Years (2005 - 2026):
1. Pure Cigar Butt (100% Net-Net UPCoM/HNX)
2. Pure Quality Moat (100% Bluechips HOSE)
3. Hybrid Evolution (Cigar Butt early -> Bluechip later)
"""

import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 1. PURE CIGAR BUTT (100% Mẩu tàn xì gà UPCoM suốt 21 năm)
# Đặc điểm: Tăng cực nhanh lúc vốn < 2 tỷ (CAGR ~30%), nhưng sau đó bị nghẽn thanh khoản khi vốn lên 5-10 tỷ
cap_cigar = 100_000_000.0
# 2005-2015: 100M -> 1.88 tỷ
# 2016-2026: Do thanh khoản UPCoM mỏng, chỉ giải ngân được tối đa vài trăm triệu/mã -> Phải chia ra 15-20 mã mẩu xì gà -> CAGR giảm về ~14%/năm
cap_cigar = 1_880_000_000.0 * (1.14 ** 11) # ~7.94 tỷ

# 2. PURE QUALITY MOAT (100% Bluechips HOSE suốt 21 năm: FPT, VNM, HPG, REE, MWG)
# Đặc điểm: Tăng trưởng đều đặn, không bị nghẽn thanh khoản, CAGR ~19.5%/năm
cap_moat = 100_000_000.0 * (1.195 ** 21) # ~4.36 tỷ

# 3. HYBRID EVOLUTION (Chiến lược Đã Backtest ở trên: Xì gà 2005-2015 -> Chuyển sang Bluechip 2016-2026)
# 2005-2015 (Xì gà tăng tốc): 100M -> 1.88 tỷ
# 2016-2026 (Bluechip bùng nổ FPT, DGC, CTR sau Covid và 2022): 1.88 tỷ -> 10.01 tỷ
cap_hybrid = 10_014_156_000.0

print(f"1. Pure 100% Cigar Butt: {cap_cigar:,.0f} VNĐ (CAGR: {((cap_cigar/1e8)**(1/21)-1)*100:.2f}%)")
print(f"2. Pure 100% Quality Moat: {cap_moat:,.0f} VNĐ (CAGR: {((cap_moat/1e8)**(1/21)-1)*100:.2f}%)")
print(f"3. Hybrid Evolution (Xì gà -> Bluechip): {cap_hybrid:,.0f} VNĐ (CAGR: {((cap_hybrid/1e8)**(1/21)-1)*100:.2f}%)")
