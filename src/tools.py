"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)

CHỦ ĐỀ NHÓM: 🏠 Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê (Đề tài #10)

═══════════════════════════════════════════════════════════════════════════
NGUỒN DỮ LIỆU — KHÔNG CÒN BẤT KỲ DỮ LIỆU HARDCODE NÀO
═══════════════════════════════════════════════════════════════════════════
  • config/listings.txt  (CHỈ ĐỌC)  — 10.000 căn hộ, sinh bởi generate_listings.py
  • config/bookings.txt  (ĐỌC/GHI)  — lịch hẹn xem nhà, cập nhật khi khách đặt

Danh sách quận và danh sách tiện ích hợp lệ đều được SUY RA TỪ DỮ LIỆU THẬT
lúc nạp file, không khai báo tay. Nhờ vậy khi Role 1 sinh lại dữ liệu với seed
khác, thông báo lỗi của tool vẫn tự động khớp.

═══════════════════════════════════════════════════════════════════════════
NGUYÊN TẮC BẤT BIẾN CỦA TOOL (Tool Contract)
═══════════════════════════════════════════════════════════════════════════
1. Tool KHÔNG BAO GIỜ raise Exception ra ngoài. Mọi lỗi trả về CHUỖI bắt đầu
   bằng "LỖI:" kèm DANH SÁCH GIÁ TRỊ HỢP LỆ để Agent tự sửa thay vì đoán mò.
2. Phân biệt rõ hai thứ khác nhau về bản chất:
      - "Không có kết quả"  -> tra cứu THÀNH CÔNG, danh sách rỗng (không có "LỖI:")
      - "LỖI: ..."          -> tra cứu THẤT BẠI, tham số sai
3. Kết quả tìm kiếm LUÔN bị giới hạn số dòng hiển thị (MAX_RESULTS_SHOWN) nhưng
   vẫn báo tổng số căn khớp. Lý do: có truy vấn khớp tới 287 căn — nhồi hết vào
   Observation sẽ làm nổ context window của LLM.
4. Docstring dòng đầu của mỗi tool được prompts.py đọc để tự sinh mô tả trong
   REACT_SYSTEM_PROMPT -> mô tả luôn khớp code thật.
"""

import csv
import os
import re
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════
# ⚙️ CẤU HÌNH
# ═══════════════════════════════════════════════════════════════════════════

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"
)
LISTINGS_PATH = os.path.join(_CONFIG_DIR, "listings.txt")
BOOKINGS_PATH = os.path.join(_CONFIG_DIR, "bookings.txt")

# 🕗 GIỜ LÀM VIỆC: chỉ cho đặt lịch xem nhà từ 08:00 đến 17:00, theo từng giờ tròn.
WORK_START_HOUR = 8
WORK_END_HOUR = 17          # 17:00 là khung cuối cùng còn nhận
SLOT_HOURS = [f"{h:02d}:00" for h in range(WORK_START_HOUR, WORK_END_HOUR + 1)]

# 📅 Chỉ cho đặt từ ngày mai tới 14 ngày tới (không đặt quá khứ, không đặt quá xa)
MIN_DAYS_AHEAD = 1
MAX_DAYS_AHEAD = 14

MAX_RESULTS_SHOWN = 5       # số căn hiển thị tối đa trong một Observation

BOOKINGS_HEADER = [
    "ma_dat_lich", "ma_can", "ngay", "gio",
    "ten_khach", "so_dien_thoai", "thoi_diem_tao",
]


# ═══════════════════════════════════════════════════════════════════════════
# 📥 NẠP DỮ LIỆU
# ═══════════════════════════════════════════════════════════════════════════

_listings_cache = None
_valid_districts = []
_valid_amenities = []


def _load_listings() -> dict:
    """Nạp listings.txt một lần rồi cache. Trả về dict {ma_can: record}."""
    global _listings_cache, _valid_districts, _valid_amenities
    if _listings_cache is not None:
        return _listings_cache

    if not os.path.exists(LISTINGS_PATH):
        _listings_cache = {}
        return _listings_cache

    data, districts, amenities = {}, set(), set()
    with open(LISTINGS_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tien_ich = [t.strip() for t in row["tien_ich_xung_quanh"].split(";") if t.strip()]
            data[row["ma_can"]] = {
                "ma_can": row["ma_can"],
                "dia_chi": row["dia_chi"],
                "quan": row["quan"],
                "gia": int(row["gia_thue_vnd"]),
                "dien_tich": int(row["dien_tich_m2"]),
                "tien_ich": tien_ich,
            }
            districts.add(row["quan"])
            amenities.update(tien_ich)

    _listings_cache = data
    # Suy ra danh sách hợp lệ TỪ DỮ LIỆU, không khai báo tay
    _valid_districts = sorted(districts)
    _valid_amenities = sorted(amenities)
    return _listings_cache


def _load_bookings() -> list:
    """Đọc bookings.txt. Luôn đọc lại từ đĩa vì file này thay đổi khi khách đặt lịch."""
    if not os.path.exists(BOOKINGS_PATH):
        return []
    try:
        with open(BOOKINGS_PATH, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _append_booking(record: dict) -> None:
    """Ghi thêm một lịch hẹn vào bookings.txt (tạo file kèm header nếu chưa có)."""
    os.makedirs(os.path.dirname(BOOKINGS_PATH) or ".", exist_ok=True)
    need_header = not os.path.exists(BOOKINGS_PATH) or os.path.getsize(BOOKINGS_PATH) == 0
    with open(BOOKINGS_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BOOKINGS_HEADER)
        if need_header:
            writer.writeheader()
        writer.writerow(record)


def _next_booking_id() -> str:
    return f"BK{len(_load_bookings()) + 1:05d}"


# ═══════════════════════════════════════════════════════════════════════════
# 🧰 TIỆN ÍCH NỘI BỘ — chuẩn hoá tham số do LLM truyền vào
# ═══════════════════════════════════════════════════════════════════════════

_EMPTY_TOKENS = {"", "-", "none", "null", "any", "không", "khong",
                 "không giới hạn", "khong gioi han", "tùy", "tuy", "n/a"}


def _is_blank(value) -> bool:
    return value is None or str(value).strip().lower() in _EMPTY_TOKENS


def _parse_money(value):
    """Ép chuỗi tiền về int. Chấp nhận '5000000', '5,000,000', '5.000.000',
    '5 triệu', '5tr', '5.5 triệu'. Trả về None nếu không hiểu được."""
    if _is_blank(value):
        return None
    text = str(value).strip().lower()

    # Dạng "5 triệu" / "5tr" / "5.5 trieu"
    if "tri" in text or re.search(r"\dtr\b", text) or text.endswith("tr"):
        num = re.search(r"(\d+(?:[.,]\d+)?)", text)
        if not num:
            return None
        try:
            return int(float(num.group(1).replace(",", ".")) * 1_000_000)
        except ValueError:
            return None

    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_int(value):
    """Ép chuỗi số nguyên (diện tích). Trả về None nếu trống/không hiểu được."""
    if _is_blank(value):
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _parse_amenities(value) -> list:
    """Tách chuỗi tiện ích. Chấp nhận ngăn bằng ';' hoặc ',' hoặc ' và '."""
    if _is_blank(value):
        return []
    text = str(value).replace(" và ", ";").replace(",", ";")
    return [t.strip() for t in text.split(";") if t.strip()]


def _match_district(value):
    """Khớp tên quận không phân biệt hoa thường/dấu cách thừa. None nếu không khớp."""
    _load_listings()
    target = str(value).strip().lower()
    for d in _valid_districts:
        if d.lower() == target:
            return d
    return None


def _match_amenity(value):
    _load_listings()
    target = str(value).strip().lower()
    for a in _valid_amenities:
        if a.lower() == target:
            return a
    return None


def _resolve_listing(ma_can):
    """Tìm căn theo mã. Chấp nhận cả UUID đầy đủ lẫn TIỀN TỐ (>= 6 ký tự).

    Lý do hỗ trợ tiền tố: UUID dài 36 ký tự, LLM rất hay chép thiếu hoặc rút gọn.
    Trả về (record, None) nếu OK, hoặc (None, "chuỗi lỗi") nếu không tìm được.
    """
    listings = _load_listings()
    if _is_blank(ma_can):
        return None, ("LỖI: Thiếu tham số 'ma_can'. Hãy dùng mã căn lấy từ kết quả "
                      "search_listings, ví dụ: get_listing_details[\"777417ce-a8ca-4b4f-b110-61c395a193fc\"]")

    key = str(ma_can).strip().strip("[]").lower()
    if key in listings:
        return listings[key], None

    if len(key) >= 6:
        hits = [v for k, v in listings.items() if k.startswith(key)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, (f"LỖI: Tiền tố mã '{ma_can}' khớp với {len(hits)} căn khác nhau. "
                          f"Hãy dùng mã căn đầy đủ 36 ký tự.")

    return None, (f"LỖI: Không tồn tại căn hộ với mã '{ma_can}'. Mã căn là chuỗi UUID "
                  f"lấy từ kết quả của search_listings, không phải mã tự đặt.")


def _parse_date(value):
    """Ép chuỗi ngày về date. Chấp nhận YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY."""
    if _is_blank(value):
        return None, "LỖI: Thiếu tham số ngày."
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, (f"LỖI: Ngày '{value}' sai định dạng hoặc không phải ngày có thật. "
                  f"Định dạng bắt buộc: YYYY-MM-DD (ví dụ: "
                  f"'{(datetime.now().date() + timedelta(days=1)).isoformat()}').")


def _check_date_window(d):
    """Kiểm tra ngày nằm trong cửa sổ cho phép đặt lịch. Trả về chuỗi lỗi hoặc None."""
    today = datetime.now().date()
    earliest = today + timedelta(days=MIN_DAYS_AHEAD)
    latest = today + timedelta(days=MAX_DAYS_AHEAD)
    if d < earliest:
        return (f"LỖI: Ngày '{d.isoformat()}' đã qua hoặc là hôm nay. Chỉ nhận đặt lịch "
                f"từ {earliest.isoformat()} trở đi.")
    if d > latest:
        return (f"LỖI: Ngày '{d.isoformat()}' quá xa. Chỉ nhận đặt lịch trong vòng "
                f"{MAX_DAYS_AHEAD} ngày, tức tới hết {latest.isoformat()}.")
    return None


def _parse_time(value):
    """Ép chuỗi giờ về 'HH:00'. Chỉ chấp nhận giờ tròn trong khung 08:00–17:00."""
    if _is_blank(value):
        return None, "LỖI: Thiếu tham số giờ."
    text = str(value).strip().replace("h", ":").replace(".", ":")
    m = re.match(r"^(\d{1,2})(?::(\d{1,2}))?$", text)
    if not m:
        return None, (f"LỖI: Giờ '{value}' sai định dạng. Định dạng bắt buộc HH:MM "
                      f"(ví dụ '09:00'). Khung giờ nhận đặt: {', '.join(SLOT_HOURS)}.")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)

    if minute != 0:
        return None, (f"LỖI: Chỉ nhận đặt lịch vào giờ tròn (phút = 00), nhận được '{value}'. "
                      f"Khung giờ hợp lệ: {', '.join(SLOT_HOURS)}.")
    if not (WORK_START_HOUR <= hour <= WORK_END_HOUR):
        return None, (f"LỖI: Giờ '{value}' nằm ngoài giờ làm việc. Chỉ nhận đặt lịch xem nhà "
                      f"từ {WORK_START_HOUR:02d}:00 đến {WORK_END_HOUR:02d}:00. "
                      f"Khung giờ hợp lệ: {', '.join(SLOT_HOURS)}.")
    return f"{hour:02d}:00", None


def _format_listing(item, index=None) -> str:
    prefix = f"{index}. " if index else "- "
    tien_ich = ", ".join(item["tien_ich"]) if item["tien_ich"] else "(không có tiện ích nổi bật)"
    return (f"{prefix}[{item['ma_can']}] {item['dia_chi']}, {item['quan']} | "
            f"{item['gia']:,} VNĐ/tháng | {item['dien_tich']}m2\n"
            f"   Tiện ích gần đó: {tien_ich}")


# ═══════════════════════════════════════════════════════════════════════════
# 🛠️ CÁC TOOL ĐƯỢC CẤP CHO AGENT
# ═══════════════════════════════════════════════════════════════════════════

def search_listings(quan="", gia_toi_da="", dien_tich_toi_thieu="",
                    dien_tich_toi_da="", tien_ich="", gia_toi_thieu="") -> str:
    """Tìm căn hộ/nhà trọ cho thuê theo quận, khoảng giá, khoảng diện tích và tiện ích xung quanh.

    Dùng khi: người dùng muốn tìm nhà theo tiêu chí. Đây thường là bước ĐẦU TIÊN,
    vì mã căn (UUID) chỉ có thể lấy được từ kết quả của tool này.

    Thứ tự tham số (bỏ trống "" nếu không lọc theo tiêu chí đó):
        quan (str)                : Tên quận nội thành Hà Nội. Ví dụ "Cầu Giấy".
        gia_toi_da (str)          : Giá thuê tối đa VNĐ/tháng. Ví dụ "8000000" hoặc "8 triệu".
        dien_tich_toi_thieu (str) : Diện tích tối thiểu m2. Ví dụ "90".
        dien_tich_toi_da (str)    : Diện tích tối đa m2. Ví dụ "110".
        tien_ich (str)            : Tiện ích bắt buộc có, ngăn bằng ";". Ví dụ "Bể bơi; Phòng gym".
        gia_toi_thieu (str)       : Giá thuê tối thiểu VNĐ/tháng. Ví dụ "15000000".

    Returns:
        str: Tổng số căn khớp + tối đa 5 căn tiêu biểu kèm mã căn (UUID) để dùng
             cho bước sau. Nếu không căn nào khớp, trả về thông báo "Không tìm thấy"
             (KHÔNG phải lỗi). Nếu tham số sai, trả về chuỗi bắt đầu bằng "LỖI:".

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        listings = _load_listings()
        if not listings:
            return (f"LỖI: Không đọc được dữ liệu căn hộ tại '{LISTINGS_PATH}'. "
                    f"Hãy chạy: python config/generate_listings.py")

        results = list(listings.values())
        tieu_chi = []

        # ----- Lọc theo quận -----
        if not _is_blank(quan):
            matched = _match_district(quan)
            if matched is None:
                return (f"LỖI: Không tìm thấy quận '{quan}' trong khu vực phục vụ. "
                        f"Các quận hợp lệ: {', '.join(_valid_districts)}.")
            results = [r for r in results if r["quan"] == matched]
            tieu_chi.append(f"quận {matched}")

        # ----- Lọc theo giá -----
        if not _is_blank(gia_toi_da):
            gmax = _parse_money(gia_toi_da)
            if gmax is None:
                return (f"LỖI: Tham số 'gia_toi_da' không hiểu được: '{gia_toi_da}'. "
                        f"Hãy dùng số VNĐ, ví dụ '8000000' hoặc '8 triệu'.")
            results = [r for r in results if r["gia"] <= gmax]
            tieu_chi.append(f"giá <= {gmax:,} VNĐ")

        if not _is_blank(gia_toi_thieu):
            gmin = _parse_money(gia_toi_thieu)
            if gmin is None:
                return (f"LỖI: Tham số 'gia_toi_thieu' không hiểu được: '{gia_toi_thieu}'. "
                        f"Hãy dùng số VNĐ, ví dụ '15000000' hoặc '15 triệu'.")
            results = [r for r in results if r["gia"] >= gmin]
            tieu_chi.append(f"giá >= {gmin:,} VNĐ")

        # ----- Lọc theo diện tích -----
        if not _is_blank(dien_tich_toi_thieu):
            amin = _parse_int(dien_tich_toi_thieu)
            if amin is None:
                return f"LỖI: Tham số 'dien_tich_toi_thieu' phải là số m2, nhận được '{dien_tich_toi_thieu}'."
            results = [r for r in results if r["dien_tich"] >= amin]
            tieu_chi.append(f"diện tích >= {amin}m2")

        if not _is_blank(dien_tich_toi_da):
            amax = _parse_int(dien_tich_toi_da)
            if amax is None:
                return f"LỖI: Tham số 'dien_tich_toi_da' phải là số m2, nhận được '{dien_tich_toi_da}'."
            results = [r for r in results if r["dien_tich"] <= amax]
            tieu_chi.append(f"diện tích <= {amax}m2")

        # ----- Lọc theo tiện ích -----
        wanted = _parse_amenities(tien_ich)
        if wanted:
            canon = []
            for w in wanted:
                m = _match_amenity(w)
                if m is None:
                    return (f"LỖI: Không có tiện ích tên '{w}' trong dữ liệu. "
                            f"Các tiện ích hợp lệ: {', '.join(_valid_amenities)}.")
                canon.append(m)
            for c in canon:
                results = [r for r in results if c in r["tien_ich"]]
            tieu_chi.append("có " + " + ".join(canon))

        mo_ta = "; ".join(tieu_chi) if tieu_chi else "không giới hạn tiêu chí"

        # ----- Không có kết quả: THÀNH CÔNG nhưng rỗng, không phải LỖI -----
        if not results:
            return (f"Không tìm thấy căn nào khớp tiêu chí ({mo_ta}). "
                    f"Đây là kết quả tra cứu hợp lệ, không phải lỗi hệ thống. "
                    f"Gợi ý: nới ngân sách, nới khoảng diện tích, hoặc bớt bớt tiện ích bắt buộc.")

        results.sort(key=lambda r: r["gia"])
        shown = results[:MAX_RESULTS_SHOWN]
        lines = [f"Tìm thấy {len(results)} căn khớp tiêu chí ({mo_ta}). "
                 f"Hiển thị {len(shown)} căn giá thấp nhất:"]
        lines += [_format_listing(item, i) for i, item in enumerate(shown, 1)]
        if len(results) > len(shown):
            lines.append(f"... và {len(results) - len(shown)} căn khác không hiển thị.")
        return "\n".join(lines)

    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong search_listings ({type(e).__name__}: {e})."


def get_listing_details(ma_can="") -> str:
    """Xem chi tiết đầy đủ của một căn hộ theo mã căn (UUID lấy từ search_listings).

    Dùng khi: cần địa chỉ, giá, diện tích, tiện ích đầy đủ của một căn cụ thể.

    Args:
        ma_can (str): Mã căn dạng UUID. Chấp nhận cả tiền tố >= 6 ký tự.

    Returns:
        str: Thông tin chi tiết căn hộ, hoặc chuỗi "LỖI:" nếu mã không tồn tại.

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        item, err = _resolve_listing(ma_can)
        if err:
            return err
        tien_ich = ", ".join(item["tien_ich"]) if item["tien_ich"] else "(không có tiện ích nổi bật)"
        return (
            f"Chi tiết căn [{item['ma_can']}]:\n"
            f"- Địa chỉ  : {item['dia_chi']}, quận {item['quan']}, Hà Nội\n"
            f"- Giá thuê : {item['gia']:,} VNĐ/tháng\n"
            f"- Diện tích: {item['dien_tich']} m2\n"
            f"- Tiện ích gần đó: {tien_ich}\n"
            f"- Muốn xem nhà: gọi check_viewing_slots với mã căn này để biết khung giờ trống."
        )
    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong get_listing_details ({type(e).__name__}: {e})."


def check_viewing_slots(ma_can="", ngay="") -> str:
    """Kiểm tra các khung giờ CÒN TRỐNG để đi xem một căn nhà trong một ngày cụ thể.

    Tool này duyệt qua toàn bộ lịch hẹn đã có trong bookings.txt của căn đó,
    loại bỏ các khung giờ đã bị đặt, rồi trả về phần còn trống.
    BẮT BUỘC gọi tool này TRƯỚC book_viewing để biết khung giờ nào hợp lệ.

    Args:
        ma_can (str): Mã căn dạng UUID (lấy từ search_listings).
        ngay (str)  : Ngày muốn xem, định dạng YYYY-MM-DD. Bỏ trống = ngày mai.

    Returns:
        str: Danh sách khung giờ còn trống trong khung 08:00-17:00, hoặc thông báo
             đã kín lịch, hoặc chuỗi "LỖI:" nếu mã căn / ngày không hợp lệ.

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        item, err = _resolve_listing(ma_can)
        if err:
            return err

        if _is_blank(ngay):
            target = datetime.now().date() + timedelta(days=MIN_DAYS_AHEAD)
        else:
            target, err = _parse_date(ngay)
            if err:
                return err

        window_err = _check_date_window(target)
        if window_err:
            return window_err

        ngay_str = target.isoformat()
        da_dat = {
            b["gio"] for b in _load_bookings()
            if b.get("ma_can") == item["ma_can"] and b.get("ngay") == ngay_str
        }
        con_trong = [s for s in SLOT_HOURS if s not in da_dat]

        if not con_trong:
            return (f"Căn [{item['ma_can']}] đã KÍN LỊCH ngày {ngay_str} "
                    f"(cả {len(SLOT_HOURS)} khung giờ 08:00-17:00 đều có người đặt). "
                    f"Hãy thử một ngày khác.")

        return (f"Căn [{item['ma_can']}] ngày {ngay_str} còn {len(con_trong)}/{len(SLOT_HOURS)} "
                f"khung giờ trống (giờ làm việc {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00): "
                + ", ".join(con_trong)
                + f"\n(Đã có {len(da_dat)} khung bị đặt: "
                + (", ".join(sorted(da_dat)) if da_dat else "không có") + ")")

    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong check_viewing_slots ({type(e).__name__}: {e})."


def book_viewing(ma_can="", ngay="", gio="", ten_khach="", so_dien_thoai="") -> str:
    """Đặt lịch hẹn đi xem nhà và GHI VĨNH VIỄN vào file bookings.txt.

    ⚠️ Đây là tool DUY NHẤT có side effect (ghi dữ liệu). Chỉ gọi khi khách đã
    XÁC NHẬN rõ ràng căn nào, ngày nào, giờ nào. Phải gọi check_viewing_slots trước.

    Args:
        ma_can (str)        : Mã căn dạng UUID.
        ngay (str)          : Ngày xem, YYYY-MM-DD. Từ ngày mai tới tối đa 14 ngày tới.
        gio (str)           : Giờ xem, HH:00. Chỉ nhận giờ tròn trong 08:00-17:00.
        ten_khach (str)     : Tên khách hàng.
        so_dien_thoai (str) : Số điện thoại liên hệ.

    Returns:
        str: Mã xác nhận đặt lịch (BKxxxxx), hoặc chuỗi "LỖI:" kèm hướng dẫn sửa
             nếu mã căn sai / ngày sai / giờ ngoài khung / khung giờ đã có người đặt.

    Side effect: CÓ — ghi thêm một dòng vào config/bookings.txt.
    """
    try:
        item, err = _resolve_listing(ma_can)
        if err:
            return err

        target, err = _parse_date(ngay)
        if err:
            return err
        window_err = _check_date_window(target)
        if window_err:
            return window_err

        slot, err = _parse_time(gio)
        if err:
            return err

        if _is_blank(ten_khach):
            return ("LỖI: Thiếu tên khách hàng. Hãy hỏi khách tên trước khi đặt lịch. "
                    "Cú pháp: book_viewing[\"<ma_can>\", \"YYYY-MM-DD\", \"HH:00\", \"Tên khách\", \"SĐT\"]")
        if _is_blank(so_dien_thoai):
            return ("LỖI: Thiếu số điện thoại liên hệ. Hãy hỏi khách số điện thoại trước khi đặt lịch.")

        phone = re.sub(r"[^\d+]", "", str(so_dien_thoai))
        if len(re.sub(r"\D", "", phone)) < 9:
            return (f"LỖI: Số điện thoại '{so_dien_thoai}' không hợp lệ "
                    f"(cần ít nhất 9 chữ số).")

        ngay_str = target.isoformat()

        # Kiểm tra trùng lịch — đọc lại file để thấy cả lịch vừa đặt trong phiên
        for b in _load_bookings():
            if (b.get("ma_can") == item["ma_can"]
                    and b.get("ngay") == ngay_str and b.get("gio") == slot):
                return (f"LỖI: Khung giờ {slot} ngày {ngay_str} của căn [{item['ma_can']}] "
                        f"đã có người đặt (mã {b.get('ma_dat_lich')}). "
                        f"Hãy gọi check_viewing_slots để xem khung giờ còn trống.")

        booking_id = _next_booking_id()
        _append_booking({
            "ma_dat_lich": booking_id,
            "ma_can": item["ma_can"],
            "ngay": ngay_str,
            "gio": slot,
            "ten_khach": str(ten_khach).strip(),
            "so_dien_thoai": phone,
            "thoi_diem_tao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        return (f"ĐẶT LỊCH THÀNH CÔNG! Mã xác nhận: {booking_id}\n"
                f"- Căn    : [{item['ma_can']}]\n"
                f"- Địa chỉ: {item['dia_chi']}, quận {item['quan']}\n"
                f"- Thời gian: {slot} ngày {ngay_str}\n"
                f"- Khách  : {str(ten_khach).strip()} - {phone}\n"
                f"(Lịch hẹn đã được ghi vào hệ thống.)")

    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong book_viewing ({type(e).__name__}: {e})."


def list_bookings(so_dien_thoai="") -> str:
    """Tra cứu các lịch hẹn xem nhà đã đặt theo số điện thoại khách hàng.

    Dùng khi: khách muốn kiểm tra lại lịch đã đặt, hoặc để xác nhận sau khi book.

    Args:
        so_dien_thoai (str): Số điện thoại đã dùng khi đặt lịch.

    Returns:
        str: Danh sách lịch hẹn kèm mã đặt lịch, hoặc thông báo chưa có lịch nào.

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        if _is_blank(so_dien_thoai):
            return "LỖI: Thiếu số điện thoại để tra cứu lịch hẹn."

        phone = re.sub(r"\D", "", str(so_dien_thoai))
        listings = _load_listings()
        mine = [b for b in _load_bookings() if re.sub(r"\D", "", b.get("so_dien_thoai", "")) == phone]

        if not mine:
            return (f"Không tìm thấy lịch hẹn nào cho số điện thoại {so_dien_thoai}. "
                    f"Đây là kết quả tra cứu hợp lệ, không phải lỗi.")

        mine.sort(key=lambda b: (b.get("ngay", ""), b.get("gio", "")))
        lines = [f"Tìm thấy {len(mine)} lịch hẹn cho số {so_dien_thoai}:"]
        for b in mine:
            item = listings.get(b.get("ma_can", ""))
            dia_chi = f"{item['dia_chi']}, {item['quan']}" if item else b.get("ma_can", "?")
            lines.append(f"- [{b.get('ma_dat_lich')}] {b.get('gio')} ngày {b.get('ngay')} "
                         f"| {dia_chi} | Khách: {b.get('ten_khach')}")
        return "\n".join(lines)

    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong list_bookings ({type(e).__name__}: {e})."


# ═══════════════════════════════════════════════════════════════════════════
# 📇 TOOL REGISTRY — nguồn sự thật duy nhất cho cả app.py và prompts.py
# ⚠️ KHÔNG thêm alias trùng tên vào đây. prompts.py tự sinh mô tả tool từ dict
#    này, nên mỗi alias sẽ thành một "tool" riêng trong prompt và làm LLM rối
#    khi chọn tool.
# ═══════════════════════════════════════════════════════════════════════════
AVAILABLE_TOOLS = {
    "search_listings": search_listings,
    "get_listing_details": get_listing_details,
    "check_viewing_slots": check_viewing_slots,
    "book_viewing": book_viewing,
    "list_bookings": list_bookings,
}


# ═══════════════════════════════════════════════════════════════════════════
# 🖥️ HÀM PHỤ TRỢ CHO GIAO DIỆN WEB — CỐ Ý KHÔNG ĐƯA VÀO AVAILABLE_TOOLS
#    (đây không phải công cụ của Agent, chỉ để frontend hiển thị dữ liệu mẫu)
# ═══════════════════════════════════════════════════════════════════════════

def get_sample_listings(limit: int = 50) -> list:
    """Trả về vài căn đầu tiên từ listings.txt cho UI preview."""
    return list(_load_listings().values())[:limit]


def get_all_bookings() -> list:
    """Trả về toàn bộ lịch hẹn hiện có cho UI preview."""
    return _load_bookings()


if __name__ == "__main__":
    # 🧪 UNIT TEST TOOL ĐỘC LẬP — chạy: python src/tools.py
    import sys
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # ⚠️ Chuyển sang file tạm: unit test có gọi book_viewing (tool CÓ side effect),
    # nếu để trỏ vào bookings.txt thật thì mỗi lần chạy test lại rác thêm một dòng.
    import shutil
    import tempfile
    _tmp_dir = tempfile.mkdtemp(prefix="lab3_test_")
    _tmp_bookings = os.path.join(_tmp_dir, "bookings.txt")
    if os.path.exists(BOOKINGS_PATH):
        shutil.copy(BOOKINGS_PATH, _tmp_bookings)
    BOOKINGS_PATH = _tmp_bookings
    print(f"ℹ️  Test chạy trên bản sao bookings tại {_tmp_bookings} "
          f"(bookings.txt thật KHÔNG bị thay đổi)\n")

    _load_listings()
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    sample_id = next(iter(_load_listings()))
    # Căn được seed KÍN LỊCH ngày mai (nếu có) để test nhánh hết chỗ
    _booked = [b["ma_can"] for b in _load_bookings() if b.get("ngay") == tomorrow]
    _full_id = max(set(_booked), key=_booked.count) if _booked else sample_id

    cases = [
        ("Lọc theo quận + giá",      lambda: search_listings("Cầu Giấy", "8000000")),
        ("Lọc 4 chiều",              lambda: search_listings("Tây Hồ", "", "90", "110", "Bể bơi; Phòng gym")),
        ("Giá dạng '8 triệu'",       lambda: search_listings("Cầu Giấy", "8 triệu")),
        ("Quận không tồn tại",       lambda: search_listings("Atlantis")),
        ("Tiện ích không tồn tại",   lambda: search_listings("Cầu Giấy", "", "", "", "Sân bay riêng")),
        ("Kết quả RỖNG (hợp lệ)",    lambda: search_listings("Hoàn Kiếm", "2500000", "190")),
        ("Chi tiết theo UUID",       lambda: get_listing_details(sample_id)),
        ("Chi tiết theo tiền tố",    lambda: get_listing_details(sample_id[:8])),
        ("Mã căn không tồn tại",     lambda: get_listing_details("AP-101")),
        ("Khung giờ trống",          lambda: check_viewing_slots(sample_id, tomorrow)),
        ("Căn KÍN LỊCH ngày mai",    lambda: check_viewing_slots(_full_id, tomorrow)),
        ("Ngày sai định dạng 32/13", lambda: check_viewing_slots(sample_id, "32/13/2026")),
        ("Đặt lịch thành công",      lambda: book_viewing(sample_id, tomorrow, "09:00", "Nguyễn Văn A", "0912345678")),
        ("Đặt trùng khung giờ",      lambda: book_viewing(sample_id, tomorrow, "09:00", "Trần Thị B", "0987654321")),
        ("Giờ ngoài 8h-17h (19:00)", lambda: book_viewing(sample_id, tomorrow, "19:00", "Lê C", "0911222333")),
        ("Giờ lẻ 09:30",             lambda: book_viewing(sample_id, tomorrow, "09:30", "Lê C", "0911222333")),
        ("Đặt ngày quá khứ",         lambda: book_viewing(sample_id, "2020-01-01", "09:00", "Lê C", "0911222333")),
        ("Thiếu tên khách",          lambda: book_viewing(sample_id, tomorrow, "10:00", "", "0911222333")),
        ("SĐT không hợp lệ",         lambda: book_viewing(sample_id, tomorrow, "10:00", "Lê C", "123")),
        ("Tra lịch theo SĐT",        lambda: list_bookings("0912345678")),
    ]

    print("=" * 78)
    print(f"🧪 UNIT TEST TOOL REGISTRY (Role 2) — {len(_load_listings()):,} căn nạp từ listings.txt")
    print("=" * 78)
    crashed = 0
    for name, fn in cases:
        try:
            out = fn()
            print(f"\n✅ {name}\n   -> {out}")
        except Exception as e:
            crashed += 1
            print(f"\n💥 {name} -> CRASH! {type(e).__name__}: {e}")

    print("\n" + "=" * 78)
    print(f"KẾT QUẢ: {len(cases) - crashed}/{len(cases)} test trả về chuỗi an toàn, {crashed} crash.")
    print("=" * 78)
