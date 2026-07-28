# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)
*Chủ đề: Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê (Lab 03)*

---

## 🎯 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1-5) | Lý do đánh giá |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | `5/5` | Cần suy luận từ tra cứu khu vực -> xem chi tiết tiện ích/giá cọc -> xác định lịch trống -> thực hiện đặt xem nhà. |
| 🛠️ **Tool Interaction** | `5/5` | Bắt buộc truy vấn CSDL phòng trọ thời gian thực và ghi nhận thông tin đặt lịch hẹn qua Tool APIs. |
| 🔀 **Dynamic Decision** | `5/5` | Kết quả tra cứu ở bước trước (Mã phòng, tình trạng phòng) quyết định trực tiếp hành động xem nhà ở bước sau. |
| ⏳ **Long Horizon** | `4/5` | Quy trình hoàn tất yêu cầu gồm từ 2 đến 4 bước luân phiên Thought-Action-Observation. |
| **TỔNG ĐIỂM FIT** | **19/20** | **KẾT LUẬN: BÀI TOÁN RẤT NÊN DÙNG REACT AGENT!** |

---

## 🔍 2. SO SÁNH CHATBOT BASELINE VS REACT AGENT

### 🟢 Test Case #1: Hỏi kinh nghiệm thuê nhà (Đơn giản - Chỉ cần LLM)
* **Câu hỏi**: *"Cho mình xin 3 kinh nghiệm quan trọng nhất khi tân sinh viên tìm thuê phòng trọ lần đầu?"*
* **Chatbot Baseline**: Trả lời ngay 3 lời khuyên hữu ích về hợp đồng, chi phí và an ninh. (Thời gian phản hồi nhanh, 0 lần gọi Tool).
* **ReAct Agent**: Đưa ra câu trả lời trực tiếp mà không cần gọi tool.
* **Đánh giá**: Với câu hỏi lý thuyết, cả hai đều hoàn thành tốt.

---

### 🟡 Test Case #3: Tra cứu phòng trọ Cầu Giấy dưới 5 triệu (Single-Step Tool)
* **Câu hỏi**: *"Tìm giúp tôi phòng trọ hoặc căn hộ cho thuê ở quận Cầu Giấy giá dưới 5 triệu/tháng."*
* **Chatbot Baseline**: 
  - *Phản hồi*: *"Tôi không có truy cập dữ liệu thời gian thực nên không thể tìm danh sách phòng trọ cụ thể ở Cầu Giấy cho bạn."*
  - *Nhận xét*: Thất bại vì không truy cập được dữ liệu phòng trọ thực tế.
* **ReAct Agent Trace Log**:
  - **Step 1**:
    - `Thought`: Cần tìm kiếm phòng trọ ở Cầu Giấy giá dưới 5 triệu.
    - `Action`: `search_apartments['Cầu Giấy', '5000000']`
    - `Observation`: `🔍 TÌM THẤY 1 CĂN HỘ Phù Hợp: - [MÃ: AP-101] Phòng trọ khép kín full đồ mới 100% Cầu Giấy | Giá: 4.5 triệu VNĐ/tháng`
  - **Final Answer**: Đã tìm thấy phòng trọ khép kín AP-101 tại Cầu Giấy giá 4.5 triệu/tháng đầy đủ nội thất.
  - *Nhận xét*: Hoàn thành chính xác nhờ gọi tool dữ liệu thật.

---

### 🟡 Test Case #4: Tìm phòng, xem chi tiết và đặt lịch xem nhà (Multi-Step Tools)
* **Câu hỏi**: *"Tìm căn hộ 1PN ở Bình Thạnh giá dưới 8 triệu, xem chi tiết căn phù hợp nhất và đặt lịch xem nhà lúc 09:30 sáng ngày 30/07/2026 cho Nguyễn Văn A, SĐT 0912345678."*
* **Chatbot Baseline**: Phản hồi ảo giác hoặc thông báo không thể thực hiện đặt lịch trên hệ thống.
* **ReAct Agent Trace Log**:
  - **Step 1**:
    - `Thought`: Cần tìm căn hộ 1PN / Studio ở Bình Thạnh giá dưới 8 triệu.
    - `Action`: `search_apartments['Bình Thạnh', '8000000', '1PN']`
    - `Observation`: `TÌM THẤY Căn hộ Studio AP-102 (7.2 triệu VNĐ/tháng)`
  - **Step 2**:
    - `Thought`: Đã tìm thấy căn AP-102 phù hợp, tiếp theo xem chi tiết căn này.
    - `Action`: `get_apartment_details['AP-102']`
    - `Observation`: `CHI TIẾT AP-102 | Giá 7.2tr | Khung giờ xem trống: 09:30, 10:30...`
  - **Step 3**:
    - `Thought`: Đã xem chi tiết căn AP-102, tiến hành đặt lịch xem nhà cho khách hàng.
    - `Action`: `book_viewing_schedule['AP-102', 'Nguyễn Văn A', '0912345678', '30/07/2026', '09:30']`
    - `Observation`: `🎉 ĐẶT LỊCH XEM NHÀ THÀNH CÔNG! Mã lịch hẹn: BK-8821`
  - **Final Answer**: Đã đặt lịch xem nhà thành công mã **BK-8821** lúc 09:30 ngày 30/07/2026 cho anh Nguyễn Văn A tại căn hộ AP-102!
  - *Nhận xét*: Xuất sắc đi qua chuỗi 3 công cụ liên tiếp thành công 100%.

---

### 🔴 Test Case #5: Edge Case & Guardrail (Bẫy tham số vô lý)
* **Câu hỏi**: *"Tôi muốn xem thông tin và đặt lịch xem căn hộ mã AP-99999 ở khu vực Sao Hỏa vào ngày 32/13/2026."*
* **ReAct Agent Trace Log**:
  - **Step 1**:
    - `Thought`: Tra cứu thông tin mã căn hộ AP-99999.
    - `Action`: `get_apartment_details['AP-99999']`
    - `Observation`: `LỖI: Không tìm thấy căn hộ có mã 'AP-99999'. Danh sách mã hợp lệ: ['AP-101', 'AP-102', 'AP-103', 'AP-104', 'AP-105'].`
  - **Final Answer**: Rất tiếc, mã căn hộ AP-99999 không tồn tại trong hệ thống. Vui lòng kiểm tra lại mã phòng hợp lệ.
  - *Nhận xét*: Tool tự bắt lỗi an toàn, Agent không bị crash code hay lặp vô tận.

---

## 📈 3. BẢNG TỔNG HỢP ĐÁNH GIÁ (SCORING RUBRIC 0-2)

| Test Case | System | Factual Correctness (0-2) | Grounding (0-2) | Tool Selection (0-2) | Termination (0-2) | Tổng điểm |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **#1 (Lý thuyết)** | Baseline Chatbot | 2 | 1 | 2 (Không gọi tool) | 2 | **7/8** |
| | ReAct Agent | 2 | 2 | 2 (Không gọi tool) | 2 | **8/8** |
| **#3 (1 Tool)** | Baseline Chatbot | 0 | 0 | 0 | 2 | **2/8** |
| | ReAct Agent | 2 | 2 | 2 | 2 | **8/8** |
| **#4 (Multi-step)** | Baseline Chatbot | 0 | 0 | 0 | 2 | **2/8** |
| | ReAct Agent | 2 | 2 | 2 | 2 | **8/8** |
| **#5 (Edge Case)** | Baseline Chatbot | 0 | 0 | 0 | 2 | **2/8** |
| | ReAct Agent | 2 | 2 | 2 | 2 | **8/8** |
