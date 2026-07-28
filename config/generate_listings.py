"""
🏗️ PROCEDURAL DATA GENERATOR (Role 1: Product Architect)

Sinh bộ dữ liệu bất động sản cho thuê tại Hà Nội ra file `config/listings.txt`
(định dạng CSV chuẩn, có header ghi rõ đơn vị).

═══════════════════════════════════════════════════════════════════════════
 TRIẾT LÝ THIẾT KẾ: DỮ LIỆU PHẢI CÓ CẤU TRÚC, KHÔNG PHẢI NGẪU NHIÊN THUẦN
═══════════════════════════════════════════════════════════════════════════
Nếu mọi cột đều random độc lập, Agent không có gì để "suy luận" — mọi câu hỏi
đều quy về lọc một chiều. Vì vậy bộ sinh này cài sẵn 3 mối tương quan:

  1. GIÁ ⟷ DIỆN TÍCH   : căn đắt có xu hướng rộng hơn (có nhiễu, nên vẫn tồn tại
                          căn nhỏ mà đắt và căn rộng mà rẻ — tạo edge case tự nhiên).
  2. GIÁ ⟷ TIỆN ÍCH    : mỗi tiện ích có tỉ lệ riêng, nội suy tuyến tính giữa
                          "tỉ lệ ở căn rẻ nhất" và "tỉ lệ ở căn đắt nhất".
  3. GIÁ ⟷ QUẬN        : quận trung tâm (Hoàn Kiếm, Tây Hồ, Ba Đình) hút các căn
                          đắt; quận vùng ven (Hà Đông, Hoàng Mai) hút các căn rẻ.

Nhờ vậy các câu hỏi kiểu *"tìm căn 100m2 ở Tây Hồ có bể bơi gần đó"* mới thực sự
cần lọc đa điều kiện thay vì tra một cột.

═══════════════════════════════════════════════════════════════════════════
 CÁCH DÙNG
═══════════════════════════════════════════════════════════════════════════
    python config/generate_listings.py                      # 10.000 căn, seed mặc định
    python config/generate_listings.py --count 500          # đổi số lượng
    python config/generate_listings.py --seed 42            # đổi seed -> bộ dữ liệu khác
    python config/generate_listings.py --stats              # in bảng thống kê kiểm chứng

⚠️ Dữ liệu sinh ra là DETERMINISTIC theo seed: cùng seed + cùng count luôn cho ra
file y hệt. Điều này quan trọng để cả nhóm cùng chạy test trên một bộ dữ liệu,
và để test case có số kết quả kỳ vọng ổn định.
"""

import argparse
import csv
import os
import random
import sys
import uuid

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# ⚙️ THAM SỐ CẤU HÌNH
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_COUNT = 10_000
DEFAULT_SEED = 20260728

PRICE_MIN = 1_000_000       # 1 triệu VNĐ/tháng
PRICE_MAX = 20_000_000      # 20 triệu VNĐ/tháng
PRICE_ROUND_TO = 100_000    # làm tròn cho giống giá rao thật

AREA_MIN = 20               # m2
AREA_MAX = 200              # m2
# Độ nhiễu diện tích. Đã hiệu chỉnh: sigma=18 cho r≈0.83 — quá chặt, KHÔNG sinh ra
# căn nào "nhỏ mà đắt". sigma=30 hạ r về ~0.65, sát thị trường thuê thật (vị trí
# và nội thất ảnh hưởng giá mạnh không kém diện tích) và tạo đủ ngoại lệ để test.
AREA_NOISE_SIGMA = 30

