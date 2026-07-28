# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)

*Dành cho Role 5: Observability & Reviewer*  
*Chủ đề: Trợ lý tìm và đặt lịch xem nhà trọ/căn hộ cho thuê*

**Nguồn log:** `rubric.md`  
**Provider / model:** `CompatibleProvider` / `openai/gpt-oss-120b`  
**Thời điểm chạy:** 28/07/2026, 15:04:39  
**Guardrails:** `MAX_ITERATIONS=8`, `MAX_REPEATED_ACTIONS=2`

---

## 🎯 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1–5) | Lý do đánh giá |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | 5/5 | Quy trình đầy đủ gồm tìm căn, chọn căn, kiểm tra lịch trống, đặt lịch và xác nhận. |
| 🛠️ **Tool Interaction** | 5/5 | Giá, địa chỉ, UUID và lịch hẹn nằm trong dữ liệu của hệ thống; `book_viewing` còn ghi lịch thật. |
| 🔀 **Dynamic Decision** | 5/5 | UUID từ `search_listings` là đầu vào của `check_viewing_slots`; khung giờ từ bước này lại là đầu vào của `book_viewing`. |
| ⏳ **Long Horizon** | 4/5 | Nhiệm vụ kéo dài 2–4 bước và có thể tiếp tục qua nhiều lượt hội thoại. |
| **TỔNG ĐIỂM FIT** | **19/20** | **KẾT LUẬN: BÀI TOÁN RẤT PHÙ HỢP VỚI REACT AGENT.** |

Mình cho điểm này dựa trên cảm giác, có thể chưa giống với điểm chương trình đề xuất.

---



## 🔍 2. SO SÁNH PHẢN HỒI (TEST CASE #3)

**Câu hỏi:** *“Tìm giúp tôi căn hộ ở quận Cầu Giấy có giá thuê dưới 8 triệu mỗi tháng.”*

### 🤖 Chatbot Baseline

- **Phản hồi:** “Mình rất muốn giúp bạn tìm được căn hộ phù hợp, nhưng hiện tại mình không có quyền truy cập vào cơ sở dữ liệu thực tế nên không thể đưa ra danh sách các căn hộ cụ thể, địa chỉ hay mức giá chính xác.”
- **Telemetry:** `llm_calls=1`, `tool_calls=0`.
- **Điểm:** **2/8**.
- **Nhận xét:** Câu trả lời an toàn và không bịa dữ liệu, nhưng chỉ đưa ra hướng dẫn chung nên không giải quyết được yêu cầu tra cứu.

### 🧠 ReAct Agent

```text
Thought: Tôi cần tìm các căn hộ cho thuê ở quận Cầu Giấy với giá tối đa
         8 triệu đồng mỗi tháng.

Action: search_listings['Cầu Giấy', '8000000', '', '', '', '']

Observation: Tìm thấy 287 căn khớp tiêu chí
             (quận Cầu Giấy; giá <= 8,000,000 VNĐ).
             Hiển thị 5 căn giá thấp nhất:
             1. 607D Dịch Vọng Hậu — 1,200,000 VNĐ/tháng — 23m2
             2. 923E Trần Duy Hưng — 1,500,000 VNĐ/tháng — 20m2
             3. 617B Xuân Thủy — 1,500,000 VNĐ/tháng — 47m2
             4. 898A Xuân Thủy — 1,500,000 VNĐ/tháng — 36m2
             5. 212E Xuân Thủy — 1,700,000 VNĐ/tháng — 78m2

Thought: Tôi đã có đủ thông tin để trả lời.

Final Answer: Hệ thống tìm được 287 căn phù hợp và trả về 5 căn có giá thấp nhất,
              kèm UUID, địa chỉ, giá, diện tích và tiện ích.
```

- **Telemetry:** `llm_calls=2`, `tool_calls=1`, `stop_reason=final_answer`.
- **Điểm:** **8/8**.
- **Nhận xét:** Agent hoàn thành yêu cầu nhờ một tool call; các dữ kiện trong câu trả lời đều truy ngược được về Observation.

---

## 🔗 3. TRACE NHIỀU BƯỚC HOÀN CHỈNH (TEST CASE #5)

