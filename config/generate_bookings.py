"""
📅 BOOKING SEED GENERATOR (Role 1: Product Architect)

Sinh file `config/bookings.txt` — các lịch hẹn xem nhà ĐÃ CÓ SẴN trong hệ thống.

═══════════════════════════════════════════════════════════════════════════
 TẠI SAO CẦN SEED LỊCH CÓ SẴN?
═══════════════════════════════════════════════════════════════════════════
Nếu bookings.txt rỗng, mọi khung giờ luôn trống và tool check_viewing_slots
sẽ luôn trả về cả 10 khung — chẳng chứng minh được điều gì. Có lịch sẵn thì
Agent mới thật sự phải ĐỌC dữ liệu để biết khung nào bận, và ta mới test được
tình huống "căn này kín lịch ngày đó, phải đổi ngày".

Seed được tập trung vào MỘT SỐ ÍT CĂN (thay vì rải đều 10.000 căn) để xác suất
gặp lịch bận đủ cao khi demo. Trong đó có vài căn bị đặt KÍN CẢ NGÀY để test
nhánh "hết chỗ".

Cách dùng:
    python config/generate_bookings.py                 # seed mặc định (GHI ĐÈ file cũ)
    python config/generate_bookings.py --listings 80   # số căn được seed lịch
    python config/generate_bookings.py --seed 99       # bộ lịch khác

⚠️ Script LUÔN ghi đè toàn bộ bookings.txt. Mọi lịch khách đã đặt qua chat sẽ mất.
⚠️ Lịch được sinh TƯƠNG ĐỐI so với ngày chạy script (từ ngày mai tới +14 ngày).
   Nếu để lâu quá 14 ngày, seed sẽ hết hạn — chạy lại script là xong.
"""

import argparse
import csv
import os
import random
import sys
from datetime import datetime, timedelta

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
LISTINGS_PATH = os.path.join(_HERE, "listings.txt")
BOOKINGS_PATH = os.path.join(_HERE, "bookings.txt")

# ⚠️ Phải khớp với cấu hình trong src/tools.py
WORK_START_HOUR = 8
WORK_END_HOUR = 17
SLOT_HOURS = [f"{h:02d}:00" for h in range(WORK_START_HOUR, WORK_END_HOUR + 1)]
MAX_DAYS_AHEAD = 14

HEADER = ["ma_dat_lich", "ma_can", "ngay", "gio",
          "ten_khach", "so_dien_thoai", "thoi_diem_tao"]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô"]
DEM = ["Văn", "Thị", "Hữu", "Đức", "Minh", "Thanh", "Quang", "Ngọc"]
TEN = ["An", "Bình", "Chi", "Dũng", "Giang", "Hà", "Khánh", "Linh",
       "Mai", "Nam", "Phong", "Quân", "Sơn", "Trang", "Vinh"]


def rand_name(rng):
    return f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"


def rand_phone(rng):
    return "0" + rng.choice(["9", "8", "7", "3", "5"]) + "".join(
        str(rng.randint(0, 9)) for _ in range(8))


def generate(n_listings: int, seed: int):
    if not os.path.exists(LISTINGS_PATH):
        print(f"❌ Chưa có {LISTINGS_PATH}. Chạy trước: python config/generate_listings.py")
        sys.exit(1)

    with open(LISTINGS_PATH, encoding="utf-8") as f:
        all_ids = [r["ma_can"] for r in csv.DictReader(f)]

    rng = random.Random(seed)
    today = datetime.now().date()
    picked = rng.sample(all_ids, min(n_listings, len(all_ids)))

    rows = []
    # 3 căn đầu tiên: cố tình đặt KÍN cả ngày mai -> test nhánh "hết chỗ"
    for ma_can in picked[:3]:
        d = (today + timedelta(days=1)).isoformat()
        for gio in SLOT_HOURS:
            rows.append((ma_can, d, gio))

    # Các căn còn lại: đặt lác đác 1-5 khung mỗi căn, rải trong 14 ngày tới
    for ma_can in picked[3:]:
        for _ in range(rng.randint(1, 5)):
            d = (today + timedelta(days=rng.randint(1, MAX_DAYS_AHEAD))).isoformat()
            rows.append((ma_can, d, rng.choice(SLOT_HOURS)))

    # Khử trùng lặp (cùng căn + cùng ngày + cùng giờ)
    seen, unique = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for i, (ma_can, ngay, gio) in enumerate(unique, 1):
        records.append({
            "ma_dat_lich": f"BK{i:05d}",
            "ma_can": ma_can,
            "ngay": ngay,
            "gio": gio,
            "ten_khach": rand_name(rng),
            "so_dien_thoai": rand_phone(rng),
            "thoi_diem_tao": now,
        })
    return records, picked[:3]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Sinh lịch hẹn xem nhà có sẵn (Lab 3).")
    ap.add_argument("--listings", type=int, default=40, help="Số căn được seed lịch (mặc định 40)")
    ap.add_argument("--seed", type=int, default=20260728, help="Seed ngẫu nhiên")
    args = ap.parse_args()

    # Script luôn GHI ĐÈ toàn bộ file (mode "w"), không cần cờ --reset riêng.
    if os.path.exists(BOOKINGS_PATH):
        print(f"⚠️  {BOOKINGS_PATH} đã tồn tại và sẽ bị ghi đè "
              f"(mọi lịch khách đặt trong chat sẽ mất).")

    records, full_ids = generate(args.listings, args.seed)

    with open(BOOKINGS_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(records)

    print(f"✅ Đã sinh {len(records):,} lịch hẹn -> {BOOKINGS_PATH}")
    print(f"   Khung giờ: {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00 (giờ tròn, {len(SLOT_HOURS)} khung/ngày)")
    print(f"\n🔴 3 căn bị đặt KÍN LỊCH ngày mai ({(datetime.now().date()+timedelta(days=1)).isoformat()}) "
          f"— dùng để test nhánh 'hết chỗ':")
    for i in full_ids:
        print(f"   {i}")
