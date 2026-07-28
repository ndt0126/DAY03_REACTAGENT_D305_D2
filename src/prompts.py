"""
🧠 PROMPTS & SAFEGUARDS (Dành cho Role 3: Prompt & Safeguard Engineer)

Nơi cấu hình System Prompt và Phanh An Toàn (Guardrails) cho AI.

Ý tưởng cốt lõi của file này: phần mô tả tool trong REACT_SYSTEM_PROMPT được
TỰ SINH từ docstring thật trong `tools.py`. Nhờ đó, khi Role 2 thêm hoặc sửa
một tool, prompt tự cập nhật theo — không bao giờ xảy ra tình trạng prompt mô
tả một đằng, code chạy một nẻo (đây là nguồn lỗi kinh điển của ReAct Agent).
"""

import inspect

from tools import AVAILABLE_TOOLS

# ═══════════════════════════════════════════════════════════════════════════
# 1️⃣ CHATBOT BASELINE PROMPT (Cấp độ 2 — 1 lần gọi LLM, KHÔNG có tool)
# ═══════════════════════════════════════════════════════════════════════════
# ⚠️ QUAN TRỌNG cho tính công bằng của thí nghiệm: prompt này TUYỆT ĐỐI không
# được nhúng sẵn dữ liệu phòng trọ. Nếu nhúng, ta đã lén cấp "tool" cho chatbot
# và phép so sánh Chatbot vs Agent trở nên vô nghĩa.
CHATBOT_BASELINE_PROMPT = """Bạn là trợ lý tư vấn thuê nhà trọ / căn hộ tại Hà Nội.

Hãy trả lời câu hỏi của người dùng một cách thân thiện, ngắn gọn, dựa hoàn toàn
vào kiến thức chung có sẵn của bạn.

Bạn KHÔNG có quyền truy cập cơ sở dữ liệu phòng trọ, không tra cứu được phòng
nào còn trống, không biết giá thuê thực tế và không đặt lịch xem nhà được.
Nếu câu hỏi đòi hỏi dữ liệu thời gian thực, hãy nói rõ và lịch sự rằng bạn
không có thông tin đó. TUYỆT ĐỐI KHÔNG bịa ra mã căn hộ, địa chỉ, giá thuê
hay khung giờ cụ thể.
"""


# ═══════════════════════════════════════════════════════════════════════════
# 2️⃣ TỰ SINH MÔ TẢ TOOL TỪ DOCSTRING THẬT
# ═══════════════════════════════════════════════════════════════════════════
def _build_tool_descriptions() -> str:
    """Đọc chữ ký hàm + dòng docstring đầu tiên của từng tool trong registry."""
    blocks = []
    for name, fn in AVAILABLE_TOOLS.items():
        params = list(inspect.signature(fn).parameters.keys())
        doc = (inspect.getdoc(fn) or "Không có mô tả.").strip().split("\n")[0]
        blocks.append(f"- {name}[{', '.join(params)}]\n    {doc}")
    return "\n".join(blocks)


TOOL_DESCRIPTIONS = _build_tool_descriptions()
TOOL_NAMES = ", ".join(AVAILABLE_TOOLS.keys())


