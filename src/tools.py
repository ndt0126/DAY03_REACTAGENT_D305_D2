"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)

CHỦ ĐỀ NHÓM: 🏠 Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê (Đề tài #10)

═══════════════════════════════════════════════════════════════════════════
NGUYÊN TẮC BẤT BIẾN CỦA TOOL (Tool Contract)
═══════════════════════════════════════════════════════════════════════════
1. Tool KHÔNG BAO GIỜ raise Exception ra ngoài. Mọi lỗi phải được bắt và trả về
   dưới dạng CHUỖI bắt đầu bằng "LỖI:". Lý do: lỗi nghiệp vụ là DỮ LIỆU để Agent
   suy luận và đổi hướng, không phải là sự cố làm sập chương trình.
2. Mỗi tool có docstring đầy đủ: mục đích, input schema, output schema, error
   semantics, side effect. Docstring này được prompts.py đọc để tự sinh phần mô
   tả tool trong REACT_SYSTEM_PROMPT -> mô tả luôn khớp với code thật.
3. Tool trả về chuỗi NGƯỜI ĐỌC ĐƯỢC, đủ chi tiết để Agent trích dẫn làm bằng chứng.
"""

from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════
# 📦 DỮ LIỆU GIẢ LẬP (Deterministic — cùng input luôn cho cùng output)
# Trong dự án thật, phần này sẽ là truy vấn database hoặc gọi API bên thứ ba.
# ═══════════════════════════════════════════════════════════════════════════

_LISTINGS = {
    "APT001": {
        "title": "Studio full nội thất, ban công",
        "district": "Cầu Giấy",
        "address": "Số 12, ngõ 165 Xuân Thủy, Cầu Giấy, Hà Nội",
        "price": 4500000,
        "area_m2": 28,
        "bedrooms": 1,
        "amenities": "Điều hòa, máy giặt riêng, nóng lạnh, wifi, thang máy",
        "status": "Còn trống",
    },
    "APT002": {
        "title": "Chung cư mini 2PN, gần ĐH Quốc Gia",
        "district": "Cầu Giấy",
        "address": "Số 48 Trần Thái Tông, Cầu Giấy, Hà Nội",
        "price": 6800000,
        "area_m2": 45,
        "bedrooms": 2,
        "amenities": "Điều hòa 2 phòng, bếp từ, chỗ để xe, an ninh 24/7",
        "status": "Còn trống",
    },
    "APT003": {
        "title": "Phòng trọ giá rẻ, khép kín",
        "district": "Thanh Xuân",
        "address": "Ngõ 178 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "price": 3200000,
        "area_m2": 20,
        "bedrooms": 1,
        "amenities": "Nóng lạnh, wifi, gác xép",
        "status": "Còn trống",
    },
    "APT004": {
        "title": "Căn hộ dịch vụ cao cấp, view hồ",
        "district": "Tây Hồ",
        "address": "Số 5 Quảng An, Tây Hồ, Hà Nội",
        "price": 12000000,
        "area_m2": 60,
        "bedrooms": 2,
        "amenities": "Full nội thất cao cấp, dọn phòng hàng tuần, hồ bơi",
        "status": "Còn trống",
    },
    "APT005": {
        "title": "Phòng ghép sinh viên, đã cho thuê",
        "district": "Thanh Xuân",
        "address": "Ngõ 90 Khương Trung, Thanh Xuân, Hà Nội",
        "price": 2000000,
        "area_m2": 18,
        "bedrooms": 1,
        "amenities": "Wifi, chỗ để xe",
        "status": "Đã cho thuê",
    },
}

# Khung giờ xem nhà còn trống theo từng mã căn hộ
_VIEWING_SLOTS = {
    "APT001": ["2026-07-29 09:00", "2026-07-29 15:00", "2026-07-30 10:00"],
    "APT002": ["2026-07-29 14:00", "2026-07-31 09:30"],
    "APT003": ["2026-07-30 16:00"],
    "APT004": ["2026-07-29 11:00", "2026-08-01 09:00"],
    "APT005": [],  # Đã cho thuê nên không còn lịch xem
}

# Bộ nhớ lưu các lịch hẹn đã đặt trong phiên chạy (side effect có chủ đích)
_BOOKINGS = []

_VALID_DISTRICTS = ["Cầu Giấy", "Thanh Xuân", "Tây Hồ", "Đống Đa", "Hai Bà Trưng"]


# ═══════════════════════════════════════════════════════════════════════════
# 🛠️ CÁC TOOL ĐƯỢC CẤP CHO AGENT
# ═══════════════════════════════════════════════════════════════════════════

def search_listings(district: str, max_price: str = "999999999") -> str:
    """Tìm danh sách phòng trọ/căn hộ đang còn trống theo quận và mức giá tối đa.

    Dùng khi: người dùng hỏi "có phòng nào ở quận X không", "tìm phòng dưới Y triệu".
    Không dùng khi: người dùng đã biết mã căn hộ (khi đó dùng get_listing_details).

    Args:
        district (str): Tên quận tại Hà Nội. Hợp lệ: Cầu Giấy, Thanh Xuân,
            Tây Hồ, Đống Đa, Hai Bà Trưng.
        max_price (str): Giá thuê tối đa mỗi tháng, đơn vị VNĐ (ví dụ: 5000000).

    Returns:
        str: Danh sách căn hộ kèm mã (APTxxx), giá, diện tích. Nếu quận không hợp
             lệ hoặc giá sai định dạng, trả về chuỗi bắt đầu bằng "LỖI:".

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        if not district or not str(district).strip():
            return "LỖI: Thiếu tham số 'district'. Cú pháp đúng: search_listings[\"Cầu Giấy\", 5000000]"

        district = str(district).strip()

        # Ép kiểu giá an toàn — LLM hay truyền "5 triệu" hoặc "5,000,000"
        try:
            price_clean = str(max_price).replace(",", "").replace(".", "").strip()
            max_price_int = int(float(price_clean))
        except (ValueError, TypeError):
            return (f"LỖI: Tham số 'max_price' phải là số nguyên VNĐ, nhận được '{max_price}'. "
                    f"Ví dụ đúng: search_listings[\"Cầu Giấy\", 5000000]")

        # Kiểm tra quận có nằm trong vùng phục vụ không
        matched = [d for d in _VALID_DISTRICTS if d.lower() == district.lower()]
        if not matched:
            return (f"LỖI: Không tìm thấy quận '{district}' trong khu vực phục vụ. "
                    f"Các quận hợp lệ: {', '.join(_VALID_DISTRICTS)}.")
        district = matched[0]

        results = [
            (code, item) for code, item in _LISTINGS.items()
            if item["district"] == district
            and item["price"] <= max_price_int
            and item["status"] == "Còn trống"
        ]

        if not results:
            return (f"Không có căn nào ở {district} với giá dưới {max_price_int:,} VNĐ. "
                    f"Gợi ý: thử nâng ngân sách hoặc đổi sang quận khác.")

        lines = [f"Tìm thấy {len(results)} căn tại {district} (giá <= {max_price_int:,} VNĐ):"]
        for code, item in sorted(results, key=lambda x: x[1]["price"]):
            lines.append(
                f"- [{code}] {item['title']} | {item['price']:,} VNĐ/tháng | "
                f"{item['area_m2']}m2 | {item['bedrooms']}PN | {item['status']}"
            )
        return "\n".join(lines)

    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong search_listings ({type(e).__name__}: {e})."


def get_listing_details(listing_id: str) -> str:
    """Xem thông tin chi tiết của một căn hộ theo mã căn (APTxxx).

    Dùng khi: cần địa chỉ đầy đủ, tiện ích, diện tích của một căn cụ thể.
    Thường được gọi SAU search_listings để đào sâu một mã căn đã tìm thấy.

    Args:
        listing_id (str): Mã căn hộ, định dạng APT + 3 chữ số (ví dụ: APT001).

    Returns:
        str: Thông tin chi tiết căn hộ, hoặc chuỗi "LỖI:" nếu mã không tồn tại.

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        if not listing_id or not str(listing_id).strip():
            return "LỖI: Thiếu tham số 'listing_id'. Cú pháp đúng: get_listing_details[\"APT001\"]"

        code = str(listing_id).strip().upper()
        item = _LISTINGS.get(code)
        if not item:
            return (f"LỖI: Không tồn tại căn hộ với mã '{listing_id}'. "
                    f"Các mã hợp lệ: {', '.join(_LISTINGS.keys())}.")

        return (
            f"Chi tiết căn [{code}]:\n"
            f"- Tiêu đề : {item['title']}\n"
            f"- Địa chỉ : {item['address']}\n"
            f"- Giá thuê: {item['price']:,} VNĐ/tháng\n"
            f"- Diện tích: {item['area_m2']}m2, {item['bedrooms']} phòng ngủ\n"
            f"- Tiện ích: {item['amenities']}\n"
            f"- Trạng thái: {item['status']}"
        )
    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong get_listing_details ({type(e).__name__}: {e})."


def check_viewing_slots(listing_id: str) -> str:
    """Kiểm tra các khung giờ còn trống để đi xem nhà của một căn hộ.

    Dùng khi: người dùng muốn biết "khi nào đi xem được".
    Bắt buộc gọi TRƯỚC book_viewing để biết khung giờ nào hợp lệ.

    Args:
        listing_id (str): Mã căn hộ (ví dụ: APT001).

    Returns:
        str: Danh sách khung giờ định dạng 'YYYY-MM-DD HH:MM', hoặc "LỖI:" nếu
             mã căn không tồn tại.

    Side effect: Không (chỉ đọc dữ liệu).
    """
    try:
        if not listing_id or not str(listing_id).strip():
            return "LỖI: Thiếu tham số 'listing_id'. Cú pháp đúng: check_viewing_slots[\"APT001\"]"

        code = str(listing_id).strip().upper()
        if code not in _LISTINGS:
            return (f"LỖI: Không tồn tại căn hộ với mã '{listing_id}'. "
                    f"Các mã hợp lệ: {', '.join(_LISTINGS.keys())}.")

        slots = _VIEWING_SLOTS.get(code, [])
        # Loại bỏ khung giờ đã có người đặt trong phiên này
        booked = {b["slot"] for b in _BOOKINGS if b["listing_id"] == code}
        free = [s for s in slots if s not in booked]

        if not free:
            return (f"Căn [{code}] hiện không còn khung giờ xem nhà nào trống "
                    f"(có thể căn đã được cho thuê hoặc lịch đã kín).")

        return f"Căn [{code}] còn {len(free)} khung giờ xem nhà: " + "; ".join(free)
    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong check_viewing_slots ({type(e).__name__}: {e})."


def book_viewing(listing_id: str, slot: str) -> str:
    """Đặt lịch hẹn đi xem nhà cho một căn hộ vào một khung giờ cụ thể.

    Dùng khi: người dùng đã chọn được căn và khung giờ.
    ⚠️ Đây là tool DUY NHẤT có side effect (ghi dữ liệu). Chỉ gọi khi đã xác nhận
    khung giờ hợp lệ bằng check_viewing_slots.

    Args:
        listing_id (str): Mã căn hộ (ví dụ: APT001).
        slot (str): Khung giờ, định dạng bắt buộc 'YYYY-MM-DD HH:MM'.

    Returns:
        str: Mã xác nhận đặt lịch, hoặc chuỗi "LỖI:" nếu mã căn sai, định dạng
             ngày sai, hoặc khung giờ không nằm trong danh sách trống.

    Side effect: CÓ — ghi thêm một bản ghi vào danh sách đặt lịch.
    """
    try:
        code = str(listing_id).strip().upper() if listing_id else ""
        if code not in _LISTINGS:
            return (f"LỖI: Không tồn tại căn hộ với mã '{listing_id}'. "
                    f"Các mã hợp lệ: {', '.join(_LISTINGS.keys())}.")

        slot = str(slot).strip() if slot else ""
        # Xác thực định dạng ngày giờ — bắt được cả ngày vô lý kiểu 32/13/2026
        try:
            datetime.strptime(slot, "%Y-%m-%d %H:%M")
        except ValueError:
            return (f"LỖI: Khung giờ '{slot}' sai định dạng hoặc không phải ngày có thật. "
                    f"Định dạng bắt buộc: 'YYYY-MM-DD HH:MM' (ví dụ: '2026-07-29 09:00').")

        if slot not in _VIEWING_SLOTS.get(code, []):
            available = _VIEWING_SLOTS.get(code, [])
            return (f"LỖI: Khung giờ '{slot}' không nằm trong lịch trống của căn [{code}]. "
                    f"Khung giờ hợp lệ: {'; '.join(available) if available else 'không còn khung nào'}.")

        if any(b["listing_id"] == code and b["slot"] == slot for b in _BOOKINGS):
            return f"LỖI: Khung giờ '{slot}' của căn [{code}] vừa có người khác đặt mất rồi."

        booking_id = f"BK{len(_BOOKINGS) + 1:03d}"
        _BOOKINGS.append({"booking_id": booking_id, "listing_id": code, "slot": slot})
        return (f"Đặt lịch thành công! Mã xác nhận: {booking_id}. "
                f"Bạn sẽ xem căn [{code}] — {_LISTINGS[code]['address']} vào lúc {slot}.")
    except Exception as e:
        return f"LỖI: Sự cố không mong muốn trong book_viewing ({type(e).__name__}: {e})."


# ═══════════════════════════════════════════════════════════════════════════
# 📇 TOOL REGISTRY — nguồn sự thật duy nhất cho cả app.py và prompts.py
# ═══════════════════════════════════════════════════════════════════════════
AVAILABLE_TOOLS = {
    "search_listings": search_listings,
    "get_listing_details": get_listing_details,
    "check_viewing_slots": check_viewing_slots,
    "book_viewing": book_viewing,
}


if __name__ == "__main__":
    # 🧪 UNIT TEST TOOL ĐỘC LẬP — chạy: python src/tools.py
    # Codelab Mốc 3 yêu cầu: test tool riêng TRƯỚC khi gắn vào Agent, để khi
    # Agent chạy sai ta biết chắc lỗi không nằm ở tầng tool.
    import sys
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    cases = [
        ("Happy path: tìm phòng", lambda: search_listings("Cầu Giấy", "5000000")),
        ("Quận không hợp lệ",     lambda: search_listings("Atlantis", "5000000")),
        ("Giá sai định dạng",     lambda: search_listings("Cầu Giấy", "năm triệu")),
        ("Thiếu tham số",         lambda: search_listings("", "")),
        ("Chi tiết căn hợp lệ",   lambda: get_listing_details("APT001")),
        ("Mã căn không tồn tại",  lambda: get_listing_details("APT999")),
        ("Lịch xem còn trống",    lambda: check_viewing_slots("APT001")),
        ("Lịch xem đã kín",       lambda: check_viewing_slots("APT005")),
        ("Đặt lịch thành công",   lambda: book_viewing("APT001", "2026-07-29 09:00")),
        ("Ngày vô lý 32/13",      lambda: book_viewing("APT001", "2026-13-32 09:00")),
        ("Khung giờ không có",    lambda: book_viewing("APT001", "2026-07-29 23:00")),
        ("Đặt trùng khung giờ",   lambda: book_viewing("APT001", "2026-07-29 09:00")),
    ]

    print("=" * 70)
    print("🧪 UNIT TEST TOOL REGISTRY (Role 2)")
    print("=" * 70)
    passed = 0
    for name, fn in cases:
        try:
            out = fn()
            ok = isinstance(out, str) and len(out) > 0
            print(f"\n{'✅' if ok else '❌'} {name}\n   -> {out}")
            passed += 1 if ok else 0
        except Exception as e:
            # Nếu rơi vào đây nghĩa là tool đã VI PHẠM hợp đồng "không được crash"
            print(f"\n💥 {name} -> CRASH! {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print(f"KẾT QUẢ: {passed}/{len(cases)} test trả về chuỗi an toàn, 0 crash.")
    print("=" * 70)