# 12 quận nội thành Hà Nội.
# `prestige` (0-1) mô tả mức "trung tâm/đắt đỏ", dùng để ghép quận với mức giá.
DISTRICTS = {
    "Hoàn Kiếm":    {"prestige": 0.95, "streets": ["Hàng Bài", "Lý Thường Kiệt", "Trần Hưng Đạo", "Hàng Bông"]},
    "Tây Hồ":       {"prestige": 0.90, "streets": ["Quảng An", "Xuân Diệu", "Lạc Long Quân", "Âu Cơ"]},
    "Ba Đình":      {"prestige": 0.85, "streets": ["Kim Mã", "Đội Cấn", "Liễu Giai", "Nguyễn Thái Học"]},
    "Cầu Giấy":     {"prestige": 0.70, "streets": ["Xuân Thủy", "Trần Duy Hưng", "Nguyễn Khánh Toàn", "Dịch Vọng Hậu"]},
    "Đống Đa":      {"prestige": 0.62, "streets": ["Chùa Bộc", "Tây Sơn", "Láng Hạ", "Xã Đàn"]},
    "Hai Bà Trưng": {"prestige": 0.60, "streets": ["Bạch Mai", "Minh Khai", "Kim Ngưu", "Trần Khát Chân"]},
    "Nam Từ Liêm":  {"prestige": 0.58, "streets": ["Mỹ Đình", "Lê Đức Thọ", "Phạm Hùng", "Đại Mỗ"]},
    "Thanh Xuân":   {"prestige": 0.55, "streets": ["Nguyễn Trãi", "Khương Trung", "Lê Văn Lương", "Nguyễn Tuân"]},
    "Bắc Từ Liêm":  {"prestige": 0.45, "streets": ["Cổ Nhuế", "Phạm Văn Đồng", "Xuân Đỉnh", "Đông Ngạc"]},
    "Long Biên":    {"prestige": 0.42, "streets": ["Ngọc Lâm", "Nguyễn Văn Cừ", "Việt Hưng", "Sài Đồng"]},
    "Hoàng Mai":    {"prestige": 0.40, "streets": ["Linh Đàm", "Định Công", "Tân Mai", "Giáp Bát"]},
    "Hà Đông":      {"prestige": 0.35, "streets": ["Quang Trung", "Văn Quán", "Mộ Lao", "Yên Nghĩa"]},
}

# ─────────────────────────────────────────────────────────────────────────
# 🏢 BẢNG TỈ LỆ TIỆN ÍCH XUNG QUANH
# (rate_re, rate_dat) = xác suất xuất hiện ở căn RẺ NHẤT và ở căn ĐẮT NHẤT.
# Giá trị thực tế được nội suy tuyến tính theo mức giá của từng căn.
#
# 📌 Lưu ý "Chợ dân sinh" là tiện ích DUY NHẤT có tỉ lệ NGHỊCH với giá.
#    Đây là lựa chọn có chủ đích để dữ liệu giống đời thật: khu bình dân
#    nhiều chợ truyền thống, khu cao cấp thay bằng siêu thị / TTTM.
#    Nó cũng tạo ra edge case thú vị: "căn đắt tiền có chợ dân sinh gần đó"
#    là truy vấn hiếm -> test được khả năng Agent xử lý kết quả rỗng/ít.
# ─────────────────────────────────────────────────────────────────────────
AMENITIES = {
    "Chợ dân sinh":          (0.78, 0.32),   # ← nghịch với giá (có chủ đích)
    "Trường học":            (0.50, 0.82),
    "Siêu thị":              (0.30, 0.88),
    "Bến xe buýt":           (0.60, 0.80),
    "Công viên":             (0.18, 0.72),
    "Bệnh viện":             (0.22, 0.58),
    "Bãi đỗ xe ô tô":        (0.12, 0.90),
    "Phòng gym":             (0.08, 0.88),
    "Khu vui chơi trẻ em":   (0.10, 0.70),
    "Trung tâm thương mại":  (0.06, 0.80),
    "Bể bơi":                (0.02, 0.75),
    "Rạp chiếu phim":        (0.04, 0.62),
    "Sân tennis":            (0.01, 0.42),
}

AMENITY_SEPARATOR = "; "   # ngăn cách nhiều tiện ích trong cùng một ô CSV

CSV_HEADER = [
    "ma_can",              # UUID định danh căn hộ
    "dia_chi",             # số nhà + chữ cái + tên đường
    "quan",                # quận nội thành Hà Nội
    "gia_thue_vnd",        # đơn vị: VNĐ/tháng (trong dữ liệu chỉ ghi số)
    "dien_tich_m2",        # đơn vị: mét vuông (trong dữ liệu chỉ ghi số)
    "tien_ich_xung_quanh", # danh sách tiện ích, ngăn bằng "; "
]


# ═══════════════════════════════════════════════════════════════════════════
# 🎲 CÁC HÀM SINH TỪNG TRƯỜNG
# ═══════════════════════════════════════════════════════════════════════════