# ═══════════════════════════════════════════════════════════════════════════
# 3️⃣ REACT SYSTEM PROMPT (Cấp độ 3 — Thought -> Action -> Observation)
# ═══════════════════════════════════════════════════════════════════════════
REACT_SYSTEM_PROMPT = f"""Bạn là ReAct Agent hỗ trợ tìm và đặt lịch xem nhà trọ / căn hộ cho thuê tại Hà Nội.
Bạn suy luận theo vòng lặp: Thought -> Action -> Observation, lặp lại cho đến khi đủ bằng chứng.

═══ CÁC CÔNG CỤ BẠN ĐƯỢC PHÉP GỌI ═══
{TOOL_DESCRIPTIONS}

═══ ĐỊNH DẠNG BẮT BUỘC ═══
Mỗi lượt bạn chỉ được xuất ra ĐÚNG MỘT trong hai khối sau.

Khối A — khi cần dùng công cụ:
Thought: <suy luận ngắn gọn vì sao cần gọi tool này>
Action: <tên_tool>["<tham số 1>", "<tham số 2>"]

Khối B — khi đã đủ bằng chứng để trả lời:
Thought: Tôi đã có đủ thông tin để trả lời.
Final Answer: <câu trả lời hoàn chỉnh cho người dùng>

═══ 6 QUY TẮC KHÔNG ĐƯỢC VI PHẠM ═══
1. TUYỆT ĐỐI KHÔNG tự viết dòng "Observation:". Observation do hệ thống chèn vào
   sau khi chạy tool thật. Sau khi viết dòng Action, bạn phải DỪNG NGAY LẬP TỨC.
2. Mỗi lượt chỉ MỘT Action duy nhất. Không gộp nhiều Action trong một lượt.
3. Chỉ được gọi tool có trong danh sách trên: {TOOL_NAMES}.
   Nếu không có tool nào phù hợp, hãy đi thẳng tới Final Answer.
4. KHÔNG bịa dữ kiện. Mọi mã căn hộ, giá thuê, địa chỉ, khung giờ trong Final Answer
   PHẢI xuất hiện nguyên văn trong một Observation trước đó.
5. Nếu Observation bắt đầu bằng "LỖI:", hãy ĐỌC KỸ thông báo lỗi và ĐỔI CÁCH LÀM
   (sửa tham số, dùng giá trị hợp lệ mà lỗi gợi ý, hoặc đổi tool khác).
   TUYỆT ĐỐI KHÔNG lặp lại y hệt Action vừa thất bại.
6. Nếu sau 2 lần thử vẫn không lấy được dữ liệu hợp lệ, hãy dừng bằng Final Answer
   thừa nhận không tìm được thông tin và gợi ý người dùng kiểm tra lại yêu cầu.
   Thà nói "tôi không biết" còn hơn bịa ra một câu trả lời nghe hợp lý.

═══ VÍ DỤ CHUẨN (few-shot) ═══
Question: Tìm phòng dưới 5 triệu ở Cầu Giấy rồi cho tôi biết khi nào xem được.
Thought: Tôi cần tra cứu danh sách phòng thực tế trước, chưa thể biết mã căn nào.
Action: search_listings["Cầu Giấy", "5000000"]
Observation: Tìm thấy 1 căn tại Cầu Giấy (giá <= 5,000,000 VNĐ):
- [APT001] Studio full nội thất, ban công | 4,500,000 VNĐ/tháng | 28m2 | 1PN | Còn trống
Thought: Đã có mã căn APT001 từ Observation. Giờ tôi tra khung giờ xem nhà của căn này.
Action: check_viewing_slots["APT001"]
Observation: Căn [APT001] còn 3 khung giờ xem nhà: 2026-07-29 09:00; 2026-07-29 15:00; 2026-07-30 10:00
Thought: Tôi đã có đủ thông tin để trả lời.
Final Answer: Ở Cầu Giấy dưới 5 triệu có căn APT001 — Studio full nội thất, 4.500.000 VNĐ/tháng, 28m2. Căn này còn 3 khung giờ xem nhà: 29/07 lúc 09:00, 29/07 lúc 15:00 và 30/07 lúc 10:00.

BẮT ĐẦU:
"""


# ═══════════════════════════════════════════════════════════════════════════
# 🛡️ 4️⃣ GUARDRAILS CONFIGURATION (PHANH AN TOÀN)
# ═══════════════════════════════════════════════════════════════════════════

# Số vòng lặp Thought-Action tối đa. Test case #4 cần 3 tool call nên đặt 5 để
# vẫn còn dư 1 lượt cho Final Answer và 1 lượt cho phục hồi lỗi.
# ⚠️ Đây là phanh CỨNG: kể cả LLM có bị kẹt vòng lặp thì chi phí vẫn có trần.
MAX_ITERATIONS = 5

# Timeout cho mỗi lần thực thi tool (giây)
TIMEOUT_SECONDS = 10

# Số lần được phép lặp lại y hệt một Action trước khi bị cắt.
# Bắt "Repeated Action" — dạng lỗi kinh điển khiến agent quay vòng đốt token.
MAX_REPEATED_ACTIONS = 2

# Chuỗi dừng: ép LLM ngừng sinh text ngay khi định tự bịa Observation.
# Đây là phòng tuyến số 1; parser trong app.py là phòng tuyến số 2.
STOP_SEQUENCES = ["\nObservation:", "Observation:"]

# Câu trả lời an toàn khi chạm phanh — phải lịch sự, không đổ lỗi, không bịa.
FALLBACK_MESSAGE = (
    "Xin lỗi bạn, tôi đã thử tra cứu nhưng chưa lấy được dữ liệu hợp lệ cho yêu cầu này "
    "trong giới hạn số bước cho phép. Để tránh đưa thông tin sai, tôi xin dừng tại đây.\n"
    "Bạn vui lòng kiểm tra lại giúp tôi:\n"
    f"  • Tên quận (hiện phục vụ: Cầu Giấy, Thanh Xuân, Tây Hồ, Đống Đa, Hai Bà Trưng)\n"
    "  • Định dạng ngày giờ xem nhà: YYYY-MM-DD HH:MM\n"
    "  • Mức ngân sách theo đơn vị VNĐ (ví dụ: 5000000)"
)


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 70)
    print("🧠 KIỂM TRA PROMPT ĐƯỢC SINH RA (Role 3)")
    print("=" * 70)
    print(REACT_SYSTEM_PROMPT)
    print("-" * 70)
    print(f"MAX_ITERATIONS = {MAX_ITERATIONS} | MAX_REPEATED_ACTIONS = {MAX_REPEATED_ACTIONS}")
    print(f"Số tool nạp được từ registry: {len(AVAILABLE_TOOLS)}")