**Câu hỏi:** *“Tìm căn rẻ nhất ở quận Thanh Xuân dưới 5 triệu, diện tích tối đa 60m2 và gần trường học. Sau đó xem giúp tôi ngày mai còn khung giờ nào trống rồi đặt lịch xem nhà sớm nhất cho tôi. Tên tôi là Nguyễn Quang Minh, số điện thoại 0912345678.”*

```text
Step 1
Thought: Cần tìm các căn ở Thanh Xuân thỏa toàn bộ bộ lọc.
Action: search_listings['Thanh Xuân', '5000000', '', '60', 'trường học', '']
Observation: Tìm thấy 77 căn.
             Căn rẻ nhất:
             [904d4b60-333c-48a8-b882-171c3ce07db5]
             259C Lê Văn Lương, Thanh Xuân
             1,300,000 VNĐ/tháng, 35m2, gần trường học.

Step 2
Thought: Dùng UUID của căn rẻ nhất để kiểm tra lịch ngày mai.
Action: check_viewing_slots[
          '904d4b60-333c-48a8-b882-171c3ce07db5',
          '2026-07-29'
        ]
Observation: Còn 10/10 khung giờ từ 08:00 đến 17:00.
             Khung sớm nhất là 08:00.

Step 3
Thought: Đặt khung sớm nhất cho khách bằng thông tin đã cung cấp.
Action: book_viewing[
          '904d4b60-333c-48a8-b882-171c3ce07db5',
          '2026-07-29',
          '08:00',
          'Nguyễn Quang Vinh',
          '0912345678'
        ]
Observation: ĐẶT LỊCH THÀNH CÔNG!
             Mã xác nhận: BK00136
             Lịch hẹn đã được ghi vào hệ thống.

Final Answer: Xác nhận căn 259C Lê Văn Lương, thời gian 08:00 ngày 29/07/2026,
              khách Nguyễn Quang Vinh, mã đặt lịch BK00136.
```

**Telemetry:** `llm_calls=4`, `tool_calls=3`, `stop_reason=final_answer`  
**Điểm:** **8/8**

### Bằng chứng Dynamic Decision

| Giá trị | Nguồn | Được dùng ở bước sau |
| :--- | :--- | :--- |
| UUID `904d4b60-...` | Observation của `search_listings` | `check_viewing_slots` và `book_viewing` |
| `2026-07-29`, `08:00` | Observation của `check_viewing_slots` | `book_viewing` |
| `BK00136` | Observation của `book_viewing` | Final Answer |

Không giá trị nào trong ba nhóm trên có thể được suy ra đáng tin cậy chỉ từ kiến thức của LLM.

---

## 📈 4. KẾT QUẢ RUBRIC 0–2

| Case | Hệ thống | Factual | Grounding | Tool selection | Termination | Tổng |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| #1 | Baseline | 2 | 2 | 2 | 2 | 8/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #2 | Baseline | 2 | 2 | 2 | 2 | 8/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #3 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #4 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #5 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #6 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 1 | 0 | 2 | 5/8 |
| #7 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #8 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 1 | 2 | 2 | 7/8 |
| #9 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #10 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 1 | 2 | 2 | 7/8 |
| #11 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 1 | 0 | 2 | 5/8 |
| #12 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| #13 | Baseline | 0 | 0 | 0 | 2 | 2/8 |
| | ReAct Agent | 2 | 2 | 2 | 2 | 8/8 |
| **Tổng** | **Baseline** | **4/26** | **4/26** | **4/26** | **26/26** | **38/104** |
| | **ReAct Agent** | **26/26** | **22/26** | **22/26** | **26/26** | **96/104** |

### Telemetry của ReAct Agent

| Case | LLM calls | Tool calls | Stop reason |
| :---: | :---: | :---: | :--- |
| #1 | 1 | 0 | `final_answer` |
| #2 | 1 | 0 | `final_answer` |
| #3 | 2 | 1 | `final_answer` |
| #4 | 2 | 1 | `final_answer` |
| #5 | 4 | 3 | `final_answer` |
| #6 | 1 | 0 | `final_answer` |
| #7 | 2 | 1 | `final_answer` |
| #8 | 3 | 2 | `final_answer` |
| #9 | 2 | 1 | `final_answer` |
| #10 | 2 | 1 | `final_answer` |
| #11 | 1 | 0 | `final_answer` |
| #12 | 2 | 1 | `final_answer` |
| #13 | 2 | 1 | `final_answer` |
| **Tổng** | **25** | **12** | **13/13 `final_answer`** |