def gen_price(rng: random.Random) -> tuple:
    """Sinh giá thuê. Trả về (giá đã làm tròn, p) với p là vị trí tương đối 0..1.

    Dùng phân phối Beta(2, 3.5) lệch về phía rẻ — phản ánh thị trường thật:
    căn bình dân nhiều hơn căn cao cấp. Nếu dùng uniform, dữ liệu sẽ có quá
    nhiều căn 15-20 triệu một cách phi thực tế.
    """
    p = rng.betavariate(2.0, 3.5)
    raw = PRICE_MIN + p * (PRICE_MAX - PRICE_MIN)
    price = int(round(raw / PRICE_ROUND_TO) * PRICE_ROUND_TO)
    return max(PRICE_MIN, min(PRICE_MAX, price)), p


def gen_area(rng: random.Random, p: float) -> int:
    """Sinh diện tích tương quan thuận với giá.

    mu đi từ ~25m2 (căn rẻ nhất) tới ~165m2 (căn đắt nhất), cộng nhiễu Gauss.
    Nhiễu là CHỦ ĐÍCH: nó tạo ra những căn "nhỏ mà đắt" (vị trí đẹp) và
    "rộng mà rẻ" (vùng ven) — chính là các edge case đáng test.
    """
    mu = 25 + p * 140
    area = rng.gauss(mu, AREA_NOISE_SIGMA)
    return int(max(AREA_MIN, min(AREA_MAX, round(area))))


def gen_district(rng: random.Random, p: float) -> str:
    """Chọn quận sao cho mức giá khớp với độ 'trung tâm' của quận.

    Trọng số = 0.12 + (1 - |prestige - p|)^3. Số hạng 0.12 giữ cho MỌI quận đều
    có cơ hội xuất hiện ở MỌI mức giá (thị trường thật luôn có ngoại lệ),
    còn lũy thừa 3 làm cho việc ghép cặp đủ rõ để thống kê nhìn thấy được.
    """
    names, weights = [], []
    for name, info in DISTRICTS.items():
        names.append(name)
        weights.append(0.12 + (1 - abs(info["prestige"] - p)) ** 3)
    return rng.choices(names, weights=weights, k=1)[0]


def gen_address(rng: random.Random, district: str) -> str:
    """Sinh địa chỉ dạng '302A Xuân Thủy' — số nhà + chữ cái + tên đường của quận."""
    number = rng.randint(1, 999)
    letter = rng.choice("ABCDE")
    street = rng.choice(DISTRICTS[district]["streets"])
    return f"{number}{letter} {street}"


def gen_amenities(rng: random.Random, p: float) -> list:
    """Tung xúc xắc độc lập cho từng tiện ích, với tỉ lệ nội suy theo mức giá p."""
    picked = []
    for name, (rate_cheap, rate_rich) in AMENITIES.items():
        rate = rate_cheap + (rate_rich - rate_cheap) * p
        if rng.random() < rate:
            picked.append(name)
    return picked


def generate(count: int, seed: int) -> list:
    """Sinh `count` bản ghi, deterministic theo `seed`."""
    rng = random.Random(seed)
    rows = []
    for _ in range(count):
        price, p = gen_price(rng)
        district = gen_district(rng, p)
        rows.append({
            "ma_can": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
            "dia_chi": gen_address(rng, district),
            "quan": district,
            "gia_thue_vnd": price,
            "dien_tich_m2": gen_area(rng, p),
            "tien_ich_xung_quanh": AMENITY_SEPARATOR.join(gen_amenities(rng, p)),
        })
    return rows


