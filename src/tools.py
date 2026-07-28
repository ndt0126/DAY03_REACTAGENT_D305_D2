"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Chủ đề: Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê
"""

import re
import json

# Cơ sở dữ liệu phòng trọ / căn hộ mẫu (Deterministic Mock Database)
SAMPLE_APARTMENTS = [
    {
        "id": "AP-101",
        "title": "Phòng trọ khép kín full đồ mới 100% Cầu Giấy",
        "location": "Cầu Giấy, Hà Nội",
        "district": "Cầu Giấy",
        "city": "Hà Nội",
        "address": "Số 15 ngõ 68 Cầu Giấy, Phường Quan Hoa, Quận Cầu Giấy, Hà Nội",
        "price": 4500000,
        "price_display": "4.5 triệu VNĐ/tháng",
        "room_type": "Phòng trọ khép kín",
        "area": "28m2",
        "amenities": ["Điều hòa", "Nóng lạnh", "Tủ lạnh", "Giường nệm", "Ban công", "Thang máy", "Khóa vân tay"],
        "utilities": "Điện 3.8k/kWh, Nước 100k/người, Wifi 100k/phòng, Dịch vụ 150k/người",
        "deposit": "1 tháng tiền phòng",
        "landlord_phone": "0987-654-321 (Anh Hoàng - Chính chủ)",
        "available_slots": ["09:00", "11:00", "14:30", "17:00"],
        "status": "Còn phòng"
    },
    {
        "id": "AP-102",
        "title": "Căn hộ Studio Studio ban công rộng view đẹp Bình Thạnh",
        "location": "Bình Thạnh, TP.HCM",
        "district": "Bình Thạnh",
        "city": "TP.HCM",
        "address": "245 Điện Biên Phủ, Phường 15, Quận Bình Thạnh, TP.HCM",
        "price": 7200000,
        "price_display": "7.2 triệu VNĐ/tháng",
        "room_type": "Studio / 1PN",
        "area": "35m2",
        "amenities": ["Full nội thất cao cấp", "Máy giặt riêng", "Bếp từ", "Sofa", "Tủ quần áo lớn", "Bảo vệ 24/7"],
        "utilities": "Điện 4.0k/kWh, Nước 120k/người, Phí quản lý 200k/tháng",
        "deposit": "1.5 tháng tiền phòng",
        "landlord_phone": "0912-888-999 (Chị Mai - Quản lý tòa nhà)",
        "available_slots": ["09:30", "10:30", "15:00", "18:00"],
        "status": "Còn phòng"
    },
    {
        "id": "AP-103",
        "title": "Căn hộ 1PN Vinhomes Central Park Quận 1 / Bình Thạnh",
        "location": "Bình Thạnh, TP.HCM",
        "district": "Bình Thạnh",
        "city": "TP.HCM",
        "address": "208 Nguyễn Hữu Cảnh, Phường 22, Quận Bình Thạnh, TP.HCM",
        "price": 12000000,
        "price_display": "12 triệu VNĐ/tháng",
        "room_type": "1PN",
        "area": "52m2",
        "amenities": ["Hồ bơi", "Gym", "Công viên", "Smart Lock", "Tủ lạnh Inverter", "Lò vi sóng"],
        "utilities": "Theo giá nhà nước + Phí quản lý Vinhomes",
        "deposit": "2 tháng tiền phòng",
        "landlord_phone": "0903-111-222 (Anh Minh)",
        "available_slots": ["10:00", "14:00", "16:00"],
        "status": "Còn phòng"
    },
    {
        "id": "AP-104",
        "title": "Phòng trọ giá rẻ cho sinh viên Đống Đa",
        "location": "Đống Đa, Hà Nội",
        "district": "Đống Đa",
        "city": "Hà Nội",
        "address": "Ngõ 121 Chùa Láng, Phường Láng Thượng, Quận Đống Đa, Hà Nội",
        "price": 3200000,
        "price_display": "3.2 triệu VNĐ/tháng",
        "room_type": "Phòng trọ",
        "area": "20m2",
        "amenities": ["Điều hòa", "Nóng lạnh", "Để xe tầng 1", "Giờ giấc tự do"],
        "utilities": "Điện 3.5k/kWh, Nước 80k/người",
        "deposit": "1 tháng tiền phòng",
        "landlord_phone": "0977-333-444 (Bác Tuấn)",
        "available_slots": ["08:30", "12:00", "17:30"],
        "status": "Còn phòng"
    },
    {
        "id": "AP-105",
        "title": "Căn hộ 2PN Vinhomes Smart City Nam Từ Liêm",
        "location": "Nam Từ Liêm, Hà Nội",
        "district": "Nam Từ Liêm",
        "city": "Hà Nội",
        "address": "Tòa S2.01 Vinhomes Smart City, Tây Mỗ, Nam Từ Liêm, Hà Nội",
        "price": 8500000,
        "price_display": "8.5 triệu VNĐ/tháng",
        "room_type": "2PN",
        "area": "64m2",
        "amenities": ["2 Phòng ngủ", "2 WC", "Điều hòa Multi", "Bếp từ âm", "Hệ sinh thái Vin", "Xe bus nội khu"],
        "utilities": "Giá công tơ điện nước nhà nước + Phí quản lý",
        "deposit": "1 tháng tiền phòng",
        "landlord_phone": "0936-555-777 (Chị Hằng)",
        "available_slots": ["09:00", "15:00", "18:30"],
        "status": "Còn phòng"
    }
]

# Lưu trữ danh sách đặt lịch giả lập trong bộ nhớ
BOOKINGS_DB = {
    "BK-8821": {
        "booking_id": "BK-8821",
        "apartment_id": "AP-102",
        "apartment_title": "Căn hộ Studio Studio ban công rộng view đẹp Bình Thạnh",
        "customer_name": "Nguyễn Văn A",
        "phone": "0912345678",
        "viewing_date": "30/07/2026",
        "viewing_time": "09:30",
        "status": "Đã xác nhận - Chờ xem nhà"
    }
}


def _parse_price_value(price_input) -> float:
    """Helper chuyển đổi chuỗi giá (e.g. '5 triệu', '5000000', '8tr') thành con số int/float"""
    if isinstance(price_input, (int, float)):
        return float(price_input)
    if not price_input:
        return float("inf")
    
    text = str(price_input).lower().strip()
    # Tìm dạng 5000000
    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    if not numbers:
        return float("inf")
    
    val = float(numbers[0])
    if "triệu" in text or "tr" in text or "m" in text:
        if val < 1000:
            val = val * 1000000
    elif val < 1000 and "ngàn" not in text and "k" not in text:
        val = val * 1000000
        
    return val


def search_apartments(location: str = "", max_price: str = "", room_type: str = "") -> str:
    """
    Tìm kiếm nhà trọ / căn hộ cho thuê theo khu vực, giá tối đa và loại phòng.
    
    Args:
        location (str): Khu vực hoặc quận/huyện (Ví dụ: 'Cầu Giấy', 'Bình Thạnh', 'Hà Nội', 'TP.HCM')
        max_price (str): Ngân sách tối đa (Ví dụ: '5000000', '5 triệu', '8tr')
        room_type (str): Loại phòng (Ví dụ: 'Studio', '1PN', '2PN', 'Phòng trọ')
        
    Returns:
        str: Danh sách căn hộ phù hợp kèm Mã phòng (ID), Giá, Địa chỉ và Tiện ích.
    """
    try:
        loc_clean = location.strip().lower() if location else ""
        room_clean = room_type.strip().lower() if room_type else ""
        price_limit = _parse_price_value(max_price)
        
        matches = []
        for ap in SAMPLE_APARTMENTS:
            # Check location
            loc_match = True
            if loc_clean:
                search_space = f"{ap['location']} {ap['district']} {ap['city']} {ap['address']}".lower()
                loc_match = any(term in search_space for term in loc_clean.split())
                
            # Check room type
            type_match = True
            if room_clean:
                type_match = room_clean in ap['room_type'].lower() or room_clean in ap['title'].lower()
                
            # Check price
            price_match = ap['price'] <= price_limit
            
            if loc_match and type_match and price_match:
                matches.append(ap)
                
        if not matches:
            return (
                f"LỖI KHÔNG TÌM THẤY: Không có phòng trọ/căn hộ nào khớp với tiêu chí "
                f"[Khu vực: '{location}', Giá tối đa: '{max_price}', Loại: '{room_type}']. "
                f"Gợi ý: Thử mở rộng khu vực tìm kiếm hoặc tăng ngân sách."
            )
            
        res = [f"🔍 TÌM THẤY {len(matches)} CĂN HỘ Phù Hợp:"]
        for item in matches:
            res.append(
                f"- [MÃ: {item['id']}] {item['title']}\n"
                f"  📍 Địa chỉ: {item['address']}\n"
                f"  💰 Giá thuê: {item['price_display']} | Loại: {item['room_type']} ({item['area']})\n"
                f"  ✨ Tiện ích: {', '.join(item['amenities'][:4])}"
            )
        return "\n\n".join(res)
    except Exception as e:
        return f"LỖI THỰC THI TOOL search_apartments: {str(e)}"


def get_apartment_details(apartment_id: str) -> str:
    """
    Xem thông tin chi tiết đầy đủ của một căn hộ theo Mã phòng (ID).
    
    Args:
        apartment_id (str): Mã căn hộ (Ví dụ: 'AP-101', 'AP-102', 'AP-103')
        
    Returns:
        str: Chi tiết tiện ích, chi phí dịch vụ, tiền cọc, SĐT chủ nhà và các khung giờ xem nhà.
    """
    try:
        ap_id_clean = apartment_id.strip().upper()
        # Handle cases like get_apartment_details['AP-101']
        ap_id_clean = re.sub(r'[\'\"\[\]]', '', ap_id_clean)
        
        found = None
        for ap in SAMPLE_APARTMENTS:
            if ap['id'].upper() == ap_id_clean:
                found = ap
                break
                
        if not found:
            valid_ids = [a['id'] for a in SAMPLE_APARTMENTS]
            return f"LỖI: Không tìm thấy căn hộ có mã '{apartment_id}'. Danh sách mã hợp lệ: {valid_ids}."
            
        return (
            f"🏢 CHI TIẾT CĂN HỘ [MÃ: {found['id']}]\n"
            f"📌 Tên: {found['title']}\n"
            f"📍 Địa chỉ: {found['address']}\n"
            f"💵 Giá thuê: {found['price_display']} (Cọc: {found['deposit']})\n"
            f"📐 Diện tích: {found['area']} | Loại phòng: {found['room_type']}\n"
            f"⚡ Phí dịch vụ: {found['utilities']}\n"
            f"🛋️ Tiện ích: {', '.join(found['amenities'])}\n"
            f"📞 Liên hệ chính chủ/quản lý: {found['landlord_phone']}\n"
            f"⏰ Khung giờ xem nhà trống: {', '.join(found['available_slots'])}\n"
            f"🟢 Trạng thái: {found['status']}"
        )
    except Exception as e:
        return f"LỖI THỰC THI TOOL get_apartment_details: {str(e)}"


def book_viewing_schedule(apartment_id: str, customer_name: str, phone: str, viewing_date: str, viewing_time: str) -> str:
    """
    Đặt lịch hẹn đi xem nhà trọ / căn hộ trực tiếp.
    
    Args:
        apartment_id (str): Mã căn hộ (Ví dụ: 'AP-102')
        customer_name (str): Họ tên khách hàng (Ví dụ: 'Nguyễn Văn A')
        phone (str): Số điện thoại liên hệ (Ví dụ: '0912345678')
        viewing_date (str): Ngày xem nhà (Ví dụ: '30/07/2026' hoặc 'Ngày mai')
        viewing_time (str): Giờ xem nhà (Ví dụ: '09:30', '15:00')
        
    Returns:
        str: Mã xác nhận đặt lịch hẹn thành công hoặc thông báo lỗi.
    """
    try:
        ap_id_clean = re.sub(r'[\'\"\[\]]', '', str(apartment_id)).strip().upper()
        
        found = None
        for ap in SAMPLE_APARTMENTS:
            if ap['id'].upper() == ap_id_clean:
                found = ap
                break
                
        if not found:
            return f"LỖI ĐẶT LỊCH: Mã căn hộ '{apartment_id}' không tồn tại trong hệ thống!"
            
        booking_code = f"BK-{len(BOOKINGS_DB) + 8821}"
        booking_record = {
            "booking_id": booking_code,
            "apartment_id": found['id'],
            "apartment_title": found['title'],
            "customer_name": customer_name,
            "phone": phone,
            "viewing_date": viewing_date,
            "viewing_time": viewing_time,
            "status": "Đã xác nhận - Chờ xem nhà"
        }
        BOOKINGS_DB[booking_code] = booking_record
        
        return (
            f"🎉 ĐẶT LỊCH XEM NHÀ THÀNH CÔNG!\n"
            f"🎫 Mã lịch hẹn: {booking_code}\n"
            f"🏠 Căn hộ: [{found['id']}] {found['title']}\n"
            f"📍 Địa chỉ xem: {found['address']}\n"
            f"👤 Khách hàng: {customer_name} (SĐT: {phone})\n"
            f"📅 Thời gian hẹn: {viewing_time} ngày {viewing_date}\n"
            f"📞 Hotline hỗ trợ xem nhà: {found['landlord_phone']}"
        )
    except Exception as e:
        return f"LỖI THỰC THI TOOL book_viewing_schedule: {str(e)}"


def check_schedule_status(booking_id_or_phone: str) -> str:
    """
    Tra cứu trạng thái lịch hẹn xem nhà đã đặt theo Mã lịch hẹn hoặc Số điện thoại.
    
    Args:
        booking_id_or_phone (str): Mã lịch hẹn (e.g. 'BK-8821') hoặc SĐT đăng ký
        
    Returns:
        str: Thông tin trạng thái lịch hẹn xem nhà.
    """
    try:
        query = re.sub(r'[\'\"\[\]]', '', str(booking_id_or_phone)).strip()
        
        matches = []
        for bk in BOOKINGS_DB.values():
            if bk['booking_id'].upper() == query.upper() or query in bk['phone']:
                matches.append(bk)
                
        if not matches:
            return f"THÔNG BÁO: Không tìm thấy lịch hẹn nào tương ứng với thông tin '{booking_id_or_phone}'."
            
        res = [f"📋 KẾT QUẢ TRA CỨU LỊCH HẸN ({len(matches)} lịch hẹn):"]
        for bk in matches:
            res.append(
                f"- [Mã: {bk['booking_id']}] Căn hộ: {bk['apartment_title']}\n"
                f"  Khách hàng: {bk['customer_name']} ({bk['phone']})\n"
                f"  Lịch hẹn: {bk['viewing_time']} ngày {bk['viewing_date']}\n"
                f"  Trạng thái: {bk['status']}"
            )
        return "\n\n".join(res)
    except Exception as e:
        return f"LỖI THỰC THI TOOL check_schedule_status: {str(e)}"


# Backward compatibility helpers (keep old tools registered so no breaking changes if referenced)
def get_weather(location: str) -> str:
    """Tra cứu thời tiết hỗ trợ phụ"""
    return f"Thời tiết tại {location}: 29°C, Nắng nhẹ, Mát mẻ."

def search_flights(origin: str, destination: str) -> str:
    """Tra cứu chuyến bay hỗ trợ phụ"""
    return f"Chuyến bay {origin} -> {destination}: Khởi hành 08:00 - Giá 1.500.000 VNĐ."


# Registry các tool khả dụng cho ReAct Agent
AVAILABLE_TOOLS = {
    "search_apartments": search_apartments,
    "get_apartment_details": get_apartment_details,
    "book_viewing_schedule": book_viewing_schedule,
    "check_schedule_status": check_schedule_status,
    "get_weather": get_weather,
    "search_flights": search_flights
}