---

## ⚠️ 5. PHÂN TÍCH CÁC CASE CHƯA ĐẠT TỐI ĐA

| Case | Điểm | Quan sát từ trace | Đề xuất |
| :---: | :---: | :--- | :--- |
| #6 | 5/8 | Agent yêu cầu người dùng chỉ rõ căn cần xem và không gọi tool. Câu trả lời an toàn nhưng lệch kỳ vọng 1–3 tool calls của rubric. | Thống nhất lại rubric: chấp nhận hỏi làm rõ hoặc bắt buộc gọi một validation tool. |
| #8 | 7/8 | Agent tìm căn và kiểm tra lịch đúng, sau đó hỏi tên/SĐT; Final Answer không nhắc lại căn và khung giờ từ Observation. | Khi hỏi bổ sung thông tin, tóm tắt lại căn đã chọn và trạng thái 09:00. |
| #10 | 7/8 | Tool trả kết quả rỗng hợp lệ; Agent không bịa căn hộ nhưng Grounding chỉ đạt 1/2. | Final Answer nên nhắc nguyên văn các tiêu chí đã kiểm tra và xác nhận “0 kết quả”. |
| #11 | 5/8 | Agent nhận ra quận và ngày vô lý ngay trong LLM, không gọi tool nên không có controlled failure trong trace. | Chấp nhận validation sớm hoặc thêm tool `validate_request` để tạo bằng chứng kiểm tra. |

### Trạng thái guardrail trong lần chạy này

- `MAX_ITERATIONS=8` và `MAX_REPEATED_ACTIONS=2` đã được cấu hình.
- Không case nào kích hoạt `max_iterations` hoặc `repeated_action`.
- Cả 13 case đều dừng bằng `final_answer`.

Vì vậy, log này chứng minh khả năng kết thúc của các luồng được kiểm thử, nhưng chưa trực tiếp chứng minh nhánh ngắt lặp. Cần một test riêng cố tình khiến model lặp cùng Action để kiểm chứng guardrail đó.

---

## 🧠 6. BẰNG CHỨNG MEMORY QUA NHIỀU LƯỢT

Trong hội thoại năm lượt ở cuối `rubric.md`, Agent tìm được UUID:

```text
35367165-a9b0-4b49-abe6-c04382755189
```

Các lượt sau, người dùng chỉ nói “căn đầu tiên” và “căn đó”, nhưng Agent vẫn:

1. Lấy đúng chi tiết căn tại 607D Dịch Vọng Hậu, Cầu Giấy.
2. Kiểm tra đúng lịch ngày 29/07/2026.
3. Chọn khung sớm nhất còn trống là 09:00.
4. Đặt lịch thành công với mã `BK00137`.
5. Tra lại danh sách lịch bằng `list_bookings['0912345678']`.

Đây là bằng chứng Agent duy trì được thực thể qua lịch sử hội thoại thay vì yêu cầu khách nhập lại UUID 36 ký tự.

---

## 📌 7. KẾT LUẬN

- Chatbot Baseline phù hợp với câu hỏi kiến thức chung nhưng không thể cung cấp dữ liệu căn hộ có bằng chứng hoặc thực hiện đặt lịch.
- ReAct Agent đạt **96/104**, hoàn thành tốt các luồng tra cứu và chuỗi hành động nhiều bước.
- Trace #5 chứng minh rõ `Thought → Action → Observation` và sự phụ thuộc dữ liệu giữa các bước.
- Các điểm cần cải thiện nằm ở việc đưa bằng chứng vào Final Answer và thống nhất tiêu chí chấm cho các trường hợp Agent từ chối sớm mà không gọi tool.
- Kết quả cần được đọc cùng lưu ý của script: tiêu chí Factual vẫn nên có người review thủ công.