def write_csv(rows: list, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # newline="" là bắt buộc với module csv để không sinh dòng trống thừa trên Windows
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════
# 📊 KIỂM CHỨNG THỐNG KÊ — chứng minh tương quan là THẬT, không phải giả định
# ═══════════════════════════════════════════════════════════════════════════

def print_stats(rows: list) -> None:
    n = len(rows)
    prices = [r["gia_thue_vnd"] for r in rows]
    areas = [r["dien_tich_m2"] for r in rows]

    # Hệ số tương quan Pearson giữa giá và diện tích
    mp, ma = sum(prices) / n, sum(areas) / n
    cov = sum((prices[i] - mp) * (areas[i] - ma) for i in range(n))
    sp = sum((x - mp) ** 2 for x in prices) ** 0.5
    sa = sum((x - ma) ** 2 for x in areas) ** 0.5
    corr = cov / (sp * sa) if sp and sa else 0

    print("=" * 78)
    print(f"📊 THỐNG KÊ KIỂM CHỨNG — {n:,} bản ghi")
    print("=" * 78)
    print(f"Giá thuê      : {min(prices):,} → {max(prices):,} VNĐ/tháng (TB {int(mp):,})")
    print(f"Diện tích     : {min(areas)} → {max(areas)} m2 (TB {ma:.1f})")
    print(f"Tương quan giá ⟷ diện tích (Pearson r) = {corr:.3f}")
    print("   → r dương và đủ lớn nghĩa là 'căn đắt thường rộng hơn' ĐÃ được cài đúng.")

    # Chia 4 nhóm giá đều nhau để soi tỉ lệ tiện ích
    ordered = sorted(rows, key=lambda r: r["gia_thue_vnd"])
    q = n // 4
    groups = [("Rẻ nhất  ", ordered[:q]), ("Thấp-TB  ", ordered[q:2 * q]),
              ("TB-Cao   ", ordered[2 * q:3 * q]), ("Đắt nhất ", ordered[3 * q:])]

    print("\n" + "-" * 78)
    print("TỈ LỆ XUẤT HIỆN TIỆN ÍCH THEO NHÓM GIÁ (%)")
    print("-" * 78)
    print(f"{'Tiện ích':<24}{'Rẻ nhất':>11}{'Thấp-TB':>11}{'TB-Cao':>11}{'Đắt nhất':>11}   Xu hướng")
    print("-" * 78)
    for amenity in AMENITIES:
        pcts = []
        for _, grp in groups:
            hits = sum(1 for r in grp if amenity in r["tien_ich_xung_quanh"].split(AMENITY_SEPARATOR))
            pcts.append(100 * hits / len(grp))
        trend = "📈 thuận" if pcts[-1] > pcts[0] + 5 else ("📉 nghịch" if pcts[-1] < pcts[0] - 5 else "➖ phẳng")
        print(f"{amenity:<24}" + "".join(f"{p:>10.1f}%" for p in pcts) + f"   {trend}")

    print("\n" + "-" * 78)
    print("PHÂN BỐ THEO QUẬN (giá trung bình tăng dần)")
    print("-" * 78)
    by_dist = {}
    for r in rows:
        by_dist.setdefault(r["quan"], []).append(r)
    print(f"{'Quận':<16}{'Số căn':>9}{'Giá TB (VNĐ)':>16}{'DT TB (m2)':>13}")
    print("-" * 78)
    for name, grp in sorted(by_dist.items(), key=lambda kv: sum(r["gia_thue_vnd"] for r in kv[1]) / len(kv[1])):
        avg_p = sum(r["gia_thue_vnd"] for r in grp) / len(grp)
        avg_a = sum(r["dien_tich_m2"] for r in grp) / len(grp)
        print(f"{name:<16}{len(grp):>9,}{int(avg_p):>16,}{avg_a:>13.1f}")
    print("=" * 78)


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Sinh dữ liệu bất động sản cho thuê (Lab 3).")
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"Số bản ghi (mặc định {DEFAULT_COUNT})")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed ngẫu nhiên (mặc định {DEFAULT_SEED})")
    ap.add_argument("--output", default=None, help="Đường dẫn file xuất (mặc định config/listings.txt)")
    ap.add_argument("--stats", action="store_true", help="In bảng thống kê kiểm chứng")
    args = ap.parse_args()

    out = args.output or os.path.join(os.path.dirname(os.path.abspath(__file__)), "listings.txt")

    rows = generate(args.count, args.seed)
    write_csv(rows, out)

    size_kb = os.path.getsize(out) / 1024
    print(f"✅ Đã sinh {len(rows):,} bản ghi -> {out}  ({size_kb:,.0f} KB)")
    print(f"   Seed = {args.seed} (chạy lại cùng seed sẽ cho file y hệt)")

    if args.stats:
        print()
        print_stats(rows)
